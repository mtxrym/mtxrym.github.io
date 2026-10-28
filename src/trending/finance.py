"""财经：华尔街见闻、财联社、金十数据、雪球、格隆汇、法布财经、MKTNews。"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlencode

from .core import FetchError, Http, Item, clean, fetcher, parse_relative_date, soup, to_iso

# ---------------------------------------------------------------- 华尔街见闻


@fetcher("wallstreetcn-quick")
def wallstreetcn_quick(http: Http) -> list[Item]:
    res = http.json("https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30")
    return [
        Item(id=str(k["id"]), title=k.get("title") or k.get("content_text", ""), url=k["uri"], time=to_iso(k.get("display_time")))
        for k in res["data"]["items"]
    ]


@fetcher("wallstreetcn-news")
def wallstreetcn_news(http: Http) -> list[Item]:
    res = http.json("https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30")
    items: list[Item] = []
    for k in res["data"]["items"]:
        h = k.get("resource") or {}
        if k.get("resource_type") in ("theme", "ad") or h.get("type") == "live" or not h.get("uri"):
            continue
        items.append(Item(id=str(h["id"]), title=h.get("title") or h.get("content_short", ""), url=h["uri"],
                          time=to_iso(h.get("display_time"))))
    return items


@fetcher("wallstreetcn-hot")
def wallstreetcn_hot(http: Http) -> list[Item]:
    res = http.json("https://api-one.wallstcn.com/apiv1/content/articles/hot?period=all")
    return [Item(id=str(h["id"]), title=h.get("title", ""), url=h["uri"]) for h in res["data"]["day_items"]]


# ---------------------------------------------------------------- 财联社


def cls_query(**extra: object) -> str:
    """财联社网页端的公开参数（不复刻客户端的请求签名）。"""
    params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5", **{k: str(v) for k, v in extra.items()}}
    return urlencode(params)


def _cls_data(res: dict) -> object:
    if "data" not in res:
        raise FetchError(f"接口拒绝了请求（需要客户端签名，未移植）：{res.get('errno', '')} {res.get('msg', '')}".strip())
    return res["data"]


def _cls_item(k: dict) -> Item:
    return Item(id=str(k["id"]), title=k.get("title") or k.get("brief", ""), url=f"https://www.cls.cn/detail/{k['id']}",
                mobile_url=k.get("shareurl", ""), time=to_iso(k.get("ctime")))


@fetcher("cls-telegraph")
def cls_telegraph(http: Http) -> list[Item]:
    query = cls_query(last_time=int(time.time()), refresh_type=1, rn=30)
    res = http.json(f"https://www.cls.cn/v1/roll/get_roll_list?{query}")
    return [_cls_item(k) for k in _cls_data(res)["roll_data"] if not k.get("is_ad")]


@fetcher("cls-depth")
def cls_depth(http: Http) -> list[Item]:
    res = http.json(f"https://www.cls.cn/v3/depth/home/assembled/1000?{cls_query()}")
    return [_cls_item(k) for k in sorted(_cls_data(res)["depth_list"], key=lambda k: k.get("ctime", 0), reverse=True)]


@fetcher("cls-hot")
def cls_hot(http: Http) -> list[Item]:
    res = http.json(f"https://www.cls.cn/v2/article/hot/list?{cls_query()}")
    items = [_cls_item(k) for k in _cls_data(res)]
    for item in items:
        item.time = ""  # 热门榜按热度排序，时间意义不大
    return items


# ---------------------------------------------------------------- 其他


@fetcher("jin10")
def jin10(http: Http) -> list[Item]:
    raw = http.text(f"https://www.jin10.com/flash_newest.js?t={int(time.time() * 1000)}")
    return parse_jin10(raw)


def parse_jin10(raw: str) -> list[Item]:
    text = re.sub(r"^\s*var\s+newest\s*=\s*", "", raw)
    text = re.sub(r";*\s*$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("金十快讯格式变了") from exc
    items: list[Item] = []
    for k in data:
        body = k.get("data") or {}
        content = body.get("title") or body.get("content")
        if not content or 5 in (k.get("channel") or []):
            continue
        content = re.sub(r"</?b>", "", content)
        match = re.match(r"^【([^】]*)】(.*)$", content, re.S)
        items.append(Item(
            id=str(k["id"]),
            title=match.group(1) if match else content,
            url=f"https://flash.jin10.com/detail/{k['id']}",
            hover=match.group(2) if match else "",
            info="重要" if k.get("important") else "",
            time=to_iso(k.get("time")),
        ))
    return items


@fetcher("xueqiu-hotstock")
def xueqiu_hotstock(http: Http) -> list[Item]:
    res = http.json("https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size=30&_type=10&type=10")
    items: list[Item] = []
    for k in res["data"]["items"]:
        if k.get("ad"):
            continue
        percent = k.get("percent")
        sign = "+" if isinstance(percent, (int, float)) and percent > 0 else ""
        items.append(Item(id=k["code"], title=k["name"], url=f"https://xueqiu.com/s/{k['code']}",
                          info=f"{sign}{percent}% {k.get('exchange', '')}".strip()))
    return items


@fetcher("gelonghui")
def gelonghui(http: Http) -> list[Item]:
    base = "https://www.gelonghui.com"
    page = soup(http.text(f"{base}/news/"))
    items: list[Item] = []
    for el in page.select(".article-content"):
        a = el.select_one(".detail-right > a")
        title = a.select_one("h2") if a else None
        if not a or not a.get("href") or not title:
            continue
        info = el.select_one(".time > span:nth-child(1)")
        when = el.select_one(".time > span:nth-child(3)")
        items.append(Item(id=a["href"], title=title.get_text(strip=True), url=base + a["href"],
                          info=info.get_text(strip=True) if info else "",
                          time=parse_relative_date(when.get_text() if when else "")))
    return items


@fetcher("fastbull-express")
def fastbull_express(http: Http) -> list[Item]:
    base = "https://www.fastbull.com"
    page = soup(http.text(f"{base}/cn/express-news"))
    items: list[Item] = []
    for el in page.select(".content-list.news-list"):
        a = el.select_one(".title_name")
        ref = el.select_one("[data-href]")
        path = ref.get("data-href") if ref else None
        if not path:
            ref = el.select_one("[data-id]")
            path = ref.get("data-id") if ref else None
        if not a or not path:
            continue
        text = clean(a.get_text())
        match = re.search(r"【(.+)】", text)
        title = match.group(1) if match and len(match.group(1)) >= 4 else text
        pathname = path if path.startswith("/") else f"/cn/fastshort/{path}"
        items.append(Item(id=path, title=title, url=base + pathname, time=to_iso(el.get("data-date"))))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("fastbull-news")
def fastbull_news(http: Http) -> list[Item]:
    base = "https://www.fastbull.com"
    page = soup(http.text(f"{base}/cn/news"))
    items: list[Item] = []
    for a in page.select(".trending_type"):
        href = a.get("href")
        title = a.select_one(".title")
        date = a.select_one("[data-date]")
        if href and title:
            items.append(Item(id=href, title=title.get_text(strip=True), url=href if href.startswith("http") else base + href,
                              time=to_iso(date.get("data-date")) if date else ""))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("mktnews-flash")
def mktnews_flash(http: Http) -> list[Item]:
    res = http.json("https://api.mktnews.net/api/flash?type=0&limit=50")
    items: list[Item] = []
    for k in res["data"]:
        body = k.get("data") or {}
        content = body.get("content") or ""
        match = re.match(r"^【([^】]*)】(.*)$", content, re.S)
        items.append(Item(
            id=str(k["id"]),
            title=body.get("title") or (match.group(1) if match else content),
            url=f"https://mktnews.net/flashDetail.html?id={k['id']}",
            info="重要" if k.get("important") == 1 else "",
            hover=content,
            time=to_iso(k.get("time")),
        ))
    return sorted(items, key=lambda k: k.time, reverse=True)
