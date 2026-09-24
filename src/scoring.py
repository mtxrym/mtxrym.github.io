"""AI Coding 重要性评分。

综合得分（0–100）= 相关性 / 热度 / 新鲜度 / 影响力 四个分项（各 0–100）的加权和，
权重和新鲜度半衰期来自 config/update_policy.yaml。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import log10
from typing import Iterable, Mapping

from src.relevance import RelevanceResult, display_keywords, keyword_relevance

DEFAULT_WEIGHTS: dict[str, float] = {"relevance": 0.5, "popularity": 0.2, "freshness": 0.2, "impact": 0.1}
DEFAULT_HALF_LIFE_DAYS = 3.0


@dataclass(slots=True)
class Item:
    title: str
    item_type: str  # paper | dataset | repo | post
    url: str = ""
    summary: str = ""
    abstract: str = ""
    published_at: datetime | None = None
    stars: int = 0  # GitHub star
    upvotes: int = 0  # HF Daily Papers 点赞
    likes: int = 0  # HF 数据集 likes
    trending_rank: int | None = None
    benchmark_improvement: bool = False
    open_source_code: bool = False
    reproducible_experiment: bool = False
    prefiltered: bool = False
    code_url: str = ""


@dataclass(slots=True)
class ScoreBreakdown:
    time_decay_score: float
    popularity_score: float
    relevance_score: float
    impact_score: float
    importance_score: float
    why_it_matters: str
    keywords: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


_CODE_RELEASE = re.compile(
    r"github\.com/|gitlab\.com/|huggingface\.co/|"
    r"code\s+(?:and\s+\w+\s+)?(?:is|are|will\s+be)\s+(?:publicly\s+|made\s+|openly\s+)?(?:available|released)|"
    r"\bopen[- ]source[sd]?\b|we\s+(?:release|open-source|publicly\s+release)",
    re.IGNORECASE,
)
_NEW_BENCHMARK = re.compile(
    r"\b(?:we|this\s+paper)\s+(?:introduce|present|propose|construct|build|release)s?\b[^.]{0,80}\b(?:benchmark|dataset|suite|leaderboard)",
    re.IGNORECASE,
)
_SOTA = re.compile(r"state[- ]of[- ]the[- ]art|\boutperform|\bsurpass|\bnew\s+sota\b", re.IGNORECASE)


def _days_since(published_at: datetime | None, now: datetime) -> float:
    """按 UTC 日历天计算，保证同一天内多次运行得分一致，避免数据文件无意义地变化。"""
    if not published_at:
        return 180.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta = now.astimezone(timezone.utc).date() - published_at.astimezone(timezone.utc).date()
    return float(max(delta.days, 0))


def compute_time_decay_score(
    published_at: datetime | None,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    now = now or datetime.now(timezone.utc)
    return 100.0 * 0.5 ** (_days_since(published_at, now) / half_life_days)


def _log_scale(value: int, per_decade: float) -> float:
    return min(100.0, per_decade * log10(1 + max(value, 0)))


def compute_popularity_score(
    stars: int = 0,
    upvotes: int = 0,
    trending_rank: int | None = None,
    likes: int = 0,
) -> float:
    """对数刻度，取各项热度信号中最强的一个。

    HF 点赞：10 → 31，100 → 60，1000 → 90；GitHub star / 数据集 likes：100 → 40，1000 → 60。
    """
    trending_boost = 0.0 if trending_rank is None else max(0.0, 40.0 - 2.0 * min(trending_rank, 20))
    return max(
        _log_scale(upvotes, 30.0),
        _log_scale(stars, 20.0),
        _log_scale(likes, 20.0),
        trending_boost,
    )


def compute_relevance_score(title: str = "", abstract: str = "", summary: str = "", prefiltered: bool = False) -> float:
    return keyword_relevance(title=title, abstract=abstract, summary=summary, prefiltered=prefiltered).score


def detect_impact_signals(item: Item) -> list[str]:
    text = f"{item.title}\n{item.abstract}\n{item.summary}"
    signals: list[str] = []
    if item.open_source_code or item.code_url or _CODE_RELEASE.search(text):
        signals.append("open_source_code")
    if item.benchmark_improvement or _NEW_BENCHMARK.search(text):
        signals.append("new_benchmark")
    if _SOTA.search(text):
        signals.append("sota")
    if item.reproducible_experiment:
        signals.append("reproducible")
    return signals


def compute_impact_score(
    benchmark_improvement: bool,
    open_source_code: bool,
    reproducible_experiment: bool,
    sota: bool = False,
) -> float:
    score = 0.0
    if open_source_code:
        score += 40.0
    if benchmark_improvement:
        score += 35.0
    if sota:
        score += 15.0
    if reproducible_experiment:
        score += 10.0
    return min(100.0, score)


def why_it_matters(item: Item, breakdown: ScoreBreakdown) -> str:
    reasons: list[str] = []
    if breakdown.relevance_score >= 60:
        reasons.append("高度聚焦 AI Coding 核心问题")
    if "new_benchmark" in breakdown.signals:
        reasons.append("提出新的 benchmark / 数据集")
    if "open_source_code" in breakdown.signals:
        reasons.append("提供开源代码便于落地")
    if "sota" in breakdown.signals:
        reasons.append("报告了领先结果")
    if breakdown.popularity_score >= 50:
        reasons.append("社区关注度高")
    if breakdown.time_decay_score >= 70:
        reasons.append("发布较新")
    if not reasons:
        reasons.append("在代码智能方向具备参考价值")
    return "；".join(reasons) + "。"


def _normalize_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    merged = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(max(v, 0.0) for v in merged.values()) or 1.0
    return {k: max(v, 0.0) / total for k, v in merged.items()}


def score_item(
    item: Item,
    now: datetime | None = None,
    *,
    weights: Mapping[str, float] | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    relevance: RelevanceResult | None = None,
) -> ScoreBreakdown:
    w = _normalize_weights(weights)
    relevance = relevance or keyword_relevance(
        title=item.title, abstract=item.abstract, summary=item.summary, prefiltered=item.prefiltered
    )
    signals = detect_impact_signals(item)

    time_score = compute_time_decay_score(item.published_at, now=now, half_life_days=half_life_days)
    pop_score = compute_popularity_score(item.stars, item.upvotes, item.trending_rank, item.likes)
    impact_score = compute_impact_score(
        benchmark_improvement="new_benchmark" in signals,
        open_source_code="open_source_code" in signals,
        reproducible_experiment="reproducible" in signals,
        sota="sota" in signals,
    )

    importance = (
        relevance.score * w["relevance"]
        + pop_score * w["popularity"]
        + time_score * w["freshness"]
        + impact_score * w["impact"]
    )

    breakdown = ScoreBreakdown(
        time_decay_score=round(time_score, 1),
        popularity_score=round(pop_score, 1),
        relevance_score=relevance.score,
        impact_score=round(impact_score, 1),
        importance_score=round(importance, 1),
        why_it_matters="",
        keywords=display_keywords(relevance),
        signals=signals,
    )
    breakdown.why_it_matters = why_it_matters(item, breakdown)
    return breakdown


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
            lines.append(f"- **{item.title}** (score={score.importance_score:.1f})")
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
