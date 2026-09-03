from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from script.website_observability import ObservabilityError, archive_logs, collect_metrics


class WebsiteObservabilityTests(unittest.TestCase):
    def test_collects_incremental_access_and_resource_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            access = root / "snh48_access.log"
            access.write_text(
                '127.0.0.1 - - [04/Sep/2026:00:01:00 +0800] "GET / HTTP/1.1" 200 100 "-" "test"\n'
                '127.0.0.1 - - [04/Sep/2026:00:01:01 +0800] "GET /static/main.css HTTP/1.1" 200 50 "-" "test"\n',
                encoding="utf-8",
            )
            visitor_file = root / "interaction_logs" / "session_20260904_000000" / "visitor_page_views.jsonl"
            visitor_file.parent.mkdir(parents=True)
            visitor_file.write_text(
                json.dumps({"timestamp": "2026-09-04T00:01:00+08:00", "visitor_id": "visitor-a"})
                + "\n"
                + json.dumps({"timestamp": "2026-09-04T00:02:00+08:00", "visitor_id": "visitor-a"})
                + "\n",
                encoding="utf-8",
            )
            output = root / "metrics"
            first = collect_metrics(
                node_id="test",
                access_patterns=[str(access)],
                active_paths=[str(access)],
                visitor_root=root / "interaction_logs",
                output_dir=output,
            )
            self.assertEqual(first["access_log_files"], 1)
            daily = json.loads((output / "daily.json").read_text(encoding="utf-8"))
            self.assertEqual(daily["days"]["2026-09-04"]["requests"], 2)
            self.assertEqual(daily["days"]["2026-09-04"]["page_requests"], 1)
            self.assertEqual(daily["days"]["2026-09-04"]["unique_visitors"], 1)

            with access.open("a", encoding="utf-8") as handle:
                handle.write(
                    '127.0.0.1 - - [04/Sep/2026:00:03:00 +0800] "GET /timeline HTTP/1.1" 404 20 "-" "test"\n'
                )
            collect_metrics(
                node_id="test",
                access_patterns=[str(access)],
                active_paths=[str(access)],
                visitor_root=root / "interaction_logs",
                output_dir=output,
            )
            daily = json.loads((output / "daily.json").read_text(encoding="utf-8"))
            self.assertEqual(daily["days"]["2026-09-04"]["requests"], 3)
            self.assertEqual(daily["days"]["2026-09-04"]["status_counts"]["404"], 1)

    def test_archive_refuses_deletion_without_cos(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            active = root / "snh48_access.log"
            rotated = root / "snh48_access.log.1"
            active.write_bytes(b"active\n")
            rotated.write_bytes(b"rotated\n" * 4)
            with self.assertRaises(ObservabilityError):
                archive_logs(
                    node_id="test",
                    log_patterns=[str(root / "*.log*")],
                    active_paths=[str(active)],
                    state_dir=root / "archives",
                    threshold_bytes=1,
                    rclone_config=None,
                    credentials_file=None,
                    remote="cjy_archive",
                    bucket="bucket",
                    prefix="website-logs",
                )
            self.assertTrue(active.exists())
            self.assertTrue(rotated.exists())


if __name__ == "__main__":
    unittest.main()
