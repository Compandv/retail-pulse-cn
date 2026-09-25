"""Account-weighted observable expressions, not investor expertise."""
from collections import defaultdict
import re
import unicodedata
import json
from pathlib import Path

METHOD = json.loads((Path(__file__).resolve().parents[1] / "config/following.json").read_text(encoding="utf-8"))
VERSION = METHOD["version"]
WEIGHTS = METHOD["weights"]
LABELS = METHOD["labels"]
if set(WEIGHTS) != {"following", "chase", "question", "hype"} or abs(sum(WEIGHTS.values()) - 1) > 1e-9:
    raise ValueError("跟风追涨权重配置无效")


def classify(text):
    text = unicodedata.normalize("NFKC", text).strip()
    result = {k: 0.0 for k in LABELS}
    evidence = {}
    def mark(key, clause, value=1.0):
        if value > result[key]: result[key] = value; evidence[key] = clause
    # Preserve quotation boundaries before splitting sentences.
    stripped = re.sub(r'[“「『"].*?[”」』"]', '', text)
    if stripped != text: mark("excluded", text)
    historical = False
    reported_context = False
    for clause in re.split(r"[，,。；;！!\n]", stripped):
        clause = clause.strip()
        if not clause: continue
        has = lambda p: re.search(p, clause) is not None
        if has(r"今天|刚刚|现在|这会|准备|打算|明天"): historical = False
        if has(r"昨天|昨日|前天|上周|去年|当年|以前|上个月"): historical = True
        own = has(r"我|本人|自己|准备|打算|决定|买了|买入了|追了|追进了|追高了|已买|已追|补了")
        question = has(r"[?？]|还能|能不能|能否|要不要|该不该|可以.{0,4}(?:买|追|上车)|吗$|么$")
        negated = has(r"不要|别追|别买|不敢|不追|不买|没买|未买|没有|没敢|不会|不想|不再|不准备|不打算|不是|并非|切勿|千万别")
        reported = has(r"有人|他说|她说|他们|你们|散户都|主力|庄家|转发|转载|新闻|老师说|博主说|据说|群里说")
        if has(r"^(?:但|不过|而)?(?:我|本人|自己)") and not reported: reported_context = False
        if reported: reported_context = True
        follow = has(r"(?:跟着|跟随).{0,8}(?:群|老师|大佬|博主|大家|别人).{0,8}(?:买|冲|上车)|(?:我|本人).{0,5}(?:跟买|跟着买|跟着冲|跟着上车)|(?:听|照着).{0,8}(?:推荐|老师|群).{0,6}(?:买|冲)")
        warning = has(r"发套|接盘|慎追|慎买|危险|不要|别追|别买|难道|谁说|笑死|呵呵|才怪|骗谁|讽刺")
        if historical or negated or warning or (reported_context and not follow):
            mark("excluded", clause)
            continue
        factual = has(r"\d+(?:\.\d+)?\s*(?:%|亿|万|元|倍)|财报|公告显示|数据显示")
        reason = has(r"因此|所以|因为|意味着|导致|但是|但|不过|如果|风险|低于|高于|传导|压缩|支撑")
        if factual and reason: mark("analysis", clause)
        if follow and not question: mark("following", clause)
        chase = has(r"追高|追涨|追进|追入|打板|扫板|还能追|上车")
        if question and chase: mark("question", clause)
        if not question and chase and own:
            done = has(r"(?:追高|追涨|追进|追入|打板|扫板|上车|买入|买).{0,3}了|已经.{0,6}(?:买|追|上车)|已买|已追|刚买")
            plan = has(r"准备|打算|决定|我要|我想|我会")
            # Boarding/buying alone is not proof of chasing a rise.
            context = has(r"追高|追涨|追进|追入|打板|扫板|涨了|大涨|涨停|新高")
            if context and (done or plan): mark("chase", clause, METHOD["chaseDoneStrength"] if done else METHOD["chasePlanStrength"])
        if not question and not (factual and reason) and has(r"无脑冲|无脑买|闭眼买|肯定翻倍|必定翻倍|必涨|稳赚|直接梭哈"):
            mark("hype", clause)
        if own and not question and has(r"割肉|亏麻|亏惨|心态崩|恐慌|不玩了"): mark("panic", clause)
        if own and not question and has(r"补了仓|补仓了|已经.{0,4}补仓|今天.{0,4}补仓") and not has(r"如果|假如|等到|一旦"): mark("refill", clause)
        if has(r"观望|先看看|暂不操作|等待确认"): mark("watch", clause)
    if not re.search(r"有人|他说|她说|转发|转载|新闻", stripped) and re.search(r"\d+(?:\.\d+)?\s*(?:%|亿|万|元|倍)|公告显示|财报显示", stripped) and re.search(r"因此|所以|因为|但|风险|导致|传导|压缩", stripped):
        mark("analysis", stripped)
    return result, evidence


def expression_profile(posts, observed_authors, sampling_ok):
    from .behavior_audit import audit_accounts
    accounts = defaultdict(dict); samples = {k: [] for k in LABELS}
    for post in sorted(posts, key=lambda p: (p["date"], p["id"]), reverse=True):
        if not post.get("author"): continue
        account = (post["source"], post["author"])
        if len(accounts[account]) >= METHOD["maxPostsPerAccount"]: continue
        normalized = re.sub(r"\s+", "", post["text"])
        if normalized in accounts[account]: continue
        values, evidence = classify(post["text"])
        accounts[account][normalized] = values
        for key in LABELS:
            if values[key] and len(samples[key]) < 3:
                samples[key].append({"text": post["text"], "evidence": evidence[key], "url": post.get("url", ""), "date": post["date"]})
    votes = [{key: max(v[key] for v in entries.values()) for key in LABELS} for entries in accounts.values()]
    total = max(observed_authors, len(votes))
    unknown = total - sum(any(v.values()) for v in votes)
    eligible = sampling_ok and total >= METHOD["minimumAccounts"]
    rates = {key: 100 * sum(v[key] for v in votes) / total if total else None for key in LABELS}
    return {"version": VERSION, "behaviorAudit": audit_accounts(posts, observed_authors, sampling_ok, METHOD["maxPostsPerAccount"]), "observedAccounts": total, "unknownAccounts": unknown, "unknownRate": round(100 * unknown / total, 1) if total else None,
            "sampledAccounts": len(votes),
            "unmatchedAccounts": sum(not any(v.values()) for v in votes),
            "unsampledAccounts": total - len(votes),
            "eligible": eligible, "labels": [{"key": key, "label": label, "count": sum(v[key] > 0 for v in votes), "rate": round(rates[key], 2) if rates[key] is not None else None, "examples": samples[key]} for key, label in LABELS.items()],
            "rates": rates, "reason": "本地规则识别的表达强度；未知仍计入分母，低分不等于理性，非实际成交或身份认证" if eligible else f"至少{METHOD['minimumAccounts']}个观察账户且来源覆盖达标才出分"}


def following_score(profile):
    inputs = {k: profile["rates"][k] for k in WEIGHTS}
    return {"score": round(sum(WEIGHTS[k] * inputs[k] for k in WEIGHTS), 1) if profile["eligible"] else None,
            "range": None, "weights": WEIGHTS, "inputs": inputs, "missing": [] if profile["eligible"] else ["有效账户／来源覆盖"], "reason": profile["reason"]}
