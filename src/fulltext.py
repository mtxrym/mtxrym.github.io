"""论文正文获取：arXiv HTML 全文（LaTeXML 渲染）→ 纯文本；没有 HTML 版本时退回 abs 页的完整摘要。"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from src.sources import http_get

HTML_URL = "https://arxiv.org/html/{id}"
ABS_URL = "https://arxiv.org/abs/{id}"

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "svg", "button", "form", "noscript"}
# 参考文献、目录、作者信息、页脚等对总结没有帮助
_SKIP_CLASSES = ("ltx_bibliography", "ltx_TOC", "ltx_toclist", "ltx_authors", "ltx_page_footer", "ltx_dates", "ltx_note_outer")
_VOID_TAGS = {"br", "img", "meta", "link", "input", "hr", "col", "source", "wbr", "area", "base", "embed", "param", "track"}
_BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "figcaption", "table", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.skip_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            if tag == "br" and self.skip_depth is None:
                self.parts.append("\n")
            return
        self.stack.append(tag)
        if self.skip_depth is not None:
            return
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "math":
            # 公式只保留 LaTeX 源码（alttext），避免 MathML 展开成一堆碎片
            alt = attr.get("alttext")
            if alt:
                self.parts.append(f" ${alt}$ ")
            self.skip_depth = len(self.stack)
            return
        # 按 class 名精确匹配：正文容器自身带有 ltx_authors_1line 之类的 class，不能用子串判断
        if tag in _SKIP_TAGS or classes.intersection(_SKIP_CLASSES):
            self.skip_depth = len(self.stack)
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("## ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS or tag not in self.stack:
            return
        # 容错：HTML 不规范时弹出到匹配的标签
        while self.stack:
            top = self.stack.pop()
            if self.skip_depth is not None and len(self.stack) < self.skip_depth:
                self.skip_depth = None
            if top == tag:
                break
        if self.skip_depth is None and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth is None:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """把 arXiv LaTeXML 页面转成纯文本（只取 <article> 正文部分）。"""
    match = re.search(r"<article\b.*?</article>", markup, re.S | re.I)
    parser = _TextExtractor()
    parser.feed(match.group(0) if match else markup)
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def abstract_from_abs_page(markup: str) -> str:
    match = re.search(r'<blockquote class="abstract[^"]*">(.*?)</blockquote>', markup, re.S)
    if not match:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^Abstract:\s*", "", text)


_CONCLUSION_RE = re.compile(r"^## (?:\d+(?:\.\d+)*\s+)?(?:Conclusions?|Discussion|Summary|Limitations)\b.*$", re.M | re.I)


def truncate_paper(text: str, max_chars: int) -> str:
    """超长时保留前 75%（摘要、引言、方法、实验）+ 结论部分，结论往往包含最重要的发现与局限。"""
    if len(text) <= max_chars:
        return text
    head_budget = int(max_chars * 0.75)
    match = None
    for match in _CONCLUSION_RE.finditer(text):
        pass  # 取最后一个结论类标题
    if match and match.start() > head_budget:
        tail = text[match.start() : match.start() + (max_chars - head_budget)]
        return text[:head_budget] + "\n\n[……中间省略……]\n\n" + tail
    return text[:max_chars]


@dataclass(slots=True)
class PaperText:
    text: str
    source: str  # fulltext | abstract


def fetch_paper_text(arxiv_id: str, *, max_chars: int, timeout: float = 30, retries: int = 1, use_fulltext: bool = True) -> PaperText | None:
    """优先取 HTML 全文（截断到 max_chars），失败时取 abs 页完整摘要；都失败返回 None。"""
    if use_fulltext:
        try:
            markup = http_get(HTML_URL.format(id=arxiv_id), timeout=timeout, retries=retries).decode("utf-8", errors="ignore")
            text = html_to_text(markup)
            # 过短说明不是正文（例如“HTML 版本不可用”的提示页）
            if len(text) > 2000:
                return PaperText(truncate_paper(text, max_chars), "fulltext")
        except RuntimeError:
            pass
    try:
        markup = http_get(ABS_URL.format(id=arxiv_id), timeout=timeout, retries=retries).decode("utf-8", errors="ignore")
    except RuntimeError:
        return None
    abstract = abstract_from_abs_page(markup)
    return PaperText(abstract, "abstract") if abstract else None
