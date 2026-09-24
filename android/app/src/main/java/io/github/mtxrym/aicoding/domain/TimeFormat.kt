package io.github.mtxrym.aicoding.domain

import io.github.mtxrym.aicoding.data.FeedStatus
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.Locale

/** 精确到小时的相对时间，用于“最近更新”。 */
fun relativeTime(instant: Instant, now: Instant = Instant.now()): String {
    val minutes = Duration.between(instant, now).toMinutes()
    return when {
        minutes < 60 -> "刚刚"
        minutes < 24 * 60 -> "${minutes / 60} 小时前"
        else -> relativeDay(instant, now)
    }
}

/** 论文日期只精确到天：今天 / 昨天 / 前天 / N 天前 / M月D日。 */
fun relativeDay(instant: Instant, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()): String {
    val date = instant.atZone(zone).toLocalDate()
    val today = now.atZone(zone).toLocalDate()
    val days = ChronoUnit.DAYS.between(date, today)
    return when {
        days <= 0 -> "今天"
        days == 1L -> "昨天"
        days == 2L -> "前天"
        days < 30 -> "$days 天前"
        date.year == today.year -> "${date.monthValue}月${date.dayOfMonth}日"
        else -> "${date.year}年${date.monthValue}月${date.dayOfMonth}日"
    }
}

fun isNew(firstSeen: Instant?, now: Instant = Instant.now(), hours: Long = 24): Boolean =
    firstSeen != null && Duration.between(firstSeen, now).toHours() < hours

fun compactNumber(value: Int): String = when {
    value >= 10_000 -> String.format(Locale.ROOT, "%.1f万", value / 10_000.0).replace(".0万", "万")
    value >= 1_000 -> String.format(Locale.ROOT, "%.1fk", value / 1_000.0).replace(".0k", "k")
    else -> value.toString()
}

enum class Health { OK, PARTIAL, STALE, ERROR, UNKNOWN }

fun health(status: FeedStatus?, newest: Instant?, now: Instant = Instant.now()): Health {
    val staleHours = status?.policy?.staleAfterHours?.takeIf { it > 0 } ?: 96
    val totals = status?.totals
    return when {
        totals != null && totals.sourcesTotal > 0 && totals.sourcesOk == 0 -> Health.ERROR
        newest == null -> Health.UNKNOWN
        Duration.between(newest, now).toHours() > staleHours -> Health.STALE
        totals != null && totals.sourcesOk < totals.sourcesTotal -> Health.PARTIAL
        else -> Health.OK
    }
}
