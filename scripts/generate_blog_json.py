#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring import Item, score_item  # noqa: E402

DEFAULT_TOP_N = 12
DEFAULT_MAX_ITEMS = 30

IMAGE_BY_CATEGORY = {
    "papers": "https://images.unsplash.com/photo-1456324504439-367cee3b3c32?auto=format&fit=crop&w=1200&q=80",
    "datasets": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=1200&q=80",
}


@dataclass(slots=True)
class RankedEntry:
    score: float
    payload: dict[str, Any]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def slugify(text: str) -> str:
    allowed = []
    for ch in text.lower():
        if ch.isalnum():
            allowed.append(ch)
        elif ch in {" ", "-", "_"}:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80] or "item"


def run_fetch(max_items: int) -> dict[str, list[dict[str, Any]]]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "trending_ai_coding.py"),
        "--max-items",
        str(max_items),
        "--no-cache-update",
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def build_blog_items(fetched: dict[str, list[dict[str, Any]]], top_n: int) -> list[dict[str, Any]]:
    ranked: list[RankedEntry] = []

    for source_id, entries in fetched.items():
        for row in entries or []:
            title = str(row.get("title") or "").strip()
            if not title:
                continue
            category = str(row.get("category") or "papers")
            heat = row.get("heat")
            likes = int(heat) if isinstance(heat, (int, float)) else 0
            item = Item(
                title=title,
                item_type="dataset" if category == "datasets" else "paper",
                url=str(row.get("link") or ""),
                summary=str(row.get("summary") or ""),
                abstract=str(row.get("summary") or ""),
                published_at=parse_time(str(row.get("time") or "")),
                stars=likes,
            )
            breakdown = score_item(item)
            link = str(row.get("link") or "").strip()
            host = urlparse(link).netloc or source_id
            blog_item = {
                "title": title,
                "sub_title": f"{category} · source={source_id} · score={breakdown.importance_score:.1f}",
                "url_title": slugify(title),
                "top_image": IMAGE_BY_CATEGORY.get(category, IMAGE_BY_CATEGORY["papers"]),
                "external_url": link,
                "source_id": source_id,
                "published_at": row.get("time"),
                "source_host": host,
            }
            ranked.append(RankedEntry(score=breakdown.importance_score, payload=blog_item))

    ranked.sort(key=lambda x: x.score, reverse=True)
    return [x.payload for x in ranked[:top_n]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate homepage data from fetched AI coding trends")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--output", default=str(ROOT / "blog.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fetched = run_fetch(max_items=args.max_items)
    items = build_blog_items(fetched=fetched, top_n=args.top_n)

    out = Path(args.output)
    if not items and out.exists():
        try:
            previous = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(previous, list) and previous:
                print("no fresh items fetched; keep previous blog.json to avoid empty homepage")
                return 0
        except json.JSONDecodeError:
            pass

    out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"generated {len(items)} items -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
