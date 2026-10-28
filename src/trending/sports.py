"""体育：虎扑、懂球帝。"""

from __future__ import annotations

import re

from .core import Http, Item, fetcher, to_iso


@fetcher("hupu")
def hupu(http: Http) -> list[Item]:
    page = http.text("https://bbs.hupu.com/topic-daily-hot")
    pattern = re.compile(r'<li class="bbs-sl-web-post-body">[\s\S]*?<a href="(/[^"]+?\.html)"[^>]*?class="p-title"[^>]*>([^<]+)</a>')
    return [
        Item(id=path, title=title, url=f"https://bbs.hupu.com{path}")
        for path, title in pattern.findall(page)
    ]


@fetcher("dongqiudi")
def dongqiudi(http: Http) -> list[Item]:
    res = http.json("https://api.dongqiudi.com/app/tabs/web/1.json")
    items = [
        Item(id=str(k["id"]), title=k["title"], url=k.get("share") or k.get("url") or f"https://www.dongqiudi.com/article/{k['id']}",
             info=k.get("category") or "", time=to_iso(k.get("created_at")))
        for k in res["articles"]
    ]
    return sorted(items, key=lambda k: k.time, reverse=True)
