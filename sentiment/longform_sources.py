"""History that can be fetched at any time (index closes, market margin balance).

Unlike the limit pools these sources keep years of history, so they are read
when a daily or weekly long-form report is built rather than stored daily.
"""
from __future__ import annotations

import json
import urllib.parse

from .collectors import request_text
from .market_watch import number

INDICES = (("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指"), ("sh000688", "科创50"))


def fetch_index_closes(count: int = 700, fetch=request_text) -> dict:
    """{symbol: {"name", "closes": {date: close}}}; a failed index is omitted."""
    result = {}
    for symbol, name in INDICES:
        try:
            query = urllib.parse.urlencode({"param": f"{symbol},day,,,{count},qfq"})
            data = json.loads(fetch("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + query, "https://gu.qq.com/", timeout=12, attempts=2))
            rows = data.get("data", {}).get(symbol, {})
            rows = rows.get("day") or rows.get("qfqday") or []
            closes = {row[0]: number(row[2]) for row in rows if isinstance(row, list) and len(row) >= 3 and number(row[2]) is not None}
            if closes:
                result[symbol] = {"name": name, "closes": closes}
        except Exception:
            continue
    return result


def fetch_margin(size: int = 600, fetch=request_text) -> dict:
    """{date: {"financing", "lending", "total", "netFinancing"}} in yuan; published T+1."""
    query = urllib.parse.urlencode({"reportName": "RPTA_RZRQ_LSHJ", "columns": "DIM_DATE,RZYE,RQYE,RZJME,RZRQYE", "sortColumns": "DIM_DATE",
                                    "sortTypes": -1, "pageNumber": 1, "pageSize": size, "source": "WEB", "client": "WEB"})
    try:
        payload = json.loads(fetch("https://datacenter-web.eastmoney.com/api/data/v1/get?" + query, "https://data.eastmoney.com/rzrq/", timeout=12, attempts=2))
    except Exception:
        return {}
    rows = (payload.get("result") or {}).get("data") or []
    return {str(row["DIM_DATE"])[:10]: {"financing": number(row.get("RZYE")), "lending": number(row.get("RQYE")),
                                        "total": number(row.get("RZRQYE")), "netFinancing": number(row.get("RZJME"))}
            for row in rows if isinstance(row, dict) and row.get("DIM_DATE")}


def change_pct(series: dict, start: str, end: str) -> float | None:
    """Close-to-close change between two dates present in `series`."""
    a, b = series.get(start), series.get(end)
    return round(100 * (b / a - 1), 2) if a and b is not None else None


def last_on_or_before(series: dict, day: str) -> tuple[str, float] | None:
    dates = [d for d in series if d <= day]
    return (max(dates), series[max(dates)]) if dates else None
