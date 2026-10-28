"""国内：微博、知乎、百度、抖音、头条、B 站、快手、贴吧、澎湃、凤凰、腾讯、牛客、豆瓣、视频站、Freebuf、虫部落。"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import quote

from .core import FetchError, Http, Item, compact_number, extract_json_after, fetcher, rss_items, soup, to_iso


@fetcher("weibo")
def weibo(http: Http) -> list[Item]:
    # 先试网页端的公开 JSON 接口，再试热搜榜页面；都需要登录态时如实失败
    try:
        res = http.json("https://weibo.com/ajax/side/hotSearch")
        items = [
            Item(id=k["word"], title=k.get("note") or k["word"],
                 url=f"https://s.weibo.com/weibo?q={quote('#' + k['word'] + '#')}",
                 info=" ".join(x for x in (compact_number(k["num"]) if k.get("num") else "", k.get("label_name", "")) if x))
            for k in (res.get("data") or {}).get("realtime") or []
            if not k.get("is_ad")
        ]
        if items:
            return items
    except FetchError:
        pass
    base = "https://s.weibo.com"
    page = http.text(f"{base}/top/summary?cate=realtimehot")
    items = []
    for row in soup(page).select("#pl_top_realtimehot table tbody tr")[1:]:
        link = next((a for a in row.select("td.td-02 a") if "javascript:void(0)" not in (a.get("href") or "")), None)
        if not link or not link.get("href"):
            continue
        title = link.get_text(strip=True)
        hot = row.select_one("td.td-02 span")
        flag = row.select_one("td.td-03")
        info = " ".join(x for x in (hot.get_text(strip=True) if hot else "", flag.get_text(strip=True) if flag else "") if x)
        items.append(Item(id=title, title=title, url=base + link["href"], info=info))
    return items


@fetcher("zhihu")
def zhihu(http: Http) -> list[Item]:
    res = http.json("https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true")
    items: list[Item] = []
    for k in res["data"]:
        target = k["target"]
        link = target["link"]["url"]
        match = re.search(r"(\d+)$", link)
        items.append(Item(
            id=match.group(1) if match else link,
            title=target["title_area"]["text"],
            url=link,
            info=target.get("metrics_area", {}).get("text", ""),
            hover=target.get("excerpt_area", {}).get("text", ""),
        ))
    return items


@fetcher("baidu")
def baidu(http: Http) -> list[Item]:
    page = http.text("https://top.baidu.com/board?tab=realtime")
    match = re.search(r"<!--s-data:(.*?)-->", page, re.S)
    if not match:
        raise FetchError("页面里没有找到 s-data（可能被拦截）")
    data = json.loads(match.group(1))
    return [
        Item(id=k["rawUrl"], title=k["word"], url=k["rawUrl"], info=compact_number(k.get("hotScore")) if k.get("hotScore") else "",
             hover=k.get("desc", ""))
        for k in data["data"]["cards"][0]["content"]
        if not k.get("isTop")
    ]


@fetcher("douyin")
def douyin(http: Http) -> list[Item]:
    res = http.json(
        "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1"
    )
    return [
        Item(id=k["sentence_id"], title=k["word"], url=f"https://www.douyin.com/hot/{k['sentence_id']}",
             info=compact_number(k.get("hot_value")) if k.get("hot_value") else "")
        for k in res["data"]["word_list"]
    ]


@fetcher("toutiao")
def toutiao(http: Http) -> list[Item]:
    res = http.json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    return [
        Item(id=k["ClusterIdStr"], title=k["Title"], url=f"https://www.toutiao.com/trending/{k['ClusterIdStr']}/",
             info=compact_number(k.get("HotValue")) if k.get("HotValue") else "")
        for k in res["data"]
    ]


def _bilibili_videos(http: Http, url: str) -> list[Item]:
    res = http.json(url)
    if res.get("code") != 0:
        raise FetchError(f"接口返回 code={res.get('code')}：{res.get('message', '')}")
    items: list[Item] = []
    for v in res["data"]["list"]:
        stat = v.get("stat", {})
        items.append(Item(
            id=v["bvid"],
            title=v["title"],
            url=f"https://www.bilibili.com/video/{v['bvid']}",
            info=f"{v.get('owner', {}).get('name', '')} · {compact_number(stat.get('view', 0))}播放",
            hover=v.get("desc", ""),
            time=to_iso(v.get("pubdate")),
        ))
    return items


@fetcher("bilibili-hot-search")
def bilibili_hot_search(http: Http) -> list[Item]:
    res = http.json("https://s.search.bilibili.com/main/hotword?limit=30")
    return [
        Item(id=k["keyword"], title=k.get("show_name") or k["keyword"],
             url=f"https://search.bilibili.com/all?keyword={quote(k['keyword'])}")
        for k in res["list"]
    ]


@fetcher("bilibili-hot-video")
def bilibili_hot_video(http: Http) -> list[Item]:
    return _bilibili_videos(http, "https://api.bilibili.com/x/web-interface/popular")


@fetcher("bilibili-ranking")
def bilibili_ranking(http: Http) -> list[Item]:
    return _bilibili_videos(http, "https://api.bilibili.com/x/web-interface/ranking/v2")


@fetcher("kuaishou")
def kuaishou(http: Http) -> list[Item]:
    page = http.text("https://www.kuaishou.com/?isHome=1")
    state = extract_json_after(page, r"window\.__APOLLO_STATE__\s*=\s*")
    client = state["defaultClient"]
    rank_id = client["ROOT_QUERY"]['visionHotRank({"page":"home"})']["id"]
    items: list[Item] = []
    for ref in client[rank_id]["items"]:
        hot = client.get(ref["id"], {})
        if hot.get("tagType") == "置顶" or not hot.get("name"):
            continue
        items.append(Item(
            id=ref["id"].replace("VisionHotRankItem:", ""),
            title=hot["name"],
            url=f"https://www.kuaishou.com/search/video?searchKey={quote(hot['name'])}",
            info=hot.get("hotValue", ""),
        ))
    return items


@fetcher("tieba")
def tieba(http: Http) -> list[Item]:
    res = http.json("https://tieba.baidu.com/hottopic/browse/topicList")
    return [
        Item(id=str(k["topic_id"]), title=k["topic_name"], url=k["topic_url"],
             info=f"{compact_number(k['discuss_num'])}讨论" if k.get("discuss_num") else "",
             hover=k.get("topic_desc", ""))
        for k in res["data"]["bang_topic"]["topic_list"]
    ]


@fetcher("thepaper")
def thepaper(http: Http) -> list[Item]:
    res = http.json("https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar")
    return [
        Item(id=str(k["contId"]), title=k["name"], url=f"https://www.thepaper.cn/newsDetail_forward_{k['contId']}",
             mobile_url=f"https://m.thepaper.cn/newsDetail_forward_{k['contId']}", time=to_iso(k.get("pubTimeLong")))
        for k in res["data"]["hotNews"]
    ]


@fetcher("ifeng")
def ifeng(http: Http) -> list[Item]:
    data = extract_json_after(http.text("https://www.ifeng.com/"), r"var\s+allData\s*=\s*")
    return [
        Item(id=k["url"], title=k["title"], url=k["url"], time=to_iso(k.get("newsTime")))
        for k in data.get("hotNews1", [])
    ]


@fetcher("tencent-hot")
def tencent_hot(http: Http) -> list[Item]:
    res = http.json("https://i.news.qq.com/web_backend/v2/getTagInfo?tagId=aEWqxLtdgmQ%3D")
    return [
        Item(id=str(k["id"]), title=k["title"], url=k["link_info"]["url"], hover=k.get("desc", ""))
        for k in res["data"]["tabs"][0]["articleList"]
    ]


@fetcher("nowcoder")
def nowcoder(http: Http) -> list[Item]:
    res = http.json(f"https://gw-c.nowcoder.com/api/sparta/hot-search/top-hot-pc?size=20&_={int(time.time() * 1000)}&t=")
    items: list[Item] = []
    for k in res["data"]["result"]:
        if k.get("type") == 74:
            items.append(Item(id=k["uuid"], title=k["title"], url=f"https://www.nowcoder.com/feed/main/detail/{k['uuid']}"))
        elif k.get("type") == 0:
            items.append(Item(id=str(k["id"]), title=k["title"], url=f"https://www.nowcoder.com/discuss/{k['id']}"))
    return items


@fetcher("douban")
def douban(http: Http) -> list[Item]:
    # movie.douban.com 选电影页用的公开接口（“热门”标签）
    res = http.json("https://movie.douban.com/j/search_subjects?type=movie&tag=%E7%83%AD%E9%97%A8&page_limit=50&page_start=0")
    return [
        Item(id=str(m["id"]), title=m["title"], url=m.get("url") or f"https://movie.douban.com/subject/{m['id']}",
             info=" · ".join(x for x in (f"{m['rate']}分" if m.get("rate") else "", "新片" if m.get("is_new") else "") if x))
        for m in res["subjects"]
    ]


_QQVIDEO_BODY = {
    "page_params": {
        "rank_channel_id": "100113", "rank_name": "HotSearch", "rank_page_size": "30",
        "tab_mvl_sub_mod_id": "792ac_19e77Sub_1b2", "tab_name": "热搜榜", "tab_type": "hot_rank",
        "tab_vl_data_src": "f5200deb4596bbf3", "page_id": "scms_shake", "page_type": "scms_shake",
        "source_key": "", "tag_id": "", "tag_type": "", "new_mark_label_enabled": "1",
    },
    "page_context": {"page_index": "1"},
    "flip_info": {
        "page_strategy_id": "", "page_module_id": "792ac_19e77", "module_strategy_id": {},
        "sub_module_id": "20251106065177",
        "flip_params": {
            "folding_screen_show_num": "", "is_mvl": "1",
            "mvl_strategy_info": '{"default_strategy_id":"06755800b45b49238582a6fa1ad0f5c5","default_version":"3836",'
                                 '"hit_page_uuid":"b5080d97dc694a5fb50eb9e7c99326ac","hit_tab_info":null,'
                                 '"gray_status_info":null,"bypass_to_un_exp_id":""}',
            "mvl_sub_mod_id": "20251106065177", "pad_post_show_num": "", "pad_pro_post_show_num": "",
            "pad_pro_small_hor_pic_display_num": "", "pad_small_hor_pic_display_num": "",
            "page_id": "scms_shake", "page_num": "0", "page_type": "scms_shake", "post_show_num": "",
            "shake_size": "", "small_hor_pic_display_num": "", "source_key": "100113",
            "un_policy_id": "06755800b45b49238582a6fa1ad0f5c5", "un_strategy_id": "06755800b45b49238582a6fa1ad0f5c5",
        },
        "relace_children_key": [],
    },
}


@fetcher("qqvideo-tv-hotsearch")
def qqvideo_tv_hotsearch(http: Http) -> list[Item]:
    res = http.post_json(
        "https://pbaccess.video.qq.com/trpc.vector_layout.page_view.PageService/getCard?video_appid=3000010&vversion_platform=2",
        _QQVIDEO_BODY,
    )
    cards = (((res.get("data") or {}).get("card") or {}).get("children_list") or {}).get("list", {}).get("cards") or []
    return [
        Item(id=c["id"], title=(c.get("params") or {}).get("title", ""), url=f"https://v.qq.com/x/cover/{c['id']}.html",
             hover=(c.get("params") or {}).get("sub_title", ""))
        for c in cards
    ]


@fetcher("iqiyi-hot-ranklist")
def iqiyi_hot_ranklist(http: Http) -> list[Item]:
    url = (
        "https://mesh.if.iqiyi.com/portal/lw/v7/channel/card/videoTab?channelName=recommend"
        "&data_source=v7_rec_sec_hot_rank_list&tempId=85&count=30&block_id=hot_ranklist"
        "&device=14a4b5ba98e790dce6dc07482447cf48&from=webapp"  # device 参数必须有
    )
    res = http.json(url)
    data = res["items"][0]["video"][0]["data"]
    return [
        Item(id=str(v["entity_id"]), title=v["title"], url=v["page_url"], info=v.get("desc", ""),
             hover=v.get("description", ""))
        for v in data
    ]


@fetcher("freebuf")
def freebuf(http: Http) -> list[Item]:
    # 被 WAF 拦截时返回挑战页，解析为空会如实记为失败
    return rss_items(http, "https://www.freebuf.com/feed")


@fetcher("chongbuluo-hot")
def chongbuluo_hot(http: Http) -> list[Item]:
    base = "https://www.chongbuluo.com/"
    page = soup(http.text(f"{base}forum.php?mod=guide&view=hot"))
    items: list[Item] = []
    for row in page.select(".bmw table tr"):
        title = row.select_one(".common .xst")
        link = row.select_one(".common a")
        if title and link and link.get("href"):
            items.append(Item(id=base + link["href"], title=title.get_text(strip=True), url=base + link["href"]))
    return items


@fetcher("chongbuluo-latest")
def chongbuluo_latest(http: Http) -> list[Item]:
    return rss_items(http, "https://www.chongbuluo.com/forum.php?mod=rss&view=newthread")

