"""Manually invoked OpenAI semantic analysis with content-addressed local cache."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .market_watch import atomic_json, read_json
from .measurement import prepare_observations
from .retail_profile import expression_tier, refine_behavior, account_profile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = read_json(ROOT / "config/semantic-agent.json", {})
PROMPT = (ROOT / "config/semantic-agent-prompt.md").read_text(encoding="utf-8")
ENUMS = {
    "stance": ["bullish", "bearish", "mixed", "neutral", "unknown"],
    "intent": ["reported_chase", "chase_intent", "question", "warning", "quoted", "historical", "analysis", "other", "unknown"],
    "level": ["L1", "L2", "L3", "L4", "L5", "unknown"],
}
PROPERTIES = {"id": {"type": "string"}, **{k: {"type": "string", "enum": v} for k, v in ENUMS.items()},
              **{k: {"type": "boolean"} for k in ("chase", "panic", "refill")},
              "evidence": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["results"], "properties": {
    "results": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": list(PROPERTIES), "properties": PROPERTIES}}}}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def settings(root=ROOT):
    # No shell evaluation, expansion or logging of secrets. Process env wins.
    values = {}
    path = Path(root) / ".env.agent.local"
    allowed = {"OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_API_TYPE", "RETAIL_AGENT_MODE", "RETAIL_AGENT_MAX_NEW_POSTS"}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in allowed:
                values[key.strip()] = value.strip().strip('"\'')
    values.update({k: os.environ[k] for k in allowed if k in os.environ})
    mode = values.get("RETAIL_AGENT_MODE", CONFIG["mode"])
    if mode not in ("off", "shadow"):
        raise ValueError("Agent模式仅支持off/shadow；先完成对照验证再接管正式评分")
    model = values.get("OPENAI_MODEL") or CONFIG["model"]
    if not re.fullmatch(r"[a-zA-Z0-9_./:-]{1,160}", model):
        raise ValueError("OPENAI_MODEL格式无效")
    try:
        limit = int(values.get("RETAIL_AGENT_MAX_NEW_POSTS", CONFIG["maxNewPostsPerRun"]))
    except ValueError:
        raise ValueError("RETAIL_AGENT_MAX_NEW_POSTS必须是整数") from None
    if not 1 <= limit <= 20000:
        raise ValueError("每次新增条数应在1—20000之间")
    options = {"key": values.get("OPENAI_API_KEY", ""), "model": model, "mode": mode, "limit": limit,
               "base_url": values.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
               "api_type": values.get("OPENAI_API_TYPE") or "responses"}
    endpoint(options)  # Validate before any request or cache operation.
    return options


def endpoint(options):
    base = options.get("base_url", "https://api.openai.com/v1").strip().rstrip("/")
    kind = options.get("api_type", "responses")
    if kind not in ("responses", "chat_completions"):
        raise ValueError("OPENAI_API_TYPE必须为responses或chat_completions")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in base):
        raise ValueError("OPENAI_BASE_URL须为HTTPS API基础地址，不含账号、查询参数或片段")
    if parsed.path.endswith(("/responses", "/chat/completions")):
        raise ValueError("请填写API基础地址，不要附加/responses或/chat/completions")
    return base + ("/responses" if kind == "responses" else "/chat/completions")


def method_id(model, options=None):
    options = options or {}
    return digest({"version": CONFIG["version"], "model": model, "endpoint": endpoint(options), "apiType": options.get("api_type", "responses"), "transportVersion": 2, "prompt": PROMPT, "schema": SCHEMA, "contextPolicy": "two-earlier-same-account-v1", "reasoning": "low"})


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def content_key(post, day):
    # Reposts across overlapping sectors by the same author are one observation.
    # Different authors saying the same thing still count as separate accounts.
    account = post.get("author") or "unknown:" + post["id"]
    return digest([day, post["source"], account, normalized(post["text"])])


def sample_posts(capture):
    """Union per-board samples so one board's author cap cannot erase another's."""
    union = {}
    for detail in capture.get("members", {}).values():
        rows = [r for member in detail.get("members", []) for r in capture.get("feeds", {}).get(member["code"], {}).get("rows", [])]
        for post in prepare_observations(rows, capture["date"], "15:00:00")["analyzed"]:
            body = capture.get("profileBodies", {}).get(post["id"], {})
            if body.get("date") == post["date"] and body.get("author") == post["author"] and body.get("code") == post["code"] and body.get("text"):
                post = {**post, "text": body["text"], "contentKind": "补采正文", "textObservedAt": body.get("observedAt")}
            key = content_key(post, capture["date"])
            if key not in union or (post["date"], post["id"]) < (union[key]["date"], union[key]["id"]):
                union[key] = post
    return union


def validate_result(value, target):
    if not isinstance(value, dict) or set(value) != set(PROPERTIES):
        raise ValueError("Agent输出字段不符合约定")
    if value["id"] != target["id"]:
        raise ValueError("Agent输出与请求ID不匹配")
    if any(value[k] not in choices for k, choices in ENUMS.items()):
        raise ValueError("Agent输出未知枚举")
    if any(type(value[k]) is not bool for k in ("chase", "panic", "refill")):
        raise ValueError("行为标签必须为布尔值")
    if value["chase"] != (value["intent"] in ("reported_chase", "chase_intent")):
        raise ValueError("追涨与意图标签冲突")
    if not isinstance(value["reason"], str) or not 1 <= len(value["reason"]) <= 600:
        raise ValueError("缺少简短判断理由")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 3 or any(not isinstance(e, str) or not e or len(e) > 300 or e not in target["text"] for e in evidence):
        raise ValueError("证据不是当前原文的逐字片段")
    if (value["level"] != "unknown" or any(value[k] for k in ("chase", "panic", "refill")) or value["stance"] in ("bullish", "bearish", "mixed")) and not evidence:
        raise ValueError("有明确判断但缺少原文证据")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_openai(items, options, *, prompt=PROMPT, schema=SCHEMA, max_tokens=None):
    payload = {"model": options["model"], "store": False, "instructions": prompt,
               "input": [{"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)}],
               "reasoning": {"effort": "low"}, "max_output_tokens": max_tokens or CONFIG["maxOutputTokens"],
               "text": {"format": {"type": "json_schema", "name": "retail_semantics", "strict": True, "schema": schema}}}
    if options.get("api_type", "responses") == "chat_completions":
        example = {"results": [{"id": "target-id", "stance": "unknown", "intent": "unknown", "level": "unknown", "chase": False, "panic": False, "refill": False, "evidence": [], "reason": "证据不足"}]}
        instructions = prompt + "\n仅输出JSON对象，遵守以下JSON Schema：\n" + json.dumps(schema, ensure_ascii=False)
        if schema == SCHEMA: instructions += "\n格式示例（内容不是待分析数据）：\n" + json.dumps(example, ensure_ascii=False)
        payload = {"model": options["model"], "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)}],
                   "max_tokens": max_tokens or CONFIG["maxOutputTokens"], "stream": False, "response_format": {"type": "json_object"}}
    request = urllib.request.Request(endpoint(options), data=json.dumps(payload).encode(),
                                     headers={"Authorization": "Bearer " + options["key"], "Content-Type": "application/json"}, method="POST")
    # No automatic retry: an uncertain timeout may already have incurred cost.
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=CONFIG["timeoutSeconds"]) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ValueError("Agent响应过大")
            data = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"模型API HTTP {error.code}，请检查密钥、模型权限或额度；本次不自动重试") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("模型API连接失败或超时，结果未确认；本次不自动重试") from None
    if options.get("api_type", "responses") == "chat_completions":
        choices = data.get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("模型响应未完整完成，未写入成功缓存")
        message = choices[0].get("message", {})
        if message.get("refusal") or message.get("tool_calls") or not isinstance(message.get("content"), str):
            raise ValueError("模型未返回有效文本标注")
        usage = data.get("usage") or {}
        return json.loads(message["content"]), {"responseId": data.get("id"), "model": data.get("model"),
            "usage": {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)}}
    if data.get("status") != "completed":
        raise ValueError("OpenAI未完整完成响应，未写入成功缓存")
    chunks = [c for item in data.get("output", []) if item.get("type") == "message" for c in item.get("content", [])]
    if any(c.get("type") == "refusal" for c in chunks):
        raise ValueError("模型拒绝标注，本批保留未分析")
    text = "".join(c.get("text", "") for c in chunks if c.get("type") == "output_text")
    return json.loads(text), {"responseId": data.get("id"), "model": data.get("model"), "usage": data.get("usage", {})}


@contextmanager
def run_lock(directory):
    """OS lock releases after interruption; avoids duplicate concurrent billing."""
    directory.mkdir(parents=True, exist_ok=True)
    handle = open(directory / "run.lock", "a+b")
    handle.seek(0)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise RuntimeError("已有Agent运行中，请等待完成后再运行") from None
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def run_agent(root, capture, options=None, transport=call_openai, dry_run=False):
    options = settings(root) if options is None else options
    day = capture["date"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day): raise ValueError("交易日格式无效")
    method = method_id(options["model"], options)
    directory = Path(root) / "work/semantic-agent" / method / day
    samples = sample_posts(capture)
    results = {}; todo = []
    summary = {"version": CONFIG["version"], "method": method, "model": options["model"], "mode": options["mode"],
               "date": day, "runAt": datetime.now(timezone.utc).isoformat(), "total": len(samples), "reused": 0, "new": 0, "failed": 0, "pending": 0,
               "requests": 0, "usage": {"input_tokens": 0, "output_tokens": 0}, "errors": [], "status": "disabled"}
    if options["mode"] == "off":
        summary["pending"] = len(samples)
        return {"summary": summary, "results": results}
    with run_lock(directory):
        for key, post in sorted(samples.items()):
            saved = read_json(directory / f"{key}.json", {})
            target = {"id": key, "text": post["text"]}
            try:
                if saved.get("method") != method or saved.get("date") != day or saved.get("key") != key: raise ValueError("cache")
                validate_result(saved["result"], target)
                results[key] = saved["result"]; summary["reused"] += 1
            except (KeyError, ValueError, TypeError):
                todo.append((key, post))
        summary["pending"] = len(todo)
        if dry_run or not options.get("key"):
            summary["status"] = "dry_run" if dry_run else "needs_key"
            summary["errors"] = [] if dry_run else ["未配置OPENAI_API_KEY，未调用模型；原规则结果仍独立保留"]
        else:
            contexts = defaultdict(list)
            for key, post in samples.items():
                if post.get("author"): contexts[(post["source"], post["author"])].append((key, post))
            limit = options["limit"]
            for offset in range(0, min(limit, len(todo)), CONFIG["batchSize"]):
                batch = todo[offset:min(offset + CONFIG["batchSize"], limit)]
                items = []
                for key, post in batch:
                    earlier = sorted((p for k, p in contexts.get((post["source"], post.get("author")), []) if k != key and p["date"] < post["date"]), key=lambda p: p["date"])[-2:]
                    items.append({"id": key, "target": {"text": post["text"], "publishedAt": post["date"], "contentKind": post.get("contentKind", "文本")}, "context": [{"text": p["text"], "publishedAt": p["date"]} for p in earlier]})
                try:
                    summary["requests"] += 1
                    output, metadata = transport(items, options)
                    for name in summary["usage"]:
                        value = metadata.get("usage", {}).get(name, 0)
                        if type(value) is int and value >= 0: summary["usage"][name] += value
                    output_rows = output.get("results") if isinstance(output, dict) and set(output) == {"results"} else None
                    if not isinstance(output_rows, list) or len(output_rows) != len(batch): raise ValueError("批量输出条数不匹配")
                    indexed = {r["id"]: r for r in output_rows if isinstance(r, dict) and isinstance(r.get("id"), str)}
                    if set(indexed) != {k for k, _ in batch}: raise ValueError("批量输出ID缺失或重复")
                    for key, post in batch: validate_result(indexed[key], {"id": key, "text": post["text"]})
                    for key, post in batch:
                        result = indexed[key]
                        atomic_json(directory / f"{key}.json", {"key": key, "method": method, "date": day, "result": result, "metadata": metadata, "input": next(item for item in items if item["id"] == key), "analyzedAt": datetime.now(timezone.utc).isoformat()})
                        results[key] = result; summary["new"] += 1
                    print(f"Agent：新增 {summary['new']}，复用 {summary['reused']}，待分析 {len(samples) - len(results)}", flush=True)
                except Exception as error:
                    summary["failed"] += len(batch)
                    # Do not log arbitrary transport exceptions which could include secrets.
                    summary["errors"].append("本批API或结构校验失败，已停止；请检查网络、模型权限和额度，下次运行重试未完成项")
                    break
            summary["pending"] = len(samples) - len(results)
            summary["status"] = "complete" if not summary["pending"] else "partial"
        package = {"summary": summary, "results": results}
        if not dry_run:
            atomic_json(directory / "latest-run.json", package)
            atomic_json(Path(root) / "work/semantic-agent" / f"{day}-latest.json", package)
        return package


def comparison_rows(capture, package):
    rows = []
    for key, post in sample_posts(capture).items():
        agent = package["results"].get(key)
        if not agent: continue
        rule = refine_behavior(post)
        level, reason = expression_tier(post["text"])
        baseline = {"level": level or "unknown", "chase": rule["classification"]["chase"], "panic": rule["classification"]["panic"], "refill": rule["refillExpression"], "reason": reason}
        rows.append({"id": key, "date": post["date"], "text": post["text"], "url": post.get("url", ""), "contentKind": post.get("contentKind", "文本"), "rule": baseline, "agent": agent,
                     "disagreements": [k for k in ("level", "chase", "panic", "refill") if baseline[k] != agent[k]], "human": {"reviewed": False, "level": None, "chase": None, "panic": None, "refill": None, "notes": ""}})
    return sorted(rows, key=lambda r: (-len(r["disagreements"]), r["id"]))


def candidate_profiles(capture, package):
    """Private shadow statistics; never substitute rule labels for missing AI labels."""
    candidates = []
    for board_id, detail in capture.get("members", {}).items():
        posts = list(sample_posts({**capture, "members": {board_id: detail}}).values())
        results = package["results"]
        annotated = [p for p in posts if content_key(p, capture["date"]) in results]
        coverage = len(annotated) / len(posts) if posts else 0
        codes = {m["code"] for m in detail.get("members", [])}
        complete = sum(bool(capture.get("feeds", {}).get(c, {}).get("complete")) and not capture["feeds"][c].get("error") for c in codes)
        sampling_ok = bool(codes) and complete / len(codes) >= .8 and detail.get("complete", False) and coverage >= CONFIG["minimumCoverage"]
        def classify(post):
            result = results.get(content_key(post, capture["date"]), {})
            return (None if result.get("level", "unknown") == "unknown" else result["level"], result.get("reason", "未分析"))
        profile = account_profile(posts, len({(p["source"], p["author"]) for p in posts if p.get("author")}), sampling_ok, classifier=classify)
        profile["version"] = CONFIG["version"]
        candidates.append({"boardId": board_id, "sampleCount": len(posts), "annotatedCount": len(annotated), "annotationCoverage": round(100 * coverage, 1), "retailProfile": profile,
                           "behaviorRates": {k: round(100 * sum(results[content_key(p, capture["date"])][k] for p in annotated) / len(annotated), 1) if sampling_ok and len(annotated) >= 20 else None for k in ("chase", "panic", "refill")}})
    return sorted(candidates, key=lambda r: (r["retailProfile"]["l1l2Share"] is None, -(r["retailProfile"]["l1l2Share"] or 0), r["boardId"]))


def save_review(root, capture, package):
    summary = package["summary"]
    path = Path(root) / "work/semantic-agent/reviews" / f"{summary['date']}-{summary['method']}.json"
    old = read_json(path, {})
    previous = {r["id"]: r for r in old.get("rows", [])}
    rows = comparison_rows(capture, package)
    for row in rows:
        if row["id"] in previous:
            row["human"] = previous[row["id"]].get("human", row["human"])
    current_ids = {r["id"] for r in rows}
    archived = {r["id"]: r for r in old.get("archivedRows", [])}
    archived.update({k: v for k, v in previous.items() if k not in current_ids})
    for key in current_ids: archived.pop(key, None)
    review = {"summary": summary, "note": "仅对照候选；L1–L5表示发言分析层次，不认证真实身份。行为率分母是已标注样本；不足80%覆盖留空。", "rows": rows,
              "archivedRows": list(archived.values()), "sectors": candidate_profiles(capture, package)}
    atomic_json(path, review)
    return path


def evaluate_review(review):
    """Compare against explicitly reviewed labels, never use rules as ground truth."""
    rows = review.get("rows", [])
    metrics = {}
    for field in ("level", "chase", "panic", "refill"):
        accepted = [r for r in rows if r.get("human", {}).get("reviewed") is True and
                    (r["human"].get(field) in ENUMS["level"] if field == "level" else type(r["human"].get(field)) is bool)]
        systems = {}
        for name in ("rule", "agent"):
            pairs = [(r["human"][field], r[name][field]) for r in accepted]
            confusion = defaultdict(int)
            for actual, predicted in pairs: confusion[f"{actual} -> {predicted}"] += 1
            value = {"accuracy": sum(a == p for a, p in pairs) / len(pairs) if pairs else None, "confusion": dict(confusion)}
            if field != "level":
                tp = sum(a is True and p is True for a, p in pairs)
                predicted = sum(p is True for a, p in pairs); positives = sum(a is True for a, p in pairs)
                value.update(precision=tp / predicted if predicted else None, recall=tp / positives if positives else None)
            systems[name] = value
        metrics[field] = {"reviewed": len(accepted), **systems}
    return {"total": len(rows), "note": "未人工复核的样本不作为真值；小样本准确率不代表整体效果。", "metrics": metrics}


def analyze_capture(root, capture, *, dry_run=False, options=None):
    package = run_agent(root, capture, dry_run=dry_run, options=options)
    if not dry_run and package["summary"]["status"] != "disabled":
        save_review(root, capture, package)
    return package["summary"]
