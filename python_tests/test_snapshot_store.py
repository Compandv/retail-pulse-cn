import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from sentiment.snapshot_store import load_daily_snapshots, save_daily_files


class SnapshotStoreTest(TestCase):
    def test_daily_snapshots_are_loaded_from_disk(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "public" / "data" / "daily"
            daily.mkdir(parents=True)
            (daily / "2026-09-01.json").write_text('{"meta":{"tradeDate":"2026-09-01","mode":"live"},"history":[]}', encoding="utf-8")
            (daily / "broken.json").write_text("{", encoding="utf-8")
            snapshots = load_daily_snapshots(root)
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["meta"]["tradeDate"], "2026-09-01")

    def test_saving_a_day_updates_the_date_index(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for day in ("2026-09-02", "2026-09-01", "2026-09-02"):
                save_daily_files(root, {"meta": {"tradeDate": day, "methodVersion": "MVP-4.0", "generatedAt": day}})
            index = json.loads((root / "public/data/index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["dates"], ["2026-09-01", "2026-09-02"])
            self.assertEqual(index["latest"], "2026-09-02")
            self.assertTrue((root / "public/data/daily/2026-09-01.json").exists())
