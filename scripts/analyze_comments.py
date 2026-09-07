"""手动重用已采集文本进行 OpenAI 对照分析；不启动轮询。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.market_watch import read_json
from sentiment.semantic_agent import analyze_capture, evaluate_review, settings


def main():
    print("此入口仅用于旧版逐条模型标注调试；日常请运行run_daily.cmd（本地分类＋一次汇总解读）。", flush=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, help="使用指定私有采集快照；默认最近复盘交易日")
    parser.add_argument("--dry-run", action="store_true", help="仅统计新增/缓存，不调用API")
    parser.add_argument("--max-new", type=int, help="本次最多新增标注条数")
    parser.add_argument("--evaluate", type=Path, help="评估已经人工填写human字段的review JSON，不调用API")
    args = parser.parse_args()
    if args.evaluate:
        print(json.dumps(evaluate_review(read_json(args.evaluate, {})), ensure_ascii=False, indent=2))
        return 0
    options = settings(ROOT)
    if args.max_new is not None:
        if not 1 <= args.max_new <= 20000: parser.error("--max-new必须在1—20000之间")
        options["limit"] = args.max_new
    day = read_json(ROOT / "public/data/report/latest.json", {}).get("meta", {}).get("tradeDate")
    capture = read_json(args.capture or ROOT / "work/report-observations" / f"{day}.json", {})
    if not capture.get("date") or not capture.get("members"):
        parser.error("缺少采集快照，请先手动运行run_daily.cmd")
    print(f"准备分析：交易日 {capture['date']}；本次最多新增 {options['limit']} 条；" + ("仅检查缓存，不调用API" if args.dry_run else "读取缓存后调用已配置的模型，请等待"), flush=True)
    summary = analyze_capture(ROOT, capture, dry_run=args.dry_run, options=options)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
