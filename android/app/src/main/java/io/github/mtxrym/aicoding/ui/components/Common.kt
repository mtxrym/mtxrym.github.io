package io.github.mtxrym.aicoding.ui.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import io.github.mtxrym.aicoding.domain.Health
import io.github.mtxrym.aicoding.ui.theme.LocalStatusColors

/** 优先用 Custom Tabs 在应用内打开链接，失败时交给系统浏览器。 */
fun openUrl(context: Context, url: String) {
    val uri = url.toUri()
    try {
        CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, uri)
    } catch (_: ActivityNotFoundException) {
        runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }
}

/** 小号标签：来源、NEW 等。 */
@Composable
fun Pill(
    text: String,
    modifier: Modifier = Modifier,
    container: Color = MaterialTheme.colorScheme.surfaceContainer,
    content: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    monospace: Boolean = false,
) {
    Surface(color = container, contentColor = content, shape = RoundedCornerShape(6.dp), modifier = modifier) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp),
            fontSize = if (monospace) 10.5.sp else 12.sp,
            fontWeight = if (monospace) FontWeight.Bold else FontWeight.Medium,
            fontFamily = if (monospace) FontFamily.Monospace else null,
            maxLines = 1,
        )
    }
}

/** 单色进度条：填充与轨道同一色系，表示 0–100 的得分。 */
@Composable
fun ScoreBar(fraction: Float, modifier: Modifier = Modifier, height: Dp = 4.dp, color: Color = MaterialTheme.colorScheme.primary) {
    Box(
        modifier
            .height(height)
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.primaryContainer),
    ) {
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(fraction.coerceIn(0.04f, 1f))
                .clip(CircleShape)
                .background(color),
        )
    }
}

data class HealthStyle(val label: String, val color: Color, val container: Color)

@Composable
fun healthStyle(health: Health): HealthStyle {
    val c = LocalStatusColors.current
    return when (health) {
        Health.OK -> HealthStyle("数据正常", c.ok, c.okContainer)
        Health.PARTIAL -> HealthStyle("部分异常", c.warn, c.warnContainer)
        Health.STALE -> HealthStyle("更新滞后", c.warn, c.warnContainer)
        Health.ERROR -> HealthStyle("抓取失败", c.error, c.errorContainer)
        Health.UNKNOWN -> HealthStyle("加载中", MaterialTheme.colorScheme.onSurfaceVariant, MaterialTheme.colorScheme.surfaceContainer)
    }
}

@Composable
fun HealthBadge(health: Health, modifier: Modifier = Modifier) {
    val style = healthStyle(health)
    Surface(color = style.container, contentColor = style.color, shape = CircleShape, modifier = modifier) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(style.color))
            Text(style.label, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}
