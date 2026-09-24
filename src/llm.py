"""大模型复核：用 DeepSeek（OpenAI 兼容接口）对候选条目做相关性判定。

流程：关键词规则负责“召回”（宽松初筛），模型负责“判定”——逐条打 0–100 分、
选主题标签、写中文一句话总结。判定结果写入缓存（data/llm_cache.json），
同一条内容只调用一次模型；模型或提示词版本变化时才会重新判定。

没有配置 API Key、接口失败或返回格式不对时，相关条目自动退回规则打分，不影响数据更新。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

PROMPT_VERSION = "2026-09-24.1"

TOPICS: tuple[str, ...] = (
    "代码生成",
    "编程智能体",
    "程序修复",
    "测试与验证",
    "代码评审",
    "代码理解与检索",
    "评测基准",
    "安全与漏洞",
    "训练数据",
    "模型训练与推理",
    "开发者与工具研究",
    "其他",
)

SYSTEM_PROMPT = f"""你是“AI 编程”方向的资深编辑，为一个中文技术资讯站筛选内容。
“AI 编程”指：用 AI / 大模型编写、理解、修复、测试、评审代码，或自主完成软件工程任务；
也包括为此服务的评测基准、训练数据、智能体框架与工具，以及开发者使用 AI 编程工具的实证研究。

对每条内容给出 0–100 的相关性分数：
- 90–100：核心贡献就是 AI 编程（代码生成、编程智能体、程序修复、SWE-bench 类评测、代码大模型训练数据等）。
- 70–89：主体与 AI 编程密切相关，但偏特定场景或较间接（如用大模型检测智能合约漏洞、编程智能体的记忆与上下文管理、AI 编程工具的使用研究）。
- 40–69：部分相关：代码只是多个应用或评测领域之一，或通用智能体技术对编程有明确应用。
- 0–39：基本无关：只把编程基准当作众多评测之一的通用模型研究、不涉及 AI 的传统软件工程、其他领域。
数据集：用于训练或评测代码模型 / 编程智能体的数据集算高相关；描述为空时按名称谨慎判断，拿不准给 50 左右；明显是灌水或与代码无关的给低分。
只看内容本身，不要因为标题里出现 agent、code 等词就给高分。

topics 从下列标签中选 1–3 个：{"、".join(TOPICS)}。
summary_zh：不超过 60 个汉字，用中文一句话说清它做了什么（专有名词保留英文）。
reason_zh：不超过 30 个汉字，说明打分理由。

只输出 JSON 对象，格式：
{{"results": [{{"id": "<输入中的 id>", "score": <整数>, "topics": ["..."], "summary_zh": "...", "reason_zh": "..."}}]}}
每个输入 id 必须恰好出现一次。"""


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = True
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    model_label: str = "DeepSeek-V4.1-Flash"
    api_key_env: str = "DEEPSEEK_API_KEY"
    reasoning_effort: str = "none"
    candidate_min_relevance: float = 8.0
    min_score: float = 60.0
    batch_size: int = 10
    max_items_per_run: int = 200
    concurrency: int = 4
    timeout_seconds: int = 90
    retries: int = 2
    abstract_chars: int = 700


@dataclass(slots=True)
class Verdict:
    score: float
    topics: list[str]
    summary_zh: str
    reason_zh: str
    model: str
    prompt_version: str
    judged_on: str

    def to_json(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "topics": self.topics,
            "summary_zh": self.summary_zh,
            "reason_zh": self.reason_zh,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "judged_on": self.judged_on,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Verdict":
        return cls(
            score=float(data.get("score", 0)),
            topics=list(data.get("topics") or []),
            summary_zh=str(data.get("summary_zh") or ""),
            reason_zh=str(data.get("reason_zh") or ""),
            model=str(data.get("model") or ""),
            prompt_version=str(data.get("prompt_version") or ""),
            judged_on=str(data.get("judged_on") or ""),
        )


@dataclass(slots=True)
class JudgeReport:
    enabled: bool
    reason: str | None = None
    candidates: int = 0
    cached: int = 0
    judged: int = 0
    failed: int = 0
    skipped_budget: int = 0
    errors: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


# 可注入的 HTTP 调用：(url, headers, body, timeout) -> 响应 JSON
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def http_post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class DeepSeekClient:
    def __init__(self, config: LLMConfig, api_key: str, transport: Transport = http_post_json) -> None:
        self.config = config
        self.api_key = api_key
        self.transport = transport

    def _request_body(self, items: list[dict[str, str]]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 300 + 220 * len(items),
        }
        if self.config.reasoning_effort in ("", "none"):
            body["thinking"] = {"type": "disabled"}
            body["temperature"] = 0
        else:
            body["thinking"] = {"type": "enabled", "reasoning_effort": self.config.reasoning_effort}
        return body

    def classify_batch(self, items: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
        """返回 {id: 原始结果}, usage。失败时抛异常。"""
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = self._request_body(items)
        last_error: Exception | None = None
        for attempt in range(self.config.retries + 1):
            try:
                data = self.transport(url, headers, body, self.config.timeout_seconds)
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                results = parsed.get("results") if isinstance(parsed, dict) else None
                if not isinstance(results, list):
                    raise ValueError("模型输出缺少 results 数组")
                by_id = {str(r.get("id")): r for r in results if isinstance(r, dict)}
                usage = {k: int(v) for k, v in (data.get("usage") or {}).items() if isinstance(v, int)}
                return by_id, usage
            except urllib.error.HTTPError as exc:
                last_error = exc
                # 401/403/400 等重试无意义；429 与 5xx 退避重试
                if exc.code < 500 and exc.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, IndexError, ValueError) as exc:
                last_error = exc
            if attempt < self.config.retries:
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f"DeepSeek 调用失败：{last_error}") from last_error


def _clean_verdict(raw: dict[str, Any], config: LLMConfig, today: str) -> Verdict | None:
    try:
        score = float(raw.get("score"))
    except (TypeError, ValueError):
        return None
    topics = [t for t in (raw.get("topics") or []) if t in TOPICS][:3]
    return Verdict(
        score=round(max(0.0, min(100.0, score)), 1),
        topics=topics,
        summary_zh=str(raw.get("summary_zh") or "").strip()[:120],
        reason_zh=str(raw.get("reason_zh") or "").strip()[:80],
        model=config.model,
        prompt_version=PROMPT_VERSION,
        judged_on=today,
    )


def _item_payload(entry: dict[str, Any], item_id: str, config: LLMConfig) -> dict[str, str]:
    return {
        "id": item_id,
        "type": "数据集" if entry.get("category") == "datasets" else "论文",
        "title": entry.get("title") or "",
        "abstract": (entry.get("summary") or "")[: config.abstract_chars],
    }


def judge(
    entries: Iterable[dict[str, Any]],
    config: LLMConfig,
    client: DeepSeekClient | None,
    cache: dict[str, dict[str, Any]],
    now: datetime,
) -> tuple[dict[str, Verdict], JudgeReport]:
    """对候选条目给出判定：优先读缓存，其余调用模型。返回 {key: Verdict} 与本次统计。"""
    today = now.astimezone(timezone.utc).date().isoformat()
    report = JudgeReport(enabled=client is not None)
    verdicts: dict[str, Verdict] = {}
    pending: list[dict[str, Any]] = []

    seen: set[str] = set()
    for entry in entries:
        key = entry["key"]
        if key in seen:
            continue
        seen.add(key)
        report.candidates += 1
        cached = cache.get(key)
        if cached and cached.get("model") == config.model and cached.get("prompt_version") == PROMPT_VERSION:
            verdicts[key] = Verdict.from_json(cached)
            report.cached += 1
        else:
            pending.append(entry)

    if client is None or not pending:
        return verdicts, report

    if len(pending) > config.max_items_per_run:
        report.skipped_budget = len(pending) - config.max_items_per_run
        pending = pending[: config.max_items_per_run]

    batches = [pending[i : i + config.batch_size] for i in range(0, len(pending), config.batch_size)]

    def run(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]] | None, dict[str, int], str | None]:
        ids = {f"i{n}": entry for n, entry in enumerate(batch)}
        try:
            results, usage = client.classify_batch([_item_payload(e, i, config) for i, e in ids.items()])
            return batch, {ids[i]["key"]: r for i, r in results.items() if i in ids}, usage, None
        except Exception as exc:  # noqa: BLE001 - 单批失败只影响这一批
            return batch, None, {}, str(exc)[:200]

    with ThreadPoolExecutor(max_workers=max(1, config.concurrency)) as pool:
        for batch, results, usage, error in pool.map(run, batches):
            for name, value in usage.items():
                report.usage[name] = report.usage.get(name, 0) + value
            if results is None:
                report.failed += len(batch)
                report.errors.append(error or "unknown error")
                continue
            for entry in batch:
                verdict = _clean_verdict(results.get(entry["key"], {}), config, today)
                if verdict is None:
                    report.failed += 1
                    continue
                verdicts[entry["key"]] = verdict
                cache[entry["key"]] = verdict.to_json()
                report.judged += 1
    return verdicts, report


def apply_verdict(entry: dict[str, Any], verdict: Verdict) -> None:
    """用模型判定覆盖规则相关性，保留规则分以便对照。"""
    if entry.get("relevance_source") != "llm":
        entry["rule_relevance"] = entry.get("relevance", 0)
    entry["relevance"] = verdict.score
    entry["relevance_source"] = "llm"
    entry["topics"] = verdict.topics
    entry["summary_zh"] = verdict.summary_zh
    entry["reason_zh"] = verdict.reason_zh


def prune_cache(cache: dict[str, dict[str, Any]], keep_keys: set[str], now: datetime, retention_days: int) -> dict[str, dict[str, Any]]:
    """保留仍在使用的条目，以及保留期内判定过的条目（避免规则分低的条目被反复送审）。"""
    cutoff = (now - timedelta(days=retention_days)).astimezone(timezone.utc).date().isoformat()
    return {k: v for k, v in cache.items() if k in keep_keys or (v.get("judged_on") or "") >= cutoff}


def make_client(config: LLMConfig, transport: Transport = http_post_json) -> tuple[DeepSeekClient | None, str | None]:
    """返回 (client, 未启用原因)。"""
    if not config.enabled:
        return None, "已在 update_policy.yaml 中关闭"
    api_key = os.environ.get(config.api_key_env, "").strip()
    if not api_key:
        return None, f"未配置 {config.api_key_env}"
    return DeepSeekClient(config, api_key, transport), None


def log(message: str) -> None:
    print(f"[llm]  {message}", file=sys.stderr)
