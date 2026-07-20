from __future__ import annotations

import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "deploy.py"
SPEC = importlib.util.spec_from_file_location("snh48_web_deploy", MODULE_PATH)
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class RoomVoiceSyncCommandTests(unittest.TestCase):
    def test_pull_and_fallback_push_commit_manifest_last(self) -> None:
        deploy_root = MODULE_PATH.parent
        for filename in ("sync-from-tencent.sh", "sync-to-aliyun.sh"):
            script = (deploy_root / filename).read_text(encoding="utf-8")
            payload_at = script.index("--delay-updates --exclude='/manifest.json'")
            manifest_copy_at = script.index("manifest.json\" \"$", payload_at)
            commit_at = script.index("mv -f", manifest_copy_at)
            cleanup_at = script.index("--delete-delay --ignore-existing", commit_at)
            self.assertLess(payload_at, manifest_copy_at, filename)
            self.assertLess(manifest_copy_at, commit_at, filename)
            self.assertLess(commit_at, cleanup_at, filename)

    def test_manifest_last_sync_orders_payload_manifest_and_cleanup(self) -> None:
        source = {
            "ssh": "source.example",
            "data_paths": [
                {
                    "type": "dir",
                    "path": "/data/room_voice_replays",
                    "delete": True,
                    "manifest_last": True,
                }
            ],
        }
        destination = {"ssh": "dest.example"}
        calls = []

        with mock.patch.object(
            deploy,
            "remote",
            side_effect=lambda target, command, dry_run=False: calls.append(command),
        ):
            deploy.sync_data(source, destination, Namespace(dry_run=False))

        self.assertEqual(calls[0], "mkdir -p /data/room_voice_replays")
        command = calls[1]
        payload_at = command.index("--delay-updates --exclude=/manifest.json")
        manifest_at = command.index("manifest.json dest.example:/data/room_voice_replays/.manifest.json.sync")
        commit_at = command.index("mv -f")
        cleanup_at = command.index("--delete-delay --ignore-existing")
        self.assertLess(payload_at, manifest_at)
        self.assertLess(manifest_at, commit_at)
        self.assertLess(commit_at, cleanup_at)


if __name__ == "__main__":
    unittest.main()
