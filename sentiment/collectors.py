from __future__ import annotations

import hashlib
import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Mapping

from .models import CollectionOutcome, Post

CN_TZ = timezone(timedelta(hours=8))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"


def normalize_text(value: object, max_chars: int = 500) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def anonymous_author(source: str, value: object) -> str:
    raw = f"{source}:{value or 'anonymous'}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def parse_time(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        try:
            return datetime.fromtimestamp(float(value), tz=CN_TZ)
        except (OverflowError, OSError, ValueError):
            return None
    candidate = str(value).strip().replace("Z", "+00:00")
    for parser in (
        lambda raw: datetime.fromisoformat(raw),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
        lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M"),
    ):
        try:
            parsed = parser(candidate)
            return parsed.replace(tzinfo=CN_TZ) if parsed.tzinfo is None else parsed.astimezone(CN_TZ)
        except ValueError:
            continue
    return None


def request_text(url: str, referer: str, timeout: int = 16, attempts: int = 2) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset)
                except (LookupError, UnicodeDecodeError):
                    return payload.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(str(last_error or "网络请求失败"))


def request_json(url: str, referer: str) -> Mapping[str, Any]:
    payload = json.loads(request_text(url, referer))
    if not isinstance(payload, dict):
        raise RuntimeError("来源返回的不是 JSON 对象")
    return payload


def eastmoney_posts(payload: Mapping[str, Any], target: Mapping[str, Any]) -> tuple[Post, ...]:
    expected_code = str(target["eastmoneyCode"])
    rows = payload.get("re")
    if not isinstance(rows, list):
        raise RuntimeError("东方财富帖子列表结构异常")
    posts: list[Post] = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("stockbar_code") or "") != expected_code:
            continue
        if int(row.get("post_type") or 0) != 0 or row.get("institution"):
            continue
        author_info = row.get("user_extendinfos") if isinstance(row.get("user_extendinfos"), dict) else {}
        accreditation = author_info.get("user_accreditinfos") if isinstance(author_info, dict) else None
        if accreditation not in (None, "", "[]", []):
            continue
        text = normalize_text(row.get("post_title"))
        published = parse_time(row.get("post_publish_time") or row.get("post_display_time"))
        if len(text) < 2 or published is None:
            continue
        posts.append(Post(
            source="eastmoney",
            target_id=str(target["id"]),
            target_name=str(target["name"]),
            text=text,
            published_at=published,
            author_key=anonymous_author("eastmoney", row.get("user_id")),
        ))
    return tuple(posts)


def sina_posts(payload: Mapping[str, Any], target: Mapping[str, Any]) -> tuple[Post, ...]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("threads") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("新浪股吧帖子列表结构异常")
    posts: list[Post] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        user = row.get("user") if isinstance(row.get("user"), dict) else {}
        if bool(user.get("verified")):
            continue
        text = normalize_text(f"{row.get('title') or ''} {row.get('content') or ''}")
        published = parse_time(row.get("timestamp") or row.get("lastctime"))
        if len(text) < 2 or published is None:
            continue
        posts.append(Post(
            source="sina",
            target_id=str(target["id"]),
            target_name=str(target["name"]),
            text=text,
            published_at=published,
            author_key=anonymous_author("sina", row.get("uid") or user.get("uid")),
        ))
    return tuple(posts)


def taoguba_posts(rows: object, target: Mapping[str, Any]) -> tuple[Post, ...]:
    if not isinstance(rows, list):
        raise RuntimeError("淘股吧帖子列表结构异常")
    posts: list[Post] = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("deleteFlag") or "N") != "N":
            continue
        if str(row.get("auth") or "0") not in ("0", "", "None"):
            continue
        subject = normalize_text(row.get("subject"), max_chars=100)
        body = normalize_text(row.get("body"), max_chars=500)
        text = normalize_text(f"{subject} {body}")
        published = parse_time(row.get("actionDate") or row.get("createDT"))
        if len(text) < 2 or published is None:
            continue
        posts.append(Post(
            source="taoguba",
            target_id=str(target["id"]),
            target_name=str(target["name"]),
            text=text,
            published_at=published,
            author_key=anonymous_author("taoguba", row.get("userID")),
        ))
    return tuple(posts)


class EastMoneyCollector:
    source = "eastmoney"

    def collect(self, target: Mapping[str, Any]) -> CollectionOutcome:
        code = str(target["eastmoneyCode"])
        referer = f"https://guba.eastmoney.com/list,{code}.html"
        query = urllib.parse.urlencode({
            "code": code,
            "sorttype": 1,
            "ps": 100,
            "p": 1,
            "from": "CommonBaPost",
            "deviceid": "2f7f40de-2fb0-4d84-8a31-111111111111",
            "version": 200,
            "product": "Guba",
            "plat": "Web",
        })
        try:
            payload = request_json("https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?" + query, referer)
        except Exception:
            try:
                page = request_text(referer, "https://guba.eastmoney.com/")
                matched = re.search(r"var\s+article_list\s*=\s*(\{.*?\});", page, re.DOTALL)
                if not matched:
                    raise RuntimeError("公开页面没有帖子列表")
                payload = json.loads(matched.group(1))
            except Exception as exc:
                return CollectionOutcome(self.source, str(target["id"]), False, error=str(exc))
        try:
            posts = eastmoney_posts(payload, target)
            raw_count = len(payload.get("re") or []) if isinstance(payload.get("re"), list) else 0
            return CollectionOutcome(self.source, str(target["id"]), True, posts, raw_count)
        except Exception as exc:
            return CollectionOutcome(self.source, str(target["id"]), False, error=str(exc))

    def collect_history(self, target: Mapping[str, Any], cutoff: datetime, max_pages: int = 48) -> tuple[Post, ...]:
        """Read bounded public pages for a market-board history estimate.

        EastMoney's public feed is not a historical API and can include pinned
        rows. We therefore page conservatively, deduplicate by normalized text,
        and let the caller label the resulting daily buckets as estimated.
        """
        code = str(target["eastmoneyCode"])
        referer = f"https://guba.eastmoney.com/list,{code}.html"
        collected: list[Post] = []
        seen: set[tuple[str, str]] = set()
        oldest: datetime | None = None
        for page_number in range(1, max_pages + 1):
            query = urllib.parse.urlencode({
                "code": code, "sorttype": 1, "ps": 100, "p": page_number,
                "from": "CommonBaPost", "deviceid": "2f7f40de-2fb0-4d84-8a31-111111111111",
                "version": 200, "product": "Guba", "plat": "Web",
            })
            try:
                payload = request_json("https://gbapi.eastmoney.com/webarticlelist/api/Article/Articlelist?" + query, referer)
                rows = payload.get("re") if isinstance(payload.get("re"), list) else []
                posts = eastmoney_posts(payload, target)
            except Exception:
                break
            for post in posts:
                key = (post.author_key, "".join(post.text.lower().split()))
                if key not in seen:
                    seen.add(key)
                    collected.append(post)
                oldest = post.published_at if oldest is None or post.published_at < oldest else oldest
            if oldest is not None and oldest <= cutoff:
                break
            if len(rows) < 100:
                break
        return tuple(collected)


class SinaCollector:
    source = "sina"

    @staticmethod
    def symbol(target: Mapping[str, Any]) -> str:
        configured = str(target.get("sinaSymbol") or "")
        if configured:
            return configured
        code = str(target["stockCode"])
        if code.startswith(("5", "6", "9")):
            return "sh" + code
        if code.startswith(("4", "8")):
            return "bj" + code
        return "sz" + code

    def collect(self, target: Mapping[str, Any]) -> CollectionOutcome:
        symbol = self.symbol(target)
        page_url = f"https://guba.sina.cn/?s=bar&name={symbol}&from=redirect"
        try:
            page = request_text(page_url, "https://guba.sina.cn/")
            matched = re.search(r"[\"']bid[\"']\s*:\s*[\"']?(\d+)", page, re.I)
            if not matched:
                matched = re.search(r"data-bid=[\"'](\d+)", page, re.I)
            if not matched:
                raise RuntimeError("未找到公开论坛编号")
            bid = matched.group(1)
            api_url = "https://guba.sina.cn/api/?" + urllib.parse.urlencode({"s": "h5bar", "bid": bid, "num": 50})
            payload = request_json(api_url, page_url)
            posts = sina_posts(payload, target)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            raw_count = len(data.get("threads") or []) if isinstance(data, dict) else 0
            return CollectionOutcome(self.source, str(target["id"]), True, posts, raw_count)
        except Exception as exc:
            return CollectionOutcome(self.source, str(target["id"]), False, error=str(exc))


class TaogubaCollector:
    source = "taoguba"

    @staticmethod
    def symbol(target: Mapping[str, Any]) -> str:
        configured = str(target.get("taogubaSymbol") or "")
        if configured:
            return configured
        code = str(target["stockCode"])
        prefix = "sh" if code.startswith(("5", "6", "9")) else "bj" if code.startswith(("4", "8")) else "sz"
        return prefix + code

    def collect(self, target: Mapping[str, Any]) -> CollectionOutcome:
        if target.get("taoguba") is False:
            return CollectionOutcome(self.source, str(target["id"]), True)
        page_url = f"https://www.tgb.cn/quotes/{self.symbol(target)}"
        try:
            page = request_text(page_url, "https://www.tgb.cn/quotes/")
            matched = re.search(r"var\s+coolAttr\s*=\s*(\[.*?\]);\s*var\s+tempFeedID", page, re.DOTALL)
            if not matched:
                matched = re.search(r"var\s+coolAttr\s*=\s*(\[.*?\]);", page, re.DOTALL)
            if not matched:
                raise RuntimeError("公开页面没有最新讨论列表")
            rows = json.loads(matched.group(1))
            posts = taoguba_posts(rows, target)
            return CollectionOutcome(self.source, str(target["id"]), True, posts, len(rows))
        except Exception as exc:
            return CollectionOutcome(self.source, str(target["id"]), False, error=str(exc))


COLLECTORS = (EastMoneyCollector(), SinaCollector(), TaogubaCollector())
