#!/usr/bin/env python3
"""抓取 → 打分 → 更新历史库 → 生成首页 / App 使用的数据文件。

输出：
  blog.json            首页和 App 展示的条目（按综合得分排序）
  data/status.json     数据源健康状态 + 当前生效的更新策略摘要
  data/archive.json    滚动历史库（去重、首次收录时间、跨天窗口）

更新策略见 config/update_policy.yaml，数据源见 config/sources.yaml。
内容没有变化时不会改写任何文件，避免产生无意义的提交。
所有数据源都失败时以非零状态退出（GitHub Actions 会发邮件提醒），且保留旧数据。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.feed import (  # noqa: E402
    ARCHIVE_VERSION,
    build_status,
    iso,
    merge_records,
    select_items,
    to_blog_item,
    update_archive,
)
from src.policy import UpdatePolicy, load_policy  # noqa: E402
from src.sources import FetchOptions, Record, Source, fetch_source, load_sources  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate homepage data from AI coding sources")
    parser.add_argument("--output", default=str(ROOT / "blog.json"), help="首页数据文件")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="status.json / archive.json 所在目录")
    parser.add_argument("--sources", nargs="*", help="只抓取指定的数据源 id（调试用）")
    parser.add_argument("--now", help="覆盖当前时间（ISO 8601，调试 / 测试用）")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    # 兼容旧参数：条数现在由 config/update_policy.yaml 控制
    parser.add_argument("--top-n", type=int, help="覆盖 selection.max_items")
    parser.add_argument("--max-items", type=int, help="覆盖 fetch.per_source_limit")
    return parser.parse_args()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def dump_archive(archive: dict[str, Any]) -> str:
    """历史库每个条目占一行：文件更紧凑，git diff 也能精确到条目。"""
    lines = [f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, sort_keys=True)}" for k, v in archive["items"].items()]
    body = ",\n".join(lines)
    return f'{{\n  "version": {archive["version"]},\n  "items": {{\n{body}\n  }}\n}}\n'


def fetch_all(sources: list[Source], policy: UpdatePolicy) -> tuple[list[Record], list[dict[str, Any]]]:
    options = FetchOptions(
        timeout=policy.timeout_seconds,
        retries=policy.retries,
        limit=policy.per_source_limit,
        skip_announce_types=policy.skip_arxiv_announce_types,
    )
    records: list[Record] = []
    reports: list[dict[str, Any]] = []
    for source in sources:
        report: dict[str, Any] = {
            "id": source.id,
            "label": source.label,
            "category": source.category,
            "type": source.type,
            "ok": True,
            "fetched": 0,
            "relevant": 0,
            "error": None,
        }
        try:
            fetched = fetch_source(source, options)
            records.extend(fetched)
            report["fetched"] = len(fetched)
            print(f"[ok]   {source.id}: {len(fetched)} items", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - 单个源失败不能影响其他源
            report["ok"] = False
            report["error"] = str(exc)[:200]
            print(f"[fail] {source.id}: {exc}", file=sys.stderr)
        reports.append(report)
    return records, reports


def main() -> int:
    args = parse_args()
    policy = load_policy()
    if args.top_n:
        policy.max_items = args.top_n
    if args.max_items:
        policy.per_source_limit = args.max_items

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    sources = load_sources()
    if args.sources:
        wanted = set(args.sources)
        sources = [s for s in sources if s.id in wanted]

    records, reports = fetch_all(sources, policy)
    if not any(r["ok"] for r in reports):
        print("所有数据源都抓取失败，保留现有数据不变。", file=sys.stderr)
        return 1

    fresh = merge_records(records, policy, now)
    for report in reports:
        report["relevant"] = sum(
            1 for e in fresh.values() if report["id"] in e["source_ids"] and e["relevance"] >= policy.min_relevance
        )

    out_path = Path(args.output)
    data_dir = Path(args.data_dir)
    archive_path = data_dir / "archive.json"
    status_path = data_dir / "status.json"

    old_archive = read_json(archive_path, {})
    archive_items = old_archive.get("items", {}) if old_archive.get("version") == ARCHIVE_VERSION else {}
    ok_sources = {r["id"] for r in reports if r["ok"]}
    archive_items = update_archive(archive_items, fresh, policy, now, ok_sources)

    items = [to_blog_item(e) for e in select_items(archive_items, policy, now)]
    previous_items = read_json(out_path, [])
    if not items and isinstance(previous_items, list) and previous_items:
        # 窗口内没有任何条目（例如长时间抓取不到新内容）时保留旧数据，页面会显示“更新滞后”而不是一片空白
        print("展示窗口内没有条目，保留现有 blog.json。", file=sys.stderr)
        items = previous_items
    status = build_status(policy, reports, len(archive_items), items)

    if args.dry_run:
        print(dump_json({"status": status, "items": items}))
        return 0

    new_archive = {"version": ARCHIVE_VERSION, "items": dict(sorted(archive_items.items()))}
    old_status = read_json(status_path, {})
    unchanged = (
        previous_items == items
        and old_archive == new_archive
        and {k: v for k, v in old_status.items() if k != "generated_at"} == status
    )
    if unchanged:
        print("内容没有变化，不改写文件。", file=sys.stderr)
        return 0

    data_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dump_json(items), encoding="utf-8")
    archive_path.write_text(dump_archive(new_archive), encoding="utf-8")
    status_path.write_text(dump_json({"generated_at": iso(now), **status}), encoding="utf-8")
    ok = sum(1 for r in reports if r["ok"])
    print(f"生成 {len(items)} 条 → {out_path}（历史库 {len(archive_items)} 条，数据源 {ok}/{len(reports)} 正常）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
