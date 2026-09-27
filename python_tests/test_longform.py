import unittest

from sentiment import longform
from sentiment.report import rebound_expression


def sector(sid, amount=100.0, change=1.0, discussion=50, spread=50, growth=50, panic=5.0, rebound=5.0, crowding=50, codes=("000001",)):
    return {"id": sid, "name": sid, "amount": amount, "changePct": change, "memberCodes": list(codes),
            "dimensions": {"discussion": discussion, "spread": spread, "growth": growth, "crowding": crowding},
            "observation": {"panic": panic, "rebound": rebound, "reboundCount": 1, "sampleCount": 40}}


class DimensionsTest(unittest.TestCase):
    def setUp(self):
        self.sectors = [sector(f"t{i}", amount=100 + i, change=-i, panic=i, rebound=10 - i, crowding=10 * i) for i in range(6)]
        self.prior = {f"t{i}": 100.0 for i in range(6)}  # every topic traded more today

    def test_weighted_total_matches_config_weights(self):
        dims = longform.dimensions_v2(self.sectors, self.prior)
        item = dims["t5"]
        values = item["dimensions"]
        expected = sum(longform.CONFIG["weights"][k] * v for k, v in values.items())
        self.assertAlmostEqual(item["total"], round(expected, 1), places=1)
        self.assertEqual(item["missing"], [])

    def test_volume_drop_only_counts_falling_topics_with_more_turnover(self):
        dims = longform.dimensions_v2(self.sectors, dict(self.prior, t5=1e9))
        self.assertEqual(dims["t5"]["inputs"]["dropValue"], 0)  # fell, but on less turnover
        self.assertEqual(dims["t4"]["inputs"]["dropValue"], 4)
        self.assertEqual(dims["t0"]["inputs"]["dropValue"], 0)  # did not fall

    def test_missing_input_leaves_dimension_and_total_empty(self):
        dims = longform.dimensions_v2(self.sectors, {})
        self.assertIsNone(dims["t1"]["dimensions"]["shake"])
        self.assertIsNone(dims["t1"]["total"])
        self.assertEqual(dims["t1"]["missing"], ["动摇度"])

    def test_too_few_comparable_topics_gives_no_rank(self):
        dims = longform.dimensions_v2(self.sectors[:3], self.prior)
        self.assertIsNone(dims["t0"]["dimensions"]["rebound"])


class LabelsTest(unittest.TestCase):
    def test_shapes_follow_rule_order(self):
        self.assertEqual(longform.shape_of({"heat": 70, "spread": 50, "shake": 70, "rebound": 70, "crowding": 50}), "hotShaky")
        self.assertEqual(longform.shape_of({"heat": 50, "spread": 70, "shake": 40, "rebound": 50, "crowding": 50}), "spreadCalm")
        self.assertEqual(longform.shape_of({"heat": 50, "spread": 50, "shake": 70, "rebound": 70, "crowding": 50}), "shakyRebound")
        self.assertEqual(longform.shape_of({"heat": 50, "spread": 50, "shake": 55, "rebound": 50, "crowding": 50},
                                           {"heat": 62, "shake": 50}), "cooling")
        self.assertEqual(longform.shape_of({"heat": 40, "spread": 40, "shake": 40, "rebound": 40, "crowding": 40}), "quiet")
        self.assertEqual(longform.shape_of({"heat": 40, "spread": None, "shake": 40, "rebound": 40, "crowding": 40}), "neutral")

    def test_alert_levels_and_wording_carry_no_advice(self):
        self.assertEqual(longform.alert_of({"crowding": 80, "shake": 70})["level"], "red")
        self.assertEqual(longform.alert_of({"crowding": 61, "shake": 10})["level"], "yellow")
        self.assertEqual(longform.alert_of({"crowding": 50, "shake": 50})["level"], "green")
        self.assertEqual(longform.alert_of({"crowding": None, "shake": 50})["level"], "grey")
        texts = [rule["text"] for rule in longform.CONFIG["alerts"].values()] + [s["text"] for s in longform.CONFIG["shapes"]]
        for text in texts:
            self.assertFalse(any(word in text for word in longform.CONFIG["forbidden"]), text)


class MainlineTest(unittest.TestCase):
    def test_mainline_is_topic_with_most_limit_ups(self):
        topics = [{"id": "a", "name": "A", "changePct": 3, "memberCodes": ["1", "2"]},
                  {"id": "b", "name": "B", "changePct": 5, "memberCodes": ["2", "3", "4"]}]
        limit = {"coverage": {"limitUp": {"complete": True}}, "metrics": {"limitUp": 10},
                 "limitUp": [{"code": c} for c in ("2", "3", "4", "9")]}
        line = longform.mainline(topics, limit)
        self.assertEqual((line["id"], line["limitUpCount"], line["concentration"]), ("b", 3, 30.0))
        self.assertEqual(topics[0]["limitUpCount"], 1)
        self.assertIsNone(longform.mainline(topics, {"coverage": {"limitUp": {"complete": False}}}))


class SourcesTest(unittest.TestCase):
    def test_anchor_rows_only_on_anniversary(self):
        indices = {"sh000001": {"name": "上证指数", "closes": {"2024-09-23": 2748.92, "2026-09-24": 3888.37}}}
        margin = {"2024-09-23": {"total": 1.37e12}, "2026-09-23": {"total": 2.655e12}}
        rows = longform.anchor_rows(indices, margin, "2026-09-24")
        self.assertEqual(rows[0]["indices"][0]["changePct"], 41.45)
        self.assertEqual(rows[0]["margin"]["end"]["date"], "2026-09-23")
        self.assertEqual(rows[0]["years"], 2)
        self.assertEqual(longform.anchor_rows(indices, margin, "2026-09-23"), [])


class ReboundRuleTest(unittest.TestCase):
    def test_wanting_back_in_counts(self):
        for text in ("卖早了，心疼", "又踏空了", "现在还能上车吗", "等回调接回来"):
            self.assertTrue(rebound_expression(text), text)

    def test_negation_hearsay_and_past_do_not_count(self):
        for text in ("别怕踏空", "不要卖早了", "据说有人卖飞了", "上周卖早了", "如果回调再接回"):
            self.assertFalse(rebound_expression(text), text)


if __name__ == "__main__":
    unittest.main()
