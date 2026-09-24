package io.github.mtxrym.aicoding.ui.components

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Code
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarOutline
import androidx.compose.material.icons.rounded.ThumbUp
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.mtxrym.aicoding.data.FeedItem
import io.github.mtxrym.aicoding.domain.categoryLabel
import io.github.mtxrym.aicoding.domain.compactNumber
import io.github.mtxrym.aicoding.domain.isNew
import io.github.mtxrym.aicoding.domain.relativeDay
import io.github.mtxrym.aicoding.ui.theme.LocalStatusColors
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FeedItemCard(
    item: FeedItem,
    rank: Int,
    highlightRank: Boolean,
    compact: Boolean,
    favorite: Boolean,
    labels: Map<String, String>,
    absoluteScores: Boolean,
    maxScore: Double,
    onToggleFavorite: () -> Unit,
    onKeyword: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val status = LocalStatusColors.current
    val fraction = (if (absoluteScores) item.effectiveScore / 100.0 else item.effectiveScore / maxScore.coerceAtLeast(1.0)).toFloat()

    Card(
        onClick = { openUrl(context, item.link) },
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(if (compact) 10.dp else 16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        if (compact) {
            Row(
                Modifier.padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RankText(rank, highlightRank)
                Spacer(Modifier.width(10.dp))
                Text(
                    item.title,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    String.format(Locale.ROOT, "%.1f", item.effectiveScore),
                    modifier = Modifier.padding(start = 8.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                FavoriteButton(favorite, onToggleFavorite)
            }
            return@Card
        }

        Column(Modifier.padding(start = 16.dp, end = 8.dp, top = 14.dp, bottom = 10.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                RankText(rank, highlightRank, Modifier.padding(top = 2.dp))
                Spacer(Modifier.width(10.dp))
                Text(
                    text = titleText(item),
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    lineHeight = 22.sp,
                )
                FavoriteButton(favorite, onToggleFavorite, Modifier.padding(start = 2.dp))
            }

            Column(Modifier.padding(start = 30.dp, end = 8.dp)) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                    itemVerticalAlignment = Alignment.CenterVertically,
                ) {
                    if (isNew(item.firstSeenInstant)) {
                        Pill("NEW", container = status.newContainer, content = status.new, monospace = true)
                    }
                    item.effectiveSources.forEach { Pill(labels[it] ?: it) }
                    val date = item.publishedInstant ?: item.firstSeenInstant
                    Text(
                        text = listOfNotNull(authorsText(item) ?: categoryLabel(item.effectiveCategory), date?.let { relativeDay(it) })
                            .joinToString(" · "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }

                if (item.summary.isNotBlank()) {
                    Summary(item.summary)
                }

                if (item.keywords.isNotEmpty()) {
                    FlowRow(
                        modifier = Modifier.padding(top = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        item.keywords.forEach { keyword ->
                            Surface(
                                onClick = { onKeyword(keyword) },
                                shape = CircleShape,
                                color = MaterialTheme.colorScheme.primaryContainer,
                                contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
                            ) {
                                Text("#$keyword", Modifier.padding(horizontal = 9.dp, vertical = 3.dp), fontSize = 12.sp, fontWeight = FontWeight.Medium)
                            }
                        }
                    }
                }

                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 10.dp, bottom = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        ScoreBar(fraction, Modifier.width(64.dp))
                        Text(
                            String.format(Locale.ROOT, "%.1f", item.effectiveScore),
                            modifier = Modifier.padding(start = 8.dp),
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Spacer(Modifier.weight(1f))
                    if (item.upvotes > 0) {
                        MetaLink(Icons.Rounded.ThumbUp, compactNumber(item.upvotes), item.hfUrl.ifBlank { null })
                    }
                    if (item.likes > 0) {
                        MetaLink(Icons.Rounded.Favorite, compactNumber(item.likes), null)
                    }
                    if (item.githubUrl.isNotBlank()) {
                        val label = if (item.githubStars > 0) "代码 ★${compactNumber(item.githubStars)}" else "代码"
                        MetaLink(Icons.Rounded.Code, label, item.githubUrl)
                    }
                }
            }
        }
    }
}

@Composable
private fun RankText(rank: Int, highlight: Boolean, modifier: Modifier = Modifier) {
    Text(
        text = rank.toString().padStart(2, '0'),
        modifier = modifier.width(20.dp),
        fontFamily = FontFamily.Monospace,
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        color = if (highlight) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
    )
}

@Composable
private fun FavoriteButton(favorite: Boolean, onToggle: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(onClick = onToggle, modifier = modifier.size(40.dp)) {
        Icon(
            imageVector = if (favorite) Icons.Rounded.Star else Icons.Rounded.StarOutline,
            contentDescription = if (favorite) "取消收藏" else "收藏",
            tint = if (favorite) LocalStatusColors.current.star else MaterialTheme.colorScheme.outline,
        )
    }
}

@Composable
private fun Summary(text: String) {
    var expanded by rememberSaveable(text) { mutableStateOf(false) }
    Column(
        Modifier
            .padding(top = 8.dp)
            .animateContentSize(),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = if (expanded) Int.MAX_VALUE else 3,
            overflow = TextOverflow.Ellipsis,
            lineHeight = 21.sp,
        )
        if (text.length > 120) {
            Row(
                Modifier
                    .padding(top = 2.dp)
                    .clickable { expanded = !expanded },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    if (expanded) "收起" else "展开摘要",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.outline,
                )
                Icon(
                    if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = MaterialTheme.colorScheme.outline,
                )
            }
        }
    }
}

@Composable
private fun MetaLink(icon: ImageVector, label: String, url: String?) {
    val context = LocalContext.current
    val base = Modifier.let { if (url != null) it.clickable { openUrl(context, url) } else it }
    Row(base.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(14.dp), tint = MaterialTheme.colorScheme.outline)
        Text(
            label,
            modifier = Modifier.padding(start = 4.dp),
            style = MaterialTheme.typography.labelMedium,
            color = if (url != null) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun titleText(item: FeedItem) = buildAnnotatedString {
    // 数据集 id：owner 弱化显示
    if (item.effectiveCategory == "datasets" && '/' in item.title) {
        withStyle(SpanStyle(color = MaterialTheme.colorScheme.outline, fontWeight = FontWeight.Normal)) {
            append(item.title.substringBefore('/') + "/")
        }
        append(item.title.substringAfter('/'))
    } else {
        append(item.title)
    }
}

private fun authorsText(item: FeedItem): String? {
    if (item.authors.isEmpty()) return null
    val shown = item.authors.take(2).joinToString(", ")
    val total = maxOf(item.authorCount, item.authors.size)
    return if (total > 2) "$shown 等 $total 人" else shown
}
