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
import com.pedro.rtplibrary.rtmp.RtmpDisplay
import com.pedro.rtplibrary.util.ConnectCheckerRtmp

/**
 * Callback status live streaming ke MainActivity.
 */
interface LiveStatusListener {
    fun onLiveConnected()
    fun onLiveFailed(reason: String)
    fun onLiveDisconnected()
}

/**
 * Foreground service (wajib bertipe mediaProjection sesuai kebijakan Android
 * 10+/14+) yang memegang instance RtmpDisplay dari library RootEncoder untuk
 * meng-capture layar HP ini (yaitu mirror PC yang sedang ditampilkan) beserta
 * audionya, lalu push ke server RTMP (YouTube Live, Facebook Live, RTMP
 * server lain).
 *
 * CATATAN VERSI LIBRARY: kode ini mengikuti API RootEncoder yang umum
 * didokumentasikan (RtmpDisplay, ConnectCheckerRtmp, prepareVideo/prepareAudio/
 * prepareInternalAudio, startStream/stopStream). Kalau versi library yang
 * ter-download sedikit beda (mis. package com.pedro.library.* alih-alih
 * com.pedro.rtplibrary.*, atau interface ConnectChecker yang unified),
 * Android Studio akan menunjukkan error import -- cek contoh resmi di
 * https://github.com/pedroSG94/RootEncoder/tree/master/app/src/main/java/com/pedro/streamer/displayexample
 * untuk menyesuaikan nama class/paket persis versi kamu.
 */
class LiveStreamService : Service(), ConnectCheckerRtmp {

    companion object {
        private const val CHANNEL_ID = "potato_live_channel"
        private const val NOTIF_ID = 501
    }

    private val binder = LocalBinder()
    private var rtmpDisplay: RtmpDisplay? = null
    var listener: LiveStatusListener? = null

    inner class LocalBinder : Binder() {
        fun getService(): LiveStreamService = this@LiveStreamService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        rtmpDisplay = RtmpDisplay(applicationContext, true, this)
    }

    private fun startForegroundNotification() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Potato Monitor Desk - Live", NotificationManager.IMPORTANCE_LOW
            )
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Potato Monitor Desk")
            .setContentText("Sedang live streaming...")
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    /**
     * Mulai live. Wajib dipanggil setelah user memberi izin MediaProjection
     * (resultCode & data didapat dari registerForActivityResult di Activity).
     * Return false kalau device gagal siapkan encoder video/audio.
     */
    fun startLive(resultCode: Int, data: Intent, rtmpUrl: String, useInternalAudio: Boolean): Boolean {
        startForegroundNotification()
        val display = rtmpDisplay ?: return false
        display.setIntentResult(resultCode, data)

        val videoOk = display.prepareVideo()
        val audioOk = if (useInternalAudio && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            display.prepareInternalAudio()
        } else {
            display.prepareAudio()
        }

        return if (videoOk && audioOk) {
            display.startStream(rtmpUrl)
            true
        } else {
            stopForeground(true)
            false
        }
    }

    fun stopLive() {
        rtmpDisplay?.let { if (it.isStreaming) it.stopStream() }
        stopForeground(true)
        stopSelf()
    }

    fun isLive(): Boolean = rtmpDisplay?.isStreaming == true

    override fun onDestroy() {
        rtmpDisplay?.let { if (it.isStreaming) it.stopStream() }
        super.onDestroy()
    }

    // ---------- ConnectCheckerRtmp ----------
    override fun onConnectionSuccessRtmp() {
        listener?.onLiveConnected()
    }

    override fun onConnectionFailedRtmp(reason: String) {
        listener?.onLiveFailed(reason)
    }

    override fun onNewBitrateRtmp(bitrate: Long) {
        // bisa dipakai nanti untuk indikator kualitas koneksi
    }

    override fun onDisconnectRtmp() {
        listener?.onLiveDisconnected()
    }

    override fun onAuthErrorRtmp() {
        listener?.onLiveFailed("Autentikasi RTMP gagal (cek stream key)")
    }

    override fun onAuthSuccessRtmp() {
        // no-op
    }
}
