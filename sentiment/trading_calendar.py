"""A-share session calendar shared by every pipeline; see config/trading-calendar.json."""
from __future__ import annotations

import json
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path

from .collectors import CN_TZ

TRADING_CALENDAR = json.loads((Path(__file__).resolve().parents[1] / "config/trading-calendar.json").read_text(encoding="utf-8"))
HOLIDAYS = {date.fromisoformat(day) for day in TRADING_CALENDAR["holidays"]}
SUPPORTED_YEARS = frozenset(TRADING_CALENDAR["supportedYears"])
DATA_AVAILABLE_AFTER = clock_time.fromisoformat(TRADING_CALENDAR["availableAfter"])


class UnsupportedCalendarYear(ValueError):
    """Raised instead of guessing: an unlisted year's weekdays may be holidays."""


def is_trading_day(day: date) -> bool:
    if day.year not in SUPPORTED_YEARS:
        raise UnsupportedCalendarYear(
            f"交易日历未包含 {day.year} 年，无法判断 {day.isoformat()} 是否交易日。"
            f"请按交易所公布的休市安排，在 config/trading-calendar.json 的 holidays 中补充该年休市日，并把 {day.year} 加入 supportedYears。")
    return day.weekday() < 5 and day not in HOLIDAYS


def calendar_warning(today: date) -> str | None:
    """Early notice in December so the new year does not start with failed updates."""
    if today.month == 12 and today.year + 1 not in SUPPORTED_YEARS:
        return (f"交易日历尚未包含 {today.year + 1} 年：1 月 1 日起每日更新将停止并报错。"
                "交易所公布休市安排后，请补充 config/trading-calendar.json。")
    return None


def previous_trading_day(day: date) -> date:
    candidate = day - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def effective_trade_date(now: datetime) -> date:
    """Latest session whose close data should be available at `now`."""
    local = now.astimezone(CN_TZ)
    if is_trading_day(local.date()) and local.time() >= DATA_AVAILABLE_AFTER:
        return local.date()
    return previous_trading_day(local.date())
