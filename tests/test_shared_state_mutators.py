from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException

from website.business_api import _batch_to_mail_mutator, _to_mail_mutator
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

    def test_business_batch_to_mail_converts_physical_and_keeps_virtual(self) -> None:
        state = {
            "version": 1,
            "tasks": [
                {
                    "id": "t-physical",
                    "fan_name": "粉丝甲",
                    "biz_type": "手写奖状",
                    "status": "未完成",
                    "planned_date": "2026-10-01",
                    "note": "领取方式：面取；礼物已买；10/01 面交",
                },
                {
                    "id": "t-virtual",
                    "fan_name": "粉丝甲",
                    "biz_type": "点唱",
                    "status": "未完成",
                    "planned_date": "2026-10-02",
                    "note": "领取方式：面取",
                },
                {
                    "id": "t-done",
                    "fan_name": "粉丝甲",
                    "biz_type": "随机拼豆",
                    "status": "已完成",
                    "planned_date": "2026-09-01",
                    "note": "领取方式：面取",
                },
            ],
        }
        # 前端把该粉丝卡片所有未完成实体业务的 id 都传过来，虚拟/已完成即使误传也应被跳过
        updated, result = _batch_to_mail_mutator(
            state, {"ids": ["t-physical", "t-virtual", "t-done"]}
        )

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual([task["id"] for task in result["tasks"]], ["t-physical"])
        by_id = {task["id"]: task for task in updated["tasks"]}

        physical = by_id["t-physical"]
        self.assertEqual(physical["planned_date"], "")
        self.assertIn("领取方式：邮寄", physical["note"])
        self.assertIn("收件信息待收集", physical["note"])
        # 其他备注段保留
        self.assertIn("礼物已买", physical["note"])
        self.assertIn("10/01 面交", physical["note"])
        self.assertNotIn("领取方式：面取", physical["note"])

        # 虚拟类业务不受影响
        virtual = by_id["t-virtual"]
        self.assertEqual(virtual["planned_date"], "2026-10-02")
        self.assertEqual(virtual["note"], "领取方式：面取")

        # 已完成业务不受影响
        done = by_id["t-done"]
        self.assertEqual(done["planned_date"], "2026-09-01")
        self.assertEqual(done["note"], "领取方式：面取")

    def test_business_batch_to_mail_matches_single_to_mail_note(self) -> None:
        def make_state() -> dict:
            return {
                "version": 1,
                "tasks": [
                    {
                        "id": "t-1",
                        "fan_name": "粉丝乙",
                        "biz_type": "指定拼豆",
                        "status": "未完成",
                        "planned_date": "2026-10-05",
                        "note": "现场交付；已付款",
                    }
                ],
            }

        single, single_result = _to_mail_mutator(make_state(), {"ids": ["t-1"]})
        batch, batch_result = _batch_to_mail_mutator(make_state(), {"ids": ["t-1"]})
        self.assertEqual(single["tasks"][0]["note"], batch["tasks"][0]["note"])
        self.assertEqual(single_result["updated_count"], batch_result["updated_count"])
        self.assertNotIn("现场交付", batch["tasks"][0]["note"])
        self.assertIn("已付款", batch["tasks"][0]["note"])

    def test_business_batch_to_mail_rejects_invalid_payload(self) -> None:
        with self.assertRaises(HTTPException):
            _batch_to_mail_mutator({"tasks": []}, {"ids": []})
        with self.assertRaises(HTTPException):
            _batch_to_mail_mutator({"tasks": []}, {"ids": ["bad id!"]})

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
