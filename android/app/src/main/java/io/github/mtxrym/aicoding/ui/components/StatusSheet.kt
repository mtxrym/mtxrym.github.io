package io.github.mtxrym.aicoding.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import io.github.mtxrym.aicoding.data.FeedRepository
import io.github.mtxrym.aicoding.data.FeedSnapshot
import io.github.mtxrym.aicoding.data.WorkflowRun
import io.github.mtxrym.aicoding.domain.categoryLabel
import io.github.mtxrym.aicoding.domain.relativeTime
import io.github.mtxrym.aicoding.ui.theme.LocalStatusColors

private val WEIGHT_LABELS = listOf("relevance" to "相关性", "popularity" to "热度", "freshness" to "新鲜度", "impact" to "影响力")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatusSheet(snapshot: FeedSnapshot?, run: WorkflowRun?, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        StatusContent(snapshot, run)
    }
}

/** 数据源、更新策略与 GitHub Actions 运行状态。 */
@Composable
fun StatusContent(snapshot: FeedSnapshot?, run: WorkflowRun?) {
    val context = LocalContext.current
    val status = snapshot?.status
    val colors = LocalStatusColors.current
    Box {
        Column(
            Modifier
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .navigationBarsPadding(),
        ) {
            Text("数据源与更新策略", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)

            SectionTitle("GitHub 自动更新")
            if (run != null) {
                val (label, color) = when {
                    run.status != "completed" -> "运行中" to colors.warn
                    run.conclusion == "success" -> "成功" to colors.ok
                    else -> "失败（${run.conclusion ?: "未知"}）" to colors.error
                }
                InfoRow("最近运行") {
                    Dot(color)
                    Text(label + (run.updatedAt?.let { " · ${relativeTime(it)}" } ?: ""), color = color, fontWeight = FontWeight.Medium)
                }
                TextButton(onClick = { openUrl(context, run.htmlUrl) }, modifier = Modifier.padding(start = 0.dp)) { Text("在 GitHub Actions 中查看") }
            } else {
                Text("暂时无法读取 GitHub Actions 状态（可能触发了匿名访问频率限制）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
            }
            snapshot?.let {
                InfoRow("数据地址") { Text(it.origin + if (it.fromCache) "（离线缓存）" else "") }
                InfoRow("本机获取") { Text(relativeTime(it.fetchedAt)) }
            }

            if (status != null) {
                val policy = status.policy
                SectionTitle("更新策略")
                InfoRow("识别方式") {
                    val llm = status.llm
                    Text(
                        if (llm.enabled) {
                            "${llm.displayName} 复核（${llm.coverage} 条）" + if (!llm.healthy) " · 本次部分调用失败" else ""
                        } else {
                            "关键词规则" + (llm.reason?.let { "（$it）" } ?: "")
                        },
                    )
                }
                InfoRow("抓取频率") { Text(policy.schedule.description.ifBlank { policy.schedule.cron }) }
                InfoRow("展示窗口") { Text("最近 ${policy.windowDays} 天首次收录") }
                InfoRow("展示上限") { Text("${policy.maxItems} 条（数据集最多 ${policy.maxDatasets} 条）") }
                InfoRow("相关性门槛") {
                    Text(if (status.llm.enabled) "模型打分 ≥ ${policy.llm.minScore.toInt()} / 100" else "≥ ${policy.minRelevance.toInt()} / 100")
                }
                InfoRow("滞后判定") { Text("${policy.staleAfterHours} 小时无新条目") }
                InfoRow("打分权重") {
                    Text(WEIGHT_LABELS.joinToString(" · ") { (key, label) -> "$label ${((policy.weights[key] ?: 0.0) * 100).toInt()}%" })
                }

                SectionTitle("数据源（${status.totals.sourcesOk}/${status.totals.sourcesTotal} 正常）")
                Row(Modifier.padding(vertical = 4.dp)) {
                    Text("来源", Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline)
                    Text("抓取", Modifier.width(56.dp), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline, textAlign = TextAlign.End)
                    Text("相关", Modifier.width(48.dp), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.outline, textAlign = TextAlign.End)
                }
                status.sources.forEach { source ->
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Dot(if (source.ok) colors.ok else colors.error)
                        Column(
                            Modifier
                                .weight(1f)
                                .padding(start = 8.dp),
                        ) {
                            Text(source.label.ifBlank { source.id }, fontWeight = FontWeight.Medium)
                            Text(
                                if (source.ok) categoryLabel(source.category) else "失败：${source.error ?: "未知错误"}",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (source.ok) MaterialTheme.colorScheme.outline else colors.error,
                            )
                        }
                        Text(if (source.ok) "${source.fetched}" else "–", Modifier.width(56.dp), textAlign = TextAlign.End)
                        Text(if (source.ok) "${source.relevant}" else "–", Modifier.width(48.dp), textAlign = TextAlign.End)
                    }
                }
                Text(
                    "策略在仓库 config/update_policy.yaml 中维护",
                    modifier = Modifier.padding(top = 12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.outline,
                )
            }
            TextButton(onClick = { openUrl(context, FeedRepository.REPO_URL) }) { Text("打开 GitHub 仓库") }
            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        modifier = Modifier.padding(top = 20.dp, bottom = 6.dp),
        style = MaterialTheme.typography.titleSmall,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.primary,
    )
}

@Composable
private fun InfoRow(label: String, content: @Composable () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(label, Modifier.width(76.dp), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.material3.ProvideTextStyle(MaterialTheme.typography.bodyMedium) { content() }
        }
    }
}

@Composable
private fun Dot(color: androidx.compose.ui.graphics.Color) {
    Box(
        Modifier
            .padding(end = 6.dp)
            .size(8.dp)
            .clip(CircleShape)
            .background(color),
    )
}
