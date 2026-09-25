"""Daily, source-defined sector discovery independent of the community watchlist."""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import statistics
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .collectors import CN_TZ, request_text
from .pipeline import effective_trade_date, is_trading_day
from .market_diagnostics import build_market_diagnostics

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/market-watch.json").read_text(encoding="utf-8"))
VERSION = CONFIG["version"]
SOURCE = "东方财富板块与 A 股公开行情"
ENDPOINT = "https://17.push2.eastmoney.com/api/qt/clist/get"
FIELDS = "f2,f3,f5,f6,f8,f12,f13,f14,f18,f20,f104,f105,f124,f128,f140,f136"


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def rounded(value):
    return round(value, 2) if value is not None else None


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".market-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def fetch_page(group, page):
    params = urllib.parse.urlencode({
        "pn": page, "pz": CONFIG["pageSize"], "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": 2, "invt": 2,
        "fid": "f3", "fs": CONFIG["groups"][group]["filter"], "fields": FIELDS,
    })
    payload = json.loads(request_text(ENDPOINT + "?" + params, "https://quote.eastmoney.com/", timeout=12, attempts=2))
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("total"), int):
        raise RuntimeError("行情目录结构异常")
    rows = data.get("diff")
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("行情目录行结构异常")
    return data["total"], rows


def collect_group(group):
    """Check every page; a provider cap/repeated page never becomes 'complete'."""
    print(f"东方财富：开始读取 {group} 目录", flush=True)
    result = {"group": group, "expected": None, "rows": [], "pages": 0, "complete": False, "errors": []}
    try:
        total, first = fetch_page(group, 1)
    except Exception as exc:
        result["errors"].append(str(exc)[:180])
        print(f"东方财富 {group} 首次请求失败，将检查备用来源", flush=True)
        return result
    result.update(expected=total, pages=1)
    print(f"东方财富 {group}：首批 {len(first)}/{total} 条，继续分页", flush=True)
    pages = {1: first}
    needed = math.ceil(total / CONFIG["pageSize"])
    if needed > CONFIG["maxPages"]:
        result["errors"].append("来源总量超过采集上限")
    with ThreadPoolExecutor(max_workers=CONFIG["workers"]) as pool:
        futures = {pool.submit(fetch_page, group, page): page for page in range(2, min(needed, CONFIG["maxPages"]) + 1)}
        for future in as_completed(futures):
            page = futures[future]
            try:
                reported, rows = future.result()
                result["pages"] += 1
                if reported != total:
                    result["errors"].append(f"第 {page} 页总数变化")
                pages[page] = rows
            except Exception as exc:
                result["errors"].append(f"第 {page} 页：{str(exc)[:120]}")
    seen = {}
    for page in sorted(pages):
        for row in pages[page]:
            code = str(row.get("f12") or "")
            if not code:
                result["errors"].append(f"第 {page} 页缺少代码")
            elif code in seen:
                result["errors"].append(f"重复代码 {code}，目录可能在分页时变化")
            else:
                seen[code] = row
    result["rows"] = list(seen.values())
    result["complete"] = not result["errors"] and len(seen) == total and total > 0
    return result


def collect_market(day, now, root=None):
    # Each source group paginates with a bounded pool; don't multiply concurrency.
    previous = read_json(Path(root) / "public/data/market/latest.json", {}) if root else {}
    if root and previous.get("meta", {}).get("sourceId") == "sina-tencent":
        from .sina_market import collect_sina_market
        return collect_sina_market(root, day, now)
    primary = {"date": day, "collectedAt": now.isoformat(timespec="seconds"), "version": VERSION, "provider": "eastmoney",
               "groups": {group: collect_group(group) for group in CONFIG["groups"]}}
    if root and not all(group["complete"] for group in primary["groups"].values()):
        from .sina_market import collect_sina_market
        fallback = collect_sina_market(root, day, now)
        if all(fallback["groups"][group]["complete"] for group in ("industry", "concept")) and any(row.get("f124") for row in fallback["groups"]["industry"]["rows"]):
            fallback["primaryErrors"] = {key: value["errors"] for key, value in primary["groups"].items()}
            return fallback
    return primary


def normalize_row(raw, group, day, provider="eastmoney"):
    code, name = str(raw.get("f12") or ""), str(raw.get("f14") or "")
    timestamp = number(raw.get("f124"))
    try:
        as_of = datetime.fromtimestamp(timestamp, CN_TZ) if timestamp is not None else None
    except (OverflowError, OSError, ValueError):
        as_of = None
    matches_day = bool(as_of and as_of.date().isoformat() == day and as_of.hour >= 15)
    amount, turnover = number(raw.get("f6")), number(raw.get("f8"))
    amount = amount if amount is not None and amount >= 0 else None
    turnover = turnover if turnover is not None and turnover >= 0 else None
    change = number(raw.get("f3"))
    up, down = number(raw.get("f104")), number(raw.get("f105"))
    return {"id": f"{provider}:{group}:{code}", "code": code, "name": name, "kind": group, "provider": provider,
            "asOf": as_of.isoformat(timespec="seconds") if as_of else None,
            "dateValid": matches_day, "price": number(raw.get("f2")) if matches_day else None,
            "changePct": change if matches_day else None, "amount": amount if matches_day else None,
            "turnover": turnover if matches_day else None,
            "up": int(up) if matches_day and up is not None and up >= 0 else None,
            "down": int(down) if matches_day and down is not None and down >= 0 else None,
            "leader": {"name": str(raw.get("f128") or ""), "code": str(raw.get("f140") or ""), "changePct": number(raw.get("f136"))} if group != "stocks" and matches_day else None,
            "memberCount": raw.get("memberCount"), "quoteCoverage": raw.get("quoteCoverage"),
            "rawMemberCount": raw.get("rawMemberCount"), "excludedMemberCount": raw.get("excludedMemberCount"),
            "memberSignature": raw.get("memberSignature"),
            "sourceUrl": (f"https://finance.sina.com.cn/stock/sl/#{code}" if provider == "sina-tencent" else f"https://quote.eastmoney.com/bk/90.{code}.html") if group != "stocks" else None}


def percentile(value, reference):
    valid = [item for item in reference if number(item) is not None]
    if value is None or not valid:
        return None
    return rounded(100 * sum(1 if item < value else .5 if item == value else 0 for item in valid) / len(valid))


def rank_rows(rows, field):
    # Stable IDs break display ties; equal values retain the same competition rank.
    ordered = sorted([row for row in rows if row.get(field) is not None], key=lambda row: (-row[field], row["id"]))
    ranks, rank, last = {}, 0, None
    for index, row in enumerate(ordered, 1):
        if row[field] != last:
            rank = index
        ranks[row["id"]] = rank
        last = row[field]
    return ranks


def summarize_stocks(rows, capture, previous=None, diagnostics_rows=None):
    valid = [row for row in rows if row["dateValid"] and row["changePct"] is not None]
    amounts = [row["amount"] for row in rows if row["dateValid"] and row["amount"] is not None]
    complete = bool(capture.get("complete")) and len(amounts) == len(rows) and bool(rows)
    amount = sum(amounts) if amounts else None
    comparable = complete and previous and previous.get("amountComplete") and previous.get("stockCodes") == sorted(row["code"] for row in rows)
    previous_amount = previous.get("amount") if comparable else None
    return {"range": "沪深北 A 股（来源证券范围）", "sourceTotal": capture.get("expected"),
            "observed": len(rows), "quoted": len(valid), "missingDate": sum(not row["dateValid"] for row in rows),
            "up": sum(row["changePct"] > 0 for row in valid), "down": sum(row["changePct"] < 0 for row in valid),
            "flat": sum(row["changePct"] == 0 for row in valid),
            "medianChange": rounded(statistics.median(row["changePct"] for row in valid)) if valid else None,
            "upRate": rounded(100 * sum(row["changePct"] > 0 for row in valid) / len(valid)) if valid else None,
            "amount": rounded(amount), "amountCoverage": len(amounts), "amountComplete": complete,
            "amountChange": rounded(amount - previous_amount) if amount is not None and previous_amount is not None else None,
            "stockCodes": sorted(row["code"] for row in rows),
            "diagnostics": build_market_diagnostics(rows if diagnostics_rows is None else diagnostics_rows, capture)}


def assemble_market(capture, history):
    day = capture["date"]
    provider = capture.get("provider", "eastmoney")
    # Never fit or compare against today's replay, future dates or another method.
    past_by_date = {item["meta"]["tradeDate"]: item for item in history if item.get("meta", {}).get("methodVersion") == VERSION and item["meta"].get("sourceId", "eastmoney") == provider and item["meta"].get("tradeDate", "") < day}
    past = [past_by_date[key] for key in sorted(past_by_date)][-CONFIG["baselineDays"]:]
    previous = past[-1] if past else None
    source_status, groups, boards = [], {}, []
    for group in CONFIG["groups"]:
        outcome = capture["groups"].get(group, {"expected": None, "rows": [], "pages": 0, "complete": False, "errors": ["未采集"]})
        raw_rows = {str(row.get("f12")): row for row in outcome["rows"] if row.get("f12")}
        catalog_complete = bool(outcome["complete"] and len(raw_rows) == len(outcome["rows"]) and len(raw_rows) == outcome["expected"])
        normalized = [normalize_row(row, group, day, provider) for row in raw_rows.values()]
        groups[group] = normalized
        all_current = bool(normalized) and all(row["dateValid"] for row in normalized)
        source_status.append({"id": group, "name": CONFIG["groups"][group]["name"], "expected": outcome["expected"], "observed": len(normalized),
                              "dated": sum(row["dateValid"] for row in normalized), "pages": outcome["pages"], "complete": catalog_complete,
                              "status": "ok" if catalog_complete and all_current else "partial" if normalized else "failed", "errors": outcome["errors"][:5]})
        if group == "stocks":
            continue
        turnover_values = [row["turnover"] for row in normalized if row["turnover"] is not None]
        change_ranks, turnover_ranks = rank_rows(normalized, "changePct"), rank_rows(normalized, "turnover")
        prior_group = [row for row in previous.get("boards", []) if row["kind"] == group] if previous else []
        previous_by_id = {row["id"]: row for row in prior_group}
        previous_ranks = rank_rows(prior_group, "changePct")
        prior_source = next((row for row in previous["meta"]["sources"] if row["id"] == group), None) if previous else None
        same_universe = bool(prior_source and prior_source["complete"] and catalog_complete and set(previous_by_id) == {row["id"] for row in normalized} and
                             {row["id"] for row in prior_group if row["changePct"] is not None} == set(change_ranks))
        for row in normalized:
            previous_row = previous_by_id.get(row["id"])
            eligible = []
            for saved in past:
                old = next((item for item in saved["boards"] if item["id"] == row["id"]), None)
                if old and old.get("dateValid") and old.get("turnover") is not None and old.get("memberSignature") == row.get("memberSignature"):
                    eligible.append(old["turnover"])
            row.update(rank=change_ranks.get(row["id"]), turnoverRank=turnover_ranks.get(row["id"]),
                       relativeActivity=percentile(row["turnover"], turnover_values), relativeCount=len(turnover_values),
                       activityHistory=percentile(row["turnover"], eligible) if len(eligible) >= CONFIG["minimumBaselineDays"] else None,
                       baselineDays=len(eligible), previousDate=previous["meta"]["tradeDate"] if previous else None,
                       previousRank=previous_ranks.get(row["id"]) if same_universe else None,
                       rankChange=previous_ranks[row["id"]] - change_ranks[row["id"]] if same_universe and row["id"] in previous_ranks and row["id"] in change_ranks else None,
                       turnoverChange=rounded(row["turnover"] - previous_row["turnover"]) if previous_row and previous_row.get("turnover") is not None and row["turnover"] is not None and previous_row.get("memberSignature") == row.get("memberSignature") else None,
                       catalogComplete=catalog_complete, discussion=None)
        boards.extend(normalized)
    stock_capture = {**capture["groups"].get("stocks", {}), "complete": next(row["complete"] for row in source_status if row["id"] == "stocks")}
    # Inspect records before legacy de-duplication so conflicting quotes remain visible.
    diagnostic_rows = [normalize_row(raw, "stocks", day, provider) for raw in capture["groups"].get("stocks", {}).get("rows", [])]
    market = summarize_stocks(groups["stocks"], stock_capture, previous.get("market") if previous else None, diagnostic_rows)
    return {"meta": {"methodVersion": VERSION, "tradeDate": day, "collectedAt": capture["collectedAt"], "source": "新浪成分目录 + 腾讯收盘行情" if provider == "sina-tencent" else SOURCE,
                     "sourceId": provider, "calculation": capture.get("sourceNote", "来源板块指数涨跌、换手及成交额；不以代表股代替板块。"),
                     "sources": source_status, "status": "ok" if all(row["status"] == "ok" for row in source_status) else "partial",
                     "rankingNote": "行业、概念每天从来源目录更新；换手活跃为当日同类板块分位，历史换手分位另列。"},
            "market": market, "boards": sorted(boards, key=lambda row: (row["kind"], row["rank"] if row["rank"] is not None else math.inf, row["id"]))}


def persist_market(root, snapshot, details=None):
    directory = Path(root) / "public/data/market"
    latest = read_json(directory / "latest.json", {})
    day = snapshot["meta"]["tradeDate"]
    if not any(row["dateValid"] and row["changePct"] is not None for row in snapshot["boards"]):
        raise RuntimeError("板块来源没有所选交易日行情，保留上一份市场快照")
    if latest.get("meta", {}).get("tradeDate", "") > day:
        raise RuntimeError("日期早于最新市场快照，拒绝覆盖")
    if latest.get("meta", {}).get("tradeDate") == day and latest["meta"].get("sourceId", "eastmoney") == snapshot["meta"].get("sourceId", "eastmoney"):
        old_sources = {row["id"]: row for row in latest["meta"]["sources"]}
        if any(old_sources.get(row["id"], {}).get("dated", 0) > row["dated"] for row in snapshot["meta"]["sources"]):
            raise RuntimeError("本次同日行情覆盖退化，保留已有市场快照")
    # Publish referenced details before making the summary discoverable.
    for code, detail in (details or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", code) or detail.get("date") != day or detail.get("code") != code:
            raise RuntimeError("成分明细代码或日期不匹配")
    for code, detail in (details or {}).items():
        atomic_json(directory / "members" / day / f"{code}.json", detail)
    atomic_json(directory / "daily" / f"{day}.json", snapshot)
    dates = sorted(path.stem for path in (directory / "daily").glob("????-??-??.json"))
    atomic_json(directory / "index.json", {"dates": dates, "methodVersion": VERSION})
    atomic_json(directory / "latest.json", snapshot)


def build_market_snapshot(root, now=None, capture=None):
    root = Path(root)
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = effective_trade_date(now).isoformat()
    capture = collect_market(day, now, root) if capture is None else capture
    if capture.get("version") != VERSION:
        raise RuntimeError("不兼容的市场采集版本")
    capture_day = datetime.strptime(capture["date"], "%Y-%m-%d").date()
    if capture_day.isoformat() != capture["date"] or not is_trading_day(capture_day) or capture["date"] > day:
        raise RuntimeError("市场采集日期不是有效已收盘交易日")
    atomic_json(root / "work/market-observations" / f"{capture['date']}.json", capture)
    history = [read_json(path, {}) for path in sorted((root / "public/data/market/daily").glob("????-??-??.json"))[-CONFIG["baselineDays"]:]]
    # Saved fallback captures retain memberships, making future replay independent
    # of the provider's current definitions. Signature changes reset the baseline.
    for group in ("industry", "concept"):
        for row in capture["groups"].get(group, {}).get("rows", []):
            detail = capture.get("details", {}).get(str(row.get("f12")))
            if detail and detail.get("complete"):
                row["memberSignature"] = hashlib.sha256(",".join(sorted(member["code"] for member in detail["members"])).encode()).hexdigest()[:20]
    snapshot = assemble_market(capture, history)
    persist_market(root, snapshot, capture.get("details"))
    return snapshot
