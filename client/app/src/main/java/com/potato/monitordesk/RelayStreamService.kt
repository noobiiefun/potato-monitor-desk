package com.potato.monitordesk

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.potato.monitordesk.relay.RtmpRelayEngine

interface RelayStatusListener {
    fun onRelayConnected()
    fun onRelayFailed(reason: String)
    fun onRelayDisconnected()
}

/**
 * Foreground service tipe "dataSync" biasa -- BUKAN mediaProjection, karena
 * service ini tidak pernah capture layar. Yang dilakukan cuma menerima data
 * dari socket TCP (feed dari PC) lalu meneruskannya ke RTMP.
 */
class RelayStreamService : Service() {

    companion object {
        private const val CHANNEL_ID = "potato_relay_channel"
        private const val NOTIF_ID = 502
        private const val HOST = "127.0.0.1"
        private const val STREAM_PORT = 9999
    }

    private val binder = LocalBinder()
    private var engine: RtmpRelayEngine? = null
    var listener: RelayStatusListener? = null

    inner class LocalBinder : Binder() {
        fun getService(): RelayStreamService = this@RelayStreamService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    private fun startForegroundNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Potato Monitor Desk - Live ke YouTube", NotificationManager.IMPORTANCE_LOW
            )
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Potato Monitor Desk")
            .setContentText("Meneruskan tampilan PC ke YouTube Live...")
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    fun startRelay(rtmpUrl: String) {
        startForegroundNotification()
        val eng = RtmpRelayEngine(HOST, STREAM_PORT, object : RtmpRelayEngine.Listener {
            override fun onRelayConnected() = listener?.onRelayConnected() ?: Unit
            override fun onRelayFailed(reason: String) {
                stopForeground(true)
                listener?.onRelayFailed(reason)
            }
            override fun onRelayDisconnected() {
                stopForeground(true)
                listener?.onRelayDisconnected()
            }
        })
        engine = eng
        eng.start(rtmpUrl)
    }

    fun stopRelay() {
        engine?.stop()
        engine = null
        stopForeground(true)
        stopSelf()
    }

    override fun onDestroy() {
        engine?.stop()
        super.onDestroy()
    }
}
