from __future__ import annotations

import math
from collections import Counter
from typing import Mapping

from .models import AnalyzedPost, Post, Signals

from .scoring import CONFIG

NOVICE = CONFIG["lexicons"]["novice"]
FOMO = CONFIG["lexicons"]["fomo"]
PANIC = CONFIG["lexicons"]["panic"]
BULLISH = CONFIG["lexicons"]["bullish"]
BEARISH = CONFIG["lexicons"]["bearish"]
SPAM_PATTERNS = CONFIG["spam"]
PROSE_PATTERNS = CONFIG["prose"]

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


def _saturate(raw: float, scale: float = CONFIG["saturationScale"]) -> float:
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
