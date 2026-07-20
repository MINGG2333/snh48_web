from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from website import action_inbox
from website import shared_runtime_state as shared


class SharedRuntimeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scroller = self.root / "scroller.json"
        self.room_ignore = self.root / "room-ignore.json"
        self.score_data = self.root / "score" / "score_gifts.json"
        self.memories = self.root / "memories.json"
        self.patches = [
            mock.patch.object(shared.cfg, "SCROLLER_TEXTS_PATH", str(self.scroller)),
            mock.patch.object(shared.cfg, "ROOM_MESSAGES_IGNORE_PATH", str(self.room_ignore)),
            mock.patch.object(shared.cfg, "SCORE_GIFTS_DATA_PATH", str(self.score_data)),
            mock.patch.object(shared.cfg, "MEMORIES_DATA_PATH", str(self.memories)),
            mock.patch.object(shared.cfg, "SHARED_STATE_HISTORY_ROOT", str(self.root / "history")),
            mock.patch.object(shared.cfg, "SHARED_STATE_OUTBOX_ROOT", str(self.root / "outbox")),
            mock.patch.object(shared.cfg, "ACTION_INBOX_ROOT", str(self.root / "inbox")),
            mock.patch.object(shared.cfg, "SHARED_STATE_SYNC_ENABLED", False),
            mock.patch.object(shared.cfg, "SHARED_STATE_IS_PRIMARY", True),
            mock.patch.object(shared.cfg, "SHARED_STATE_PEER", ""),
            mock.patch.object(shared.cfg, "SHARED_STATE_NODE_ID", "tencent"),
        ]
        for patcher in self.patches:
            patcher.start()

        def append_text(document, payload):
            document.setdefault("texts", []).append(str(payload["text"]))
            return document, {"count": len(document["texts"])}

        shared.register_mutator("scroller", "test_append", append_text)

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_legacy_state_gets_versioned_and_mutation_is_idempotent(self) -> None:
        self.scroller.write_text(json.dumps(["旧背景词"], ensure_ascii=False), encoding="utf-8")
        baseline = shared.ensure_baseline("scroller")
        baseline_revision = baseline["_state"]["revision"]

        first = shared.execute_mutation(
            "scroller", "test_append", {"text": "新背景词"}, operation_id="test-operation-1"
        )
        duplicate = shared.execute_mutation(
            "scroller", "test_append", {"text": "不应再次写入"}, operation_id="test-operation-1"
        )

        self.assertEqual(first["state"]["texts"], ["旧背景词", "新背景词"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["state"]["texts"], ["旧背景词", "新背景词"])
        self.assertEqual(len(shared.list_history("scroller")), 2)

        restored = shared.restore_revision("scroller", baseline_revision)
        self.assertEqual(restored["state"]["texts"], ["旧背景词"])
        self.assertNotEqual(restored["state"]["_state"]["revision"], baseline_revision)

    def test_delayed_replica_revision_cannot_roll_back_newer_state(self) -> None:
        self.scroller.write_text(json.dumps(["起点"], ensure_ascii=False), encoding="utf-8")
        older = shared.ensure_baseline("scroller")
        newer = shared.execute_mutation(
            "scroller", "test_append", {"text": "最新"}, operation_id="test-operation-2"
        )["state"]

        installed = shared.install_replica("scroller", older)

        self.assertEqual(installed["_state"]["revision"], newer["_state"]["revision"])
        self.assertEqual(shared.load_document("scroller")["texts"], ["起点", "最新"])

    def test_failed_replication_is_queued_and_retried(self) -> None:
        self.scroller.write_text(json.dumps(["起点"], ensure_ascii=False), encoding="utf-8")
        with (
            mock.patch.object(shared.cfg, "SHARED_STATE_SYNC_ENABLED", True),
            mock.patch.object(shared.cfg, "SHARED_STATE_PEER", "root@peer"),
            mock.patch.object(
                shared, "peer_command", side_effect=shared.SharedStatePeerError("offline")
            ),
        ):
            state = shared.execute_mutation(
                "scroller", "test_append", {"text": "已本地提交"}, operation_id="test-operation-3"
            )["state"]

        queued = self.root / "outbox" / "state" / "scroller" / f"{state['_state']['revision']}.json"
        self.assertTrue(queued.exists())

        with (
            mock.patch.object(shared.cfg, "SHARED_STATE_SYNC_ENABLED", True),
            mock.patch.object(shared.cfg, "SHARED_STATE_PEER", "root@peer"),
            mock.patch.object(shared, "peer_command", return_value={"ok": True}),
        ):
            stats = shared.retry_outbox_once()
        self.assertEqual(stats["state_sent"], 1)
        self.assertFalse(queued.exists())


class ActionInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(action_inbox.cfg, "ACTION_INBOX_ROOT", str(self.root / "inbox")),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_OUTBOX_ROOT", str(self.root / "outbox")),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_SYNC_ENABLED", False),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_PEER", ""),
            mock.patch.object(action_inbox.cfg, "SHARED_STATE_NODE_ID", "tencent"),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_requests_keep_origin_and_status_events_are_immutable(self) -> None:
        action_inbox.record_request(
            "complaint",
            {"content": "测试投诉"},
            event_id="CMP-1",
            created_at="2026-07-20T10:00:00+08:00",
        )
        action_inbox.install_event({
            "schema_version": 1,
            "event_id": "EMAIL-ALI-1",
            "event_type": "email_request",
            "created_at": "2026-07-20T10:01:00+08:00",
            "origin_node": "aliyun",
            "origin_label": "阿里云 cjy.我爱你",
            "payload": {"email": "example@example.com"},
        })
        action_inbox.record_status("CMP-1", "processing", note="已开始处理")

        requests = {item["event_id"]: item for item in action_inbox.list_requests()}
        self.assertEqual(requests["CMP-1"]["origin_node"], "tencent")
        self.assertEqual(requests["CMP-1"]["origin_label"], "腾讯云 cjy.plus")
        self.assertEqual(requests["CMP-1"]["status"], "processing")
        self.assertEqual(requests["EMAIL-ALI-1"]["origin_node"], "aliyun")
        self.assertEqual(len(list((self.root / "inbox" / "events").glob("*.json"))), 3)

    def test_event_id_collision_is_rejected(self) -> None:
        action_inbox.record_request(
            "complaint", {"content": "第一条"}, event_id="CMP-2", created_at="2026-07-20T10:00:00+08:00"
        )
        with self.assertRaises(action_inbox.InboxError):
            action_inbox.record_request(
                "complaint", {"content": "不同内容"}, event_id="CMP-2", created_at="2026-07-20T10:00:00+08:00"
            )


if __name__ == "__main__":
    unittest.main()
