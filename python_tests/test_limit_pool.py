import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sentiment import limit_pool

DAY = date(2026, 9, 24)


def row(code, **fields):
    return {"c": code, "n": f"股{code}", "zdp": 10.0, "hybk": "电子", **fields}


def fake_fetch(pools, qdate="20260924", page_size=None):
    """Serve pools by endpoint name; optionally force small pages."""
    def fetch(url, referer, timeout=15, attempts=2):
        query = parse_qs(urlparse(url).query)
        name = urlparse(url).path.strip("/")
        rows = pools.get(name, [])
        size = page_size or int(query["pagesize"][0])
        page = int(query["Pageindex"][0])
        return json.dumps({"rc": 0, "data": {"tc": len(rows), "qdate": int(qdate), "pool": rows[page * size:(page + 1) * size]}})
    return fetch


POOLS = {
    "getTopicZTPool": [row("000001", lbc=1, zbc=0, fbt=93000, lbt=93000, zttj={"days": 1, "ct": 1}),
                       row("000002", lbc=3, zbc=1, fbt=100512, lbt=132000, zttj={"days": 3, "ct": 3}),
                       row("000003", lbc=5, zbc=0, fbt=92500, lbt=92500, zttj={"days": 7, "ct": 5}),
                       row("000004", lbc=2, zbc=0)],
    "getTopicZBPool": [row("000010", zdp=3.0, zbc=2)],
    "getTopicDTPool": [row("000020", zdp=-10.0, days=2)],
    "getYesterdayZTPool": [row("000002", zdp=10.0, ylbc=2), row("000003", zdp=10.0, ylbc=4),
                           row("000030", zdp=-5.0, ylbc=1), row("000031", zdp=1.0, ylbc=3)],
}


class LimitPoolTest(unittest.TestCase):
    def test_metrics_from_complete_pools(self):
        capture = limit_pool.collect(DAY, fake_fetch(POOLS))
        m = limit_pool.metrics(capture["pools"])
        self.assertEqual((m["limitUp"], m["limitDown"], m["broken"]), (4, 1, 1))
        self.assertEqual(m["brokenRate"], 20.0)  # 1 / (4 + 1)
        self.assertEqual(m["maxBoards"], 5)
        self.assertEqual(m["maxBoardStocks"], [{"code": "000003", "name": "股000003"}])
        self.assertEqual(m["ladder"], {"1": 1, "2": 1, "3": 1, "4": 0, "5+": 1})
        self.assertEqual(m["yesterdayMean"], 4.0)
        self.assertEqual(m["yesterdayStreakMean"], 7.0)  # ylbc>=2: 10, 10, 1
        self.assertEqual((m["promoted"], m["promotionRate"]), (2, 50.0))

    def test_wrong_date_is_rejected_not_relabelled(self):
        capture = limit_pool.collect(DAY, fake_fetch(POOLS, qdate="20260923"))
        for pool in capture["pools"].values():
            self.assertFalse(pool["complete"])
            self.assertIn("20260923", pool["error"])
        self.assertIsNone(limit_pool.metrics(capture["pools"])["limitUp"])

    def test_past_session_is_served_although_qdate_is_latest(self):
        # qdate is the provider's latest session, not the rows' date.
        capture = limit_pool.collect(date(2026, 9, 16), fake_fetch(POOLS, qdate="20260924"))
        self.assertTrue(all(pool["complete"] for pool in capture["pools"].values()))

    def test_non_trading_day_is_never_requested(self):
        calls = []
        with self.assertRaises(RuntimeError):
            limit_pool.collect(date(2026, 9, 26), lambda *a, **k: calls.append(a) or "{}")
        self.assertEqual(calls, [])

    def test_all_empty_pools_mean_out_of_range(self):
        capture = limit_pool.collect(date(2026, 9, 3), fake_fetch({}))
        self.assertTrue(all(not pool["complete"] and "保留期" in pool["error"] for pool in capture["pools"].values()))
        self.assertIsNone(limit_pool.metrics(capture["pools"])["limitUp"])

    def test_chain_check_rejects_another_days_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            previous = dict(POOLS, getTopicZTPool=[row(code, lbc=1) for code in ("000002", "000003", "000030", "000031")])
            limit_pool.save(root, limit_pool.collect(date(2026, 9, 23), fake_fetch(previous)))
            saved = limit_pool.save(root, limit_pool.collect(DAY, fake_fetch(POOLS)))
            self.assertTrue(saved["chainCheck"]["passed"])
            self.assertEqual(saved["chainCheck"]["matchRate"], 100.0)
            unrelated = dict(POOLS, getYesterdayZTPool=[row(f"9{i:05d}", ylbc=1) for i in range(4)])
            with tempfile.TemporaryDirectory() as other:
                limit_pool.save(Path(other), limit_pool.collect(date(2026, 9, 23), fake_fetch(previous)))
                with self.assertRaises(RuntimeError):
                    limit_pool.save(Path(other), limit_pool.collect(DAY, fake_fetch(unrelated)))
                self.assertFalse((Path(other) / "public/data/limit/daily/2026-09-24.json").exists())

    def test_pages_are_followed_until_total(self):
        many = {"getTopicZTPool": [row(f"{i:06d}", lbc=1) for i in range(7)]}
        original = limit_pool.PAGE_SIZE
        limit_pool.PAGE_SIZE = 3
        try:
            pool = limit_pool.fetch_pool("limitUp", DAY, fake_fetch(many))
        finally:
            limit_pool.PAGE_SIZE = original
        self.assertTrue(pool["complete"])
        self.assertEqual(len(pool["rows"]), 7)

    def test_small_streak_subset_and_missing_yesterday_stay_empty(self):
        pools = dict(POOLS, getYesterdayZTPool=[row("000002", zdp=1.0, ylbc=2)])
        m = limit_pool.metrics(limit_pool.collect(DAY, fake_fetch(pools))["pools"])
        self.assertIsNone(m["yesterdayStreakMean"])
        broken = limit_pool.collect(DAY, fake_fetch({"getTopicZTPool": POOLS["getTopicZTPool"]}))
        broken["pools"]["yesterday"] = {"expected": None, "rows": [], "complete": False, "error": "timeout"}
        m = limit_pool.metrics(broken["pools"])
        self.assertIsNone(m["promotionRate"])
        self.assertIsNone(m["yesterdayMean"])

    def test_save_writes_public_snapshot_and_keeps_better_day(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            good = limit_pool.collect(DAY, fake_fetch(POOLS))
            summary = limit_pool.save(root, good)
            self.assertEqual(summary["meta"]["tradeDate"], "2026-09-24")
            self.assertEqual(summary["limitUp"][1]["streak"], "3天3板")
            self.assertEqual(summary["limitUp"][1]["firstSeal"], "10:05:12")
            self.assertNotIn("ltsz", json.dumps(summary))
            index = json.loads((root / "public/data/limit/index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["dates"], ["2026-09-24"])
            worse = limit_pool.collect(DAY, fake_fetch(POOLS, qdate="20260923"))
            with self.assertRaises(RuntimeError):
                limit_pool.save(root, worse)
            self.assertEqual(json.loads((root / "public/data/limit/latest.json").read_text(encoding="utf-8"))["metrics"]["limitUp"], 4)


if __name__ == "__main__":
    unittest.main()
