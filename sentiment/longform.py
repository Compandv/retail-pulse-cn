"""Daily long-form report: six dimensions v2, limit ecosystem, mainline and templates.

Design: docs/plans/longform-report-2026-09-27/spec.md. Every number is computed
from saved snapshots; a missing input leaves the value empty with a reason.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .collectors import CN_TZ
from .market_watch import atomic_json, number, read_json
from .report import assemble_report, relative, score

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/longform.json").read_text(encoding="utf-8"))
ANCHORS = json.loads((ROOT / CONFIG["anchorsFile"]).read_text(encoding="utf-8"))["anchors"]
VERSION = CONFIG["version"]
LABELS = {item["key"]: item["label"] for item in CONFIG["dimensions"]}
SHAPES = {item["key"]: item for item in CONFIG["shapes"]}
LIGHTS = {"red": "红", "yellow": "黄", "green": "绿", "grey": "灰"}


def mix(*pairs):
    """Weighted sum of (weight, value); empty when any value is missing."""
    if any(value is None for _, value in pairs):
        return None
    return score(sum(weight * value for weight, value in pairs))


def previous_amounts(sectors, previous_capture, previous_day, previous_market=None):
    """Member turnover of each topic on the previous session, same member list.

    Prefers the private capture; otherwise the public market snapshot's
    stockAmounts (saved since 2026-09-27), so a cloud run can use it too.
    """
    if previous_capture:
        amounts = {r["code"]: r["amount"] for r in previous_capture.get("stockFacts", [])
                   if r.get("date") == previous_day and number(r.get("amount")) is not None and r["amount"] >= 0}
    elif previous_market and previous_market.get("stockAmounts") and len(previous_market["stockAmounts"]) == len(previous_market.get("stockCodes", [])):
        amounts = {code: value for code, value in zip(previous_market["stockCodes"], previous_market["stockAmounts"]) if value is not None and value >= 0}
    else:
        return {}
    result = {}
    for sector in sectors:
        codes = sector.get("memberCodes") or []
        have = [amounts[code] for code in codes if code in amounts]
        if codes and len(have) / len(codes) >= 0.9:
            result[sector["id"]] = sum(have)
    return result


def dimensions_v2(sectors, prior_amounts):
    """Per topic: five dimensions, inputs, weighted total and what is missing."""
    obs = lambda s, key: s.get("observation", {}).get(key)  # noqa: E731
    amounts = [s.get("amount") for s in sectors]
    panics = [obs(s, "panic") for s in sectors]
    rebounds = [obs(s, "rebound") for s in sectors]

    def drop_value(sector):
        before, now, change = prior_amounts.get(sector["id"]), sector.get("amount"), number(sector.get("changePct"))
        if before is None or now is None or change is None:
            return None
        return abs(change) if change < 0 and now > before else 0

    drops = [drop_value(s) for s in sectors]
    result = {}
    for sector, drop in zip(sectors, drops):
        dims = sector.get("dimensions", {})
        amount_rank = relative(amounts, sector.get("amount"))
        panic_rank = relative(panics, obs(sector, "panic"))
        drop_rank = relative(drops, drop)
        values = {
            "heat": mix((0.4, dims.get("discussion")), (0.6, amount_rank)),
            "spread": mix((0.5, dims.get("spread")), (0.5, dims.get("growth"))),
            "shake": mix((0.6, panic_rank), (0.4, drop_rank)),
            "rebound": relative(rebounds, obs(sector, "rebound")),
            "crowding": score(dims.get("crowding")),
        }
        missing = [LABELS[key] for key, value in values.items() if value is None]
        total = None if missing else mix(*((CONFIG["weights"][key], value) for key, value in values.items()))
        audit = (sector.get("expressionProfile") or {}).get("behaviorAudit") or {}
        result[sector["id"]] = {
            "dimensions": values, "total": total, "missing": missing,
            "chaseTrial": {"score": audit.get("score"), "coverage": audit.get("coverage"), "judged": audit.get("judgedAccounts")},
            "inputs": {"discussion": dims.get("discussion"), "amount": sector.get("amount"), "amountRank": amount_rank,
                       "spread": dims.get("spread"), "growth": dims.get("growth"), "panicRate": obs(sector, "panic"), "panicRank": panic_rank,
                       "previousAmount": prior_amounts.get(sector["id"]), "dropValue": drop, "dropRank": drop_rank,
                       "reboundRate": obs(sector, "rebound"), "reboundCount": obs(sector, "reboundCount"), "sampleCount": obs(sector, "sampleCount"),
                       "turnover": sector.get("turnover")},
        }
    return result


def shape_of(dims, previous_dims=None):
    """First matching descriptive shape; see config/longform.json."""
    high, low = CONFIG["high"], CONFIG["low"]
    get = lambda key: dims.get(key)  # noqa: E731
    is_high = lambda key: get(key) is not None and get(key) >= high  # noqa: E731
    if is_high("heat") and is_high("shake"):
        return "hotShaky"
    if is_high("spread") and get("shake") is not None and get("shake") <= low:
        return "spreadCalm"
    if is_high("shake") and is_high("rebound"):
        return "shakyRebound"
    if previous_dims and None not in (get("heat"), get("shake"), previous_dims.get("heat"), previous_dims.get("shake")) \
            and previous_dims["heat"] - get("heat") >= CONFIG["coolingDrop"] and get("shake") > previous_dims["shake"]:
        return "cooling"
    if all(value is not None and value <= low for value in dims.values()):
        return "quiet"
    return "neutral"


def alert_of(dims):
    crowding, shake = dims.get("crowding"), dims.get("shake")
    rules = CONFIG["alerts"]
    if crowding is None or shake is None:
        return {"level": "grey", "text": rules["grey"]["text"]}
    if crowding >= rules["red"]["crowding"] and shake >= rules["red"]["shake"]:
        return {"level": "red", "text": rules["red"]["text"]}
    if crowding >= rules["yellow"]["crowding"] or shake >= rules["yellow"]["shake"]:
        return {"level": "yellow", "text": rules["yellow"]["text"]}
    return {"level": "green", "text": rules["green"]["text"]}


def mainline(topics, limit):
    """Topic with the most limit-up members; concentration = its share of all limit-ups."""
    if not limit or not limit.get("coverage", {}).get("limitUp", {}).get("complete"):
        return None
    codes = {row["code"] for row in limit.get("limitUp", [])}
    best = None
    for topic in topics:
        hits = sorted(codes & set(topic.get("memberCodes") or []))
        topic["limitUpCount"] = len(hits)
        topic["limitUpStocks"] = [row for row in limit["limitUp"] if row["code"] in hits]
        key = (len(hits), number(topic.get("changePct")) or -999)
        if hits and (best is None or key > best[0]):
            best = (key, topic)
    total = limit["metrics"].get("limitUp")
    if not best or not total:
        return None
    topic = best[1]
    return {"id": topic["id"], "name": topic["name"], "limitUpCount": topic["limitUpCount"], "limitUpTotal": total,
            "concentration": round(100 * topic["limitUpCount"] / total, 1), "changePct": topic.get("changePct")}


def index_rows(indices, day):
    rows = []
    for symbol, item in indices.items():
        dates = sorted(d for d in item["closes"] if d <= day)
        if not dates or dates[-1] != day:
            rows.append({"symbol": symbol, "name": item["name"], "close": None, "changePct": None})
            continue
        close = item["closes"][day]
        prev = item["closes"][dates[-2]] if len(dates) >= 2 else None
        rows.append({"symbol": symbol, "name": item["name"], "close": close, "changePct": round(100 * (close / prev - 1), 2) if prev else None})
    return rows


def margin_row(margin, day):
    """Latest margin balance published on or before `day` (it lags one session)."""
    dates = sorted(d for d in margin if d <= day)
    if not dates:
        return None
    current = margin[dates[-1]]
    previous = margin[dates[-2]] if len(dates) >= 2 else None
    return {"date": dates[-1], **current, "change": current["total"] - previous["total"] if previous and current.get("total") is not None and previous.get("total") is not None else None}


def anchor_rows(indices, margin, day):
    result = []
    for anchor in ANCHORS:
        if anchor["date"][5:] != day[5:] or anchor["date"] >= day:
            continue
        rows = []
        for symbol, item in indices.items():
            before = [d for d in item["closes"] if d < anchor["date"]]
            if not before or day not in item["closes"]:
                continue
            base = max(before)
            rows.append({"name": item["name"], "baseDate": base, "base": item["closes"][base], "close": item["closes"][day],
                         "changePct": round(100 * (item["closes"][day] / item["closes"][base] - 1), 2)})
        base_margin = margin_row(margin, max(d for d in margin if d < anchor["date"])) if any(d < anchor["date"] for d in margin) else None
        end_margin = margin_row(margin, day)
        result.append({**anchor, "years": int(day[:4]) - int(anchor["date"][:4]), "indices": rows,
                       "margin": {"base": base_margin, "end": end_margin,
                                  "changePct": round(100 * (end_margin["total"] / base_margin["total"] - 1), 1) if base_margin and end_margin and base_margin.get("total") and end_margin.get("total") else None}})
    return result


def yi(amount):
    if amount is None:
        return "—"
    return f"{amount / 1e12:.2f} 万亿" if abs(amount) >= 1e12 else f"{amount / 1e8:,.0f} 亿"


def template_text(report):
    """Plain sentences built only from computed fields; used when no model runs."""
    market, limit, top = report["market"], report.get("limit") or {}, report["topics"]
    metrics = limit.get("metrics") or {}
    main = report.get("mainline")
    parts = [f"红盘率 {market['upRate']}%" if market.get("upRate") is not None else None,
             f"涨停 {metrics['limitUp']} 家" if metrics.get("limitUp") is not None else None,
             f"主线 {main['name']}" if main else None]
    day = date.fromisoformat(report["meta"]["tradeDate"])
    title = f"{day.month}月{day.day}日：" + "，".join(p for p in parts if p)
    ranked = [t for t in top if t["total"] is not None]
    change = market.get("amountChange")
    one = [f"上涨 {market['up']} 家、下跌 {market['down']} 家，成交 {yi(market.get('amount'))}"
           + (f"（较前一交易日{'增加' if change > 0 else '减少'} {yi(abs(change))}）" if change is not None else "")]
    if metrics.get("limitUp") is not None:
        one.append(f"涨停 {metrics['limitUp']}、跌停 {metrics.get('limitDown', '—')}，炸板率 {metrics.get('brokenRate', '—')}%")
    if ranked:
        best = ranked[0]
        one.append(f"十强题材中总分最高的是{best['name']}（{best['total']}，{best['shape']['label']}）")
    lines = {t["id"]: f"{t['name']}：{t['shape']['text']}；拥挤提示为{LIGHTS[t['alert']['level']]}灯。" for t in top}
    return {"source": "template", "title": title, "oneLiner": "；".join(one) + "。", "topics": lines}


def build_daily(root, day: str, indices=None, margin=None) -> dict:
    """Assemble one day from saved snapshots; network only for index and margin history."""
    from .longform_sources import fetch_index_closes, fetch_margin
    from .trading_calendar import previous_trading_day
    root = Path(root)
    market = read_json(root / "public/data/market/daily" / f"{day}.json", None)
    if not market:
        raise RuntimeError(f"{day} 没有市场快照，无法生成长图")
    previous_day = previous_trading_day(date.fromisoformat(day)).isoformat()
    capture = read_json(root / "work/report-observations" / f"{day}.json", None)
    report, source = None, None
    if capture:
        try:
            report, source = assemble_report(market, capture), "recomputed"
        except Exception:
            report = None
    if report is None:
        report = read_json(root / "public/data/report/daily" / f"{day}.json", None)
        source = "saved" if report else None
    sectors = (report or {}).get("sectors", [])
    prev_market = read_json(root / "public/data/market/daily" / f"{previous_day}.json", {}).get("market", {})
    prior = previous_amounts(sectors, read_json(root / "work/report-observations" / f"{previous_day}.json", None), previous_day, prev_market)
    dims = dimensions_v2(sectors, prior)
    previous_longform = read_json(root / "public/data/longform/daily" / f"{previous_day}.json", {})
    before = {t["id"]: t for t in previous_longform.get("topics", [])}
    topics = []
    for sector in sectors:
        item = dims[sector["id"]]
        prev = before.get(sector["id"])
        topics.append({"id": sector["id"], "code": sector.get("code"), "name": sector["name"], "changePct": sector.get("changePct"),
                       "turnover": sector.get("turnover"), "leader": sector.get("leader"), "amount": sector.get("amount"),
                       "memberCodes": sector.get("memberCodes") or [], **item,
                       "totalChange": round(item["total"] - prev["total"], 1) if prev and prev.get("total") is not None and item["total"] is not None else None,
                       "isNew": prev is None and bool(previous_longform),
                       "shape": {"key": (key := shape_of(item["dimensions"], prev and prev.get("dimensions"))), **SHAPES[key]},
                       "alert": alert_of(item["dimensions"]),
                       "evidence": (sector.get("observation") or {}).get("posts", [])[:3]})
    topics.sort(key=lambda t: (t["total"] is None, -(t["total"] or 0)))
    limit = read_json(root / "public/data/limit/daily" / f"{day}.json", None)
    line = mainline(topics, limit)
    indices = fetch_index_closes() if indices is None else indices
    margin = fetch_margin() if margin is None else margin
    m = market["market"]
    amount_change = m["amount"] - prev_market["amount"] if m.get("amountComplete") and prev_market.get("amountComplete") else None
    result = {
        "meta": {"version": VERSION, "dimensionsVersion": CONFIG["dimensionsVersion"], "tradeDate": day, "previousDate": previous_day,
                 "builtAt": datetime.now(CN_TZ).isoformat(timespec="seconds"), "reportSource": source,
                 "reportMethod": (report or {}).get("meta", {}).get("analysisVersion"),
                 "marketCollectedAt": market["meta"].get("collectedAt"), "limitCollectedAt": (limit or {}).get("collectedAt"),
                 "weights": CONFIG["weights"], "dimensions": CONFIG["dimensions"],
                 "notes": ["六维为十强题材之间的相对分位（本表分位），冷门的一天也会有题材得高分。",
                           "总分为试验组合，未经样本外校准；高分表示本表内相对热闹，不是买卖信号。",
                           "两融数据次一交易日公布，展示的是最近已公布日期。"]},
        "market": {**{k: m.get(k) for k in ("up", "down", "flat", "upRate", "medianChange", "amount", "amountComplete")},
                   "amountChange": amount_change, "diagnostics": m.get("diagnostics")},
        "thermometers": (report or {}).get("thermometers", []),
        "limit": {k: limit[k] for k in ("metrics", "coverage", "chainCheck", "collectedAt")} if limit else None,
        "limitTop": sorted((limit or {}).get("limitUp", []), key=lambda r: -(r.get("boards") or 0))[:10],
        "mainline": line,
        "topics": topics,
        "flows": top_flows((report or {}).get("flows", {}).get("rows", [])),
        "indices": index_rows(indices, day),
        "margin": margin_row(margin, day),
        "anchors": anchor_rows(indices, margin, day),
    }
    result["narrative"] = template_text(result)
    return result


def top_flows(rows, n=5):
    out = {}
    for kind in ("industry", "concept"):
        subset = [r for r in rows if r.get("kind") == kind and number(r.get("net")) is not None]
        out[kind] = {"inflow": sorted([r for r in subset if r["net"] > 0], key=lambda r: -r["net"])[:n],
                     "outflow": sorted([r for r in subset if r["net"] < 0], key=lambda r: r["net"])[:n]}
    return out


def save_daily(root, report) -> dict:
    root = Path(root)
    directory = root / "public/data/longform/daily"
    atomic_json(directory / f"{report['meta']['tradeDate']}.json", report)
    dates = sorted(p.stem for p in directory.glob("????-??-??.json"))
    atomic_json(root / "public/data/longform/index.json", {"version": VERSION, "dates": dates})
    atomic_json(root / "public/data/longform/latest.json", read_json(directory / f"{dates[-1]}.json", report))
    return report


def build_longform_snapshot(root, now=None) -> dict:
    """Daily entry for update_index: the latest session with a market snapshot."""
    from .trading_calendar import effective_trade_date
    from .longform_sources import fetch_index_closes, fetch_margin
    from .weekly import build_weekly, is_week_end, save_weekly, week_id
    day = effective_trade_date(now or datetime.now(CN_TZ))
    from .longform_reading import narrate
    indices, margin = fetch_index_closes(), fetch_margin()
    report = build_daily(root, day.isoformat(), indices, margin)
    report["narrative"] = narrate(root, report, "daily")  # template text unless a model key is configured
    save_daily(root, report)
    if is_week_end(day):  # the weekly report follows the week's last session automatically
        week = build_weekly(root, week_id(day), indices)
        week["narrative"] = narrate(root, week, "weekly")
        save_weekly(root, week)
    return report
