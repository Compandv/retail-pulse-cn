import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from sentiment.analyzer import analyze_post
from sentiment.collectors import CN_TZ
from sentiment.models import AnalyzedPost, CollectionOutcome, Post, Signals
from sentiment.pipeline import build_legacy_snapshot as build_snapshot, _participant_indices
from sentiment.scoring import CONFIG, METHOD_VERSION, score_source


class ScoringTests(TestCase):
    def post(self, text="普通讨论", target="gold"):
        return Post("eastmoney", target, "黄金", text, datetime(2026, 9, 4, 16, tzinfo=CN_TZ), "a")

    def test_full_scale_and_empty_data_are_distinct(self):
        full = AnalyzedPost(self.post(), Signals(1, 1, 1, 1, ()))
        neutral = AnalyzedPost(self.post(), Signals(0, 0, 0, 0, ()))
        self.assertEqual(sum(CONFIG["weights"].values()), 1)
        self.assertEqual(score_source([full] * 80)["overall"], 100)
        self.assertEqual(score_source([neutral] * 80)["overall"], 20)
        self.assertIsNone(score_source([])["overall"])
        self.assertGreater(score_source([full])["overall"], 80)
        self.assertIsNone(_participant_indices(score_source([]))["buyIndex"])

    def test_mixed_emotions_increase_intensity_without_inventing_direction(self):
        bullish = AnalyzedPost(self.post(), Signals(0, 1, 0, 1, ()))
        bearish = AnalyzedPost(self.post(), Signals(0, 0, 1, -1, ()))
        result = score_source([bullish, bearish] * 40)
        self.assertEqual(result["direction"], 0)
        self.assertGreater(result["overall"], 20)

    def test_migration_keeps_old_history_separate_and_missing_sector_null(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "public/data/daily").mkdir(parents=True)
            (root / "config/targets.json").write_text(json.dumps({"targets": [{"id": "gold", "name": "黄金"}, {"id": "empty", "name": "空板块"}]}), encoding="utf-8")
            previous = {"meta": {"tradeDate": "2026-09-04", "methodVersion": "MVP-2.0", "mode": "live", "historyMode": "live_only"}, "history": [{"date": "2026-09-03", "overall": 99, "heat": 99, "recordType": "measured"}], "sectors": []}
            (root / "public/data/latest.json").write_text(json.dumps(previous), encoding="utf-8")
            (root / "public/data/daily/2026-09-04.json").write_text(json.dumps(previous), encoding="utf-8")
            outcomes = [CollectionOutcome("eastmoney", "gold", True, (self.post("小白求助能买吗"),), 1)]
            with patch("sentiment.pipeline._collect", return_value=outcomes), patch("sentiment.pipeline.fetch_market_data", return_value={}), patch("sentiment.pipeline._backfill_market_history", return_value=[]):
                snapshot = build_snapshot(root, datetime(2026, 9, 4, 18, tzinfo=CN_TZ))
            self.assertEqual(snapshot["meta"]["methodVersion"], METHOD_VERSION)
            self.assertEqual(len(snapshot["history"]), 1)
            self.assertIsNone(snapshot["summary"]["change"])
            self.assertEqual(snapshot["legacy"]["history"][0]["overall"], 99)
            self.assertEqual(json.loads((root / "public/data/archive/2026-09-04-v2.json").read_text()), previous)
            empty = next(row for row in snapshot["sectors"] if row["id"] == "empty")
            self.assertIsNone(empty["overall"])
            self.assertNotIn("empty", [row["id"] for row in snapshot["sectorHistory"][-1]["sectors"]])
            self.assertTrue(snapshot["comments"][0]["reasoning"])
            self.assertEqual(len(snapshot["comments"][0]["evidence"]), 4)

    def test_total_collection_failure_preserves_latest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "public/data").mkdir(parents=True)
            (root / "config/targets.json").write_text('{"targets":[{"id":"market"}]}')
            path = root / "public/data/latest.json"
            path.write_text('{"meta":{"methodVersion":"MVP-2.0"}}')
            previous = path.read_bytes()
            with patch("sentiment.pipeline._collect", return_value=[]):
                with self.assertRaises(RuntimeError):
                    build_snapshot(root)
            self.assertEqual(path.read_bytes(), previous)
