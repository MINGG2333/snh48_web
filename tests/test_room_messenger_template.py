from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "website" / "templates" / "room_messenger.html"
SCRIPT = ROOT / "website" / "static" / "js" / "room_messenger.js"


class RoomMessengerTemplateTests(unittest.TestCase):
    def test_template_uses_cookie_login_and_tracker(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("/static/js/room_messenger.js", source)
        self.assertIn("/static/js/tracker.js", source)
        self.assertIn('autocomplete="new-password"', source)
        self.assertNotIn('autocomplete="current-password"', source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertIn("noindex,nofollow", source)
        self.assertIn("确认发送", source)
        self.assertIn("每日", source)
        self.assertIn("定时", source)
        self.assertIn("批量", source)
        self.assertIn("deleteModal", source)
        self.assertIn("switchAccountWrap", source)
        self.assertIn("tokenWarning", source)
        self.assertNotIn("个人号专用", source)
        self.assertNotIn("HttpOnly", source)

    def test_script_uses_api_prefix_and_never_persists_password(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('var API_ROOT = "/api/room-messenger"', source)
        self.assertIn("/login", source)
        self.assertIn("/logout", source)
        self.assertIn("/verify", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("X-Room-Messenger-Password", source)
        self.assertIn("confirm_word", source)
        self.assertIn("toShanghaiIso", source)
        self.assertIn("selectedIds: new Set()", source)
        self.assertIn("selectMode: false", source)
        self.assertIn("deleteTargets: []", source)

    def test_mobile_and_accessibility_hooks_exist(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('name="viewport"', source)
        self.assertIn("aria-modal", source)
        self.assertIn("rm-mobile-only", source)
        self.assertIn("sidebarBackdrop", source)


if __name__ == "__main__":
    unittest.main()
