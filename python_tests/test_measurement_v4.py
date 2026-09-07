import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from sentiment import build_snapshot
from sentiment.collectors import CN_TZ, SinaCollector, TaogubaCollector, anonymous_author
from sentiment.measurement import METHOD_VERSION, universe_key
from sentiment.observations import collect_feed, collect_trading
from sentiment.pipeline_v4 import assemble_snapshot, persist_snapshot, scopes_for


DAY = "2026-09-04"
NOW = datetime(2026, 9, 5, 16, tzinfo=CN_TZ)
CODES = ["002714", "920970"]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def setup(root):
    write(root / "config/themes.json", {"themes": [{"id": "pork", "name": "猪肉", "description": "测试观察篮子", "members": [{"code": code, "name": code, "role": "观察成分"} for code in CODES]}]})
    write(root / "config/targets.json", {"targets": [{"id": "market"}]})


def batch(day=DAY):
    result = {"date": day, "collectedAt": NOW.isoformat(), "feeds": {}, "trading": {}, "supplement": []}
    for code in CODES:
        result["feeds"][code] = {"code": code, "rows": [{"id": code, "author": "same-observer", "text": "今天追高买入了", "date": day + " 10:00:00", "source": "eastmoney", "code": code, "url": ""}], "rawCount": 1, "pages": 1, "complete": True, "error": None, "reason": "末页"}
        result["trading"][code] = {"code": code, "changePct": 5, "activityScore": 90}
    return result


class MeasurementPipelineTests(TestCase):
    def test_public_entry_uses_v4_archives_v3_and_reloads_prior_real_history(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            setup(root)
            old = {"meta": {"methodVersion": "MVP-3.0", "tradeDate": DAY}, "history": [{"date": "2026-09-03", "overall": 93, "recordType": "estimated"}]}
            write(root / "public/data/latest.json", old)
            with patch("sentiment.pipeline_v4.collect_batch", return_value=batch()):
                first = build_snapshot(root, NOW)
                repeated = build_snapshot(root, NOW)
            self.assertEqual(first["meta"]["methodVersion"], METHOD_VERSION)
            self.assertEqual(first["legacy"]["history"], old["history"])
            self.assertEqual(first["history"], repeated["history"])
            self.assertIsNone(first["summary"]["attention"]["score"])
            self.assertEqual(first["summary"]["attention"]["observedAuthors"], 1)
            self.assertEqual(first["summary"]["attention"]["baselineDays"], 0)
            self.assertTrue(all("author" not in row for row in first["summary"]["posts"]))
            archived = json.loads((root / "public/data/archive/2026-09-04-mvp-3-0.json").read_text(encoding="utf-8"))
            self.assertEqual(archived, old)
            # Reconstructing a later day must load persisted measurements, not
            # the V3 estimated points or the same-day rerun as extra history.
            with patch("sentiment.pipeline_v4.collect_batch", return_value=batch("2026-09-07")):
                second = build_snapshot(root, datetime(2026, 9, 7, 17, tzinfo=CN_TZ))
            self.assertEqual([point["date"] for point in second["history"]], [DAY, "2026-09-07"])
            self.assertEqual(second["summary"]["attention"]["baselineDays"], 1)
            for code in CODES:
                self.assertEqual(len(second["attentionHistory"][universe_key([code])]), 2)
            self.assertEqual(second["meta"]["collectedAt"], NOW.isoformat())

    def test_failures_and_out_of_window_only_samples_keep_previous_file(self):
        for mode in ("unavailable", "wrong_day", "advertisement"):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                root = Path(folder)
                setup(root)
                previous = {"meta": {"methodVersion": "MVP-3.0", "tradeDate": DAY}, "history": []}
                target = root / "public/data/latest.json"
                write(target, previous)
                original_bytes = target.read_bytes()
                capture = batch()
                for feed in capture["feeds"].values():
                    if mode == "unavailable":
                        feed.update(rows=[], complete=False, error="timeout")
                    elif mode == "wrong_day":
                        feed["rows"][0]["date"] = "2026-08-26 10:00:00"
                    else:
                        feed["rows"][0]["text"] = "费率可调，开户享新客专属福利"
                with patch("sentiment.pipeline_v4.collect_batch", return_value=capture):
                    with self.assertRaises(RuntimeError):
                        build_snapshot(root, NOW)
                self.assertEqual(target.read_bytes(), original_bytes)
                self.assertFalse((root / "public/data/daily" / f"{DAY}.json").exists())

    def test_replay_cannot_replace_a_newer_snapshot(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            setup(root)
            snapshot = assemble_snapshot(root, batch(), scopes_for(root), NOW)
            target = root / "public/data/latest.json"
            write(target, {"meta": {"tradeDate": "2026-09-07", "methodVersion": METHOD_VERSION}})
            before = target.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "早于"):
                persist_snapshot(root, snapshot)
            self.assertEqual(target.read_bytes(), before)

    def test_missing_accounts_are_not_one_person_or_a_valid_baseline(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            setup(root)
            capture = batch()
            capture["feeds"][CODES[0]]["rows"][0]["author"] = ""
            source_row = capture["feeds"][CODES[0]]["rows"][0]
            capture["supplement"] = [{"code": CODES[0], "source": "sina", "error": None, "rows": [{**source_row, "source": "sina", "author": anonymous_author("sina", None), "id": str(i), "text": f"第{i}个独立匿名讨论"} for i in range(4)]}]
            snapshot = assemble_snapshot(root, capture, scopes_for(root), NOW)
            self.assertEqual(snapshot["summary"]["expressions"]["sampleCount"], 6)
            self.assertEqual(snapshot["summary"]["attention"]["unknownAuthorPosts"], 1)
            point = snapshot["attentionHistory"][universe_key(CODES)][0]
            self.assertIsNone(point["value"])
            self.assertFalse(point["complete"])


class MeasurementSourceTests(TestCase):
    def test_all_source_prefixes_prioritize_the_beijing_920_range(self):
        for collector in (SinaCollector, TaogubaCollector):
            self.assertEqual(collector.symbol({"stockCode": "920970"}), "bj920970")
            self.assertEqual(collector.symbol({"stockCode": "900901"}), "sh900901")

    def test_string_zero_pin_flag_does_not_prevent_date_boundary_detection(self):
        row = {"stockbar_code": "920970", "post_type": 0, "post_title": "普通行情讨论", "post_publish_time": "2026-09-03 10:00:00", "post_last_time": "2026-09-03 10:00:00", "post_top_status": "0"}
        payloads = [{"re": [{**row, "post_id": str(i * 100 + j)} for j in range(100)]} for i in range(2)]
        with patch("sentiment.observations.get_json", side_effect=payloads) as request:
            feed = collect_feed("920970", DAY)
        self.assertEqual(request.call_count, 2)
        self.assertTrue(feed["complete"])

    def test_historical_quote_ignores_future_prices_and_volumes(self):
        rows = [[f"2026-08-{i:02d}", "10", "10", "11", "9", "100"] for i in range(1, 21)]
        rows.extend([[DAY, "10", "11", "11", "10", "300"], ["2026-09-07", "11", "20", "20", "11", "99999"]])
        with patch("sentiment.observations.request_text", side_effect=RuntimeError("quote unavailable")), patch("sentiment.observations.get_json", return_value={"data": {"bj920970": {"qfqday": rows}}}):
            quote = collect_trading("920970", DAY)
        self.assertEqual(quote["price"], 11)
        self.assertEqual(quote["changePct"], 10)
        self.assertEqual(quote["activityScore"], 100)
        self.assertEqual(quote["volumeRatio"], 3)
        self.assertIsNone(quote["turnover"])
        self.assertIn("前复权", quote["source"])
