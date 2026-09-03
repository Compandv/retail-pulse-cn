from datetime import date, datetime
from unittest import TestCase

from sentiment.analyzer import analyze_post
from sentiment.collectors import CN_TZ
from sentiment.models import Post
from pathlib import Path
from tempfile import TemporaryDirectory

from sentiment.pipeline import _calendar_payload, _load_persisted_daily_snapshots, _merge_history_rows, aggregate_group, effective_trade_date, recent_trading_days


class PipelineTests(TestCase):
    def test_missing_sources_keep_neutral_seats(self):
        post = Post("eastmoney", "market", "全市场", "梭哈满仓起飞", datetime(2026, 9, 2, 16, tzinfo=CN_TZ), "a")
        analyzed = analyze_post(post)
        assert analyzed is not None
        metrics = aggregate_group([analyzed])
        self.assertGreater(metrics["overall"], 45)
        self.assertLess(metrics["overall"], 70)

    def test_trade_date_before_close_uses_previous_session(self):
        now = datetime(2026, 9, 2, 10, 0, tzinfo=CN_TZ)
        self.assertEqual(effective_trade_date(now), date(2026, 9, 1))

    def test_recent_sessions_skip_weekend(self):
        days = recent_trading_days(date(2026, 8, 31), 3)
        self.assertEqual(days, {date(2026, 8, 31), date(2026, 8, 28), date(2026, 8, 27)})

    def test_history_rows_are_sorted_deduplicated_and_measured_wins(self):
        rows = _merge_history_rows([
            {"date": "2026-09-01", "overall": 48, "recordType": "estimated"},
            {"date": "2026-08-31", "overall": 47, "recordType": "estimated"},
            {"date": "2026-09-01", "overall": 51, "recordType": "measured"},
        ])
        self.assertEqual([row["date"] for row in rows], ["2026-08-31", "2026-09-01"])
        self.assertEqual(rows[-1]["overall"], 51)
        self.assertEqual(rows[-1]["recordType"], "measured")

    def test_complete_estimate_replaces_partial_estimate(self):
        rows = _merge_history_rows([
            {"date": "2026-09-01", "overall": 48, "recordType": "estimated"},
            {"date": "2026-09-01", "overall": 48, "sampleCount": 12, "recordType": "estimated"},
        ])
        self.assertEqual(rows[0]["sampleCount"], 12)

    def test_calendar_keeps_unknown_sample_count_unknown(self):
        rows = _calendar_payload([{"date": "2026-09-01", "overall": 48, "heat": 20, "recordType": "estimated"}])
        self.assertIsNone(rows[0]["sampleCount"])

    def test_daily_snapshots_are_loaded_from_disk(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "public" / "data" / "daily"
            daily.mkdir(parents=True)
            (daily / "2026-09-01.json").write_text('{"meta":{"tradeDate":"2026-09-01","mode":"live"},"history":[]}', encoding="utf-8")
            snapshots = _load_persisted_daily_snapshots(root)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["meta"]["tradeDate"], "2026-09-01")
