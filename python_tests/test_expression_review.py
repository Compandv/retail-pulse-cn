import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import expression_review  # noqa: E402


def post(i, text, panic=False, bullish=False, bearish=False, chase=False):
    return {"id": str(i), "text": text, "date": "2026-09-28 10:00:00", "code": "300750", "refillExpression": False,
            "classification": {"panic": panic, "chase": chase, "bullish": bullish, "bearish": bearish}}


class ExpressionReviewTest(unittest.TestCase):
    def test_draw_deduplicates_and_splits_by_rule_hits(self):
        posts = [post(1, "割肉了", panic=True), post(2, "割 肉了", panic=True), post(3, "明天涨", bullish=True),
                 post(4, "闲聊一"), post(5, "闲聊二"), post(6, "卖飞了"), post(7, "追进去了", chase=True)]
        chosen, population = expression_review.draw(posts, "2026-09-28", 4)
        # "卖飞了" fires the rebound rule and the chase flag counts as greed: four distinct rule-positive texts.
        self.assertEqual(population, {"rule_positive": 4, "rule_negative": 2})
        self.assertEqual(sorted(s for _, _, s in chosen), ["rule_negative", "rule_negative", "rule_positive", "rule_positive"])

    def test_evaluate_prefers_human_and_weights_strata(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(expression_review, "ROOT", Path(tmp)):
            out = expression_review.folder("2026-09-28")
            out.mkdir(parents=True)
            no = {"panic": False, "greed": False, "direction": "none", "rebound": False}
            rules = {"p1": {**no, "panic": True, "stratum": "rule_positive"}, "p2": {**no, "panic": True, "stratum": "rule_positive"},
                     "n1": {**no, "stratum": "rule_negative"}, "n2": {**no, "stratum": "rule_negative"}}
            meta = {"population": {"rule_positive": 10, "rule_negative": 90}, "sampled": {"rule_positive": 2, "rule_negative": 2}, "spotCheck": []}
            ai = [{"id": "p1", **no, "panic": True}, {"id": "p2", **no, "panic": True},
                  {"id": "n1", **no, "panic": True}, {"id": "n2", **no, "unsure": True}]
            queue = [{"id": "p2", "text": "x", "humanPanic": False, "humanGreed": False, "humanDirection": "none", "humanRebound": False},
                     {"id": "n2", "text": "y", "humanPanic": False, "humanGreed": False, "humanDirection": "unsure", "humanRebound": False}]
            (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            (out / "rule-predictions.json").write_text(json.dumps(rules), encoding="utf-8")
            expression_review.write_jsonl(out / "ai-labels.jsonl", ai)
            expression_review.write_jsonl(out / "review-queue.jsonl", queue)
            result = expression_review.evaluate("2026-09-28")
        # AI-unsure items still count for agreement: the AI gave an answer, only flagged it.
        self.assertEqual(result["aiHumanAgreement"]["panic"], {"compared": 2, "agree": 1, "rate": 50.0})
        self.assertEqual(result["aiHumanAgreement"]["direction"]["compared"], 1)  # n2's "unsure" is not an answer
        # n2 has no confident direction from either side, so three items form the reference.
        self.assertEqual(result["referenceItems"], 3)
        panic = result["rulesVsReference"]["panic"]
        self.assertEqual(panic["precision"], 50.0)  # p1 right, p2 overruled by the human
        # Positive weight 5, negative weight 45: recall = 5 / (5 + 45).
        self.assertEqual(panic["recall"], 10.0)


if __name__ == "__main__":
    unittest.main()
