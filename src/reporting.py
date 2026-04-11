"""Utilities to render markdown reports from Jinja2 templates."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("daily_report.reporting")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_DIR / "reporting.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def retry(operation_name: str, attempts: int = 3, delay_seconds: float = 1.0):
    """Retry decorator with structured error logging."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - keep broad to avoid silent failures
                    last_error = exc
                    logger.exception(
                        "%s failed (attempt %s/%s): %s",
                        operation_name,
                        attempt,
                        attempts,
                        exc,
                    )
                    if attempt < attempts:
                        time.sleep(delay_seconds)
            raise RuntimeError(f"{operation_name} failed after {attempts} attempts") from last_error

        return wrapper

    return decorator


@retry("render_daily_report")
def render_daily_report(
    context: dict[str, Any],
    template_dir: str | Path = "templates",
    template_name: str = "daily_report.md.j2",
) -> str:
    """Render daily markdown report using template context."""
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    markdown = template.render(**context)
    logger.info("Report rendered successfully: template=%s", template_name)
    return markdown.strip() + "\n"


@retry("save_report")
def save_report(content: str, output_path: str | Path) -> Path:
    """Save markdown report to file and return its path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Report saved: %s", path)
    return path
