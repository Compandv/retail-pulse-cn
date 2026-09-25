import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sentiment import pipeline  # noqa: E402
from sentiment.collectors import CN_TZ  # noqa: E402
from sentiment.pipeline import UnsupportedCalendarYear, calendar_warning, effective_trade_date, is_trading_day  # noqa: E402
import update_index  # noqa: E402


class TradingCalendarTest(unittest.TestCase):
    def test_supported_year_uses_listed_holidays(self):
        self.assertTrue(is_trading_day(date(2026, 9, 24)))
        self.assertFalse(is_trading_day(date(2026, 9, 25)))  # listed holiday
        self.assertFalse(is_trading_day(date(2026, 9, 26)))  # weekend

    def test_unlisted_year_raises_instead_of_guessing(self):
        # 2027-01-01 is a weekday; without a calendar it must not pass as a session.
        with self.assertRaises(UnsupportedCalendarYear) as raised:
            is_trading_day(date(2027, 1, 1))
        self.assertIn("config/trading-calendar.json", str(raised.exception))
        with self.assertRaises(UnsupportedCalendarYear):
            effective_trade_date(datetime(2027, 1, 4, 16, 0, tzinfo=CN_TZ))

    def test_adding_a_year_makes_it_usable(self):
        with mock.patch.object(pipeline, "SUPPORTED_YEARS", pipeline.SUPPORTED_YEARS | {2027}), \
             mock.patch.object(pipeline, "HOLIDAYS", pipeline.HOLIDAYS | {date(2027, 1, 1)}):
            self.assertEqual(effective_trade_date(datetime(2027, 1, 4, 16, 0, tzinfo=CN_TZ)), date(2027, 1, 4))
            self.assertEqual(pipeline.previous_trading_day(date(2027, 1, 4)), date(2026, 12, 31))

    def test_december_warning_only_when_next_year_missing(self):
        self.assertIsNone(calendar_warning(date(2026, 11, 30)))
        self.assertIn("2027", calendar_warning(date(2026, 12, 1)))
        with mock.patch.object(pipeline, "SUPPORTED_YEARS", pipeline.SUPPORTED_YEARS | {2027}):
            self.assertIsNone(calendar_warning(date(2026, 12, 1)))

    def test_update_stops_once_before_any_step(self):
        with mock.patch.object(update_index, "say") as say:
            self.assertFalse(update_index.check_calendar(datetime(2027, 1, 4, 16, 0, tzinfo=CN_TZ)))
            self.assertTrue(any("更新未启动" in call.args[0] for call in say.call_args_list))
            self.assertTrue(update_index.check_calendar(datetime(2026, 9, 24, 16, 0, tzinfo=CN_TZ)))


if __name__ == "__main__":
    unittest.main()
