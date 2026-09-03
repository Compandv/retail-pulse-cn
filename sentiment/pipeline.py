from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analyzer import PANIC, evidence_counts, analyze_post
from .collectors import CN_TZ, COLLECTORS, EastMoneyCollector
from .market_data import fetch_market_data
from .models import AnalyzedPost, CollectionOutcome

SOURCE_NAMES = {"eastmoney": "东方财富股吧", "sina": "新浪股吧", "taoguba": "淘股吧"}
EXPECTED_SOURCES = tuple(SOURCE_NAMES)
HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 1, 2),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 23),
    date(2026, 4, 6), date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5), date(2026, 6, 19), date(2026, 9, 25),
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day not in HOLIDAYS_2026


def previous_trading_day(day: date) -> date:
    candidate = day - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def next_trading_day(day: date) -> date:
    candidate = day
    while not is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def effective_trade_date(now: datetime) -> date:
    local = now.astimezone(CN_TZ)
    if is_trading_day(local.date()) and local.time() >= clock_time(15, 30):
        return local.date()
    probe = local.date() - timedelta(days=1)
    while not is_trading_day(probe):
        probe -= timedelta(days=1)
    return probe


def recent_trading_days(end: date, count: int = 3) -> set[date]:
    days = {end}
    probe = end
    while len(days) < count:
        probe = previous_trading_day(probe)
        days.add(probe)
    return days


def trading_day_offset(end: date, offset: int) -> date:
    probe = end
    for _ in range(max(0, offset)):
        probe = previous_trading_day(probe)
    return probe


def session_date(published_at: datetime) -> date:
    return next_trading_day(published_at.astimezone(CN_TZ).date())


def _round(value: float) -> float:
    return round(float(value), 1)


def _source_metrics(posts: list[AnalyzedPost]) -> dict[str, float]:
    if not posts:
        # Missing sentiment keeps a neutral seat, but missing activity must not
        # pretend to be medium heat.
        return {"overall": 50.0, "direction": 0.0, "novice": 50.0, "fomo": 50.0, "panic": 50.0, "heat": 0.0}
    count = len(posts)
    novice = min(100.0, statistics.fmean(item.signals.novice for item in posts) * 145)
    fomo = min(100.0, statistics.fmean(item.signals.fomo for item in posts) * 155)
    panic = min(100.0, statistics.fmean(item.signals.panic for item in posts) * 155)
    direction = statistics.fmean(item.signals.direction for item in posts) * 100
    heat = min(100.0, math.log1p(count) / math.log1p(80) * 100)
    raw_overall = 20 + 0.30 * heat + 0.20 * fomo + 0.15 * novice + 0.10 * panic + 0.10 * abs(direction)
    reliability = count / (count + 15)
    overall = 50 + (raw_overall - 50) * reliability
    return {
        "overall": _round(max(0, min(100, overall))),
        "direction": _round(max(-100, min(100, direction * reliability))),
        "novice": _round(novice), "fomo": _round(fomo), "panic": _round(panic), "heat": _round(heat),
    }


PARTICIPANT_LABELS = {
    "newcomer": "新手求助",
    "chaser": "追涨短线",
    "trapped": "套牢恐慌",
    "bull": "看多跟随",
    "bear": "看空防守",
    "observer": "观望讨论",
}


def _participant_mix(posts: list[AnalyzedPost]) -> list[dict[str, Any]]:
    """Classify expression styles, never infer a user's real identity."""
    counts: Counter[str] = Counter()
    for item in posts:
        signals = item.signals
        emotion_scores = {"newcomer": signals.novice, "chaser": signals.fomo, "trapped": signals.panic}
        strongest = max(emotion_scores, key=emotion_scores.get)
        if emotion_scores[strongest] >= 0.28:
            category = strongest
        elif signals.direction >= 0.22:
            category = "bull"
        elif signals.direction <= -0.22:
            category = "bear"
        else:
            category = "observer"
        counts[category] += 1
    total = sum(counts.values()) or 1
    return [
        {"key": key, "label": PARTICIPANT_LABELS[key], "count": count, "share": _round(count / total * 100)}
        for key, count in counts.most_common()
    ]


def _profit_effect(metrics: Mapping[str, float], quote: Mapping[str, Any]) -> float:
    """Estimate the felt profit effect from price action plus community tone."""
    price_change = quote.get("priceChange")
    try:
        price_change = float(price_change) if price_change is not None else None
    except (TypeError, ValueError):
        price_change = None
    # A representative quote is deliberately capped; it is a useful visual
    # proxy, not a substitute for constituent-level breadth data.
    price_component = max(-20.0, min(20.0, (price_change or 0.0) * 3.5))
    sentiment_component = metrics["direction"] * 0.12 + (metrics["fomo"] - metrics["panic"]) * 0.2
    return _round(max(0.0, min(100.0, 50.0 + price_component + sentiment_component)))


def _market_breadth(sectors: list[Mapping[str, Any]], direction: float) -> dict[str, Any]:
    changes: list[float] = []
    for row in sectors:
        try:
            if row.get("priceChange") is not None:
                changes.append(float(row["priceChange"]))
        except (TypeError, ValueError):
            continue
    up = sum(value > 0.05 for value in changes)
    down = sum(value < -0.05 for value in changes)
    flat = len(changes) - up - down
    up_rate = up / len(changes) * 100 if changes else 0.0
    median_change = statistics.median(changes) if changes else 0.0
    average_change = statistics.fmean(changes) if changes else 0.0
    breadth_component = up_rate * 0.55
    return_component = max(0.0, min(100.0, 50.0 + median_change * 9.0)) * 0.35
    tone_component = max(0.0, min(100.0, 50.0 + direction * 0.7)) * 0.10
    score = max(0.0, min(100.0, breadth_component + return_component + tone_component))
    return {
        "profitEffect": _round(score),
        "breadthUp": up,
        "breadthDown": down,
        "breadthFlat": flat,
        "breadthTotal": len(changes),
        "breadthUpRate": _round(up_rate),
        "breadthMedianChange": _round(median_change),
        "breadthAverageChange": _round(average_change),
    }


def _trend_label(delta: float) -> str:
    if delta >= 8:
        return "快速升温"
    if delta >= 2:
        return "升温"
    if delta <= -8:
        return "快速降温"
    if delta <= -2:
        return "降温"
    return "平稳"


def _participant_indices(metrics: Mapping[str, float]) -> dict[str, float | str]:
    """Expose buy/sell sub-indices in the same 0-100 language as mom-index."""
    buy = max(0.0, min(100.0, 45.0 + metrics["direction"] * 0.22 + metrics["fomo"] * 0.48 - metrics["panic"] * 0.16))
    sell = max(0.0, min(100.0, 45.0 - metrics["direction"] * 0.22 + metrics["panic"] * 0.48 - metrics["fomo"] * 0.16))
    ratio = buy / sell if sell > 0.5 else (99.0 if buy > 0.5 else 1.0)
    return {
        "buyIndex": _round(buy),
        "sellIndex": _round(sell),
        "buySellRatio": _round(min(99.0, ratio)),
    }


def _safe_excerpt(text: str, max_chars: int = 92) -> str:
    clean = " ".join(str(text or "").split()).replace("\u0000", "")
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _comment_rows(analyzed: list[AnalyzedPost], trade_date: date, target_names: Mapping[str, str], limit: int = 14) -> list[dict[str, Any]]:
    current = [item for item in analyzed if session_date(item.post.published_at) == trade_date]

    def score(item: AnalyzedPost) -> float:
        s = item.signals
        return s.novice * 1.4 + s.fomo * 1.2 + s.panic * 1.2 + abs(s.direction) * 0.6

    rows: list[dict[str, Any]] = []
    for item in sorted(current, key=score, reverse=True)[:limit]:
        signals = item.signals
        if signals.panic >= max(signals.fomo, signals.novice) and signals.panic > 0.22:
            tone, intent = "panic", "恐慌/离场"
        elif signals.fomo >= max(signals.panic, signals.novice) and signals.fomo > 0.22:
            tone, intent = "fomo", "追涨/买入"
        elif signals.novice > 0.22:
            tone, intent = "novice", "求助/跟随"
        elif signals.direction >= 0.18:
            tone, intent = "bull", "看多"
        elif signals.direction <= -0.18:
            tone, intent = "bear", "看空"
        else:
            tone, intent = "neutral", "观望"
        rows.append({
            "id": f"{item.post.source}-{item.post.target_id}-{item.post.published_at.isoformat()}",
            "date": item.post.published_at.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M"),
            "source": SOURCE_NAMES.get(item.post.source, item.post.source),
            "sectorId": item.post.target_id,
            "sectorName": target_names.get(item.post.target_id, item.post.target_name),
            "excerpt": _safe_excerpt(item.post.text),
            "tone": tone,
            "intent": intent,
            "signals": list(signals.matched[:5]),
        })
    return rows


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    # Three observations can manufacture a visually convincing ±1.0. Require
    # a slightly longer common window before exposing a relationship.
    if len(xs) < 5 or len(xs) != len(ys):
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (denom_x * denom_y)))


def _correlation_payload(sector_history: list[Mapping[str, Any]], sectors: list[Mapping[str, Any]], days: int = 30) -> dict[str, Any]:
    recent = sorted((row for row in sector_history if isinstance(row, Mapping)), key=lambda row: str(row.get("date", "")))[-days:]
    labels = [{"id": str(row.get("id")), "name": str(row.get("name")), "group": str(row.get("group", "其他"))} for row in sectors]
    values: dict[str, list[float | None]] = {item["id"]: [] for item in labels}
    for snapshot in recent:
        by_id = {str(row.get("id")): row for row in (snapshot.get("sectors") or []) if isinstance(row, Mapping)}
        for item in labels:
            row = by_id.get(item["id"])
            try:
                values[item["id"]].append(float(row.get("heat")) if row is not None else None)
            except (TypeError, ValueError):
                values[item["id"]].append(None)
    matrix: list[list[float | None]] = []
    for left in labels:
        matrix_row: list[float | None] = []
        for right in labels:
            pairs = [(x, y) for x, y in zip(values[left["id"]], values[right["id"]]) if x is not None and y is not None]
            correlation = _pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
            matrix_row.append(_round(correlation) if correlation is not None else None)
        matrix.append(matrix_row)
    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(labels):
        for j in range(i + 1, len(labels)):
            right = labels[j]
            value = matrix[i][j]
            if value is None:
                continue
            strength = "strong" if abs(value) >= 0.7 else "medium" if abs(value) >= 0.4 else "weak"
            if strength != "weak":
                pairs.append({"left": left["name"], "right": right["name"], "r": value, "strength": strength})
    pairs.sort(key=lambda row: abs(float(row["r"])), reverse=True)
    return {
        "days": len(recent),
        "minimumDays": 5,
        "sufficient": len(recent) >= 5,
        "sectors": labels,
        "matrix": matrix,
        "pairs": pairs[:18],
    }


def _calendar_payload(history: list[Mapping[str, Any]], days: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for point in sorted((row for row in history if isinstance(row, Mapping)), key=lambda row: str(row.get("date", "")))[-days:]:
        try:
            overall = float(point.get("overall", 50))
            heat = float(point.get("heat", 0))
            raw_sample_count = point.get("sampleCount")
            sample_count = int(raw_sample_count) if raw_sample_count is not None else None
        except (TypeError, ValueError):
            continue
        if overall >= 70:
            bucket = "hot"
        elif overall >= 55:
            bucket = "warm"
        elif overall >= 42:
            bucket = "cool"
        else:
            bucket = "cold"
        rows.append({"date": str(point.get("date")), "overall": _round(overall), "heat": _round(heat), "sampleCount": sample_count, "bucket": bucket, "recordType": point.get("recordType", "measured")})
    return rows


def _interpretation_payload(summary: Mapping[str, float], sectors: list[Mapping[str, Any]], trade_date: date) -> dict[str, str]:
    hottest = sorted(sectors, key=lambda row: float(row.get("heat", 0)), reverse=True)[:3]
    rising = [row for row in sorted(sectors, key=lambda row: float(row.get("heatChange", 0)), reverse=True) if row.get("heatChangeAvailable")][:3]
    top_names = "、".join(str(row.get("name")) for row in hottest) or "暂无"
    rising_names = "、".join(str(row.get("name")) for row in rising) or "基线积累中"
    profit_values = [float(row["profitEffect"]) for row in sectors if row.get("profitEffect") is not None]
    flow_values = [float(row["flowNet"]) for row in sectors if row.get("flowNet") is not None]
    profit = statistics.fmean(profit_values) if profit_values else None
    flow = sum(flow_values) if flow_values else None
    profit_text = f"{profit:.1f}" if profit is not None else "—"
    flow_text = f"{flow:+.2f}亿" if flow is not None else "—"
    if summary["panic"] > summary["fomo"] + 12:
        tone = "恐慌盘明显占上风，嘴上都说要跑，真正能不能跑还要看成交和资金。"
    elif summary["fomo"] > summary["panic"] + 12:
        tone = "追涨表达比恐慌更抢戏，市场不一定马上反转，但接力情绪已经开始冒烟。"
    else:
        tone = "多空没有形成压倒性共识，热闹归热闹，方向还没有被散户投票决定。"
    interpretation = (
        f"{trade_date.isoformat()}：讨论热度 {summary['heat']:.1f}，当前最热是{top_names}，最近升温靠前的是{rising_names}。"
        f"代表主题赚钱效应约 {profit_text}，可见主题净流入合计 {flow_text}。{tone}"
    )
    contradiction = "热度和赚钱效应同向" if profit is not None and profit >= 55 else "热度未被赚钱效应完全确认"
    tongue = (
        f"毒舌结论：今天的散户不是完全没钱，而是把钱分成了两拨——一拨在追热点，一拨在研究怎么体面地解套。"
        f"现在{contradiction}（热度 {summary['heat']:.1f} / 赚钱效应 {profit_text} / 净流入 {flow_text}），别把评论区的音量当成账户收益。"
    )
    return {"interpretation": interpretation, "tongue": tongue}


def _merge_sector_history(rows: Iterable[Mapping[str, Any]], points: Iterable[Mapping[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for raw in list(rows) + list(points):
        if not isinstance(raw, Mapping):
            continue
        day = str(raw.get("date", "")).strip()
        if day:
            by_date[day] = dict(raw)
    return [by_date[day] for day in sorted(by_date)][-max(1, limit):]


def _sector_metric_series(history: list[Mapping[str, Any]], sector_id: str, metric: str, end: date) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for snapshot in sorted(history, key=lambda row: str(row.get("date", ""))):
        snapshot_day = str(snapshot.get("date", ""))
        if not snapshot_day or snapshot_day > end.isoformat():
            continue
        rows = snapshot.get("sectors") if isinstance(snapshot, Mapping) else None
        if not isinstance(rows, list):
            continue
        row = next((item for item in rows if isinstance(item, Mapping) and str(item.get("id")) == sector_id), None)
        if row is None:
            continue
        try:
            values.append((snapshot_day, float(row[metric])))
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _daily_sector_history(analyzed: list[AnalyzedPost], targets: list[Mapping[str, Any]], trade_date: date) -> list[dict[str, Any]]:
    """Build observed daily sector activity from the collected three-session window."""
    allowed_days = sorted(recent_trading_days(trade_date, 3))
    points: list[dict[str, Any]] = []
    for day in allowed_days:
        sector_rows: list[dict[str, Any]] = []
        for target in targets:
            target_id = str(target.get("id"))
            if target_id == "market":
                continue
            posts = [item for item in analyzed if item.post.target_id == target_id and session_date(item.post.published_at) == day]
            if not posts:
                continue
            metrics = aggregate_group(posts)
            sector_rows.append({
                "id": target_id,
                "overall": metrics["overall"],
                "heat": metrics["heat"],
                "sampleCount": len(posts),
            })
        if sector_rows:
            points.append({"date": day.isoformat(), "sectors": sector_rows})
    return points


def aggregate_group(posts: Iterable[AnalyzedPost], expected_sources: Iterable[str] = EXPECTED_SOURCES) -> dict[str, float]:
    grouped: dict[str, list[AnalyzedPost]] = defaultdict(list)
    for item in posts:
        grouped[item.post.source].append(item)
    source_metrics = {source: _source_metrics(grouped.get(source, [])) for source in expected_sources}
    return {metric: _round(statistics.fmean(values[metric] for values in source_metrics.values())) for metric in ("overall", "direction", "novice", "fomo", "panic", "heat")}


def confidence_label(coverage: float, sample_count: int) -> str:
    if coverage >= 0.99 and sample_count >= 240:
        return "A"
    if coverage >= 0.66 and sample_count >= 100:
        return "B"
    if coverage >= 0.33 and sample_count >= 30:
        return "C"
    return "D"


def temperature_label(score: float) -> str:
    if score >= 80: return "极度亢奋"
    if score >= 65: return "明显升温"
    if score >= 45: return "情绪平稳"
    if score >= 30: return "明显降温"
    return "极度冷清"


def readout(metrics: Mapping[str, float]) -> str:
    if metrics["panic"] >= 65:
        return "恐慌与离场表达显著增加，需结合方向和覆盖率判断。"
    if metrics["fomo"] >= 65 and metrics["novice"] >= 55:
        return "追涨表达和新手提问同步增加，但高热本身不是卖出信号。"
    if metrics["fomo"] >= 60:
        return "错失焦虑和追涨表达升温，社区情绪较为躁动。"
    if abs(metrics["direction"]) < 10:
        return "多空表达接近平衡，暂未出现明确一致方向。"
    return "社区方向出现偏移，建议结合分项指标和来源覆盖继续观察。"


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _load_persisted_daily_snapshots(root: Path, limit: int = 60) -> list[dict[str, Any]]:
    """Load daily snapshots written by prior runs.

    The latest snapshot is intentionally not the only source of history: a
    daily file is the durable observation for that session, so rebuilding from
    all files lets a fresh run recover 20/60-day curves after a restart.
    Invalid or partially-written files are skipped safely.
    """
    daily_dir = root / "public" / "data" / "daily"
    snapshots: list[dict[str, Any]] = []
    try:
        paths = sorted(daily_dir.glob("*.json"))
    except OSError:
        return snapshots
    for path in paths:
        payload = _load_json(path, {})
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta")
        trade_date = meta.get("tradeDate") if isinstance(meta, dict) else None
        if not trade_date:
            trade_date = path.stem
        if isinstance(trade_date, str) and trade_date:
            snapshots.append(payload)
    snapshots.sort(key=lambda item: str((item.get("meta") or {}).get("tradeDate") or ""))
    return snapshots[-max(1, limit):]


def _load_persisted_market_history(snapshots: Iterable[Mapping[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for snapshot in snapshots:
        history = snapshot.get("history") if isinstance(snapshot, Mapping) else None
        snapshot_day = str((snapshot.get("meta") or {}).get("tradeDate") or "")
        summary = snapshot.get("summary") if isinstance(snapshot, Mapping) else None
        snapshot_sample_count = summary.get("sampleCount") if isinstance(summary, Mapping) else None
        if isinstance(history, list) and history:
            for item in history:
                if not isinstance(item, Mapping):
                    continue
                row = dict(item)
                if row.get("date") == snapshot_day and row.get("sampleCount") is None and snapshot_sample_count is not None:
                    row["sampleCount"] = snapshot_sample_count
                rows.append(row)
        elif snapshot_day and isinstance(summary, Mapping) and summary.get("overall") is not None:
            # Be tolerant of compact daily files that contain only summary
            # metrics. They still represent a measured session.
            keys = ("overall", "direction", "novice", "fomo", "panic", "heat", "profitEffect")
            row = {"date": snapshot_day, "recordType": "measured"}
            row.update({key: summary[key] for key in keys if summary.get(key) is not None})
            if snapshot_sample_count is not None:
                row["sampleCount"] = snapshot_sample_count
            rows.append(row)
    return _merge_history_rows(rows, limit=limit)


def _load_persisted_sector_history(snapshots: Iterable[Mapping[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for snapshot in snapshots:
        history = snapshot.get("sectorHistory") if isinstance(snapshot, Mapping) else None
        if isinstance(history, list):
            rows.extend(item for item in history if isinstance(item, Mapping))
    return _merge_sector_history([], rows, limit=limit)


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _save_daily_files(root: Path, snapshot: Mapping[str, Any]) -> None:
    """Persist one immutable-by-date snapshot plus a lightweight date index."""
    day = str((snapshot.get("meta") or {}).get("tradeDate") or "")
    if not day:
        return
    daily_dir = root / "public" / "data" / "daily"
    _save_json(daily_dir / f"{day}.json", snapshot)
    index_path = root / "public" / "data" / "index.json"
    previous = _load_json(index_path, {})
    previous_dates = previous.get("dates") if isinstance(previous, dict) else []
    if not isinstance(previous_dates, list):
        previous_dates = []
    dates = {str(value) for value in previous_dates if isinstance(value, str)}
    dates.add(day)
    index = {
        "updatedAt": (snapshot.get("meta") or {}).get("generatedAt"),
        "latest": day,
        "methodVersion": (snapshot.get("meta") or {}).get("methodVersion"),
        "dates": sorted(dates)[-60:],
    }
    _save_json(index_path, index)


def _collect(targets: list[Mapping[str, Any]]) -> list[CollectionOutcome]:
    futures = {}
    outcomes: list[CollectionOutcome] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for collector in COLLECTORS:
            for target in targets:
                if collector.source == "taoguba" and target.get("taoguba") is False:
                    continue
                future = pool.submit(collector.collect, target)
                futures[future] = (collector.source, str(target["id"]))
        for future in as_completed(futures):
            source, target_id = futures[future]
            try:
                outcomes.append(future.result())
            except Exception as exc:
                outcomes.append(CollectionOutcome(source, target_id, False, error=str(exc)))
    return outcomes


def _prepare_posts(outcomes: list[CollectionOutcome], trade_date: date) -> tuple[list[AnalyzedPost], int, int]:
    allowed_days = recent_trading_days(trade_date, 3)
    dedup: set[tuple[str, str, str]] = set()
    author_counts: Counter[tuple[str, str, date]] = Counter()
    accepted: list[AnalyzedPost] = []
    filtered = 0
    unique_authors: set[str] = set()
    for outcome in outcomes:
        for post in outcome.posts:
            if session_date(post.published_at) not in allowed_days:
                filtered += 1
                continue
            normalized = "".join(post.text.lower().split())
            dedup_key = (post.source, post.target_id, normalized)
            author_key = (post.source, post.author_key, session_date(post.published_at))
            if dedup_key in dedup or author_counts[author_key] >= 3:
                filtered += 1
                continue
            dedup.add(dedup_key)
            author_counts[author_key] += 1
            analyzed = analyze_post(post)
            if analyzed is None:
                filtered += 1
                continue
            accepted.append(analyzed)
            unique_authors.add(f"{post.source}:{post.author_key}")
    return accepted, filtered, len(unique_authors)


def _source_rows(outcomes: list[CollectionOutcome], analyzed: list[AnalyzedPost], targets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sample_counts = Counter(item.post.source for item in analyzed)
    rows: list[dict[str, Any]] = []
    for source in EXPECTED_SOURCES:
        expected = sum(1 for target in targets if not (source == "taoguba" and target.get("taoguba") is False))
        source_outcomes = [outcome for outcome in outcomes if outcome.source == source]
        successes = sum(1 for outcome in source_outcomes if outcome.ok)
        failures = [outcome for outcome in source_outcomes if not outcome.ok]
        if successes == expected and sample_counts[source] > 0:
            status, note = "ok", "公开页面读取正常"
        elif successes > 0:
            status, note = "partial", f"{len(failures)} 个入口读取失败或近期无样本"
        else:
            status, note = "failed", (failures[0].error[:52] if failures else "本次没有可用样本")
        rows.append({"id": source, "name": SOURCE_NAMES[source], "status": status, "sampleCount": sample_counts[source], "note": note})
    return rows


def _top_signals(analyzed: list[AnalyzedPost]) -> list[dict[str, Any]]:
    counts = evidence_counts(analyzed)
    rows = counts.most_common(5) or [("暂无明显集中表达", 0)]
    return [{"label": phrase, "count": count, "tone": "cool" if phrase in PANIC else "hot" if count else "neutral"} for phrase, count in rows]


def _backfill_market_history(target: Mapping[str, Any], trade_date: date, points: int = 60) -> list[dict[str, Any]]:
    """Rebuild a bounded market-board history from public paginated posts.

    This is deliberately labelled estimated: the public feed can contain pinned
    rows and does not provide an official historical sentiment series. We only
    use dates with observed posts and never fill missing sessions with zeros.
    """
    cutoff_day = trading_day_offset(trade_date, points - 1)
    cutoff = datetime.combine(cutoff_day, clock_time.min, tzinfo=CN_TZ)
    collector = EastMoneyCollector()
    posts = collector.collect_history(target, cutoff, max_pages=48)
    buckets: dict[date, list[AnalyzedPost]] = defaultdict(list)
    for post in posts:
        day = session_date(post.published_at)
        if cutoff_day <= day <= trade_date:
            analyzed = analyze_post(post)
            if analyzed is not None:
                buckets[day].append(analyzed)
    result: list[dict[str, Any]] = []
    for day in sorted(buckets):
        # Keep even thinly observed days as provisional points. The UI and
        # metadata expose that these are estimates; silently dropping them
        # would make a 20/60-day view look empty after the first run.
        if not buckets[day]:
            continue
        metrics = aggregate_group(buckets[day], expected_sources=("eastmoney",))
        result.append({"date": day.isoformat(), **metrics, "profitEffect": _profit_effect(metrics, {}), "sampleCount": len(buckets[day]), "recordType": "estimated"})
    return result


def _merge_history_rows(rows: Iterable[Mapping[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    """Normalize history into one chronologically sorted row per date.

    A daily live run and the public-feed backfill can both produce a row for
    the same session.  Measured data is authoritative, so it replaces an
    estimate for that date.  Invalid rows are ignored rather than making the
    whole snapshot unusable.
    """
    by_date: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        day = str(raw.get("date", "")).strip()
        if not day:
            continue
        row = dict(raw)
        current = by_date.get(day)
        measured_replaces_estimate = row.get("recordType") == "measured" and current and current.get("recordType") != "measured"
        if current is None or measured_replaces_estimate:
            by_date[day] = row
        elif current.get("recordType") == row.get("recordType"):
            # Daily files may have been written before a field was added. Merge
            # same-type rows so newer, non-null enrichment fills those gaps.
            merged = dict(current)
            merged.update({key: value for key, value in row.items() if value is not None})
            by_date[day] = merged
    return [by_date[day] for day in sorted(by_date)][-max(1, limit):]


def build_snapshot(root: Path, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(CN_TZ)
    config = _load_json(root / "config" / "targets.json", {})
    targets = config.get("targets") if isinstance(config, dict) else None
    if not isinstance(targets, list) or not targets:
        raise RuntimeError("config/targets.json 没有有效目标")
    latest_path = root / "public" / "data" / "latest.json"
    previous = _load_json(latest_path, {})
    persisted_snapshots = [
        snapshot
        for snapshot in _load_persisted_daily_snapshots(root, limit=60)
        if str((snapshot.get("meta") or {}).get("mode", "live")) != "demo"
    ]
    outcomes = _collect(targets)
    if not any(outcome.ok and outcome.posts for outcome in outcomes):
        raise RuntimeError("所有公开来源均未取得帖子；已保留上一份快照")
    trade_date = effective_trade_date(now)
    analyzed, filtered, unique_authors = _prepare_posts(outcomes, trade_date)
    if not analyzed:
        raise RuntimeError("来源可访问，但最近三个交易日没有有效样本；已保留上一份快照")

    source_rows = _source_rows(outcomes, analyzed, targets)
    available_sources = sum(row["status"] in ("ok", "partial") and row["sampleCount"] > 0 for row in source_rows)
    coverage = available_sources / len(EXPECTED_SOURCES)
    summary_metrics = aggregate_group(analyzed)
    summary_subindices = _participant_indices(summary_metrics)
    try:
        market_data = fetch_market_data(targets, trade_date)
    except Exception:
        # Quotes and flow are enrichment only; sentiment remains usable when
        # an optional quote endpoint is unavailable or rate-limited.
        market_data = {}
    previous_meta = previous.get("meta", {}) if isinstance(previous, dict) and isinstance(previous.get("meta", {}), dict) else {}
    # A snapshot produced before live history metadata was introduced may still
    # contain the bundled demo curve. Start a clean live method segment once.
    previous_is_demo = bool(previous_meta.get("mode") == "demo" or "historyMode" not in previous_meta)
    previous_history_rows = [] if previous_is_demo else (previous.get("history") if isinstance(previous, dict) and isinstance(previous.get("history"), list) else [])
    persisted_history = _load_persisted_market_history(persisted_snapshots)
    previous_history = _merge_history_rows([*previous_history_rows, *persisted_history])
    older_history = [row for row in previous_history if str(row.get("date", "")) < trade_date.isoformat()]
    previous_overall = float(older_history[-1].get("overall", summary_metrics["overall"])) if older_history else summary_metrics["overall"]

    previous_sector_map = {} if previous_is_demo else ({str(row.get("id")): row for row in (previous.get("sectors") or []) if isinstance(row, dict)} if isinstance(previous, dict) else {})
    previous_sector_rows = [] if previous_is_demo else (previous.get("sectorHistory") if isinstance(previous, dict) and isinstance(previous.get("sectorHistory"), list) else [])
    persisted_sector_history = _load_persisted_sector_history(persisted_snapshots)
    previous_sector_history = _merge_sector_history([*previous_sector_rows, *persisted_sector_history], [])
    observed_sector_history = _daily_sector_history(analyzed, targets, trade_date)
    sector_history = _merge_sector_history(previous_sector_history, observed_sector_history)
    today_sector_total = sum(
        1 for item in analyzed
        if item.post.target_id != "market" and session_date(item.post.published_at) == trade_date
    )
    sectors = []
    target_names = {str(target.get("id")): str(target.get("name")) for target in targets}
    for target in targets:
        if target.get("id") == "market":
            continue
        target_id = str(target["id"])
        sector_posts = [item for item in analyzed if item.post.target_id == target_id]
        current_posts = [item for item in sector_posts if session_date(item.post.published_at) == trade_date]
        score_posts = current_posts or sector_posts
        metrics = aggregate_group(score_posts)
        sector_coverage = len({item.post.source for item in score_posts}) / len(EXPECTED_SOURCES)
        previous_sector = previous_sector_map.get(target_id, {})
        heat_series = _sector_metric_series(sector_history, target_id, "heat", trade_date)
        overall_series = _sector_metric_series(sector_history, target_id, "overall", trade_date)
        sample_series = _sector_metric_series(sector_history, target_id, "sampleCount", trade_date)
        current_heat = heat_series[-1][1] if heat_series and heat_series[-1][0] == trade_date.isoformat() else metrics["heat"]
        prior_heat = [value for day, value in heat_series if day < trade_date.isoformat()]
        prior_overall = [value for day, value in overall_series if day < trade_date.isoformat()]
        prior_samples = [value for day, value in sample_series if day < trade_date.isoformat()]
        heat_change_available = bool(current_posts and prior_heat)
        heat_change_5d_available = bool(current_posts and len(prior_heat) >= 5)
        heat_change = _round(current_heat - prior_heat[-1]) if heat_change_available else 0.0
        heat_change_5d = _round(current_heat - prior_heat[-5]) if heat_change_5d_available else None
        previous_score = prior_overall[-1] if prior_overall else metrics["overall"]
        previous_sample_count = int(prior_samples[-1]) if prior_samples else len(current_posts)
        mix_posts = current_posts if len(current_posts) >= 5 else sector_posts
        subindices = _participant_indices(metrics)
        quote = market_data.get(target_id, {})
        if str(previous_meta.get("tradeDate", "")) == trade_date.isoformat() and quote.get("flowNet") is None and previous_sector.get("flowNet") is not None:
            quote = {
                **quote,
                "flowNet": previous_sector.get("flowNet"),
                "flow5d": previous_sector.get("flow5d"),
                "flowRatio": previous_sector.get("flowRatio"),
                "flowSource": previous_sector.get("flowSource", "东方财富主力净流入（代表标的）"),
            }
        flow_net = quote.get("flowNet")
        flow_5d = quote.get("flow5d")
        row = {
            "id": target_id,
            "name": str(target["name"]),
            "stockCode": str(target.get("stockCode") or ""),
            "group": str(target.get("group") or "其他"),
            "representative": str(target.get("representative") or target["name"]),
            **metrics,
            **subindices,
            "heat": _round(current_heat),
            "sampleCount": len(current_posts),
            "sampleCount3d": len(sector_posts),
            "sampleShare": _round(len(current_posts) / max(1, today_sector_total) * 100),
            "sampleChange": len(current_posts) - previous_sample_count,
            "dataWindow": "当日" if current_posts else "近3日回看",
            "mixWindow": "当日" if len(current_posts) >= 5 else "近3日",
            "confidence": confidence_label(sector_coverage, len(score_posts)),
            "change": _round(metrics["overall"] - previous_score),
            "heatChange": heat_change,
            "heatChange5d": heat_change_5d,
            "heatChangeAvailable": heat_change_available,
            "heatChange5dAvailable": heat_change_5d_available,
            "heatTrend": _trend_label(heat_change) if heat_change_available else "基线不足",
            "heatSeries": [{"date": day, "value": value} for day, value in heat_series[-6:]],
            "participantMix": _participant_mix(mix_posts),
            "priceChange": quote.get("priceChange"),
            "profitEffect": _profit_effect(metrics, quote),
            "flowNet": flow_net,
            "flow5d": flow_5d,
            "flowRatio": quote.get("flowRatio"),
            "flowAvailable": flow_net is not None,
            "flowSource": quote.get("flowSource", "公开资金流字段暂不可用"),
        }
        sectors.append(row)
    sectors.sort(key=lambda row: (-row["overall"], row["name"]))
    for index, row in enumerate(sectors, start=1):
        row["rank"] = index
        previous_rank = previous_sector_map.get(row["id"], {}).get("rank")
        row["rankChange"] = (int(previous_rank) - index) if previous_rank is not None else 0

    market_quote = market_data.get("market", {})
    breadth = _market_breadth(sectors, summary_metrics["direction"])
    flow_rows = [row for row in sectors if row.get("flowNet") is not None]
    flow_net_total = _round(sum(float(row["flowNet"]) for row in flow_rows)) if flow_rows else None
    flow_5d_rows = [row for row in sectors if row.get("flow5d") is not None]
    flow_5d_total = _round(sum(float(row["flow5d"]) for row in flow_5d_rows)) if flow_5d_rows else None
    market_stats = {
        "heat": summary_metrics["heat"],
        "priceChange": market_quote.get("priceChange"),
        **breadth,
        "flowNet": flow_net_total,
        "flow5d": flow_5d_total,
        "flowAvailable": bool(flow_rows),
        "flowCoverage": len(flow_rows),
        "flowTotal": len(sectors),
        "quoteSource": market_quote.get("source", "腾讯行情公开报价"),
        "flowSource": "可用主题代表标的主力净流入合计",
        "note": "赚钱效应结合代表池涨跌广度、中位涨跌与社区方向估算；资金流只合计当前可得的代表标的。",
    }

    current_sector_history = {
        "date": trade_date.isoformat(),
        "sectors": [
            {
                "id": row["id"],
                "overall": row["overall"],
                "heat": row["heat"],
                "sampleCount": row["sampleCount"],
                "profitEffect": row["profitEffect"],
                "priceChange": row["priceChange"],
                "flowNet": row["flowNet"],
            }
            for row in sectors
        ],
    }
    sector_history = _merge_sector_history(sector_history, [current_sector_history])

    point = {
        "date": trade_date.isoformat(),
        **summary_metrics,
        "profitEffect": market_stats["profitEffect"],
        "sampleCount": len(analyzed),
        "recordType": "measured",
    }
    history = [row for row in previous_history if isinstance(row, dict) and row.get("date") != point["date"]]
    needs_backfill = len(history) < 20 or any(
        row.get("recordType") == "estimated" and row.get("sampleCount") is None
        for row in history
        if isinstance(row, Mapping)
    )
    if needs_backfill:
        market_target = next((target for target in targets if target.get("id") == "market"), None)
        if market_target is not None:
            try:
                estimates = _backfill_market_history(market_target, trade_date, points=60)
                history.extend(estimates)
            except Exception:
                # A backfill failure should never prevent today's live point.
                pass

    # Merge all available observations into a deterministic chronological
    # series.  A live measurement always wins over a historical estimate for
    # the same session; sorting also handles old snapshots whose rows arrived
    # out of order.
    history = _merge_history_rows(history + [point])
    estimated_points = sum(1 for row in history if row.get("recordType") == "estimated")
    source_scores = [_source_metrics([item for item in analyzed if item.post.source == source])["overall"] for source in EXPECTED_SOURCES if any(item.post.source == source for item in analyzed)]
    agreement = _round(max(0, min(100, 100 - (statistics.pstdev(source_scores) * 3.2 if len(source_scores) > 1 else 35))))
    comments = _comment_rows(analyzed, trade_date, target_names)
    calendar = _calendar_payload(history)
    correlation = _correlation_payload(sector_history, sectors, days=30)
    interpretation = _interpretation_payload(summary_metrics, sectors, trade_date)

    snapshot = {
        "meta": {
            "generatedAt": now.astimezone(CN_TZ).isoformat(timespec="seconds"), "tradeDate": trade_date.isoformat(), "mode": "live", "historyMode": "live_with_estimate" if estimated_points else "live_only", "methodVersion": "MVP-2.0",
            "coverage": round(coverage, 3), "confidence": confidence_label(coverage, len(analyzed)),
            "estimatedHistoryPoints": estimated_points,
            "historyNote": "历史曲线中的回溯点来自全市场公开股吧分页观察，仅作估算；最新交易日为实测。" if estimated_points else "历史曲线由每日实测逐步累积。",
            "disclaimer": "本工具仅用于社区情绪观察与研究，不构成投资建议。高分不代表市场必然下跌，低分也不代表市场必然上涨。", "sources": source_rows,
        },
        "summary": {**summary_metrics, **summary_subindices, "change": _round(summary_metrics["overall"] - previous_overall), "sampleCount": len(analyzed), "label": temperature_label(summary_metrics["overall"]), "readout": readout(summary_metrics)},
        "marketStats": market_stats,
        "history": history, "sectorHistory": sector_history, "sectors": sectors, "signals": _top_signals(analyzed),
        "comments": comments,
        "calendar": calendar,
        "correlation": correlation,
        "interpretation": interpretation,
        "diagnostics": {"validPosts": len(analyzed), "filteredPosts": filtered, "uniqueAuthors": unique_authors, "sourceAgreement": agreement},
    }
    _save_json(latest_path, snapshot)
    _save_daily_files(root, snapshot)
    return snapshot
