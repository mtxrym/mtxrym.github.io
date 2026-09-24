package io.github.mtxrym.aicoding.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.IOException
import java.time.Instant
import java.util.concurrent.TimeUnit

/** 一次加载的结果：条目 + 状态 + 来自哪个镜像 / 是否为离线缓存。 */
data class FeedSnapshot(
    val items: List<FeedItem>,
    val status: FeedStatus?,
    val fetchedAt: Instant,
    val origin: String,
    val fromCache: Boolean,
)

/**
 * 从 GitHub 读取数据。依次尝试：
 * 1. GitHub Pages（与网页同源，部署后即最新）
 * 2. raw.githubusercontent.com（直接读仓库 master 分支，Pages 部署延迟时也能拿到）
 * 3. jsDelivr CDN（国内网络下通常更稳定）
 */
class FeedRepository(
    private val context: Context,
    private val client: OkHttpClient = defaultClient(),
    private val json: Json = defaultJson,
) {
    private val cacheFile: File get() = File(context.filesDir, CACHE_FILE)

    suspend fun loadCached(): FeedSnapshot? = withContext(Dispatchers.IO) {
        runCatching {
            val cached = json.decodeFromString(CachedFeed.serializer(), cacheFile.readText())
            FeedSnapshot(
                items = parseItems(cached.blog),
                status = cached.status?.let(::parseStatus),
                fetchedAt = Instant.ofEpochMilli(cached.fetchedAtMillis),
                origin = cached.origin,
                fromCache = true,
            )
        }.getOrNull()
    }

    suspend fun fetch(): FeedSnapshot = withContext(Dispatchers.IO) {
        var lastError: Exception? = null
        for (mirror in MIRRORS) {
            try {
                return@withContext fetchFrom(mirror)
            } catch (e: Exception) {
                lastError = e
            }
        }
        throw IOException("所有数据地址都无法访问：${lastError?.message}", lastError)
    }

    private suspend fun fetchFrom(mirror: Mirror): FeedSnapshot = coroutineScope {
        val blogDeferred = async { get(mirror.base + "blog.json") }
        val statusDeferred = async { runCatching { get(mirror.base + "data/status.json") }.getOrNull() }
        val blog = blogDeferred.await()
        val items = parseItems(blog) // 格式不对时抛异常，换下一个镜像
        val statusText = statusDeferred.await()
        val now = Instant.now()
        runCatching {
            cacheFile.writeText(
                json.encodeToString(CachedFeed.serializer(), CachedFeed(blog, statusText, now.toEpochMilli(), mirror.name)),
            )
        }
        FeedSnapshot(items, statusText?.let(::parseStatus), now, mirror.name, fromCache = false)
    }

    /** 最近一次定时更新任务的运行情况（GitHub API 匿名访问，每小时 60 次，失败时返回 null）。 */
    suspend fun latestWorkflowRun(): WorkflowRun? = withContext(Dispatchers.IO) {
        runCatching {
            val body = get(WORKFLOW_RUNS_URL, accept = "application/vnd.github+json")
            val run = json.parseToJsonElement(body).jsonObject["workflow_runs"]!!.jsonArray.first().jsonObject
            WorkflowRun(
                status = run["status"]!!.jsonPrimitive.content,
                conclusion = run["conclusion"]?.jsonPrimitive?.contentOrNull,
                updatedAt = parseInstant(run["updated_at"]?.jsonPrimitive?.content),
                htmlUrl = run["html_url"]!!.jsonPrimitive.content,
            )
        }.getOrNull()
    }

    fun parseItems(text: String): List<FeedItem> = json.decodeFromString<List<FeedItem>>(text)

    fun parseStatus(text: String): FeedStatus? = runCatching { json.decodeFromString<FeedStatus>(text) }.getOrNull()

    private fun get(url: String, accept: String = "application/json"): String {
        val request = Request.Builder()
            .url(url)
            .header("Accept", accept)
            .header("Cache-Control", "no-cache")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code} $url")
            return response.body?.string() ?: throw IOException("空响应 $url")
        }
    }

    @Serializable
    private data class CachedFeed(
        val blog: String,
        val status: String?,
        val fetchedAtMillis: Long,
        val origin: String,
    )

    private data class Mirror(val name: String, val base: String)

    companion object {
        private const val CACHE_FILE = "feed_cache.json"
        private const val REPO = "mtxrym/mtxrym.github.io"
        const val SITE_URL = "https://mtxrym.github.io/"
        const val REPO_URL = "https://github.com/$REPO"
        private const val WORKFLOW_RUNS_URL =
            "https://api.github.com/repos/$REPO/actions/workflows/update-content.yml/runs?per_page=1"

        private val MIRRORS = listOf(
            Mirror("GitHub Pages", SITE_URL),
            Mirror("GitHub Raw", "https://raw.githubusercontent.com/$REPO/master/"),
            Mirror("jsDelivr", "https://cdn.jsdelivr.net/gh/$REPO@master/"),
        )

        val defaultJson = Json {
            ignoreUnknownKeys = true
            coerceInputValues = true
            explicitNulls = false
        }

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .callTimeout(20, TimeUnit.SECONDS)
            .build()
    }
}
