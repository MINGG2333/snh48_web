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
        self.assertIn('autocomplete="off"', template)
        self.assertNotIn('localStorage.getItem("snh48_feedback_chat_id")', template)
        self.assertNotIn('localStorage.setItem("snh48_feedback_chat_id"', template)
        self.assertIn('fetch("/api/feedback-chat/history"', template)
        self.assertIn('fetch("/api/feedback-chat/message"', template)
        self.assertIn('href="/complaint"', template)

    def test_ob_tools_are_modal_and_chat_refresh_is_separate(self) -> None:
        template = (ROOT / "website/templates/ob.html").read_text(encoding="utf-8")
        for element_id in ("inboxOpenBtn", "inboxModal", "inboxClose", "chatOpenBtn", "chatAdminModal", "chatAdminClose"):
            self.assertIn(f'id="{element_id}"', template)
        self.assertIn("setObToolScrollLocked", template)
        self.assertIn("body.style.position = 'fixed'", template)
        self.assertIn("}, 3000);", template)
        self.assertIn("chatRefreshBusy", template)


if __name__ == "__main__":
    unittest.main()
