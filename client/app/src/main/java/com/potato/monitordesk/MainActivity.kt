package com.potato.monitordesk

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.ui.PlayerView

/**
 * Potato Monitor Desk - Client
 *
 * Menerima stream MPEG-TS (video H.264 + audio AAC) langsung dari server PC
 * lewat TCP socket. Koneksi dilakukan ke 127.0.0.1 karena `adb reverse`
 * di sisi PC meneruskan port itu lewat kabel USB ke port yang sama di PC.
 *
 * Pastikan sebelum membuka app ini:
 *   1. Kabel USB PC <-> HP terpasang, USB debugging aktif.
 *   2. potato_server.exe sudah dijalankan di PC (otomatis memasang adb reverse).
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val HOST = "127.0.0.1"
        private const val PORT = 9999
        private const val RETRY_DELAY_MS = 2000L
    }

    private lateinit var player: ExoPlayer
    private lateinit var statusText: TextView
    private lateinit var reconnectButton: Button
    private val mainHandler = Handler(Looper.getMainLooper())
    private var retryPending = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val playerView = findViewById<PlayerView>(R.id.playerView)
        statusText = findViewById(R.id.statusText)
        reconnectButton = findViewById(R.id.reconnectButton)

        player = ExoPlayer.Builder(this).build()
        playerView.player = player

        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) {
                    statusText.text = ""
                }
            }

            override fun onPlayerError(error: PlaybackException) {
                statusText.text = "Terputus dari PC. Mencoba ulang..."
                scheduleReconnect()
            }
        })

        reconnectButton.setOnClickListener { startStream() }

        startStream()
    }

    private fun startStream() {
        statusText.text = "Menghubungkan ke PC..."

        val mediaItem = MediaItem.Builder()
            .setUri("tcp://$HOST:$PORT")
            .setMimeType(MimeTypes.VIDEO_MP2T)
            .build()

        val mediaSource = ProgressiveMediaSource.Factory(TcpDataSourceFactory(HOST, PORT))
            .createMediaSource(mediaItem)

        player.setMediaSource(mediaSource)
        player.prepare()
        player.playWhenReady = true
    }

    private fun scheduleReconnect() {
        if (retryPending) return
        retryPending = true
        mainHandler.postDelayed({
            retryPending = false
            startStream()
        }, RETRY_DELAY_MS)
    }

    override fun onDestroy() {
        player.release()
        super.onDestroy()
    }
}
