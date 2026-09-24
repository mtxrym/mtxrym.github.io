#!/usr/bin/env python3
"""调试用：抓取各数据源并按源输出原始记录（JSON）。

生成首页数据请用 scripts/generate_blog_json.py；这里只负责“抓到了什么”，
便于排查某个数据源是否正常。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.policy import load_policy  # noqa: E402
from src.sources import FetchOptions, fetch_source, load_sources, parse_datetime  # noqa: E402

CACHE_FILE = ROOT / "cache" / "last_fetch.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch AI coding sources and print raw records")
    parser.add_argument("--since", help="只输出该时间之后发布的条目（ISO 8601）；缺省时使用 cache 中每个源的上次时间")
    parser.add_argument("--max-items", type=int, help="每个源最多输出多少条（默认取 update_policy.yaml 的 per_source_limit）")
    parser.add_argument("--sources", nargs="*", help="只抓取指定的数据源 id")
    parser.add_argument("--no-cache-update", action="store_true", help="不把最新时间写回 cache/last_fetch.json")
    return parser.parse_args()


def to_json(record: Any) -> dict[str, Any]:
    data = asdict(record)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat().replace("+00:00", "Z")
    # 兼容旧输出字段
    data["time"] = data["published_at"]
    data["heat"] = record.upvotes or record.likes
    return data


def main() -> int:
    args = parse_args()
    policy = load_policy()
    limit = args.max_items or policy.per_source_limit
    if limit <= 0:
        raise SystemExit("--max-items must be > 0")

    cli_since = parse_datetime(args.since)
    if args.since and cli_since is None:
        raise SystemExit(f"Invalid --since value: {args.since}")

    options = FetchOptions(
        timeout=policy.timeout_seconds,
        retries=policy.retries,
        limit=limit,
        skip_announce_types=policy.skip_arxiv_announce_types,
    )
    sources = load_sources()
    if args.sources:
        sources = [s for s in sources if s.id in set(args.sources)]

    try:
        cache: dict[str, str] = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    output: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        since = cli_since or parse_datetime(cache.get(source.id))
        try:
            records = fetch_source(source, options)
        except Exception as exc:  # noqa: BLE001 - 依赖外部网络
            print(f"[warn] failed source={source.id}: {exc}", file=sys.stderr)
            output[source.id] = []
            continue
        kept = [r for r in records if since is None or (r.published_at and r.published_at > since)]
        output[source.id] = [to_json(r) for r in kept]
        newest = max((r.published_at for r in kept if r.published_at), default=None)
        if newest:
            cache[source.id] = newest.isoformat().replace("+00:00", "Z")

    if not args.no_cache_update:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
