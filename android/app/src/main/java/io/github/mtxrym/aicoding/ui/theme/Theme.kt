package io.github.mtxrym.aicoding.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

val BrandIndigo = Color(0xFF4F46E5)
val BrandCyan = Color(0xFF0891B2)

private val LightColors = lightColorScheme(
    primary = BrandIndigo,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFE0E7FF),
    onPrimaryContainer = Color(0xFF312E81),
    secondary = BrandCyan,
    secondaryContainer = Color(0xFFCFFAFE),
    onSecondaryContainer = Color(0xFF164E63),
    background = Color(0xFFF7F8FA),
    surface = Color(0xFFF7F8FA),
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color.White,
    surfaceContainer = Color(0xFFF2F4F7),
    surfaceContainerHigh = Color(0xFFEAECF0),
    onSurface = Color(0xFF101828),
    onSurfaceVariant = Color(0xFF475467),
    outline = Color(0xFFD0D5DD),
    outlineVariant = Color(0xFFE4E7EC),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8B93FF),
    onPrimary = Color(0xFF0C0E13),
    primaryContainer = Color(0xFF272C4F),
    onPrimaryContainer = Color(0xFFC9CCFF),
    secondary = Color(0xFF5CCFE6),
    secondaryContainer = Color(0xFF123A44),
    onSecondaryContainer = Color(0xFFBDEFF8),
    background = Color(0xFF0C0E13),
    surface = Color(0xFF0C0E13),
    surfaceContainerLowest = Color(0xFF101319),
    surfaceContainerLow = Color(0xFF13161D),
    surfaceContainer = Color(0xFF1A1E27),
    surfaceContainerHigh = Color(0xFF242935),
    onSurface = Color(0xFFE7E9EE),
    onSurfaceVariant = Color(0xFFA4ACBD),
    outline = Color(0xFF343B4B),
    outlineVariant = Color(0xFF242935),
)

/** 状态色：不随动态取色变化，保证“正常 / 异常”语义稳定。 */
@Immutable
data class StatusColors(
    val ok: Color,
    val okContainer: Color,
    val warn: Color,
    val warnContainer: Color,
    val error: Color,
    val errorContainer: Color,
    val star: Color,
    val new: Color,
    val newContainer: Color,
)

private val LightStatus = StatusColors(
    ok = Color(0xFF067647), okContainer = Color(0xFFECFDF3),
    warn = Color(0xFFB54708), warnContainer = Color(0xFFFFFAEB),
    error = Color(0xFFB42318), errorContainer = Color(0xFFFEF3F2),
    star = Color(0xFFF79009),
    new = Color(0xFFC11574), newContainer = Color(0xFFFDF2FA),
)

private val DarkStatus = StatusColors(
    ok = Color(0xFF47CD89), okContainer = Color(0x1F47CD89),
    warn = Color(0xFFFDB022), warnContainer = Color(0x1FFDB022),
    error = Color(0xFFF97066), errorContainer = Color(0x1FF97066),
    star = Color(0xFFFDB022),
    new = Color(0xFFF670C7), newContainer = Color(0x1FF670C7),
)

val LocalStatusColors = staticCompositionLocalOf { LightStatus }

@Composable
fun AICodingTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colors: ColorScheme = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalStatusColors provides if (darkTheme) DarkStatus else LightStatus) {
        MaterialTheme(colorScheme = colors, content = content)
    }
}
