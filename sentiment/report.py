"""Explainable report statistics; scores describe observations, not investors."""
from __future__ import annotations

import re
import statistics
from datetime import datetime
from pathlib import Path
from .collectors import CN_TZ
from .market_watch import atomic_json, read_json, number, percentile
from .measurement import prepare_observations, summarize_expressions
from .observations import CUTOFF
from .report_sources import CONFIG, VERSION, collect_report, select_hot_boards
from .retail_profile import refine_behavior
from .following import VERSION as ANALYSIS_VERSION, expression_profile, following_score


def score(value):
    value = number(value)
    return round(max(0, min(100, value)), 1) if value is not None else None


def public_evidence(posts):
    chosen, seen = [], set()
    groups = [lambda r: r["classification"]["chase"], lambda r: r["classification"]["panic"], lambda r: r.get("refillExpression", False), lambda r: True]
    for predicate in groups:
        count = 0
        for row in sorted(posts, key=lambda r: r["date"], reverse=True):
            identity = (row["source"], row["id"])
            if identity in seen or not predicate(row):
                continue
            seen.add(identity); chosen.append(row); count += 1
            if count == 3:
                break
    return [{"text": r["text"], "url": r["url"], "date": r["date"], "code": r["code"], "intent": r["classification"]["intentLabel"],
             "panic": r["classification"]["panic"], "refill": r.get("refillExpression", False), "replies": r.get("replies"), "forwards": r.get("forwards")} for r in chosen]


def refill_expression(text):
    """Conservative own-action/intention rule, separate from real transactions."""
    if re.search(r"他说|她说|据说|转发|昨天|前天|上周|上个月|去年", text):
        return False
    for clause in re.split(r"[，,。！!；;\n]", text):
        if re.search(r"不要|别|不敢|不想|不再|没有|没敢|没补|未补|如果|假如|等到|一旦|据说|有人|他说|她说|老师说|能否|要不要|该不该|是否|吗|么|？|[?]", clause):
            continue
        if re.search(r"补(?:了|过|点|个|一笔|了点)?仓|加仓摊(?:低|薄)|摊低成本", clause):
            return True
    return False


def measure_members(capture, codes, day, topic=None):
    feeds = [capture["feeds"].get(code) for code in codes]
    good = [f for f in feeds if f and not f.get("error") and f.get("pages", 0) > 0]
    rows = [r for f in feeds if f for r in f.get("rows", [])]
    if topic:
        from .topic_discovery import terms_for
        core = set(topic.get('coreMembers', []))
        terms = terms_for(topic['name']) + topic.get('aliases', [])
        rows = [p for p in rows if p['code'] in core or any(t.lower() in p['text'].lower() for t in terms)]
    prepared = prepare_observations(rows, day, capture.get('cutoff', CUTOFF))
    posts = [refine_behavior(post) for post in prepared["analyzed"]]
    expressions = summarize_expressions(posts)
    total = len(posts)
    refills = sum(r["refillExpression"] for r in posts)
    interactions = [r["replies"] + r["forwards"] for r in posts if number(r.get("replies")) is not None and number(r.get("forwards")) is not None and r["replies"] >= 0 and r["forwards"] >= 0]
    enough = bool(codes) and len(good) / len(codes) >= CONFIG["minimumMemberCoverage"] and total >= CONFIG["minimumPosts"]
    complete = bool(codes) and all(f and f.get("complete") and not f.get("error") for f in feeds)
    profile_posts = []
    body_count = 0
    for post in posts:
        body = capture.get("profileBodies", {}).get(post["id"], {})
        verified = body.get("date") == post["date"] and body.get("code") == post["code"] and body.get("author") == post["author"]
        profile_posts.append({**post, "text": body["text"] if verified and body.get("text") else post["text"]})
        body_count += bool(verified and body.get("text"))
    profile = expression_profile(profile_posts, prepared["observedAuthors"], enough and not prepared["unknownAuthorPosts"])
    profile.update(enrichedPosts=body_count, contentObservedAt=capture.get("profileEnrichment", {}).get("observedAt"), contentSampling=capture.get("profileEnrichment", {}).get("sampling", "本次使用保存的公开列表文本"))
    return {"authors": prepared["observedAuthors"], "observedPosts": prepared["observedPosts"], "sampleCount": total,
            "memberTotal": len(codes), "memberObserved": len(good), "memberComplete": sum(bool(f and f.get("complete") and not f.get("error")) for f in feeds),
            "complete": complete, "eligible": enough and not prepared["unknownAuthorPosts"],
            "density": prepared["observedAuthors"] / len(codes) if enough and codes and not prepared["unknownAuthorPosts"] else None,
            "interactionMean": statistics.mean(interactions) if enough and len(interactions) >= .8 * total else None,
            "panic": expressions["panic"] if enough else None, "chase": expressions["chase"] if enough else None,
            "refill": score(100 * refills / total) if enough else None,
            "refillCount": refills, "chaseCount": sum(r["classification"]["chase"] for r in posts), "panicCount": sum(r["classification"]["panic"] for r in posts),
            "bullishCount": sum(r["classification"]["bullish"] for r in posts), "bearishCount": sum(r["classification"]["bearish"] for r in posts),
            "profile": profile,
            "posts": public_evidence(posts)}


def relative(values, value):
    valid = [x for x in values if x is not None]
    if value is None or len(valid) < CONFIG["minimumComparableBoards"]:
        return None
    return 0.0 if value == 0 else score(percentile(value, valid))


def flow_diagnosis(net, change):
    if net == 0:
        return "主力净额接近平衡"
    if change is None:
        return "主力净流入" if net > 0 else "主力净流出"
    if net > 0:
        return "上涨与净流入同向" if change > 0 else "净流入伴随价格回落" if change < 0 else "价格持平、资金净流入"
    return "上涨伴随资金净流出" if change > 0 else "价格与资金共同走弱" if change < 0 else "价格持平、资金净流出"


def assemble_report(market, capture):
    day = market["meta"]["tradeDate"]
    selected = capture.get('topicBoards') if capture.get('discovery') else select_hot_boards(market)
    if capture.get("version") != VERSION or capture.get("date") != day or capture.get("marketCollectedAt") != market["meta"]["collectedAt"] or capture.get("selectedIds") != [b["id"] for b in selected]:
        raise RuntimeError("报告采集日期、版本或热点范围不匹配")
    measured, all_codes = [], set()
    for board in selected:
        detail = capture.get("members", {}).get(board["id"], {})
        codes = [m["code"] for m in detail.get("members", [])] if detail.get("complete") and detail.get("date") == day else []
        all_codes.update(codes)
        topic = board if capture.get('discovery') else None
        measurement = measure_members(capture, codes, day, topic)
        paired_codes = [code for code in codes if capture["feeds"].get(code, {}).get("complete") and not capture["feeds"].get(code, {}).get("error")]
        current_pair = measure_members(capture, paired_codes, day, topic)
        previous_pair = measure_members(capture, paired_codes, capture["previousDate"], topic)
        pair_total = current_pair["authors"] + previous_pair["authors"]
        growth_ok = codes and len(paired_codes) / len(codes) >= CONFIG["minimumMemberCoverage"] and current_pair["eligible"] and previous_pair["eligible"] and pair_total
        measured.append({"id": board["id"], "code": board["code"], "name": board["name"], "selectionScore": board["selectionScore"],
                         "changePct": board["changePct"], "turnover": board["turnover"], "leader": board.get("leader"), "crowding": board.get("relativeActivity"),
                         "growth": {"score": score(100 * current_pair["authors"] / pair_total) if growth_ok else None, "today": current_pair["authors"], "previous": previous_pair["authors"], "pairedMembers": len(paired_codes), "previousDate": capture["previousDate"], "basis": "两日同范围；50为持平"},
                         "observation": measurement})
    for row in measured:
        observation = row["observation"]
        topic = next((b for b in selected if b['id'] == row['id']), {}) if capture.get('discovery') else {}
        discussion = topic.get('attentionScore') if topic else relative([r["observation"]["authors"] if r["observation"]["eligible"] else None for r in measured], observation["authors"] if observation["eligible"] else None)
        spread = topic.get('spreadScore') if topic else relative([r["observation"]["interactionMean"] for r in measured], observation["interactionMean"])
        chase_rank = relative([r["observation"]["chase"] for r in measured], observation["chase"])
        parts = [discussion, spread, row["crowding"], chase_rank]
        row["dimensions"] = {"discussion": discussion, "spread": spread, "panic": observation["panic"], "refill": observation["refill"], "crowding": row.pop("crowding"),
                             "overheat": score(statistics.mean(parts)) if all(v is not None for v in parts) else None}
        row["overheatInputs"] = {"discussion": discussion, "spread": spread, "crowding": row["dimensions"]["crowding"], "chaseRank": chase_rank}
        row["dimensions"].update(growth=row["growth"]["score"], chase=observation["chase"], trading=row["dimensions"]["crowding"])
        row["expressionProfile"] = observation.pop("profile")
        row["leekScore"] = following_score(row["expressionProfile"])
        if capture.get('discovery') and (row['expressionProfile'].get('unknownRate') or 0) > 50:
            row['leekScore'].update(rawExpressionScore=row['leekScore']['score'], score=None,
                                    missing=['超过半数账户表达无法判别'],
                                    reason='超过半数账户表达无法判别，暂不发布韭菜综合分；原始规则表达率仍保留，不将识别不到解释为理性。')
        row["shape"] = "高换手分歧" if (row["dimensions"]["crowding"] or 0) >= 80 and (observation["panic"] or 0) >= 10 else "量价活跃" if row["changePct"] > 0 and (row["dimensions"]["crowding"] or 0) >= 80 else "价格回落" if row["changePct"] < 0 else "温和活跃"
        row["diagnosis"] = f"涨跌 {row['changePct']:+.2f}% · 换手 {row['turnover']:.2f}% · 观察 {observation['authors']} 个账户；{observation['chaseCount']}/{observation['sampleCount']} 条明确追涨表达。"
    overall = measure_members(capture, sorted(all_codes), day)
    # Comparison uses the exact same, fully scanned stock set on both dates.
    paired = [code for code in all_codes if capture["feeds"].get(code, {}).get("complete") and not capture["feeds"].get(code, {}).get("error")]
    today_pair = measure_members(capture, paired, day)
    previous_pair = measure_members(capture, paired, capture["previousDate"])
    discussion_score = None
    total_pair = today_pair["authors"] + previous_pair["authors"]
    if all_codes and len(paired) / len(all_codes) >= CONFIG["minimumMemberCoverage"] and today_pair["eligible"] and previous_pair["eligible"] and total_pair:
        discussion_score = score(100 * today_pair["authors"] / total_pair)
    direction_total = overall["bullishCount"] + overall["bearishCount"]
    greed = score(100 * overall["bullishCount"] / direction_total) if overall["eligible"] and direction_total >= CONFIG["minimumPosts"] else None
    index_scores = [value["volumeScore"] for value in capture.get("indices", {}).values() if value.get("date") == day and value.get("volumeScore") is not None]
    activity = score(statistics.mean(index_scores)) if len(index_scores) == len(CONFIG["indexSymbols"]) else None
    # Saved dated stock facts keep risk-appetite computation independent of sectors.
    stocks = capture.get("stockFacts", [])
    quoted = list({r["code"]: r for r in stocks if r.get("date") == day and number(r.get("amount")) is not None and r["amount"] >= 0}.values())
    total_amount = sum(r["amount"] for r in quoted)
    high_amount = sum(r["amount"] for r in quoted if r["code"].startswith(("300", "301", "688", "689", "920", "8", "4")))
    risk = score(100 * high_amount / total_amount) if total_amount and {r["code"] for r in quoted} == set(market["market"].get("stockCodes", [])) and len(quoted) == market["market"]["sourceTotal"] and market["market"].get("amountComplete") else None
    thermo = [
        {"key": "activity", "name": "市场热度", "score": activity, "unit": "分", "scope": "沪深指数成交量历史分位", "detail": "上证指数、深证成指成交量分别与此前60日比较，再等权平均；每个至少20日。", "evidence": [{"name": v["name"], "score": v["volumeScore"], "baselineDays": v["baselineDays"]} for v in capture.get("indices", {}).values()]},
        {"key": "profit", "name": "赚钱效应", "score": score(market["market"]["upRate"]), "unit": "%", "scope": "当日上涨股票占比", "detail": f"{market['market']['up']} 涨 / {market['market']['down']} 跌 / {market['market']['flat']} 平；涨跌中位数 {market['market']['medianChange']}%。不是持仓盈利人数。"},
        {"key": "discussion", "name": "讨论热度", "score": discussion_score, "unit": "分", "scope": "十强热点样本 · 日环比温度", "detail": f"{len(paired)}/{len(all_codes)} 只成分具有两日可比窗口；今日 {today_pair['authors']} / 前日 {previous_pair['authors']} 个账户。100×今日/(今日+前日)，50为持平；覆盖不足则留空。"},
        {"key": "greed", "name": "恐贪情绪", "score": greed, "unit": "%", "scope": "热点样本 · 多空表达平衡", "detail": f"看涨 {overall['bullishCount']} / 看跌 {overall['bearishCount']} 次标签；100×看涨/(看涨+看跌)，越高越偏乐观。双向表达计入两侧，不是全体投资者心态。"},
        {"key": "risk", "name": "风险偏好", "score": risk, "unit": "%", "scope": "高弹性交易板块成交占比", "detail": "创业板、科创板、北交所成交额占当前来源A股总额；每股仅计一次。衡量交易分布，不直接认定追涨或真实风险承受能力。"},
    ]
    board_ids = {r["id"] for r in market["boards"]}
    flows = [{k: v for k, v in row.items() if k != "history"} for row in capture.get("flows", {}).values() if row.get("date") == day and row.get("boardId") in board_ids and number(row.get("net")) is not None]
    for row in flows:
        row["diagnosis"] = flow_diagnosis(row["net"], row.get("changePct"))
    flow_coverage = [{"kind": kind, "expected": sum(r["kind"] == kind for r in market["boards"]), "observed": sum(r["kind"] == kind for r in flows)} for kind in ("industry", "concept")]
    return {"meta": {"version": VERSION, "analysisVersion": 'following-topic-2.0' if capture.get('discovery') else ANALYSIS_VERSION, 'discovery': capture.get('discovery'), "tradeDate": day, "previousDate": capture["previousDate"], "collectedAt": capture["collectedAt"],
                     "interactionAsOf": max((f.get("observedAt", capture["collectedAt"]) for f in capture["feeds"].values()), default=capture["collectedAt"]), "cutoff": capture.get('cutoff', CUTOFF), "marketSource": market["meta"]["source"],
                     "selectionNote": capture['discovery']['note'] if capture.get('discovery') else "每日在来源概念目录中，以涨幅分位×50% + 换手分位×50%选取前十；不是讨论前十，名单随行情轮动。",
                     "feedObserved": sum(not f.get("error") and f.get("pages", 0) > 0 for code, f in capture["feeds"].items() if code in all_codes), "feedExpected": len(all_codes), "errors": capture.get("errors", []),
                     "flowNote": "新浪板块日线 r0_net 主力口径；按元保存、亿元展示。它是订单分类统计，不是已确认机构账户；交叉板块不相加。"},
            "thermometers": thermo, "sectors": measured, "flows": {"coverage": flow_coverage, "rows": flows},
            "summary": f"当日 {market['market']['up']} 只上涨、{market['market']['down']} 只下跌，中位涨跌 {market['market']['medianChange']}%；当前热点为" + "、".join(r["name"] for r in measured[:3]) + "。"}


def build_report(root, capture=None, *, agent=False):
    root = Path(root)
    fresh_capture = capture is None
    market = read_json(root / "public/data/market/latest.json", {})
    if not market.get("boards"):
        raise RuntimeError("市场快照不可用，保留原报告")
    capture = collect_report(root, market) if capture is None else capture
    if not capture.get("stockFacts"):
        raw = read_json(root / "work/market-observations" / f"{capture['date']}.json", {})
        capture["stockFacts"] = []
        for row in raw.get("groups", {}).get("stocks", {}).get("rows", []):
            stamp = number(row.get("f124"))
            if stamp is not None and datetime.fromtimestamp(stamp, CN_TZ).date().isoformat() == capture["date"]:
                capture["stockFacts"].append({"code": row["f12"], "date": capture["date"], "amount": number(row.get("f6"))})
    report = assemble_report(market, capture)
    directory = root / "public/data/report"
    previous = read_json(directory / "latest.json", {})
    day = report["meta"]["tradeDate"]
    if previous.get("meta", {}).get("tradeDate", "") > day:
        raise RuntimeError("报告日期倒退，保留原报告")
    if not any(r["observation"]["sampleCount"] for r in report["sectors"]) and not report["flows"]["rows"]:
        raise RuntimeError("报告来源全部不可用，保留原报告")
    same_selection = [r["id"] for r in previous.get("sectors", [])] == [r["id"] for r in report["sectors"]]
    if previous.get("meta", {}).get("tradeDate") == day and same_selection and (len(previous.get("flows", {}).get("rows", [])) > len(report["flows"]["rows"]) or previous["meta"].get("feedObserved", 0) > report["meta"]["feedObserved"] or sum(r["score"] is not None for r in previous.get("thermometers", [])) > sum(r["score"] is not None for r in report["thermometers"])):
        raise RuntimeError("同日报告覆盖退化，保留已有报告")
    if previous and previous.get("meta", {}).get("tradeDate") == day and previous.get("meta", {}).get("analysisVersion") != report['meta']['analysisVersion']:
        old_version = previous["meta"].get("analysisVersion", "daily-report-1.0")
        archive_path = directory / "archive" / old_version / f"{day}.json"
        if not archive_path.exists():
            atomic_json(archive_path, previous)
    atomic_json(root / "work/report-observations" / f"{day}.json", capture)
    if fresh_capture or agent:
        from .market_reading import analyze_report
        try:
            print("本地复盘统计已完成；正在读取汇总解读缓存，必要时调用一次模型（不逐条分析评论）。", flush=True)
            report["llmReading"] = analyze_report(root, report)
            print(f"汇总解读：{report['llmReading']['status']}（不逐条标注评论）", flush=True)
        except Exception:
            report["llmReading"] = {"status": "error", "note": "汇总解读暂不可用，本地指标已保存"}
    atomic_json(directory / "daily" / f"{day}.json", report)
    atomic_json(directory / "index.json", {"dates": sorted(p.stem for p in (directory / "daily").glob("????-??-??.json"))})
    atomic_json(directory / "latest.json", report)
    return report
