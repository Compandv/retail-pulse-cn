"""Dated source captures for the five thermometers, hot-board matrix and flows."""
from __future__ import annotations

import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from .collectors import CN_TZ, request_text
from .market_watch import atomic_json, read_json, number, percentile
from .observations import collect_feed
from .pipeline import previous_trading_day, effective_trade_date

CONFIG = read_json(Path(__file__).resolve().parents[1] / "config/report.json", {})
VERSION = CONFIG["version"]
FLOW_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_zjlrqs"


def select_hot_boards(market):
    rows = [row for row in market["boards"] if row["kind"] == CONFIG["topKind"] and row.get("changePct") is not None and row.get("turnover") is not None]
    changes, turnovers = [r["changePct"] for r in rows], [r["turnover"] for r in rows]
    selected = [{**row, "selectionScore": round(CONFIG["momentumWeight"] * percentile(row["changePct"], changes) + CONFIG["turnoverWeight"] * percentile(row["turnover"], turnovers), 1)} for row in rows]
    return sorted(selected, key=lambda r: (-r["selectionScore"], -r["changePct"], r["id"]))[:CONFIG["topCount"]]


def fetch_flow(board, day):
    if board.get("provider") != "sina-tencent":
        raise RuntimeError("当前资金适配仅支持新浪板块代码，不跨来源强配同名板块")
    query = urllib.parse.urlencode({"page": 1, "num": 10, "sort": "opendate", "asc": 0, "bankuai": board["code"]})
    rows = json.loads(request_text(FLOW_URL + "?" + query, "https://money.finance.sina.com.cn/moneyflow/", timeout=10, attempts=2))
    if not isinstance(rows, list):
        raise RuntimeError("资金历史结构异常")
    current = next((r for r in rows if r.get("opendate") == day), None)
    if not current or number(current.get("r0_net")) is None:
        raise RuntimeError("来源未提供所选日期的主力资金，未使用旧日替代")
    return {"boardId": board["id"], "code": board["code"], "name": board["name"], "kind": board["kind"],
            "date": day, "net": number(current["r0_net"]), "ratio": number(current.get("r0_ratio")) * 100 if number(current.get("r0_ratio")) is not None else None,
            "changePct": number(current.get("avg_changeratio")) * 100 if number(current.get("avg_changeratio")) is not None else None,
            "sourceUrl": "https://money.finance.sina.com.cn/moneyflow/#!bk!" + board["code"],
            "source": "新浪板块日线主力资金 r0_net", "history": [r for r in rows if r.get("opendate", "") <= day]}


def fetch_index(symbol, name, day):
    query = urllib.parse.urlencode({"param": f"{symbol},day,,,80,qfq"})
    payload = json.loads(request_text("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + query, "https://gu.qq.com/", timeout=10, attempts=2))
    data = payload.get("data", {}).get(symbol, {})
    rows = data.get("day") or data.get("qfqday") or []
    by_date = {r[0]: r for r in rows if len(r) >= 6 and r[0] <= day and number(r[5]) is not None}
    current = by_date.get(day)
    past = [by_date[d] for d in sorted(by_date) if d < day][-60:]
    return {"symbol": symbol, "name": name, "date": day, "volumeScore": percentile(number(current[5]), [number(r[5]) for r in past]) if current and len(past) >= 20 else None,
            "baselineDays": len(past), "rows": list(by_date.values()), "source": "腾讯指数日线成交量"}


def collect_report(root, market, now=None):
    root = Path(root); now = now or datetime.now(CN_TZ)
    day = market["meta"]["tradeDate"]
    if day != effective_trade_date(now).isoformat():
        raise RuntimeError("历史报告请回放已保存的采集记录，不用当前互动量冒充旧日观测")
    previous = previous_trading_day(datetime.fromisoformat(day).date()).isoformat()
    from .topic_discovery import discover, CUTOFF as topic_cutoff
    discovery, selected, discovery_feeds = discover(root, market, previous)
    members = {b['id']: {'date': day, 'complete': True, 'sampled': True, 'members': b['members']} for b in selected}
    codes = sorted({m["code"] for d in members.values() if d.get("date") == day and d.get("complete") for m in d.get("members", [])})
    capture = {"version": VERSION, "date": day, "previousDate": previous, "collectedAt": now.isoformat(timespec="seconds"),
               "marketCollectedAt": market["meta"]["collectedAt"], "selectedIds": [b["id"] for b in selected], "members": members,
               "feeds": discovery_feeds, "flows": {}, "indices": {}, "errors": [], 'cutoff': topic_cutoff,
               'discovery': discovery, 'topicBoards': selected}
    cache = root / "work/report-cache" / VERSION / day
    def cached(group, key, fn):
        saved = read_json(cache / group / f"{key}.json", {})
        if group != "feeds" and saved.get("date") == day and saved.get("version") == VERSION:
            return {**saved["value"], "observedAt": saved["observedAt"]}
        value = fn()
        value["observedAt"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
        if not value.get("error"):
            atomic_json(cache / group / f"{key}.json", {"version": VERSION, "date": day, "observedAt": value["observedAt"], "value": value})
        return value
    def feed(code):
        return cached("feeds", code, lambda: collect_feed(code, previous, CONFIG["feedPages"]))
    def flow(board):
        return cached("flows", board["code"], lambda: fetch_flow(board, day))
    with ThreadPoolExecutor(max_workers=CONFIG["feedWorkers"]) as community_pool, ThreadPoolExecutor(max_workers=CONFIG["flowWorkers"]) as flow_pool:
        tasks = {community_pool.submit(feed, code): ("feeds", code) for code in codes if code not in capture['feeds']}
        tasks.update({flow_pool.submit(flow, b): ("flows", b["id"]) for b in market["boards"]})
        for symbol, name in CONFIG["indexSymbols"].items():
            tasks[flow_pool.submit(cached, "indices", symbol, lambda symbol=symbol, name=name: fetch_index(symbol, name, day))] = ("indices", symbol)
        for i, future in enumerate(as_completed(tasks), 1):
            group, key = tasks[future]
            try:
                capture[group][key] = future.result()
            except Exception as exc:
                capture["errors"].append({"group": group, "key": key, "error": str(exc)[:160]})
            if i == 1 or i % 10 == 0 or i == len(tasks):
                print(f"复盘任务已返回 {i}/{len(tasks)}：社区 {len(capture['feeds'])}、板块资金 {len(capture['flows'])}；稍后核验覆盖和日期。", flush=True)
    capture["completedAt"] = datetime.now(CN_TZ).isoformat(timespec="seconds")
    enrichment = CONFIG.get("bodyEnrichment", {})
    if enrichment.get("enabled") and capture.get("discovery"):
        try:
            from .profile_texts import enrich_profiles
            capture = enrich_profiles(root, capture, cutoff=topic_cutoff, max_posts=int(enrichment.get("maxPosts", 48)), min_text_length=int(enrichment.get("minTextLength", 8)))
            print(f"正文补充：尝试 {capture.get('profileEnrichment', {}).get('attempted', 0)} 条，取得 {capture.get('profileEnrichment', {}).get('observed', 0)} 条；不改变互动计数。", flush=True)
        except Exception as exc:
            capture["profileEnrichment"] = {"attempted": 0, "observed": 0, "failures": 1, "observedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"), "sampling": "正文补充失败，继续使用公开列表文本", "error": str(exc)[:160]}
            print(f"正文补充失败：{str(exc)[:160]}；继续使用公开列表文本。", flush=True)
    # Daily path uses captured public text plus a bounded, auditable body
    # sample. It never treats missing bodies as negative evidence.
    atomic_json(root / "work/report-observations" / f"{day}.json", capture)
    return capture
