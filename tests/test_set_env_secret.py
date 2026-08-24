from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from deploy.set_env_secret import update_env_secret


class SetEnvSecretTests(unittest.TestCase):
    def test_updates_atomically_without_changing_other_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text("# comment\nTARGET=old\nOTHER=value\n", encoding="utf-8")
            path.chmod(0o640)

            update_env_secret(path, "TARGET", "new-secret")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "# comment\nTARGET=new-secret\nOTHER=value\n",
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_creates_private_file_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private" / "monitor.env"

            update_env_secret(path, "TOKEN", "secret", create=True)

            self.assertEqual(path.read_text(encoding="utf-8"), "TOKEN=secret\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_rejects_duplicate_keys_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            duplicate = root / "duplicate.env"
            duplicate.write_text("TOKEN=one\nTOKEN=two\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                update_env_secret(duplicate, "TOKEN", "replacement")

            target = root / "target.env"
            target.write_text("TOKEN=one\n", encoding="utf-8")
            symlink = root / "symlink.env"
            os.symlink(target, symlink)
            with self.assertRaises(ValueError):
                update_env_secret(symlink, "TOKEN", "replacement")


if __name__ == "__main__":
    unittest.main()
