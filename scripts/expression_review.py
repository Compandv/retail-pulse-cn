"""Label check for the post judgments behind shake, rebound, the bull/bear balance and greed (chasing).

  sample    draw a stratified, blind sample from a saved report capture
  queue     after AI labels exist: the human spot-check queue (random subset + every AI-unsure item)
  evaluate  AI vs human agreement, then rules vs the reference labels (human where given, else confident AI)

Everything is written under work/expression-review/<date>/ (git-ignored, private). No network, no model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.market_watch import read_json  # noqa: E402
from sentiment.report import analyze_posts, rule_labels  # noqa: E402

VERSION = "expression-review-1.1"
FIELDS = ("panic", "greed", "direction", "rebound")
DIRECTIONS = ("bullish", "bearish", "both", "none")
# Binary targets scored for the rules; bullish/bearish come from the direction label.
TARGETS = {"panic": lambda l: l["panic"], "greed": lambda l: l["greed"], "rebound": lambda l: l["rebound"],
           "bullish": lambda l: l["direction"] in ("bullish", "both"), "bearish": lambda l: l["direction"] in ("bearish", "both")}


def folder(day: str) -> Path:
    return ROOT / "work/expression-review" / day


def stable(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def draw(posts: list[dict], day: str, size: int) -> tuple[list[dict], dict]:
    """Deduplicate texts, split by whether any rule fires, take up to half from each stratum."""
    unique = {}
    for post in posts:
        key = re.sub(r"\s+", "", post["text"])
        if key and key not in unique:
            unique[key] = post
    strata = {"rule_positive": [], "rule_negative": []}
    for post in unique.values():
        labels = rule_labels(post)
        fired = labels["panic"] or labels["greed"] or labels["rebound"] or labels["direction"] != "none"
        strata["rule_positive" if fired else "rule_negative"].append((post, labels))
    for rows in strata.values():
        rows.sort(key=lambda item: stable(f"{day}|{item[0]['text']}"))
    positive = strata["rule_positive"][:size // 2]
    negative = strata["rule_negative"][:size - len(positive)]
    chosen = [(p, l, "rule_positive") for p, l in positive] + [(p, l, "rule_negative") for p, l in negative]
    chosen.sort(key=lambda item: stable(f"order|{item[0]['id']}"))
    population = {name: len(rows) for name, rows in strata.items()}
    return chosen, population


def sample(day: str, size: int, spot: int) -> dict:
    capture = read_json(ROOT / "work/report-observations" / f"{day}.json", None)
    if not capture:
        raise SystemExit(f"没有 {day} 的复盘采集记录（work/report-observations）。")
    rows = [r for f in capture["feeds"].values() if f for r in f.get("rows", [])]
    _, posts, _, _ = analyze_posts(capture, rows, day)
    chosen, population = draw(posts, day, size)
    out = folder(day)
    out.mkdir(parents=True, exist_ok=True)
    blind = out / "sample-blind.jsonl"
    if blind.exists():
        raise SystemExit(f"{blind} 已存在；为避免覆盖已有标注，请先移走旧文件。")
    write_jsonl(blind, [{"id": p["id"], "date": p["date"], "code": p["code"], "text": p["text"], "url": p.get("url")} for p, _, _ in chosen])
    predictions = {p["id"]: {**labels, "stratum": stratum} for p, labels, stratum in chosen}
    sampled = {name: sum(s == name for _, _, s in chosen) for name in population}
    spot_ids = sorted(predictions, key=lambda i: stable(f"spot|{day}|{i}"))[:spot]
    meta = {"version": VERSION, "date": day, "analyzedPosts": len(posts), "population": population, "sampled": sampled,
            "strataRules": list(FIELDS),
            "spotCheck": spot_ids,
            "note": "去重文本按“规则是否命中”分层后各取一半；评估按层内总数加权还原，不是账户比例。"}
    (out / "rule-predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"folder": str(out), **{k: meta[k] for k in ("analyzedPosts", "population", "sampled")}}


def valid(label: dict) -> bool:
    return all(isinstance(label.get(f), bool) for f in ("panic", "greed", "rebound")) and label.get("direction") in DIRECTIONS


def queue(day: str) -> dict:
    out = folder(day)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    ai = {r["id"]: r for r in read_jsonl(out / "ai-labels.jsonl")}
    blind = read_jsonl(out / "sample-blind.jsonl")
    if len(ai) < len(blind):
        raise SystemExit(f"AI 标注只有 {len(ai)}/{len(blind)} 条，请先补齐 ai-labels.jsonl。")
    target = out / "review-queue.jsonl"
    if target.exists():
        raise SystemExit(f"{target} 已存在；为避免覆盖人工标注，请先移走旧文件。")
    wanted = set(meta["spotCheck"]) | {i for i, r in ai.items() if r.get("unsure") or not valid(r)}
    # Blind: no AI or rule labels, and the order does not reveal why an item was picked.
    rows = sorted((r for r in blind if r["id"] in wanted), key=lambda r: stable(f"queue|{r['id']}"))
    write_jsonl(target, rows)
    return {"queue": str(target), "items": len(rows), "spotCheck": len(meta["spotCheck"]),
            "aiUnsure": sum(bool(r.get("unsure")) for r in ai.values())}


def human_labels(row: dict) -> dict | None:
    """Fields the reviewer answered; a field marked unsure is left out."""
    label = {"panic": row.get("humanPanic"), "greed": row.get("humanGreed"), "direction": row.get("humanDirection"), "rebound": row.get("humanRebound")}
    return {k: v for k, v in label.items() if (isinstance(v, bool) if k != "direction" else v in DIRECTIONS)} or None


def evaluate(day: str) -> dict:
    out = folder(day)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    rules = json.loads((out / "rule-predictions.json").read_text(encoding="utf-8"))
    ai = {r["id"]: r for r in read_jsonl(out / "ai-labels.jsonl") if valid(r)}
    human = {r["id"]: h for r in read_jsonl(out / "review-queue.jsonl") if (h := human_labels(r))}

    agreement = {}
    for field in FIELDS:
        pairs = [(ai[i][field], h[field]) for i, h in human.items() if field in h and i in ai]
        agreement[field] = {"compared": len(pairs), "agree": sum(a == b for a, b in pairs),
                            "rate": round(100 * sum(a == b for a, b in pairs) / len(pairs), 1) if pairs else None}
    disagreements = [{"id": i, "field": f, "ai": ai[i][f], "human": h[f], "aiReason": ai[i].get("reason")}
                     for i, h in human.items() if i in ai for f in FIELDS if f in h and h[f] != ai[i][f]]

    # Reference: the human answer where given, else a confident AI label.
    reference = {}
    for i in rules:
        base = dict(ai[i]) if i in ai and not ai[i].get("unsure") else {}
        base.update(human.get(i, {}))
        if all(f in base for f in FIELDS):
            reference[i] = base
    weight = {s: meta["population"][s] / meta["sampled"][s] for s in meta["sampled"] if meta["sampled"][s]}
    scores = {}
    for name, truth in TARGETS.items():
        tp = fp = fn = 0.0
        for i, ref in reference.items():
            w = weight[rules[i]["stratum"]]
            predicted, actual = TARGETS[name](rules[i]), truth(ref)
            tp += w * (predicted and actual); fp += w * (predicted and not actual); fn += w * (actual and not predicted)
        scores[name] = {"precision": round(100 * tp / (tp + fp), 1) if tp + fp else None,
                        "recall": round(100 * tp / (tp + fn), 1) if tp + fn else None,
                        "estimatedShare": round(100 * (tp + fn) / sum(weight[rules[i]["stratum"]] for i in reference), 2) if reference else None}
    result = {"version": VERSION, "date": day, "humanReviewed": len(human), "aiLabeled": len(ai), "referenceItems": len(reference),
              "aiHumanAgreement": agreement, "rulesVsReference": scores, "disagreements": disagreements,
              "note": "一致率只在人工复核的条目上计算。规则的精确率、召回率按分层权重还原到全部去重文本；"
                      "参考标签以人工为准，其余用 AI 非存疑标签。AI 与人工一致率偏低时，规则评分只能参考人工部分。"}
    (out / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("sample", "queue", "evaluate"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--spot", type=int, default=80, help="random items every human review includes")
    args = parser.parse_args(argv)
    result = sample(args.date, args.size, args.spot) if args.action == "sample" else queue(args.date) if args.action == "queue" else evaluate(args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
