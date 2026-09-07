"""Update rotating sector and market facts, independently of community collection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.market_watch import build_market_snapshot, read_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="Replay a saved market capture, keeping its original collection time")
    args = parser.parse_args()
    try:
        snapshot = build_market_snapshot(ROOT, capture=read_json(args.capture, {}) if args.capture else None)
    except Exception as exc:
        print(f"市场更新失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"交易日": snapshot["meta"]["tradeDate"], "状态": snapshot["meta"]["status"], "来源": snapshot["meta"]["sources"], "板块": len(snapshot["boards"]), "行情股票": snapshot["market"]["quoted"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
