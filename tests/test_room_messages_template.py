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
        self.assertIn("overflow-y: auto;", template)
        self.assertIn(".page.ready {\n        display: block;", template)
        self.assertIn(".chat-scroll {\n        display: block;", template)
        self.assertIn("position: sticky;", template)
        self.assertIn("top: 0;", template)
        self.assertIn('href="/room-voice-replays"', template)
        self.assertIn('initialTargetId', template)
        self.assertIn("function usesDocumentScroll()", template)
        self.assertIn("window.addEventListener(\"scroll\", function()", template)
        self.assertIn("setCurrentScrollTop(currentScrollHeight())", template)
        self.assertIn("function setRoomPageScrollLocked(locked)", template)
        self.assertIn('document.body.style.position = "fixed"', template)
        self.assertIn("if (open && isMobile) setRoomPageScrollLocked(true)", template)
        self.assertIn("if (!open || !isMobile) setRoomPageScrollLocked(false)", template)
        self.assertIn('input[type="date"]::-webkit-date-and-time-value', template)
        self.assertIn('align-items: center;', template)
        self.assertNotIn('.filter-modal-scroll .field input[type="date"] {\n        display: block;', template)
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
        self.assertIn('input[type="date"]::-webkit-date-and-time-value', template)
        self.assertNotIn('.field input[type="date"] {\n      display: block;', template)
        self.assertIn('<span>反馈</span>', template)
        self.assertNotIn('<span>客服反馈</span>', template)
        self.assertIn('id="supportChatIdentifier"', template)
        self.assertIn('autocomplete="off"', template)
        self.assertIn('class="support-chat-card setup-mode"', template)
        self.assertIn('可以在这里反馈网站中希望改进的地方', template)
        self.assertIn('也可以告诉我们你期待新增的功能', template)
        self.assertIn('id="supportChatStart" type="button">进入反馈</button>', template)
        self.assertNotIn('id="supportChatStart" type="button">进入聊天</button>', template)
        self.assertIn('.support-chat-card.setup-mode { height: auto;', template)
        self.assertIn('supportChatCard.classList.remove("setup-mode")', template)
        self.assertIn('supportChatCard.classList.add("setup-mode")', template)
        self.assertNotIn('localStorage.getItem("snh48_feedback_chat_id")', template)
        self.assertNotIn('localStorage.setItem("snh48_feedback_chat_id"', template)
        self.assertIn('fetch("/api/feedback-chat/history"', template)
        self.assertIn('fetch("/api/feedback-chat/message"', template)
        self.assertIn('fetch("/api/feedback-chat/watch"', template)
        self.assertIn('new AbortController()', template)
        self.assertNotIn('window.setInterval(function() { loadSupportChatHistory(false); }, 1000)', template)
        self.assertIn('href="/complaint"', template)

    def test_ob_tools_are_modal_and_chat_refresh_is_separate(self) -> None:
        template = (ROOT / "website/templates/ob.html").read_text(encoding="utf-8")
        for element_id in ("inboxOpenBtn", "inboxModal", "inboxClose", "chatOpenBtn", "chatAdminModal", "chatAdminClose"):
            self.assertIn(f'id="{element_id}"', template)
        self.assertIn("setObToolScrollLocked", template)
        self.assertIn("body.style.position = 'fixed'", template)
        self.assertIn("fetch('/api/feedback-chat/admin-watch'", template)
        self.assertIn('new AbortController()', template)
        self.assertNotIn('客服会话独立高频刷新', template)
        self.assertIn("chatRefreshBusy", template)
        self.assertIn("!options.loginAttempt", template)
        self.assertIn("const requestPassword = obPassword", template)
        self.assertIn("requestPassword !== obPassword", template)
        self.assertNotIn("setInterval(fetchData, 10000)", template)
        self.assertIn("loginVerified && obPassword && loginOverlay.classList.contains('hidden')", template)


if __name__ == "__main__":
    unittest.main()
