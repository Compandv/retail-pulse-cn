"""Pure descriptive market facts from date-validated, unique stock observations.

No requests, invented limit-up rules, default neutral scores or predictions.
"""
from __future__ import annotations

import math
import statistics

VERSION = "market-diagnostics-1.0"


def finite(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def nonnegative(value):
    value = finite(value)
    return value if value is not None and value >= 0 else None


def build_market_diagnostics(rows, catalog):
    """Rows must have already passed normalize_row's date and close-time checks."""
    unique, conflicts = {}, set()
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if code in unique and unique[code] != row:
            conflicts.add(code)
        else:
            unique[code] = row
    usable = [r for code, r in unique.items() if code not in conflicts]
    dated = [r for r in usable if r.get("dateValid") is True]
    changes = [finite(r.get("changePct")) for r in dated]
    changes = [v for v in changes if v is not None]
    amounts = [nonnegative(r.get("amount")) for r in dated]
    amounts = [v for v in amounts if v is not None]
    turnovers = [nonnegative(r.get("turnover")) for r in dated]
    turnovers = [v for v in turnovers if v is not None]
    expected = nonnegative(catalog.get("expected"))
    expected = int(expected) if expected is not None and expected.is_integer() else None
    catalog_complete = bool(catalog.get("complete")) and expected is not None and expected > 0 and len(unique) == expected and not conflicts
    amount_complete = catalog_complete and len(amounts) == expected
    total_amount = sum(amounts) if amount_complete else None
    top_share = None
    if not amount_complete:
        concentration_reason = "证券目录或当日成交额不完整，不计算全范围集中度"
    elif total_amount == 0:
        concentration_reason = "完整成交额合计为零，集中度无定义"
    elif len(amounts) < 10:
        concentration_reason = "不足10只股票，不计算前10股集中度"
    else:
        top_share = round(100 * sum(sorted(amounts, reverse=True)[:10]) / total_amount, 2)
        concentration_reason = "前10只股票成交额之和 / 同来源完整A股成交额；按股票去重，不叠加交叉板块"
    count = len(changes)
    bands = [
        ("strongUp", "涨幅 ≥5%", sum(v >= 5 for v in changes)),
        ("up", "0% < 涨幅 <5%", sum(0 < v < 5 for v in changes)),
        ("flat", "平盘", sum(v == 0 for v in changes)),
        ("down", "−5% < 涨幅 <0%", sum(-5 < v < 0 for v in changes)),
        ("strongDown", "跌幅 ≥5%", sum(v <= -5 for v in changes)),
    ]
    return {
        "version": VERSION, "sourceTotal": expected, "observed": len(unique),
        "catalogComplete": catalog_complete, "conflictingCodes": len(conflicts),
        "changeCoverage": count, "turnoverCoverage": len(turnovers),
        "amountCoverage": len(amounts), "amountComplete": amount_complete,
        "netAdvanceShare": round(100 * (sum(v > 0 for v in changes) - sum(v < 0 for v in changes)) / count, 2) if count else None,
        "medianTurnover": round(statistics.median(turnovers), 2) if turnovers else None,
        "distribution": [{"key": key, "name": name, "count": n if count else None, "share": round(100 * n / count, 2) if count else None} for key, name, n in bands],
        "top10AmountShare": top_share, "concentrationReason": concentration_reason,
        "note": "纯行情描述，不参与韭菜分。涨跌分布的分母仅为有当日有效涨跌幅的股票；5%是描述阈值，不是涨跌停认定。",
    }
