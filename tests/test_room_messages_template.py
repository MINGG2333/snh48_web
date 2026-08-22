from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RoomMessagesTemplateTests(unittest.TestCase):
    def test_room_controls_cover_mobile_filter_and_feedback_workflow(self) -> None:
        template = (ROOT / "website/templates/room_messages.html").read_text(encoding="utf-8")

        self.assertNotIn('刷新 <strong id="refreshSeconds">', template)
        self.assertIn('id="filterModal"', template)
        self.assertIn("overflow-y: auto;", template)
        self.assertIn("-webkit-overflow-scrolling: touch;", template)
        self.assertIn('unrepliedPanel.classList.toggle("visible", shouldShow)', template)
        self.assertIn('function isGiftReplyFamilyView()', template)
        self.assertIn('id="feedbackNav"', template)
        self.assertIn("background: rgba(98, 168, 255, 0.14);", template)
        self.assertIn('id="feedbackForm"', template)
        self.assertIn('fetch("/api/complaint/submit"', template)
        self.assertIn('href="/complaint"', template)


if __name__ == "__main__":
    unittest.main()
