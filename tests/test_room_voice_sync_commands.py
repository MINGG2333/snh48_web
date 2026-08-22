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

    def test_flip_web_sync_commits_accounts_manifest_last(self) -> None:
        deploy_root = MODULE_PATH.parent
        for filename in ("sync-from-tencent.sh", "sync-to-aliyun.sh"):
            script = (deploy_root / filename).read_text(encoding="utf-8")
            audio_at = script.index("flip_data/audio done")
            video_at = script.index("flip_data/video done")
            payload_at = script.index("--delay-updates --exclude='/accounts.json'")
            manifest_at = script.index("accounts.json\"", payload_at)
            commit_at = script.index("mv -f", manifest_at)
            cleanup_at = script.index("--delete-delay --ignore-existing", commit_at)
            self.assertLess(audio_at, payload_at, filename)
            self.assertLess(video_at, payload_at, filename)
            self.assertLess(payload_at, manifest_at, filename)
            self.assertLess(manifest_at, commit_at, filename)
            self.assertLess(commit_at, cleanup_at, filename)

        data_paths = [item["path"] for item in deploy.BUILTIN_TARGETS["tencent"]["data_paths"]]
        audio_at = data_paths.index("/home/snh48-fan-hub/flip_data/audio")
        video_at = data_paths.index("/home/snh48-fan-hub/flip_data/video")
        web_at = data_paths.index("/home/snh48-fan-hub/flip_data/web")
        self.assertLess(audio_at, web_at)
        self.assertLess(video_at, web_at)

    def test_named_manifest_sync_uses_accounts_json(self) -> None:
        source = {
            "ssh": "source.example",
            "data_paths": [{
                "type": "dir",
                "path": "/data/flip_data/web",
                "delete": True,
                "manifest_last": True,
                "manifest_name": "accounts.json",
            }],
        }
        calls = []
        with mock.patch.object(
            deploy,
            "remote",
            side_effect=lambda target, command, dry_run=False: calls.append(command),
        ):
            deploy.sync_data(source, {"ssh": "dest.example"}, Namespace(dry_run=False))

        command = calls[1]
        self.assertIn("--exclude=/accounts.json", command)
        self.assertIn("accounts.json dest.example:/data/flip_data/web/.accounts.json.sync", command)
        self.assertIn("/data/flip_data/web/accounts.json", command)


if __name__ == "__main__":
    unittest.main()
