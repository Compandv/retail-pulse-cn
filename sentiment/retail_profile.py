"""Auditable expression tiers, one vote per observed account, with abstention."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import unicodedata

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/retail-profile.json").read_text(encoding="utf-8"))
VERSION = CONFIG["version"]


def hit(pattern, text):
    return re.search(pattern, text, re.I) is not None


def expression_tier(text):
    text = unicodedata.normalize("NFKC", text).strip()
    # A quoted example or headline is not evidence about its author's expertise.
    if hit(r"转发|转载|新闻摘要|原文|老师说|博主说|有人说|有人问|有人喊|他们说|所谓|[“”「」]|难道|凭什么|谁说", text):
        return None, "引用、转述或反问，不能据此分层"
    financial = hit(r"净利润|营收|毛利|现金流|市盈率|市净率|股息率|分红率|扣非|资产负债|估值|负债率|出栏|头均成本", text)
    evidence = hit(r"\d+(?:\.\d+)?\s*(?:%|亿|万|元|倍)|财报|公告显示|数据显示|年报|季报|中报|同比|环比|相比|对比", text)
    reasoning = hit(r"因为|所以|因此|意味着|导致|带来|受益|影响|传导|推升|压低|推动|压缩|提升|改善|支撑|低估|高估|贵了|便宜|低于|高于|取决于|使得|但|不过|风险|如果|需要|才能|仍需|难以", text)
    policy_chain = hit(r"十五五|十四五|国家政策|政策支持|补贴|规划|产业链|上下游|上游|下游|订单|产能|供需|涨价传导|成本传导", text)
    macro = hit(r"美联储|美国加息|美国降息|美债|美元|汇率|地缘|海外|全球|关税|外围|国际油价|通胀", text)
    risk = hit(r"如果|若|一旦|情景|假设|失效|风险|不及预期|敏感|回撤|但|否则|未必", text)
    causal_count = len(re.findall(r"导致|影响|传导|推升|压低|推动|压缩|提升|改善|支撑|带来|因此|从而|使得", text))
    technical = hit(r"均线|日线|量能|放量|缩量|筹码|托单|缺口|金叉|死叉|K线|支撑|压力位|连板|炸板|洗盘|建仓|出货|吸筹|收割|避雷针|通道|低吸", text)
    if macro and (financial or policy_chain) and evidence and risk and causal_count >= 2:
        return "L5", "宏观因素与企业／产业关联，有论据、传导链及风险条件"
    if policy_chain and reasoning and (financial or evidence) and causal_count >= 1:
        return "L4", "政策／产业链与经营结果相联系，并给出论据和传导判断"
    if financial and evidence and reasoning:
        return "L3", "企业数据或估值证据与自主判断相联系"
    if technical and evidence and hit(r"止损|失效|若.*跌破|如果.*跌破|仓位.*不超过", text) and reasoning:
        return "L3", "量价论据与明确的风险／失效条件相联系"
    if hit(r"我是(?:一个)?(?:小白|新手)|刚开户|第一次(?:炒股|买股|入市)", text) and not hit(r"不是小白|不是新手|别说我是|不要说我是", text):
        return "L1", "本人明确自述入门阶段；不等于已经追买"
    # Do not demote analytical but insufficiently evidenced text into novice tiers.
    if financial or macro or (policy_chain and reasoning):
        return None, "有分析主题，但论据或推理不足以稳定分层"
    if not technical and hit(r"(?:我(?:是|才是)|本人是|作为一个).{0,3}(?:小白|新手)|刚开户|第一次(?:买股|炒股|入市)|(?:还能|能不能|可以|现在能|要不要|能否|可不可以).{0,4}(?:追|上车|买入|进场)|怎么买股票|怎么下单|(?:问|请教).{0,8}(?:大神|股神)|梭哈|猛干|不懂.{0,6}(?:买|梭哈)|不管.{0,6}(?:先买|梭哈)|跟着.{0,5}(?:老师|大佬).{0,5}(?:买|冲)|买在最高点.*听天由命", text) and not hit(r"别追|不要追|不能追|不是小白|不是新手|别问|不要问|别梭哈|不梭哈|不要梭哈", text):
        return "L1", "基础求助或缺乏分析的跟随表达；询问本身不等于已追买"
    if (technical or hit(r"涨停潮|主力.{0,8}(?:拉升|控盘|护盘|吃|玩)|资金.{0,8}(?:拉升|回流|出逃)", text)) and not hit(r"吗|[?]|未必|不代表|不一定", text):
        return "L2", "使用资金／技术叙事，但未提供可核对的完整分析链"
    return None, "普通讨论或证据不足，保留未知"


def refine_behavior(post):
    """Only for report v2; legacy observations keep their original method version."""
    text = unicodedata.normalize("NFKC", post["text"])
    chase = panic = refill = False
    for clause in re.split(r"[，,。；;！!\n]", text):
        quoted = hit(r"主力|庄家|有人|他们|你们|散户都|老师说|博主说|转发|[“”「」]", clause)
        question = hit(r"[?？]|(?:吗|么)$|能不能|要不要|该不该|能否|是否", clause)
        refusal = hit(r"不敢|不要|别追|不追|不能|不想|不再|没买|没有|未买|没补|不补|没敢|未补|不会", clause)
        historical = hit(r"昨天|昨日|前天|上周|去年|当年", clause)
        own = hit(r"我|本人|买了|买入了|追了|追高了|追进了|打板了|上车了|已买|已追|刚买|准备|打算|我要|决定", clause)
        warning = hit(r"发套|被套|接盘|慎|危险|别|不要", clause) and not own
        if not (quoted or question or refusal or historical or warning):
            chase_word = hit(r"追高|追涨|追进|追入|打板|扫板|抢筹|踏空|赶紧.*(?:买|上车)|忍不住.*买", clause)
            action = own or hit(r"今天.*(?:买入|追入|上车)|(?:追高|追涨|打板).*(?:买入|上车|进场)|明天.*(?:追|打板)|买少了|后悔没买|再不买", clause)
            chase = chase or (chase_word and action) or (own and hit(r"买|上车|加仓", clause) and hit(r"涨停|大涨|新高|拉升|涨了", text))
            panic = panic or hit(r"亏麻|亏惨|血亏|救命|心态崩|不玩了|割肉了|我.{0,8}(?:割肉|深套|套牢)|(?:已经|今天|刚).{0,5}割肉", clause)
            refill = refill or (hit(r"补(?:了|过|点|个|一笔|了点)?仓|摊低成本", clause) and (own or hit(r"今天补|补了仓|补仓了|早盘.*补仓|尾盘.*补仓", clause)) and not hit(r"没到|差几分|机会|如果|假如|等到|一旦|距离", clause))
    classification = {**post["classification"], "chase": chase, "panic": panic}
    classification["intentLabel"] = "追买自述／意愿" if chase else "恐慌表达" if panic else "补仓表达" if refill else "一般讨论／待辨语境"
    return {**post, "classification": classification, "refillExpression": refill}


def account_profile(posts, observed_authors, sampling_ok, classifier=None):
    grouped = defaultdict(list)
    for post in posts:
        if post.get("author"):
            grouped[(post["source"], post["author"])].append(post)
    counts = Counter(); examples = defaultdict(list)
    single = conflicts = 0
    for entries in grouped.values():
        votes = []; seen = set()
        for entry in entries[:3]:
            normalized = re.sub(r"\s+", "", entry["text"])
            if normalized in seen:
                continue
            seen.add(normalized)
            level, reason = classifier(entry) if classifier else expression_tier(entry["text"])
            if level:
                votes.append((level, reason, entry))
        if not votes:
            continue
        distribution = Counter(v[0] for v in votes)
        winner, count = distribution.most_common(1)[0]
        if count / len(votes) <= .5 or max(int(v[0][1]) for v in votes) - min(int(v[0][1]) for v in votes) >= 2:
            conflicts += 1
            continue
        counts[winner] += 1
        single += len(votes) == 1
        if len(examples[winner]) < 3:
            _, reason, entry = next(v for v in votes if v[0] == winner)
            examples[winner].append({"text": entry["text"], "url": entry["url"], "date": entry["date"], "reason": reason, "supportingPosts": count})
    classified = sum(counts.values())
    total = max(observed_authors, len(grouped))
    unknown = total - classified
    coverage = 100 * classified / total if total else 0
    enough = sampling_ok and classified >= CONFIG["minimumClassifiedAccounts"]
    low = counts["L1"] + counts["L2"]
    return {"version": VERSION, "observedAccounts": total, "classifiedAccounts": classified, "unknownAccounts": unknown,
            "coverage": round(coverage, 1), "singleEvidenceAccounts": single, "conflictingAccounts": conflicts,
            "eligible": enough, "pointEligible": enough and classified / total >= CONFIG["minimumPointCoverage"],
            "l1l2Share": round(100 * low / classified, 1) if enough else None,
            "l1l2Bounds": [round(100 * low / total, 1), round(100 * (low + unknown) / total, 1)] if total else None,
            "levels": [{"key": key, "label": label, "count": counts[key], "share": round(100 * counts[key] / classified, 1) if classified else None,
                        "examples": examples[key]} for key, label in CONFIG["labels"].items()],
            "reason": "采样不足" if not sampling_ok else "可判定账户不足20个" if not enough else "分类覆盖不足50%，只显示区间" if coverage < 50 else "样本试验估计；非真实身份或经验认证"}


def leek_score(profile, inputs):
    weights = CONFIG["weights"]
    parts = {"l1l2": profile["l1l2Share"], **inputs}
    required = [key for key, weight in weights.items() if weight > 0]
    missing = [key for key in required if parts.get(key) is None]
    result = {"score": None, "range": None, "weights": weights, "inputs": parts, "missing": missing, "reason": profile["reason"]}
    if missing or not profile["eligible"]:
        result["reason"] = "缺少可比输入：" + "、".join(missing) if missing else profile["reason"]
        return result
    other = sum(weights[key] * parts[key] for key in required if key != "l1l2")
    result["range"] = [round(other + weights["l1l2"] * bound, 1) for bound in profile["l1l2Bounds"]]
    if profile["pointEligible"]:
        result["score"] = round(other + weights["l1l2"] * parts["l1l2"], 1)
    return result
