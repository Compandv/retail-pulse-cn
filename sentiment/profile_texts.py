"""Bounded full-text enrichment; never changes saved historical interactions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from threading import Event, Lock
from .collectors import CN_TZ, anonymous_author, normalize_text, request_text
from .market_watch import atomic_json, read_json
from .measurement import prepare_observations


def parse_article(body, row):
    match = re.search(r"var\s+post_article\s*=\s*", body)
    if not match:
        raise ValueError("页面没有可核对的原帖内容")
    article, _ = json.JSONDecoder().raw_decode(body[match.end():])
    if str(article.get("post_id")) != row["id"] or str(article.get("post_publish_time", ""))[:19] != row["date"] or str(article.get("post_guba", {}).get("stockbar_code")) != row["code"]:
        raise ValueError("原帖标识或发表日期不匹配")
    user = article.get("post_user", {}).get("user_id")
    if not user or anonymous_author("eastmoney", user) != row["author"]:
        raise ValueError("原帖账户无法核对")
    content = normalize_text(article.get("post_content") or "", max_chars=1800)
    if not content:
        raise ValueError("原帖正文为空")
    return content


def enrich_profiles(root, capture):
    day = capture["date"]; chosen = {}
    for detail in capture.get("members", {}).values():
        codes = [r["code"] for r in detail.get("members", [])]
        raw = [r for code in codes for r in capture["feeds"].get(code, {}).get("rows", [])]
        posts = prepare_observations(raw, day, "15:00:00")["analyzed"]
        candidates = [r for r in posts if r.get("contentKind") != "正文" and len(r["text"]) >= 36 and r.get("author") and re.fullmatch(r"\d+", r["id"])]
        candidates.sort(key=lambda r: hashlib.sha256(f"{day}:{r['id']}".encode()).hexdigest())
        for row in candidates[:64]: chosen[row["id"]] = row
    cache = Path(root) / "work/profile-bodies" / day
    unavailable = Event(); lock = Lock(); failed_in_a_row = 0
    def fetch(row):
        nonlocal failed_in_a_row
        saved = read_json(cache / f"{row['id']}.json", {})
        if saved.get("date") == row["date"] and saved.get("code") == row["code"] and saved.get("author") == row["author"]:
            return saved
        if unavailable.is_set():
            raise ValueError("来源连续不可核对，暂停本批剩余正文请求")
        url = f"https://guba.eastmoney.com/news,{row['code']},{row['id']}.html"
        try:
            body = request_text(url, "https://guba.eastmoney.com/", timeout=8, attempts=1)
            content = parse_article(body, row)
        except Exception:
            with lock:
                failed_in_a_row += 1
                if failed_in_a_row >= 6: unavailable.set()
            raise
        with lock: failed_in_a_row = 0
        value = {"date": row["date"], "code": row["code"], "author": row["author"], "text": content, "observedAt": datetime.now(CN_TZ).isoformat(timespec="seconds")}
        atomic_json(cache / f"{row['id']}.json", value)
        return value
    results = dict(capture.get("profileBodies", {})); failures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, row): key for key, row in chosen.items()}
        for index, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try: results[key] = future.result()
            except Exception as error: failures.append({"id": key, "error": str(error)[:120]})
            if index % 100 == 0: print(f"分层正文核对 {index}/{len(chosen)}，成功 {len(results)}", flush=True)
    capture["profileBodies"] = results
    capture["profileEnrichment"] = {"attempted": len(chosen), "observed": len(results), "failures": len(failures), "observedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"), "sampling": "每板块按稳定哈希选最多64条长标题补正文；用于分层，不更新历史互动；非随机全市场账户样本"}
    atomic_json(Path(root) / "work/profile-bodies" / f"{day}-errors.json", failures)
    return capture
