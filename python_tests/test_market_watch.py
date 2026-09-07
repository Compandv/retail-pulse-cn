import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from sentiment.collectors import CN_TZ
from sentiment.market_watch import VERSION, assemble_market, atomic_json, build_market_snapshot, collect_group, normalize_row, persist_market
from sentiment.sina_market import collect_sina_market

DAY = "2026-09-04"
NOW = datetime(2026, 9, 5, 18, tzinfo=CN_TZ)


def row(code, change=3, turnover=4, day=DAY, amount=100000000):
    return {"f12": code, "f14": "板块" + code, "f3": change, "f8": turnover, "f6": amount,
            "f124": int(datetime.fromisoformat(day + "T15:30:00+08:00").timestamp()), "f104": 6, "f105": 2}


def capture(day=DAY, industry=None, concept=None, stocks=None):
    groups = {}
    for key, data in (("industry", industry), ("concept", concept), ("stocks", stocks)):
        data = data if data is not None else [row("000001" if key == "stocks" else "BK1000", day=day)]
        groups[key] = {"group": key, "expected": len(data), "rows": data, "complete": True, "pages": 1, "errors": []}
    return {"date": day, "collectedAt": NOW.isoformat(), "version": VERSION, "groups": groups}


class MarketCollectionTests(TestCase):
    def test_daily_entry_attempts_both_pipelines_when_either_fails(self):
        from scripts.update_index import main
        community = {"meta": {"tradeDate": DAY, "cutoff": "15:00"}, "summary": {
            "attention": {"score": None, "reason": "历史不足", "observedAuthors": 1},
            "trading": {"score": 50}, "expressions": {"chase": 0, "sampleCount": 1}}}
        market = assemble_market(capture(), [])
        for failed in ("market", "community", "report"):
            with self.subTest(failed=failed), patch("scripts.update_index.build_market_snapshot", side_effect=RuntimeError("source unavailable") if failed == "market" else None, return_value=market) as collect_market, patch("scripts.update_index.build_snapshot", side_effect=RuntimeError("source unavailable") if failed == "community" else None, return_value=community) as collect_community, patch("scripts.update_index.build_report", side_effect=RuntimeError("source unavailable") if failed == "report" else None, return_value=market) as collect_report, redirect_stdout(StringIO()), patch("sys.stderr", new_callable=StringIO):
                self.assertEqual(main(), 1)
                collect_market.assert_called_once()
                collect_community.assert_called_once()
                collect_report.assert_called_once()

    def test_invalid_replays_do_not_fetch_or_publish(self):
        with TemporaryDirectory() as folder, patch("sentiment.market_watch.collect_market") as fetch:
            for invalid in ({}, capture(day="2026-09-07"), capture(day="2026-09-05")):
                with self.assertRaises(RuntimeError):
                    build_market_snapshot(folder, now=NOW, capture=invalid)
            fetch.assert_not_called()
            self.assertFalse((Path(folder) / "public/data/market/latest.json").exists())

    def test_catalog_reads_every_page_not_first_hundred(self):
        def page(_group, number):
            return 201, [row(f"BK{1000+i}") for i in range((number-1)*100, min(number*100, 201))]
        with patch("sentiment.market_watch.fetch_page", side_effect=page) as fetch:
            result = collect_group("industry")
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(len(result["rows"]), 201)
        self.assertTrue(result["complete"])

    def test_repeated_or_missing_pages_cannot_be_full_catalog(self):
        for failure in ("repeat", "timeout"):
            def page(_group, number):
                if failure == "timeout" and number == 2:
                    raise RuntimeError("timeout")
                return 200, [row(f"BK{1000+i}") for i in range(100)]
            with patch("sentiment.market_watch.fetch_page", side_effect=page):
                result = collect_group("concept")
            self.assertFalse(result["complete"])
            self.assertEqual(len(result["rows"]), 100)
            self.assertTrue(result["errors"])

    def test_quote_date_and_missing_numbers_are_not_invented(self):
        result = normalize_row(row("BK1000", day="2026-09-03"), "industry", DAY)
        self.assertFalse(result["dateValid"])
        self.assertIsNone(result["changePct"])
        self.assertIsNone(result["amount"])
        result = normalize_row({**row("BK1000"), "f3": "-", "f8": float("nan"), "f6": -1}, "industry", DAY)
        self.assertIsNone(result["changePct"])
        self.assertIsNone(result["turnover"])
        self.assertIsNone(result["amount"])


class MarketRankingTests(TestCase):
    def test_constituent_changes_reset_comparable_history(self):
        first = assemble_market(capture(day="2026-09-03", industry=[{**row("BK1", day="2026-09-03"), "memberSignature": "old"}]), [])
        result = assemble_market(capture(industry=[{**row("BK1"), "memberSignature": "new"}]), [first])
        board = next(row for row in result["boards"] if row["kind"] == "industry")
        self.assertEqual(board["baselineDays"], 0)
        self.assertIsNone(board["turnoverChange"])

    def test_details_exist_before_latest_is_published(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = assemble_market(capture(), [])
            detail = {"code": "BK1000", "date": DAY, "members": []}
            def write(path, value):
                if Path(path).name == "latest.json":
                    self.assertTrue((root / "public/data/market/members" / DAY / "BK1000.json").exists())
                atomic_json(path, value)
            with patch("sentiment.market_watch.atomic_json", side_effect=write):
                persist_market(root, snapshot, {"BK1000": detail})
            before = (root / "public/data/market/latest.json").read_bytes()
            with self.assertRaises(RuntimeError):
                persist_market(root, snapshot, {"BK1000": {**detail, "date": "2026-09-03"}})
            self.assertEqual((root / "public/data/market/latest.json").read_bytes(), before)

    def test_any_new_sector_can_lead_and_rotate_next_day(self):
        first = assemble_market(capture(industry=[row("BK1111", 8), row("BK9999", 2)]), [])
        next_day = "2026-09-07"
        second = assemble_market(capture(day=next_day, industry=[row("BK1111", -2, day=next_day), row("BK9999", 9, day=next_day)]), [first])
        leaders = [[r for r in s["boards"] if r["kind"] == "industry"][0]["code"] for s in (first, second)]
        self.assertEqual(leaders, ["BK1111", "BK9999"])
        changed = next(row for row in second["boards"] if row["code"] == "BK9999")
        self.assertEqual(changed["rankChange"], 1)
        self.assertIsNone(changed["activityHistory"])

    def test_relative_percentiles_separate_types_and_keep_ties(self):
        snapshot = assemble_market(capture(industry=[row("BK1", turnover=2), row("BK2", turnover=2)], concept=[row("BK3", turnover=99)]), [])
        self.assertTrue(all(row["relativeActivity"] == 50 for row in snapshot["boards"]))
        self.assertEqual(snapshot["boards"][0]["relativeCount"], 1)  # concept is sorted first
        self.assertIsNone(snapshot["boards"][0]["discussion"])

    def test_market_uses_unique_stocks_not_overlapping_sector_amounts(self):
        snapshot = assemble_market(capture(industry=[row("BK1", amount=900000000)], concept=[row("BK2", amount=900000000)],
                                           stocks=[row("000001", 2, amount=100), row("000001", 2, amount=100), row("000002", -4, amount=300)]), [])
        self.assertEqual(snapshot["market"]["amount"], 400)
        self.assertEqual(snapshot["market"]["observed"], 2)
        self.assertEqual(snapshot["market"]["medianChange"], -1)

    def test_history_ignores_future_today_wrong_method_and_source(self):
        first = assemble_market(capture(), [])
        invalid = [{**first, "meta": {**first["meta"], "tradeDate": "2026-09-07"}},
                   {**first, "meta": {**first["meta"], "tradeDate": "2026-09-03", "methodVersion": "old"}},
                   {**first, "meta": {**first["meta"], "tradeDate": "2026-09-03", "sourceId": "sina-tencent"}}]
        result = assemble_market(capture(), [first, *invalid])
        self.assertTrue(all(row["baselineDays"] == 0 for row in result["boards"]))

    def test_historical_score_needs_twenty_distinct_prior_measurements(self):
        history = []
        start = datetime(2026, 8, 1)
        for i in range(20):
            day = (start + timedelta(days=i)).date().isoformat()
            history.append(assemble_market(capture(day=day, industry=[row("BK1000", turnover=i+1, day=day)]), []))
        result = assemble_market(capture(industry=[row("BK1000", turnover=30)]), history + [history[0]])
        industry = next(row for row in result["boards"] if row["kind"] == "industry")
        self.assertEqual(industry["baselineDays"], 20)
        self.assertEqual(industry["activityHistory"], 100)

    def test_changed_universe_does_not_claim_rank_change(self):
        first = assemble_market(capture(), [])
        later = "2026-09-07"
        second = assemble_market(capture(day=later, industry=[row("BK1000", day=later), row("BK2000", day=later)]), [first])
        self.assertTrue(all(row["rankChange"] is None for row in second["boards"] if row["kind"] == "industry"))

    def test_failed_stale_or_lower_coverage_capture_preserves_latest(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            full = assemble_market(capture(industry=[row("BK1"), row("BK2")]), [])
            persist_market(root, full)
            path = root / "public/data/market/latest.json"
            before = path.read_bytes()
            for bad in (assemble_market(capture(industry=[row("BK1")]), []),
                        assemble_market(capture(day="2026-09-03"), []),
                        assemble_market(capture(industry=[], concept=[]), [])):
                with self.assertRaises(RuntimeError):
                    persist_market(root, bad)
                self.assertEqual(path.read_bytes(), before)


class FallbackTests(TestCase):
    def test_failed_universe_page_keeps_successful_pages_for_retry(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            cache = root / "work/market-source-cache" / DAY
            for group in ("industry", "concept"):
                atomic_json(cache / ("catalog-" + group + ".json"), {"date": DAY, "data": [{"code": "test", "name": "测试", "declaredMembers": 0}]})
            atomic_json(cache / "members-test.json", {"date": DAY, "data": {"members": [], "complete": True, "expected": 0, "pages": 1}})
            calls, fail_page = [], True
            def response(url, *_args, **_kwargs):
                if "getHQNodeStockCount" in url:
                    return "81"
                if "getHQNodeData" in url:
                    page = int(parse_qs(urlparse(url).query)["page"][0])
                    calls.append(page)
                    if page == 2 and fail_page:
                        raise TimeoutError("test timeout")
                    if page > 2:
                        return "[]"
                    return json.dumps([{"symbol": f"sz{i:06d}", "code": f"{i:06d}"} for i in range(1 if page == 1 else 81, 81 if page == 1 else 82)])
                return ""  # No valid quotes; this case only verifies directory recovery.
            with patch("sentiment.sina_market.request_text", side_effect=response), redirect_stdout(StringIO()):
                first = collect_sina_market(root, DAY, NOW)
                fail_page = False
                second = collect_sina_market(root, DAY, NOW)
            self.assertEqual(len(first["groups"]["stocks"]["rows"]), 80)
            self.assertFalse(first["groups"]["stocks"]["complete"])
            self.assertEqual(len(second["groups"]["stocks"]["rows"]), 81)
            self.assertTrue(second["groups"]["stocks"]["complete"])
            self.assertEqual(calls.count(1), 1)
            self.assertEqual(calls.count(2), 2)

    def test_fallback_uses_dated_constituents_not_undated_aggregates(self):
        for missing, retired in ((False, False), (True, False), (False, True)):
            with self.subTest(missing=missing, retired=retired), TemporaryDirectory() as folder:
                root = Path(folder)
                cache = root / "work/market-source-cache" / DAY
                def save(key, data):
                    atomic_json(cache / (key + ".json"), {"date": DAY, "data": data})
                for group in ("industry", "concept"):
                    save("catalog-" + group, [{"code": "new_test", "name": "新板块", "declaredMembers": 2}])
                members = [{"symbol": "sz000001", "code": "000001", "name": "甲"}, {"symbol": "sz000002", "code": "000002", "name": "乙"}]
                for node in ("hs_a", "new_test"):
                    observed = members + ([{"symbol": "sz000003", "code": "000003", "name": "来源旧成员"}] if retired and node == "new_test" else [])
                    save("members-" + node, {"members": observed, "expected": len(observed), "complete": True, "pages": 1})
                quotes = []
                for i, member in enumerate(members):
                    fields = [""] * 39
                    fields[1], fields[2], fields[3] = member["name"], member["code"], "10"
                    fields[30], fields[32], fields[37], fields[38] = "20260904153000", str(2+i*2), "100", str(4+i*2)
                    if missing and i == 1:
                        fields[30] = "20260903153000"
                    quotes.append(f'v_{member["symbol"]}="' + "~".join(fields) + '";')
                with patch("sentiment.sina_market.request_text", return_value="\n".join(quotes)), redirect_stdout(StringIO()):
                    result = collect_sina_market(root, DAY, NOW)
                board = result["groups"]["industry"]["rows"][0]
                self.assertEqual(board["excludedMemberCount"], int(retired))
                self.assertEqual(board["memberCount"], 2)
                self.assertEqual(result["provider"], "sina-tencent")
                if missing:
                    self.assertIsNone(board["f3"])
                    self.assertIsNone(board["f6"])
                else:
                    self.assertEqual(board["f3"], 3)
                    self.assertEqual(board["f8"], 5)
                    self.assertEqual(board["f6"], 2000000)
