"""数据更新策略：读取 config/update_policy.yaml，缺省值与校验集中在这里。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "config" / "update_policy.yaml"

DEFAULT_WEIGHTS = {"relevance": 0.5, "popularity": 0.2, "freshness": 0.2, "impact": 0.1}


@dataclass(slots=True)
class UpdatePolicy:
    schedule_cron: str = "30 5,11,17,23 * * *"
    schedule_description: str = ""
    per_source_limit: int = 500
    timeout_seconds: int = 20
    retries: int = 2
    skip_arxiv_announce_types: tuple[str, ...] = ("replace", "replace-cross")
    min_relevance: float = 35.0
    window_days: int = 7
    max_items: int = 30
    max_datasets: int = 6
    retention_days: int = 21
    stale_after_hours: int = 96
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    freshness_half_life_days: float = 3.0

    def summary(self) -> dict[str, Any]:
        """写进 data/status.json 给网页 / App 展示的策略摘要。"""
        return {
            "schedule": {"cron": self.schedule_cron, "description": self.schedule_description},
            "window_days": self.window_days,
            "max_items": self.max_items,
            "max_datasets": self.max_datasets,
            "min_relevance": self.min_relevance,
            "retention_days": self.retention_days,
            "stale_after_hours": self.stale_after_hours,
            "weights": self.weights,
        }


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name) or {}
    if not isinstance(value, dict):
        raise ValueError(f"update_policy.{name} 必须是映射")
    return value


def _positive(name: str, value: Any, *, allow_zero: bool = False) -> float:
    number = float(value)
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"update_policy: {name} 必须为正数，当前为 {value!r}")
    return number


def parse_policy(raw: dict[str, Any] | None) -> UpdatePolicy:
    raw = raw or {}
    defaults = UpdatePolicy()
    schedule = _section(raw, "schedule")
    fetch = _section(raw, "fetch")
    selection = _section(raw, "selection")
    archive = _section(raw, "archive")
    health = _section(raw, "health")
    scoring = _section(raw, "scoring")

    weights = {**DEFAULT_WEIGHTS, **(scoring.get("weights") or {})}
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"update_policy.scoring.weights 包含未知分项: {sorted(unknown)}")
    total = sum(_positive(f"weights.{k}", v, allow_zero=True) for k, v in weights.items())
    if total <= 0:
        raise ValueError("update_policy.scoring.weights 之和必须大于 0")
    weights = {k: round(float(v) / total, 4) for k, v in weights.items()}

    policy = UpdatePolicy(
        schedule_cron=str(schedule.get("cron", defaults.schedule_cron)).strip(),
        schedule_description=str(schedule.get("description", defaults.schedule_description)).strip(),
        per_source_limit=int(_positive("fetch.per_source_limit", fetch.get("per_source_limit", defaults.per_source_limit))),
        timeout_seconds=int(_positive("fetch.timeout_seconds", fetch.get("timeout_seconds", defaults.timeout_seconds))),
        retries=int(_positive("fetch.retries", fetch.get("retries", defaults.retries), allow_zero=True)),
        skip_arxiv_announce_types=tuple(fetch.get("skip_arxiv_announce_types", defaults.skip_arxiv_announce_types) or ()),
        min_relevance=_positive("selection.min_relevance", selection.get("min_relevance", defaults.min_relevance), allow_zero=True),
        window_days=int(_positive("selection.window_days", selection.get("window_days", defaults.window_days))),
        max_items=int(_positive("selection.max_items", selection.get("max_items", defaults.max_items))),
        max_datasets=int(_positive("selection.max_datasets", selection.get("max_datasets", defaults.max_datasets), allow_zero=True)),
        retention_days=int(_positive("archive.retention_days", archive.get("retention_days", defaults.retention_days))),
        stale_after_hours=int(_positive("health.stale_after_hours", health.get("stale_after_hours", defaults.stale_after_hours))),
        weights=weights,
        freshness_half_life_days=_positive(
            "scoring.freshness_half_life_days",
            scoring.get("freshness_half_life_days", defaults.freshness_half_life_days),
        ),
    )
    if policy.retention_days < policy.window_days:
        raise ValueError("update_policy: archive.retention_days 不能小于 selection.window_days")
    return policy


def load_policy(path: Path = POLICY_FILE) -> UpdatePolicy:
    if not path.exists():
        return UpdatePolicy()
    return parse_policy(yaml.safe_load(path.read_text(encoding="utf-8")))
