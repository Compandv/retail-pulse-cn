"""Fallback: observed Sina membership + dated Tencent constituent quotes.

Sina's undated aggregate prices are deliberately not used as historical facts.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .collectors import CN_TZ, request_text
from .market_watch import CONFIG, VERSION, atomic_json, number, read_json
from .pipeline import effective_trade_date

SINA = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center."


def collect_sina_market(root, day, now):
    if day != effective_trade_date(now).isoformat():
        raise RuntimeError("备用来源仅采最新已收盘交易日，不能用当前成分回填历史")
    cache = Path(root) / "work/market-source-cache" / day

    def cached(key, fetch):
        path = cache / f"{key}.json"
        stored = read_json(path, {})
        if stored.get("date") == day and "data" in stored and not (key.startswith("members-") and not stored["data"].get("complete")):
            return stored["data"]
        value = fetch()
        if not key.startswith("members-") or value.get("complete"):
            atomic_json(path, {"date": day, "collectedAt": now.isoformat(timespec="seconds"), "data": value})
        return value

    def get_json(url):
        return json.loads(request_text(url, "https://finance.sina.com.cn/", timeout=10, attempts=2))

    def catalog(group):
        url = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php" if group == "industry" else "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class"
        def fetch():
            raw = request_text(url, "https://finance.sina.com.cn/", timeout=10, attempts=2)
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start:end + 1])
            if not isinstance(data, dict) or not data:
                raise RuntimeError("备用板块目录为空")
            rows = []
            for value in data.values():
                fields = value.split(",")
                if len(fields) < 3 or not re.fullmatch(r"[A-Za-z0-9_]+", fields[0]):
                    raise RuntimeError("备用板块目录结构异常")
                rows.append({"code": fields[0], "name": fields[1], "declaredMembers": int(fields[2])})
            return rows
        return cached("catalog-" + group, fetch)

    def members(node):
        def fetch():
            expected = int(cached("counts/" + node, lambda: get_json(SINA + "getHQNodeStockCount?" + urllib.parse.urlencode({"node": node}))))
            if expected < 0 or expected > 10000:
                raise RuntimeError("备用成分数量异常")
            unique, pages, errors = {}, 0, []
            def fetch_page(page):
                def fetch_rows():
                    params = urllib.parse.urlencode({"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": node, "symbol": "", "_s_r_a": "page"})
                    rows = get_json(SINA + "getHQNodeData?" + params)
                    if not isinstance(rows, list):
                        raise RuntimeError("备用成分列表结构异常")
                    return rows
                return cached(f"pages/{node}-{page}", fetch_rows)
            page_numbers = range(1, min(math.ceil(expected / 80) + 2, 128))
            batches = {}
            if node == "hs_a":
                # This broad universe runs before the board pool: at most three
                # concurrent requests, and successful pages survive a failed run.
                with ThreadPoolExecutor(max_workers=CONFIG["workers"]) as pool:
                    futures = {pool.submit(fetch_page, page): page for page in page_numbers}
                    for future in as_completed(futures):
                        try:
                            batches[futures[future]] = future.result()
                        except Exception as exc:
                            errors.append(f"第 {futures[future]} 页：{str(exc)[:100]}")
            else:
                for page in page_numbers:
                    try:
                        batches[page] = fetch_page(page)
                        if len(batches[page]) < 80:
                            break
                    except Exception as exc:
                        errors.append(f"第 {page} 页：{str(exc)[:100]}")
                        break
            reached_end = False
            for page in sorted(batches):
                rows = batches[page]
                pages += 1
                duplicate = False
                for row in rows:
                    symbol = row.get("symbol", "")
                    if not re.fullmatch(r"(?:sh|sz|bj)\d{6}", symbol):
                        duplicate = True
                        continue
                    if symbol in unique:
                        duplicate = True
                    unique[symbol] = {"symbol": symbol, "code": str(row.get("code") or symbol[2:]), "name": str(row.get("name") or symbol[2:])}
                if duplicate:
                    errors.append("成分分页存在重复或非法代码")
                    break
                if len(rows) < 80:
                    # The provider documents that its count can understate membership.
                    reached_end = True
                    break
            complete = not errors and pages > 0 and reached_end and len(unique) >= expected
            return {"members": list(unique.values()), "expected": expected, "complete": complete, "pages": pages,
                    "reason": "已读至成分末页" if complete else "成分覆盖未确认", "errors": errors[:5]}
        return cached("members-" + node, fetch)

    catalogs, errors = {}, {}
    for group in ("industry", "concept"):
        print(f"备用来源：开始请求 {group} 目录", flush=True)
        try:
            catalogs[group] = catalog(group)
            print(f"备用来源 {group}：收到 {len(catalogs[group])} 个板块", flush=True)
        except Exception as exc:
            catalogs[group] = []
            errors[group] = str(exc)[:180]
            print(f"备用来源 {group} 请求失败：{errors[group]}", flush=True)
    nodes = {row["code"] for values in catalogs.values() for row in values} | {"hs_a"}
    components = {}
    print("备用来源：读取全A股目录和板块成分", flush=True)
    try:
        components["hs_a"] = members("hs_a")
        print(f"A 股目录：已读 {len(components['hs_a']['members'])}/{components['hs_a']['expected']} 股", flush=True)
    except Exception as exc:
        errors["hs_a"] = str(exc)[:180]
    with ThreadPoolExecutor(max_workers=CONFIG["workers"]) as pool:
        futures = {pool.submit(members, node): node for node in sorted(nodes - {"hs_a"})}
        for future in as_completed(futures):
            node = futures[future]
            try:
                components[node] = future.result()
            except Exception as exc:
                errors[node] = str(exc)[:180]
    print(f"备用目录：{len(catalogs['industry'])} 行业 / {len(catalogs['concept'])} 概念；已取得 {len(components)}/{len(nodes)} 组成分", flush=True)
    all_stocks = components.get("hs_a", {})
    listed = {row["symbol"]: row for row in all_stocks.get("members", [])} if all_stocks.get("complete") else None
    # Source theme lists can retain delisted stocks. Only a complete current A
    # share universe permits filtering; missing pages never imply delisting.
    universe = listed if listed is not None else {row["symbol"]: row for component in components.values() for row in component["members"]}
    symbols = sorted(universe)

    def quotes(batch):
        def fetch():
            raw = request_text("https://qt.gtimg.cn/q=" + ",".join(batch), "https://qt.gtimg.cn/", timeout=10, attempts=2)
            result = {}
            for match in re.finditer(r'v_((?:sh|sz|bj)\d{6})="([^"]*)"', raw):
                symbol, body = match.groups()
                fields = body.split("~")
                if len(fields) < 39 or symbol not in batch or fields[2] != symbol[2:]:
                    continue
                try:
                    stamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CN_TZ)
                except ValueError:
                    continue
                if stamp.date().isoformat() != day or stamp.hour < 15:
                    continue
                amount = number(fields[37])
                result[symbol] = {"f12": fields[2], "f14": fields[1], "f2": number(fields[3]), "f3": number(fields[32]),
                                  "f6": amount * 10000 if amount is not None else None, "f8": number(fields[38]), "f124": int(stamp.timestamp())}
            # Missing quotes should be retried on a later run instead of cached forever.
            if not result:
                raise RuntimeError("腾讯没有该日收盘行情")
            return result
        # Quotes remain in this capture; next run can improve date coverage.
        return fetch()

    quoted = {}
    batches = [symbols[index:index + 80] for index in range(0, len(symbols), 80)]
    with ThreadPoolExecutor(max_workers=CONFIG["workers"]) as pool:
        futures = {pool.submit(quotes, batch): index for index, batch in enumerate(batches)}
        for future in as_completed(futures):
            try:
                quoted.update(future.result())
            except Exception as exc:
                errors[f"quotes-{futures[future]}"] = str(exc)[:120]
    print(f"备用行情：{len(quoted)}/{len(symbols)} 股有 {day} 收盘报价", flush=True)
    groups, details = {}, {}
    for group in ("industry", "concept"):
        rows = []
        for entry in catalogs[group]:
            code = entry["code"]
            component = components.get(code)
            source_members = component["members"] if component else []
            all_members = [member for member in source_members if listed is None or member["symbol"] in listed]
            excluded_members = [member for member in source_members if listed is not None and member["symbol"] not in listed]
            valid = [quoted[row["symbol"]] for row in all_members if row["symbol"] in quoted and quoted[row["symbol"]]["f3"] is not None]
            enough = bool(component and component["complete"] and all_members and len(valid) / len(all_members) >= .9)
            leader = max(valid, key=lambda row: row["f3"]) if valid else None
            turnovers = [row["f8"] for row in valid if row["f8"] is not None]
            amounts = [row["f6"] for row in valid if row["f6"] is not None]
            row = {"f12": code, "f14": entry["name"], "f2": None,
                   "f3": sum(item["f3"] for item in valid) / len(valid) if enough else None,
                   "f8": sum(turnovers) / len(turnovers) if enough and len(turnovers) >= len(all_members) * .9 else None,
                   "f6": sum(amounts) if enough and len(amounts) == len(all_members) else None,
                   "f104": sum(item["f3"] > 0 for item in valid) if enough else None,
                   "f105": sum(item["f3"] < 0 for item in valid) if enough else None,
                   "f124": min(item["f124"] for item in valid) if enough else None,
                   "f128": leader["f14"] if enough and leader else None, "f140": leader["f12"] if enough and leader else None,
                   "f136": leader["f3"] if enough and leader else None,
                   "memberCount": len(all_members), "quoteCoverage": len(valid), "membersComplete": bool(component and component["complete"]),
                   "rawMemberCount": len(source_members), "excludedMemberCount": len(excluded_members)}
            rows.append(row)
            details[code] = {"code": code, "date": day, "collectedAt": now.isoformat(timespec="seconds"), "expected": len(all_members) if component and component["complete"] else entry["declaredMembers"],
                             "complete": bool(component and component["complete"]), "reason": "当次采集的新浪成分；腾讯行情按日期核验" + (f"；剔除 {len(excluded_members)} 个不在完整当期 A 股目录的成员" if listed is not None else "；A 股目录未完整，暂不剔除旧成员"),
                             "listedUniverseComplete": listed is not None, "rawMemberCount": len(source_members), "excludedMembers": excluded_members,
                             "members": [{"code": member["code"], "name": member["name"], "changePct": quoted.get(member["symbol"], {}).get("f3"),
                                          "amount": quoted.get(member["symbol"], {}).get("f6"), "turnover": quoted.get(member["symbol"], {}).get("f8"),
                                          "asOf": datetime.fromtimestamp(quoted[member["symbol"]]["f124"], CN_TZ).isoformat() if member["symbol"] in quoted else None} for member in all_members]}
        missing = sum(not row["membersComplete"] for row in rows)
        groups[group] = {"group": group, "expected": len(catalogs[group]) if catalogs[group] else None, "rows": rows, "pages": 1 if rows else 0,
                         "complete": bool(catalogs[group]), "errors": [errors[group]] if group in errors else ([f"{missing} 个板块成分覆盖不足"] if missing else [])}
    stock_rows = [{**quoted.get(member["symbol"], {"f12": member["code"], "f14": member["name"]})} for member in all_stocks.get("members", [])]
    groups["stocks"] = {"group": "stocks", "expected": len(stock_rows) if all_stocks.get("complete") else all_stocks.get("expected"), "rows": stock_rows, "pages": all_stocks.get("pages", 0), "complete": all_stocks.get("complete", False), "errors": [errors["hs_a"]] if "hs_a" in errors else all_stocks.get("errors", [])}
    return {"date": day, "collectedAt": now.isoformat(timespec="seconds"), "version": VERSION, "provider": "sina-tencent", "groups": groups, "details": details,
            "errors": errors, "sourceNote": "新浪当次观察成分 + 腾讯日期核验收盘行情；" + ("成分只保留完整当期 A 股目录内证券；" if listed is not None else "A 股目录未完整，未排除源列表旧成员；") + "板块涨跌及换手为有效成分等权均值，至少90%成分有行情；金额仅在全部成分量额完整时汇总。"}
