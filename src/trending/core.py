"""热榜抓取的公共部分：数据源配置、HTTP 会话、条目结构和常用解析函数。

源列表与抓取逻辑移植自 NewsNow（https://github.com/ourongxing/newsnow，MIT 协议）。
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "trending_sources.yaml"

CST = ZoneInfo("Asia/Shanghai")
USER_AGENT = "mtxrym-trending/1.0 (+https://mtxrym.github.io/trending/)"
COLUMNS = {"china": "国内", "world": "国际", "tech": "科技", "finance": "财经", "sports": "体育"}
TYPES = {"hottest", "realtime", ""}
MAX_ITEMS = 50


class FetchError(RuntimeError):
    """抓取或解析失败，message 会原样展示在页面和报告里。"""


# ---------------------------------------------------------------------------
# 数据源配置
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SourceMeta:
    id: str
    name: str
    column: str
    home: str
    title: str = ""
    type: str = ""
    interval: int = 10
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} · {self.title}" if self.title else self.name


def load_sources(path: Path = CONFIG_FILE) -> list[SourceMeta]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources: list[SourceMeta] = []
    seen: set[str] = set()
    for entry in raw.get("sources", []):
        meta = SourceMeta(
            id=str(entry["id"]),
            name=str(entry["name"]),
            column=str(entry["column"]),
            home=str(entry["home"]),
            title=str(entry.get("title") or ""),
            type=str(entry.get("type") or ""),
            interval=int(entry.get("interval") or 10),
            note=str(entry.get("note") or ""),
        )
        if meta.id in seen:
            raise ValueError(f"重复的数据源 id：{meta.id}")
        if meta.column not in COLUMNS:
            raise ValueError(f"{meta.id}：未知栏目 {meta.column}")
        if meta.type not in TYPES:
            raise ValueError(f"{meta.id}：未知类型 {meta.type}")
        seen.add(meta.id)
        sources.append(meta)
    return sources


# ---------------------------------------------------------------------------
# 条目
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Item:
    id: str
    title: str
    url: str
    mobile_url: str = ""
    info: str = ""  # 热度、分数、涨跌幅等短信息
    hover: str = ""  # 摘要 / 描述
    time: str = ""  # ISO 8601（UTC）

    def to_dict(self) -> dict[str, str]:
        data = {"id": self.id, "title": self.title, "url": self.url}
        for key in ("mobile_url", "info", "hover", "time"):
            value = getattr(self, key)
            if value:
                data[key] = value
        return data


def normalize(items: list[Item]) -> list[Item]:
    """清洗标题、去掉空条目和重复条目，最多保留 MAX_ITEMS 条。"""
    result: list[Item] = []
    seen: set[str] = set()
    for item in items:
        title = clean(item.title)
        url = (item.url or "").strip()
        if not title or not url:
            continue
        key = str(item.id or url)
        if key in seen:
            continue
        seen.add(key)
        item.id, item.title, item.url = key, title, url
        item.info = clean(item.info)
        item.hover = clean(item.hover)[:300]
        result.append(item)
        if len(result) >= MAX_ITEMS:
            break
    return result


# ---------------------------------------------------------------------------
# 抓取器注册
# ---------------------------------------------------------------------------

Fetcher = Callable[["Http"], list[Item]]
FETCHERS: dict[str, Fetcher] = {}


def fetcher(*ids: str) -> Callable[[Fetcher], Fetcher]:
    def register(fn: Fetcher) -> Fetcher:
        for source_id in ids:
            if source_id in FETCHERS:
                raise ValueError(f"抓取器重复注册：{source_id}")
            FETCHERS[source_id] = fn
        return fn

    return register


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Http:
    """普通的公开请求：如实标明身份的 UA，不伪造 cookie、签名或来源页，不处理反爬验证。

    4xx 不重试（被拒绝就如实记为失败），429 / 5xx / 网络错误重试。
    """

    def __init__(self, timeout: float = 10.0, retries: int = 2) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self.timeout = timeout
        self.retries = retries

    def request(self, method: str, url: str, *, check: bool = True, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        last: str = ""
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                last = type(exc).__name__
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                elif check and resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code}（{short_host(url)}）")
                else:
                    return resp
            if attempt < self.retries:
                time.sleep(1 + attempt)
        raise FetchError(f"{last}（{short_host(url)}）")

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def text(self, url: str, *, encoding: str | None = None, **kwargs: Any) -> str:
        return decode(self.get(url, **kwargs), encoding)

    def json(self, url: str, **kwargs: Any) -> Any:
        return parse_json(self.get(url, **kwargs))

    def post_json(self, url: str, payload: Any, **kwargs: Any) -> Any:
        return parse_json(self.request("POST", url, json=payload, **kwargs))


def decode(resp: requests.Response, encoding: str | None = None) -> str:
    if encoding:
        return resp.content.decode(encoding, errors="replace")
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return resp.content.decode(resp.apparent_encoding or "utf-8", errors="replace")


def parse_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError as exc:
        snippet = clean(resp.text[:60])
        raise FetchError(f"返回的不是 JSON（{short_host(resp.url)}）：{snippet}") from exc


def short_host(url: str) -> str:
    match = re.match(r"https?://([^/]+)", url)
    return match.group(1) if match else url


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text) if "<" in text else text
    return re.sub(r"\s+", " ", text).strip()


def soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup, "html.parser")


def extract_json_after(text: str, marker: str | re.Pattern[str]) -> Any:
    """取出页面里 `marker` 之后紧跟的 JSON 对象（比非贪婪正则可靠，不会被字符串里的 `};` 截断）。"""
    pattern = re.compile(marker) if isinstance(marker, str) else marker
    match = pattern.search(text)
    if not match:
        raise FetchError("页面里没有找到数据（结构可能变了或被拦截）")
    start = text.find("{", match.end())
    if start < 0:
        raise FetchError("页面里没有找到数据（结构可能变了或被拦截）")
    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise FetchError("页面内嵌数据解析失败") from exc
    return value


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CST)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_iso(value: Any) -> str:
    """把时间戳（秒 / 毫秒）、ISO 字符串、北京时间字符串统一成 UTC ISO；无法解析返回空字符串。"""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        number = float(value)
        if number <= 0:
            return ""
        if number > 1e12:
            number /= 1000
        return to_utc_iso(datetime.fromtimestamp(number, tz=timezone.utc))
    text = str(value).strip()
    try:
        return to_utc_iso(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    return parse_relative_date(text)


_REL_UNITS = {"秒": "seconds", "分钟": "minutes", "分": "minutes", "小时": "hours", "天": "days"}


def parse_relative_date(text: str, now: datetime | None = None) -> str:
    """解析中文站点常见的时间写法（北京时间）：刚刚 / 5分钟前 / 今天 12:30 / 昨天 08:00 / 10-02 17:06 / 2024-10-02 17:06。"""
    now = (now or datetime.now(timezone.utc)).astimezone(CST)
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    if text in {"刚刚", "刚才"}:
        return to_utc_iso(now)
    match = re.match(r"^(\d+)\s*(秒|分钟|分|小时|天)前", text)
    if match:
        return to_utc_iso(now - timedelta(**{_REL_UNITS[match.group(2)]: int(match.group(1))}))
    match = re.match(r"^(今天|今日|昨天|昨日|前天)\s*(\d{1,2}):(\d{2})", text)
    if match:
        offset = {"今天": 0, "今日": 0, "昨天": 1, "昨日": 1, "前天": 2}[match.group(1)]
        day = now - timedelta(days=offset)
        return to_utc_iso(day.replace(hour=int(match.group(2)), minute=int(match.group(3)), second=0, microsecond=0))
    match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", text)
    if match:
        dt = now.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=int(match.group(3) or 0), microsecond=0)
        if dt > now + timedelta(minutes=5):
            dt -= timedelta(days=1)
        return to_utc_iso(dt)
    match = re.match(r"^(?:(\d{4})[-/年.])?(\d{1,2})[-/月.](\d{1,2})日?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", text)
    if match:
        year = int(match.group(1) or now.year)
        try:
            dt = datetime(year, int(match.group(2)), int(match.group(3)), int(match.group(4) or 0),
                          int(match.group(5) or 0), int(match.group(6) or 0), tzinfo=CST)
        except ValueError:
            return ""
        if not match.group(1) and dt > now + timedelta(days=1):
            dt = dt.replace(year=year - 1)
        return to_utc_iso(dt)
    return ""


def rss_items(http: Http, url: str, *, with_date: bool = True, **kwargs: Any) -> list[Item]:
    """RSS / Atom 源：用我们自己的会话下载（统一 UA 和超时），再交给 feedparser 解析。"""
    return parse_feed(http.get(url, **kwargs).content, url, with_date=with_date)


def parse_feed(content: bytes, url: str, *, with_date: bool = True) -> list[Item]:
    feed = feedparser.parse(content)
    items: list[Item] = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        items.append(Item(
            id=entry.get("id") or link,
            title=entry.get("title") or "",
            url=link,
            hover=entry.get("summary") or "",
            time=to_utc_iso(datetime(*published[:6], tzinfo=timezone.utc)) if (with_date and published) else "",
        ))
    if not items:
        raise FetchError(f"RSS 为空（{short_host(url)}，可能被拦截）")
    return items


def compact_number(value: Any) -> str:
    """1234567 → 123.5万，与国内站点的显示习惯一致。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return clean(value)
    if number >= 1e8:
        return f"{number / 1e8:.1f}亿".replace(".0亿", "亿")
    if number >= 1e4:
        return f"{number / 1e4:.1f}万".replace(".0万", "万")
    return str(int(number))
