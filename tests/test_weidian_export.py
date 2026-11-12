from __future__ import annotations

import io
import unittest

from PIL import Image

from website.weidian_export import (
    latest_order_time,
    mask_name,
    render_orders_png,
    sort_orders,
)


class WeidianExportTests(unittest.TestCase):
    def test_mask_name(self) -> None:
        self.assertEqual(mask_name("徐某人"), "徐**人")
        self.assertEqual(mask_name("ama"), "a**a")
        self.assertEqual(mask_name("A"), "*")
        self.assertEqual(mask_name(""), "匿名")
        self.assertEqual(mask_name("再坏对你不好吗"), "再**吗")
        self.assertEqual(mask_name("vv"), "v**")

    def test_sorts_orders_old_to_new_and_latest_time(self) -> None:
        rows = [
            {"order_id": "3", "add_time": "2026-10-18 21:01:23"},
            {"order_id": "1", "add_time": "2026-10-06 09:18:29"},
            {"order_id": "2", "paid_at": "2026-10-17 22:36:27"},
        ]
        ordered = sort_orders(rows)
        self.assertEqual([row["order_id"] for row in ordered], ["1", "2", "3"])
        self.assertEqual(latest_order_time(rows), "2026-10-18 21:01:23")

    def test_renders_filtered_orders_png(self) -> None:
        rows = [
            {"order_id": "1", "item_name": "补邮", "display_name": "徐某人", "amount": "1.00"},
            {"order_id": "2", "item_name": "【百场应援＆Mini Live应援】陈嘉仪", "display_name": "再坏对你不好吗", "amount": "10.50"},
        ]
        png = render_orders_png(
            rows,
            updated="2026-11-10 01:30",
            mask_names=True,
        )
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(png))
        self.assertGreaterEqual(image.size[0], 560)
        self.assertGreater(image.size[1], 200)

    def test_long_display_name_widens_image_instead_of_truncating(self) -> None:
        long_name = "陈嘉仪应援会超长播报昵称测试一二三四五六七八九十" * 2
        png = render_orders_png(
            [{"order_id": "1", "item_name": "补邮", "display_name": long_name, "amount": "1.00"}],
            updated="2026-11-12 08:00",
            mask_names=False,
        )
        image = Image.open(io.BytesIO(png))
        # 48 个汉字 × 22px 字号约 1056px，加上商品/金额列与列距后应明显超过旧版 560~700px。
        self.assertGreater(image.size[0], 1200)

    def test_renders_without_mask(self) -> None:
        rows = [{"order_id": "1", "item_name": "补邮", "display_name": "ama", "amount": "3.00"}]
        png = render_orders_png(rows, updated="", mask_names=False)
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(png))
        self.assertGreater(image.size[0], 500)
        masked = render_orders_png(rows, updated="", mask_names=True)
        self.assertEqual(Image.open(io.BytesIO(masked)).size, image.size, "mask note must not add an extra line")


if __name__ == "__main__":
    unittest.main()
