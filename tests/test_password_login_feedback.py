from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PasswordLoginFeedbackTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_header_password_pages_verify_before_loading_data(self) -> None:
        cases = (
            ("website/templates/gift_reply_senders.html", "/api/gift-replies/verify"),
            ("website/templates/gift_replies.html", "/api/gift-replies/verify"),
            ("website/templates/room_messages.html", "/api/room-messages/verify"),
            ("website/templates/score_gifts.html", "/api/score-gifts/verify"),
            ("website/templates/pk_score.html", "/api/pk-score/verify"),
            ("website/templates/ob.html", "/api/ob/verify"),
        )
        for template, verify_path in cases:
            with self.subTest(template=template):
                source = self.read(template)
                self.assertIn(verify_path, source)
                self.assertIn("正在验证密码…", source)
                self.assertIn("密码正确，正在加载", source)
                self.assertIn("重试加载", source)

    def test_memories_uses_lightweight_verify_and_retry_state(self) -> None:
        template = self.read("website/templates/memories.html")
        script = self.read("website/static/js/memories.js")
        self.assertIn('id="memoriesLoginSubmit"', template)
        self.assertIn("/api/memories/verify", script)
        self.assertIn("密码正确，正在加载记忆…", script)
        self.assertIn("重试加载", script)

    def test_cookie_login_pages_distinguish_verification_and_data_loading(self) -> None:
        cases = (
            ("website/templates/flip_cards.html", "密码正确，正在加载翻牌记录…"),
            ("website/templates/room_voice_replays.html", "密码正确，正在加载录音列表…"),
        )
        for template, loading_message in cases:
            with self.subTest(template=template):
                source = self.read(template)
                self.assertIn(loading_message, source)
                self.assertIn("重试加载", source)
                self.assertIn("loginVerified", source)

    def test_password_pages_do_not_show_initial_auth_error(self) -> None:
        cases = (
            "website/templates/ob.html",
            "website/templates/flip_cards.html",
            "website/templates/gift_replies.html",
            "website/templates/gift_reply_senders.html",
            "website/templates/room_messages.html",
        )
        for template in cases:
            with self.subTest(template=template):
                source = self.read(template)
                self.assertRegex(source, r'id="loginError"[^>]*></(?:div|p)>')

        flip = self.read("website/templates/flip_cards.html")
        self.assertIn("error.status === 401 || error.status === 403", flip)
        self.assertIn('showLogin("")', flip)


if __name__ == "__main__":
    unittest.main()
