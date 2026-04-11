"""AI Coding 重要性评分。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp
from typing import Iterable

from src.relevance import keyword_relevance


@dataclass(slots=True)
class Item:
    title: str
    item_type: str  # paper | dataset | repo | post
    url: str = ""
    summary: str = ""
    abstract: str = ""
    published_at: datetime | None = None
    stars: int = 0
    upvotes: int = 0
    trending_rank: int | None = None
    benchmark_improvement: bool = False
    open_source_code: bool = False
    reproducible_experiment: bool = False


@dataclass(slots=True)
class ScoreBreakdown:
    time_decay_score: float
    popularity_score: float
    relevance_score: float
    impact_score: float
    importance_score: float
    why_it_matters: str


def _days_since(published_at: datetime | None, now: datetime) -> float:
    if not published_at:
        return 180.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return max((now - published_at).total_seconds() / 86400.0, 0.0)


def compute_time_decay_score(published_at: datetime | None, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    days = _days_since(published_at, now)
    return 100.0 * exp(-days / 45.0)


def compute_popularity_score(stars: int = 0, upvotes: int = 0, trending_rank: int | None = None) -> float:
    trending_boost = 0.0 if trending_rank is None else max(0.0, 20.0 - min(trending_rank, 20))
    return min(100.0, stars * 0.15 + upvotes * 0.2 + trending_boost)


def compute_relevance_score(title: str = "", abstract: str = "", summary: str = "") -> float:
    result = keyword_relevance(title=title, abstract=abstract, summary=summary)
    semantic_bonus = 8.0 if any(token in (abstract + summary).lower() for token in ["agent", "repository", "benchmark", "code"]) else 0.0
    return min(100.0, result.score * 12.0 + semantic_bonus)


def compute_impact_score(
    benchmark_improvement: bool,
    open_source_code: bool,
    reproducible_experiment: bool,
) -> float:
    score = 0.0
    if benchmark_improvement:
        score += 45.0
    if open_source_code:
        score += 35.0
    if reproducible_experiment:
        score += 20.0
    return min(100.0, score)


def why_it_matters(item: Item, breakdown: ScoreBreakdown) -> str:
    reasons: list[str] = []
    if breakdown.relevance_score >= 60:
        reasons.append("高度聚焦 AI Coding 核心问题")
    if item.benchmark_improvement:
        reasons.append("包含 benchmark 提升信号")
    if item.open_source_code:
        reasons.append("提供开源代码便于落地")
    if item.reproducible_experiment:
        reasons.append("实验可复现便于验证")
    if breakdown.time_decay_score >= 70:
        reasons.append("发布较新")
    if not reasons:
        reasons.append("在代码智能方向具备稳定参考价值")
    return "；".join(reasons) + "。"


def score_item(item: Item, now: datetime | None = None) -> ScoreBreakdown:
    time_score = compute_time_decay_score(item.published_at, now=now)
    pop_score = compute_popularity_score(item.stars, item.upvotes, item.trending_rank)
    rel_score = compute_relevance_score(item.title, item.abstract, item.summary)
    impact_score = compute_impact_score(
        benchmark_improvement=item.benchmark_improvement,
        open_source_code=item.open_source_code,
        reproducible_experiment=item.reproducible_experiment,
    )

    importance = (
        time_score * 0.2
        + pop_score * 0.25
        + rel_score * 0.35
        + impact_score * 0.2
    )

    placeholder = ScoreBreakdown(
        time_decay_score=time_score,
        popularity_score=pop_score,
        relevance_score=rel_score,
        impact_score=impact_score,
        importance_score=importance,
        why_it_matters="",
    )
    placeholder.why_it_matters = why_it_matters(item, placeholder)
    return placeholder


def top_n(items: Iterable[Item], n: int = 10, now: datetime | None = None) -> list[tuple[Item, ScoreBreakdown]]:
    ranked = [(item, score_item(item, now=now)) for item in items]
    ranked.sort(key=lambda row: row[1].importance_score, reverse=True)
    return ranked[:n]


def render_markdown_report(items: Iterable[Item], n: int = 10, now: datetime | None = None) -> str:
    ranked = top_n(items, n=n, now=now)
    papers = [(i, s) for i, s in ranked if i.item_type == "paper"]
    datasets = [(i, s) for i, s in ranked if i.item_type == "dataset"]

    def _section(title: str, rows: list[tuple[Item, ScoreBreakdown]]) -> str:
        lines = [f"## {title}", ""]
        if not rows:
            lines.append("- 暂无结果")
            lines.append("")
            return "\n".join(lines)
        for item, score in rows:
            lines.append(f"- **{item.title}** (score={score.importance_score:.2f})")
            if item.url:
                lines.append(f"  - link: {item.url}")
            lines.append(f"  - why_it_matters: {score.why_it_matters}")
        lines.append("")
        return "\n".join(lines)

    return "\n".join(
        [
            "# AI Coding Importance Report",
            "",
            _section("Top Papers for AI Coding", papers),
            _section("Top Datasets for AI Coding", datasets),
        ]
    )
