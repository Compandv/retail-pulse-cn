from __future__ import annotations

import json
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentiment.pipeline_v4 import build_snapshot  # noqa: E402
from sentiment.market_watch import build_market_snapshot  # noqa: E402
from sentiment.report import build_report  # noqa: E402
from sentiment.run_progress import logged_run, stage_progress, say
from sentiment.semantic_agent import run_lock


def run_steps(only="all") -> int:
    failures = []
    started = time.monotonic()
    steps = [(key, name, build) for key, name, build in (("market", "市场行情与板块", build_market_snapshot), ("community", "社区采集与本地分类", build_snapshot), ("report", "十强复盘与模型汇总解读", build_report)) if only == "all" or key == only]
    succeeded = 0
    # All three paths get an attempt; failure in one does not discard the others.
    for index, (key, name, build) in enumerate(steps, 1):
        try:
            with stage_progress(f"{index}/{len(steps)} {name}"):
                step_started = time.monotonic()
                result = build(ROOT)
            succeeded += 1
            say(f"步骤完成：{index}/{len(steps)} {name} · 耗时 {time.monotonic() - step_started:.1f} 秒")
            print(json.dumps({"模块": name, "状态": "已更新", "交易日": result["meta"]["tradeDate"]}, ensure_ascii=False), flush=True)
            if result.get("llmReading", {}).get("status") in ("error", "needs_key"):
                say("提示：本地指标已保存，模型解读未完成。" + result["llmReading"].get("note", ""))
        except Exception as exc:
            failures.append(f"{name}：{exc}")
            say(f"步骤失败：{name}；{exc}。继续尝试后续独立步骤。")
    say(f"运行结束：成功 {succeeded}/{len(steps)}，失败 {len(failures)}；总耗时 {time.monotonic() - started:.1f} 秒。")
    if failures:
        print("部分更新失败；成功数据已保存，失败模块保留原结果：" + "；".join(failures), file=sys.stderr)
        return 1
    return 0


def main(argv=()) -> int:
    parser = argparse.ArgumentParser(description="手动更新，可按模块运行；每10秒显示当前步骤耗时。")
    parser.add_argument("--only", choices=("all", "market", "community", "report"), default="all")
    args = parser.parse_args(argv)
    log_path = ROOT / "work/logs" / f"update-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    with logged_run(log_path):
        say(f"日志文件：{log_path}")
        say("采集速度取决于数据源响应。可先查看已有看板；Ctrl+C可请求中止，正在等待的网络请求可能需要超时后退出。")
        try:
            with run_lock(ROOT / "work/update-lock"):
                return run_steps(args.only)
        except KeyboardInterrupt:
            say("运行已中止；已保存数据保留。")
            return 130
        except RuntimeError:
            say("更新未启动：已有更新运行中或无法取得运行锁，请勿重复启动。")
            return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
