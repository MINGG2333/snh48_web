from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from website.score_gifts_api import _build_score_gifts_xlsx, _build_sender_distribution_xlsx


SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _sheet_rows(payload: bytes, path: str) -> list[list[str]]:
    with ZipFile(BytesIO(payload)) as archive:
        root = ET.fromstring(archive.read(path))
    rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", SHEET_NS):
        values: list[str] = []
        for cell in row.findall("x:c", SHEET_NS):
            inline = cell.find("x:is/x:t", SHEET_NS)
            number = cell.find("x:v", SHEET_NS)
            if inline is not None and inline.text is not None:
                values.append(inline.text)
            else:
                values.append(number.text if number is not None and number.text is not None else "")
        rows.append(values)
    return rows


def _gift_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "gift-1",
        "source": "room",
        "source_label": "",
        "event_time": "2026-08-08 10:00:00",
        "date": "2026-08-08",
        "sender_name": "小甲",
        "sender_id": "1001",
        "gift_id": "gift-a",
        "gift_name": "星梦棒",
        "gift_count": 2,
        "unit_score": 3,
        "total_score": 6,
    }
    row.update(overrides)
    return row


class ScoreGiftSenderExportTests(unittest.TestCase):
    def test_existing_detail_export_remains_a_valid_single_sheet_workbook(self) -> None:
        payload = _build_score_gifts_xlsx([_gift_row()], "2026-08-08 11:30:00")

        with ZipFile(BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            self.assertNotIn("xl/worksheets/sheet2.xml", archive.namelist())
            workbook = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn('name="计分礼物明细"', workbook)

    def test_workbook_contains_sender_summary_and_grouped_details(self) -> None:
        rows = [
            _gift_row(),
            _gift_row(
                id="gift-2",
                source="live",
                event_time="2026-08-08 09:00:00",
                gift_id="gift-b",
                gift_name="小船",
                gift_count=3,
                unit_score=2,
                total_score=6,
            ),
            _gift_row(
                id="gift-3",
                source="live",
                event_time="2026-08-08 11:00:00",
                sender_name="小乙",
                sender_id="1002",
                gift_id="gift-c",
                gift_name="彩虹",
                gift_count=1,
                unit_score=5,
                total_score=5,
            ),
        ]

        payload = _build_sender_distribution_xlsx(rows, "2026-08-08 11:30:00")

        with ZipFile(BytesIO(payload)) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            self.assertIn("xl/worksheets/sheet2.xml", archive.namelist())
            workbook = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn('name="送礼用户汇总"', workbook)
            self.assertIn('name="投分明细"', workbook)

        summary_rows = _sheet_rows(payload, "xl/worksheets/sheet1.xml")
        self.assertEqual(summary_rows[4][:8], [
            "送礼用户", "送礼用户ID", "关联昵称", "总分", "房间分", "直播分", "计分礼物数量", "投分明细数",
        ])
        self.assertEqual(summary_rows[5][:8], ["小甲", "1001", "小甲", "12.0", "6.0", "6.0", "5", "2"])
        self.assertEqual(summary_rows[6][0], "小乙")

        detail_rows = _sheet_rows(payload, "xl/worksheets/sheet2.xml")
        self.assertEqual(detail_rows[4][:8], [
            "送礼用户", "送礼用户ID", "送礼时间", "投分来源", "计分礼物", "数量", "单个分值", "对应分数",
        ])
        self.assertEqual(detail_rows[5][:8], ["小甲", "1001", "2026-08-08 10:00:00", "房间", "星梦棒", "2", "3", "6"])
        self.assertEqual(detail_rows[6][:8], ["小甲", "1001", "2026-08-08 09:00:00", "直播", "小船", "3", "2", "6"])
        self.assertEqual(detail_rows[7][:8], ["小乙", "1002", "2026-08-08 11:00:00", "直播", "彩虹", "1", "5", "5"])

    def test_score_page_has_sender_export_button_and_endpoint(self) -> None:
        template = Path("website/templates/score_gifts.html").read_text(encoding="utf-8")
        self.assertIn('id="exportSendersBtn"', template)
        self.assertIn('/api/score-gifts/sender-export.xlsx', template)
        self.assertIn('action: "export_sender_distribution"', template)


if __name__ == "__main__":
    unittest.main()
