"""Build the separated V4 observations; old scores never enter the baseline."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from .collectors import CN_TZ, SinaCollector, TaogubaCollector, anonymous_author
from .measurement import METHOD_VERSION, CONFIG, prepare_observations, summarize_expressions, historical_percentile, universe_key
from .observations import CUTOFF, collect_feed, collect_trading, summarize_trading
from .pipeline import _load_json, _save_json, _save_daily_files, _load_persisted_daily_snapshots, effective_trade_date


def scopes_for(root):
    themes = _load_json(root / "config/themes.json", {"themes": []})["themes"]
    scopes = [{**theme, "kind": "basket", "group": "多股主题"} for theme in themes]
    for target in _load_json(root / "config/targets.json", {})["targets"]:
        if target["id"] == "market" or (target["id"] == "agriculture" and any(scope["id"] == "pork" for scope in scopes)):
            continue
        name = target.get("representative") or target["name"]
        scopes.append({"id": target["id"], "name": target["name"], "kind": "proxy", "group": target.get("group", "其他"), "description": f"单股主题代理：{name}，尚未覆盖整个板块。", "members": [{"code": target.get("stockCode", ""), "name": name, "role": "单股代理"}]})
    return scopes


def _supplement(code, collector):
    outcome = collector.collect({"id": code, "name": code, "stockCode": code, "eastmoneyCode": code})
    return {"code": code, "source": collector.source, "ok": outcome.ok, "error": outcome.error,
            "rows": [{"id": hashlib.sha256((post.author_key + post.text + post.published_at.isoformat()).encode()).hexdigest()[:16], "text": post.text,
                      "date": post.published_at.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"), "source": post.source, "author": post.author_key,
                      "code": code, "url": post.url, "contentKind": "标题／摘要"} for post in outcome.posts]}


def collect_batch(scopes, day, now):
    codes = sorted({member["code"] for scope in scopes for member in scope["members"] if member["code"]})
    batch = {"date": day, "collectedAt": now.isoformat(timespec="seconds"), "feeds": {}, "trading": {}, "supplement": []}
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = {}
        for code in codes:
            tasks[pool.submit(collect_feed, code, day)] = ("feeds", code)
            tasks[pool.submit(collect_trading, code, day)] = ("trading", code)
            for collector in (SinaCollector(), TaogubaCollector()):
                tasks[pool.submit(_supplement, code, collector)] = ("supplement", code)
        print(f"社区：{len(codes)} 只股票，{len(tasks)} 个采集任务（含行情及补充来源）", flush=True)
        for index, future in enumerate(as_completed(tasks), 1):
            kind, code = tasks[future]
            value = future.result()
            if kind == "supplement":
                batch[kind].append(value)
            else:
                batch[kind][code] = value
            if index == 1 or index % 10 == 0 or index == len(tasks):
                print(f"社区任务已返回 {index}/{len(tasks)}；列表 {len(batch['feeds'])}、行情 {len(batch['trading'])}；返回不代表数据有效，稍后统一核验。", flush=True)
    return batch


def assemble_snapshot(root, batch, scopes, now):
    day = batch["date"]
    previous = _load_json(root / "public/data/latest.json", {})
    saved = _load_persisted_daily_snapshots(root)
    saved.append(previous)
    saved = [item for item in saved if item.get("meta", {}).get("methodVersion") == METHOD_VERSION and item.get("meta", {}).get("tradeDate", "") <= day]
    attention_history, history_by_date, scopes_by_date = {}, {}, {}
    for item in saved:
        for universe, points in item.get("attentionHistory", {}).items():
            attention_history.setdefault(universe, {}).update({point["date"]: point for point in points if point["date"] < day})
        history_by_date.update({point["date"]: point for point in item.get("history", []) if point["date"] < day})
        scopes_by_date.update({point["date"]: point for point in item.get("scopeHistory", []) if point["date"] < day})

    def measure(scope):
        codes = [member["code"] for member in scope["members"]]
        feeds = [batch["feeds"][code] for code in codes]
        rows = [row for feed in feeds for row in feed["rows"]]
        # Only this common source is used for the attention time series.
        attention_posts = prepare_observations(rows, day, CUTOFF)
        # Old parsers hash missing IDs to a shared placeholder. Undo that
        # placeholder rather than treating every anonymous post as one person.
        auxiliary = [{**row, "author": "" if row["author"] == anonymous_author(row["source"], None) else row["author"]}
                     for supplement in batch.get("supplement", []) if supplement["code"] in codes for row in supplement["rows"]]
        prepared = prepare_observations(sorted(rows + auxiliary, key=lambda row: (row["date"], row["source"], row["id"])), day, CUTOFF)
        expressions = summarize_expressions(prepared["analyzed"])
        universe = universe_key(codes)
        complete = all(feed["complete"] and not feed["error"] for feed in feeds)
        value = None if attention_posts["unknownAuthorPosts"] else attention_posts["observedAuthors"]
        past = list(attention_history.get(universe, {}).values())
        attention = {**historical_percentile(value, past, day, universe, complete, CUTOFF), "universe": universe, "complete": complete,
                     **{key: attention_posts[key] for key in ("observedAuthors", "observedPosts", "unknownAuthorPosts", "excludedDate", "excludedNoise")},
                     "rawCount": sum(feed["rawCount"] for feed in feeds), "analyzedCount": len(attention_posts["analyzed"]), "memberCoverage": sum(feed["complete"] for feed in feeds), "memberTotal": len(feeds), "source": "东方财富公开列表", "cutoff": CUTOFF}
        # Unknown author counts and incomplete captures are persisted as such,
        # never silently promoted to valid calibration observations.
        point = {"date": day, "value": value, "complete": complete and value is not None, "universe": universe, "methodVersion": METHOD_VERSION, "recordType": "measured", "cutoff": CUTOFF}
        attention_history.setdefault(universe, {})[day] = point
        trading = summarize_trading([batch["trading"][code] for code in codes])
        public_posts = [{key: value for key, value in post.items() if key != "author"} for post in sorted(prepared["analyzed"], key=lambda row: row["date"], reverse=True)[:80]]
        return {**scope, "date": day, "cutoff": CUTOFF, "dataWindow": f"{day} 00:00–15:00（北京时间）", "methodVersion": METHOD_VERSION,
                "attention": attention, "expressions": expressions, "trading": trading, "posts": public_posts,
                "expressionSources": sorted({post["source"] for post in prepared["analyzed"]}),
                "feeds": [{key: value for key, value in feed.items() if key != "rows"} for feed in feeds],
                "note": "表达比例来自去重、每账户最多三条的公开样本；多平台账户分别计数。L1–L5 分级暂缓，不推定真实投资经验。"}

    measured = [measure(scope) for scope in scopes]
    all_members = {member["code"]: member for scope in scopes for member in scope["members"]}
    summary = measure({"id": "pool", "name": "观察池", "kind": "basket", "group": "观察池", "description": "配置标的的公开社区观察池，不等于 A 股全市场。", "members": list(all_members.values())})
    # Persist constituent baselines too, so querying a basket member as a
    # stock can accumulate its own history instead of inheriting the basket.
    for code in all_members:
        universe = universe_key([code])
        if day in attention_history.get(universe, {}):
            continue
        feed = batch["feeds"][code]
        prepared = prepare_observations(feed["rows"], day, CUTOFF)
        value = None if prepared["unknownAuthorPosts"] else prepared["observedAuthors"]
        attention_history.setdefault(universe, {})[day] = {"date": day, "value": value, "complete": feed["complete"] and not feed["error"] and value is not None, "universe": universe, "methodVersion": METHOD_VERSION, "recordType": "measured", "cutoff": CUTOFF}
    for row in measured:
        # Multi-theme attention shares may overlap: each numerator uses a set
        # of accounts and the pool denominator is a union, not a sum.
        denominator = summary["attention"]["observedAuthors"]
        row["attentionShare"] = round(row["attention"]["observedAuthors"] / denominator * 100, 1) if denominator else None
    expressions = summary["expressions"]
    history_by_date[day] = {"date": day, "recordType": "measured", "methodVersion": METHOD_VERSION, "overall": None, "heat": summary["attention"]["score"], "fomo": expressions["chase"], "panic": expressions["panic"], "direction": expressions["direction"], "profitEffect": summary["trading"]["score"], "sampleCount": expressions["sampleCount"]}
    scopes_by_date[day] = {"date": day, "scopes": [{"id": row["id"], "heat": row["attention"]["score"], "activity": row["trading"]["score"], "chase": row["expressions"]["chase"], "authors": row["attention"]["observedAuthors"], "complete": row["attention"]["complete"]} for row in measured]}
    sources = []
    for source, name in (("eastmoney", "东方财富"), ("sina", "新浪股吧"), ("taoguba", "淘股吧")):
        count = sum(row["source"] == source for row in summary["posts"])
        outcomes = list(batch["feeds"].values()) if source == "eastmoney" else [row for row in batch.get("supplement", []) if row["source"] == source]
        success = sum(not row.get("error") for row in outcomes)
        sources.append({"id": source, "name": name, "status": "ok" if outcomes and success == len(outcomes) else "partial" if success else "failed", "observedEntrances": success, "totalEntrances": len(outcomes), "displayedEvidence": count})
    legacy = previous.get("legacy")
    if previous.get("meta", {}).get("methodVersion") != METHOD_VERSION and previous.get("meta"):
        legacy = {"methodVersion": previous["meta"].get("methodVersion", "旧版"), "history": previous.get("history", []), "sectorHistory": previous.get("sectorHistory", []), "earlier": previous.get("legacy")}
    return {"meta": {"methodVersion": METHOD_VERSION, "tradeDate": day, "generatedAt": now.isoformat(timespec="seconds"), "collectedAt": batch["collectedAt"], "cutoff": CUTOFF, "mode": "live", "sources": sources, "scopeVersion": CONFIG["scopeVersion"], "historyNote": "仅积累同口径真实观测；至少 20 个有效历史日期才发布关注热度分。"}, "summary": summary,
            "scopes": measured, "history": [history_by_date[key] for key in sorted(history_by_date)][-60:], "scopeHistory": [scopes_by_date[key] for key in sorted(scopes_by_date)][-60:],
            "attentionHistory": {universe: [points[key] for key in sorted(points)][-61:] for universe, points in attention_history.items()}, "legacy": legacy}


def build_snapshot(root: Path, now=None):
    now = (now or datetime.now(CN_TZ)).astimezone(CN_TZ)
    day = effective_trade_date(now).isoformat()
    scopes = scopes_for(root)
    batch = collect_batch(scopes, day, now)
    if not any(feed["rows"] for feed in batch["feeds"].values()):
        raise RuntimeError("核心公开来源没有有效列表，已保留上一份快照")
    _save_json(root / f"work/v4-observations-{day}.json", batch)
    snapshot = assemble_snapshot(root, batch, scopes, now)
    persist_snapshot(root, snapshot)
    return snapshot


def persist_snapshot(root: Path, snapshot):
    """Use the same archive and stale-date guards for collection and replay."""
    if not snapshot["summary"]["expressions"]["sampleCount"]:
        raise RuntimeError("所选交易日没有有效表达，已保留上一份快照")
    previous = _load_json(root / "public/data/latest.json", {})
    if previous.get("meta", {}).get("tradeDate", "") > snapshot["meta"]["tradeDate"]:
        raise RuntimeError("观测日期早于最新快照，拒绝覆盖最新结果")
    if previous.get("meta", {}).get("methodVersion") != METHOD_VERSION and previous.get("meta", {}).get("tradeDate"):
        archive = root / "public/data/archive" / f"{previous['meta']['tradeDate']}-{previous['meta'].get('methodVersion', 'legacy').lower().replace('.', '-')}.json"
        if not archive.exists():
            _save_json(archive, previous)
    _save_json(root / "public/data/latest.json", snapshot)
    _save_daily_files(root, snapshot)
