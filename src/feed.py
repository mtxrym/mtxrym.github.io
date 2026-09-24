"""首页数据的核心逻辑（纯函数，便于测试）：去重合并 → 历史库滚动更新 → 打分 → 选出展示条目。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

from src.policy import UpdatePolicy
from src.scoring import (
    Item,
    compute_impact_score,
    compute_popularity_score,
    compute_time_decay_score,
    score_item,
)
from src.sources import Record, parse_datetime

ARCHIVE_VERSION = 2
LLM_FIELDS = ("relevance", "relevance_source", "rule_relevance", "topics", "summary_zh", "reason_zh")
ARCHIVE_SUMMARY_CHARS = 420
BLOG_SUMMARY_CHARS = 360
BLOG_AUTHOR_LIMIT = 6

IMAGE_BY_CATEGORY = {
    "papers": "https://images.unsplash.com/photo-1456324504439-367cee3b3c32?auto=format&fit=crop&w=1200&q=80",
    "datasets": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:，；：")
    return cut + "…"


def slugify(text: str) -> str:
    chars = [ch if ch.isalnum() else "-" for ch in text.lower() if ch.isalnum() or ch in " -_"]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80] or "item"


def normalize_link(link: str) -> str:
    parts = urlsplit(link.strip())
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}".removeprefix("www.")


def record_key(record: Record) -> str:
    if record.arxiv_id:
        return f"arxiv:{record.arxiv_id}"
    if record.link:
        return f"url:{normalize_link(record.link)}"
    return f"title:{record.title.strip().lower()}"


def _later(a: str | None, b: str | None) -> str | None:
    return max(filter(None, (a, b)), default=None)


# ---------------------------------------------------------------------------
# 合并同一条内容的多个来源
# ---------------------------------------------------------------------------


def entry_from_record(record: Record, policy: UpdatePolicy, now: datetime) -> dict[str, Any]:
    """把一条抓取记录变成历史库条目。相关性 / 影响力信号依赖完整摘要，所以在这里一次算好存下。"""
    breakdown = score_item(
        Item(
            title=record.title,
            item_type="dataset" if record.category == "datasets" else "paper",
            url=record.link,
            abstract=record.summary,
            published_at=record.published_at,
            prefiltered=record.prefiltered,
            code_url=record.github_url,
        ),
        now=now,
        weights=policy.weights,
        half_life_days=policy.freshness_half_life_days,
    )
    return {
        "key": record_key(record),
        "title": record.title,
        "link": record.link,
        "category": record.category,
        "source_ids": [record.source_id],
        "published_at": iso(record.published_at),
        "featured_at": iso(record.featured_at),
        "summary": truncate(record.summary, ARCHIVE_SUMMARY_CHARS),
        "authors": record.authors[:BLOG_AUTHOR_LIMIT],
        "author_count": len(record.authors),
        "upvotes": record.upvotes,
        "likes": record.likes,
        "trending_rank": record.trending_rank,
        "github_url": record.github_url,
        "github_stars": record.github_stars,
        "arxiv_id": record.arxiv_id,
        "hf_url": record.hf_url,
        "relevance": breakdown.relevance_score,
        "keywords": breakdown.keywords,
        "signals": sorted(breakdown.signals),
    }


def merge_entry(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """把同一条内容的另一份记录并入 base（例如同一篇论文同时出现在 arXiv 与 HF Daily Papers）。"""
    merged = dict(base)
    merged["source_ids"] = list(dict.fromkeys([*base["source_ids"], *other["source_ids"]]))
    for key in ("upvotes", "likes", "github_stars", "author_count"):
        merged[key] = max(base.get(key) or 0, other.get(key) or 0)
    # 模型判定优先于规则分；都是规则分时取较高者
    base_llm = base.get("relevance_source") == "llm"
    other_llm = other.get("relevance_source") == "llm"
    if other_llm and not base_llm:
        for key in LLM_FIELDS:
            if key in other:
                merged[key] = other[key]
    elif not base_llm:
        merged["relevance"] = max(base.get("relevance") or 0, other.get("relevance") or 0)
    for key in ("github_url", "hf_url", "arxiv_id", "link", "title"):
        merged[key] = base.get(key) or other.get(key) or ""
    if len(other.get("summary") or "") > len(base.get("summary") or ""):
        merged["summary"] = other["summary"]
    if len(other.get("authors") or []) > len(base.get("authors") or []):
        merged["authors"] = other["authors"]
    ranks = [r for r in (base.get("trending_rank"), other.get("trending_rank")) if r]
    merged["trending_rank"] = min(ranks) if ranks else None
    # arXiv RSS 的日期是公开发布日，HF 给的是提交日；取较晚者，避免“NEW”条目显示一个月前的日期
    merged["published_at"] = _later(base.get("published_at"), other.get("published_at"))
    merged["featured_at"] = _later(base.get("featured_at"), other.get("featured_at"))
    merged["keywords"] = list(dict.fromkeys([*(base.get("keywords") or []), *(other.get("keywords") or [])]))[:4]
    merged["signals"] = sorted(set(base.get("signals") or []) | set(other.get("signals") or []))
    return merged


def merge_records(records: Iterable[Record], policy: UpdatePolicy, now: datetime) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.title:
            continue
        entry = entry_from_record(record, policy, now)
        key = entry["key"]
        entries[key] = merge_entry(entries[key], entry) if key in entries else entry
    return entries


def passes_relevance(entry: dict[str, Any], policy: UpdatePolicy) -> bool:
    """模型判定过的条目用模型门槛，否则用规则门槛。"""
    if entry.get("relevance_source") == "llm":
        return (entry.get("relevance") or 0) >= policy.llm.min_score
    return (entry.get("relevance") or 0) >= policy.min_relevance


# ---------------------------------------------------------------------------
# 历史库
# ---------------------------------------------------------------------------


def update_archive(
    archive: dict[str, dict[str, Any]],
    fresh: dict[str, dict[str, Any]],
    policy: UpdatePolicy,
    now: datetime,
    ok_sources: set[str],
) -> dict[str, dict[str, Any]]:
    """合并本次抓取结果到历史库：保留首次收录时间，刷新热度，按保留期清理。

    - first_seen_at：首次收录时间，决定是否还在展示窗口内；
    - last_seen_on：最近一次仍出现在数据源里的日期（按天记录，避免每次运行都产生变更）。
      清理按 last_seen_on 判断，长期在热榜上的条目不会被清理后又当成“新条目”重新收录。
    """
    now_iso = iso(now)
    today = now.astimezone(timezone.utc).date().isoformat()
    result: dict[str, dict[str, Any]] = {}

    for key, entry in archive.items():
        kept = dict(entry)
        # 热榜排名只对本次抓取有效；来源本次抓取成功却没再出现，说明已掉出榜单
        if kept.get("trending_rank") and set(kept["source_ids"]) <= ok_sources and key not in fresh:
            kept["trending_rank"] = None
        result[key] = kept

    for key, entry in fresh.items():
        if not passes_relevance(entry, policy):
            continue
        if key in result:
            updated = merge_entry(result[key], entry)
            # 热度以本次为准（数值可能回落，例如数据集热榜排名）
            updated["trending_rank"] = entry.get("trending_rank")
            updated["first_seen_at"] = result[key].get("first_seen_at") or now_iso
            updated["last_seen_on"] = today
            result[key] = updated
        else:
            result[key] = {**entry, "first_seen_at": now_iso, "last_seen_on": today}

    cutoff = (now - timedelta(days=policy.retention_days)).astimezone(timezone.utc).date().isoformat()

    def last_seen(entry: dict[str, Any]) -> str:
        return entry.get("last_seen_on") or (entry.get("first_seen_at") or now_iso)[:10]

    return {k: v for k, v in result.items() if last_seen(v) >= cutoff}


# ---------------------------------------------------------------------------
# 打分与挑选
# ---------------------------------------------------------------------------


def score_entry(entry: dict[str, Any], policy: UpdatePolicy, now: datetime) -> dict[str, float]:
    published = parse_datetime(entry.get("published_at"))
    featured = parse_datetime(entry.get("featured_at"))
    freshness_anchor = max(filter(None, (published, featured)), default=None) or parse_datetime(entry.get("first_seen_at"))
    signals = set(entry.get("signals") or [])

    scores = {
        "relevance": float(entry.get("relevance") or 0),
        "popularity": compute_popularity_score(
            stars=entry.get("github_stars") or 0,
            upvotes=entry.get("upvotes") or 0,
            trending_rank=entry.get("trending_rank"),
            likes=entry.get("likes") or 0,
        ),
        "freshness": compute_time_decay_score(freshness_anchor, now=now, half_life_days=policy.freshness_half_life_days),
        "impact": compute_impact_score(
            benchmark_improvement="new_benchmark" in signals,
            open_source_code="open_source_code" in signals,
            reproducible_experiment="reproducible" in signals,
            sota="sota" in signals,
        ),
    }
    total = sum(scores[name] * weight for name, weight in policy.weights.items())
    return {**{k: round(v, 1) for k, v in scores.items()}, "total": round(total, 1)}


def select_items(archive: dict[str, dict[str, Any]], policy: UpdatePolicy, now: datetime) -> list[dict[str, Any]]:
    window_start = iso(now - timedelta(days=policy.window_days))
    candidates = []
    for entry in archive.values():
        if not passes_relevance(entry, policy):
            continue
        if (entry.get("first_seen_at") or "") < window_start:
            continue
        candidates.append({**entry, "scores": score_entry(entry, policy, now)})

    # 得分降序；同分时新发布的在前，再按标题保证顺序稳定
    candidates.sort(key=lambda e: e["title"])
    candidates.sort(key=lambda e: e.get("published_at") or "", reverse=True)
    candidates.sort(key=lambda e: e["scores"]["total"], reverse=True)
    selected: list[dict[str, Any]] = []
    datasets = 0
    for entry in candidates:
        if len(selected) >= policy.max_items:
            break
        if entry["category"] == "datasets":
            if datasets >= policy.max_datasets:
                continue
            datasets += 1
        selected.append(entry)
    return selected


# ---------------------------------------------------------------------------
# 输出格式
# ---------------------------------------------------------------------------


def to_blog_item(entry: dict[str, Any]) -> dict[str, Any]:
    """首页 / App 使用的条目格式。保留旧字段（sub_title / url_title / top_image 等）以兼容旧版页面。"""
    scores = entry["scores"]
    primary = entry["source_ids"][0]
    return {
        "title": entry["title"],
        "sub_title": f"{entry['category']} · source={primary} · score={scores['total']:.1f}",
        "url_title": slugify(entry["title"]),
        "top_image": IMAGE_BY_CATEGORY.get(entry["category"], IMAGE_BY_CATEGORY["papers"]),
        "external_url": entry["link"],
        "source_id": primary,
        "source_ids": entry["source_ids"],
        "source_host": urlsplit(entry["link"]).netloc or primary,
        "category": entry["category"],
        "published_at": entry.get("published_at"),
        "first_seen_at": entry.get("first_seen_at"),
        "score": scores["total"],
        "scores": {k: scores[k] for k in ("relevance", "popularity", "freshness", "impact")},
        "keywords": entry.get("keywords") or [],
        "topics": entry.get("topics") or [],
        "summary_zh": entry.get("summary_zh") or "",
        "reason_zh": entry.get("reason_zh") or "",
        "relevance_source": entry.get("relevance_source") or "rules",
        "signals": entry.get("signals") or [],
        "summary": truncate(entry.get("summary") or "", BLOG_SUMMARY_CHARS),
        "authors": (entry.get("authors") or [])[:BLOG_AUTHOR_LIMIT],
        "author_count": entry.get("author_count") or len(entry.get("authors") or []),
        "upvotes": entry.get("upvotes") or 0,
        "likes": entry.get("likes") or 0,
        "github_url": entry.get("github_url") or "",
        "github_stars": entry.get("github_stars") or 0,
        "hf_url": entry.get("hf_url") or "",
        "arxiv_id": entry.get("arxiv_id") or "",
    }


def build_status(
    policy: UpdatePolicy,
    source_reports: list[dict[str, Any]],
    archive_size: int,
    items: list[dict[str, Any]],
    llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "policy": policy.summary(),
        "llm": llm or {"enabled": False, "reason": "未启用"},
        "sources": source_reports,
        "totals": {
            "archive": archive_size,
            "displayed": len(items),
            "sources_ok": sum(1 for s in source_reports if s["ok"]),
            "sources_total": len(source_reports),
        },
    }
