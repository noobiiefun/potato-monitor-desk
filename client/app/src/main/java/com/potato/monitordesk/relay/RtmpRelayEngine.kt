package com.potato.monitordesk.relay

import android.graphics.BitmapFactory
import android.graphics.Rect
import android.media.MediaCodec
import com.pedro.common.ConnectChecker
import com.pedro.rtmp.rtmp.RtmpClient
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Engine relay "spacedesk-style": PC cuma kirim JPEG mentah (murah di CPU
 * PC) + AAC audio lewat socket TCP. HP yang decode JPEG lalu ENCODE ulang
 * jadi H.264 pakai hardware encoder (H264SurfaceEncoder) -- baru dikirim
 * ke RTMP. PC tidak pernah encode H.264 sama sekali.
 */
class RtmpRelayEngine(
    private val host: String,
    private val port: Int,
    private val listener: Listener
) : ConnectChecker {

    interface Listener {
        fun onRelayConnected()
        fun onRelayFailed(reason: String)
        fun onRelayDisconnected()
    }

    private val running = AtomicBoolean(false)
    private var socket: Socket? = null
    private var readThread: Thread? = null
    private var videoWorkerThread: Thread? = null
    private lateinit var rtmpClient: RtmpClient
    private var encoder: H264SurfaceEncoder? = null
    private val videoSlot = LatestFrameSlot()

    private var audioInfoSent = false
    private var connectedNotified = false

    // resolusi HARUS sama dengan config.json server ("resolution": "1280x720" default)
    private var videoWidth = 1280
    private var videoHeight = 720

    fun start(rtmpUrl: String) {
        if (running.getAndSet(true)) return
        rtmpClient = RtmpClient(this)

        readThread = Thread {
            try {
                val s = Socket()
                s.connect(InetSocketAddress(host, port), 5000)
                s.tcpNoDelay = true
                socket = s

                encoder = H264SurfaceEncoder(
                    width = videoWidth, height = videoHeight,
                    onEncoded = { data, ptsUs, isKey ->
                        try {
                            val info = MediaCodec.BufferInfo().apply {
                                presentationTimeUs = ptsUs
                                size = data.size
                                offset = 0
                                flags = if (isKey) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                            }
                            rtmpClient.sendVideo(ByteBuffer.wrap(data), info)
                        } catch (_: Exception) {
                        }
                    },
                    onConfig = { sps, pps ->
                        try {
                            rtmpClient.setVideoInfo(ByteBuffer.wrap(sps), ByteBuffer.wrap(pps), null)
                        } catch (_: Exception) {
                        }
                    }
                )
                encoder?.start()
                startVideoWorker()

                rtmpClient.connect(rtmpUrl)

                // Thread ini HANYA membaca dari socket & naruh ke slot/queue --
                // tidak pernah decode/gambar langsung di sini, supaya baca
                // socket tidak pernah ketahan oleh proses decode yang lambat.
                FrameProtocol.readLoop(s.getInputStream(), object : FrameProtocol.Listener {
                    override fun onVideoFrame(jpeg: ByteArray) {
                        videoSlot.put(jpeg)
                    }

                    override fun onAudioFrame(adts: ByteArray) {
                        handleAudioFrame(adts)
                    }
                }, isRunning = { running.get() })
            } catch (e: Exception) {
                listener.onRelayFailed(e.message ?: "Gagal konek ke server PC")
            } finally {
                videoWorkerThread?.interrupt()
                encoder?.stop()
                encoder = null
            }
        }.apply { isDaemon = true; start() }
    }

    private fun startVideoWorker() {
        videoWorkerThread = Thread {
            while (running.get()) {
                val jpeg = videoSlot.take()
                handleVideoFrame(jpeg)
            }
        }.apply { isDaemon = true; start() }
    }

    private fun handleVideoFrame(jpeg: ByteArray) {
        val enc = encoder ?: return
        try {
            val bmp = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return
            val canvas = enc.inputSurface.lockCanvas(null) ?: run { bmp.recycle(); return }
            val dst = Rect(0, 0, canvas.width, canvas.height)
            canvas.drawBitmap(bmp, null, dst, null)
            enc.inputSurface.unlockCanvasAndPost(canvas)
            bmp.recycle()
        } catch (_: Exception) {
            // 1 frame korup/parsial, skip -- lanjut frame berikutnya
        }
    }

    private fun handleAudioFrame(adts: ByteArray) {
        if (adts.size < 7) return
        try {
            if (!audioInfoSent) {
                val (sampleRate, channels) = parseAdtsHeader(adts)
                rtmpClient.setAudioInfo(sampleRate, channels >= 2)
                audioInfoSent = true
            }
            // buang 7 byte header ADTS, RtmpClient butuh raw AAC saja
            val raw = adts.copyOfRange(7, adts.size)
            val info = MediaCodec.BufferInfo().apply {
                presentationTimeUs = System.nanoTime() / 1000
                size = raw.size
                offset = 0
                flags = 0
            }
            rtmpClient.sendAudio(ByteBuffer.wrap(raw), info)
        } catch (_: Exception) {
        }
    }

    /** Parse header ADTS 7 byte -> (sampleRate, channelCount). */
    private fun parseAdtsHeader(h: ByteArray): Pair<Int, Int> {
        val freqTable = intArrayOf(
            96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050,
            16000, 12000, 11025, 8000, 7350, 0, 0, 0
        )
        val freqIdx = ((h[2].toInt() and 0x3C) shr 2)
        val sampleRate = if (freqIdx in freqTable.indices) freqTable[freqIdx] else 44100
        val channelCfg = ((h[2].toInt() and 0x01) shl 2) or ((h[3].toInt() and 0xC0) shr 6)
        return Pair(sampleRate, channelCfg)
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        readThread?.interrupt()
        videoWorkerThread?.interrupt()
        videoSlot.wakeUp()
        try {
            if (::rtmpClient.isInitialized) rtmpClient.disconnect()
        } catch (_: Exception) {
        }
        try {
            socket?.close()
        } catch (_: Exception) {
        }
        encoder?.stop()
        encoder = null
    }

    // ---------- ConnectChecker (status koneksi RTMP) ----------
    override fun onConnectionStarted(url: String) {}
    override fun onConnectionSuccess() {
        if (!connectedNotified) {
            connectedNotified = true
            listener.onRelayConnected()
        }
    }
    override fun onConnectionFailed(reason: String) = listener.onRelayFailed(reason)
    override fun onNewBitrate(bitrate: Long) {}
    override fun onDisconnect() = listener.onRelayDisconnected()
    override fun onAuthError() = listener.onRelayFailed("Autentikasi RTMP gagal (cek stream key)")
    override fun onAuthSuccess() {}
}
