"""Bounded, date-labelled public observations for the V4 daily job."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
from .collectors import request_text, normalize_text, anonymous_author
from .measurement import CONFIG, rounded
from .market_data import quote_symbol

CUTOFF = "15:00:00"


def get_json(url):
    return json.loads(request_text(url, "https://guba.eastmoney.com/", timeout=8, attempts=1))


def collect_feed(code, day, max_pages=None):
    page_limit = max_pages or CONFIG["maxPages"]
    result = {"code": code, "rows": [], "rawCount": 0, "pages": 0, "maxPages": page_limit, "pageLimitReached": False, "complete": False, "reason": "已达分页上限，数量为已观察下限", "error": None}
    seen_pages, older_pages = set(), 0
    for page in range(1, page_limit + 1):
        params = urllib.parse.urlencode({"code": code, "sorttype": 1, "ps": CONFIG["pageSize"], "p": page, "from": "CommonBaPost", "deviceid": "2f7f40de-2fb0-4d84-8a31-111111111111", "version": 200, "product": "Guba", "plat": "Web"})
        try:
            payload = get_json("https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?" + params)
            rows = payload.get("re")
            if not isinstance(rows, list):
                raise RuntimeError("帖子列表结构异常")
            rows = [row for row in rows if isinstance(row, dict)]
            result["pages"] += 1
            page_key = "|".join(str(row.get("post_id") or row.get("post_title")) for row in rows)
            if rows and page_key in seen_pages:
                result["reason"] = "列表重复返回，覆盖未确认"
                break
            seen_pages.add(page_key)
            result["rawCount"] += len(rows)
            for row in rows:
                if str(row.get("stockbar_code")) != code or int(row.get("post_type") or 0) != 0 or row.get("institution"):
                    continue
                accreditation = (row.get("user_extendinfos") or {}).get("user_accreditinfos")
                if accreditation not in (None, "", "[]", []):
                    continue
                published = str(row.get("post_publish_time") or "")
                if not re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", published):
                    continue
                post_id = str(row.get("post_id") or "")
                text = normalize_text(row.get("post_content") or row.get("post_title"), max_chars=1800)
                result["rows"].append({"id": post_id or f"{code}:{published}:{text[:20]}", "text": text, "date": published[:19], "source": "eastmoney", "author": anonymous_author("eastmoney", row["user_id"]) if row.get("user_id") else "", "code": code, "url": f"https://guba.eastmoney.com/news,{code},{post_id}.html" if post_id.isdigit() else "", "contentKind": "正文" if row.get("post_content") else "标题", "replies": number(row.get("post_comment_count")), "views": number(row.get("post_click_count")), "forwards": number(row.get("post_forward_count"))})
            ordinary = [row for row in rows if not number(row.get("post_top_status"))]
            older = bool(ordinary) and all(re.match(r"\d{4}-\d{2}-\d{2}", str(row.get("post_publish_time") or "")) and re.match(r"\d{4}-\d{2}-\d{2}", str(row.get("post_last_time") or "")) and str(row["post_publish_time"])[:10] < day and str(row["post_last_time"])[:10] < day for row in ordinary)
            older_pages = older_pages + 1 if older else 0
            if len(rows) < CONFIG["pageSize"] or older_pages >= 2:
                result.update(complete=True, reason="公开列表已读至末页" if len(rows) < CONFIG["pageSize"] else "连续两页已越过日期起点")
                break
        except Exception as exc:
            result.update(error=str(exc)[:200], reason="部分采集失败，数量为已观察下限")
            break
    if not result["complete"] and not result["error"] and result["pages"] >= page_limit:
        result["pageLimitReached"] = True
    return result


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def collect_trading(code, day):
    symbol = quote_symbol({"stockCode": code})
    result = {"code": code, "name": code, "price": None, "changePct": None, "turnover": None, "amount": None, "volumeRatio": None, "activityScore": None, "baselineDays": 0, "asOf": "", "source": "", "error": None}
    try:
        raw = request_text("https://qt.gtimg.cn/q=" + symbol, "https://qt.gtimg.cn/", timeout=8, attempts=1)
        match = re.search(r'v_' + symbol + r'="([^"]*)"', raw)
        fields = match[1].split("~") if match else []
        if len(fields) >= 39 and fields[2] == code:
            result["name"] = fields[1] or code
            if fields[30].startswith(day.replace("-", "")):
                result.update(price=number(fields[3]), changePct=number(fields[32]), turnover=number(fields[38]), amount=number(fields[37]) * 10000 if number(fields[37]) is not None else None, asOf=fields[30], source="腾讯公开报价")
    except Exception:
        pass
    try:
        param = f"{symbol},day,,{day},80,qfq"
        data = get_json("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + urllib.parse.quote(param)).get("data") or {}
        rows = sorted([row for row in (data.get(symbol, {}).get("qfqday") or data.get(symbol, {}).get("day", [])) if len(row) >= 6 and row[0] <= day], key=lambda row: row[0])
        current = next((row for row in rows if row[0] == day), None)
        past = [row for row in rows if row[0] < day]
        if current:
            missing_quote = result["price"] is None
            if missing_quote:
                result["price"] = number(current[2])
            previous_close = number(past[-1][2]) if past else None
            if missing_quote and previous_close is not None and previous_close > 0 and result["price"] is not None:
                result["changePct"] = rounded((result["price"] / previous_close - 1) * 100)
            result.update(asOf=f"{day} 15:00", source="腾讯公开日线（参考价前复权；成交量历史分位）" if missing_quote else "腾讯公开报价 + 日线成交量")
            volumes = [number(row[5]) for row in past[-60:]]
            volumes = [value for value in volumes if value is not None and value > 0]
            volume = number(current[5])
            result["baselineDays"] = len(volumes)
            if len(volumes) >= CONFIG["minimumBaselineDays"] and volume is not None:
                result["activityScore"] = rounded(100 * sum(1 if value < volume else .5 if value == volume else 0 for value in volumes) / len(volumes))
                result["volumeRatio"] = rounded(volume / (sum(volumes[-20:]) / 20))
        else:
            result["error"] = "所选日期历史日线缺失"
    except Exception:
        result["error"] = "历史成交基线暂不可用"
    return result


def summarize_trading(rows):
    quoted = [row for row in rows if row.get("changePct") is not None]
    scored = [row for row in rows if row.get("activityScore") is not None]
    minimum = math.ceil(len(rows) * .7)
    up = sum(row["changePct"] > 0 for row in quoted)
    return {"score": rounded(sum(row["activityScore"] for row in scored) / len(scored)) if minimum and len(scored) >= minimum else None,
            "coverage": len(quoted), "baselineCoverage": len(scored), "total": len(rows), "up": up, "down": sum(row["changePct"] < 0 for row in quoted),
            "upRate": rounded(up / len(quoted) * 100) if quoted else None,
            "averageChange": rounded(sum(row["changePct"] for row in quoted) / len(quoted)) if quoted else None, "members": rows,
            "reason": "历史成交基线不足" if len(scored) < minimum else "成分成交量历史分位的等权均值"}
