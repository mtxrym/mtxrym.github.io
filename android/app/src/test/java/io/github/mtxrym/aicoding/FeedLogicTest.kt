package io.github.mtxrym.aicoding

import io.github.mtxrym.aicoding.data.FeedItem
import io.github.mtxrym.aicoding.data.FeedRepository
import io.github.mtxrym.aicoding.data.FeedStatus
import io.github.mtxrym.aicoding.data.parseInstant
import io.github.mtxrym.aicoding.domain.FeedFilter
import io.github.mtxrym.aicoding.domain.Health
import io.github.mtxrym.aicoding.domain.SortOrder
import io.github.mtxrym.aicoding.domain.applyFilter
import io.github.mtxrym.aicoding.domain.categoryCounts
import io.github.mtxrym.aicoding.domain.compactNumber
import io.github.mtxrym.aicoding.domain.dedupe
import io.github.mtxrym.aicoding.domain.health
import io.github.mtxrym.aicoding.domain.relativeDay
import io.github.mtxrym.aicoding.domain.sourceLabels
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneOffset

class FeedLogicTest {
    private val json = FeedRepository.defaultJson

    private val newFormat = """
        [
          {"title": "CodeMidas: Agentic Coding RL", "sub_title": "papers · source=hf_daily_papers · score=73.3",
           "external_url": "https://arxiv.org/abs/2609.1", "source_id": "hf_daily_papers", "source_ids": ["hf_daily_papers"],
           "category": "papers", "published_at": "2026-09-18T00:00:00Z", "first_seen_at": "2026-09-24T04:33:52Z",
           "score": 73.3, "scores": {"relevance": 93.1, "popularity": 63.5, "freshness": 50.0, "impact": 40.0},
           "keywords": ["agentic coding"], "summary": "Training coding agents.", "authors": ["Bowen Ye"], "author_count": 19,
           "upvotes": 130, "unknown_future_field": true},
          {"title": "SWE-bench/SWE-bench_Verified", "external_url": "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
           "source_ids": ["hf_datasets_swe"], "category": "datasets", "published_at": "2026-08-16T04:23:43Z",
           "first_seen_at": "2026-09-24T04:33:52Z", "score": 54.4, "likes": 163}
        ]
    """.trimIndent()

    private val legacyFormat = """
        [
          {"title": "Old A", "sub_title": "papers · source=arxiv_cs_se · score=19.1", "url_title": "a",
           "external_url": "https://arxiv.org/abs/1", "source_id": "arxiv_cs_se", "published_at": "Wed, 23 Sep 2026 00:00:00 -0400"},
          {"title": "Old A (cross-list)", "sub_title": "papers · source=arxiv_cs_cl · score=10.7", "url_title": "a",
           "external_url": "https://arxiv.org/abs/1", "source_id": "arxiv_cs_cl", "published_at": "Wed, 23 Sep 2026 00:00:00 -0400"}
        ]
    """.trimIndent()

    private fun parse(text: String) = json.decodeFromString<List<FeedItem>>(text)

    @Test
    fun parsesNewFormatAndIgnoresUnknownFields() {
        val items = parse(newFormat)
        assertEquals(2, items.size)
        assertEquals(73.3, items[0].effectiveScore, 0.001)
        assertEquals(93.1, items[0].scores!!.relevance, 0.001)
        assertEquals("datasets", items[1].effectiveCategory)
        assertEquals(Instant.parse("2026-09-18T00:00:00Z"), items[0].publishedInstant)
    }

    @Test
    fun parsesLlmFieldsAndPrefersTopics() {
        val item = json.decodeFromString<FeedItem>(
            """{"title": "X", "keywords": ["swe-bench"], "topics": ["评测基准", "编程智能体"], "summary_zh": "中文总结",
                "reason_zh": "理由", "relevance_source": "llm"}""",
        )
        assertTrue(item.llmJudged)
        assertEquals(listOf("评测基准", "编程智能体"), item.tags)
        assertEquals("中文总结", item.summaryZh)
        val legacy = json.decodeFromString<FeedItem>("""{"title": "Y", "keywords": ["swe-bench"]}""")
        assertEquals(listOf("swe-bench"), legacy.tags)
        assertEquals(false, legacy.llmJudged)

        val status = json.decodeFromString<FeedStatus>(
            """{"llm": {"enabled": true, "model": "deepseek-flash", "model_label": "DeepSeek-V4.1-Flash", "coverage": 30}}""",
        )
        assertEquals("DeepSeek-V4.1-Flash", status.llm.displayName)
        assertEquals(30, status.llm.coverage)
        assertEquals(false, json.decodeFromString<FeedStatus>("{}").llm.enabled)
        // 中文总结和主题可被搜索
        assertEquals(1, applyFilter(listOf(item), FeedFilter(query = "中文总结"), emptySet(), sourceLabels(null)).size)
        assertEquals(1, applyFilter(listOf(item), FeedFilter(query = "编程智能体"), emptySet(), sourceLabels(null)).size)
    }

    @Test
    fun legacyFormatFallsBackToSubTitleAndRfcDates() {
        val items = parse(legacyFormat)
        assertEquals(19.1, items[0].effectiveScore, 0.001)
        assertEquals("papers", items[0].effectiveCategory)
        assertEquals(listOf("arxiv_cs_se"), items[0].effectiveSources)
        assertEquals(Instant.parse("2026-09-23T04:00:00Z"), items[0].publishedInstant)
    }

    @Test
    fun dedupeMergesSources() {
        val merged = dedupe(parse(legacyFormat))
        assertEquals(1, merged.size)
        assertEquals(listOf("arxiv_cs_se", "arxiv_cs_cl"), merged[0].effectiveSources)
        assertEquals(19.1, merged[0].effectiveScore, 0.001)
    }

    @Test
    fun filterMatchesKeywordsAuthorsAndSourceLabels() {
        val items = parse(newFormat)
        val labels = sourceLabels(null)
        assertEquals(1, applyFilter(items, FeedFilter(query = "agentic"), emptySet(), labels).size)
        assertEquals(1, applyFilter(items, FeedFilter(query = "bowen"), emptySet(), labels).size)
        assertEquals(1, applyFilter(items, FeedFilter(query = "HF 数据集"), emptySet(), labels).size)
        assertEquals(1, applyFilter(items, FeedFilter(category = "datasets"), emptySet(), labels).size)
        assertEquals(1, applyFilter(items, FeedFilter(source = "hf_daily_papers"), emptySet(), labels).size)
        val favorites = setOf("https://arxiv.org/abs/2609.1")
        assertEquals("CodeMidas: Agentic Coding RL", applyFilter(items, FeedFilter(favoritesOnly = true), favorites, labels).single().title)
    }

    @Test
    fun sortOrders() {
        val items = parse(newFormat)
        val labels = sourceLabels(null)
        assertEquals("SWE-bench/SWE-bench_Verified", applyFilter(items, FeedFilter(sort = SortOrder.DATE), emptySet(), labels).last().title)
        assertEquals("CodeMidas: Agentic Coding RL", applyFilter(items, FeedFilter(sort = SortOrder.SCORE), emptySet(), labels).first().title)
    }

    @Test
    fun categoryCountsPutPapersFirst() {
        assertEquals(listOf("papers", "datasets"), categoryCounts(parse(newFormat).reversed()).map { it.first })
    }

    @Test
    fun statusLabelsOverrideFallbacks() {
        val status = json.decodeFromString<FeedStatus>("""{"sources": [{"id": "arxiv_cs_se", "label": "arXiv SE"}], "totals": {"sources_ok": 7, "sources_total": 7}}""")
        assertEquals("arXiv SE", sourceLabels(status)["arxiv_cs_se"])
        assertEquals("HF Daily Papers", sourceLabels(status)["hf_daily_papers"])
    }

    @Test
    fun healthStates() {
        val now = Instant.parse("2026-09-24T12:00:00Z")
        val ok = json.decodeFromString<FeedStatus>("""{"policy": {"stale_after_hours": 96}, "totals": {"sources_ok": 7, "sources_total": 7}}""")
        val partial = json.decodeFromString<FeedStatus>("""{"totals": {"sources_ok": 5, "sources_total": 7}}""")
        val failed = json.decodeFromString<FeedStatus>("""{"totals": {"sources_ok": 0, "sources_total": 7}}""")
        assertEquals(Health.OK, health(ok, now.minusSeconds(3600), now))
        assertEquals(Health.STALE, health(ok, now.minusSeconds(97 * 3600), now))
        assertEquals(Health.PARTIAL, health(partial, now.minusSeconds(3600), now))
        assertEquals(Health.ERROR, health(failed, now, now))
        assertEquals(Health.UNKNOWN, health(null, null, now))
    }

    @Test
    fun relativeDayAndNumbers() {
        val now = Instant.parse("2026-09-24T12:00:00Z")
        assertEquals("今天", relativeDay(now, now, ZoneOffset.UTC))
        assertEquals("昨天", relativeDay(now.minusSeconds(86_400), now, ZoneOffset.UTC))
        assertEquals("5 天前", relativeDay(now.minusSeconds(5 * 86_400), now, ZoneOffset.UTC))
        assertEquals("8月1日", relativeDay(Instant.parse("2026-08-01T00:00:00Z"), now, ZoneOffset.UTC))
        assertEquals("1.2k", compactNumber(1234))
        assertEquals("3万", compactNumber(30_000))
        assertEquals("42", compactNumber(42))
    }

    @Test
    fun parsesRealRepositoryData() {
        // 直接解析仓库根目录下由 Python 流水线生成的真实数据，保证两端格式一致
        val root = generateSequence(java.io.File("").absoluteFile) { it.parentFile }.first { java.io.File(it, "blog.json").exists() }
        val items = parse(java.io.File(root, "blog.json").readText())
        assertTrue(items.isNotEmpty())
        assertTrue(items.all { it.title.isNotBlank() && it.effectiveScore > 0 })
        val status = json.decodeFromString<FeedStatus>(java.io.File(root, "data/status.json").readText())
        assertNotNull(status.generatedInstant)
        assertTrue(status.sources.isNotEmpty())
        assertNotNull(parseInstant(status.generatedAt))
    }
}
