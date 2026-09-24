import unittest

from src.sources import (
    FetchOptions,
    Source,
    clean_text,
    extract_arxiv_id,
    parse_arxiv_rss,
    parse_datetime,
    parse_hf_daily_papers,
    parse_hf_datasets,
    parse_sources,
)

RSS = """<?xml version='1.0' encoding='UTF-8'?>
<rss xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <item>
      <title>Schr\\"odinger's Code Repository: Have LLMs Learned SWE-bench?</title>
      <link>https://arxiv.org/abs/2609.26835</link>
      <description>arXiv:2609.26835v1 Announce Type: new
Abstract: We study coding agents on SWE-bench.</description>
      <guid>oai:arXiv.org:2609.26835v1</guid>
      <pubDate>Thu, 24 Sep 2026 00:00:00 -0400</pubDate>
      <arxiv:announce_type>new</arxiv:announce_type>
      <dc:creator>Alice A. (MIT, CSAIL), Bob B., Carol C. (ETH)</dc:creator>
    </item>
    <item>
      <title>An old paper, new version</title>
      <link>https://arxiv.org/abs/2501.00001</link>
      <description>arXiv:2501.00001v3 Announce Type: replace
Abstract: Old.</description>
      <pubDate>Thu, 24 Sep 2026 00:00:00 -0400</pubDate>
      <arxiv:announce_type>replace</arxiv:announce_type>
    </item>
  </channel>
</rss>"""

ARXIV_SOURCE = Source(id="arxiv_cs_se", type="arxiv_rss", category="papers", url="https://rss.arxiv.org/rss/cs.SE")


class ParsingTest(unittest.TestCase):
    def test_parse_datetime_formats(self):
        self.assertEqual(parse_datetime("2026-09-24T00:00:00.000Z").isoformat(), "2026-09-24T00:00:00+00:00")
        self.assertEqual(parse_datetime("Thu, 24 Sep 2026 00:00:00 -0400").isoformat(), "2026-09-24T04:00:00+00:00")
        self.assertIsNone(parse_datetime("not a date"))
        self.assertIsNone(parse_datetime(""))

    def test_extract_arxiv_id(self):
        self.assertEqual(extract_arxiv_id("https://arxiv.org/abs/2609.26835v2"), "2609.26835")
        self.assertEqual(extract_arxiv_id("oai:arXiv.org:2609.26835v1"), "2609.26835")
        self.assertEqual(extract_arxiv_id("2609.26835"), "2609.26835")
        self.assertEqual(extract_arxiv_id("https://huggingface.co/datasets/a/b"), "")

    def test_clean_text_converts_latex_accents(self):
        self.assertEqual(clean_text('Schr\\"odinger  and Erd\\H{o}s'), "Schrödinger and Erdős")

    def test_arxiv_rss_skips_replacements_and_parses_fields(self):
        records = parse_arxiv_rss(RSS, ARXIV_SOURCE, FetchOptions())
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.title, "Schrödinger's Code Repository: Have LLMs Learned SWE-bench?")
        self.assertEqual(record.arxiv_id, "2609.26835")
        self.assertEqual(record.authors, ["Alice A.", "Bob B.", "Carol C."])
        self.assertEqual(record.summary, "We study coding agents on SWE-bench.")
        self.assertEqual(record.published_at.isoformat(), "2026-09-24T04:00:00+00:00")

    def test_arxiv_rss_respects_limit(self):
        options = FetchOptions(limit=1, skip_announce_types=())
        self.assertEqual(len(parse_arxiv_rss(RSS, ARXIV_SOURCE, options)), 1)

    def test_hf_daily_papers(self):
        payload = [
            {
                "paper": {
                    "id": "2609.28256",
                    "title": "CodeMidas",
                    "summary": "Agentic coding RL.",
                    "upvotes": 42,
                    "publishedAt": "2026-09-23T00:00:00.000Z",
                    "submittedOnDailyAt": "2026-09-24T00:00:00.000Z",
                    "authors": [{"name": "A"}, {"name": "B"}],
                    "githubRepo": "https://github.com/x/codemidas",
                    "githubStars": 10,
                }
            },
            {"paper": {}},
        ]
        source = Source(id="hf_daily_papers", type="hf_daily_papers", category="papers", url="u")
        [record] = parse_hf_daily_papers(payload, source, FetchOptions())
        self.assertEqual(record.link, "https://arxiv.org/abs/2609.28256")
        self.assertEqual(record.upvotes, 42)
        self.assertEqual(record.authors, ["A", "B"])
        self.assertEqual(record.featured_at.isoformat(), "2026-09-24T00:00:00+00:00")

    def test_hf_datasets(self):
        payload = [{"id": "SWE-bench/SWE-bench_Verified", "likes": 160, "lastModified": "2026-08-16T04:23:43.000Z"}]
        source = Source(id="hf_datasets_swe", type="hf_datasets", category="datasets", url="u", prefiltered=True)
        [record] = parse_hf_datasets(payload, source, FetchOptions())
        self.assertEqual(record.link, "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified")
        self.assertEqual(record.trending_rank, 1)
        self.assertTrue(record.prefiltered)

    def test_unexpected_payload_raises(self):
        source = Source(id="x", type="hf_datasets", category="datasets", url="u")
        with self.assertRaises(RuntimeError):
            parse_hf_datasets({"error": "moved"}, source, FetchOptions())

    def test_parse_sources_validates(self):
        with self.assertRaises(ValueError):
            parse_sources({"papers": [{"id": "a", "type": "nope", "url": "u"}]})
        with self.assertRaises(ValueError):
            parse_sources({"papers": [{"id": "a", "type": "arxiv_rss", "url": "u"}, {"id": "a", "type": "arxiv_rss", "url": "u"}]})


if __name__ == "__main__":
    unittest.main()
