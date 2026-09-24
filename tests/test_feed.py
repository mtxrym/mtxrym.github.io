import unittest
from datetime import datetime, timedelta, timezone

from src.feed import merge_records, select_items, to_blog_item, update_archive
from src.policy import UpdatePolicy
from src.sources import Record

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)
ABSTRACT = "We present an LLM coding agent for repository-level program repair evaluated on SWE-bench."


def paper(source_id="arxiv_cs_se", arxiv_id="2609.00001", title="Coding agent for repository-level program repair", **kw):
    defaults = dict(
        source_id=source_id,
        category="papers",
        title=title,
        link=f"https://arxiv.org/abs/{arxiv_id}",
        published_at=NOW,
        summary=ABSTRACT,
        arxiv_id=arxiv_id,
    )
    defaults.update(kw)
    return Record(**defaults)


def dataset(name, rank=1):
    return Record(
        source_id="hf_datasets_swe",
        category="datasets",
        title=name,
        link=f"https://huggingface.co/datasets/{name}",
        published_at=NOW,
        summary="SWE-bench style tasks for coding agents.",
        trending_rank=rank,
        likes=100,
        prefiltered=True,
    )


class FeedTest(unittest.TestCase):
    def setUp(self):
        self.policy = UpdatePolicy(min_relevance=35, window_days=7, max_items=5, max_datasets=1, retention_days=14)

    def test_same_paper_from_two_sources_is_merged(self):
        records = [paper(), paper(source_id="hf_daily_papers", upvotes=30, github_url="https://github.com/x/y")]
        entries = merge_records(records, self.policy, NOW)
        self.assertEqual(len(entries), 1)
        entry = entries["arxiv:2609.00001"]
        self.assertEqual(entry["source_ids"], ["arxiv_cs_se", "hf_daily_papers"])
        self.assertEqual(entry["upvotes"], 30)
        self.assertEqual(entry["github_url"], "https://github.com/x/y")

    def test_archive_keeps_first_seen_and_filters_irrelevant(self):
        irrelevant = paper(arxiv_id="2609.00002", title="Protein folding with diffusion", summary="Biology.")
        fresh = merge_records([paper(), irrelevant], self.policy, NOW)
        archive = update_archive({}, fresh, self.policy, NOW, {"arxiv_cs_se"})
        self.assertEqual(list(archive), ["arxiv:2609.00001"])
        first_seen = archive["arxiv:2609.00001"]["first_seen_at"]

        later = NOW + timedelta(days=2)
        archive = update_archive(archive, merge_records([paper(upvotes=5)], self.policy, later), self.policy, later, {"arxiv_cs_se"})
        self.assertEqual(archive["arxiv:2609.00001"]["first_seen_at"], first_seen)
        self.assertEqual(archive["arxiv:2609.00001"]["last_seen_on"], "2026-09-26")

    def test_archive_prunes_by_last_seen(self):
        archive = update_archive({}, merge_records([paper()], self.policy, NOW), self.policy, NOW, set())
        still_listed = NOW + timedelta(days=30)
        kept = update_archive(archive, merge_records([paper()], self.policy, still_listed), self.policy, still_listed, set())
        self.assertIn("arxiv:2609.00001", kept)
        gone = update_archive(archive, {}, self.policy, still_listed, set())
        self.assertEqual(gone, {})

    def test_selection_window_and_dataset_quota(self):
        records = [paper(arxiv_id=f"2609.0000{i}") for i in range(3)] + [dataset("a/swe-1"), dataset("b/swe-2", rank=2)]
        archive = update_archive({}, merge_records(records, self.policy, NOW), self.policy, NOW, set())
        selected = select_items(archive, self.policy, NOW)
        self.assertEqual(sum(1 for e in selected if e["category"] == "datasets"), 1)
        self.assertEqual(len(selected), 4)
        self.assertEqual([e["scores"]["total"] for e in selected], sorted((e["scores"]["total"] for e in selected), reverse=True))

        outside_window = NOW + timedelta(days=8)
        self.assertEqual(select_items(archive, self.policy, outside_window), [])

    def test_blog_item_keeps_legacy_fields(self):
        archive = update_archive({}, merge_records([paper()], self.policy, NOW), self.policy, NOW, set())
        item = to_blog_item(select_items(archive, self.policy, NOW)[0])
        for field in ("title", "sub_title", "url_title", "external_url", "source_id", "source_host", "published_at"):
            self.assertIn(field, item)
        self.assertRegex(item["sub_title"], r"^papers · source=arxiv_cs_se · score=\d+\.\d$")
        self.assertEqual(item["source_host"], "arxiv.org")


if __name__ == "__main__":
    unittest.main()
