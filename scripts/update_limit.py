"""Collect or replay the daily limit-up ecosystem; supports backfilling a date range.

The provider keeps only about 15 recent sessions, so backfill promptly.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.limit_pool import build_limit_snapshot, save  # noqa: E402
from sentiment.market_watch import read_json  # noqa: E402
from sentiment.trading_calendar import is_trading_day  # noqa: E402


def sessions(start: date, end: date):
    day = start
    while day <= end:
        if is_trading_day(day):
            yield day
        day += timedelta(days=1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="单个交易日，默认最近已收盘交易日")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, help="回补起始日（含）")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="回补结束日（含），默认最近已收盘交易日")
    parser.add_argument("--capture", type=Path, help="离线回放已保存的原始记录，不联网")
    args = parser.parse_args(argv)
    if args.capture:
        summary = save(ROOT, read_json(args.capture, {}))
        print(f"{summary['date']}：已回放，涨停 {summary['metrics']['limitUp']} 家")
        return 0
    if args.start:
        from datetime import datetime
        from sentiment.collectors import CN_TZ
        from sentiment.trading_calendar import effective_trade_date
        end = args.end or effective_trade_date(datetime.now(CN_TZ))
        days = list(sessions(args.start, end))
    else:
        days = [args.date] if args.date else [None]
    failures = 0
    for day in days:
        try:
            summary = build_limit_snapshot(ROOT, day=day)
            coverage = "、".join(kind for kind, item in summary["coverage"].items() if not item["complete"])
            m = summary["metrics"]
            print(f"{summary['date']}：涨停 {m['limitUp']}、跌停 {m['limitDown']}、炸板率 {m['brokenRate']}%、连板高度 {m['maxBoards']}"
                  + (f"；未取满：{coverage}" if coverage else ""), flush=True)
        except Exception as exc:
            failures += 1
            print(f"{day or '最近交易日'}：失败，{exc}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
