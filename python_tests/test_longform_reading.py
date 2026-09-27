import json
import tempfile
import unittest
from pathlib import Path

from sentiment import longform_reading as reading

FACTS = [{"id": "market.upRate", "label": "红盘率", "display": "20.14%"},
         {"id": "limit.limitUp", "label": "涨停家数", "display": "32"},
         {"id": "topic.0", "label": "题材", "name": "5G通信", "display": "72.4", "shape": "高热高动摇"}]
TEMPLATE = {"source": "template", "title": "模板标题", "oneLiner": "模板一句话。", "topics": {"a": "模板题材句。"}}


def section(text, refs=("market.upRate",)):
    return {"text": text, "factIds": list(refs)}


class CheckTest(unittest.TestCase):
    def test_placeholders_are_filled_with_page_values(self):
        text = reading.check(section("红盘率降到{{f:market.upRate}}，涨停{{f:limit.limitUp}}家"), FACTS, 150)
        self.assertEqual(text, "红盘率降到20.14%，涨停32家")

    def test_bare_digits_are_rejected_but_names_with_digits_are_fine(self):
        with self.assertRaises(ValueError):
            reading.check(section("红盘率只有20%"), FACTS, 150)
        self.assertEqual(reading.check(section("5G通信关注度最高", ("topic.0",)), FACTS, 150), "5G通信关注度最高")

    def test_unknown_ids_advice_words_and_length_are_rejected(self):
        for bad in (section("看{{f:nope}}"), section("可以抄底"), section("走势", ("nope",)), section("长" * 200)):
            with self.assertRaises(ValueError):
                reading.check(bad, FACTS, 150)


class ApplyTest(unittest.TestCase):
    def test_each_section_falls_back_on_its_own(self):
        output = {"title": section("红盘率{{f:market.upRate}}"), "oneLiner": section("明天必涨"), "topics": [section("5G通信分歧明显", ("topic.0",))]}
        narrative, fallbacks = reading.apply(output, TEMPLATE, FACTS, "daily", ["a"])
        self.assertEqual(narrative["title"], "红盘率20.14%")
        self.assertEqual(narrative["oneLiner"], "模板一句话。")
        self.assertEqual(narrative["topics"]["a"], "5G通信分歧明显")
        self.assertEqual(fallbacks, ["oneLiner"])
        self.assertEqual(narrative["source"], "model")


class NarrateTest(unittest.TestCase):
    def report(self):
        return {"narrative": dict(TEMPLATE), "market": {"upRate": 20.14, "up": 1120, "down": 4375, "amount": 1.6e12, "amountChange": None},
                "limit": {"metrics": {"limitUp": 32}}, "indices": [], "mainline": None,
                "topics": [{"id": "a", "name": "5G通信", "total": 72.4, "changePct": 1.0, "missing": [], "shape": {"label": "高热高动摇", "text": "x"}, "alert": {"level": "red"}}]}

    def test_without_key_the_template_is_kept_and_nothing_is_sent(self):
        calls = []
        result = reading.narrate(".", self.report(), "daily", options={"mode": "shadow", "key": ""}, transport=lambda *a, **k: calls.append(a))
        self.assertEqual(result["title"], "模板标题")
        self.assertEqual(result["modelStatus"], "needs_key")
        self.assertEqual(calls, [])

    def test_model_output_is_validated_and_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            options = {"mode": "shadow", "key": "test", "model": "m", "base_url": "https://example.test/v1", "api_type": "responses"}
            calls = []

            def transport(facts, opts, **kwargs):
                calls.append(facts)
                ids = {f["id"] for f in facts}
                self.assertIn("topic.0", ids)
                return {"title": section("红盘率{{f:market.upRate}}"), "oneLiner": section("涨停{{f:limit.limitUp}}家", ("limit.limitUp",)),
                        "topics": [section("5G通信拥挤", ("topic.0",))]}, {"usage": {}}
            first = reading.narrate(folder, self.report(), "daily", options, transport)
            second = reading.narrate(folder, self.report(), "daily", options, transport)
            self.assertEqual(first["title"], "红盘率20.14%")
            self.assertEqual(first["topics"]["a"], "5G通信拥挤")
            self.assertEqual(second["oneLiner"], "涨停32家")
            self.assertEqual(len(calls), 1)  # second run reads the cache
            cached = list(Path(folder, "work/longform-reading").glob("*.json"))
            self.assertTrue(any("output" in json.loads(p.read_text(encoding="utf-8")) for p in cached))

    def test_transport_failure_keeps_template(self):
        with tempfile.TemporaryDirectory() as folder:
            def broken(*a, **k):
                raise RuntimeError("down")
            options = {"mode": "shadow", "key": "test", "model": "m", "base_url": "https://example.test/v1", "api_type": "responses"}
            result = reading.narrate(folder, self.report(), "daily", options, broken)
            self.assertEqual(result["modelStatus"], "error")
            self.assertEqual(result["oneLiner"], "模板一句话。")


if __name__ == "__main__":
    unittest.main()
