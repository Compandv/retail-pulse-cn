"""Best-effort public quote data used to enrich the sentiment dashboard.

The project intentionally keeps sentiment collection independent from quote
collection.  Quote endpoints are optional: a rate limit or an upstream schema
change must not prevent a sentiment snapshot from being written.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Mapping

from .collectors import request_text


def _float(value: object) -> float | None:
    try:
        if value in (None, "", "-", "--"):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def quote_symbol(target: Mapping[str, Any]) -> str:
    configured = str(target.get("quoteSymbol") or "").strip()
    if configured:
        return configured
    code = str(target.get("stockCode") or "")
    if code.startswith(("5", "6", "9")):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def _parse_tencent_quotes(payload: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r'v_([a-z0-9]+)="([^"]*)"', payload, flags=re.I):
        symbol, raw = match.groups()
        fields = raw.split("~")
        if len(fields) < 33:
            continue
        code = fields[2].strip()
        price = _float(fields[3])
        previous_close = _float(fields[4])
        change = _float(fields[31])
        change_pct = _float(fields[32])
        if change_pct is None and price is not None and previous_close not in (None, 0):
            change_pct = (price / previous_close - 1) * 100
        result[code] = {
            "symbol": symbol,
            "name": fields[1].strip(),
            "price": price,
            "previousClose": previous_close,
            "priceChange": change_pct,
            "priceChangeAmount": change,
            "asOf": fields[30].strip() if len(fields) > 30 else "",
            "source": "腾讯行情公开报价",
        }
    return result


def _eastmoney_secid(target: Mapping[str, Any]) -> str | None:
    code = str(target.get("stockCode") or "")
    if not code:
        return None
    configured_symbol = str(target.get("quoteSymbol") or "").lower()
    prefix = "1" if configured_symbol.startswith("sh") or code.startswith(("5", "6", "9")) else "0"
    return f"{prefix}.{code}"


def _fetch_daily_quote(target: Mapping[str, Any], trade_date: date) -> dict[str, Any]:
    secid = _eastmoney_secid(target)
    if not secid:
        return {}
    day = trade_date.strftime("%Y%m%d")
    params = urllib.parse.urlencode({
        "secid": secid,
        "klt": 101,
        "fqt": 1,
        "beg": day,
        "end": day,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    })
    try:
        payload = json.loads(request_text("https://push2his.eastmoney.com/api/qt/stock/kline/get?" + params, "https://quote.eastmoney.com/", timeout=12, attempts=2))
        data = payload.get("data") if isinstance(payload, dict) else None
        klines = data.get("klines") if isinstance(data, dict) else None
        fields = str(klines[-1]).split(",") if isinstance(klines, list) and klines else []
        if len(fields) < 10 or fields[0] != trade_date.isoformat():
            return {}
        return {
            "price": _float(fields[2]),
            "priceChange": _float(fields[8]),
            "priceChangeAmount": _float(fields[9]),
            "turnover": _float(fields[10]) if len(fields) > 10 else None,
            "asOf": fields[0],
            "source": "东方财富历史日线（代表标的）",
        }
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _fetch_flow(target: Mapping[str, Any], trade_date: date) -> tuple[str, dict[str, Any]]:
    target_id = str(target.get("id") or "")
    if target_id == "market":
        return target_id, {}
    secid = _eastmoney_secid(target)
    if not secid:
        return target_id, {}
    # The daily flow endpoint is more stable than the quote payload's nested
    # f178 field and gives us a compact, date-labelled history.
    day_params = urllib.parse.urlencode({
        "lmt": 0,
        "klt": 101,
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62",
    })
    try:
        payload = json.loads(request_text("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?" + day_params, "https://quote.eastmoney.com/", timeout=12, attempts=2))
        data = payload.get("data") if isinstance(payload, dict) else None
        klines = data.get("klines") if isinstance(data, dict) else None
        history: list[dict[str, Any]] = []
        for line in klines if isinstance(klines, list) else []:
            fields = str(line).split(",")
            if len(fields) < 2:
                continue
            amount = _float(fields[1])
            if amount is not None:
                history.append({"date": fields[0], "mainNetAmt": amount})
        history = [row for row in history if str(row.get("date", "")) <= trade_date.isoformat()]
        amounts = [_float(row.get("mainNetAmt")) for row in reversed(history)]
        amounts = [amount for amount in amounts if amount is not None]
        flow_1d = amounts[0] / 100_000_000 if amounts else None
        flow_5d = sum(amounts[:5]) / 100_000_000 if amounts else None
        return target_id, {
            "flowNet": round(flow_1d, 2) if flow_1d is not None else None,
            "flow5d": round(flow_5d, 2) if flow_5d is not None else None,
            "flowRatio": None,
            "flowHistory": list(reversed(history[-5:])),
            "flowSource": "东方财富日线主力净流入（代表标的）",
        }
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        # Keep a fallback for deployments where push2his is unavailable.
        try:
            params = urllib.parse.urlencode({"secid": secid, "fields": "f43,f57,f58,f60,f169,f170,f173,f178,f184"})
            payload = json.loads(request_text("https://push2.eastmoney.com/api/qt/stock/get?" + params, "https://quote.eastmoney.com/", timeout=10, attempts=2))
            data = payload.get("data") if isinstance(payload, dict) else None
            raw_history = data.get("f178") if isinstance(data, dict) else None
            if isinstance(raw_history, str):
                raw_history = json.loads(raw_history)
            history = [row for row in (raw_history if isinstance(raw_history, list) else []) if isinstance(row, dict) and str(row.get("date", "")) <= trade_date.isoformat()]
            amounts = [_float(row.get("mainNetAmt")) for row in history]
            amounts = [amount for amount in amounts if amount is not None]
            return target_id, {
                "flowNet": round(amounts[0] / 100_000_000, 2) if amounts else None,
                "flow5d": round(sum(amounts[:5]) / 100_000_000, 2) if amounts else None,
                "flowRatio": _float(data.get("f184")) if isinstance(data, dict) else None,
                "flowHistory": history[:5],
                "flowSource": "东方财富主力净流入（代表标的）",
            }
        except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
            return target_id, {}


def _fetch_target_market_data(target: Mapping[str, Any], trade_date: date) -> tuple[str, dict[str, Any]]:
    target_id = str(target.get("id") or "")
    row = _fetch_daily_quote(target, trade_date)
    _, flow = _fetch_flow(target, trade_date)
    row.update(flow)
    return target_id, row


def fetch_market_data(targets: list[Mapping[str, Any]], trade_date: date) -> dict[str, dict[str, Any]]:
    """Fetch optional quote and flow fields keyed by configured target id."""
    if not targets:
        return {}
    symbols = [quote_symbol(target) for target in targets]
    quote_by_code: dict[str, dict[str, Any]] = {}
    query = ",".join(symbols)
    try:
        encoded = urllib.parse.quote(query, safe=",")
        payload = request_text("https://qt.gtimg.cn/q=" + encoded, "https://qt.gtimg.cn/", timeout=10, attempts=1)
        quote_by_code = _parse_tencent_quotes(payload)
    except (OSError, RuntimeError):
        quote_by_code = {}

    result: dict[str, dict[str, Any]] = {}
    for target in targets:
        target_id = str(target.get("id") or "")
        symbol = quote_symbol(target)
        code = str(target.get("stockCode") or "")
        row = dict(quote_by_code.get(code, {}))
        if not row:
            row = dict(next((value for value in quote_by_code.values() if value.get("symbol") == symbol), {}))
        # Real-time quotes are only valid if their timestamp belongs to the
        # snapshot's trade date.  Otherwise a historical close is fetched.
        if not str(row.get("asOf", "")).startswith(trade_date.strftime("%Y%m%d")):
            row = {}
        result[target_id] = row

    # Flow calls are deliberately bounded and isolated from sentiment calls.
    # Concurrent requests keep the daily job practical while each failure is
    # represented as missing optional data rather than a zero flow.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_fetch_target_market_data, target, trade_date) for target in targets]
        for future in as_completed(futures):
            target_id, row = future.result()
            if row:
                result.setdefault(target_id, {}).update(row)
    return result
