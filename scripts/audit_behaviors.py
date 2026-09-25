"""Offline trial report and deterministic, private human-review sample."""
import argparse
import hashlib
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.behavior_audit import judge_text  # noqa: E402
from sentiment.report import assemble_report  # noqa: E402
from sentiment.market_watch import read_json, atomic_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.sample_size <= 10000:
        parser.error("sample-size must be between 1 and 10000")
    capture = read_json(args.capture, {})
    day = capture.get("date", "")
    # Validate before using a capture date in a filesystem path.
    from datetime import date
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid capture date")
    market = read_json(ROOT / "public/data/market/daily" / f"{day}.json", {})
    print(f"离线回放 {day}，不联网、不调用模型、不覆盖公开快照。", flush=True)
    report = assemble_report(market, capture)
    directory = ROOT / "work/behavior-audit" / day
    atomic_json(directory / "report-preview.json", report)
    summary = [{"name": s["name"], "oldScore": s["leekScore"]["score"], **s["expressionProfile"]["behaviorAudit"]} for s in report["sectors"]]
    atomic_json(directory / "summary.json", summary)
    def display(value):
        return "—" if value is None else escape(str(value))
    table = "".join("<tr>" + "".join(f"<td>{display(value)}</td>" for value in (
        s["name"], s["oldScore"], s["targetAccounts"], s["judgedAccounts"], s["observedAccounts"],
        s["coverage"], s["score"], "；".join(s["missing"]))) + "</tr>" for s in summary)
    (directory / "comparison.html").write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>跟风追涨表达试验对照</title><style>body{font:16px system-ui;margin:32px;background:#f7f9fc;color:#182438}h1{font-size:26px}table{border-collapse:collapse;background:white;width:100%}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}th{background:#e4edf9}p{line-height:1.7}.scroll{overflow:auto}</style>'
        f'<h1>{escape(day)} · 跟风追涨表达试验对照</h1><p>基于已保存记录离线回放，未采集新数据。'
        '试验比例 = 目标账户 ÷ 可判断账户 × 100；条件为至少20个可判断账户、判断覆盖率80%且来源达标。'
        '目标是本人明确跟随或追涨执行／计划，不包含单纯询问与喊涨。阈值未经准确率校准。</p>'
        '<p>规则识别率不等于准确率；未知不算非目标。覆盖不足时留空，不能把少量可判断样本外推成全板块占比。旧分未替换。</p>'
        '<div class="scroll"><table><thead><tr><th>题材</th><th>旧分</th><th>目标账户</th><th>可判断账户</th><th>观察账户</th><th>判断覆盖%</th><th>试验比例%</th><th>未发布原因</th></tr></thead>'
        f'<tbody>{table}</tbody></table></div></html>', encoding="utf-8")
    # One review item per normalized text; hash ordering is deterministic and
    # does not preferentially select positive labels or high-interaction posts.
    candidates = {}
    for feed in capture["feeds"].values():
        for row in feed.get("rows", []):
            if not row.get("date", "").startswith(day) or not row.get("text"):
                continue
            import unicodedata
            text = unicodedata.normalize("NFKC", row["text"]).strip()
            key = hashlib.sha256("".join(text.split()).encode()).hexdigest()
            body = capture.get("profileBodies", {}).get(row["id"], {})
            verified = all(body.get(k) == row.get(k) and row.get(k) is not None for k in ("date", "code", "author"))
            body_text = body.get("text") if verified else None
            state, reason = judge_text(body_text or text)
            candidates.setdefault(key, {"id": key, "date": row["date"], "code": row.get("code"), "source": row.get("source"), "text": text,
                "verifiedBody": body_text, "url": row.get("url"), "suggestedLabel": state, "suggestedReason": reason,
                "humanLabel": None, "humanReason": None, "titleOnlyLabel": None, "withBodyLabel": None})
    selected = sorted(candidates, key=lambda k: hashlib.sha256((day + k).encode()).hexdigest())[:args.sample_size]
    directory.mkdir(parents=True, exist_ok=True)
    # Do not overwrite human work on repeated runs.
    review = directory / "review-sample-blind.jsonl"
    atomic_json(directory / "review-predictions.json", {key: {"label": candidates[key]["suggestedLabel"], "reason": candidates[key]["suggestedReason"]} for key in selected})
    if not review.exists():
        with review.open("x", encoding="utf-8") as stream:
            for key in selected:
                stream.write(json.dumps({k: v for k, v in candidates[key].items() if not k.startswith("suggested")}, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(directory), "candidateTexts": len(candidates), "reviewSample": str(review), "sectors": [{"name": s["name"], "coverage": s["coverage"], "conditionalRate": s["conditionalRate"], "score": s["score"]} for s in summary]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
