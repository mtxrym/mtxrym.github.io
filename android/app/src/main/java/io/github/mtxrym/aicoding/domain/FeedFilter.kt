package io.github.mtxrym.aicoding.domain

import io.github.mtxrym.aicoding.data.FeedItem
import io.github.mtxrym.aicoding.data.FeedStatus

enum class SortOrder(val label: String) {
    SCORE("按得分"),
    DATE("按时间"),
    POPULARITY("按热度"),
}

data class FeedFilter(
    val query: String = "",
    val category: String? = null,
    val source: String? = null,
    val favoritesOnly: Boolean = false,
    val sort: SortOrder = SortOrder.SCORE,
) {
    val isActive: Boolean get() = query.isNotBlank() || category != null || source != null || favoritesOnly
}

val CATEGORY_LABELS = linkedMapOf("papers" to "论文", "datasets" to "数据集")

private val FALLBACK_SOURCE_LABELS = mapOf(
    "arxiv_cs_se" to "arXiv · cs.SE",
    "arxiv_cs_cl" to "arXiv · cs.CL",
    "arxiv_cs_ai" to "arXiv · cs.AI",
    "arxiv_cs_lg" to "arXiv · cs.LG",
    "hf_daily_papers" to "HF Daily Papers",
    "hf_datasets_code" to "HF 数据集 · code",
    "hf_datasets_swe" to "HF 数据集 · SWE",
)

fun categoryLabel(id: String): String = CATEGORY_LABELS[id] ?: id

fun sourceLabels(status: FeedStatus?): Map<String, String> =
    FALLBACK_SOURCE_LABELS + status?.sources.orEmpty().associate { it.id to it.label.ifBlank { it.id } }

/** 同一篇论文可能出现在多个来源里（旧版数据），合并为一条。 */
fun dedupe(items: List<FeedItem>): List<FeedItem> {
    val byId = LinkedHashMap<String, FeedItem>()
    for (item in items) {
        val existing = byId[item.id]
        byId[item.id] = if (existing == null) {
            item
        } else {
            existing.copy(
                sourceIds = (existing.effectiveSources + item.effectiveSources).distinct(),
                score = maxOf(existing.effectiveScore, item.effectiveScore),
            )
        }
    }
    return byId.values.toList()
}

private fun FeedItem.popularity(): Double = scores?.popularity ?: (upvotes + likes + githubStars).toDouble()

fun applyFilter(
    items: List<FeedItem>,
    filter: FeedFilter,
    favorites: Set<String>,
    labels: Map<String, String>,
): List<FeedItem> {
    val keyword = filter.query.trim().lowercase()
    return items
        .filter { item ->
            val matchesKeyword = keyword.isEmpty() || listOf(
                item.title,
                item.summaryZh,
                item.summary,
                item.topics.joinToString(" "),
                item.authors.joinToString(" "),
                item.keywords.joinToString(" "),
                item.effectiveSources.joinToString(" ") { labels[it] ?: it },
            ).any { it.lowercase().contains(keyword) }
            matchesKeyword &&
                (filter.category == null || item.effectiveCategory == filter.category) &&
                (filter.source == null || filter.source in item.effectiveSources) &&
                (!filter.favoritesOnly || item.id in favorites)
        }
        .sortedWith(
            when (filter.sort) {
                SortOrder.SCORE -> compareByDescending { it.effectiveScore }
                SortOrder.DATE -> compareByDescending<FeedItem> { (it.publishedInstant ?: it.firstSeenInstant)?.toEpochMilli() ?: 0L }
                    .thenByDescending { it.effectiveScore }
                SortOrder.POPULARITY -> compareByDescending<FeedItem> { it.popularity() }.thenByDescending { it.effectiveScore }
            },
        )
}

/** 各来源条数，按数量降序。 */
fun sourceCounts(items: List<FeedItem>): List<Pair<String, Int>> =
    items.flatMap { it.effectiveSources }.groupingBy { it }.eachCount().toList().sortedByDescending { it.second }

fun categoryCounts(items: List<FeedItem>): List<Pair<String, Int>> {
    val order = CATEGORY_LABELS.keys.toList()
    return items.groupingBy { it.effectiveCategory }.eachCount().toList()
        .sortedWith(compareBy({ order.indexOf(it.first).let { i -> if (i < 0) 99 else i } }, { it.first }))
}
