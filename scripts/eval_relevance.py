#!/usr/bin/env python3
"""用人工标注集评估“是否与 AI 编程相关”的识别准确率：关键词规则 vs 大模型复核。

    python scripts/eval_relevance.py                  # 只评估规则
    DEEPSEEK_API_KEY=... python scripts/eval_relevance.py --llm
    DEEPSEEK_API_KEY=... python scripts/eval_relevance.py --llm --effort low

标注集：tests/fixtures/relevance_gold.json（borderline 样本单独统计）。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm import judge, make_client  # noqa: E402
from src.policy import load_policy  # noqa: E402
from src.relevance import keyword_relevance  # noqa: E402

GOLD = ROOT / "tests" / "fixtures" / "relevance_gold.json"


def metrics(pairs: list[tuple[int, int]]) -> dict[str, float]:
    tp = sum(1 for y, p in pairs if y and p)
    fp = sum(1 for y, p in pairs if not y and p)
    fn = sum(1 for y, p in pairs if y and not p)
    tn = sum(1 for y, p in pairs if not y and not p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"n": len(pairs), "precision": precision, "recall": recall, "f1": f1, "accuracy": (tp + tn) / len(pairs), "fp": fp, "fn": fn}


def report(name: str, items: list[dict], predictions: dict[str, int]) -> None:
    clear = [(it["label"], predictions[it["key"]]) for it in items if not it["borderline"]]
    every = [(it["label"], predictions[it["key"]]) for it in items]
    for label, pairs in (("非边界样本", clear), ("全部样本", every)):
        m = metrics(pairs)
        print(
            f"{name:<14} {label:<6} n={m['n']:<3} 精确率 {m['precision']:.1%}  召回率 {m['recall']:.1%}  "
            f"F1 {m['f1']:.3f}  准确率 {m['accuracy']:.1%}  误收 {m['fp']}  漏判 {m['fn']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", action="store_true", help="同时评估大模型复核（需要 API Key）")
    parser.add_argument("--effort", choices=["none", "low", "high", "max"], help="覆盖 reasoning_effort")
    parser.add_argument("--model", help="覆盖模型 id")
    parser.add_argument("--show-errors", action="store_true", help="列出判错的样本")
    args = parser.parse_args()

    policy = load_policy()
    items = json.loads(GOLD.read_text(encoding="utf-8"))["items"]

    def rule_score(it: dict) -> float:
        return keyword_relevance(it["title"], it["abstract"], prefiltered=it["source"].startswith("hf_datasets")).score

    rules = {it["key"]: int(rule_score(it) >= policy.min_relevance) for it in items}
    print(f"标注集 {len(items)} 条（正样本 {sum(i['label'] for i in items)}，边界 {sum(i['borderline'] for i in items)}）\n")
    report("关键词规则", items, rules)
    errors = {"关键词规则": [it for it in items if rules[it["key"]] != it["label"]]}

    if args.llm:
        config = policy.llm
        if args.effort:
            config = replace(config, reasoning_effort=args.effort)
        if args.model:
            config = replace(config, model=args.model)
        client, reason = make_client(config)
        if client is None:
            print(f"\n无法评估大模型：{reason}")
            return 1
        now = datetime.now(timezone.utc)
        # 与线上一致：规则分低于召回门槛的条目不送审，直接判为不相关
        candidates = []
        for it in items:
            if rule_score(it) >= config.candidate_min_relevance:
                candidates.append({"key": it["key"], "title": it["title"], "summary": it["abstract"], "category": it["category"]})
        verdicts, stats = judge(candidates, config, client, {}, now)
        llm_pred = {it["key"]: int(it["key"] in verdicts and verdicts[it["key"]].score >= config.min_score) for it in items}
        name = f"{config.model}/{config.reasoning_effort}"
        report(name, items, llm_pred)
        print(f"\n送审 {stats.candidates} 条，成功 {stats.judged}，失败 {stats.failed}，token 用量 {stats.usage}")
        errors[name] = [it for it in items if llm_pred[it["key"]] != it["label"]]
        if args.show_errors:
            for it in errors[name]:
                v = verdicts.get(it["key"])
                print(f"  {'误收' if not it['label'] else '漏判'}{'（边界）' if it['borderline'] else ''} "
                      f"{v.score if v else '-':>5} {it['title'][:80]}  {v.reason_zh if v else '未送审'}")

    if args.show_errors:
        print("\n关键词规则判错：")
        for it in errors["关键词规则"]:
            print(f"  {'误收' if not it['label'] else '漏判'}{'（边界）' if it['borderline'] else ''} {rule_score(it):5.1f} {it['title'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
