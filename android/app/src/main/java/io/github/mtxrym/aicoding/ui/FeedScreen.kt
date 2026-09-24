package io.github.mtxrym.aicoding.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material.icons.rounded.ViewAgenda
import androidx.compose.material.icons.rounded.ViewHeadline
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.mtxrym.aicoding.data.FeedRepository
import io.github.mtxrym.aicoding.domain.SortOrder
import io.github.mtxrym.aicoding.domain.categoryCounts
import io.github.mtxrym.aicoding.domain.health
import io.github.mtxrym.aicoding.domain.relativeTime
import io.github.mtxrym.aicoding.domain.sourceCounts
import io.github.mtxrym.aicoding.ui.components.FeedItemCard
import io.github.mtxrym.aicoding.ui.components.FilterBar
import io.github.mtxrym.aicoding.ui.components.HealthBadge
import io.github.mtxrym.aicoding.ui.components.Kpi
import io.github.mtxrym.aicoding.ui.components.OverviewHeader
import io.github.mtxrym.aicoding.ui.components.StatusSheet
import io.github.mtxrym.aicoding.ui.components.openUrl
import kotlinx.coroutines.launch
import java.util.Locale

@Composable
fun FeedScreen(viewModel: FeedViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    FeedContent(state, viewModel)
}

/** 无状态的主界面：只依赖 [FeedUiState] 与 [FeedActions]，便于预览与截图测试。 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun FeedContent(state: FeedUiState, actions: FeedActions) {
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val scrollBehavior = TopAppBarDefaults.pinnedScrollBehavior()
    var showStatus by rememberSaveable { mutableStateOf(false) }

    val snapshot = state.snapshot
    val newest = remember(state.items) { state.items.mapNotNull { it.firstSeenInstant ?: it.publishedInstant }.maxOrNull() }
    val healthState = health(snapshot?.status, newest)
    val showScrollTop by remember { derivedStateOf { listState.firstVisibleItemIndex > 4 } }

    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            actions.consumeMessage()
        }
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            TopAppBar(
                title = { Text("AI Coding 资讯", fontWeight = FontWeight.SemiBold) },
                actions = {
                    HealthBadge(
                        healthState,
                        Modifier
                            .padding(end = 4.dp)
                            .clip(CircleShape)
                            .clickable { showStatus = true },
                    )
                    IconButton(onClick = { showStatus = true }) {
                        Icon(Icons.Rounded.Public, contentDescription = "数据源与更新策略")
                    }
                    IconButton(onClick = actions::toggleCompact) {
                        Icon(
                            if (state.compact) Icons.Rounded.ViewAgenda else Icons.Rounded.ViewHeadline,
                            contentDescription = if (state.compact) "卡片视图" else "紧凑视图",
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainer,
                ),
                scrollBehavior = scrollBehavior,
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            if (showScrollTop) {
                SmallFloatingActionButton(onClick = { scope.launch { listState.animateScrollToItem(0) } }) {
                    Icon(Icons.Rounded.KeyboardArrowUp, contentDescription = "回到顶部")
                }
            }
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing && !state.loading,
            onRefresh = actions::refresh,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (state.loading && snapshot == null) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                return@PullToRefreshBox
            }
            if (snapshot == null) {
                ErrorState(onRetry = actions::refresh)
                return@PullToRefreshBox
            }

            val absoluteScores = remember(state.items) { state.items.any { it.scores != null } }
            val maxScore = remember(state.items) { state.items.maxOfOrNull { it.effectiveScore } ?: 1.0 }
            val policy = snapshot.status?.policy

            LazyColumn(
                state = listState,
                contentPadding = PaddingValues(bottom = 32.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item(key = "header") {
                    val avg = if (state.items.isEmpty()) 0.0 else state.items.sumOf { it.effectiveScore } / state.items.size
                    val totals = snapshot.status?.totals
                    val updated = snapshot.status?.generatedInstant ?: newest
                    OverviewHeader(
                        kpis = listOf(
                            Kpi("精选", state.items.size.toString()),
                            Kpi("数据源", totals?.let { "${it.sourcesOk}/${it.sourcesTotal}" } ?: "–"),
                            Kpi("均分", String.format(Locale.ROOT, "%.1f", avg)),
                            Kpi("更新", updated?.let { relativeTime(it) } ?: "–"),
                        ),
                        policyNote = listOfNotNull(
                            policy?.schedule?.description?.takeIf { it.isNotBlank() },
                            policy?.windowDays?.takeIf { it > 0 }?.let { "展示最近 $it 天" },
                        ).joinToString(" · "),
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }

                stickyHeader(key = "filters") {
                    Surface(color = MaterialTheme.colorScheme.surface) {
                        Column {
                            FilterBar(
                                filter = state.filter,
                                categories = categoryCounts(state.items),
                                sources = sourceCounts(state.items),
                                total = state.items.size,
                                favoriteCount = state.favorites.size,
                                labels = state.labels,
                                onQuery = actions::setQuery,
                                onCategory = actions::setCategory,
                                onSource = actions::setSource,
                                onSort = actions::setSort,
                                onFavoritesOnly = actions::setFavoritesOnly,
                            )
                            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        }
                    }
                }

                if (state.filter.isActive) {
                    item(key = "result") {
                        Row16 {
                            Text(
                                "显示 ${state.visible.size} / ${state.items.size} 条",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.outline,
                                modifier = Modifier.weight(1f),
                            )
                            TextButton(onClick = actions::resetFilters) { Text("重置筛选") }
                        }
                    }
                }

                if (state.visible.isEmpty()) {
                    item(key = "empty") {
                        Text(
                            if (state.filter.favoritesOnly && state.favorites.isEmpty()) "还没有收藏任何条目，点条目右上角的星标即可收藏。" else "没有匹配的内容，试试调整关键词或筛选条件。",
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 32.dp, vertical = 48.dp),
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                itemsIndexed(state.visible, key = { _, item -> item.id }) { index, item ->
                    FeedItemCard(
                        item = item,
                        rank = index + 1,
                        highlightRank = state.filter.sort == SortOrder.SCORE && index < 3,
                        compact = state.compact,
                        favorite = item.id in state.favorites,
                        labels = state.labels,
                        absoluteScores = absoluteScores,
                        maxScore = maxScore,
                        onToggleFavorite = { actions.toggleFavorite(item.id) },
                        onKeyword = actions::setQuery,
                        modifier = Modifier
                            .padding(horizontal = 16.dp)
                            .animateItem(),
                    )
                }

                item(key = "footer") {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        if (snapshot.fromCache) {
                            Row16(padding = false) {
                                Icon(Icons.Rounded.CloudOff, contentDescription = null, tint = MaterialTheme.colorScheme.outline)
                                Text(" 离线缓存", color = MaterialTheme.colorScheme.outline, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                        Text(
                            "数据来自 ${snapshot.origin} · 本机获取于 ${relativeTime(snapshot.fetchedAt)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.outline,
                        )
                        TextButton(onClick = { openUrl(context, FeedRepository.SITE_URL) }) { Text("在网页中打开") }
                    }
                }
            }
        }
    }

    if (showStatus) {
        StatusSheet(snapshot = snapshot, run = state.workflowRun, onDismiss = { showStatus = false })
    }
}

@Composable
private fun Row16(padding: Boolean = true, content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit) {
    androidx.compose.foundation.layout.Row(
        modifier = if (padding) Modifier.padding(horizontal = 16.dp) else Modifier,
        verticalAlignment = Alignment.CenterVertically,
        content = content,
    )
}

@Composable
private fun ErrorState(onRetry: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize()) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 32.dp, vertical = 96.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(Icons.Rounded.CloudOff, contentDescription = null, tint = MaterialTheme.colorScheme.outline)
                Text(
                    "暂时无法从 GitHub 获取数据，请检查网络后重试。",
                    modifier = Modifier.padding(top = 12.dp),
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                TextButton(onClick = onRetry, modifier = Modifier.padding(top = 8.dp)) { Text("重试") }
            }
        }
    }
}
