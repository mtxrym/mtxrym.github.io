package io.github.mtxrym.aicoding.ui

import io.github.mtxrym.aicoding.domain.SortOrder

/** 界面可触发的操作。FeedViewModel 实现它；预览 / 截图测试使用 [NoopFeedActions]。 */
interface FeedActions {
    fun refresh() {}
    fun consumeMessage() {}
    fun setQuery(query: String) {}
    fun setCategory(category: String?) {}
    fun setSource(source: String?) {}
    fun setSort(sort: SortOrder) {}
    fun setFavoritesOnly(enabled: Boolean) {}
    fun resetFilters() {}
    fun toggleFavorite(id: String) {}
    fun toggleCompact() {}
}

object NoopFeedActions : FeedActions
