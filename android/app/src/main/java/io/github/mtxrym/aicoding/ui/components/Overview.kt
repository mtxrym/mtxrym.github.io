package io.github.mtxrym.aicoding.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.automirrored.rounded.Sort
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.Badge
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.mtxrym.aicoding.domain.FeedFilter
import io.github.mtxrym.aicoding.domain.SortOrder
import io.github.mtxrym.aicoding.domain.categoryLabel
import io.github.mtxrym.aicoding.ui.theme.LocalStatusColors

data class Kpi(val label: String, val value: String)

@Composable
fun OverviewHeader(kpis: List<Kpi>, policyNote: String, modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val secondary = MaterialTheme.colorScheme.secondary
    Column(modifier.padding(horizontal = 16.dp)) {
        Text(
            text = buildAnnotatedString {
                append("AI 编程前沿，")
                withStyle(SpanStyle(brush = Brush.linearGradient(listOf(primary, secondary)))) { append("每日精选") }
            },
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "arXiv 与 Hugging Face 上和 AI 编程相关的论文、数据集，按相关性、热度、新鲜度与影响力综合打分。",
            modifier = Modifier.padding(top = 6.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedCard(
            modifier = Modifier
                .padding(top = 16.dp)
                .fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        ) {
            Row(Modifier.height(IntrinsicSize.Min)) {
                kpis.forEachIndexed { index, kpi ->
                    if (index > 0) VerticalDivider(Modifier.fillMaxHeight(), color = MaterialTheme.colorScheme.outlineVariant)
                    Column(
                        Modifier
                            .weight(1f)
                            .padding(horizontal = 12.dp, vertical = 12.dp),
                    ) {
                        Text(kpi.label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1)
                        Text(kpi.value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold, maxLines = 1)
                    }
                }
            }
        }
        if (policyNote.isNotBlank()) {
            Text(
                policyNote,
                modifier = Modifier.padding(top = 8.dp, start = 2.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

@Composable
private fun chipColors() = FilterChipDefaults.filterChipColors(
    selectedContainerColor = MaterialTheme.colorScheme.primaryContainer,
    selectedLabelColor = MaterialTheme.colorScheme.onPrimaryContainer,
    selectedLeadingIconColor = MaterialTheme.colorScheme.onPrimaryContainer,
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FilterBar(
    filter: FeedFilter,
    categories: List<Pair<String, Int>>,
    sources: List<Pair<String, Int>>,
    total: Int,
    favoriteCount: Int,
    labels: Map<String, String>,
    onQuery: (String) -> Unit,
    onCategory: (String?) -> Unit,
    onSource: (String?) -> Unit,
    onSort: (SortOrder) -> Unit,
    onFavoritesOnly: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    val focus = LocalFocusManager.current
    Column(modifier.padding(vertical = 8.dp)) {
        OutlinedTextField(
            value = filter.query,
            onValueChange = onQuery,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            placeholder = { Text("搜索标题、摘要、作者或主题") },
            leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
            trailingIcon = {
                if (filter.query.isNotEmpty()) {
                    IconButton(onClick = { onQuery("") }) { Icon(Icons.Rounded.Close, contentDescription = "清空") }
                }
            },
            singleLine = true,
            shape = RoundedCornerShape(12.dp),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = { focus.clearFocus() }),
            colors = OutlinedTextFieldDefaults.colors(
                unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
                focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
                unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
            ),
        )

        Row(
            Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilterChip(selected = filter.category == null, onClick = { onCategory(null) }, label = { Text("全部 $total") }, colors = chipColors())
            categories.forEach { (category, count) ->
                FilterChip(
                    selected = filter.category == category,
                    onClick = { onCategory(if (filter.category == category) null else category) },
                    label = { Text("${categoryLabel(category)} $count") },
                    colors = chipColors(),
                )
            }
            VerticalDivider(Modifier.height(20.dp))
            FilterChip(
                selected = filter.favoritesOnly,
                onClick = { onFavoritesOnly(!filter.favoritesOnly) },
                label = { Text("收藏 $favoriteCount") },
                colors = chipColors(),
                leadingIcon = {
                    Icon(
                        Icons.Rounded.Star,
                        contentDescription = null,
                        modifier = Modifier.size(FilterChipDefaults.IconSize),
                        tint = if (filter.favoritesOnly) LocalStatusColors.current.star else MaterialTheme.colorScheme.outline,
                    )
                },
            )
            SortMenu(filter.sort, onSort)
        }

        Row(
            Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SourceChip("全部来源", total, filter.source == null) { onSource(null) }
            sources.forEach { (source, count) ->
                SourceChip(labels[source] ?: source, count, filter.source == source) {
                    onSource(if (filter.source == source) null else source)
                }
            }
        }
    }
}

@Composable
private fun SourceChip(label: String, count: Int, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = {
            Text(label, fontSize = 12.5.sp)
            Badge(
                modifier = Modifier.padding(start = 6.dp),
                containerColor = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
                contentColor = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
            ) { Text(count.toString()) }
        },
        shape = RoundedCornerShape(50),
        colors = chipColors(),
    )
}

@Composable
private fun SortMenu(sort: SortOrder, onSort: (SortOrder) -> Unit) {
    var open by remember { mutableStateOf(false) }
    FilterChip(
        selected = false,
        onClick = { open = true },
        label = { Text(sort.label) },
        leadingIcon = { Icon(Icons.AutoMirrored.Rounded.Sort, contentDescription = null, modifier = Modifier.size(FilterChipDefaults.IconSize)) },
    )
    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
        SortOrder.entries.forEach { option ->
            DropdownMenuItem(
                text = { Text(option.label) },
                onClick = {
                    onSort(option)
                    open = false
                },
                trailingIcon = { if (option == sort) Icon(Icons.Rounded.Check, contentDescription = null) else Unit },
                modifier = Modifier.width(140.dp),
            )
        }
    }
}
