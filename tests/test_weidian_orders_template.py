from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "website" / "templates" / "weidian_orders.html"


class WeidianOrdersTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def test_account_filter_is_a_multi_select(self) -> None:
        for marker in (
            'id="accountMenu"',
            'id="accountSummary"',
            'id="accountOptions"',
            'id="accountAll"',
            'id="accountClear"',
            'data-account-key',
            "selectedAccounts",
            "Object.keys(selectedAccounts).length",
        ):
            self.assertIn(marker, self.template)

    def test_account_filter_uses_sanitized_account_fields(self) -> None:
        self.assertIn("row.buyer_id", self.template)
        self.assertIn("row.buyer_phone_masked", self.template)
        self.assertIn("下单账号：", self.template)
        self.assertNotIn("buyerTelephone", self.template)
        self.assertNotIn("buyerBindTelephone", self.template)

    def test_account_filter_is_part_of_keyword_search(self) -> None:
        self.assertIn(
            "[row.order_id, row.display_name, row.receiver_name, row.buyer_id, row.buyer_phone_masked",
            self.template,
        )
        self.assertIn("WEIDIAN_ACCOUNT_FILTER_PURE_START", self.template)
        self.assertIn("WEIDIAN_ACCOUNT_FILTER_PURE_END", self.template)

    def test_bulk_selection_and_shipping_controls(self) -> None:
        for marker in (
            'id="selectAll"',
            'id="shipSelectedBtn"',
            'data-select=',
            "selectedOrders",
            "reloadQueued",
            "WEIDIAN_BULK_SHIP_PURE_START",
            "WEIDIAN_BULK_SHIP_PURE_END",
            "function isSelectable",
            "function selectedShipRows",
            "function shipSelectedOrders",
            'type: "ship"',
            "批量无需物流发货",
        ):
            self.assertIn(marker, self.template)
        self.assertIn("colspan=\"11\"", self.template)
        self.assertNotIn("colspan=\"10\"", self.template)
        self.assertIn("发货任务完成后立即重读订单库", self.template)

    def test_status_filter_is_multi_select_with_semantic_labels(self) -> None:
        for marker in (
            'id="statusMenu"',
            'id="statusSummary"',
            'id="statusOptions"',
            'id="statusAll"',
            'id="statusClear"',
            'data-status-key',
            "selectedStatuses",
            "function statusMatches",
            "statuses: selectedStatuses",
        ):
            self.assertIn(marker, self.template)
        for group in ("进行中", "已结束", "退款/售后"):
            self.assertIn(f'"{group}"', self.template)
        for label in (
            "待付款（未付款）",
            "待发货（已付款）",
            "已发货（运输中）",
            "已完成（交易成功）",
            "已关闭（未付款/取消）",
            "退款中（退款处理中）",
            "已退款（钱已退回买家）",
        ):
            self.assertIn(label, self.template)
        self.assertNotIn("全部退款/售后", self.template)
        self.assertNotIn("已完成＝交易成功", self.template)
        self.assertNotIn('id="statusFilter"', self.template)
        self.assertNotIn('value="broadcast_none"', self.template)
        self.assertIn(".pill.closed", self.template)
        self.assertIn(".pill.refunded", self.template)
        self.assertIn("function statusText", self.template)
        self.assertIn("function statusTitle", self.template)
