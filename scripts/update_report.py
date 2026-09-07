"""Collect the daily report, or replay its private capture without network calls."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sentiment.market_watch import read_json  # noqa: E402
from sentiment.report import build_report  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--agent", action="store_true", help="回放已有快照时也生成一次模型汇总解读；正常采集默认执行")
    parser.add_argument("--enrich-profiles", action="store_true", help="核对原帖正文用于表达分层；保留原始历史互动")
    args = parser.parse_args()
    try:
        capture = read_json(args.capture, {}) if args.capture else None
        if args.enrich_profiles and capture:
            from sentiment.profile_texts import enrich_profiles
            capture = enrich_profiles(ROOT, capture)
        result = build_report(ROOT, capture, agent=args.agent)
        print(f"复盘已更新：{result['meta']['tradeDate']}，{len(result['sectors'])} 个热点，{len(result['flows']['rows'])} 个板块资金记录")
        return 0
    except Exception as exc:
        print(f"复盘更新失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
