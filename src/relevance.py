"""AI Coding 主题相关性工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AI_CODING_KEYWORDS: dict[str, float] = {
    "code generation": 2.0,
    "codegen": 1.6,
    "agentic coding": 2.2,
    "coding agent": 1.8,
    "software engineering": 1.3,
    "swe-bench": 2.4,
    "repo reasoning": 2.1,
    "repository-level": 1.8,
    "code llm": 2.1,
    "code language model": 1.8,
    "program repair": 1.5,
    "bug fixing": 1.4,
    "unit test generation": 1.4,
    "developer productivity": 1.1,
    "tool use": 1.2,
    "autonomous coding": 2.0,
}

NEGATIVE_KEYWORDS: dict[str, float] = {
    "medical imaging": -2.0,
    "radiology": -1.6,
    "pathology": -1.4,
    "drug discovery": -1.2,
    "genomics": -1.1,
    "pure vision": -1.3,
    "image segmentation": -1.4,
    "object detection": -1.2,
    "text-to-image": -1.2,
    "fashion generation": -1.0,
    "protein folding": -1.5,
    "autonomous driving perception": -1.3,
}


@dataclass(slots=True)
class RelevanceResult:
    score: float
    positive_hits: list[str]
    negative_hits: list[str]


def _normalized_text(parts: Iterable[str]) -> str:
    return " ".join(parts).strip().lower()


def keyword_relevance(title: str = "", abstract: str = "", summary: str = "") -> RelevanceResult:
    """根据标题/摘要/总结进行关键词相关性打分。"""
    text = _normalized_text([title, abstract, summary])

    positive_hits = [kw for kw in AI_CODING_KEYWORDS if kw in text]
    negative_hits = [kw for kw in NEGATIVE_KEYWORDS if kw in text]

    score = sum(AI_CODING_KEYWORDS[kw] for kw in positive_hits)
    score += sum(NEGATIVE_KEYWORDS[kw] for kw in negative_hits)

    return RelevanceResult(
        score=max(score, 0.0),
        positive_hits=positive_hits,
        negative_hits=negative_hits,
    )
