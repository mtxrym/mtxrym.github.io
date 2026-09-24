package io.github.mtxrym.aicoding.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.mtxrym.aicoding.data.FeedItem
import io.github.mtxrym.aicoding.data.FeedRepository
import io.github.mtxrym.aicoding.data.FeedSnapshot
import io.github.mtxrym.aicoding.data.UserPreferences
import io.github.mtxrym.aicoding.data.WorkflowRun
import io.github.mtxrym.aicoding.domain.FeedFilter
import io.github.mtxrym.aicoding.domain.SortOrder
import io.github.mtxrym.aicoding.domain.applyFilter
import io.github.mtxrym.aicoding.domain.dedupe
import io.github.mtxrym.aicoding.domain.sourceLabels
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class FeedUiState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val snapshot: FeedSnapshot? = null,
    val items: List<FeedItem> = emptyList(),
    val visible: List<FeedItem> = emptyList(),
    val filter: FeedFilter = FeedFilter(),
    val favorites: Set<String> = emptySet(),
    val compact: Boolean = false,
    val labels: Map<String, String> = emptyMap(),
    val workflowRun: WorkflowRun? = null,
    val message: String? = null,
)

private data class LoadState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val snapshot: FeedSnapshot? = null,
    val workflowRun: WorkflowRun? = null,
    val message: String? = null,
)

class FeedViewModel(application: Application) : AndroidViewModel(application), FeedActions {
    private val repository = FeedRepository(application)
    private val preferences = UserPreferences(application)

    private val load = MutableStateFlow(LoadState())
    private val filter = MutableStateFlow(FeedFilter())

    val state: StateFlow<FeedUiState> = combine(
        load,
        filter,
        preferences.favorites,
        preferences.compactView,
    ) { load, filter, favorites, compact ->
        val snapshot = load.snapshot
        val items = snapshot?.items?.let(::dedupe).orEmpty()
        val labels = sourceLabels(snapshot?.status)
        FeedUiState(
            loading = load.loading,
            refreshing = load.refreshing,
            snapshot = snapshot,
            items = items,
            visible = applyFilter(items, filter, favorites, labels),
            filter = filter,
            favorites = favorites,
            compact = compact,
            labels = labels,
            workflowRun = load.workflowRun,
            message = load.message,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), FeedUiState())

    init {
        viewModelScope.launch {
            repository.loadCached()?.let { cached -> load.update { it.copy(loading = false, snapshot = cached) } }
            refresh()
        }
    }

    override fun refresh() {
        if (load.value.refreshing) return
        viewModelScope.launch {
            load.update { it.copy(refreshing = true) }
            val run = async { repository.latestWorkflowRun() }
            val result = runCatching { repository.fetch() }
            load.update { current ->
                current.copy(
                    loading = false,
                    refreshing = false,
                    snapshot = result.getOrNull() ?: current.snapshot,
                    workflowRun = run.await() ?: current.workflowRun,
                    message = result.exceptionOrNull()?.let {
                        if (current.snapshot != null) "刷新失败，正在显示离线缓存" else "加载失败：${it.message}"
                    },
                )
            }
        }
    }

    override fun consumeMessage() = load.update { it.copy(message = null) }

    override fun setQuery(query: String) = filter.update { it.copy(query = query) }

    override fun setCategory(category: String?) = filter.update { it.copy(category = category) }

    override fun setSource(source: String?) = filter.update { it.copy(source = source) }

    override fun setSort(sort: SortOrder) = filter.update { it.copy(sort = sort) }

    override fun setFavoritesOnly(enabled: Boolean) = filter.update { it.copy(favoritesOnly = enabled) }

    override fun resetFilters() = filter.update { FeedFilter(sort = it.sort) }

    override fun toggleFavorite(id: String) {
        viewModelScope.launch { preferences.toggleFavorite(id) }
    }

    override fun toggleCompact() {
        viewModelScope.launch { preferences.setCompactView(!state.value.compact) }
    }
}
