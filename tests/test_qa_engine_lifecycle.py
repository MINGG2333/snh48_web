import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class QaEngineLifecycleTests(unittest.TestCase):
    def test_timeout_is_reported_and_finished_worker_can_retry(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            import time
            import types

            defaults = types.SimpleNamespace(
                vector_top_k=1,
                bm25_top_k=1,
                context_window=1,
                vector_score_threshold=0.1,
                bm25_score_threshold=0.1,
                analysis_batch_size=1,
                synthesis_context_window=1,
                synthesis_batch_trigger_count=1,
                synthesis_batch_size=1,
            )
            kb_pkg = types.ModuleType("kb_qa")
            kb_config = types.ModuleType("kb_qa.config")
            kb_config.KB_QA_DEFAULTS = defaults
            kb_pkg.__path__ = []
            sys.modules["kb_qa"] = kb_pkg
            sys.modules["kb_qa.config"] = kb_config

            from website import config as cfg
            cfg.QA_ENGINE_LOAD_TIMEOUT_SECONDS = 1
            import importlib
            qa = importlib.import_module("website.qa_api.router")

            class FakeEngine:
                class Store:
                    segments = {"one": object()}
                store = Store()

            calls = []

            def slow_build():
                calls.append("slow")
                time.sleep(2.0)
                raise RuntimeError("slow failure")

            qa._build_qa_engine = slow_build
            assert qa.warmup_qa_engine_async() is True
            time.sleep(1.2)
            timed_out = qa.get_status()
            assert timed_out["loading"] is False, timed_out
            assert timed_out["ready"] is False, timed_out
            assert timed_out["retryable"] is True, timed_out
            assert "超时" in timed_out["message"], timed_out
            assert calls == ["slow"], calls

            # The timed-out worker is still alive, so status checks must not
            # start a duplicate expensive load.
            qa.get_status()
            assert calls == ["slow"], calls

            time.sleep(1.1)

            def fast_build():
                calls.append("fast")
                return FakeEngine()

            qa._build_qa_engine = fast_build
            qa.get_status()
            deadline = time.time() + 2
            while time.time() < deadline:
                status = qa.get_status()
                if status["ready"]:
                    break
                time.sleep(0.05)
            assert status["ready"] is True, status
            assert status["loading"] is False, status
            assert status["stats"]["segment_count"] == 1, status
            assert calls == ["slow", "fast"], calls
            """
        )
        env = os.environ.copy()
        env["QA_ENABLED"] = "true"
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
