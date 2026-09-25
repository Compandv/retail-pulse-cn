from unittest import TestCase
from sentiment.behavior_audit import audit_accounts, judge_text
from sentiment.following import expression_profile
from python_tests.test_retail_profile import post


class BehaviorAuditTests(TestCase):
    def test_target_is_not_sentiment_or_investor_identity(self):
        for text in ["我今天追高买入了", "我准备追高买入", "我跟着买"]:
            self.assertEqual(judge_text(text)[0], "target", text)
        for text in ["还能追吗？", "无脑冲，肯定翻倍", "主力在建仓", "如果涨停我准备追高买入", "昨天我追高买入了", "他说我准备追高买入", "我不跟着买", "我追高了才怪"]:
            self.assertNotEqual(judge_text(text)[0], "target", text)
        self.assertEqual(judge_text("我今天不追高")[0], "non_target")
        self.assertEqual(judge_text("普通市场讨论")[0], "unknown")
        self.assertEqual(judge_text("今天成交额多少？")[0], "non_target")
        self.assertEqual(judge_text("还能追吗？")[0], "non_target")
        self.assertEqual(judge_text("今天成交额多少？我已经追高买入了")[0], "target")

    def test_all_chasing_is_100_without_multilabel_inflation(self):
        rows = [post("我今天追高买入了", str(i)) for i in range(20)]
        result = audit_accounts(rows * 3, 20, True)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["targetAccounts"], 20)
        self.assertEqual(result["coverage"], 100)
        self.assertEqual(expression_profile(rows, 20, True)["behaviorAudit"], result)

    def test_unknown_does_not_become_negative_or_published_score(self):
        rows = [post("我今天追高买入了", str(i)) for i in range(20)]
        rows += [post("我今天不追高", str(i)) for i in range(20, 50)]
        rows += [post("哈哈哈哈", str(i)) for i in range(50, 100)]
        result = audit_accounts(rows, 100, True)
        self.assertEqual(result["conditionalRate"], 40)
        self.assertEqual(result["observedTargetRate"], 20)
        self.assertEqual(result["coverage"], 50)
        self.assertIsNone(result["score"])
        self.assertEqual(sum(r["count"] for r in result["unknownReasons"]), 50)

    def test_conflicts_truncation_unsampled_and_source_failure(self):
        rows = [post("我今天追高买入了", "a", 1), post("我今天不追高", "a", 2), post("我准备追高买入…", "b", 3)]
        result = audit_accounts(rows, 3, True)
        reasons = {r["key"]: r["count"] for r in result["unknownReasons"]}
        self.assertEqual(reasons["conflict"], 1)
        self.assertEqual(reasons["incomplete"], 1)
        self.assertEqual(reasons["unsampled"], 1)
        self.assertIsNone(result["conditionalRate"])
        self.assertIsNone(audit_accounts([], 0, False)["coverage"])
        rows = [post("我今天追高买入了", str(i)) for i in range(20)]
        self.assertIsNone(audit_accounts(rows, 20, False)["score"])

    def test_evaluation_requires_real_labels_and_counts_abstentions(self):
        from scripts.evaluate_behaviors import evaluate
        self.assertIsNone(evaluate([{"humanLabel": None}])["accuracy"])
        result = evaluate([
            {"id": "a", "text": "我今天追高买入了", "humanLabel": "target"},
            {"id": "b", "text": "无法识别", "humanLabel": "target"},
            {"id": "c", "text": "我今天追高买入了", "humanLabel": "non_target"},
        ])
        self.assertEqual(result["targetPrecision"], .5)
        self.assertEqual(result["targetRecall"], .5)
