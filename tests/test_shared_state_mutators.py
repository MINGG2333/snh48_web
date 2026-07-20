from __future__ import annotations

import unittest
from unittest import mock

from website.memories_api import _review_memory_mutator, _seed_merge_mutator, _submit_memory_mutator
from website.room_messages_api import _ignore_latest_mutator, _undo_latest_mutator
from website.score_gifts_api import _business_review_mutator
from website.scroller_api.router import _set_texts_mutator


class SharedStateMutatorTests(unittest.TestCase):
    def test_scroller_replaces_only_managed_texts(self) -> None:
        state, result = _set_texts_mutator(
            {"version": 2, "texts": ["旧"], "future_field": True},
            {"texts": [" 新 ", "第二条"]},
        )
        self.assertEqual(state["texts"], ["新", "第二条"])
        self.assertTrue(state["future_field"])
        self.assertEqual(result["count"], 2)

    def test_room_ignore_and_undo_preserve_other_batches(self) -> None:
        summary = {
            "latest_unreplied_gift_batch": {
                "start_message_id": "gift-2",
                "end_message_id": "gift-2",
                "gift_message_ids": ["gift-2"],
            }
        }
        initial = {
            "version": 2,
            "ignored_batches": [{"batch_id": "older", "gift_message_ids": ["gift-1"]}],
        }
        with mock.patch("website.room_messages_api._load_dataset", return_value=([], summary)):
            state, result = _ignore_latest_mutator(initial, {})
        self.assertEqual(len(state["ignored_batches"]), 2)
        self.assertEqual(result["ignored_batch"]["gift_message_ids"], ["gift-2"])

        state, undone = _undo_latest_mutator(state, {})
        self.assertEqual([item["batch_id"] for item in state["ignored_batches"]], ["older"])
        self.assertEqual(undone["undone_batch"]["gift_message_ids"], ["gift-2"])

    def test_score_review_keeps_analyzer_and_other_records(self) -> None:
        item = {
            "id": "live-1",
            "source": "live",
            "event_time": "2026-07-20 10:00:00",
            "sender_name": "粉丝",
            "sender_id": "1",
            "gift_id": "2",
            "gift_name": "礼物",
            "gift_count": 1,
            "unit_score": 1,
            "total_score": 1,
            "live_id": "live",
            "live_title": "直播",
            "live_bj_time": "2026-07-20 09:00:00",
            "danmu_offset": "00:10",
            "danmu_file": "test.lrc",
            "danmu_line_number": 1,
            "raw_content": "礼物弹幕",
        }
        state = {"version": 1, "records": {"other": {"status": "redeemed"}}}
        payload = {
            "action": "override",
            "item_id": "live-1",
            "business_status": "uncertain",
            "reasoning": "人工核对",
        }
        with mock.patch("website.score_gifts_api._load_dataset", return_value={"items": [item]}):
            updated, result = _business_review_mutator(state, payload)
        self.assertIn("other", updated["records"])
        self.assertEqual(updated["records"]["live-1"]["status"], "uncertain")
        self.assertEqual(result["item_id"], "live-1")

    def test_memory_submit_review_and_seed_merge_keep_manual_state(self) -> None:
        record = {
            "id": "MEM-1",
            "audit_status": "pending_manual",
            "visibility": "pending",
            "confirmation_status": "unconfirmed",
        }
        state, _ = _submit_memory_mutator({"version": 1, "items": []}, {"record": record})
        state, _ = _review_memory_mutator(
            state, {"id": "MEM-1", "action": "approve", "actor": "fanclub", "reason": "核对通过"}
        )
        generated = {"id": "MEM-1", "audit_status": "auto_approved", "visibility": "public"}
        state, result = _seed_merge_mutator(state, {"items": [generated]})
        self.assertEqual(state["items"][0]["audit_status"], "approved")
        self.assertEqual(state["items"][0]["audit_reason"], "核对通过")
        self.assertEqual(result["total"], 1)


if __name__ == "__main__":
    unittest.main()
