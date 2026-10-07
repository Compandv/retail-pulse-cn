import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_data_conflict as resolver  # noqa: E402


def raw(value) -> bytes:
    return json.dumps(value).encode()


class ChooseTest(unittest.TestCase):
    def test_index_lists_are_united(self):
        merged = resolver.choose("index.json", raw({"dates": ["2026-09-30", "2026-10-09"]}), raw({"dates": ["2026-09-30"], "v": 1}))
        self.assertEqual(json.loads(merged), {"dates": ["2026-09-30", "2026-10-09"], "v": 1})
        local = raw({"weeks": ["2026-W40", "2026-W41"]})
        self.assertIs(resolver.choose("weekly/index.json", raw({"weeks": ["2026-W40"]}), local), local)  # nothing new: kept verbatim

    def test_newer_snapshot_wins_and_local_wins_a_tie(self):
        remote, local = raw({"meta": {"tradeDate": "2026-10-09"}}), raw({"meta": {"tradeDate": "2026-09-30"}})
        self.assertIs(resolver.choose("latest.json", remote, local), remote)
        same = raw({"meta": {"tradeDate": "2026-10-09"}, "v": "local"})
        self.assertIs(resolver.choose("latest.json", remote, same), same)

    def test_unparseable_side_and_both_broken(self):
        local = raw({"a": 1})
        self.assertIs(resolver.choose("x.json", b"{broken", local), local)
        self.assertIs(resolver.choose("x.json", local, None), local)  # deleted locally: the remaining side
        with self.assertRaises(RuntimeError):
            resolver.choose("x.json", b"{", b"{")


if __name__ == "__main__":
    unittest.main()
