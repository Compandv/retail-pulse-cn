"""Offline regression tests for metadata, coverage and descriptive market facts."""
import copy
import json
from pathlib import Path
from unittest import TestCase

from sentiment.following import METHOD, WEIGHTS, expression_profile, following_score
from sentiment.market_diagnostics import build_market_diagnostics
from sentiment.market_watch import assemble_market
from sentiment.report import assemble_report, measure_members
from python_tests.test_report import fixture
from python_tests.test_market_watch import capture, DAY


def observation(index, text="随便聊聊市场"):
    return {"id": str(index), "author": str(index), "source": "eastmoney", "date": f"{DAY} 10:00:00", "text": text}


def quote(code, change=1, amount=100, turnover=2, dated=True):
    return {"code": str(code), "dateValid": dated, "changePct": change, "amount": amount, "turnover": turnover}


class ReliabilityTests(TestCase):
    def test_shared_definition_preserves_original_scoring(self):
        self.assertEqual(WEIGHTS, {"following": .3, "chase": .4, "question": .2, "hype": .1})
        config = json.loads((Path(__file__).resolve().parents[1] / "config/measurement.json").read_text(encoding="utf-8"))
        self.assertEqual(METHOD["maxPostsPerAccount"], config["maxPostsPerAuthor"])
        self.assertEqual(METHOD["minimumAccounts"], 20)
        profile = expression_profile([observation(i, "我准备追高买入") for i in range(20)], 20, True)
        self.assertEqual(following_score(profile)["score"], 28)

    def test_unknown_split_keeps_the_same_denominator(self):
        posts = [observation(i, "我今天追高买入了") for i in range(10)]
        posts += [observation(i) for i in range(10, 15)]
        before = copy.deepcopy(posts)
        profile = expression_profile(posts, 20, True)
        self.assertEqual(profile["sampledAccounts"], 15)
        self.assertEqual(profile["unmatchedAccounts"], 5)
        self.assertEqual(profile["unsampledAccounts"], 5)
        self.assertEqual(profile["unknownAccounts"], 10)
        self.assertEqual(profile["unknownRate"], 50)
        self.assertEqual(following_score(profile)["score"], 20)
        self.assertEqual(posts, before)

    def test_empty_profile_is_not_a_neutral_score(self):
        profile = expression_profile([], 0, False)
        self.assertIsNone(profile["unknownRate"])
        self.assertIsNone(following_score(profile)["score"])
        self.assertEqual(profile["unmatchedAccounts"], 0)
        self.assertEqual(profile["unsampledAccounts"], 0)

    def test_content_provenance_is_not_guessed_from_missing_fields(self):
        _, batch = fixture()
        code = next(iter(batch["feeds"]))
        result = measure_members(batch, [code], DAY)
        self.assertEqual(result["contentCoverage"], {"bodyTexts": 0, "titleOnlyTexts": 0, "unspecifiedTexts": 20, "total": 20})
        self.assertEqual(result["unknownAuthorPosts"], 0)
        rows = [r for r in batch["feeds"][code]["rows"] if r["date"].startswith(DAY)]
        rows[0]["contentKind"] = "正文"
        rows[1]["contentKind"] = "标题"
        rows[2]["contentKind"] = "标题"
        batch["profileBodies"] = {rows[2]["id"]: {**rows[2], "text": "我准备追高买入"}}
        result = measure_members(batch, [code], DAY)
        self.assertEqual(result["contentCoverage"], {"bodyTexts": 2, "titleOnlyTexts": 1, "unspecifiedTexts": 17, "total": 20})
        self.assertEqual(result["bodyObserved"], 1)
        batch["profileBodies"][rows[2]["id"]]["author"] = "different"
        result = measure_members(batch, [code], DAY)
        self.assertEqual(result["bodyObserved"], 0)
        self.assertEqual(result["contentCoverage"]["bodyTexts"], 1)

    def test_report_quality_metadata_has_distinct_complete_entry_count(self):
        market, batch = fixture()
        report = assemble_report(market, batch)
        self.assertEqual(report["meta"]["qualityVersion"], "observation-quality-1.0")
        self.assertEqual(report["meta"]["marketTradeDate"], market["meta"]["tradeDate"])
        self.assertEqual(report["meta"]["feedComplete"], report["meta"]["feedExpected"])
        first = next(iter(batch["feeds"]))
        batch["feeds"][first]["complete"] = False
        updated = assemble_report(market, batch)
        self.assertEqual(updated["meta"]["feedObserved"], report["meta"]["feedObserved"])
        self.assertEqual(updated["meta"]["feedComplete"], report["meta"]["feedComplete"] - 1)
        self.assertNotIn('"author"', json.dumps(updated))


class MarketDiagnosticsTests(TestCase):
    def test_partition_boundaries_and_known_zero_are_distinct_from_missing(self):
        rows = [quote(i, v) for i, v in enumerate([-10, -5, -4.99, 0, 4.99, 5, 10])]
        d = build_market_diagnostics(rows, {"expected": 7, "complete": True})
        self.assertEqual([x["count"] for x in d["distribution"]], [2, 1, 1, 1, 2])
        self.assertEqual(sum(x["count"] for x in d["distribution"]), 7)
        self.assertEqual(d["netAdvanceShare"], 0)
        self.assertEqual(d["medianTurnover"], 2)
        self.assertIsNone(d["top10AmountShare"])

    def test_full_turnover_concentration_uses_unique_stocks(self):
        rows = [quote(i, amount=i + 1) for i in range(12)]
        before = copy.deepcopy(rows)
        d = build_market_diagnostics(rows + [copy.deepcopy(rows[0])], {"expected": 12, "complete": True})
        self.assertEqual(d["observed"], 12)
        self.assertEqual(d["top10AmountShare"], round(100 * 75 / 78, 2))
        self.assertTrue(d["amountComplete"])
        self.assertEqual(rows, before)

    def test_missing_amount_or_catalog_does_not_produce_concentration(self):
        rows = [quote(i) for i in range(12)]
        for catalog in [{"expected": 12, "complete": False}, {"expected": 13, "complete": True}, {"expected": None, "complete": True}]:
            self.assertIsNone(build_market_diagnostics(rows, catalog)["top10AmountShare"])
        rows[0]["amount"] = None
        d = build_market_diagnostics(rows, {"expected": 12, "complete": True})
        self.assertFalse(d["amountComplete"])
        self.assertEqual(d["amountCoverage"], 11)
        self.assertIsNone(d["top10AmountShare"])

    def test_stale_conflicting_and_nonfinite_quotes_are_excluded(self):
        rows = [quote("a", dated=False), quote("b", change=2), quote("b", change=3), quote("c", change=float("nan"), amount=-1, turnover=True), quote("d", change=None)]
        d = build_market_diagnostics(rows, {"expected": 4, "complete": True})
        self.assertEqual(d["conflictingCodes"], 1)
        self.assertEqual(d["changeCoverage"], 0)
        self.assertIsNone(d["netAdvanceShare"])
        self.assertTrue(all(x["count"] is None and x["share"] is None for x in d["distribution"]))
        self.assertFalse(d["catalogComplete"])
        json.dumps(d, allow_nan=False)

    def test_empty_and_zero_amount_totals_are_not_neutral_defaults(self):
        empty = build_market_diagnostics([], {"expected": 0, "complete": True})
        self.assertIsNone(empty["medianTurnover"])
        self.assertIsNone(empty["netAdvanceShare"])
        d = build_market_diagnostics([quote(i, amount=0) for i in range(12)], {"expected": 12, "complete": True})
        self.assertTrue(d["amountComplete"])
        self.assertIsNone(d["top10AmountShare"])

    def test_market_pipeline_does_not_hide_conflicting_quotes(self):
        batch = capture()
        duplicate = copy.deepcopy(batch["groups"]["stocks"]["rows"][0])
        duplicate["f3"] = float(duplicate["f3"]) + 1
        batch["groups"]["stocks"]["rows"].append(duplicate)
        market = assemble_market(batch, [])
        self.assertEqual(market["market"]["diagnostics"]["conflictingCodes"], 1)
        self.assertEqual(market["market"]["diagnostics"]["changeCoverage"], market["market"]["quoted"] - 1)

    def test_market_pipeline_includes_additive_diagnostics(self):
        batch = capture()
        before = copy.deepcopy(batch)
        market = assemble_market(batch, [])
        self.assertEqual(market["market"]["diagnostics"]["version"], "market-diagnostics-1.0")
        self.assertEqual(market["market"]["diagnostics"]["changeCoverage"], market["market"]["quoted"])
        self.assertEqual(batch, before)
