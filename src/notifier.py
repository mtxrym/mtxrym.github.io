"""Notification adapter for report delivery."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("daily_report.notifier")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_DIR / "notifier.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def retry(operation_name: str, attempts: int = 3, delay_seconds: float = 1.0):
    """Retry decorator with file logging to prevent silent failures."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
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


@retry("notify_stdout")
def notify_stdout(message: str) -> None:
    """Send report to stdout."""
    print(message)
    logger.info("Message sent to stdout")


@retry("notify_slack_webhook")
def notify_slack_webhook(webhook_url: str, message: str) -> None:
    """Send report through Slack incoming webhook."""
    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            if status_code < 200 or status_code >= 300:
                body = response.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Unexpected status code {status_code}: {body}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Slack webhook request failed: {exc}") from exc

    logger.info("Message sent to Slack webhook")


def notify(channel: Literal["stdout", "slack"], message: str, webhook_url: str | None = None) -> None:
    """Dispatch notification by channel."""
    if channel == "stdout":
        notify_stdout(message)
        return

    if channel == "slack":
        if not webhook_url:
            raise ValueError("webhook_url is required when channel='slack'")
        notify_slack_webhook(webhook_url=webhook_url, message=message)
        return

    raise ValueError(f"Unsupported channel: {channel}")
