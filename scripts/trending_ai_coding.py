#!/usr/bin/env python3
"""AI Coding trending collector, analyzer and report generator."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests
from jinja2 import Template
from pydantic import BaseModel, Field, HttpUrl

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_RAW = ROOT / "outputs" / "raw"
OUTPUT_REPORTS = ROOT / "outputs" / "reports"

ARXIV_RSS = "https://rss.arxiv.org/rss/cs.AI"
HF_TRENDING_DATASETS = "https://huggingface.co/api/datasets?sort=trendingScore&limit=30"

AI_CODING_KEYWORDS = {
    "code": 4,
    "coding": 4,
    "programming": 4,
    "software": 3,
    "agent": 3,
    "repository": 3,
    "benchmark": 2,
    "developer": 2,
    "autonomous": 2,
    "llm": 2,
    "bug": 2,
    "debug": 2,
    "test": 2,
    "swe": 5,
}


class TrendItem(BaseModel):
    title: str
    url: HttpUrl
    source: str
    published_at: datetime
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    score: float = 0.0


class AnalysisResult(BaseModel):
    generated_at: datetime
    total_items: int
    selected_items: int
    items: list[TrendItem]


def ensure_dirs() -> None:
    OUTPUT_RAW.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def fetch_arxiv() -> list[dict[str, Any]]:
    feed = feedparser.parse(ARXIV_RSS)
    entries: list[dict[str, Any]] = []
    for item in feed.entries:
        published = item.get("published_parsed")
        published_dt = (
            datetime(*published[:6], tzinfo=timezone.utc).isoformat()
            if published
            else datetime.now(timezone.utc).isoformat()
        )
        entries.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "source": "arxiv",
                "published_at": published_dt,
                "description": item.get("summary", ""),
                "tags": [tag["term"] for tag in item.get("tags", []) if "term" in tag],
            }
        )
    return entries


def fetch_hf_datasets() -> list[dict[str, Any]]:
    resp = requests.get(HF_TRENDING_DATASETS, timeout=20)
    resp.raise_for_status()
    rows = resp.json()
    entries: list[dict[str, Any]] = []
    for row in rows:
        dataset_id = row.get("id") or row.get("_id") or "unknown"
        tags = row.get("tags", []) or []
        entries.append(
            {
                "title": dataset_id,
                "url": f"https://huggingface.co/datasets/{dataset_id}",
                "source": "huggingface-dataset",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "description": row.get("description", "") or row.get("cardData", {}).get("description", ""),
                "tags": [str(tag) for tag in tags],
            }
        )
    return entries


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_file(pattern: str) -> Path:
    matches = sorted(OUTPUT_RAW.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No files match: {pattern}")
    return matches[-1]


def load_items_from_raw(path: Path) -> list[TrendItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_items = data.get("items", [])
    items: list[TrendItem] = []
    for raw in raw_items:
        try:
            items.append(TrendItem(**raw))
        except Exception:
            continue
    return items


def score_item(item: TrendItem) -> float:
    text = f"{item.title} {item.description} {' '.join(item.tags)}".lower()
    relevance = sum(weight for keyword, weight in AI_CODING_KEYWORDS.items() if keyword in text)
    recency_bonus = max(0.0, 5.0 - (datetime.now(timezone.utc) - item.published_at).days * 0.25)
    source_bonus = 1.5 if item.source == "arxiv" else 1.0
    return round(relevance + recency_bonus + source_bonus, 2)


def tag_item(item: TrendItem) -> list[str]:
    text = f"{item.title} {item.description} {' '.join(item.tags)}".lower()
    tags = [keyword for keyword in AI_CODING_KEYWORDS if keyword in text]
    return sorted(set(tags))


def cmd_fetch(_: argparse.Namespace) -> None:
    ensure_dirs()
    arxiv_entries = fetch_arxiv()
    dataset_entries = fetch_hf_datasets()
    ts = now_str()

    save_json(
        OUTPUT_RAW / f"papers_{ts}.json",
        {"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "arxiv", "items": arxiv_entries},
    )
    save_json(
        OUTPUT_RAW / f"datasets_{ts}.json",
        {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "huggingface-dataset",
            "items": dataset_entries,
        },
    )
    print(f"Fetched {len(arxiv_entries)} papers and {len(dataset_entries)} datasets.")


def cmd_analyze(args: argparse.Namespace) -> None:
    ensure_dirs()
    papers_file = Path(args.papers_file) if args.papers_file else latest_file("papers_*.json")
    datasets_file = Path(args.datasets_file) if args.datasets_file else latest_file("datasets_*.json")

    items = load_items_from_raw(papers_file) + load_items_from_raw(datasets_file)
    selected: list[TrendItem] = []
    for item in items:
        item.tags = tag_item(item)
        item.score = score_item(item)
        if item.score >= args.min_score:
            selected.append(item)

    selected.sort(key=lambda x: x.score, reverse=True)
    result = AnalysisResult(
        generated_at=datetime.now(timezone.utc),
        total_items=len(items),
        selected_items=len(selected),
        items=selected,
    )
    output = OUTPUT_RAW / f"analysis_{now_str()}.json"
    save_json(output, result.model_dump(mode="json"))
    print(f"Analyzed {len(items)} items, selected {len(selected)} items -> {output}")


REPORT_TEMPLATE = """# AI Coding 趋势{{ period_cn }}（{{ report_date }}）

- 生成时间（UTC）：{{ generated_at }}
- 总样本数：{{ total_items }}
- 入选条目：{{ selected_items }}

## Top {{ top_n }}
{% for item in items %}
### {{ loop.index }}. {{ item.title }}
- 来源：{{ item.source }}
- 发布时间：{{ item.published_at }}
- 分数：{{ item.score }}
- 标签：{{ item.tags | join(', ') if item.tags else 'N/A' }}
- 链接：{{ item.url }}
- 摘要：{{ item.description | replace('\n', ' ') | truncate(200, True, '...') }}

{% endfor %}
"""


def cmd_report(args: argparse.Namespace) -> None:
    ensure_dirs()
    analysis_file = Path(args.analysis_file) if args.analysis_file else latest_file("analysis_*.json")
    data = json.loads(analysis_file.read_text(encoding="utf-8"))
    items = data.get("items", [])[: args.top_n]
    period_cn = "日报" if args.period == "daily" else "周报"
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rendered = Template(REPORT_TEMPLATE).render(
        period_cn=period_cn,
        report_date=report_date,
        generated_at=data.get("generated_at"),
        total_items=data.get("total_items", 0),
        selected_items=data.get("selected_items", 0),
        items=items,
        top_n=args.top_n,
    )

    out_file = OUTPUT_REPORTS / f"{report_date}.md"
    out_file.write_text(rendered, encoding="utf-8")
    print(f"Report generated: {out_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Coding trending workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch trending papers and datasets")
    fetch.set_defaults(func=cmd_fetch)

    analyze = sub.add_parser("analyze", help="Analyze relevance and rank importance")
    analyze.add_argument("--papers-file", help="Optional papers json path")
    analyze.add_argument("--datasets-file", help="Optional datasets json path")
    analyze.add_argument("--min-score", type=float, default=6.0, help="Min score for selection")
    analyze.set_defaults(func=cmd_analyze)

    report = sub.add_parser("report", help="Generate markdown daily/weekly report")
    report.add_argument("--analysis-file", help="Optional analysis json path")
    report.add_argument("--top-n", type=int, default=10, help="How many top entries to include")
    report.add_argument(
        "--period",
        choices=["daily", "weekly"],
        default="daily",
        help="Report period label",
    )
    report.set_defaults(func=cmd_report)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
