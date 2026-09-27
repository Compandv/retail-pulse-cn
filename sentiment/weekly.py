"""Weekly long-form report aggregated from saved daily snapshots.

Design: docs/plans/longform-report-2026-09-27/spec.md section 4.6. Weekly topic
scores need enough days with a daily long-form report; the market part is
always built from whatever days exist, and missing days are listed.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

from .collectors import CN_TZ
from .longform import CONFIG, alert_of, shape_of, SHAPES, yi
from .market_watch import atomic_json, number, read_json
from .report import score
from .trading_calendar import UnsupportedCalendarYear, is_trading_day

VERSION = CONFIG["weeklyVersion"]
DIMS = [item["key"] for item in CONFIG["dimensions"]]


def week_id(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_days(week: str) -> list[date]:
    year, number_ = week.split("-W")
    monday = date.fromisocalendar(int(year), int(number_), 1)
    return [monday + timedelta(days=i) for i in range(7)]


def sessions(week: str) -> list[date]:
    result = []
    for day in week_days(week):
        try:
            if is_trading_day(day):
                result.append(day)
        except UnsupportedCalendarYear:
            continue
    return result


def is_week_end(day: date) -> bool:
    """True when `day` is the last session of its ISO week."""
    days = sessions(week_id(day))
    return bool(days) and days[-1] == day


def required_days(total: int) -> int:
    return min(total, max(3, math.ceil(0.6 * total)))


def mean(values, minimum=1):
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 1) if len(values) >= minimum else None


def aggregate_topics(dailies: list[dict], previous: dict | None) -> list[dict]:
    """Average each topic's daily totals and dimensions over the days it appeared."""
    pool: dict[str, dict] = {}
    for daily in dailies:
        for topic in daily.get("topics", []):
            entry = pool.setdefault(topic["id"], {"id": topic["id"], "name": topic["name"], "days": [], "totals": [], "dims": {k: [] for k in DIMS},
                                                  "changes": [], "limitUps": 0})
            entry["days"].append(daily["meta"]["tradeDate"])
            entry["totals"].append(topic.get("total"))
            entry["changes"].append(number(topic.get("changePct")))
            entry["limitUps"] += topic.get("limitUpCount") or 0
            for key in DIMS:
                entry["dims"][key].append(topic.get("dimensions", {}).get(key))
    before = {t["id"]: t for t in (previous or {}).get("topics", [])}
    topics = []
    for entry in pool.values():
        dims = {key: mean(values, minimum=2) for key, values in entry["dims"].items()}
        total = mean(entry["totals"], minimum=2)
        prev = before.get(entry["id"])
        topics.append({"id": entry["id"], "name": entry["name"], "days": entry["days"], "appearances": len(entry["days"]),
                       "scoredDays": sum(v is not None for v in entry["totals"]), "total": total, "dimensions": dims,
                       "missing": [item["label"] for item in CONFIG["dimensions"] if dims[item["key"]] is None],
                       "limitUps": entry["limitUps"], "meanChange": mean(entry["changes"]),
                       "totalChange": round(total - prev["total"], 1) if prev and prev.get("total") is not None and total is not None else None,
                       "isNew": prev is None and previous is not None and bool(previous.get("topics")),
                       "shape": {"key": (key := shape_of(dims, prev and prev.get("dimensions"))), **SHAPES[key]},
                       "alert": alert_of(dims)})
    topics.sort(key=lambda t: (t["total"] is None, -(t["total"] or 0), -t["appearances"], t["name"]))
    return topics[:9]


def sum_flows(reports: list[dict], total_days: int, n=5) -> dict:
    """Weekly main-force net per board: sum of the days each board was reported."""
    boards: dict[str, dict] = {}
    for report in reports:
        for row in report.get("flows", {}).get("rows", []):
            if number(row.get("net")) is None:
                continue
            entry = boards.setdefault(row["boardId"], {"boardId": row["boardId"], "name": row["name"], "kind": row["kind"], "net": 0.0, "days": 0})
            entry["net"] += row["net"]
            entry["days"] += 1
    out = {"days": len(reports), "totalDays": total_days}
    for kind in ("industry", "concept"):
        subset = [b for b in boards.values() if b["kind"] == kind]
        out[kind] = {"inflow": sorted([b for b in subset if b["net"] > 0], key=lambda b: -b["net"])[:n],
                     "outflow": sorted([b for b in subset if b["net"] < 0], key=lambda b: b["net"])[:n]}
    return out


def index_week(indices: dict, days: list[str]) -> list[dict]:
    """Close of the week's last session vs the last close before the week."""
    rows = []
    for symbol, item in indices.items():
        closes = item["closes"]
        inside = [d for d in days if d in closes]
        before = [d for d in closes if d < days[0]] if days else []
        if not inside or not before:
            rows.append({"symbol": symbol, "name": item["name"], "close": None, "changePct": None, "high": None})
            continue
        base, end = closes[max(before)], closes[inside[-1]]
        rows.append({"symbol": symbol, "name": item["name"], "close": end, "changePct": round(100 * (end / base - 1), 2),
                     "high": max(closes[d] for d in inside), "baseDate": max(before)})
    return rows


def timeline(root: Path, days: list[date], indices: dict) -> list[dict]:
    rows = []
    for day in days:
        key = day.isoformat()
        daily = read_json(root / "public/data/longform/daily" / f"{key}.json", None)
        market = read_json(root / "public/data/market/daily" / f"{key}.json", {}).get("market")
        limit = read_json(root / "public/data/limit/daily" / f"{key}.json", None)
        sh = indices.get("sh000001", {}).get("closes", {})
        prior = [d for d in sh if d < key]
        rows.append({"date": key, "weekday": "一二三四五六日"[day.weekday()],
                     "hasLongform": daily is not None, "hasMarket": market is not None, "hasLimit": limit is not None,
                     "upRate": market.get("upRate") if market else None, "amount": market.get("amount") if market and market.get("amountComplete") else None,
                     "up": market.get("up") if market else None, "down": market.get("down") if market else None,
                     "limitUp": (limit or {}).get("metrics", {}).get("limitUp"), "limitDown": (limit or {}).get("metrics", {}).get("limitDown"),
                     "brokenRate": (limit or {}).get("metrics", {}).get("brokenRate"), "maxBoards": (limit or {}).get("metrics", {}).get("maxBoards"),
                     "mainline": (daily or {}).get("mainline"),
                     "shClose": sh.get(key), "shChange": round(100 * (sh[key] / sh[max(prior)] - 1), 2) if key in sh and prior else None,
                     "topTopic": next(({"name": t["name"], "total": t["total"]} for t in (daily or {}).get("topics", []) if t.get("total") is not None), None)})
    return rows


def market_summary(rows: list[dict], index_rows: list[dict]) -> dict:
    lines = [r["mainline"]["name"] for r in rows if r.get("mainline")]
    switches = sum(a != b for a, b in zip(lines, lines[1:]))
    amounts = [r["amount"] for r in rows if r["amount"] is not None]
    sh = next((r for r in index_rows if r["symbol"] == "sh000001"), {})
    return {"meanAmount": statistics.fmean(amounts) if amounts else None, "amountDays": len(amounts),
            "upRates": [r["upRate"] for r in rows], "minUpRate": min((r["upRate"] for r in rows if r["upRate"] is not None), default=None),
            "meanLimitUp": mean([r["limitUp"] for r in rows]), "maxBoards": max((r["maxBoards"] for r in rows if r["maxBoards"] is not None), default=None),
            "mainlines": lines, "mainlineSwitches": switches if len(lines) >= 2 else None, "shChange": sh.get("changePct")}


def recap(current: dict, previous: dict | None) -> list[dict]:
    """Last week's value next to this week's; facts only, no verdicts."""
    if not previous:
        return []
    pairs = [("日均成交额", "meanAmount", yi), ("最低红盘率", "minUpRate", lambda v: f"{v}%"), ("日均涨停家数", "meanLimitUp", lambda v: f"{v}"),
             ("最高连板", "maxBoards", lambda v: f"{v} 板"), ("主线切换次数", "mainlineSwitches", lambda v: f"{v} 次"), ("上证指数周涨跌", "shChange", lambda v: f"{v:+.2f}%")]
    rows = []
    for label, key, fmt in pairs:
        a, b = previous["market"].get(key), current["market"].get(key)
        rows.append({"label": label, "previous": fmt(a) if a is not None else "—", "current": fmt(b) if b is not None else "—"})
    return rows


def template_text(week: dict) -> dict:
    market, days = week["market"], week["meta"]["sessions"]
    first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    parts = [f"本周 {len(days)} 个交易日"]
    if market["mainlineSwitches"] is not None:
        parts.append(f"主线切换 {market['mainlineSwitches']} 次（{'→'.join(market['mainlines'])}）")
    rates = [r for r in market["upRates"] if r is not None]
    if len(rates) >= 2:
        parts.append(f"红盘率 {rates[0]}% → {rates[-1]}%")
    if market["meanAmount"] is not None:
        parts.append(f"日均成交 {yi(market['meanAmount'])}")
    if market["shChange"] is not None:
        parts.append(f"上证指数周涨跌 {market['shChange']:+.2f}%")
    title = f"{first.month}月{first.day}日—{last.month}月{last.day}日周报：" + ("，".join(parts[1:3]) or f"{len(days)} 个交易日")
    conclusions = []
    scored = [t for t in week["topics"] if t["total"] is not None]
    if scored:
        top = scored[0]
        conclusions.append(f"周分最高的题材是{top['name']}（{top['total']}，出现 {top['appearances']} 天，{top['shape']['label']}）。")
    if market["maxBoards"] is not None:
        conclusions.append(f"本周最高连板 {market['maxBoards']} 板，日均涨停 {market['meanLimitUp']} 家。")
    reds = [t["name"] for t in week["topics"] if t["alert"]["level"] == "red"]
    if reds:
        conclusions.append(f"拥挤提示为红灯的题材：{'、'.join(reds)}（换手与恐慌表达同处本表高位）。")
    missing = week["meta"]["missingDays"]
    if missing:
        conclusions.append(f"缺少 {len(missing)} 个交易日的长图数据（{'、'.join(d[5:] for d in missing)}），周分只基于已有日期。")
    return {"source": "template", "title": title, "oneLiner": "；".join(parts) + "。", "conclusions": conclusions,
            "summary": "本周报由每日快照汇总生成，数字均可在各日长图中核对；题材分数为十强题材之间的相对分位平均，不是买卖信号。"}


def build_weekly(root, week: str, indices=None, previous: dict | None = None, with_recap: bool = True) -> dict:
    from .longform_sources import fetch_index_closes
    root = Path(root)
    days = sessions(week)
    if not days:
        raise RuntimeError(f"{week} 没有交易日")
    keys = [d.isoformat() for d in days]
    dailies = [d for d in (read_json(root / "public/data/longform/daily" / f"{k}.json", None) for k in keys) if d]
    reports = [r for r in (read_json(root / "public/data/report/daily" / f"{k}.json", None) for k in keys) if r]
    indices = fetch_index_closes() if indices is None else indices
    if previous is None and with_recap:
        prior_week = week_id(days[0] - timedelta(days=7))
        previous = read_json(root / "public/data/weekly" / f"{prior_week}.json", None)
        if previous is None and sessions(prior_week):
            try:
                previous = build_weekly(root, prior_week, indices, with_recap=False)
            except Exception:
                previous = None
    need = required_days(len(days))
    rows = timeline(root, days, indices)
    index_rows = index_week(indices, keys)
    result = {
        "meta": {"version": VERSION, "dimensionsVersion": CONFIG["dimensionsVersion"], "week": week, "sessions": keys,
                 "startDate": keys[0], "endDate": keys[-1], "builtAt": datetime.now(CN_TZ).isoformat(timespec="seconds"),
                 "longformDays": [d["meta"]["tradeDate"] for d in dailies], "missingDays": [k for k in keys if k not in {d["meta"]["tradeDate"] for d in dailies}],
                 "requiredDays": need, "complete": len(dailies) == len(days), "topicsPublished": len(dailies) >= need,
                 "notes": ["周题材分 = 该题材在出现各天的日总分平均，至少有 2 天总分才出；各维度同理。",
                           f"已有长图的交易日达到 {need} 天才发布周题材排名；否则只展示市场部分。",
                           "题材每天由行情重新选出，成分表也可能变化，周分是不同日期成分表的平均。",
                           "资金为新浪主力口径各日净额相加，只加有数据的日期；行业分类与申万不同。"]},
        "timeline": rows,
        "indices": index_rows,
        "topics": aggregate_topics(dailies, previous) if len(dailies) >= need else [],
        "flows": sum_flows(reports, len(days)),
    }
    result["market"] = market_summary(rows, index_rows)
    result["recap"] = recap(result, previous) if with_recap else []
    result["previousWeek"] = previous["meta"]["week"] if previous else None
    result["narrative"] = template_text(result)
    return result


def save_weekly(root, week_report: dict) -> dict:
    root = Path(root)
    directory = root / "public/data/weekly"
    atomic_json(directory / f"{week_report['meta']['week']}.json", week_report)
    weeks = sorted(p.stem for p in directory.glob("????-W??.json"))
    atomic_json(root / "public/data/weekly/index.json", {"version": VERSION, "weeks": weeks})
    atomic_json(root / "public/data/weekly/latest.json", read_json(directory / f"{weeks[-1]}.json", week_report))
    return week_report
