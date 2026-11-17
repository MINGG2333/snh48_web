"""按条目导出 PNG 的版式回归：最后一行必须完整落在白色卡片内。"""
from __future__ import annotations

import io
import unittest

from PIL import Image

from website.gift_reply_export import BG, SECTION_BG
from website.redblue_export import (
    ENTRIES_DAY_GAP,
    ENTRIES_DAY_HEIGHT,
    ENTRIES_ROW_HEIGHT,
    PAD,
    render_entries_png,
)

ENTRY_SEPARATOR = (240, 232, 245)


def _entries(days: int, rows_per_day: int) -> list[dict]:
    items = []
    for day in range(days):
        date = f"2026-11-{day + 1:02d}"
        for row in range(rows_per_day):
            items.append(
                {
                    "id": f"{date}-{row}",
                    "fan_name": f"粉丝{row}",
                    "raw_name": f"粉丝{row}",
                    "score": 1,
                    "source": "room",
                    "scoring_method": "计分卡",
                    "source_time": f"{date} 12:00:00",
                    "duplicate": False,
                }
            )
    return items


class RedblueEntriesExportLayoutTests(unittest.TestCase):
    def _render(self, entries: list[dict]) -> Image.Image:
        png = render_entries_png(
            entries,
            summary={},
            period="全部时间",
            filter_text="",
            updated="2026-11-17 20:00",
        )
        return Image.open(io.BytesIO(png)).convert("RGB")

    def test_last_day_separator_stays_inside_card(self) -> None:
        days, rows_per_day = 12, 2
        entries = _entries(days, rows_per_day)
        image = self._render(entries)
        width, height = image.size

        # _draw_header 在无筛选时返回 128；卡片从该位置开始。
        section_top = 128
        content_height = days * (
            ENTRIES_DAY_HEIGHT + rows_per_day * ENTRIES_ROW_HEIGHT + ENTRIES_DAY_GAP
        )
        section_bottom = section_top + 74 + content_height + 14

        # 距离卡片右边缘 25px：避开圆角和右对齐文字，仍覆盖分隔线范围。
        x = width - PAD - 25
        self.assertEqual(image.getpixel((x, section_bottom - 1)), SECTION_BG)
        self.assertEqual(image.getpixel((x, section_bottom + 1)), BG)

        # 最后一条的分隔线必须画在卡片内部（旧版会画到卡片下方的页面底色上）。
        last_row_top = (
            section_top
            + 74
            + (days - 1) * (ENTRIES_DAY_HEIGHT + rows_per_day * ENTRIES_ROW_HEIGHT + ENTRIES_DAY_GAP)
            + ENTRIES_DAY_HEIGHT
            + (rows_per_day - 1) * ENTRIES_ROW_HEIGHT
        )
        separator_y = last_row_top + ENTRIES_ROW_HEIGHT + 6
        self.assertLess(separator_y, section_bottom)
        self.assertEqual(image.getpixel((x, separator_y)), ENTRY_SEPARATOR)


if __name__ == "__main__":
    unittest.main()
