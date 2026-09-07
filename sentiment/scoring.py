"""Versioned, transparent 0–100 scoring shared with the online query contract."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

from .models import AnalyzedPost

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/scoring.json").read_text(encoding="utf-8"))
METHOD_VERSION = CONFIG["version"]
METRICS = ("overall", "direction", "novice", "fomo", "panic", "heat", "intensity")


def rounded(value: float) -> float:
    # Match JavaScript Math.round, including negative half steps.
    return math.floor(value * 10 + 0.5) / 10


def score_source(posts: list[AnalyzedPost]) -> dict[str, Any]:
    if not posts:
        return {**{key: None for key in METRICS}, "sampleCount": 0}
    metrics: dict[str, Any] = {}
    for key in ("novice", "fomo", "panic"):
        values = [getattr(item.signals, key) for item in posts]
        share = sum(value >= CONFIG["signalThreshold"] for value in values) / len(values)
        metrics[key] = 100 * (CONFIG["prevalenceWeight"] * share + (1 - CONFIG["prevalenceWeight"]) * statistics.fmean(values))
    metrics["direction"] = statistics.fmean(item.signals.direction for item in posts) * 100
    metrics["intensity"] = abs(metrics["direction"])
    metrics["heat"] = min(100, math.log1p(len(posts)) / math.log1p(CONFIG["heatReference"]) * 100)
    metrics = {key: rounded(value) for key, value in metrics.items()}
    metrics["overall"] = rounded(sum(metrics[key] * weight for key, weight in CONFIG["weights"].items()))
    return {**metrics, "sampleCount": len(posts)}


def aggregate_scores(posts: Iterable[AnalyzedPost], expected_sources: Iterable[str]) -> dict[str, Any]:
    items = list(posts)
    sources = [score_source([item for item in items if item.post.source == source]) for source in expected_sources]
    available = [row for row in sources if row["sampleCount"]]
    if not available:
        return {key: None for key in METRICS}
    result = {key: rounded(statistics.fmean(row[key] for row in available)) for key in METRICS if key != "overall"}
    result["overall"] = rounded(sum(result[key] * weight for key, weight in CONFIG["weights"].items()))
    return result


def contributions(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, "label": CONFIG["labels"][key], "weight": weight, "value": metrics.get(key),
             "points": rounded(metrics[key] * weight) if metrics.get(key) is not None else None}
            for key, weight in CONFIG["weights"].items()]


def expression_evidence(item: AnalyzedPost) -> dict[str, Any]:
    signals = item.signals
    axes = [{"key": key, "label": CONFIG["labels"][key], "value": rounded(getattr(signals, key) * 100),
             "matched": [word for word in signals.matched if word in CONFIG["lexicons"][key]]}
            for key in ("novice", "fomo", "panic")]
    axes.append({"key": "direction", "label": "看多方向" if signals.direction >= 0 else "看空方向", "value": rounded(abs(signals.direction) * 100),
                 "matched": [word for word in signals.matched if word in CONFIG["lexicons"]["bullish"] or word in CONFIG["lexicons"]["bearish"]]})
    strongest = max(axes, key=lambda row: row["value"])
    matched = "、".join(signals.matched[:6])
    reason = f"命中“{matched}”，以{strongest['label']}信号为主。" if matched else "未命中明显情绪关键词；问句和标点可能产生少量结构信号。"
    return {"score": rounded(max(signals.novice, signals.fomo, signals.panic, abs(signals.direction)) * 100),
            "reasoning": reason + "这是文本表达的规则解释，不判断作者真实身份。", "evidence": axes}
