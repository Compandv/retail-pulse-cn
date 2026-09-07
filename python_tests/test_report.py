import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from python_tests.test_market_watch import capture as market_capture, row, DAY
from sentiment.market_watch import assemble_market, atomic_json
from sentiment.report import assemble_report, build_report, refill_expression, relative, score
from sentiment.report_sources import VERSION, select_hot_boards, fetch_flow, fetch_index


def fixture():
    codes = ["300001", "000001", "000002", "000003", "000004"]
    market = assemble_market(market_capture(concept=[row(f"BK{9000+i}", i+1, i+1) for i in range(5)], stocks=[row(c, amount=400 if i == 0 else 100) for i, c in enumerate(codes)]), [])
    selected = select_hot_boards(market)
    batch = {"version": VERSION, "date": DAY, "previousDate": "2026-09-03", "collectedAt": "2026-09-05T16:00:00+08:00", "marketCollectedAt": market["meta"]["collectedAt"], "selectedIds": [b["id"] for b in selected], "members": {}, "feeds": {}, "flows": {}, "errors": [],
             "indices": {s: {"symbol": s, "name": s, "volumeScore": value, "baselineDays": 60, "date": DAY} for s, value in [("sh000001", 20), ("sz399001", 60)]},
             "stockFacts": [{"code": c, "date": DAY, "amount": 400 if i == 0 else 100} for i, c in enumerate(codes)]}
    for board, code in zip(selected, codes):
        batch["members"][board["id"]] = {"date": DAY, "complete": True, "members": [{"code": code}]}
        posts = [{"id": f"{code}-{day}-{i}", "date": f"{day} 10:00:00", "source": "eastmoney", "author": f"{code}-{i}", "code": code, "text": "今天追高买入了，继续看涨" if i % 2 else "今天补了仓，继续看涨", "url": "https://example.com/post", "replies": i, "forwards": 0} for day in [DAY, "2026-09-03"] for i in range(20)]
        batch["feeds"][code] = {"pages": 1, "error": None, "complete": True, "rows": posts, "observedAt": "2026-09-05T16:10:00+08:00"}
    b = selected[0]
    batch["flows"][b["id"]] = {"boardId": b["id"], "name": b["name"], "code": b["code"], "kind": "concept", "date": DAY, "net": -200000000, "changePct": 3}
    return market, batch


class ReportTests(TestCase):
    def test_thermometers_keep_distinct_denominators_and_observation_time(self):
        market, batch = fixture()
        report = assemble_report(market, batch)
        values = {r["key"]: r["score"] for r in report["thermometers"]}
        self.assertEqual(values["activity"], 40)
        self.assertEqual(values["discussion"], 50)
        self.assertEqual(values["profit"], 100)
        self.assertEqual(values["risk"], 50)
        self.assertEqual(report["meta"]["interactionAsOf"], "2026-09-05T16:10:00+08:00")
        self.assertEqual(report["flows"]["rows"][0]["diagnosis"], "上涨伴随资金净流出")
        self.assertNotIn('"author"', json.dumps(report))

    def test_mismatched_market_capture_is_rejected(self):
        market, batch = fixture()
        for key, value in [("date", "2026-09-03"), ("selectedIds", []), ("marketCollectedAt", "different")]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                assemble_report(market, {**batch, key: value})

    def test_thin_missing_or_incomplete_inputs_do_not_produce_composites(self):
        market, batch = fixture()
        for f in batch["feeds"].values():
            f.update(error="timeout", complete=False, pages=0)
        batch["indices"] = {}; batch["stockFacts"] = []
        result = assemble_report(market, batch)
        values = {r["key"]: r["score"] for r in result["thermometers"]}
        self.assertIsNone(values["activity"]); self.assertIsNone(values["discussion"]); self.assertIsNone(values["risk"])
        self.assertEqual(result["meta"]["feedObserved"], 0)
        self.assertTrue(all(r["dimensions"]["overheat"] is None for r in result["sectors"]))

    def test_overlap_and_duplicate_stocks_cannot_inflate_risk_share(self):
        market, batch = fixture()
        batch["stockFacts"].append(copy.deepcopy(batch["stockFacts"][0]))
        result = assemble_report(market, batch)
        self.assertEqual(next(r["score"] for r in result["thermometers"] if r["key"] == "risk"), 50)

    def test_same_input_replay_and_failed_rerun_preserve_report(self):
        market, batch = fixture()
        with TemporaryDirectory() as folder:
            root = Path(folder); atomic_json(root / "public/data/market/latest.json", market)
            first = build_report(root, copy.deepcopy(batch))
            self.assertEqual(build_report(root, copy.deepcopy(batch)), first)
            path = root / "public/data/report/latest.json"; before = path.read_bytes()
            batch["flows"] = {}
            with self.assertRaises(RuntimeError): build_report(root, batch)
            self.assertEqual(path.read_bytes(), before)

    def test_refill_rule_excludes_questions_negation_and_reported_history(self):
        for text in ["今天补了仓", "今天回调，补仓摊低成本"]:
            self.assertTrue(refill_expression(text), text)
        for text in ["不要补仓", "今天补仓？", "该不该补仓", "昨天补了仓", "他说，今天补了仓", "如果继续跌就补仓", "不敢补仓", "没有补仓"]:
            self.assertFalse(refill_expression(text), text)
        self.assertIsNone(score(float("nan")))
        self.assertIsNone(relative([1, 2, 3, 4], 3))
        self.assertEqual(relative([0] * 5, 0), 0)


class ReportSourcesTests(TestCase):
    def test_funds_use_dated_main_net_field_and_keep_signed_units(self):
        board = {"provider": "sina-tencent", "id": "id", "code": "new_test", "name": "测试", "kind": "industry"}
        rows = [{"opendate": "2026-09-07", "r0_net": "999"}, {"opendate": DAY, "r0_net": "-123000000", "netamount": "900000000", "r0_ratio": "-0.12", "avg_changeratio": "0.03"}]
        with patch("sentiment.report_sources.request_text", return_value=json.dumps(rows)):
            result = fetch_flow(board, DAY)
        self.assertEqual(result["net"], -123000000); self.assertEqual(result["ratio"], -12); self.assertEqual(result["changePct"], 3)
        with patch("sentiment.report_sources.request_text", return_value=json.dumps(rows[:1])), self.assertRaises(RuntimeError): fetch_flow(board, DAY)

    def test_index_volume_baseline_excludes_same_day_and_future(self):
        rows = [[f"2026-08-{i:02}", "1", "1", "1", "1", str(i)] for i in range(1, 21)]
        rows += [[DAY, "1", "1", "1", "1", "30"], ["2026-09-07", "1", "1", "1", "1", "999999"]]
        with patch("sentiment.report_sources.request_text", return_value=json.dumps({"data": {"sh000001": {"day": rows}}})):
            result = fetch_index("sh000001", "上证", DAY)
        self.assertEqual(result["volumeScore"], 100); self.assertEqual(result["baselineDays"], 20)
