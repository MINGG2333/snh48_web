import unittest
from datetime import date

from website.debut_milestones import (
    build_homepage_context,
    debut_date,
    milestone_date,
    timeline_milestone_days,
)


class DebutMilestoneTests(unittest.TestCase):
    def test_milestone_dates(self):
        self.assertEqual(debut_date(), date(2025, 10, 5))
        self.assertEqual(milestone_date(300), date(2026, 7, 31))
        self.assertEqual(milestone_date(400), date(2026, 11, 8))

    def test_day_300_celebration_window_and_permanent_scroller(self):
        before = build_homepage_context(date(2026, 7, 30))
        self.assertFalse(before["active"])
        self.assertEqual(before["featured_texts"], [])

        first = build_homepage_context(date(2026, 7, 31))
        self.assertTrue(first["active"])
        self.assertEqual(first["milestone_day"], 300)
        self.assertEqual(first["window_end"], "2026-08-07")
        self.assertEqual(first["featured_texts"], ["祝贺嘉仪出道300天！"])

        last = build_homepage_context(date(2026, 8, 7))
        self.assertTrue(last["active"])

        after = build_homepage_context(date(2026, 8, 8))
        self.assertFalse(after["active"])
        self.assertEqual(after["featured_texts"], ["祝贺嘉仪出道300天！"])

    def test_day_400_repeats_and_keeps_earlier_scroller(self):
        first = build_homepage_context(date(2026, 11, 8))
        self.assertTrue(first["active"])
        self.assertEqual(first["milestone_day"], 400)
        self.assertEqual(first["window_end"], "2026-11-15")
        self.assertEqual(
            first["featured_texts"],
            ["祝贺嘉仪出道300天！", "祝贺嘉仪出道400天！"],
        )
        self.assertTrue(build_homepage_context(date(2026, 11, 15))["active"])
        self.assertFalse(build_homepage_context(date(2026, 11, 16))["active"])

    def test_timeline_milestones_are_permanent(self):
        self.assertEqual(timeline_milestone_days(date(2026, 7, 17)), [300])
        self.assertEqual(timeline_milestone_days(date(2026, 11, 7)), [300])
        self.assertEqual(timeline_milestone_days(date(2026, 11, 8)), [300, 400])
        self.assertEqual(timeline_milestone_days(date(2027, 2, 16)), [300, 400, 500])


if __name__ == "__main__":
    unittest.main()
