from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FlipCardsConfigTests(unittest.TestCase):
    def run_config(self, *, node: str, enabled: str) -> list[str]:
        environment = dict(os.environ)
        environment.update({
            "SHARED_STATE_NODE_ID": node,
            "SHARED_STATE_IS_PRIMARY": "true" if node == "tencent" else "false",
            "FLIP_CARDS_ACCOUNT_ADMIN_ENABLED": enabled,
            "FLIP_CARDS_ACCOUNT_ADMIN_PYTHON": "",
            "FLIP_CARDS_ACCOUNT_ADMIN_SCRIPT": "",
        })
        proc = subprocess.run(
            [
                str(ROOT / "venv" / "bin" / "python"),
                "-c",
                (
                    "from website import config as c; "
                    "print(c.FLIP_CARDS_ACCOUNT_ADMIN_ENABLED); "
                    "print(c.FLIP_CARDS_ACCOUNT_ADMIN_PYTHON); "
                    "print(c.FLIP_CARDS_ACCOUNT_ADMIN_SCRIPT)"
                ),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        )
        return proc.stdout.splitlines()

    def test_blank_values_follow_node_role_and_keep_default_paths(self) -> None:
        tencent = self.run_config(node="tencent", enabled="")
        aliyun = self.run_config(node="aliyun", enabled="")

        self.assertEqual(tencent[0], "True")
        self.assertEqual(aliyun[0], "False")
        self.assertTrue(tencent[1].endswith("/snh48-fan-hub/venv/bin/python3"))
        self.assertTrue(tencent[2].endswith("/snh48-fan-hub/scripts/web/flip_account_admin.py"))


if __name__ == "__main__":
    unittest.main()
