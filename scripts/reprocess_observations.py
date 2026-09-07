"""Reproduce V4 output from a saved local capture without recollecting comments."""
from __future__ import annotations
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.collectors import CN_TZ  # noqa: E402
from sentiment.pipeline import _load_json, _save_json  # noqa: E402
from sentiment.pipeline_v4 import assemble_snapshot, scopes_for, persist_snapshot  # noqa: E402
from sentiment.observations import collect_trading  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--refresh-trading", action="store_true")
    args = parser.parse_args()
    batch = _load_json(args.capture, {})
    if not batch.get("date") or not batch.get("feeds"):
        raise RuntimeError("不是有效的本地 V4 采集记录")
    if args.refresh_trading:
        codes = list(batch["feeds"])
        with ThreadPoolExecutor(max_workers=6) as pool:
            batch["trading"] = dict(zip(codes, pool.map(lambda code: collect_trading(code, batch["date"]), codes)))
        _save_json(args.capture, batch)
    snapshot = assemble_snapshot(ROOT, batch, scopes_for(ROOT), datetime.now(CN_TZ))
    persist_snapshot(ROOT, snapshot)
    print(f"已按 {snapshot['meta']['methodVersion']} 重算 {batch['date']}，原始采集时刻保持 {batch['collectedAt']}")


if __name__ == "__main__":
    main()
