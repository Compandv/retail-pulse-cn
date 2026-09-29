import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import update_index  # noqa: E402
from sentiment.collectors import CN_TZ  # noqa: E402

# 2026-09-27 is a Sunday; 09-25 is a listed holiday, so the latest session is 09-24.
SUNDAY = datetime(2026, 9, 27, 10, 0, tzinfo=CN_TZ)


class ScheduledUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.summary = self.root / "last-run.json"

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, **dates):
        for key, _, path in update_index.STEPS:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"meta": {"tradeDate": dates.get(key, "2026-09-24")}}), encoding="utf-8")

    def test_missing_days_lists_recent_sessions_without_both_daily_files(self):
        for day in ("2026-09-24", "2026-09-28", "2026-09-30"):
            for pattern in update_index.DAILY_FILES:
                target = self.root / pattern.format(day)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("{}", encoding="utf-8")
        (self.root / update_index.DAILY_FILES[1].format("2026-09-30")).unlink()
        # 09-29 absent, 09-30 has only the report; 09-24 predates the tracking start.
        self.assertEqual(update_index.missing_days("2026-09-30", self.root), ["2026-09-29", "2026-09-30"])
        self.assertEqual(update_index.missing_days("2026-09-30", self.root, sessions=1), ["2026-09-30"])
        self.assertEqual(update_index.missing_days("2026-09-28", self.root), [])

    def test_stale_keys_follow_latest_closed_session(self):
        self.save()
        self.assertEqual(update_index.stale_keys(SUNDAY, self.root), [])
        self.save(market="2026-09-23")
        self.assertEqual(update_index.stale_keys(SUNDAY, self.root), ["market", "longform"])  # long-form follows any refreshed input
        (self.root / "public/data/report/latest.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(update_index.stale_keys(SUNDAY, self.root), ["market", "report", "longform"])

    def run_main(self, stale, **builds):
        out = StringIO()
        with mock.patch.object(update_index, "LAST_RUN", self.summary), \
             mock.patch.object(update_index, "stale_keys", return_value=stale), \
             mock.patch.object(update_index, "logged_run"), \
             mock.patch.object(update_index, "build_market_snapshot", **builds.get("market", {"return_value": {"meta": {"tradeDate": "2026-09-24"}}})) as market, \
             mock.patch.object(update_index, "build_snapshot", **builds.get("community", {"return_value": {"meta": {"tradeDate": "2026-09-24"}}})) as community, \
             mock.patch.object(update_index, "build_report", **builds.get("report", {"return_value": {"meta": {"tradeDate": "2026-09-24"}}})) as report, \
             redirect_stdout(out), redirect_stderr(out):
            code = update_index.main(["--if-stale"])
        return code, json.loads(self.summary.read_text(encoding="utf-8")), (market, community, report)

    def test_up_to_date_run_skips_without_collecting(self):
        code, summary, builds = self.run_main([])
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "skipped")
        self.assertTrue(all(not build.called for build in builds))

    def test_only_stale_modules_run_in_order(self):
        code, summary, (market, community, report) = self.run_main(["report", "market"])
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual((summary["succeeded"], summary["total"]), (2, 2))
        self.assertTrue(market.called and report.called)
        self.assertFalse(community.called)

    def test_failure_is_recorded_for_notification(self):
        code, summary, _ = self.run_main(["market", "community"], community={"side_effect": RuntimeError("source unavailable")})
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(len(summary["failures"]), 1)
        self.assertIn("source unavailable", summary["failures"][0])
        self.assertIn("log", summary)


if __name__ == "__main__":
    unittest.main()
