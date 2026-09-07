"""V4 context rules and observable proportions, shared with TypeScript via JSON."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/measurement.json").read_text(encoding="utf-8"))
LEGACY = json.loads((ROOT / "config/scoring.json").read_text(encoding="utf-8"))
METHOD_VERSION = CONFIG["version"]


def rounded(value):
    return math.floor(value * 10 + 0.5) / 10


def has(key, text):
    return re.search(CONFIG["patterns"][key], text, re.I) is not None


def matches(key, text):
    return list(re.finditer(CONFIG["patterns"][key], text, re.I))


def classify_text(text):
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
    if len(text) < 2 or len(text) > 2000 or re.search(CONFIG["spamPatterns"], text) or any(word in text for word in LEGACY["spam"]) or sum(word in text for word in LEGACY["prose"]) >= 2:
        return None
    evidence, intents = [], set()
    bullish = bearish = panic = False
    clauses = re.findall(CONFIG["patterns"]["clauses"], text) or [text]
    own_context = "，".join(clause for clause in clauses if not any(has(key, clause) for key in ("thirdParty", "rhetorical", "historical", "refusal")))
    for raw in clauses:
        clause = raw.strip()
        if not any(has(key, clause) for key in ("chase", "buy", "rising", "urgent", "panic", "bullish", "bearish")):
            continue
        if has("rhetorical", clause):
            intents.add("avoid")
            evidence.append(f"反问：{clause}")
            continue
        if has("historical", clause):
            intents.add("past")
            evidence.append(f"历史回顾：{clause}")
            continue
        if has("thirdParty", clause) and not has("following", clause):
            intents.add("quoted")
            evidence.append(f"他人观点：{clause}")
            continue
        if has("refusal", clause):
            intents.add("avoid")
            evidence.append(f"劝阻或观望：{clause}")
            continue
        def positive(key):
            return [m for m in matches(key, clause) if not has("negation", clause[max(0, m.start() - 8):m.start()])]
        chase, buy = bool(positive("chase")), bool(positive("buy"))
        rising = has("rising", own_context)
        urgent = has("urgent", clause) and (buy or rising)
        if chase or ((urgent or buy) and rising):
            if has("question", clause) and not has("reported", clause):
                intents.add("chase_question")
            elif has("reported", clause) and not re.search("如果|假如|打算|准备|明天|计划", clause):
                intents.add("reported_chase")
            else:
                intents.add("chase_intent")
            evidence.append(f"追涨语境：{clause}")
        elif urgent and buy:
            intents.add("aggressive_buy")
            evidence.append(f"激进买入，缺少追涨价格语境：{clause}")
        elif buy:
            intents.add("buy")
            evidence.append(f"买入表达：{clause}")
        elif has("wish", clause) and positive("rising"):
            intents.add("wish")
            evidence.append(f"看涨期待：{clause}")
        if positive("panic") and not (has("plan", clause) and has("condition", text)):
            panic = True
            evidence.append(f"恐慌表达：{clause}")
        bullish = bullish or bool(positive("bullish"))
        bearish = bearish or bool(positive("bearish"))
    order = ["reported_chase", "chase_intent", "chase_question", "aggressive_buy", "buy", "wish", "avoid", "past", "quoted"]
    intent = next((key for key in order if key in intents), "panic" if panic else "discussion")
    own = "，".join(clause for clause in clauses if not has("thirdParty", clause) and not has("rhetorical", clause))
    def own_has(key):
        return any(not has("negation", own[max(0, m.start() - 8):m.start()]) for m in matches(key, own))
    level = "unknown"
    if CONFIG.get("levelsEnabled", False) and own_has("basic"):
        level = "L1"
    elif CONFIG.get("levelsEnabled", False) and len(text) >= 70 and all(own_has(key) for key in ("research", "evidence", "comparison", "risk")):
        level = "L5"
    elif CONFIG.get("levelsEnabled", False) and len(text) >= 35 and own_has("scenario") and len(matches("risk", own)) >= 2 and own_has("condition"):
        level = "L4"
    elif CONFIG.get("levelsEnabled", False) and len(text) >= 20 and own_has("plan") and own_has("condition"):
        level = "L3"
    elif CONFIG.get("levelsEnabled", False) and has("following", text) and not has("refusal", text) and not has("rhetorical", text):
        level = "L2"
    if level != "unknown":
        evidence.append(f"表达类型：{CONFIG['levelLabels'][level]}（语境规则试验）")
    return {"intent": intent, "intentLabel": CONFIG["intentLabels"][intent], "level": level,
            "levelLabel": CONFIG["levelLabels"][level], "chase": intent in ("reported_chase", "chase_intent"),
            "reportedChase": intent == "reported_chase", "panic": panic, "bullish": bullish, "bearish": bearish,
            "evidence": list(dict.fromkeys(evidence))[:6],
            "reason": "按语境区分行动、期待、转述和否定；自述不等于已核实成交。" if evidence else "缺少足够的行动或类型证据，保留为一般讨论／无法判断。"}


def prepare_observations(rows, day, cutoff="23:59:59"):
    seen, authors, counts, analyzed = set(), set(), {}, []
    observed = unknown = excluded_date = noise = 0
    for row in sorted(rows, key=lambda row: (row["date"], row["source"], row["id"]), reverse=True):
        if row["date"][:10] != day or row["date"][11:19] > cutoff:
            excluded_date += 1
            continue
        classification = classify_text(row["text"])
        if classification is None:
            noise += 1
            continue
        identity = row["source"] + ":" + (row["author"] or "missing:" + row["id"]) + ":" + re.sub(r"\s+", "", row["text"].lower())
        if identity in seen:
            noise += 1
            continue
        seen.add(identity)
        observed += 1
        if row["author"]:
            authors.add(row["source"] + ":" + row["author"])
        else:
            unknown += 1
        key = row["source"] + ":" + (row["author"] or "missing:" + row["id"])
        count = counts.get(key, 0)
        counts[key] = count + 1
        if count < CONFIG["maxPostsPerAuthor"]:
            analyzed.append({**row, "classification": classification})
    return {"analyzed": analyzed, "observedPosts": observed, "observedAuthors": len(authors), "unknownAuthorPosts": unknown, "excludedDate": excluded_date, "excludedNoise": noise}


def summarize_expressions(posts):
    total = len(posts)
    def rate(n):
        return rounded(n / total * 100) if total else None
    def count(key):
        return sum(bool(post["classification"][key]) for post in posts)
    levels = [{"key": key, "label": label, "count": sum(p["classification"]["level"] == key for p in posts)} for key, label in CONFIG["levelLabels"].items()]
    intents = [{"key": key, "label": label, "count": sum(p["classification"]["intent"] == key for p in posts)} for key, label in CONFIG["intentLabels"].items()]
    for row in levels + intents:
        row["share"] = rate(row["count"])
    return {"sampleCount": total, **{key: rate(count(key)) for key in ("chase", "reportedChase", "panic", "bullish", "bearish")},
            "direction": rounded((count("bullish") - count("bearish")) / total * 100) if total else None,
            "intensity": rate(sum(p["classification"]["bullish"] or p["classification"]["bearish"] for p in posts)),
            "levels": levels, "intents": intents, "levelCoverage": rate(total - levels[-1]["count"]),
            "l1l2Share": rate(sum(row["count"] for row in levels if row["key"] in ("L1", "L2"))),
            "thin": total < CONFIG["minimumSemanticSamples"]}


def historical_percentile(value, history, day, universe, complete, cutoff):
    by_date = {row["date"]: row for row in history if row["date"] < day and row.get("complete") and row.get("universe") == universe and row.get("methodVersion") == METHOD_VERSION and row.get("recordType") == "measured" and row.get("cutoff") == cutoff and isinstance(row.get("value"), (float, int)) and math.isfinite(row["value"]) and row["value"] >= 0}
    past = [by_date[key] for key in sorted(by_date)][-CONFIG["baselineDays"]:]
    valid_value = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    reason = "当前采集覆盖不足" if not complete else "账户标识不足" if not valid_value else "历史基线不足" if len(past) < CONFIG["minimumBaselineDays"] else "窗口内无有效讨论" if value == 0 else "历史分位"
    ready = complete and valid_value and len(past) >= CONFIG["minimumBaselineDays"]
    score = (0 if value == 0 else rounded(100 * sum(1 if row["value"] < value else .5 if row["value"] == value else 0 for row in past) / len(past))) if ready else None
    recent = sorted(row["value"] for row in past[-20:])
    median = (recent[(len(recent)-1)//2] + recent[len(recent)//2]) / 2 if ready else None
    previous = past[-1] if complete and valid_value and past else None
    return {"score": score, "baselineDays": len(past), "minimumDays": CONFIG["minimumBaselineDays"], "reason": reason,
            "baselineMedian": median, "growthPct": rounded((value / median - 1) * 100) if median is not None and median > 0 else None,
            "abnormalAttention": math.floor(math.log((1 + value) / (1 + median)) * 1000 + .5) / 1000 if median is not None else None,
            "comparisonDate": previous["date"] if previous else None, "previousAuthors": previous["value"] if previous else None,
            "authorChange": value - previous["value"] if previous else None, "lowBase": median == 0}


def universe_key(codes, source="eastmoney"):
    return f"{CONFIG['scopeVersion']}:{source}:{','.join(sorted(set(codes)))}"
