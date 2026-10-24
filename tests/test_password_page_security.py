from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "website" / "templates"
STATIC_JS = ROOT / "website" / "static" / "js"
WEB_STORAGE_PASSWORD = re.compile(
    r"(?:sessionStorage|localStorage)\.(?:getItem|setItem)\s*\(",
    re.IGNORECASE,
)


class PasswordPageSecurityTests(unittest.TestCase):
    def test_password_inputs_do_not_use_current_password_autocomplete(self) -> None:
        offenders = []
        for path in sorted(TEMPLATES.glob("*.html")):
            source = path.read_text(encoding="utf-8")
            if 'autocomplete="current-password"' in source:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "密码页必须使用 autocomplete=new-password，避免浏览器密码管理器自动保存")

    def test_password_pages_do_not_persist_password_in_web_storage(self) -> None:
        offenders = []
        paths = sorted(TEMPLATES.glob("*.html")) + sorted(STATIC_JS.glob("*.js"))
        for path in paths:
            source = path.read_text(encoding="utf-8")
            if "password" not in source.lower() and "passwd" not in source.lower():
                continue
            for line_number, line in enumerate(source.splitlines(), 1):
                lowered = line.lower()
                if (
                    ("password" in lowered or "passwd" in lowered)
                    and WEB_STORAGE_PASSWORD.search(line)
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual(offenders, [], "密码不得写入 localStorage/sessionStorage；请改用 HttpOnly Cookie")

    def test_redblue_uses_server_cookie_login_not_password_storage(self) -> None:
        template = TEMPLATES / "redblue_ledger_2026.html"
        if not template.is_file():
            self.skipTest("redblue 页面未在当前工作区")
        source = template.read_text(encoding="utf-8")
        self.assertIn("/api/redblue/login", source)
        self.assertIn("/api/redblue/logout", source)
        self.assertIn("/api/redblue/verify", source)
        self.assertNotIn("X-Redblue-Password", source)
        self.assertNotIn("sessionStorage.setItem", source)
        self.assertNotIn("localStorage.setItem", source)


if __name__ == "__main__":
    unittest.main()
