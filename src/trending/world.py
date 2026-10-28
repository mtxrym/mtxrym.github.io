"""国际：联合早报、卫星通讯社、参考消息、靠谱新闻、Steam 在线人数。"""

from __future__ import annotations

from .core import Http, Item, fetcher, parse_relative_date, rss_items, soup, to_iso


@fetcher("zaobao")
def zaobao(http: Http) -> list[Item]:
    base = "https://www.zaochenbao.com"
    page = soup(http.text(f"{base}/realtime/", encoding="gb18030"))
    items: list[Item] = []
    for a in page.select("div.list-block > a.item"):
        href = a.get("href")
        title = a.select_one(".eps")
        date = a.select_one(".pdt10")
        if href and title:
            when = date.get_text().replace("- ", " ") if date else ""
            items.append(Item(id=href, title=title.get_text(strip=True), url=base + href, time=parse_relative_date(when)))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("sputniknewscn")
def sputniknewscn(http: Http) -> list[Item]:
    page = soup(http.text("https://sputniknews.cn/services/widget/lenta/"))
    items: list[Item] = []
    for el in page.select(".lenta__item"):
        a = el.select_one("a")
        title = el.select_one(".lenta__item-text")
        date = el.select_one(".lenta__item-date")
        if a and a.get("href") and title:
            items.append(Item(
                id=a["href"],
                title=title.get_text(strip=True),
                url="https://sputniknews.cn" + a["href"],
                time=to_iso(date.get("data-unixtime")) if date else "",
            ))
    return items


@fetcher("cankaoxiaoxi")
def cankaoxiaoxi(http: Http) -> list[Item]:
    items: list[Item] = []
    for channel in ("zhongguo", "guandian", "gj"):
        res = http.json(f"http://china.cankaoxiaoxi.com/json/channel/{channel}/list.json")
        for k in res["list"]:
            d = k["data"]
            items.append(Item(id=str(d["id"]), title=d["title"], url=d["url"], time=to_iso(d.get("publishTime"))))
    return sorted(items, key=lambda k: k.time, reverse=True)


@fetcher("kaopu")
def kaopu(http: Http) -> list[Item]:
    return rss_items(http, "https://kaopunews.com/feed.xml")


@fetcher("steam")
def steam(http: Http) -> list[Item]:
    page = soup(http.text("https://store.steampowered.com/stats/stats/"))
    items: list[Item] = []
    for row in page.select("#detailStats tr.player_count_row"):
        a = row.select_one("a.gameLink")
        current = row.select_one("td:first-child .currentServers")
        if a and a.get("href"):
            items.append(Item(
                id=a["href"],
                title=a.get_text(strip=True),
                url=a["href"],
                info=f"在线 {current.get_text(strip=True)}" if current else "",
            ))
    return items
