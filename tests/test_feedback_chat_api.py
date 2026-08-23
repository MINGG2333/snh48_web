from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from website import action_inbox
from website import feedback_chat_api as chat_api


class FeedbackChatApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(action_inbox.cfg, "ACTION_INBOX_ROOT", str(self.root / "inbox")),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_OUTBOX_ROOT", str(self.root / "outbox")),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_SYNC_ENABLED", False),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_PEER", ""),
            mock.patch.object(chat_api, "check_feedback_chat_limit"),
            mock.patch.object(chat_api, "check_feedback_chat_history_limit"),
        ]
        for patcher in self.patches:
            patcher.start()
        self.request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_identifier_history_and_admin_reply_round_trip(self) -> None:
        identifier = "idol-test-2026"
        sent = chat_api.send_message(
            chat_api.ChatMessageRequest(identifier=identifier, content="网站筛选在手机上不方便"),
            self.request,
            chat_api.Response(),
        )
        self.assertEqual(sent["messages"][-1]["sender"], "visitor")
        conversation_id = sent["conversation_id"]
        self.assertNotIn(identifier, json.dumps(sent, ensure_ascii=False))

        chat_api.reply_message(
            chat_api.AdminReplyRequest(conversation_id=conversation_id, content="收到，我们会尽快处理"),
            chat_api.Response(),
            True,
        )
        history = chat_api.get_history(
            chat_api.ChatIdentifierRequest(identifier=identifier),
            self.request,
            chat_api.Response(),
        )
        self.assertEqual([item["sender"] for item in history["messages"]], ["visitor", "support"])

        conversations = chat_api.list_conversations(chat_api.Response(), True)
        self.assertEqual(conversations["conversations"][0]["conversation_id"], conversation_id)
        self.assertEqual(conversations["conversations"][0]["user_identifier"], identifier)
        self.assertFalse(conversations["conversations"][0]["pending_reply"])

        admin_history = chat_api.get_admin_history(
            chat_api.AdminConversationRequest(conversation_id=conversation_id),
            chat_api.Response(),
            True,
        )
        self.assertEqual(admin_history["user_identifier"], identifier)

        event_files = list((self.root / "inbox" / "events").glob("*.json"))
        self.assertEqual(len(event_files), 2)
        self.assertIn(identifier, event_files[0].read_text(encoding="utf-8"))

    def test_identifier_and_content_validation(self) -> None:
        with self.assertRaises(ValueError):
            chat_api.ChatIdentifierRequest(identifier="abc")
        with self.assertRaises(ValueError):
            chat_api.ChatMessageRequest(identifier="valid-code", content=" ")
        with self.assertRaises(ValueError):
            chat_api.AdminConversationRequest(conversation_id="not-a-hash")
        with self.assertRaises(ValueError):
            chat_api.AdminWatchRequest(revision="not-a-revision")

    async def test_visitor_watch_returns_as_soon_as_reply_arrives(self) -> None:
        identifier = "visitor-watch-2026"
        sent = chat_api.send_message(
            chat_api.ChatMessageRequest(identifier=identifier, content="第一条消息"),
            self.request,
            chat_api.Response(),
        )
        conversation_id = sent["conversation_id"]
        cursor = sent["messages"][-1]["message_id"]

        async def add_reply() -> None:
            await asyncio.sleep(0.02)
            chat_api.reply_message(
                chat_api.AdminReplyRequest(conversation_id=conversation_id, content="即时回复"),
                chat_api.Response(),
                True,
            )

        task = asyncio.create_task(add_reply())
        with (
            mock.patch.object(chat_api, "_WATCH_TIMEOUT_SECONDS", 0.5),
            mock.patch.object(chat_api, "_WATCH_POLL_SECONDS", 0.005),
        ):
            watched = await chat_api.watch_history(
                chat_api.ChatWatchRequest(identifier=identifier, after_message_id=cursor),
                self.request,
                chat_api.Response(),
            )
        await task

        self.assertTrue(watched["changed"])
        self.assertEqual(watched["messages"][-1]["content"], "即时回复")

    async def test_admin_watch_returns_updated_conversation_revision(self) -> None:
        initial = chat_api.list_conversations(chat_api.Response(), True)
        identifier = "admin-watch-2026"

        async def add_message() -> None:
            await asyncio.sleep(0.02)
            chat_api.send_message(
                chat_api.ChatMessageRequest(identifier=identifier, content="需要立即看到"),
                self.request,
                chat_api.Response(),
            )

        task = asyncio.create_task(add_message())
        with (
            mock.patch.object(chat_api, "_WATCH_TIMEOUT_SECONDS", 0.5),
            mock.patch.object(chat_api, "_WATCH_POLL_SECONDS", 0.005),
        ):
            watched = await chat_api.watch_conversations(
                chat_api.AdminWatchRequest(revision=initial["revision"]),
                chat_api.Response(),
                True,
            )
        await task

        self.assertTrue(watched["changed"])
        self.assertNotEqual(watched["revision"], initial["revision"])
        self.assertEqual(watched["conversations"][0]["user_identifier"], identifier)


if __name__ == "__main__":
    unittest.main()
