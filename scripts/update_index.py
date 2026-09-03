from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentiment.pipeline import build_snapshot  # noqa: E402


def main() -> int:
    try:
        snapshot = build_snapshot(ROOT)
    except Exception as exc:
        print(f"更新失败：{exc}", file=sys.stderr)
        return 1
    summary = snapshot["summary"]
    meta = snapshot["meta"]
    print(json.dumps({
        "状态": "更新成功", "交易日": meta["tradeDate"], "综合温度": summary["overall"], "情绪方向": summary["direction"],
        "有效样本": summary["sampleCount"], "来源覆盖": meta["coverage"], "置信等级": meta["confidence"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
