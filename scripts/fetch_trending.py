#!/usr/bin/env python3
"""抓取全部热榜数据源，生成 /trending/ 的静态接口。

输出（默认写到 trending/data/）：
  index.json   各数据源的元信息与抓取状态（不含条目）
  all.json     index.json + 每个源的条目（页面一次性加载）
  <id>.json    单个源的条目，相当于 NewsNow 的 /api/s?id=<id>

给了 --previous（上一版 all.json 的地址或路径）时：
  - 每个条目带 first_seen（首次上榜时间），本轮新出现的条目 first_seen 等于本次生成时间；
  - 热榜类条目带 rank_delta（与上一轮相比的名次变化，正数为上升）；
  - 本轮失败的源沿用上一版数据，标记为 stale，页面不会突然变空。
脚本只在自身出错时以非零退出；数据源失败只记录在状态里，不影响部署。

用法：
  python scripts/fetch_trending.py                       # 全部抓取，写入 trending/data/
  python scripts/fetch_trending.py --only weibo,zhihu --dry-run
  python scripts/fetch_trending.py --previous https://mtxrym.github.io/trending/data/all.json --summary "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trending import COLUMNS, FETCHERS, FetchError, Http, SourceMeta, load_sources, normalize  # noqa: E402

ATTRIBUTION = "数据源列表与抓取逻辑移植自 NewsNow（https://github.com/ourongxing/newsnow，MIT 协议）"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_one(meta: SourceMeta, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "id": meta.id,
        "name": meta.name,
        "title": meta.title,
        "label": meta.label,
        "column": meta.column,
        "type": meta.type,
        "home": meta.home,
        "color": meta.color,
        "interval": meta.interval,
        "note": meta.note,
        "status": "error",
        "error": None,
        "updated_at": None,
        "items": [],
    }
    try:
        items = normalize(FETCHERS[meta.id](Http(timeout=timeout)))
        if not items:
            raise FetchError("没有解析到条目（页面结构可能变了或被拦截）")
        result.update(status="ok", updated_at=now_iso(), items=[item.to_dict() for item in items])
    except FetchError as exc:
        result["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - 接口格式变化（KeyError 等）不能影响其他源
        result["error"] = f"解析失败：{type(exc).__name__} {str(exc)[:120]}"
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


def load_previous(location: str) -> dict[str, Any] | None:
    """读取上一版 all.json（URL 或本地路径）；拿不到就当作没有上一版。"""
    if not location:
        return None
    try:
        if location.startswith(("http://", "https://")):
            resp = requests.get(location, timeout=15)
            if not resp.ok:
                return None
            data = resp.json()
        else:
            data = json.loads(Path(location).read_text(encoding="utf-8"))
    except (requests.RequestException, OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("sources"), list) else None


def annotate(results: list[dict[str, Any]], previous: dict[str, Any] | None, generated_at: str) -> None:
    """对照上一版：补 first_seen / rank_delta，失败的源用上一版数据顶上。"""
    prev_sources = {s.get("id"): s for s in (previous or {}).get("sources", []) if isinstance(s, dict)}
    for result in results:
        prev = prev_sources.get(result["id"]) or {}
        prev_items = [it for it in prev.get("items") or [] if isinstance(it, dict) and it.get("id")]
        if result["status"] == "error":
            if prev_items:
                for item in prev_items:
                    item.pop("rank_delta", None)
                result.update(status="stale", items=prev_items, updated_at=prev.get("updated_at"))
            continue
        if not previous:
            continue
        # 上一版没有 first_seen（旧数据）时，用上一版的生成时间，避免把老条目都当成新上榜
        fallback_seen = previous.get("generated_at") or prev.get("updated_at") or generated_at
        prev_index = {it["id"]: (i, it) for i, it in enumerate(prev_items)}
        for i, item in enumerate(result["items"]):
            hit = prev_index.get(item["id"])
            if hit is None:
                item["first_seen"] = generated_at
                continue
            old_rank, old_item = hit
            item["first_seen"] = old_item.get("first_seen") or fallback_seen
            if result["type"] == "hottest" and old_rank != i:
                item["rank_delta"] = old_rank - i


def summary_markdown(results: list[dict[str, Any]], generated_at: str) -> str:
    ok = sum(r["status"] == "ok" for r in results)
    lines = [
        f"### 热榜抓取：{ok}/{len(results)} 个源成功（{generated_at}）",
        "",
        "| 状态 | 数据源 | 栏目 | 条数 | 新上榜 | 耗时 | 错误 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    icon = {"ok": "✅", "stale": "🟡 旧数据", "error": "❌"}
    for r in sorted(results, key=lambda r: (r["status"] != "ok", r["column"], r["id"])):
        error = (r["error"] or "").replace("|", "\\|")
        fresh = sum(it.get("first_seen") == generated_at for it in r["items"]) if r["status"] == "ok" else 0
        lines.append(
            f"| {icon[r['status']]} | {r['label']} (`{r['id']}`) | {COLUMNS[r['column']]} | "
            f"{len(r['items'])} | {fresh} | {r['elapsed_ms'] / 1000:.1f}s | {error} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "trending" / "data", help="输出目录")
    parser.add_argument("--only", default="", help="只抓这些源（逗号分隔的 id）")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=10.0, help="单次请求超时（秒）")
    parser.add_argument("--previous", default="", help="上一版 all.json 的地址或路径，如 https://mtxrym.github.io/trending/data/all.json")
    parser.add_argument("--summary", default="", help="追加 Markdown 汇总表到这个文件（GitHub Actions 用 $GITHUB_STEP_SUMMARY）")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件")
    args = parser.parse_args()

    sources = load_sources()
    missing = [s.id for s in sources if s.id not in FETCHERS]
    if missing:
        raise SystemExit(f"这些数据源没有抓取器：{', '.join(missing)}")
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = wanted - {s.id for s in sources}
        if unknown:
            raise SystemExit(f"未知数据源：{', '.join(sorted(unknown))}")
        sources = [s for s in sources if s.id in wanted]

    previous = load_previous(args.previous)
    generated_at = now_iso()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda meta: run_one(meta, args.timeout), sources))
    annotate(results, previous, generated_at)

    for result in results:
        tag = {"ok": "[ok]   ", "stale": "[stale]", "error": "[fail] "}[result["status"]]
        detail = f"{len(result['items'])} 条" if result["status"] == "ok" else result["error"]
        print(f"{tag} {result['id']:24} {result['elapsed_ms'] / 1000:5.1f}s  {detail}", file=sys.stderr)

    totals = {
        "total": len(results),
        "ok": sum(r["status"] == "ok" for r in results),
        "stale": sum(r["status"] == "stale" for r in results),
        "error": sum(r["status"] == "error" for r in results),
    }
    print(f"热榜：{totals['ok']}/{totals['total']} 个源成功，{totals['stale']} 个用旧数据，{totals['error']} 个失败"
          f"（上一版：{previous.get('generated_at') if previous else '无'}）", file=sys.stderr)

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(summary_markdown(results, generated_at))
    if args.dry_run:
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    head = {
        "generated_at": generated_at,
        "previous_generated_at": previous.get("generated_at") if previous else None,
        "attribution": ATTRIBUTION,
        "columns": COLUMNS,
        "totals": totals,
    }
    index = {**head, "sources": [{k: v for k, v in r.items() if k != "items"} | {"count": len(r["items"])} for r in results]}
    dump(args.out / "index.json", index)
    dump(args.out / "all.json", {**head, "sources": results})
    for result in results:
        dump(args.out / f"{result['id']}.json", {k: v for k, v in result.items() if k != "elapsed_ms"})
    return 0


def dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
