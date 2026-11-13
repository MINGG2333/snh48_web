from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "website/templates/redblue_ledger_2026.html"


class RedblueLedgerTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        if not TEMPLATE.is_file():
            self.skipTest("redblue 页面未在当前工作区")
        self.source = TEMPLATE.read_text(encoding="utf-8")

    def test_batch_proxy_detail_entry_points_exist(self) -> None:
        self.assertIn('id="proxyBatchBtn"', self.source)
        self.assertIn('$("proxyBatchBtn").addEventListener("click", openProxyBatch);', self.source)
        self.assertIn("function selectedProxyEntries()", self.source)
        self.assertIn("function renderProxyBatch(rows, skipped)", self.source)

    def test_batch_proxy_detail_only_accepts_settled_proxy_entries(self) -> None:
        self.assertIn(
            "return selected.has(entry.id) && entry.proxy_settlement && entry.proxy_settlement.method;",
            self.source,
        )
        self.assertIn("请先勾选已完成代投的条目", self.source)

    def test_batch_share_text_aggregates_by_gift_and_name(self) -> None:
        self.assertIn("function batchProxyShareLines(rows)", self.source)
        self.assertIn('var key = giftName + "\\u0000" + person;', self.source)
        self.assertIn('lines.push(group.name + " 的" + score(group.count) + "个" + group.gift);', self.source)
        self.assertIn('var lines = ["包含："];', self.source)

    def test_batch_modal_hides_confirm_button(self) -> None:
        self.assertIn('$("proxyTitle").textContent = "代投明细（合计）";', self.source)
        self.assertIn('$("proxyConfirmBtn").classList.add("hidden");', self.source)

    def test_entry_edit_shows_actual_source_and_scoring(self) -> None:
        self.assertIn("function entryEditSourceLabel(entry)", self.source)
        self.assertIn('return method ? base + "·" + method : base;', self.source)
        self.assertIn(
            '$("entrySource").innerHTML = \'<option value="\' + esc(entry.source || "manual") + \'">\' + esc(entryEditSourceLabel(entry)) + \'</option>\';',
            self.source,
        )

    def test_entry_edit_skips_invalid_duplicate_toggle(self) -> None:
        self.assertIn('id="entryDuplicateField"', self.source)
        self.assertIn(
            "var duplicateLocked = associationEntry || proxyLocked;",
            self.source,
        )
        self.assertIn(
            'if (!$("entryDuplicateField").classList.contains("hidden")) {\n      payload.duplicate = $("entryDuplicate").checked;\n    }',
            self.source,
        )
        self.assertIn("if (!editingId) {\n      payload.source = source;\n    }", self.source)


    def test_status_filter_groups_and_hides_abnormal_checkbox(self) -> None:
        self.assertNotIn('<option value="normal">', self.source)
        self.assertNotIn(">正常<", self.source)
        self.assertIn('<optgroup label="投送状态">', self.source)
        self.assertIn('<optgroup label="订单状态">', self.source)
        self.assertIn('<optgroup label="异常">', self.source)
        self.assertIn('id="hideAbnormal"', self.source)
        self.assertIn(
            'params.set("hide_abnormal", $("hideAbnormal").checked ? "true" : "false");',
            self.source,
        )
        self.assertIn('"includeDuplicate","hideAbnormal"', self.source)


if __name__ == "__main__":
    unittest.main()
