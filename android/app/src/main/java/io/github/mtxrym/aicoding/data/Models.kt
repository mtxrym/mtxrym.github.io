package io.github.mtxrym.aicoding.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.time.Instant
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/** blog.json 中的一条内容。字段全部带默认值，兼容旧版只有 title / sub_title 的数据。 */
@Serializable
data class FeedItem(
    val title: String = "",
    @SerialName("sub_title") val subTitle: String = "",
    @SerialName("url_title") val urlTitle: String = "",
    @SerialName("external_url") val externalUrl: String = "",
    @SerialName("source_id") val sourceId: String = "",
    @SerialName("source_ids") val sourceIds: List<String> = emptyList(),
    @SerialName("source_host") val sourceHost: String = "",
    val category: String = "",
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("first_seen_at") val firstSeenAt: String? = null,
    val score: Double? = null,
    val scores: ScoreParts? = null,
    val keywords: List<String> = emptyList(),
    val summary: String = "",
    val authors: List<String> = emptyList(),
    @SerialName("author_count") val authorCount: Int = 0,
    val upvotes: Int = 0,
    val likes: Int = 0,
    @SerialName("github_url") val githubUrl: String = "",
    @SerialName("github_stars") val githubStars: Int = 0,
    @SerialName("hf_url") val hfUrl: String = "",
    val topics: List<String> = emptyList(),
    @SerialName("summary_zh") val summaryZh: String = "",
    @SerialName("reason_zh") val reasonZh: String = "",
    @SerialName("relevance_source") val relevanceSource: String = "rules",
    val digest: Digest? = null,
) {
    val llmJudged: Boolean get() = relevanceSource == "llm"

    /** 优先展示大模型给的中文主题，没有时退回关键词。 */
    val tags: List<String> get() = topics.ifEmpty { keywords }

    /** 与网页一致的 id 规则，收藏在两端含义相同。 */
    val id: String get() = externalUrl.ifBlank { urlTitle.ifBlank { title } }

    val effectiveScore: Double
        get() = score ?: LEGACY_SCORE.find(subTitle)?.groupValues?.get(1)?.toDoubleOrNull() ?: 0.0

    val effectiveCategory: String
        get() = category.ifBlank { subTitle.substringBefore('·').trim().ifBlank { "papers" } }

    val effectiveSources: List<String>
        get() = sourceIds.ifEmpty {
            listOf(sourceId.ifBlank { LEGACY_SOURCE.find(subTitle)?.groupValues?.get(1) ?: sourceHost.ifBlank { "unknown" } })
        }

    val publishedInstant: Instant? get() = parseInstant(publishedAt)
    val firstSeenInstant: Instant? get() = parseInstant(firstSeenAt)

    val link: String get() = externalUrl.ifBlank { "https://mtxrym.github.io/" }

    private companion object {
        val LEGACY_SCORE = Regex("""score=([\d.]+)""")
        val LEGACY_SOURCE = Regex("""source=([\w-]+)""")
    }
}

/** 论文解读：问题 / 方法 / 结果 / 启示 / 局限。basis 为 fulltext（基于全文）或 abstract（基于摘要）。 */
@Serializable
data class Digest(
    val problem: String = "",
    val method: List<String> = emptyList(),
    val results: List<String> = emptyList(),
    val takeaways: List<String> = emptyList(),
    val limitations: String = "",
    val basis: String = "abstract",
) {
    val isValid: Boolean get() = problem.isNotBlank()
    val basisLabel: String get() = if (basis == "fulltext") "基于全文" else "基于摘要"
    val searchText: String get() = (listOf(problem, limitations) + method + results + takeaways).joinToString(" ")
}

@Serializable
data class ScoreParts(
    val relevance: Double = 0.0,
    val popularity: Double = 0.0,
    val freshness: Double = 0.0,
    val impact: Double = 0.0,
)

/** data/status.json：数据源健康状态与当前生效的更新策略。 */
@Serializable
data class FeedStatus(
    @SerialName("generated_at") val generatedAt: String? = null,
    val policy: Policy = Policy(),
    val llm: LlmStatus = LlmStatus(),
    val sources: List<SourceStatus> = emptyList(),
    val totals: Totals = Totals(),
) {
    val generatedInstant: Instant? get() = parseInstant(generatedAt)
}

@Serializable
data class Policy(
    val schedule: Schedule = Schedule(),
    @SerialName("window_days") val windowDays: Int = 0,
    @SerialName("max_items") val maxItems: Int = 0,
    @SerialName("max_datasets") val maxDatasets: Int = 0,
    @SerialName("min_relevance") val minRelevance: Double = 0.0,
    @SerialName("retention_days") val retentionDays: Int = 0,
    @SerialName("stale_after_hours") val staleAfterHours: Int = 96,
    val weights: Map<String, Double> = emptyMap(),
    val llm: PolicyLlm = PolicyLlm(),
)

@Serializable
data class PolicyLlm(@SerialName("min_score") val minScore: Double = 60.0)

/** 大模型复核状态（status.json 的 llm 字段）。 */
@Serializable
data class LlmStatus(
    val enabled: Boolean = false,
    val model: String = "",
    @SerialName("model_label") val modelLabel: String = "",
    val reason: String? = null,
    val healthy: Boolean = true,
    val coverage: Int = 0,
) {
    val displayName: String get() = modelLabel.ifBlank { model }
}

@Serializable
data class Schedule(val cron: String = "", val description: String = "")

@Serializable
data class SourceStatus(
    val id: String = "",
    val label: String = "",
    val category: String = "",
    val ok: Boolean = true,
    val fetched: Int = 0,
    val relevant: Int = 0,
    val error: String? = null,
)

@Serializable
data class Totals(
    val archive: Int = 0,
    val displayed: Int = 0,
    @SerialName("sources_ok") val sourcesOk: Int = 0,
    @SerialName("sources_total") val sourcesTotal: Int = 0,
)

/** GitHub Actions 中“Update AI Coding Feed”最近一次运行。 */
data class WorkflowRun(
    val status: String,
    val conclusion: String?,
    val updatedAt: Instant?,
    val htmlUrl: String,
)

/** ISO 8601（新版数据）与 RFC 1123（旧版 arXiv 日期）都能解析。 */
fun parseInstant(raw: String?): Instant? {
    if (raw.isNullOrBlank()) return null
    return runCatching { Instant.parse(raw) }.getOrNull()
        ?: runCatching { ZonedDateTime.parse(raw, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant() }.getOrNull()
        ?: runCatching { ZonedDateTime.parse(raw, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant() }.getOrNull()
}
