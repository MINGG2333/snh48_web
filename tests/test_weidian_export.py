from __future__ import annotations

import io
import unittest

from PIL import Image

from website.weidian_export import mask_name, render_orders_png


class WeidianExportTests(unittest.TestCase):
    def test_mask_name(self) -> None:
        self.assertEqual(mask_name("徐某人"), "徐**")
        self.assertEqual(mask_name("ama"), "a**")
        self.assertEqual(mask_name("A"), "*")
        self.assertEqual(mask_name(""), "匿名")
        self.assertEqual(mask_name("再坏对你不好吗"), "再**")

    def test_renders_filtered_orders_png(self) -> None:
        rows = [
            {"order_id": "1", "item_name": "补邮", "display_name": "徐某人", "amount": "1.00"},
            {"order_id": "2", "item_name": "【百场应援＆Mini Live应援】陈嘉仪", "display_name": "再坏对你不好吗", "amount": "10.50"},
        ]
        png = render_orders_png(
            rows,
            filter_text="状态：待发货",
            updated="2026-11-10 01:30",
            mask_names=True,
        )
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(png))
        self.assertGreaterEqual(image.size[0], 900)
        self.assertGreater(image.size[1], 300)

    def test_renders_without_mask(self) -> None:
        png = render_orders_png(
            [{"order_id": "1", "item_name": "补邮", "display_name": "ama", "amount": "3.00"}],
            filter_text="",
            updated="",
            mask_names=False,
        )
        self.assertTrue(png.startswith(b"\x89PNG"))
        image = Image.open(io.BytesIO(png))
        self.assertGreater(image.size[0], 500)


if __name__ == "__main__":
    unittest.main()
