package com.potato.monitordesk

import android.content.Context

enum class BadgePosition { TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT }

/**
 * Menyimpan pengaturan live streaming: alamat RTMP tujuan, posisi badge
 * timer LIVE di layar, dan sumber audio (internal PC audio vs mikrofon HP).
 */
object LivePrefs {
    private const val PREFS = "potato_live_prefs"
    private const val KEY_RTMP_URL = "rtmp_url"
    private const val KEY_BADGE_POS = "badge_position"
    private const val KEY_USE_INTERNAL_AUDIO = "use_internal_audio"

    fun getRtmpUrl(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_RTMP_URL, "") ?: ""

    fun setRtmpUrl(context: Context, url: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_RTMP_URL, url).apply()
    }

    fun getBadgePosition(context: Context): BadgePosition {
        val name = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_BADGE_POS, BadgePosition.TOP_RIGHT.name) ?: BadgePosition.TOP_RIGHT.name
        return try {
            BadgePosition.valueOf(name)
        } catch (_: Exception) {
            BadgePosition.TOP_RIGHT
        }
    }

    fun setBadgePosition(context: Context, position: BadgePosition) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_BADGE_POS, position.name).apply()
    }

    /** true = ambil audio dari PC (internal/system audio, butuh Android 10+),
     *  false = ambil dari mikrofon HP (fallback untuk Android lama). */
    fun useInternalAudio(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_USE_INTERNAL_AUDIO, true)

    fun setUseInternalAudio(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_USE_INTERNAL_AUDIO, value).apply()
    }
}
