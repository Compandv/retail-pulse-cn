"""Build daily long-form reports from saved snapshots (and weekly reports when a week ends).

Only index closes and margin history are fetched; everything else is read locally.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.longform import build_daily, save_daily  # noqa: E402
from sentiment.longform_sources import fetch_index_closes, fetch_margin  # noqa: E402
from sentiment.trading_calendar import is_trading_day  # noqa: E402
from sentiment.weekly import build_weekly, save_weekly, week_id  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="单个交易日")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, help="重建起始日（含）")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="重建结束日（含）")
    parser.add_argument("--week", action="append", help="生成周报，如 2026-W39；可重复。与 --from/--to 同用时为范围内每一周")
    parser.add_argument("--weekly-only", action="store_true", help="只生成周报，不重建日报长图")
    args = parser.parse_args(argv)
    market_dir = ROOT / "public/data/market/daily"
    if args.start:
        end = args.end or date.today()
        days, probe = [], args.start
        while probe <= end:
            if is_trading_day(probe) and (market_dir / f"{probe}.json").exists():
                days.append(probe.isoformat())
            probe += timedelta(days=1)
    elif args.date:
        days = [args.date.isoformat()]
    else:
        days = [sorted(p.stem for p in market_dir.glob("????-??-??.json"))[-1]]
    indices, margin = fetch_index_closes(), fetch_margin()
    failures = 0
    weeks = list(args.week or [])
    if args.start and not weeks and args.weekly_only:
        weeks = sorted({week_id(date.fromisoformat(d)) for d in days} | {week_id(args.start)})
    if args.weekly_only:
        days = []
    for day in days:  # oldest first, so each day can compare with the previous one
        try:
            report = save_daily(ROOT, build_daily(ROOT, day, indices, margin))
            totals = sum(t["total"] is not None for t in report["topics"])
            print(f"{day}：已生成，{len(report['topics'])} 个题材（{totals} 个有总分）；{report['narrative']['title']}", flush=True)
        except Exception as exc:
            failures += 1
            print(f"{day}：失败，{exc}", flush=True)
    for week in weeks:
        try:
            result = save_weekly(ROOT, build_weekly(ROOT, week, indices))
            meta = result["meta"]
            print(f"{week}：周报已生成，{len(meta['sessions'])} 个交易日，长图 {len(meta['longformDays'])} 天，"
                  + ("题材排名已发布" if meta["topicsPublished"] else f"题材排名未发布（需 {meta['requiredDays']} 天）") + f"；{result['narrative']['title']}", flush=True)
        except Exception as exc:
            failures += 1
            print(f"{week}：周报失败，{exc}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
