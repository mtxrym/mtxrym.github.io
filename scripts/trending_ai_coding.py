#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config" / "sources.yaml"
CACHE_FILE = ROOT / "cache" / "last_fetch.json"
DEFAULT_TIMEOUT = 20


@dataclass
class Source:
    id: str
    type: str
    category: str
    url: str
    params: dict[str, Any]
    fields: dict[str, Any]


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def parse_sources_yaml(text: str) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    current_category: str | None = None
    current_item: dict[str, Any] | None = None
    current_block: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if indent == 0 and line.endswith(":"):
            current_category = line[:-1]
            data[current_category] = []
            current_item = None
            current_block = None
            continue

        if line.startswith("- "):
            if current_category is None:
                continue
            content = line[2:]
            current_item = {}
            data[current_category].append(current_item)
            current_block = None
            if ":" in content:
                key, value = content.split(":", 1)
                current_item[key.strip()] = parse_scalar(value)
            continue

        if current_item is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if indent == 4:
            if value == "":
                current_item[key] = {}
                current_block = key
            else:
                current_item[key] = parse_scalar(value)
                current_block = None
        elif indent >= 6 and current_block:
            block = current_item.get(current_block)
            if isinstance(block, dict):
                block[key] = parse_scalar(value)

    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch trending AI coding sources")
    parser.add_argument(
        "--since",
        help=(
            "Only include items published after this time (ISO8601, e.g. "
            "2026-04-10T00:00:00Z). If omitted, falls back to per-source cache timestamp."
        ),
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=30,
        help="Maximum items to return for each source (default: 30).",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        help="Optional list of source IDs to fetch. If omitted, fetches all sources.",
    )
    parser.add_argument(
        "--no-cache-update",
        action="store_true",
        help="Do not write latest fetch timestamps into cache/last_fetch.json.",
    )
    return parser.parse_args()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        dt = parsedate_to_datetime(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def load_sources() -> list[Source]:
    raw = parse_sources_yaml(SOURCES_FILE.read_text(encoding="utf-8"))
    sources: list[Source] = []
    for category, items in raw.items():
        for item in items or []:
            sources.append(
                Source(
                    id=item["id"],
                    type=item["type"],
                    category=item.get("category", category),
                    url=item["url"],
                    params=item.get("params", {}),
                    fields=item.get("fields", {}),
                )
            )
    return sources


def load_cache() -> dict[str, str]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_url(url: str, params: dict[str, Any]) -> str:
    if not params:
        return url
    parsed = urllib.parse.urlsplit(url)
    existing = urllib.parse.parse_qs(parsed.query)
    for key, value in params.items():
        existing[key] = [str(value)]
    query = urllib.parse.urlencode(existing, doseq=True)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def http_get_json(url: str, params: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        build_url(url, params),
        headers={"User-Agent": "trending-ai-coding/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, params: dict[str, Any]) -> str:
    req = urllib.request.Request(
        build_url(url, params),
        headers={"User-Agent": "trending-ai-coding/1.0"},
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_path(obj: dict[str, Any], path: Any) -> Any:
    if path is None:
        return None
    if not isinstance(path, str):
        return path
    cursor: Any = obj
    for part in path.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return None
    return cursor


def map_item(raw_item: dict[str, Any], source: Source) -> dict[str, Any]:
    fields = source.fields
    mapped = {
        "source_id": source.id,
        "source_type": source.type,
        "category": source.category,
        "title": extract_path(raw_item, fields.get("title")),
        "link": extract_path(raw_item, fields.get("link")),
        "time": extract_path(raw_item, fields.get("time")),
        "summary": extract_path(raw_item, fields.get("summary")),
        "heat": extract_path(raw_item, fields.get("heat")),
    }
    return mapped


def fetch_pwc_api(source: Source) -> list[dict[str, Any]]:
    payload = http_get_json(source.url, source.params)
    if isinstance(payload, dict):
        items = payload.get("results")
        if items is None:
            items = payload.get("items")
        if items is None:
            items = payload.get("data")
        if isinstance(items, list):
            return items
    if isinstance(payload, list):
        return payload
    return []


def fetch_hf_trending(source: Source) -> list[dict[str, Any]]:
    payload = http_get_json(source.url, source.params)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "results", "datasets"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def fetch_arxiv_rss(source: Source) -> list[dict[str, Any]]:
    xml_text = http_get_text(source.url, source.params)
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        items.append(
            {
                "title": item.findtext("title"),
                "link": item.findtext("link"),
                "published": item.findtext("pubDate"),
                "summary": item.findtext("description"),
            }
        )
    return items


FETCHERS = {
    "pwc_api": fetch_pwc_api,
    "hf_trending": fetch_hf_trending,
    "arxiv_rss": fetch_arxiv_rss,
}


def should_keep(item: dict[str, Any], since: datetime | None) -> bool:
    if since is None:
        return True
    item_dt = parse_datetime(str(item.get("time") or ""))
    if item_dt is None:
        return False
    return item_dt > since


def resolve_since(cli_since: datetime | None, cache: dict[str, str], source_id: str) -> datetime | None:
    if cli_since is not None:
        return cli_since
    return parse_datetime(cache.get(source_id))


def fetch_source(source: Source, since: datetime | None, max_items: int) -> tuple[list[dict[str, Any]], datetime | None]:
    fetcher = FETCHERS.get(source.type)
    if fetcher is None:
        raise ValueError(f"Unsupported source type: {source.type} (source: {source.id})")

    raw_items = fetcher(source)
    mapped = [map_item(item, source) for item in raw_items if isinstance(item, dict)]
    filtered = [item for item in mapped if should_keep(item, since)]
    limited = filtered[:max_items]

    newest: datetime | None = None
    for item in limited:
        dt = parse_datetime(str(item.get("time") or ""))
        if dt and (newest is None or dt > newest):
            newest = dt
    return limited, newest


def main() -> int:
    args = parse_args()

    if args.max_items <= 0:
        raise SystemExit("--max-items must be > 0")

    cli_since = parse_datetime(args.since)
    if args.since and cli_since is None:
        raise SystemExit(f"Invalid --since value: {args.since}")

    sources = load_sources()
    if args.sources:
        source_set = set(args.sources)
        sources = [s for s in sources if s.id in source_set]

    cache = load_cache()
    output: dict[str, list[dict[str, Any]]] = {}

    for source in sources:
        source_since = resolve_since(cli_since, cache, source.id)
        try:
            items, newest_time = fetch_source(source, source_since, args.max_items)
            output[source.id] = items
            if newest_time and not args.no_cache_update:
                cache[source.id] = newest_time.isoformat().replace("+00:00", "Z")
        except Exception as exc:  # pragma: no cover - depends on external network
            print(f"[warn] failed source={source.id}: {exc}", file=sys.stderr)
            output[source.id] = []

    if not args.no_cache_update:
        save_cache(cache)

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
