package io.github.mtxrym.aicoding.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "user_prefs")

/** 收藏与视图偏好，保存在本机 DataStore。 */
class UserPreferences(private val context: Context) {

    val favorites: Flow<Set<String>> = context.dataStore.data.map { it[FAVORITES] ?: emptySet() }

    val compactView: Flow<Boolean> = context.dataStore.data.map { it[COMPACT] ?: false }

    suspend fun toggleFavorite(id: String) {
        context.dataStore.edit { prefs ->
            val current = prefs[FAVORITES] ?: emptySet()
            prefs[FAVORITES] = if (id in current) current - id else current + id
        }
    }

    suspend fun setCompactView(enabled: Boolean) {
        context.dataStore.edit { it[COMPACT] = enabled }
    }

    private companion object {
        val FAVORITES = stringSetPreferencesKey("favorites")
        val COMPACT = booleanPreferencesKey("compact_view")
    }
}
