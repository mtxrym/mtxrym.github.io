"""AI Coding 主题相关性：双轴关键词模型。

一篇内容要同时具备两类信号才算“AI 编程”：
- 代码信号：代码生成、程序修复、SWE-bench、代码评审……（带权重）
- AI 信号：LLM、agent、语言模型……（只判断有没有）

只有代码信号没有 AI 信号（例如传统软件工程研究），或只有 AI 信号没有代码信号
（例如通用 agent 推理），相关性都会被显著压低。标题命中比摘要命中权重更高。
最终分数通过饱和函数映射到 0–100。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from math import exp
from typing import Iterable

# 代码 / 软件工程信号。以 * 结尾表示前缀匹配（如 decompil* 匹配 decompiler / decompilation）。
AI_CODING_KEYWORDS: dict[str, float] = {
    # 核心任务
    "code generation": 3.0,
    "program synthesis": 3.0,
    "code completion": 3.0,
    "code llm": 3.5,
    "code model": 2.5,
    "code language model": 3.5,
    "language models for code": 3.5,
    "llms for code": 3.5,
    "code reasoning": 3.0,
    "code agent": 3.5,
    "coding agent": 3.5,
    "software agent": 3.0,
    "software engineering agent": 3.5,
    "swe-agent": 3.5,
    "agentic coding": 3.5,
    "vibe coding": 3.0,
    "pair programming": 2.5,
    "code assistant": 3.0,
    "coding assistant": 3.0,
    "copilot": 2.0,
    "claude code": 3.0,
    "codex": 2.0,
    # 评测
    "swe-bench": 4.0,
    "humaneval": 3.0,
    "mbpp": 2.5,
    "livecodebench": 3.0,
    "bigcodebench": 3.0,
    "repobench": 3.0,
    "terminal-bench": 3.0,
    "codeforces": 2.0,
    # 仓库级 / 工程流程
    "repository-level": 3.0,
    "repo-level": 3.0,
    "codebase": 2.0,
    "issue resolution": 3.0,
    "github issue": 2.5,
    "pull request": 2.0,
    "github": 1.5,
    "agentic engineering": 2.5,
    "commit message": 2.0,
    "code review": 2.5,
    # 质量与维护
    "program repair": 3.0,
    "bug fixing": 2.5,
    "bug localization": 2.5,
    "fault localization": 2.5,
    "vulnerability detection": 2.0,
    "vulnerability repair": 2.5,
    "test generation": 2.5,
    "unit test": 2.0,
    "test case": 1.5,
    "fuzzing": 1.5,
    "code translation": 2.5,
    "code migration": 2.5,
    "refactoring": 2.0,
    "decompil*": 1.5,
    "text-to-sql": 2.0,
    "code search": 2.0,
    "code summarization": 2.0,
    # 泛化信号（权重低）
    "software engineering": 1.5,
    "software development": 1.5,
    "programming": 1.5,
    "source code": 1.5,
    "developer": 1.0,
    "compiler": 1.0,
    "static analysis": 1.0,
    "code": 1.0,
}

# AI 信号：只判断是否存在
AI_SIGNALS: tuple[str, ...] = (
    "llm",
    "large language model",
    "language model",
    "foundation model",
    "agent",
    "agentic",
    "gpt",
    "transformer",
    "generative ai",
    "neural",
    "deep learning",
    "reinforcement learning",
    "fine-tun*",
    "prompt*",
    "in-context learning",
    "copilot",
    "codex",
    "swe-bench",
    "humaneval",
)

NEGATIVE_KEYWORDS: dict[str, float] = {
    "medical imaging": -3.0,
    "radiology": -2.5,
    "pathology": -2.0,
    "drug discovery": -2.0,
    "genomics": -2.0,
    "protein": -1.5,
    "image segmentation": -2.0,
    "object detection": -2.0,
    "text-to-image": -2.0,
    "video generation": -2.0,
    "speech recognition": -1.5,
    "autonomous driving": -1.5,
    "robot*": -1.0,
    # “programming” 在运筹 / 算法语境下与写代码无关
    "linear programming": -2.5,
    "integer programming": -2.5,
    "quadratic programming": -2.5,
    "mathematical programming": -2.5,
    "dynamic programming": -2.0,
    # 语言学里的“语码转换”
    "code-switching": -2.5,
    "code-mixing": -2.5,
}

# 摘要里的“代码已开源”之类套话不代表主题相关，打分前先去掉（影响力打分会单独识别它们）
BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(
        r"(?:our|the|all)?\s*(?:source\s+)?code(?:\s*(?:,|and)\s*(?:the\s+)?\w+)*\s+"
        r"(?:is|are|will\s+be|has\s+been|have\s+been)\s+(?:publicly\s+|made\s+|openly\s+|freely\s+)?"
        r"(?:available|released|open[- ]sourced|accessible)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:code|data|models?)\s*(?:and\s+\w+\s*)?:\s*$", re.IGNORECASE),
)

TITLE_MULTIPLIER = 1.6
NO_AI_SIGNAL_FACTOR = 0.3
# 标题里一个代码相关词都没有时（例如只在摘要里把 SWE-bench 当评测集提了一句），整体打折
BODY_ONLY_FACTOR = 0.6
SATURATION = 7.0


@dataclass(slots=True)
class RelevanceResult:
    score: float
    positive_hits: list[str]
    negative_hits: list[str]
    has_ai_signal: bool = False
    raw_score: float = 0.0
    title_hits: list[str] = field(default_factory=list)


@lru_cache(maxsize=None)
def _pattern(term: str) -> re.Pattern[str]:
    if term.endswith("*"):
        body = re.escape(term[:-1]) + r"[\w-]*"
    else:
        body = re.escape(term) + r"(?:s|es)?"
    # 连字符视为词边界：UltraData-Code 能匹配 code，multi-agent 能匹配 agent
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _contains(term: str, text: str) -> bool:
    return bool(text) and _pattern(term).search(text) is not None


def _normalized_text(parts: Iterable[str]) -> str:
    text = " ".join(p for p in parts if p)
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub(" ", text)
    # 数据集 id（如 openbmb/UltraData-Code）拆成单词，方便匹配
    return re.sub(r"[/_]", " ", text).strip()


def keyword_relevance(
    title: str = "",
    abstract: str = "",
    summary: str = "",
    *,
    prefiltered: bool = False,
) -> RelevanceResult:
    """根据标题 / 摘要打出 0–100 的相关性分数。

    prefiltered=True 表示内容来自已限定主题的查询（如 HF 数据集搜索 "code"），视为具备 AI 信号。
    """
    title_text = _normalized_text([title])
    body_text = _normalized_text([abstract, summary])
    full_text = f"{title_text} {body_text}"

    positive_hits: list[str] = []
    title_hits: list[str] = []
    raw = 0.0
    for term, weight in AI_CODING_KEYWORDS.items():
        in_title = _contains(term, title_text)
        if in_title or _contains(term, body_text):
            positive_hits.append(term)
            raw += weight * (TITLE_MULTIPLIER if in_title else 1.0)
            if in_title:
                title_hits.append(term)

    negative_hits = [term for term in NEGATIVE_KEYWORDS if _contains(term, full_text)]
    raw += sum(NEGATIVE_KEYWORDS[term] for term in negative_hits)

    has_ai_signal = prefiltered or any(_contains(term, full_text) for term in AI_SIGNALS)
    if not has_ai_signal:
        raw *= NO_AI_SIGNAL_FACTOR
    if not title_hits:
        raw *= BODY_ONLY_FACTOR

    raw = max(raw, 0.0)
    score = 100.0 * (1.0 - exp(-raw / SATURATION))
    return RelevanceResult(
        score=round(score, 1),
        positive_hits=positive_hits,
        negative_hits=negative_hits,
        has_ai_signal=has_ai_signal,
        raw_score=round(raw, 2),
        title_hits=title_hits,
    )


def display_keywords(result: RelevanceResult, limit: int = 4) -> list[str]:
    """挑出最有代表性的命中词作为主题标签：标题命中优先，泛化词（code / developer 等）排除。"""
    generic = {"code", "developer", "programming", "compiler", "software engineering", "software development", "source code"}
    ranked = sorted(
        (hit for hit in result.positive_hits if hit not in generic),
        key=lambda hit: (hit not in result.title_hits, -AI_CODING_KEYWORDS[hit]),
    )
    return [hit.rstrip("*") for hit in ranked[:limit]]
