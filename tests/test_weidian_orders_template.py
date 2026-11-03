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


if __name__ == "__main__":
    unittest.main()
