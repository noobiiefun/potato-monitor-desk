package com.potato.monitordesk

import android.app.PictureInPictureParams
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
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
 * Menerima stream MPEG-TS (video H.264 + audio AAC) dari server PC lewat
 * TCP socket (diteruskan via adb reverse lewat kabel USB).
 *
 * Fitur tambahan:
 *  - Fullscreen immersive (sembunyikan status/nav bar).
 *  - Picture-in-Picture: tekan tombol minimize atau tombol Home untuk
 *    mengecilkan jadi floating window, tetap jalan sambil pakai app lain.
 *  - Pengaturan kualitas (resolusi/bitrate) dikirim ke server lewat
 *    ControlClient, server otomatis restart stream dengan setting baru.
 *  - Pintasan ke halaman "aplikasi yang disunyikan" & izin notification access.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val HOST = "127.0.0.1"
        private const val STREAM_PORT = 9999
        private const val RETRY_DELAY_MS = 2000L

        // preset kualitas: label -> Pair(resolusi, bitrate video)
        private val QUALITY_PRESETS = linkedMapOf(
            "Rendah (640x360, hemat data)" to Pair("640x360", "1M"),
            "Sedang (960x540)" to Pair("960x540", "2M"),
            "Tinggi (1280x720)" to Pair("1280x720", "3M"),
            "Sangat Tinggi (1920x1080)" to Pair("1920x1080", "6M")
        )
    }

    private lateinit var player: ExoPlayer
    private lateinit var statusText: TextView
    private lateinit var reconnectButton: Button
    private lateinit var settingsButton: ImageButton
    private lateinit var minimizeButton: ImageButton
    private val mainHandler = Handler(Looper.getMainLooper())
    private var retryPending = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        applyImmersiveFullscreen()

        val playerView = findViewById<PlayerView>(R.id.playerView)
        statusText = findViewById(R.id.statusText)
        reconnectButton = findViewById(R.id.reconnectButton)
        settingsButton = findViewById(R.id.settingsButton)
        minimizeButton = findViewById(R.id.minimizeButton)

        player = ExoPlayer.Builder(this).build()
        playerView.player = player

        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY) statusText.text = ""
            }

            override fun onPlayerError(error: PlaybackException) {
                statusText.text = "Terputus dari PC. Mencoba ulang..."
                scheduleReconnect()
            }
        })

        reconnectButton.setOnClickListener { startStream() }
        settingsButton.setOnClickListener { showSettingsMenu() }
        minimizeButton.setOnClickListener { enterPipMode() }

        startStream()
    }

    private fun applyImmersiveFullscreen() {
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )
    }

    private fun startStream() {
        statusText.text = "Menghubungkan ke PC..."

        val mediaItem = MediaItem.Builder()
            .setUri("tcp://$HOST:$STREAM_PORT")
            .setMimeType(MimeTypes.VIDEO_MP2T)
            .build()

        val mediaSource = ProgressiveMediaSource.Factory(TcpDataSourceFactory(HOST, STREAM_PORT))
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

    // ---------- Menu pengaturan ----------
    private fun showSettingsMenu() {
        val options = arrayOf(
            "Kualitas Streaming",
            "Aplikasi yang Disunyikan",
            "Izin Akses Notifikasi"
        )
        AlertDialog.Builder(this)
            .setTitle("Pengaturan")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showQualityDialog()
                    1 -> startActivity(Intent(this, AppListActivity::class.java))
                    2 -> startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                }
            }
            .show()
    }

    private fun showQualityDialog() {
        val labels = QUALITY_PRESETS.keys.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Pilih Kualitas Streaming")
            .setItems(labels) { _, which ->
                val label = labels[which]
                val (resolution, bitrate) = QUALITY_PRESETS.getValue(label)
                Toast.makeText(this, "Menerapkan: $label...", Toast.LENGTH_SHORT).show()
                ControlClient.sendQuality(resolution, bitrate) { success ->
                    mainHandler.post {
                        if (success) {
                            Toast.makeText(
                                this, "Kualitas diubah, stream akan reconnect otomatis.", Toast.LENGTH_SHORT
                            ).show()
                        } else {
                            Toast.makeText(
                                this, "Gagal mengirim ke server. Pastikan server sedang jalan.", Toast.LENGTH_SHORT
                            ).show()
                        }
                    }
                }
            }
            .show()
    }

    // ---------- Picture-in-Picture ----------
    private fun enterPipMode() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            enterPictureInPictureMode(PictureInPictureParams.Builder().build())
        } else {
            Toast.makeText(this, "Picture-in-Picture butuh Android 8.0+", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        // Tekan tombol Home -> otomatis mengecil jadi floating window, bukan hilang total.
        enterPipMode()
    }

    override fun onDestroy() {
        player.release()
        super.onDestroy()
    }
}
