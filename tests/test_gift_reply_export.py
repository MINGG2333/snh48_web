from __future__ import annotations

import io
import unittest

from PIL import Image, ImageDraw

from website.gift_replies_api import (
    _export_period_text,
    _sender_filter_text,
    _timeline_filter_text,
)
from website.gift_reply_export import (
    EMOJI_FONT_PATH,
    ExportTooLarge,
    SCALE,
    _display_text,
    _fallback_fonts,
    _fallback_for,
    _fit,
    _font,
    _glyph_is_missing,
    render_overview_png,
    render_timeline_png,
)


def row(
    message_id: str,
    time: str,
    sender: str,
    gift: str,
    *,
    replied: bool,
    count: int = 1,
) -> dict:
    return {
        "gift_message_id": message_id,
        "gift_bj_time": time,
        "sender_name": sender,
        "gift_name": gift,
        "gift_count": count,
        "has_reply": replied,
        "reply_status": "replied" if replied else "unreplied",
    }


class GiftReplyExportTests(unittest.TestCase):
    def test_timeline_png_contains_all_rows(self) -> None:
        rows = [
            row("a", "2026-10-23 19:00:00", "用户甲", "心锁", replied=False),
            row("b", "2026-10-22 18:00:00", "用户乙", "巧克力", replied=True, count=3),
        ]
        data = render_timeline_png(
            rows,
            period="2026-10-01 起",
            filter_text="全部状态",
            updated="2026-10-23 19:30",
        )
        self.assertTrue(data.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000 * SCALE)
            self.assertGreater(image.height, 150)

    def test_timeline_png_is_single_column(self) -> None:
        rows = [
            row(f"d1-{index}", f"2026-10-23 {19 - index:02d}:00:00", f"用户{index}", "心锁", replied=False)
            for index in range(6)
        ] + [
            row(f"d2-{index}", f"2026-10-22 {19 - index:02d}:00:00", f"用户{index}", "心锁", replied=True)
            for index in range(6)
        ]
        data = render_timeline_png(rows, period="2026-10-01 起")
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000 * SCALE)
            self.assertGreater(image.height, 850 * SCALE)

    def test_overview_png_groups_senders(self) -> None:
        groups = [
            {
                "sender_name": "用户甲",
                "items": [
                    row("a", "2026-10-23 19:00:00", "用户甲", "心锁", replied=False),
                    row("c", "2026-10-22 19:00:00", "用户甲", "玫瑰花", replied=True),
                ],
            },
            {
                "sender_name": "用户乙",
                "items": [row("b", "2026-10-21 18:00:00", "用户乙", "巧克力", replied=True)],
            },
        ]
        data = render_overview_png(
            groups,
            period="2026-10-01 至 2026-10-23",
            filter_text="全部",
            updated="2026-10-23 19:30",
        )
        self.assertTrue(data.startswith(b"\x89PNG"))
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000 * SCALE)
            self.assertGreater(image.height, 150)

    def test_overview_png_stays_two_columns(self) -> None:
        groups = [
            {
                "sender_name": f"用户{group_index}",
                "items": [
                    row(f"{group_index}-{index}", f"2026-10-2{index} 18:00:00", f"用户{group_index}", "心锁", replied=True)
                    for index in range(5)
                ],
            }
            for group_index in range(4)
        ]
        data = render_overview_png(groups, period="2026-10-01 至 2026-10-25")
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.width, 1000 * SCALE)
            self.assertLess(image.height, 1100 * SCALE)

    def test_too_tall_export_is_rejected_before_rendering(self) -> None:
        rows = [
            row(f"r{index}", "2026-10-23 19:00:00", f"用户{index}", "心锁", replied=False)
            for index in range(2000)
        ]
        with self.assertRaises(ExportTooLarge):
            render_timeline_png(rows, period="全部时间")

    def test_empty_export_is_still_png(self) -> None:
        data = render_timeline_png([], period="全部时间")
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_display_text_preserves_decorative_glyphs_with_fallback(self) -> None:
        font = _font(24)
        fallback = _fallback_for(font)
        self.assertIsNotNone(fallback)
        name = "嘉菲猫不吃鱼𓈒𓂂𓏸"
        self.assertEqual(_display_text(name, font, fallback), name)
        self.assertEqual(_display_text(name, font), "嘉菲猫不吃鱼")
        self.assertEqual(_display_text("嘉菲猫不吃鱼", font, fallback), "嘉菲猫不吃鱼")

    def test_display_text_preserves_symbol_and_emoji_with_fallback(self) -> None:
        font = _font(24)
        fallback = _fallback_for(font)
        for name in ("JOJO⭐", "拾蹄悦(悦悦🌲)", "衡绥suí🌲🐒", "挺吉⛽", "✅测试", "闪电⚡"):
            with self.subTest(name=name):
                self.assertEqual(_display_text(name, font, fallback), name)

    def test_display_text_keeps_kaomoji_glyphs(self) -> None:
        """kaomoji 里的 ᴗ 等装饰字符曾被当成“字体不支持”整段过滤掉。"""
        font = _font(24)
        fallback = _fallback_for(font)
        name = "炸毛小猫🐱⌯>ᴗo⌯ಣ"
        rendered = _display_text(name, font, fallback)
        self.assertIn("ᴗ", rendered)
        self.assertIn("🐱", rendered)
        # 生僻字（⌯/ಣ）是否保留取决于节点装了哪些字体，但顺序不能变、也不能多出字符。
        name_iter = iter(name)
        self.assertTrue(all(char in name_iter for char in rendered))

    def test_display_text_never_keeps_unrenderable_glyphs(self) -> None:
        """保留下来的字符必须在主字体或备用字体链里有真实字形，避免导出方框。"""
        font = _font(24)
        fallback = _fallback_for(font)
        candidates = (font, *fallback)
        for name in ("炸毛小猫🐱⌯>ᴗo⌯ಣ", "ʕ•ᴥ•ʔ", "衡绥suí🌲🐒", "1️⃣键帽", "👍🏻赞"):
            with self.subTest(name=name):
                rendered = _display_text(name, font, fallback)
                for char in rendered:
                    if char in {"\u200d", "\ufe0e", "\ufe0f"} or char.isspace():
                        continue
                    self.assertTrue(
                        any(not _glyph_is_missing(item, char) for item in candidates),
                        f"{char!r} 没有可用字形",
                    )

    def test_display_text_keeps_emoji_sequences_together(self) -> None:
        font = _font(24)
        fallback = _fallback_for(font)
        for name in ("👨‍👩‍👧家庭", "👍🏻赞", "❤️爱"):
            with self.subTest(name=name):
                self.assertEqual(_display_text(name, font, fallback), name)

    def test_emoji_fallback_is_monochrome_vendored_font(self) -> None:
        fonts = _fallback_fonts(24)
        paths = [str(getattr(item, "path", "")) for item in fonts]
        self.assertIn(str(EMOJI_FONT_PATH), paths)
        for path in paths:
            self.assertNotIn("NotoColorEmoji", path)

    def test_fit_truncates_on_grapheme_clusters(self) -> None:
        font = _font(20)
        fallback = _fallback_for(font)
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        name = "一二三四五👨‍👩‍👧六七八九十一二三四五"
        fitted = _fit(draw, name, font, 80, fallback)
        self.assertTrue(fitted.endswith("…"))
        self.assertFalse(fitted[:-1].endswith("\u200d"))

    def test_filter_labels(self) -> None:
        self.assertEqual(_export_period_text("2026-10-01", "2026-10-23"), "2026-10-01 至 2026-10-23")
        self.assertEqual(_export_period_text("2026-10-01", ""), "2026-10-01 起")
        self.assertEqual(_timeline_filter_text("unreplied", "心锁", "", "all"), "未回复 · 礼物：心锁")
        self.assertEqual(_sender_filter_text("unreplied", "用户甲"), "有未回复 · 送礼人：用户甲")


if __name__ == "__main__":
    unittest.main()
