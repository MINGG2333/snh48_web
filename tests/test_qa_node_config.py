import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class QaNodeConfigTests(unittest.TestCase):
    def test_disabled_node_has_local_unavailable_page_and_no_qa_api(self) -> None:
        script = textwrap.dedent(
            """
            from fastapi.testclient import TestClient
            from website.main import app

            client = TestClient(app, base_url="http://localhost")
            assert client.get("/api/qa/config").status_code == 404

            response = client.get("/qa")
            assert response.status_code == 503
            assert "当前服务器未启用 AI 问答服务" in response.text
            assert "xn--6qq986b3xl" not in response.text
            """
        )
        env = os.environ.copy()
        env["QA_ENABLED"] = "false"
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
