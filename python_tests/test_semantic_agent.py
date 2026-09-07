import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from python_tests.test_report import fixture
from sentiment.semantic_agent import run_agent, sample_posts, content_key, validate_result, save_review, evaluate_review, run_lock, candidate_profiles, call_openai


def response(items, options):
    return {"results": [{"id": i["id"], "stance": "neutral", "intent": "other", "level": "unknown", "chase": False, "panic": False, "refill": False, "evidence": [], "reason": "证据不足"} for i in items]}, {"usage": {"input_tokens": 10, "output_tokens": 20}}


class AgentTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.capture = fixture()[1]
        self.options = {"key": "private-test-key", "model": "gpt-5.4-mini", "mode": "shadow", "limit": 200}

    def run_model(self, capture=None, transport=response, **kwargs):
        return run_agent(self.root, capture or self.capture, options=self.options, transport=transport, **kwargs)

    def test_repeat_new_changed_and_model_version(self):
        first = self.run_model()
        self.assertEqual(first["summary"]["new"], 100)
        second = self.run_model()
        self.assertEqual(second["summary"]["requests"], 0)
        self.assertEqual(second["summary"]["reused"], 100)
        row = copy.deepcopy(next(iter(self.capture["feeds"].values()))["rows"][0])
        row.update(id="new", author="new-user", text="我今天已经追高买入了")
        next(iter(self.capture["feeds"].values()))["rows"].append(row)
        self.assertEqual(self.run_model()["summary"]["new"], 1)
        row["text"] += "，刚补充正文"
        self.assertEqual(self.run_model()["summary"]["new"], 1)
        self.options["model"] = "other-model"
        self.assertEqual(self.run_model()["summary"]["new"], 101)
        self.assertNotIn(self.options["key"], "".join(p.read_text(encoding="utf-8") for p in self.root.rglob("*.json")))

    def test_failed_batch_is_not_cached_and_can_resume(self):
        def invalid(items, options):
            data, meta = response(items, options)
            data["results"][0]["level"] = "L5"
            return data, meta
        result = self.run_model(transport=invalid)
        self.assertEqual(result["summary"]["new"], 0)
        self.assertEqual(result["summary"]["failed"], 6)
        self.assertEqual(self.run_model()["summary"]["new"], 100)

    def test_limit_dry_run_missing_key_and_no_rule_fallback(self):
        self.assertEqual(self.run_model(dry_run=True)["summary"]["requests"], 0)
        self.options["key"] = ""
        result = self.run_model()
        self.assertEqual(result["summary"]["status"], "needs_key")
        self.assertTrue(all(r["retailProfile"]["classifiedAccounts"] == 0 for r in candidate_profiles(self.capture, result)))
        self.options.update(key="test", limit=7)
        result = self.run_model()
        self.assertEqual(result["summary"]["new"], 7)
        self.assertEqual(result["summary"]["requests"], 2)
        self.assertEqual(self.run_model()["summary"]["reused"], 7)

    def test_identity_and_date_dedup(self):
        post = next(iter(sample_posts(self.capture).values()))
        key = content_key(post, self.capture["date"])
        self.assertEqual(key, content_key({**post, "id": "duplicate", "code": "other"}, self.capture["date"]))
        self.assertNotEqual(key, content_key({**post, "author": "other"}, self.capture["date"]))
        self.assertNotEqual(key, content_key(post, "2026-09-07"))

    def test_review_preserves_human_labels_and_only_evaluates_reviewed(self):
        package = self.run_model()
        path = save_review(self.root, self.capture, package)
        review = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(evaluate_review(review)["metrics"]["chase"]["agent"]["accuracy"])
        review["rows"][0]["human"].update(reviewed=True, chase=False, level="unknown", notes="已人工核对")
        path.write_text(json.dumps(review), encoding="utf-8")
        save_review(self.root, self.capture, package)
        updated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(updated["rows"][0]["human"]["notes"], "已人工核对")
        self.assertEqual(evaluate_review(updated)["metrics"]["chase"]["agent"]["accuracy"], 1)

    def test_lock_and_invalid_evidence(self):
        with run_lock(self.root):
            with self.assertRaises(RuntimeError):
                with run_lock(self.root): pass
        with run_lock(self.root): pass
        row = response([{"id": "a"}], {})[0]["results"][0]
        row.update(level="L1", evidence=["不存在"])
        with self.assertRaises(ValueError): validate_result(row, {"id": "a", "text": "还能追吗"})

    def test_responses_payload_and_incomplete_reply(self):
        from unittest.mock import MagicMock
        opener = MagicMock()
        output = {"status": "completed", "id": "response", "model": "gpt-5.4-mini", "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"results": []}'}]}]}
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(output).encode()
        with patch("sentiment.semantic_agent.urllib.request.build_opener", return_value=opener):
            self.assertEqual(call_openai([], self.options)[0], {"results": []})
            request = opener.open.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertFalse(payload["store"])
            self.assertTrue(payload["text"]["format"]["strict"])
            output["status"] = "incomplete"
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(output).encode()
            with self.assertRaises(ValueError): call_openai([], self.options)

    def test_replay_does_not_invoke_agent_without_explicit_flag(self):
        from sentiment.market_watch import atomic_json
        from sentiment.report import build_report
        market, capture = fixture()
        atomic_json(self.root / "public/data/market/latest.json", market)
        with patch("sentiment.market_reading.analyze_report", return_value={"status": "needs_key"}) as analyze:
            first = build_report(self.root, capture)
            analyze.assert_not_called()
            second = build_report(self.root, capture, agent=True)
            analyze.assert_called_once()
            self.assertEqual(first["sectors"], second["sectors"])
            self.assertEqual(first["thermometers"], second["thermometers"])

    def test_custom_chat_endpoint_payload_usage_and_truncation(self):
        from unittest.mock import MagicMock
        from sentiment.semantic_agent import endpoint, method_id
        for base in ("https://api.deepseek.com/", "https://open.bigmodel.cn/api/paas/v4"):
            options = {**self.options, "base_url": base, "api_type": "chat_completions"}
            opener = MagicMock()
            data = {"choices": [{"finish_reason": "stop", "message": {"content": '{"results": []}'}}], "usage": {"prompt_tokens": 12, "completion_tokens": 34}}
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
            with patch("sentiment.semantic_agent.urllib.request.build_opener", return_value=opener):
                result, meta = call_openai([], options)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, base.rstrip("/") + "/chat/completions")
                payload = json.loads(request.data)
                self.assertNotIn("reasoning", payload)
                self.assertNotIn("store", payload)
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                self.assertEqual(meta["usage"]["input_tokens"], 12)
                self.assertEqual(result, {"results": []})
                data["choices"][0]["finish_reason"] = "length"
                opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(data).encode()
                with self.assertRaises(ValueError): call_openai([], options)
            self.assertNotEqual(method_id("same-model"), method_id("same-model", options))
        for bad in ("http://example.com", "https://user:secret@example.com", "https://example.com?key=secret", "https://example.com/v1/chat/completions"):
            with self.assertRaises(ValueError): endpoint({"base_url": bad})

    def test_settings_loads_custom_url_without_exposing_key(self):
        from sentiment.semantic_agent import settings
        (self.root / ".env.agent.local").write_text("OPENAI_API_KEY=test\nOPENAI_BASE_URL=https://api.deepseek.com\nOPENAI_API_TYPE=chat_completions\nOPENAI_MODEL=deepseek-v4-flash\n", encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            config = settings(self.root)
        self.assertEqual(config["base_url"], "https://api.deepseek.com")
        self.assertEqual(config["api_type"], "chat_completions")
