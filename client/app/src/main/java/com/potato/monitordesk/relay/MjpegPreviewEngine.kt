package com.potato.monitordesk.relay

import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.widget.ImageView
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Preview ringan: connect ke server PC, decode frame JPEG yang masuk,
 * tampilkan di ImageView. TIDAK memutar audio sama sekali (disengaja --
 * biar tidak ada risiko gema mic dari speaker HP; suara yang sesungguhnya
 * dikirim ke YouTube tetap penuh lewat RelayStreamService, terpisah dari
 * preview ini).
 */
class MjpegPreviewEngine(
    private val host: String,
    private val port: Int,
    private val imageView: ImageView,
    private val onError: (String) -> Unit
) {
    private val running = AtomicBoolean(false)
    private var thread: Thread? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var socket: Socket? = null

    fun start() {
        if (running.getAndSet(true)) return
        thread = Thread {
            try {
                val s = Socket()
                s.connect(InetSocketAddress(host, port), 5000)
                s.tcpNoDelay = true
                socket = s
                FrameProtocol.readLoop(s.getInputStream(), object : FrameProtocol.Listener {
                    override fun onVideoFrame(jpeg: ByteArray) {
                        val bmp = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return
                        mainHandler.post { imageView.setImageBitmap(bmp) }
                    }

                    override fun onAudioFrame(adts: ByteArray) {
                        // sengaja diabaikan -- preview tidak butuh audio
                    }
                }, isRunning = { running.get() })
            } catch (e: Exception) {
                if (running.get()) onError(e.message ?: "Terputus dari PC")
            }
        }.apply { isDaemon = true; start() }
    }

    fun stop() {
        running.set(false)
        thread?.interrupt()
        try {
            socket?.close()
        } catch (_: Exception) {
        }
    }
}
