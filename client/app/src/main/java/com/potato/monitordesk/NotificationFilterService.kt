package com.potato.monitordesk

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Membaca notifikasi masuk dan membatalkan (menyunyikan) hanya notifikasi
 * dari aplikasi yang ada di daftar blokir user (mis. WhatsApp, Telegram).
 * App lain (termasuk app live-streaming) tidak disentuh sama sekali.
 *
 * Butuh izin manual dari user: Settings > Apps > Special app access >
 * Notification access > aktifkan untuk Potato Monitor Desk.
 */
class NotificationFilterService : NotificationListenerService() {

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (!NotificationPrefs.isFilterEnabled(applicationContext)) return
        val blocked = NotificationPrefs.getBlockedPackages(applicationContext)
        if (sbn.packageName in blocked) {
            cancelNotification(sbn.key)
        }
    }
}
