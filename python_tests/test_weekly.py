import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sentiment import weekly


def daily(day, topics, mainline=None):
    return {"meta": {"tradeDate": day}, "mainline": mainline,
            "topics": [{"id": tid, "name": tid.upper(), "total": total, "changePct": 1.0, "limitUpCount": 1,
                        "dimensions": {"heat": total, "spread": 50, "shake": 50, "rebound": 50, "crowding": 50}} for tid, total in topics]}


def write(root, folder, name, payload):
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


INDICES = {"sh000001": {"name": "上证指数", "closes": {"2026-09-18": 100.0, "2026-09-21": 101.0, "2026-09-22": 102.0, "2026-09-23": 99.0, "2026-09-24": 99.4}}}


class WeekCalendarTest(unittest.TestCase):
    def test_week_boundaries_follow_the_trading_calendar(self):
        self.assertEqual(weekly.week_id(date(2026, 9, 24)), "2026-W39")
        self.assertEqual([d.isoformat() for d in weekly.sessions("2026-W39")], ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"])
        self.assertTrue(weekly.is_week_end(date(2026, 9, 24)))  # 09-25 is a holiday
        self.assertFalse(weekly.is_week_end(date(2026, 9, 23)))
        self.assertEqual([d.isoformat() for d in weekly.sessions("2026-W41")], ["2026-10-08", "2026-10-09"])

    def test_publication_threshold(self):
        self.assertEqual(weekly.required_days(5), 3)
        self.assertEqual(weekly.required_days(4), 3)
        self.assertEqual(weekly.required_days(3), 3)
        self.assertEqual(weekly.required_days(2), 2)


class WeeklyBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_topic_scores_average_days_present_and_need_two(self):
        days = ["2026-09-21", "2026-09-22", "2026-09-23"]
        write(self.root, "public/data/longform/daily", f"{days[0]}.json", daily(days[0], [("a", 60), ("b", 40)], {"name": "A", "concentration": 10, "limitUpCount": 1, "limitUpTotal": 10}))
        write(self.root, "public/data/longform/daily", f"{days[1]}.json", daily(days[1], [("a", 70), ("c", 90)], {"name": "C", "concentration": 20, "limitUpCount": 2, "limitUpTotal": 10}))
        write(self.root, "public/data/longform/daily", f"{days[2]}.json", daily(days[2], [("a", None), ("b", 50)], {"name": "C", "concentration": 30, "limitUpCount": 3, "limitUpTotal": 10}))
        write(self.root, "public/data/report/daily", f"{days[0]}.json", {"flows": {"rows": [{"boardId": "x", "name": "电子", "kind": "industry", "net": -5e8}]}})
        write(self.root, "public/data/report/daily", f"{days[1]}.json", {"flows": {"rows": [{"boardId": "x", "name": "电子", "kind": "industry", "net": -1e8}]}})
        result = weekly.build_weekly(self.root, "2026-W39", INDICES, with_recap=False)
        self.assertTrue(result["meta"]["topicsPublished"])
        self.assertFalse(result["meta"]["complete"])
        self.assertEqual(result["meta"]["missingDays"], ["2026-09-24"])
        topics = {t["id"]: t for t in result["topics"]}
        self.assertEqual(topics["a"]["total"], 65.0)  # (60 + 70) / 2; the empty day is skipped
        self.assertEqual(topics["b"]["total"], 45.0)
        self.assertIsNone(topics["c"]["total"])  # one scored day is not enough
        self.assertEqual(result["topics"][0]["id"], "a")
        self.assertEqual(result["market"]["mainlineSwitches"], 1)  # A -> C -> C
        self.assertEqual(result["flows"]["industry"]["outflow"][0]["net"], -6e8)
        self.assertEqual(result["flows"]["industry"]["outflow"][0]["days"], 2)
        self.assertEqual(result["indices"][0]["changePct"], -0.6)  # 99.4 vs 100 on 09-18

    def test_too_few_days_publish_market_part_only(self):
        write(self.root, "public/data/longform/daily", "2026-09-21.json", daily("2026-09-21", [("a", 60)]))
        write(self.root, "public/data/limit/daily", "2026-09-22.json", {"metrics": {"limitUp": 63, "limitDown": 3, "brokenRate": 22.2, "maxBoards": 6}})
        result = weekly.build_weekly(self.root, "2026-W39", INDICES, with_recap=False)
        self.assertFalse(result["meta"]["topicsPublished"])
        self.assertEqual(result["topics"], [])
        self.assertEqual(result["timeline"][1]["limitUp"], 63)
        self.assertIn("缺少 3 个交易日", "".join(result["narrative"]["conclusions"]))

    def test_recap_lists_values_without_verdicts(self):
        current = {"market": {"meanAmount": 1.9e12, "minUpRate": 20.6, "meanLimitUp": 67.2, "maxBoards": 6, "mainlineSwitches": 3, "shChange": -0.6}}
        previous = {"market": {"meanAmount": 1.79e12, "minUpRate": None, "meanLimitUp": 60.0, "maxBoards": 6, "mainlineSwitches": None, "shChange": 0.61}}
        rows = {r["label"]: r for r in weekly.recap(current, previous)}
        self.assertEqual(rows["日均成交额"]["current"], "1.90 万亿")
        self.assertEqual(rows["最低红盘率"]["previous"], "—")
        self.assertEqual(rows["上证指数周涨跌"]["previous"], "+0.61%")
        text = json.dumps(rows, ensure_ascii=False)
        for word in ("印证", "兑现", "预判"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
