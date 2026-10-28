#!/usr/bin/env python3
"""抓取全部热榜数据源，生成 /trending/ 的静态接口。

输出（默认写到 trending/data/）：
  index.json   各数据源的元信息与抓取状态（不含条目）
  all.json     index.json + 每个源的条目（页面一次性加载）
  <id>.json    单个源的条目，相当于 NewsNow 的 /api/s?id=<id>

单个源失败时，如果给了 --fallback-base，会取线上上一版数据顶上（标记为 stale），页面不会突然变空。
脚本只在自身出错时以非零退出；数据源失败只记录在状态里，不影响部署。

用法：
  python scripts/fetch_trending.py                       # 全部抓取，写入 trending/data/
  python scripts/fetch_trending.py --only weibo,zhihu --dry-run
  python scripts/fetch_trending.py --fallback-base https://mtxrym.github.io/trending/data --summary "$GITHUB_STEP_SUMMARY"
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


def apply_fallback(result: dict[str, Any], base: str) -> None:
    """失败的源用线上上一版数据顶上。"""
    try:
        resp = requests.get(f"{base.rstrip('/')}/{result['id']}.json", timeout=10)
        previous = resp.json() if resp.ok else None
    except (requests.RequestException, ValueError):
        previous = None
    if previous and previous.get("items"):
        result.update(status="stale", items=previous["items"], updated_at=previous.get("updated_at"))


def summary_markdown(results: list[dict[str, Any]], generated_at: str) -> str:
    ok = sum(r["status"] == "ok" for r in results)
    lines = [
        f"### 热榜抓取：{ok}/{len(results)} 个源成功（{generated_at}）",
        "",
        "| 状态 | 数据源 | 栏目 | 条数 | 耗时 | 错误 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    icon = {"ok": "✅", "stale": "🟡 旧数据", "error": "❌"}
    for r in sorted(results, key=lambda r: (r["status"] != "ok", r["column"], r["id"])):
        error = (r["error"] or "").replace("|", "\\|")
        lines.append(
            f"| {icon[r['status']]} | {r['label']} (`{r['id']}`) | {COLUMNS[r['column']]} | "
            f"{len(r['items'])} | {r['elapsed_ms'] / 1000:.1f}s | {error} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "trending" / "data", help="输出目录")
    parser.add_argument("--only", default="", help="只抓这些源（逗号分隔的 id）")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=10.0, help="单次请求超时（秒）")
    parser.add_argument("--fallback-base", default="", help="失败时读取上一版数据的地址，如 https://mtxrym.github.io/trending/data")
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

    generated_at = now_iso()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda meta: run_one(meta, args.timeout), sources))

    for result in results:
        if result["status"] == "error" and args.fallback_base:
            apply_fallback(result, args.fallback_base)
        tag = {"ok": "[ok]   ", "stale": "[stale]", "error": "[fail] "}[result["status"]]
        detail = f"{len(result['items'])} 条" if result["status"] == "ok" else result["error"]
        print(f"{tag} {result['id']:24} {result['elapsed_ms'] / 1000:5.1f}s  {detail}", file=sys.stderr)

    totals = {
        "total": len(results),
        "ok": sum(r["status"] == "ok" for r in results),
        "stale": sum(r["status"] == "stale" for r in results),
        "error": sum(r["status"] == "error" for r in results),
    }
    print(f"热榜：{totals['ok']}/{totals['total']} 个源成功，{totals['stale']} 个用旧数据，{totals['error']} 个失败", file=sys.stderr)

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(summary_markdown(results, generated_at))
    if args.dry_run:
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    head = {"generated_at": generated_at, "attribution": ATTRIBUTION, "columns": COLUMNS, "totals": totals}
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
