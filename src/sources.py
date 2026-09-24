"""数据源：读取 config/sources.yaml，按类型抓取并统一成 Record。"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config" / "sources.yaml"
USER_AGENT = "mtxrym-ai-coding-feed/2.0 (+https://github.com/mtxrym/mtxrym.github.io)"

ARXIV_NS = "{http://arxiv.org/schemas/atom}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")


@dataclass(slots=True)
class Source:
    id: str
    type: str
    category: str
    url: str
    label: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    prefiltered: bool = False


@dataclass(slots=True)
class Record:
    source_id: str
    category: str
    title: str
    link: str
    published_at: datetime | None = None
    summary: str = ""
    authors: list[str] = field(default_factory=list)
    upvotes: int = 0
    likes: int = 0
    trending_rank: int | None = None
    github_url: str = ""
    github_stars: int = 0
    arxiv_id: str = ""
    hf_url: str = ""
    featured_at: datetime | None = None
    announce_type: str = ""
    prefiltered: bool = False


@dataclass(slots=True)
class FetchOptions:
    timeout: float = 20
    retries: int = 2
    limit: int = 500
    skip_announce_types: tuple[str, ...] = ("replace", "replace-cross")


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def parse_datetime(value: Any) -> datetime | None:
    """同时支持 ISO 8601（HF）与 RFC 2822（arXiv RSS）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt: datetime | None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_arxiv_id(*candidates: str | None) -> str:
    for value in candidates:
        if value and ("arxiv" in value.lower() or ARXIV_ID_RE.fullmatch(value.strip())):
            match = ARXIV_ID_RE.search(value)
            if match:
                return match.group(1)
    return ""


_LATEX_ACCENTS = {'"': "\u0308", "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303", "c": "\u0327", "H": "\u030b"}
_LATEX_ACCENT_RE = re.compile(r"\{?\\([\"'`^~]|[cH](?=[\s{]))\s*\{?([A-Za-z])\}?\}?")


def _replace_latex_accent(match: re.Match[str]) -> str:
    return unicodedata.normalize("NFC", match.group(2) + _LATEX_ACCENTS[match.group(1)])


def clean_text(value: Any) -> str:
    """压缩空白，并把 arXiv 标题里常见的 LaTeX 重音（Schr\\"odinger）转成 Unicode（Schrödinger）。"""
    text = _LATEX_ACCENT_RE.sub(_replace_latex_accent, str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    query.update({k: str(v) for k, v in params.items()})
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def http_get(url: str, *, timeout: float, retries: int, accept: str = "*/*") -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            # 4xx（限流除外）重试也不会成功
            if 400 <= exc.code < 500 and exc.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(2**attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}") from last_error


def http_get_json(url: str, options: FetchOptions) -> Any:
    raw = http_get(url, timeout=options.timeout, retries=options.retries, accept="application/json")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{url} 返回的不是 JSON（接口可能已下线或跳转）") from exc


# ---------------------------------------------------------------------------
# 抓取器
# ---------------------------------------------------------------------------


def parse_arxiv_rss(xml_text: str | bytes, source: Source, options: FetchOptions) -> list[Record]:
    root = ET.fromstring(xml_text)
    records: list[Record] = []
    for item in root.findall("./channel/item"):
        description = item.findtext("description") or ""
        announce = (item.findtext(f"{ARXIV_NS}announce_type") or "").strip()
        if not announce:
            match = re.search(r"Announce Type:\s*(\S+)", description)
            announce = match.group(1) if match else ""
        if announce in options.skip_announce_types:
            continue

        abstract = description.split("Abstract:", 1)[1] if "Abstract:" in description else description
        creators = re.sub(r"\s*\([^)]*\)", "", item.findtext(f"{DC_NS}creator") or "")
        link = clean_text(item.findtext("link"))
        records.append(
            Record(
                source_id=source.id,
                category=source.category,
                title=clean_text(item.findtext("title")),
                link=link,
                published_at=parse_datetime(item.findtext("pubDate")),
                summary=clean_text(abstract),
                authors=[a.strip() for a in creators.split(",") if a.strip()],
                arxiv_id=extract_arxiv_id(link, item.findtext("guid")),
                announce_type=announce,
                prefiltered=source.prefiltered,
            )
        )
        if len(records) >= options.limit:
            break
    return records


def parse_hf_daily_papers(payload: Any, source: Source, options: FetchOptions) -> list[Record]:
    if not isinstance(payload, list):
        raise RuntimeError("HF daily_papers 返回格式异常（期望数组）")
    records: list[Record] = []
    for row in payload[: options.limit]:
        paper = row.get("paper") if isinstance(row, dict) else None
        if not isinstance(paper, dict) or not paper.get("id"):
            continue
        arxiv_id = extract_arxiv_id(str(paper["id"]))
        records.append(
            Record(
                source_id=source.id,
                category=source.category,
                title=clean_text(paper.get("title") or row.get("title")),
                link=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else f"https://huggingface.co/papers/{paper['id']}",
                published_at=parse_datetime(paper.get("publishedAt") or row.get("publishedAt")),
                featured_at=parse_datetime(paper.get("submittedOnDailyAt")),
                summary=clean_text(paper.get("summary") or row.get("summary")),
                authors=[clean_text(a.get("name")) for a in paper.get("authors") or [] if isinstance(a, dict) and a.get("name")],
                upvotes=int(paper.get("upvotes") or 0),
                github_url=str(paper.get("githubRepo") or ""),
                github_stars=int(paper.get("githubStars") or 0),
                arxiv_id=arxiv_id,
                hf_url=f"https://huggingface.co/papers/{paper['id']}",
                prefiltered=source.prefiltered,
            )
        )
    return records


def parse_hf_datasets(payload: Any, source: Source, options: FetchOptions) -> list[Record]:
    if not isinstance(payload, list):
        raise RuntimeError("HF datasets 返回格式异常（期望数组）")
    records: list[Record] = []
    for rank, row in enumerate(payload[: options.limit], start=1):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        dataset_id = str(row["id"])
        records.append(
            Record(
                source_id=source.id,
                category=source.category,
                title=dataset_id,
                link=f"https://huggingface.co/datasets/{dataset_id}",
                published_at=parse_datetime(row.get("lastModified") or row.get("createdAt")),
                summary=clean_text(row.get("description")),
                likes=int(row.get("likes") or 0),
                trending_rank=rank,
                prefiltered=source.prefiltered,
            )
        )
    return records


def fetch_arxiv_rss(source: Source, options: FetchOptions) -> list[Record]:
    raw = http_get(build_url(source.url, source.params), timeout=options.timeout, retries=options.retries)
    return parse_arxiv_rss(raw, source, options)


def fetch_hf_daily_papers(source: Source, options: FetchOptions) -> list[Record]:
    return parse_hf_daily_papers(http_get_json(build_url(source.url, source.params), options), source, options)


def fetch_hf_datasets(source: Source, options: FetchOptions) -> list[Record]:
    return parse_hf_datasets(http_get_json(build_url(source.url, source.params), options), source, options)


FETCHERS: dict[str, Callable[[Source, FetchOptions], list[Record]]] = {
    "arxiv_rss": fetch_arxiv_rss,
    "hf_daily_papers": fetch_hf_daily_papers,
    "hf_datasets": fetch_hf_datasets,
}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def parse_sources(raw: dict[str, Any] | None) -> list[Source]:
    sources: list[Source] = []
    seen: set[str] = set()
    for category, items in (raw or {}).items():
        for item in items or []:
            source = Source(
                id=str(item["id"]),
                type=str(item["type"]),
                category=str(item.get("category", category)),
                url=str(item["url"]),
                label=str(item.get("label") or item["id"]),
                params=dict(item.get("params") or {}),
                prefiltered=bool(item.get("prefiltered", False)),
            )
            if source.type not in FETCHERS:
                raise ValueError(f"sources.yaml: 未知的数据源类型 {source.type!r}（{source.id}）")
            if source.id in seen:
                raise ValueError(f"sources.yaml: 数据源 id 重复 {source.id!r}")
            seen.add(source.id)
            sources.append(source)
    return sources


def load_sources(path: Path = SOURCES_FILE) -> list[Source]:
    return parse_sources(yaml.safe_load(path.read_text(encoding="utf-8")))


def fetch_source(source: Source, options: FetchOptions) -> list[Record]:
    return FETCHERS[source.type](source, options)
