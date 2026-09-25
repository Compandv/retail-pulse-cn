"""Conservative, experimental account-level behavior audit; no network calls.

Absence of a rule match is never evidence of absence of chasing.
"""
import re
import unicodedata
from collections import Counter, defaultdict

VERSION = "behavior-audit-0.1"
MINIMUM_JUDGED = 20
MINIMUM_COVERAGE = 80
REASONS = {
    "incomplete": "文本明确截断或缺失",
    "context": "条件、转述、历史或语境不明",
    "unmatched": "规则未覆盖，需人工复核",
    "conflict": "同一账户存在相反行为证据",
    "unsampled": "账户未进入分析样本",
}


def judge_text(text):
    """Return an auditable decision, never an investor identity or trade fact."""
    text = unicodedata.normalize("NFKC", text or "").strip()
    if not text or re.search(r"(?:…|\.\.\.|展开全文|点击查看全文)\s*$", text):
        return "unknown", "incomplete"
    # Abstain on mixed context rather than silently discarding inconvenient clauses.
    if re.search(r"如果|假如|要是|一旦|等到|除非|否则|昨天|昨日|前天|上周|去年|以前|有人|他说|她说|据说|转发|转载|[“”「」『』\"]|呵呵|才怪|笑死|难道", text):
        return "unknown", "context"
    from .following import classify
    # Preserve question marks on their own sentence so an earlier question
    # does not suppress a subsequent explicit statement of action.
    values = [classify(part)[0] for part in re.split(r"(?<=[?？])", text) if part.strip()]
    target = any(value["following"] or value["chase"] for value in values)
    # Only explicit statements, not generic neutral/factual sentiment, establish
    # a known non-target observation. Scope is sampled expressions, not people.
    non_target = bool(re.search(r"^(?:我|本人)?(?:今天|现在|暂时)?(?:不追高|不追涨|不跟买|不买|暂不操作|观望|先观望|继续观望|持币观望|空仓观望)[。.!！\s]*$", text))
    # Closed patterns for understandable questions: not an assertion of action.
    ordinary_question = bool(re.fullmatch(r"(?:今天|今日)?(?:成交额|成交量|换手率|市盈率)(?:是|有)?多少[?？。\s]*", text))
    chase_question = bool(re.fullmatch(r"(?:现在|今天)?(?:还能追吗|能不能追|能否追高|还能上车吗)[?？。\s]*", text))
    if target and re.search(r"不追|不买|没追|未追|没有追|别追|不要追|不跟", text):
        return "unknown", "conflict"
    if target:
        return "target", "本人明确跟随或追涨执行／计划"
    if non_target or ordinary_question or chase_question:
        return "non_target", "明确观望／不追买自述，或仅询问而未自述执行与计划"
    return "unknown", "unmatched"


def audit_accounts(posts, observed_accounts, sampling_ok, max_posts=3):
    accounts = defaultdict(dict)
    for post in sorted(posts, key=lambda p: (p["date"], p["id"]), reverse=True):
        if not post.get("author"):
            continue
        key = (post["source"], post["author"])
        normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", post["text"]))
        if len(accounts[key]) < max_posts and normalized not in accounts[key]:
            accounts[key][normalized] = judge_text(post["text"])
    targets = negatives = 0
    reasons = Counter()
    for entries in accounts.values():
        states = {state for state, _ in entries.values()}
        if "target" in states and "non_target" in states:
            reasons["conflict"] += 1
        elif "target" in states:
            targets += 1
        elif states == {"non_target"}:
            negatives += 1
        else:
            # A negative statement cannot resolve another ambiguous sampled post.
            why = {reason for state, reason in entries.values() if state == "unknown"}
            reasons[next(r for r in ("conflict", "incomplete", "context", "unmatched") if r in why)] += 1
    total = max(observed_accounts, len(accounts))
    reasons["unsampled"] = total - len(accounts)
    judged = targets + negatives
    coverage = 100 * judged / total if total else None
    conditional = 100 * targets / judged if judged else None
    missing = []
    if not sampling_ok:
        missing.append("来源覆盖或账户标识未达标")
    if judged < MINIMUM_JUDGED:
        missing.append(f"可判断账户不足{MINIMUM_JUDGED}个")
    if coverage is None or coverage < MINIMUM_COVERAGE:
        missing.append(f"判断覆盖不足{MINIMUM_COVERAGE}%")
    return {
        "version": VERSION, "status": "experimental", "observedAccounts": total,
        "targetAccounts": targets, "nonTargetAccounts": negatives,
        "judgedAccounts": judged, "unknownAccounts": total - judged,
        "coverage": round(coverage, 1) if coverage is not None else None,
        "conditionalRate": round(conditional, 1) if conditional is not None else None,
        "observedTargetRate": round(100 * targets / total, 1) if total else None,
        "score": round(conditional, 1) if not missing else None,
        "missing": missing,
        "unknownReasons": [{"key": key, "label": label, "count": reasons[key]} for key, label in REASONS.items()],
        "note": "试验规则，尚未完成人工准确率验证；比例仅描述采样账户的表达，不代表实际成交、投资水平或全板块人数。未知不算非目标；条件比例不能外推到全部账户。",
    }
