"""Daily limit-up ecosystem from Eastmoney's public limit pools; see METHOD_LONGFORM.md.

Provider behaviour (checked 2026-09-27): `qdate` is the provider's latest
session, not the date of the rows; a non-trading date silently returns the
latest session; dates older than ~15 sessions return empty pools. So only
calendar sessions are requested, sessions after `qdate` are rejected, all-empty
pools are treated as out of range, and each day's "yesterday" pool is checked
against the previous day's limit-up pool when both are saved.
"""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime
from pathlib import Path

from .collectors import CN_TZ, request_text
from .market_watch import atomic_json, number, read_json

VERSION = "limit-ecosystem-1.0"
SOURCE = "东方财富涨停板行情（公开页面接口）"
ENDPOINT = "https://push2ex.eastmoney.com/{name}?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex={page}&pagesize={size}&sort={sort}&date={day}"
REFERER = "https://quote.eastmoney.com/ztb/"
PAGE_SIZE = 500
MAX_PAGES = 10
POOLS = {
    "limitUp": ("getTopicZTPool", "fbt:asc"),
    "broken": ("getTopicZBPool", "fbt:asc"),
    "limitDown": ("getTopicDTPool", "fund:asc"),
    "yesterday": ("getYesterdayZTPool", "zs:desc"),
}


def fetch_pool(kind: str, day: date, fetch=request_text) -> dict:
    """All pages of one pool; `complete` only when rows match the reported total."""
    name, sort = POOLS[kind]
    result = {"kind": kind, "expected": None, "rows": [], "complete": False, "error": None}
    try:
        for page in range(MAX_PAGES):
            url = ENDPOINT.format(name=name, page=page, size=PAGE_SIZE, sort=sort, day=day.strftime("%Y%m%d"))
            payload = json.loads(fetch(url, REFERER, timeout=15, attempts=2))
            data = payload.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("接口没有返回数据")
            if str(data.get("qdate", "")) < day.strftime("%Y%m%d"):
                raise RuntimeError(f"接口最新交易日为 {data.get('qdate')}，尚无所请求日期的数据")
            total, rows = data.get("tc"), data.get("pool")
            if not isinstance(total, int) or not isinstance(rows, list):
                raise RuntimeError("接口结构异常")
            result["expected"] = total
            result["rows"].extend(row for row in rows if isinstance(row, dict))
            if len(rows) < PAGE_SIZE or len(result["rows"]) >= total:
                break
        codes = [row.get("c") for row in result["rows"]]
        result["complete"] = result["expected"] is not None and len(set(codes)) == len(codes) == result["expected"]
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def collect(day: date, fetch=request_text) -> dict:
    from .trading_calendar import is_trading_day
    if not is_trading_day(day):
        raise RuntimeError(f"{day} 不是交易日；接口会改为返回最近交易日的数据，因此不请求")
    pools = {kind: fetch_pool(kind, day, fetch) for kind in POOLS}
    if all(pools[kind].get("expected") == 0 for kind in ("limitUp", "broken", "limitDown")):
        # A real session always has some limit moves; all-empty means out of range.
        for pool in pools.values():
            pool.update(rows=[], complete=False, error="涨停、炸板、跌停池均为空，判定为超出接口保留期")
    return {"version": VERSION, "date": day.isoformat(), "collectedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"), "pools": pools}


def chain_check(summary: dict, previous: dict | None) -> dict | None:
    """Today's 'yesterday' pool should list the previous session's limit-up stocks.

    A mismatch means the provider returned another day's rows for this date.
    """
    if not previous or not summary.get("coverage", {}).get("yesterday", {}).get("complete") \
            or not previous.get("coverage", {}).get("limitUp", {}).get("complete"):
        return None
    expected = {row["code"] for row in previous.get("limitUp", [])}
    found = {row["code"] for row in summary.get("yesterday", [])}
    matched = len(expected & found)
    ratio = round(100 * matched / len(expected), 1) if expected else None
    return {"previousDate": previous["date"], "expected": len(expected), "found": len(found), "matched": matched,
            "matchRate": ratio, "passed": ratio is not None and ratio >= 90}


def _seal_time(value):
    """Provider times are integers like 93136 -> '09:31:36'."""
    value = number(value)
    if value is None:
        return None
    text = f"{int(value):06d}"
    return f"{text[:2]}:{text[2:4]}:{text[4:]}"


def _streak(row):
    stats = row.get("zttj") if isinstance(row.get("zttj"), dict) else {}
    days, count = number(stats.get("days")), number(stats.get("ct"))
    return f"{int(days)}天{int(count)}板" if days and count else None


def _public(kind, row):
    base = {"code": str(row.get("c", "")), "name": str(row.get("n", "")), "changePct": _round(number(row.get("zdp"))),
            "industry": row.get("hybk") or None}
    if kind == "limitUp":
        base.update(boards=_int(row.get("lbc")), streak=_streak(row), breaks=_int(row.get("zbc")), firstSeal=_seal_time(row.get("fbt")),
                    lastSeal=_seal_time(row.get("lbt")), amount=number(row.get("amount")), turnover=_round(number(row.get("hs"))))
    elif kind == "broken":
        base.update(breaks=_int(row.get("zbc")), streak=_streak(row))
    elif kind == "limitDown":
        base.update(days=_int(row.get("days")))
    elif kind == "yesterday":
        base.update(yesterdayBoards=_int(row.get("ylbc")))
    return base


def _round(value, digits=2):
    return round(value, digits) if value is not None else None


def _int(value):
    value = number(value)
    return int(value) if value is not None else None


def metrics(pools: dict) -> dict:
    """Descriptive statistics only; derived values need complete pools."""
    up, broken, down, yesterday = (pools.get(kind, {}) for kind in POOLS)
    count = lambda pool: pool.get("expected") if not pool.get("error") else None  # noqa: E731
    ok = lambda *items: all(item.get("complete") for item in items)  # noqa: E731
    up_n, broken_n = count(up), count(broken)
    result = {"limitUp": up_n, "limitDown": count(down), "broken": broken_n, "yesterdayLimitUp": count(yesterday)}
    result["brokenRate"] = _round(100 * broken_n / (up_n + broken_n), 1) if up_n is not None and broken_n is not None and up_n + broken_n else None

    boards = [_int(row.get("lbc")) for row in up.get("rows", [])]
    boards = [value for value in boards if value]
    if ok(up) and boards:
        top = max(boards)
        result["maxBoards"] = top
        result["maxBoardStocks"] = [{"code": row.get("c"), "name": row.get("n")} for row in up["rows"] if _int(row.get("lbc")) == top]
        ladder = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
        for value in boards:
            ladder["5+" if value >= 5 else str(value)] += 1
        result["ladder"] = ladder
    else:
        result.update(maxBoards=None, maxBoardStocks=[], ladder=None)

    changes = [number(row.get("zdp")) for row in yesterday.get("rows", [])]
    changes = [value for value in changes if value is not None]
    if ok(yesterday) and changes:
        result["yesterdayMean"] = _round(statistics.fmean(changes))
        result["yesterdayMedian"] = _round(statistics.median(changes))
        streaks = [number(row.get("zdp")) for row in yesterday["rows"] if (_int(row.get("ylbc")) or 0) >= 2 and number(row.get("zdp")) is not None]
        result["yesterdayStreakMean"] = _round(statistics.fmean(streaks)) if len(streaks) >= 3 else None
        result["yesterdayStreakCount"] = len(streaks)
    else:
        result.update(yesterdayMean=None, yesterdayMedian=None, yesterdayStreakMean=None, yesterdayStreakCount=None)

    if ok(up, yesterday) and yesterday.get("rows"):
        today = {row.get("c") for row in up["rows"]}
        promoted = sum(row.get("c") in today for row in yesterday["rows"])
        result["promotionRate"] = _round(100 * promoted / len(yesterday["rows"]), 1)
        result["promoted"] = promoted
    else:
        result.update(promotionRate=None, promoted=None)
    return result


def summarize(capture: dict) -> dict:
    """Public snapshot: counts, derived metrics and trimmed stock rows."""
    pools = capture["pools"]
    return {"meta": {"version": VERSION, "tradeDate": capture["date"], "collectedAt": capture["collectedAt"]},
            "version": VERSION, "date": capture["date"], "collectedAt": capture["collectedAt"], "source": SOURCE,
            "coverage": {kind: {"expected": pool.get("expected"), "observed": len(pool.get("rows", [])), "complete": bool(pool.get("complete")),
                                "error": pool.get("error")} for kind, pool in pools.items()},
            "metrics": metrics(pools),
            **{kind: [_public(kind, row) for row in pool.get("rows", [])] for kind, pool in pools.items()}}


def save(root: Path, capture: dict) -> dict:
    """Write the private capture and public snapshot; never replace a better saved day."""
    root = Path(root)
    day = capture["date"]
    summary = summarize(capture)
    daily = root / "public/data/limit/daily"
    target = daily / f"{day}.json"
    previous = read_json(target, None)
    if previous and _completeness(previous) > _completeness(summary):
        raise RuntimeError(f"{day} 已保存更完整的涨停数据，本次结果不覆盖")
    from .trading_calendar import previous_trading_day
    before = read_json(daily / f"{previous_trading_day(date.fromisoformat(day)).isoformat()}.json", None)
    summary["chainCheck"] = chain_check(summary, before)
    if summary["chainCheck"] and not summary["chainCheck"]["passed"]:
        raise RuntimeError(f"{day} 的昨日涨停池与 {before['date']} 涨停池只对上 {summary['chainCheck']['matchRate']}%，疑似接口返回了其他日期，不保存")
    atomic_json(root / "work/limit-observations" / f"{day}.json", capture)
    atomic_json(target, summary)
    following = _next_session(day)
    after = read_json(daily / f"{following}.json", None) if following else None
    if after:  # backfilling out of order: re-check the following saved day
        after["chainCheck"] = chain_check(after, summary)
        atomic_json(daily / f"{after['date']}.json", after)
    dates = sorted(path.stem for path in daily.glob("????-??-??.json"))
    atomic_json(root / "public/data/limit/index.json", {"version": VERSION, "dates": dates})
    latest = read_json(daily / f"{dates[-1]}.json", summary)
    atomic_json(root / "public/data/limit/latest.json", latest)
    return summary


def _next_session(day: str) -> str | None:
    from datetime import timedelta
    from .trading_calendar import UnsupportedCalendarYear, is_trading_day
    probe = date.fromisoformat(day) + timedelta(days=1)
    try:
        while not is_trading_day(probe):
            probe += timedelta(days=1)
    except UnsupportedCalendarYear:
        return None
    return probe.isoformat()


def _completeness(summary):
    coverage = summary.get("coverage", {})
    return sum(bool(item.get("complete")) for item in coverage.values())


def build_limit_snapshot(root, now=None, day: date | None = None, fetch=request_text) -> dict:
    """Daily entry used by update_index; `day` defaults to the latest closed session."""
    from .trading_calendar import effective_trade_date
    day = day or effective_trade_date(now or datetime.now(CN_TZ))
    capture = collect(day, fetch)
    if not any(pool.get("complete") for pool in capture["pools"].values()):
        errors = "；".join(f"{kind}: {pool.get('error')}" for kind, pool in capture["pools"].items() if pool.get("error"))
        raise RuntimeError(f"{day} 涨停数据全部未取得：{errors}")
    return save(root, capture)
