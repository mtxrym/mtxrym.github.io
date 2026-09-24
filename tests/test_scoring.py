import unittest
from datetime import datetime, timezone

from src.scoring import Item, compute_popularity_score, compute_time_decay_score, detect_impact_signals, score_item

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class ScoringTest(unittest.TestCase):
    def test_freshness_uses_calendar_days(self):
        morning = datetime(2026, 9, 24, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(compute_time_decay_score(morning, NOW), 100.0)
        three_days = datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc)
        self.assertAlmostEqual(compute_time_decay_score(three_days, NOW, half_life_days=3), 50.0)

    def test_rfc2822_dates_are_not_treated_as_missing(self):
        # 旧版 bug：arXiv 的 RFC 2822 日期解析失败，新鲜度恒为 0
        from src.sources import parse_datetime

        published = parse_datetime("Thu, 24 Sep 2026 00:00:00 -0400")
        self.assertIsNotNone(published)
        self.assertEqual(compute_time_decay_score(published, NOW), 100.0)

    def test_popularity_is_monotonic_and_bounded(self):
        values = [compute_popularity_score(upvotes=n) for n in (0, 10, 100, 1000, 100000)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0)
        self.assertLessEqual(values[-1], 100)

    def test_impact_signals(self):
        item = Item(
            title="X",
            item_type="paper",
            abstract="We introduce a new benchmark for agents. Code is available at https://github.com/a/b. It outperforms baselines.",
        )
        self.assertEqual(set(detect_impact_signals(item)), {"open_source_code", "new_benchmark", "sota"})

    def test_importance_in_range_and_weights_normalized(self):
        item = Item(
            title="SWE-bench coding agent for repository-level program repair",
            item_type="paper",
            abstract="An LLM coding agent.",
            published_at=NOW,
            upvotes=200,
        )
        a = score_item(item, NOW, weights={"relevance": 1, "popularity": 1, "freshness": 1, "impact": 1})
        b = score_item(item, NOW, weights={"relevance": 2, "popularity": 2, "freshness": 2, "impact": 2})
        self.assertAlmostEqual(a.importance_score, b.importance_score)
        self.assertTrue(0 <= a.importance_score <= 100)


if __name__ == "__main__":
    unittest.main()
