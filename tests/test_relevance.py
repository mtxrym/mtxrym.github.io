import unittest

from src.relevance import display_keywords, keyword_relevance


class KeywordRelevanceTest(unittest.TestCase):
    def test_core_ai_coding_paper_scores_high(self):
        result = keyword_relevance(
            "FeatLens: Feature-Guided Dynamic Code Graph Construction and Retrieval for Repository-Level Code Generation",
            "Large language models struggle with repository-level code generation in large codebases.",
        )
        self.assertGreaterEqual(result.score, 70)
        self.assertIn("repository-level", display_keywords(result))

    def test_software_engineering_without_ai_is_suppressed(self):
        result = keyword_relevance(
            "Understanding Maintenance and Support in a Community-Driven Scientific Workflow Ecosystem",
            "We study how developers maintain software in the Galaxy ecosystem through mining issue trackers.",
        )
        self.assertFalse(result.has_ai_signal)
        self.assertLess(result.score, 35)

    def test_ai_paper_mentioning_benchmark_once_in_abstract_is_suppressed(self):
        result = keyword_relevance(
            "Recovering Agentic Sovereignty: Mitigating the Consensus Paradox via Contrastive Epistemic Decoding",
            "Multi-agent LLM systems converge prematurely. We evaluate on reasoning tasks and SWE-bench.",
        )
        self.assertLess(result.score, 35)

    def test_code_release_boilerplate_is_not_a_topic_signal(self):
        result = keyword_relevance(
            "Stable Neural Decoding Across Sessions",
            "We propose a transformer model. Our code is available at https://github.com/x/y.",
        )
        self.assertEqual(result.score, 0)

    def test_linear_programming_is_not_programming(self):
        result = keyword_relevance("Online Linear Programming with Neural Networks", "A deep learning approach.")
        self.assertLess(result.score, 20)

    def test_prefiltered_dataset_counts_as_ai_signal(self):
        plain = keyword_relevance("openbmb/UltraData-Code")
        prefiltered = keyword_relevance("openbmb/UltraData-Code", prefiltered=True)
        self.assertGreater(prefiltered.score, plain.score)
        self.assertTrue(prefiltered.has_ai_signal)

    def test_score_is_bounded(self):
        text = " ".join(["coding agent swe-bench code generation program repair repository-level"] * 5)
        result = keyword_relevance(text, text)
        self.assertLessEqual(result.score, 100)
        self.assertGreaterEqual(result.score, 0)


if __name__ == "__main__":
    unittest.main()
