import json
import os
import unittest
import urllib.error
from dataclasses import replace
from datetime import datetime, timezone
from unittest import mock

from src.feed import merge_entry, passes_relevance, select_items, to_blog_item, update_archive
from src.llm import PROMPT_VERSION, DeepSeekClient, LLMConfig, Verdict, apply_verdict, generate_digests, judge, make_client, prune_cache
from src.policy import UpdatePolicy, parse_policy

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)


def entry(key, title="A coding agent paper", relevance=40.0, category="papers"):
    return {
        "key": key,
        "title": title,
        "link": f"https://arxiv.org/abs/{key}",
        "category": category,
        "source_ids": ["arxiv_cs_se"],
        "summary": "An LLM coding agent.",
        "relevance": relevance,
        "keywords": [],
        "signals": [],
        "published_at": "2026-09-24T04:00:00Z",
    }


class FakeTransport:
    """按请求里的 id 回填分数；可指定哪些调用失败。"""

    def __init__(self, scores, fail_calls=(), content_override=None):
        self.scores = scores
        self.fail_calls = set(fail_calls)
        self.content_override = content_override
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(body)
        if len(self.calls) in self.fail_calls:
            raise urllib.error.URLError("boom")
        items = json.loads(body["messages"][1]["content"])["items"]
        results = [
            {
                "id": it["id"],
                "score": self.scores.get(it["title"], 10),
                "topics": ["编程智能体", "不存在的标签"],
                "summary_zh": "一句话总结",
                "reason_zh": "理由",
            }
            for it in items
        ]
        content = self.content_override if self.content_override is not None else json.dumps({"results": results}, ensure_ascii=False)
        return {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def config(**kw):
    return replace(LLMConfig(retries=0, batch_size=2, concurrency=1), **kw)


class JudgeTest(unittest.TestCase):
    def test_batches_cache_and_cleaning(self):
        transport = FakeTransport({"good": 150, "bad": 12})
        cfg = config()
        client = DeepSeekClient(cfg, "key", transport)
        cache = {}
        entries = [entry("1", "good"), entry("2", "bad"), entry("3", "good")]

        verdicts, report = judge(entries, cfg, client, cache, NOW)
        self.assertEqual(len(transport.calls), 2)  # batch_size=2 → 2 次调用
        self.assertEqual(report.judged, 3)
        self.assertEqual(verdicts["1"].score, 100.0)  # 超出范围被截断
        self.assertEqual(verdicts["2"].score, 12.0)
        self.assertEqual(verdicts["1"].topics, ["编程智能体"])  # 未知标签被过滤
        self.assertEqual(report.usage["prompt_tokens"], 200)
        self.assertEqual(set(cache), {"1", "2", "3"})

        # 第二次运行全部命中缓存，不再调用接口
        verdicts, report = judge(entries, cfg, client, cache, NOW)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(report.cached, 3)
        self.assertEqual(report.judged, 0)

    def test_cache_invalidated_by_model_or_prompt_version(self):
        cache = {"1": {**Verdict(80, [], "", "", "old-model", PROMPT_VERSION, "2026-09-20").to_json()}}
        transport = FakeTransport({"A coding agent paper": 70})
        cfg = config()
        _, report = judge([entry("1")], cfg, DeepSeekClient(cfg, "k", transport), cache, NOW)
        self.assertEqual(report.judged, 1)
        self.assertEqual(cache["1"]["model"], cfg.model)

    def test_failed_batch_falls_back_without_verdict(self):
        transport = FakeTransport({}, fail_calls={1})
        cfg = config()
        verdicts, report = judge([entry("1"), entry("2"), entry("3")], cfg, DeepSeekClient(cfg, "k", transport), {}, NOW)
        self.assertEqual(report.failed, 2)
        self.assertEqual(set(verdicts), {"3"})
        self.assertEqual(len(report.errors), 1)

    def test_malformed_output_counts_as_failure(self):
        transport = FakeTransport({}, content_override="not json")
        cfg = config()
        verdicts, report = judge([entry("1")], cfg, DeepSeekClient(cfg, "k", transport), {}, NOW)
        self.assertEqual(verdicts, {})
        self.assertEqual(report.failed, 1)

    def test_budget_limits_new_judgements(self):
        transport = FakeTransport({})
        cfg = config(max_items_per_run=2)
        _, report = judge([entry(str(i)) for i in range(5)], cfg, DeepSeekClient(cfg, "k", transport), {}, NOW)
        self.assertEqual(report.judged, 2)
        self.assertEqual(report.skipped_budget, 3)

    def test_request_body_thinking_modes(self):
        body = DeepSeekClient(config(reasoning_effort="none"), "k")._request_body([])
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["response_format"], {"type": "json_object"})
        body = DeepSeekClient(config(reasoning_effort="low"), "k")._request_body([])
        self.assertEqual(body["thinking"], {"type": "enabled", "reasoning_effort": "low"})

    def test_make_client_requires_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            client, reason = make_client(LLMConfig())
            self.assertIsNone(client)
            self.assertIn("DEEPSEEK_API_KEY", reason)
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}):
            client, reason = make_client(LLMConfig())
            self.assertIsNotNone(client)
            self.assertIsNone(reason)
            client, reason = make_client(LLMConfig(enabled=False))
            self.assertIsNone(client)

    def test_prune_cache(self):
        cache = {"keep": {"judged_on": "2026-01-01"}, "recent": {"judged_on": "2026-09-20"}, "old": {"judged_on": "2026-08-01"}}
        self.assertEqual(set(prune_cache(cache, {"keep"}, NOW, 14)), {"keep", "recent"})


class DigestTest(unittest.TestCase):
    def transport(self, calls, fail_titles=()):
        def post(url, headers, body, timeout):
            calls.append(body)
            content = body["messages"][1]["content"]
            if any(t in content for t in fail_titles):
                return {"choices": [{"message": {"content": "{}"}}]}  # 缺少 problem → 格式错误
            return {
                "choices": [{"message": {"content": json.dumps({
                    "problem": "要解决的问题",
                    "method": ["方法一", "方法二", "方法三", "方法四"],
                    "results": "单条结果",
                    "takeaways": ["启示"],
                    "limitations": "",
                }, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
            }
        return post

    def test_generate_cache_and_cleaning(self):
        calls, fetched = [], []
        cfg = config(digest_concurrency=1)
        client = DeepSeekClient(cfg, "k", self.transport(calls))

        def fetch(e):
            fetched.append(e["key"])
            return ("full text", "fulltext") if e["key"] == "1" else ("abstract", "abstract")

        entries = [entry("1"), entry("2"), entry("3", category="datasets")]
        cache = {}
        digests, report = generate_digests(entries, cfg, client, cache, NOW, fetch=fetch)
        self.assertEqual(set(digests), {"1", "2"})  # 数据集不生成解读
        self.assertEqual(report.generated, 2)
        self.assertEqual(report.fulltext, 1)
        self.assertEqual(digests["1"]["method"], ["方法一", "方法二", "方法三"])  # 最多 3 条
        self.assertEqual(digests["1"]["results"], ["单条结果"])  # 字符串转列表
        self.assertEqual(digests["2"]["basis"], "abstract")
        self.assertIn("论文正文", calls[0]["messages"][1]["content"])
        self.assertEqual(report.usage["prompt_tokens"], 2000)

        digests, report = generate_digests(entries, cfg, client, cache, NOW, fetch=fetch)
        self.assertEqual(report.cached, 2)
        self.assertEqual(len(calls), 2)  # 全部命中缓存
        self.assertEqual(fetched, ["1", "2"])

    def test_failures_and_disabled(self):
        calls = []
        cfg = config(digest_concurrency=1)
        client = DeepSeekClient(cfg, "k", self.transport(calls, fail_titles=("bad",)))
        entries = [entry("1", title="bad paper"), entry("2")]
        digests, report = generate_digests(entries, cfg, client, {}, NOW, fetch=lambda e: None if e["key"] == "2" else ("t", "abstract"))
        self.assertEqual(digests, {})
        self.assertEqual(report.failed, 2)
        # 未配置 key 或关闭时不调用
        digests, report = generate_digests([entry("1")], cfg, None, {}, NOW, fetch=lambda e: ("t", "abstract"))
        self.assertEqual((digests, report.generated), ({}, 0))
        digests, report = generate_digests([entry("1")], replace(cfg, digest_enabled=False), client, {}, NOW)
        self.assertEqual(report.generated, 0)

    def test_blog_item_includes_digest(self):
        policy = UpdatePolicy(min_relevance=35, window_days=7, max_items=10, max_datasets=2, retention_days=14)
        archive = update_archive({}, {"1": entry("1")}, policy, NOW, set())
        selected = select_items(archive, policy, NOW)
        digest = {"problem": "P", "method": ["M"], "results": [], "takeaways": [], "limitations": "", "basis": "fulltext", "model": "m"}
        item = to_blog_item(selected[0], digest)
        self.assertEqual(item["digest"]["problem"], "P")
        self.assertNotIn("model", item["digest"])
        self.assertIsNone(to_blog_item(selected[0])["digest"])


class PipelineIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.policy = UpdatePolicy(min_relevance=35, window_days=7, max_items=10, max_datasets=2, retention_days=14)

    def test_llm_threshold_overrides_rules(self):
        high_rule_low_llm = entry("1", relevance=80)
        apply_verdict(high_rule_low_llm, Verdict(30, [], "", "", "m", PROMPT_VERSION, "2026-09-24"))
        low_rule_high_llm = entry("2", relevance=12)
        apply_verdict(low_rule_high_llm, Verdict(85, ["训练数据"], "中文总结", "理由", "m", PROMPT_VERSION, "2026-09-24"))
        self.assertFalse(passes_relevance(high_rule_low_llm, self.policy))
        self.assertTrue(passes_relevance(low_rule_high_llm, self.policy))
        self.assertEqual(low_rule_high_llm["rule_relevance"], 12)

        archive = update_archive({}, {"1": high_rule_low_llm, "2": low_rule_high_llm}, self.policy, NOW, set())
        self.assertEqual(list(archive), ["2"])
        item = to_blog_item(select_items(archive, self.policy, NOW)[0])
        self.assertEqual(item["relevance_source"], "llm")
        self.assertEqual(item["summary_zh"], "中文总结")
        self.assertEqual(item["topics"], ["训练数据"])
        self.assertEqual(item["scores"]["relevance"], 85)

    def test_merge_prefers_llm_verdict(self):
        rules_only = entry("1", relevance=90)
        judged = entry("1", relevance=90)
        apply_verdict(judged, Verdict(40, [], "", "", "m", PROMPT_VERSION, "2026-09-24"))
        self.assertEqual(merge_entry(rules_only, judged)["relevance"], 40)
        self.assertEqual(merge_entry(judged, rules_only)["relevance"], 40)
        self.assertEqual(merge_entry(entry("1", relevance=20), entry("1", relevance=50))["relevance"], 50)

    def test_policy_llm_section(self):
        policy = parse_policy({"llm": {"model": "deepseek-flash", "reasoning_effort": "low", "min_score": 70}})
        self.assertEqual(policy.llm.reasoning_effort, "low")
        self.assertEqual(policy.llm.min_score, 70)
        self.assertEqual(policy.summary()["llm"]["model"], "deepseek-flash")
        with self.assertRaises(ValueError):
            parse_policy({"llm": {"reasoning_effort": "turbo"}})


if __name__ == "__main__":
    unittest.main()
