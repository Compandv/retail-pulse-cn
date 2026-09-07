import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from sentiment.following import classify, expression_profile, following_score
from sentiment.market_reading import analyze_report, FIELDS, validate
from python_tests.test_retail_profile import post
from python_tests.test_report import fixture
from sentiment.report import assemble_report


class FollowingTests(TestCase):
    def test_semantics_and_negation(self):
        for text, key, value in [("群里都说涨，我跟着买", "following", 1), ("还能追吗？", "question", 1), ("我今天追高买入了", "chase", 1), ("我准备追高买入", "chase", .7), ("无脑冲，肯定翻倍", "hype", 1), ("利润增长33%，但现金流下降，因此观望", "analysis", 1)]:
            self.assertEqual(classify(text)[0][key], value, text)
        for text in ["不要追高", "昨天追高买入了", "他说，今天追高买入了", "有人问还能追吗", "主力在出货", "我不准备追高", "我今天上车了", "我今天买了", "稳赚？笑死", "他说“无脑冲，肯定翻倍”"]:
            values = classify(text)[0]
            self.assertEqual(sum(values[k] for k in ("following", "chase", "question", "hype")), 0, text)
        self.assertEqual(classify("昨天追高了，今天我准备追高买入")[0]["chase"], .7)

    def test_accounts_unknown_weights_and_missing(self):
        rows = [post("我跟着买，我今天追高买入了，还能追吗，无脑冲", str(i)) for i in range(10)]
        rows += [post("哈哈哈哈", str(i)) for i in range(10,20)]
        p = expression_profile(rows, 20, True)
        self.assertEqual(p["unknownAccounts"], 10)
        self.assertEqual(following_score(p)["score"], 50)
        duplicated = expression_profile(rows + rows[:1] * 100, 20, True)
        self.assertEqual(duplicated["rates"], p["rates"])
        self.assertIsNone(following_score(expression_profile(rows, 20, False))["score"])
        self.assertIsNone(following_score(expression_profile(rows[:10], 10, True))["score"])
        p = expression_profile([post("我准备追高买入", str(i)) for i in range(20)], 20, True)
        self.assertEqual(following_score(p)["score"], 28)

    def test_one_summary_call_cache_and_unchanged_metrics(self):
        market, capture = fixture()
        report = assemble_report(market, capture)
        original = copy.deepcopy(report)
        options = dict(key="test", model="test", mode="shadow")
        calls = []
        def transport(facts, options, **kwargs):
            calls.append(facts)
            self.assertNotIn('"author"', str(facts))
            return {k: {"text": "样本有局限。", "factIds": ["scope"]} for k in FIELDS}, {"usage": {}}
        with TemporaryDirectory() as folder:
            a = analyze_report(Path(folder), report, options, transport)
            b = analyze_report(Path(folder), report, options, transport)
            self.assertEqual(a["status"], "complete")
            self.assertTrue(b["reused"])
            self.assertEqual(len(calls), 1)
            report["sectors"][0]["leekScore"]["score"] = 99
            analyze_report(Path(folder), report, options, transport)
            self.assertEqual(len(calls), 2)
        report["sectors"][0]["leekScore"]["score"] = original["sectors"][0]["leekScore"]["score"]
        self.assertEqual(report, original)

    def test_summary_failure_does_not_become_cached_success(self):
        report = assemble_report(*fixture())
        def bad(*args, **kwargs): return {k: {"text": "杜撰", "factIds": ["nonexistent"]} for k in FIELDS}, {}
        with TemporaryDirectory() as folder:
            result = analyze_report(folder, report, dict(key="test", model="test", mode="shadow"), bad)
            self.assertEqual(result["status"], "error")
            self.assertEqual([p.name for p in Path(folder).glob("**/*.json")], ["last-failure.json"])
        output = {k: {"text": "韭菜分99。", "factIds": ["scope"]} for k in FIELDS}
        validate(output, [{"id": "scope"}])
        self.assertNotIn("99", output["market"]["text"])
        output = {k: {"text": "说明" * 213, "factIds": ["scope"]} for k in FIELDS}
        validate(output, [{"id": "scope"}])
        output["market"]["text"] = "字" * 801
        with self.assertRaises(ValueError): validate(output, [{"id": "scope"}])
