from __future__ import annotations

import importlib.util
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "deploy.py"
SPEC = importlib.util.spec_from_file_location("snh48_web_deploy_shared_state", MODULE_PATH)
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class SharedStateSyncExcludeTests(unittest.TestCase):
    def test_manual_data_sync_excludes_authoritative_business_state(self) -> None:
        source = {
            "ssh": "source.example",
            "data_paths": [{
                "type": "dir",
                "path": "/data/score_gifts",
                "delete": True,
                "excludes": ["live_business_fulfillments.json", ".*.lock"],
            }],
        }
        destination = {"ssh": "dest.example"}
        calls: list[str] = []

        with mock.patch.object(
            deploy,
            "remote",
            side_effect=lambda target, command, dry_run=False: calls.append(command),
        ):
            deploy.sync_data(source, destination, Namespace(dry_run=False))

        self.assertIn("--exclude=live_business_fulfillments.json", calls[1])
        self.assertIn("--exclude='.*.lock'", calls[1])


if __name__ == "__main__":
    unittest.main()
