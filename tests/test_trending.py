import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from src.trending import FETCHERS, FetchError, Item, load_sources, normalize
from src.trending.core import CST, USER_AGENT, extract_json_after, parse_feed, parse_relative_date, to_iso
from src.trending.finance import parse_jin10

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, body, status=200, url="https://example.com/"):
        self.content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.status_code = status
        self.url = url
        self.text = self.content.decode()
        self.apparent_encoding = "utf-8"

    def json(self):
        return json.loads(self.content)


class FakeHttp:
    """按 URL 前缀返回预置内容，不发真实请求。"""

    def __init__(self, routes):
        self.routes = routes

    def _match(self, url):
        for prefix, body in self.routes.items():
            if url.startswith(prefix):
                return body
        raise AssertionError(f"unexpected url {url}")

    def get(self, url, **kwargs):
        return FakeResponse(self._match(url), url=url)

    def text(self, url, **kwargs):
        return self.get(url).text

    def json(self, url, **kwargs):
        return self.get(url).json()


class SourceConfigTest(unittest.TestCase):
    def test_every_source_has_a_fetcher_and_vice_versa(self):
        ids = {s.id for s in load_sources()}
        self.assertEqual(ids, set(FETCHERS))
        self.assertGreaterEqual(len(ids), 40)

    def test_fetchers_send_plain_public_requests_only(self):
        # 不伪造 cookie / 来源页 / 签名，不处理反爬验证，UA 如实标明身份
        self.assertIn("mtxrym-trending", USER_AGENT)
        for path in (ROOT / "src" / "trending").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for banned in ('"Cookie"', '"Referer"', '"Origin"', "access_review", "X-App-Token", "Mozilla/5.0"):
                self.assertNotIn(banned, text, f"{path.name} 含有 {banned}")


class ParseHelpersTest(unittest.TestCase):
    NOW = datetime(2026, 10, 28, 12, 0, tzinfo=CST)

    def test_relative_dates(self):
        cases = {
            "刚刚": "2026-10-28T04:00:00Z",
            "5分钟前": "2026-10-28T03:55:00Z",
            "2小时前": "2026-10-28T02:00:00Z",
            "今天 09:30": "2026-10-28T01:30:00Z",
            "昨天 23:10": "2026-10-27T15:10:00Z",
            "10:15": "2026-10-28T02:15:00Z",
            "23:50": "2026-10-27T15:50:00Z",  # 晚于现在 → 昨天
            "10-02 17:06": "2026-10-02T09:06:00Z",
            "2025-12-31 08:00": "2025-12-31T00:00:00Z",
            "不是时间": "",
        }
        for text, expected in cases.items():
            self.assertEqual(parse_relative_date(text, now=self.NOW), expected, text)

    def test_to_iso(self):
        self.assertEqual(to_iso(1761624000), "2025-10-28T04:00:00Z")
        self.assertEqual(to_iso(1761624000000), "2025-10-28T04:00:00Z")
        self.assertEqual(to_iso("2026-10-28T03:00:00Z"), "2026-10-28T03:00:00Z")
        self.assertEqual(to_iso("2026-10-28 11:00:00"), "2026-10-28T03:00:00Z")  # 无时区按北京时间
        self.assertEqual(to_iso(None), "")
        self.assertEqual(to_iso(0), "")

    def test_extract_json_after_is_not_fooled_by_braces_in_strings(self):
        page = 'var allData = {"a": "x};y", "b": [1, 2]}; var other = 1;'
        self.assertEqual(extract_json_after(page, r"var\s+allData\s*=\s*"), {"a": "x};y", "b": [1, 2]})
        with self.assertRaises(FetchError):
            extract_json_after("<html></html>", r"var\s+allData\s*=\s*")

    def test_normalize_cleans_dedupes_and_caps(self):
        items = [
            Item(id="1", title="  <b>标题</b>&amp;一 ", url="https://a/1"),
            Item(id="1", title="重复", url="https://a/1"),
            Item(id="", title="没有 id 用 url", url="https://a/2"),
            Item(id="3", title="", url="https://a/3"),
            Item(id="4", title="没有链接", url=""),
        ] + [Item(id=f"x{i}", title=f"t{i}", url=f"https://b/{i}") for i in range(80)]
        result = normalize(items)
        self.assertEqual(result[0].title, "标题 &一")
        self.assertEqual(result[1].id, "https://a/2")
        self.assertEqual(len(result), 50)

    def test_parse_feed(self):
        rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
          <item><title>Hello</title><link>https://s/1</link><pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate></item>
        </channel></rss>"""
        [item] = parse_feed(rss, "https://s/feed")
        self.assertEqual((item.title, item.url, item.time), ("Hello", "https://s/1", "2026-10-27T10:00:00Z"))
        with self.assertRaises(FetchError):
            parse_feed(b"<html>challenge</html>", "https://s/feed")

    def test_parse_jin10(self):
        raw = 'var newest = [{"id":"1","time":"2026-10-28 11:00:00","important":1,"channel":[1],' \
              '"data":{"content":"<b>【标题】</b>正文"}},{"id":"2","time":"2026-10-28 10:00:00","channel":[5],' \
              '"data":{"content":"VIP"}},{"id":"3","time":"2026-10-28 09:00:00","data":{"content":"没有括号"}}];'
        items = parse_jin10(raw)
        self.assertEqual([i.id for i in items], ["1", "3"])
        self.assertEqual((items[0].title, items[0].hover, items[0].info), ("标题", "正文", "重要"))
        self.assertEqual(items[0].time, "2026-10-28T03:00:00Z")


class FetcherParsingTest(unittest.TestCase):
    def test_zhihu(self):
        http = FakeHttp({"https://www.zhihu.com/": {"data": [{"target": {
            "title_area": {"text": "问题"}, "excerpt_area": {"text": "摘要"}, "metrics_area": {"text": "100 万热度"},
            "link": {"url": "https://www.zhihu.com/question/123"}}}]}})
        [item] = FETCHERS["zhihu"](http)
        self.assertEqual((item.id, item.title, item.info), ("123", "问题", "100 万热度"))

    def test_baidu_skips_pinned(self):
        data = {"data": {"cards": [{"content": [
            {"word": "置顶", "rawUrl": "https://b/0", "isTop": True},
            {"word": "热点", "rawUrl": "https://b/1", "hotScore": "7809000", "desc": "说明"},
        ]}]}}
        http = FakeHttp({"https://top.baidu.com/": f"<html><!--s-data:{json.dumps(data)}--></html>"})
        [item] = FETCHERS["baidu"](http)
        self.assertEqual((item.title, item.info, item.hover), ("热点", "780.9万", "说明"))

    def test_hackernews_html(self):
        page = """<table><tr class="athing" id="42"><td><span class="titleline"><a href="https://x">Show HN</a></span></td></tr>
                  <tr><td><span class="score" id="score_42">99 points</span></td></tr></table>"""
        [item] = FETCHERS["hackernews"](FakeHttp({"https://news.ycombinator.com": page}))
        self.assertEqual((item.id, item.title, item.url, item.info), ("42", "Show HN", "https://news.ycombinator.com/item?id=42", "99 points"))

    def test_github_trending_html(self):
        page = """<main><article class="Box-row"><h2><a href="/owner/repo"> owner /
                  repo </a></h2><p> A tool </p><a href="/owner/repo/stargazers"> 1,234 </a>
                  <span class="d-inline-block float-sm-right">56 stars today</span></article></main>"""
        [item] = FETCHERS["github-trending-today"](FakeHttp({"https://github.com/trending": page}))
        self.assertEqual((item.title, item.url, item.info, item.hover), ("owner/repo", "https://github.com/owner/repo", "★ 1,234 · 56 今日", " A tool "))

    def test_hupu_regex(self):
        page = '<li class="bbs-sl-web-post-body"><div><a href="/123.html" class="p-title">热帖标题</a></div></li>'
        [item] = FETCHERS["hupu"](FakeHttp({"https://bbs.hupu.com/": page}))
        self.assertEqual((item.title, item.url), ("热帖标题", "https://bbs.hupu.com/123.html"))

    def test_cls_rejection_is_reported_clearly(self):
        http = FakeHttp({"https://www.cls.cn/": {"errno": 50001, "msg": "sign error"}})
        with self.assertRaisesRegex(FetchError, "签名"):
            FETCHERS["cls-hot"](http)


class FetchScriptTest(unittest.TestCase):
    def test_run_one_reports_ok_empty_and_parse_errors(self):
        from scripts.fetch_trending import run_one

        meta = load_sources()[0]
        fake = {
            "ok": lambda http: [Item(id="1", title="t", url="https://a")],
            "empty": lambda http: [],
            "broken": lambda http: {}["missing"],
        }
        results = {}
        for name, fn in fake.items():
            with mock.patch.dict(FETCHERS, {meta.id: fn}):
                results[name] = run_one(meta, timeout=1)
        self.assertEqual(results["ok"]["status"], "ok")
        self.assertEqual(results["ok"]["items"], [{"id": "1", "title": "t", "url": "https://a"}])
        self.assertEqual(results["empty"]["status"], "error")
        self.assertIn("没有解析到条目", results["empty"]["error"])
        self.assertTrue(re.match(r"解析失败：KeyError", results["broken"]["error"]))


if __name__ == "__main__":
    unittest.main()
