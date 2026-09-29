from __future__ import annotations

import json
import argparse
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentiment.pipeline_v4 import build_snapshot  # noqa: E402
from sentiment.market_watch import build_market_snapshot  # noqa: E402
from sentiment.report import build_report  # noqa: E402
from sentiment.limit_pool import build_limit_snapshot  # noqa: E402
from sentiment.longform import build_longform_snapshot  # noqa: E402
from sentiment.run_progress import logged_run, stage_progress, say
from sentiment.semantic_agent import run_lock
from sentiment.collectors import CN_TZ  # noqa: E402
from sentiment.trading_calendar import UnsupportedCalendarYear, calendar_warning, effective_trade_date, previous_trading_day  # noqa: E402


def check_calendar(now=None) -> bool:
    """Stop once with a clear message rather than failing every step alike."""
    now = now or datetime.now(CN_TZ)
    warning = calendar_warning(now.date())
    if warning:
        say("提示：" + warning)
    try:
        effective_trade_date(now)
    except UnsupportedCalendarYear as exc:
        say(f"更新未启动：{exc}")
        return False
    return True


# Order matters: the report reads the market snapshot saved just before it,
# and the long-form report reads market, limit and report snapshots.
STEPS = (("market", "市场行情与板块", "public/data/market/latest.json"),
         ("limit", "涨停生态", "public/data/limit/latest.json"),
         ("community", "社区采集与本地分类", "public/data/latest.json"),
         ("report", "十强复盘与模型汇总解读", "public/data/report/latest.json"),
         ("longform", "复盘长图", "public/data/longform/latest.json"))
KEYS = tuple(key for key, _, _ in STEPS)
LAST_RUN = ROOT / "work/logs/last-run.json"


def stale_keys(now=None, root=ROOT) -> list[str]:
    """Modules whose latest snapshot is older than the most recent closed session."""
    day = effective_trade_date(now or datetime.now(CN_TZ)).isoformat()
    stale = []
    for key, _, path in STEPS:
        try:
            saved = json.loads((root / path).read_text(encoding="utf-8")).get("meta", {}).get("tradeDate", "")
        except (OSError, ValueError):
            saved = ""
        if saved < day:
            stale.append(key)
    # The long-form report is built from the others: rebuild it whenever any input is refreshed.
    if stale and "longform" not in stale:
        stale.append("longform")
    return stale


# Daily collection became automatic on this date; earlier gaps are known and not reported.
CONTINUITY_SINCE = "2026-09-28"
CONTINUITY_SESSIONS = 10
# A day counts as complete only when both the report and the long-form page were saved.
DAILY_FILES = ("public/data/report/daily/{}.json", "public/data/longform/daily/{}.json")


def missing_days(day: str, root=ROOT, sessions=CONTINUITY_SESSIONS, since=CONTINUITY_SINCE) -> list[str]:
    """Recent sessions (up to `day`) lacking a daily report; discussion data cannot be collected afterwards."""
    current, missing = date.fromisoformat(day), []
    for _ in range(sessions):
        if current.isoformat() < since:
            break
        if not all((root / pattern.format(current.isoformat())).exists() for pattern in DAILY_FILES):
            missing.append(current.isoformat())
        current = previous_trading_day(current)
    return sorted(missing)


def write_summary(summary: dict) -> None:
    """Machine-readable outcome for the scheduled task's notification."""
    LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps({**summary, "finishedAt": datetime.now(CN_TZ).isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")


def run_steps(only="all", keys=None, summary=None) -> int:
    summary = {} if summary is None else summary
    if not check_calendar():
        summary.update(status="not_started", reason="交易日历未包含当前年份")
        return 1
    failures = []
    started = time.monotonic()
    builders = {"market": build_market_snapshot, "limit": build_limit_snapshot, "community": build_snapshot,
                "report": build_report, "longform": build_longform_snapshot}
    wanted = keys if keys is not None else [key for key, _, _ in STEPS if only == "all" or key == only]
    steps = [(key, name, builders[key]) for key, name, _ in STEPS if key in wanted]
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
    summary.update(status="failed" if not succeeded and failures else "partial" if failures else "ok",
                   succeeded=succeeded, total=len(steps), failures=failures)
    if failures:
        print("部分更新失败；成功数据已保存，失败模块保留原结果：" + "；".join(failures), file=sys.stderr)
        return 1
    return 0


def main(argv=()) -> int:
    parser = argparse.ArgumentParser(description="手动更新，可按模块运行；每10秒显示当前步骤耗时。")
    parser.add_argument("--only", choices=("all",) + KEYS, default="all")
    parser.add_argument("--if-stale", action="store_true",
                        help="只更新快照早于最近已收盘交易日的模块；都已最新时直接结束（供计划任务使用）")
    args = parser.parse_args(argv)
    log_path = ROOT / "work/logs" / f"update-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    summary = {"log": str(log_path)}
    try:
        with logged_run(log_path):
            say(f"日志文件：{log_path}")
            keys = None
            if args.if_stale:
                try:
                    keys = [key for key in stale_keys() if args.only in ("all", key)]
                except UnsupportedCalendarYear as exc:
                    say(f"更新未启动：{exc}")
                    summary.update(status="not_started", reason="交易日历未包含当前年份")
                    return 1
                if not keys:
                    say("各模块快照已是最近已收盘交易日，无需更新。")
                    summary.update(status="skipped")
                    return 0
                say("需要更新：" + "、".join(name for key, name, _ in STEPS if key in keys))
            say("采集速度取决于数据源响应。可先查看已有看板；Ctrl+C可请求中止，正在等待的网络请求可能需要超时后退出。")
            try:
                with run_lock(ROOT / "work/update-lock"):
                    return run_steps(args.only, keys, summary)
            except KeyboardInterrupt:
                say("运行已中止；已保存数据保留。")
                summary.update(status="interrupted")
                return 130
            except RuntimeError:
                say("更新未启动：已有更新运行中或无法取得运行锁，请勿重复启动。")
                summary.update(status="not_started", reason="已有更新运行中")
                return 1
    finally:
        try:
            summary["tradeDate"] = effective_trade_date(datetime.now(CN_TZ)).isoformat()
        except UnsupportedCalendarYear:
            pass
        summary["calendarWarning"] = calendar_warning(datetime.now(CN_TZ).date())
        try:
            summary["missingDays"] = missing_days(summary["tradeDate"]) if summary.get("tradeDate") else []
        except (UnsupportedCalendarYear, ValueError):
            summary["missingDays"] = []
        if summary["missingDays"]:
            say(f"连续性提醒：近 {CONTINUITY_SESSIONS} 个交易日中缺少日报：{'、'.join(summary['missingDays'])}。讨论数据无法事后补采。")
        write_summary(summary)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
