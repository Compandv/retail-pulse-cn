"""Evaluate independently reviewed JSONL; absent human labels are never gold."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.behavior_audit import judge_text, VERSION  # noqa: E402


def evaluate(rows):
    labels = ("target", "non_target", "unknown")
    matrix = {gold: {pred: 0 for pred in labels} for gold in labels}
    reviewed = skipped = 0
    seen = set()
    for row in rows:
        if row.get("humanLabel") is None:
            skipped += 1
            continue
        gold = row["humanLabel"]
        if gold not in labels:
            raise ValueError("humanLabel must be target, non_target or unknown")
        if not row.get("id") or row["id"] in seen:
            raise ValueError("Reviewed IDs must be present and unique")
        seen.add(row["id"])
        pred, _ = judge_text(row.get("verifiedBody") or row["text"])
        matrix[gold][pred] += 1
        reviewed += 1
    tp = matrix["target"]["target"]
    predicted = sum(matrix[gold]["target"] for gold in labels)
    actual = sum(matrix["target"].values())
    return {"version": VERSION, "reviewed": reviewed, "unreviewed": skipped,
            "targetPrecision": tp / predicted if predicted else None,
            "targetRecall": tp / actual if actual else None,
            "accuracy": sum(matrix[k][k] for k in labels) / reviewed if reviewed else None,
            "confusionMatrix": matrix,
            "note": "仅为人工标注样本上的文本分类表现，不是账户比例误差或市场预测准确率。未标注时不输出准确率；开发样本不能冒充独立测试集。"}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path, nargs="+",
                        help="one or more reviewed JSONL files; each is scored separately, e.g. a dev date and a held-out test date")
    args = parser.parse_args()
    results = {str(path): evaluate(read_rows(path)) for path in args.sample}
    print(json.dumps(results[str(args.sample[0])] if len(results) == 1 else results, ensure_ascii=False, indent=2))
