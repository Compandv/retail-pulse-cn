import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prune_data  # noqa: E402


def _snapshot(day):
    return {"meta": {"tradeDate": day, "methodVersion": "v4"},
            "history": [{"date": day, "score": 1}], "scopeHistory": [{"date": day}], "attentionHistory": {"all": [{"date": day}]},
            "summary": {"posts": [{"text": "a"}]},
            "scopes": [{"id": "s", "attention": {"x": 1}, "expressions": {"y": 2}, "posts": [{"text": "b" * 500}, {"text": "c" * 500}]}]}


class PruneDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        data = self.root / "public/data"
        (data / "daily").mkdir(parents=True)
        self.days = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(62)]
        for day in self.days:
            (data / "daily" / f"{day}.json").write_text(json.dumps(_snapshot(day)), encoding="utf-8")
            members = data / "market/members" / day
            members.mkdir(parents=True)
            (members / "gn_x.json").write_text("{}", encoding="utf-8")
        (data / "latest.json").write_text(json.dumps(_snapshot(self.days[-1])), encoding="utf-8")
        (data / "daily" / "index.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, day):
        return json.loads((self.root / "public/data/daily" / f"{day}.json").read_text(encoding="utf-8"))

    def test_dry_run_changes_nothing(self):
        result = prune_data.run(self.root, 60, apply=False)
        self.assertEqual(result["communityPostsRemoved"], self.days[:2])
        self.assertEqual(result["memberDetailsRemoved"], self.days[:2])
        self.assertGreater(result["bytesFreed"], 0)
        self.assertEqual(len(self.read(self.days[0])["scopes"][0]["posts"]), 2)
        self.assertTrue((self.root / "public/data/market/members" / self.days[0]).exists())

    def test_apply_keeps_aggregates_recent_dates_and_latest(self):
        prune_data.run(self.root, 60, apply=True)
        old = self.read(self.days[0])
        self.assertEqual(old["scopes"][0]["posts"], [])
        self.assertEqual(old["summary"]["posts"], [])
        self.assertIn("postsPruned", old["meta"])
        for key in ("history", "scopeHistory", "attentionHistory"):
            self.assertEqual(old[key], _snapshot(self.days[0])[key])
        self.assertEqual(old["scopes"][0]["expressions"], {"y": 2})
        self.assertEqual(len(self.read(self.days[2])["scopes"][0]["posts"]), 2)
        latest = json.loads((self.root / "public/data/latest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(latest["scopes"][0]["posts"]), 2)
        self.assertFalse((self.root / "public/data/market/members" / self.days[1]).exists())
        self.assertTrue((self.root / "public/data/market/members" / self.days[2]).exists())

    def test_second_run_is_a_no_op(self):
        prune_data.run(self.root, 60, apply=True)
        again = prune_data.run(self.root, 60, apply=True)
        self.assertEqual(again["communityPostsRemoved"], [])
        self.assertEqual(again["memberDetailsRemoved"], [])

    def test_keep_below_baseline_window_is_rejected(self):
        with self.assertRaises(SystemExit):
            prune_data.main(["--keep", "20"])


if __name__ == "__main__":
    unittest.main()
