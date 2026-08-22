from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RoomMessagesTemplateTests(unittest.TestCase):
    def test_room_controls_keep_mobile_filter_and_gift_reply_visibility(self) -> None:
        template = (ROOT / "website/templates/room_messages.html").read_text(encoding="utf-8")

        self.assertNotIn('刷新 <strong id="refreshSeconds">', template)
        self.assertIn('id="filterModal"', template)
        self.assertIn("overflow-y: auto;", template)
        self.assertIn("-webkit-overflow-scrolling: touch;", template)
        self.assertIn('id="latestTime">更新时间：-', template)
        self.assertIn('data.refreshed_at || "-"', template)
        self.assertIn("room-filters-open", template)
        self.assertIn('unrepliedPanel.classList.toggle("visible", shouldShow)', template)
        self.assertIn('function isGiftReplyFamilyView()', template)
        self.assertNotIn('id="feedbackNav"', template)
        self.assertNotIn('id="feedbackForm"', template)

    def test_gift_senders_contains_customer_service_chat(self) -> None:
        template = (ROOT / "website/templates/gift_reply_senders.html").read_text(encoding="utf-8")

        self.assertIn('id="supportChatNav"', template)
        self.assertIn('class="fas fa-headset"', template)
        self.assertIn('id="supportChatModal"', template)
        self.assertIn('id="giftFilterModal"', template)
        self.assertIn('id="giftFilterToggle"', template)
        self.assertIn('<span>反馈</span>', template)
        self.assertNotIn('<span>客服反馈</span>', template)
        self.assertIn('id="supportChatIdentifier"', template)
        self.assertIn('fetch("/api/feedback-chat/history"', template)
        self.assertIn('fetch("/api/feedback-chat/message"', template)
        self.assertIn('href="/complaint"', template)


if __name__ == "__main__":
    unittest.main()
