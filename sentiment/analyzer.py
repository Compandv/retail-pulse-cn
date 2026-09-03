from __future__ import annotations

import math
from collections import Counter
from typing import Mapping

from .models import AnalyzedPost, Post, Signals

NOVICE: Mapping[str, float] = {
    "小白": 3, "新手": 3, "新人": 2, "第一次": 2, "请教": 2, "求助": 2,
    "大佬": 1, "老师": 1, "能买吗": 3, "怎么买": 3, "怎么操作": 3,
    "该不该": 2, "要不要": 2, "可以吗": 1.5, "什么意思": 2, "求带": 2,
    "听说": 1.5, "朋友说": 2, "博主说": 2, "解套": 1.5, "成本多少": 1,
}
FOMO: Mapping[str, float] = {
    "上车": 2, "冲": 1, "梭哈": 3, "满仓": 2.5, "all in": 3, "起飞": 2,
    "暴涨": 2, "翻倍": 2.5, "稳赚": 3, "必涨": 3, "躺赚": 3, "踏空": 2,
    "错过": 2, "后悔没买": 3, "买少了": 2, "再不买": 2.5, "忍不住": 1.5,
}
PANIC: Mapping[str, float] = {
    "割肉": 3, "清仓": 2.5, "止损": 1.5, "不玩了": 2.5, "救命": 3,
    "完了": 2, "亏麻": 3, "亏惨": 2.5, "血亏": 3, "深套": 2.5,
    "套牢": 2, "崩盘": 3, "跌惨": 2.5, "跑了": 1.5, "心态崩": 3,
}
BULLISH: Mapping[str, float] = {
    "看多": 2, "看涨": 2, "上涨": 1, "大涨": 2, "涨停": 2.5, "起飞": 2,
    "突破": 1.5, "抄底": 1.5, "加仓": 1.5, "买入": 1, "牛市": 2,
    "利空出尽": 2.5, "黄金坑": 2.5, "反包": 2,
}
BEARISH: Mapping[str, float] = {
    "看空": 2, "看跌": 2, "下跌": 1, "大跌": 2, "跌停": 2.5, "崩盘": 3,
    "破位": 2, "割肉": 2, "清仓": 2, "卖出": 1, "熊市": 2, "出货": 2,
    "套牢": 1.5, "亏麻": 2.5, "跑路": 2,
}
SPAM_PATTERNS = (
    "开户链接", "扫码进群", "老师带单", "内部消息", "添加微信", "点击领取",
    "诊股", "荐股", "免费领取", "财富号",
)
PROSE_PATTERNS = ("证券研究报告", "风险提示如下", "投资评级", "目标价", "研报")


def _weighted_hits(text: str, lexicon: Mapping[str, float]) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []
    lowered = text.lower()
    for phrase, weight in lexicon.items():
        count = lowered.count(phrase.lower())
        if count:
            score += weight * min(count, 2)
            matched.append(phrase)
    return score, matched


def _saturate(raw: float, scale: float = 4.0) -> float:
    return 1.0 - math.exp(-max(0.0, raw) / scale)


def analyze_post(post: Post) -> AnalyzedPost | None:
    text = post.text.strip()
    if len(text) < 2 or len(text) > 700:
        return None
    if any(pattern in text for pattern in SPAM_PATTERNS):
        return None
    if sum(pattern in text for pattern in PROSE_PATTERNS) >= 2:
        return None

    novice_raw, novice_hits = _weighted_hits(text, NOVICE)
    fomo_raw, fomo_hits = _weighted_hits(text, FOMO)
    panic_raw, panic_hits = _weighted_hits(text, PANIC)
    bull_raw, bull_hits = _weighted_hits(text, BULLISH)
    bear_raw, bear_hits = _weighted_hits(text, BEARISH)

    if text.endswith(("吗", "呢", "？", "?")):
        novice_raw += 0.8
    punctuation = text.count("!") + text.count("！") + text.count("?") + text.count("？")
    if punctuation >= 3:
        emotional_boost = min(1.2, punctuation * 0.15)
        fomo_raw += emotional_boost if bull_raw >= bear_raw else 0
        panic_raw += emotional_boost if bear_raw > bull_raw else 0

    direction = math.tanh((bull_raw - bear_raw) / 3.5)
    matched = tuple(dict.fromkeys(novice_hits + fomo_hits + panic_hits + bull_hits + bear_hits))
    return AnalyzedPost(post, Signals(
        novice=_saturate(novice_raw),
        fomo=_saturate(fomo_raw),
        panic=_saturate(panic_raw),
        direction=direction,
        matched=matched,
    ))


def evidence_counts(posts: list[AnalyzedPost]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in posts:
        for phrase in item.signals.matched:
            counts[phrase] += 1
    return counts
