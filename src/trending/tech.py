"""科技：GitHub Trending、Hacker News、Product Hunt、V2EX、IT之家、掘金、少数派、36氪、AIHOT、Solidot、远景论坛。"""

from __future__ import annotations

import re
import time
from datetime import datetime

from .core import CST, FetchError, Http, Item, clean, fetcher, parse_relative_date, rss_items, soup, to_iso


@fetcher("github-trending-today")
def github_trending_today(http: Http) -> list[Item]:
    page = soup(http.text("https://github.com/trending?spoken_language_code="))
    items: list[Item] = []
    for article in page.select("article.Box-row") or page.select("main .Box div[data-hpc] > article"):
        a = article.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        repo = re.sub(r"\s+", "", a.get_text())
        stars = article.select_one('a[href$="/stargazers"]')
        today = article.select_one("span.d-inline-block.float-sm-right")
        desc = article.select_one("p")
        info = " · ".join(x for x in (
            f"★ {clean(stars.get_text())}" if stars else "",
            clean(today.get_text()).replace("stars today", "今日") if today else "",
        ) if x)
        items.append(Item(id=a["href"], title=repo, url="https://github.com" + a["href"], info=info,
                          hover=desc.get_text() if desc else ""))
    return items


@fetcher("hackernews")
def hackernews(http: Http) -> list[Item]:
    base = "https://news.ycombinator.com"
    try:
        page = soup(http.text(base))
        items: list[Item] = []
        for row in page.select(".athing"):
            story_id = row.get("id")
            a = row.select_one(".titleline a")
            score = page.select_one(f"#score_{story_id}") if story_id else None
            if story_id and a:
                items.append(Item(id=story_id, title=a.get_text(), url=f"{base}/item?id={story_id}",
                                  info=score.get_text() if score else ""))
        if items:
            return items
    except FetchError:
        pass
    # 直连失败时退回 hnrss
    items = rss_items(http, "https://hnrss.org/frontpage?count=30")
    for item in items:
        match = re.search(r'Comments URL: <a href="([^"]+)"', item.hover) or re.search(r"(https://news\.ycombinator\.com/item\?id=\d+)", item.hover)
        points = re.search(r"Points: (\d+)", item.hover)
        if match:
            item.url = match.group(1)
            item.id = item.url.rsplit("=", 1)[-1]
        item.info = f"{points.group(1)} points" if points else ""
        item.hover = ""
    return items


@fetcher("producthunt")
def producthunt(http: Http) -> list[Item]:
    return rss_items(http, "https://www.producthunt.com/feed")


@fetcher("v2ex-share")
def v2ex_share(http: Http) -> list[Item]:
    items: list[Item] = []
    for node in ("create", "ideas", "programmer", "share"):
        res = http.json(f"https://www.v2ex.com/feed/{node}.json")
        for k in res["items"]:
            items.append(Item(id=k["id"], title=k["title"], url=k["url"],
                              time=to_iso(k.get("date_modified") or k.get("date_published"))))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("ithome")
def ithome(http: Http) -> list[Item]:
    page = soup(http.text("https://www.ithome.com/list/"))
    items: list[Item] = []
    for li in page.select("#list > div.fl > ul > li"):
        a = li.select_one("a.t")
        date = li.select_one("i")
        if not a or not a.get("href"):
            continue
        url, title = a["href"], a.get_text(strip=True)
        if "lapin" in url or any(word in title for word in ("神券", "优惠", "补贴", "京东")):
            continue  # 广告
        items.append(Item(id=url, title=title, url=url, time=parse_relative_date(date.get_text() if date else "")))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("juejin")
def juejin(http: Http) -> list[Item]:
    res = http.json("https://api.juejin.cn/content_api/v1/content/article_rank?category_id=1&type=hot&spider=0")
    items: list[Item] = []
    for k in res["data"]:
        content = k["content"]
        hot = (k.get("content_counter") or {}).get("hot_rank")
        items.append(Item(id=content["content_id"], title=content["title"],
                          url=f"https://juejin.cn/post/{content['content_id']}", info=f"热度 {hot}" if hot else ""))
    return items


@fetcher("sspai")
def sspai(http: Http) -> list[Item]:
    url = (
        "https://sspai.com/api/v1/article/tag/page/get?limit=30&offset=0"
        f"&created_at={int(time.time() * 1000)}&tag=%E7%83%AD%E9%97%A8%E6%96%87%E7%AB%A0&released=false"
    )
    return [Item(id=str(k["id"]), title=k["title"], url=f"https://sspai.com/post/{k['id']}") for k in http.json(url)["data"]]


@fetcher("36kr-quick")
def kr36_quick(http: Http) -> list[Item]:
    base = "https://www.36kr.com"
    page = soup(http.text(f"{base}/newsflashes"))
    items: list[Item] = []
    for el in page.select(".newsflash-item"):
        a = el.select_one("a.item-title")
        when = el.select_one(".time")
        if a and a.get("href"):
            items.append(Item(id=a["href"], title=a.get_text(strip=True), url=base + a["href"],
                              time=parse_relative_date(when.get_text() if when else "")))
    return items


@fetcher("36kr-renqi")
def kr36_renqi(http: Http) -> list[Item]:
    base = "https://36kr.com"
    today = datetime.now(CST).strftime("%Y-%m-%d")
    page = soup(http.text(f"{base}/hot-list/renqi/{today}/1", headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }))
    items: list[Item] = []
    for el in page.select(".article-item-info"):
        a = el.select_one("a.article-item-title.weight-bold")
        if not a or not a.get("href"):
            continue
        href = a["href"]
        author = el.select_one(".kr-flow-bar-author")
        hot = el.select_one(".kr-flow-bar-hot span")
        desc = el.select_one("a.article-item-description")
        items.append(Item(
            id=href,
            title=a.get_text(strip=True),
            url=href if href.startswith("http") else base + href,
            info=" · ".join(x.get_text(strip=True) for x in (author, hot) if x),
            hover=desc.get_text() if desc else "",
        ))
    return items or kr36_quick(http)


@fetcher("aihot")
def aihot(http: Http) -> list[Item]:
    return rss_items(http, "https://aihot.news/feed/all.xml?aihot_actor=8d0ffb92-7f76-45e4-9d1b-8341f0eabf6c")


@fetcher("solidot")
def solidot(http: Http) -> list[Item]:
    return rss_items(http, "https://www.solidot.org/index.rss")


@fetcher("pcbeta-windows11")
def pcbeta_windows11(http: Http) -> list[Item]:
    # 远景论坛常对自动访问返回反爬验证页，这里不做处理，拿不到就如实记为失败
    return rss_items(http, "https://bbs.pcbeta.com/forum.php?mod=rss&fid=563&auth=0")
