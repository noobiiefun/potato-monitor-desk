package com.potato.monitordesk

import android.content.Context

/**
 * Menyimpan daftar package name aplikasi yang notifnya mau disunyikan
 * saat Potato Monitor Desk sedang dipakai. App yang TIDAK dicentang
 * (misal app live-streaming kamu sendiri) tetap tampil normal.
 */
object NotificationPrefs {
    private const val PREFS_NAME = "potato_notif_prefs"
    private const val KEY_BLOCKED = "blocked_packages"
    private const val KEY_FILTER_ENABLED = "filter_enabled"

    fun getBlockedPackages(context: Context): Set<String> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getStringSet(KEY_BLOCKED, emptySet()) ?: emptySet()
    }

    fun setBlockedPackages(context: Context, packages: Set<String>) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putStringSet(KEY_BLOCKED, packages)
            .apply()
    }

    fun isFilterEnabled(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getBoolean(KEY_FILTER_ENABLED, true)
    }

    fun setFilterEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_FILTER_ENABLED, enabled)
            .apply()
    }
}
