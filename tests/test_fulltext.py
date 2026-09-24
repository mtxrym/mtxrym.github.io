import unittest

from src.fulltext import abstract_from_abs_page, html_to_text, truncate_paper

PAGE = """<html><head><style>.x{}</style><script>var a=1;</script></head><body>
<nav class="ltx_page_navbar">菜单</nav>
<article class="ltx_document ltx_authors_1line">
  <h1 class="ltx_title">CodeFoo: A Title</h1>
  <div class="ltx_authors"><span class="ltx_personname">Alice</span></div>
  <div class="ltx_abstract"><h6>Abstract</h6><p>We study coding agents.</p></div>
  <nav class="ltx_TOC"><ol class="ltx_toclist"><li>TOC-ENTRY</li></ol></nav>
  <section class="ltx_section"><h2>1 Introduction</h2>
    <p>Agents score <math alttext="42\\%"><mi>42</mi><mo>%</mo></math> on SWE-bench.<br>Next line.</p>
    <figure><img src="x.png"><figcaption>Figure 1: Overview.</figcaption></figure>
  </section>
  <section class="ltx_bibliography"><h2>References</h2><ul><li>Smith et al. 2020</li></ul></section>
</article></body></html>"""


class FullTextTest(unittest.TestCase):
    def test_html_to_text_keeps_body_and_drops_noise(self):
        text = html_to_text(PAGE)
        self.assertIn("## CodeFoo: A Title", text)
        self.assertIn("We study coding agents.", text)
        self.assertIn("$42\\%$", text)  # 公式保留 LaTeX 源码
        self.assertIn("Figure 1: Overview.", text)
        for noise in ("菜单", "Alice", "TOC-ENTRY", "Smith et al.", "var a", ".x{}"):
            self.assertNotIn(noise, text)

    def test_truncate_keeps_conclusion(self):
        text = "## Abstract\n" + "a" * 5000 + "\n## 6 Conclusion\nWe conclude X works.\n"
        out = truncate_paper(text, 2000)
        self.assertLessEqual(len(out), 2100)
        self.assertIn("We conclude X works.", out)
        self.assertIn("中间省略", out)
        self.assertEqual(truncate_paper("short", 2000), "short")

    def test_abstract_from_abs_page(self):
        page = '<blockquote class="abstract mathjax"><span class="descriptor">Abstract:</span>COBOL &amp; LLMs\n  remain.</blockquote>'
        self.assertEqual(abstract_from_abs_page(page), "COBOL & LLMs remain.")
        self.assertEqual(abstract_from_abs_page("<html></html>"), "")


if __name__ == "__main__":
    unittest.main()
