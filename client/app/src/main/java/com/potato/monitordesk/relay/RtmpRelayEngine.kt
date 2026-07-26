package com.potato.monitordesk.relay

import android.media.MediaCodec
import androidx.media3.common.C
import androidx.media3.common.DataReader
import androidx.media3.extractor.DefaultExtractorInput
import androidx.media3.extractor.PositionHolder
import androidx.media3.extractor.ts.TsExtractor
import com.pedro.common.ConnectChecker
import com.pedro.rtmp.rtmp.RtmpClient
import java.io.InputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Mengambil stream MPEG-TS mentah dari server PC (socket TCP yang sama yang
 * dipakai preview di MainActivity), demux jadi access unit H.264/AAC yang
 * MASIH TERKOMPRESI, lalu kirim langsung ke RTMP (YouTube dkk) tanpa decode
 * dan tanpa re-encode ulang. Tidak menyentuh layar/MediaProjection sama sekali.
 *
 * CATATAN PENTING (tolong dites langsung di device, bagian ini paling
 * mungkin butuh penyesuaian kecil):
 * - Server PC HARUS bisa terima lebih dari 1 koneksi TCP sekaligus di port
 *   yang sama (satu untuk preview ExoPlayer, satu untuk relay ini), atau
 *   siapkan port kedua khusus relay kalau server belum multi-client.
 * - Asumsi audio AAC-LC (paling umum). Kalau OBS di-setting pakai codec
 *   lain, ganti bagian setAudioInfo.
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
    private var demuxThread: Thread? = null
    private var videoThread: Thread? = null
    private var audioThread: Thread? = null
    private lateinit var rtmpClient: RtmpClient

    private var videoInfoSent = false
    private var audioInfoSent = false

    fun start(rtmpUrl: String) {
        if (running.getAndSet(true)) return
        rtmpClient = RtmpClient(this)

        demuxThread = Thread {
            try {
                val s = Socket()
                s.connect(InetSocketAddress(host, port), 5000)
                s.tcpNoDelay = true
                socket = s
                rtmpClient.connect(rtmpUrl)
                runDemuxLoop(s.getInputStream())
            } catch (e: Exception) {
                listener.onRelayFailed(e.message ?: "Gagal konek ke server PC")
            }
        }.apply { isDaemon = true; start() }
    }

    fun stop() {
        if (!running.getAndSet(false)) return
        videoThread?.interrupt()
        audioThread?.interrupt()
        demuxThread?.interrupt()
        try {
            if (::rtmpClient.isInitialized) rtmpClient.disconnect()
        } catch (_: Exception) {
        }
        try {
            socket?.close()
        } catch (_: Exception) {
        }
    }

    private fun runDemuxLoop(inputStream: InputStream) {
        val output = RelayExtractorOutput()
        val extractor = TsExtractor()
        extractor.init(output)

        val dataReader = DataReader { buffer, offset, length -> inputStream.read(buffer, offset, length) }
        val extractorInput = DefaultExtractorInput(dataReader, 0L, C.LENGTH_UNSET.toLong())
        val seekPositionHolder = PositionHolder()

        var consumersStarted = false

        while (running.get()) {
            val result = try {
                extractor.read(extractorInput, seekPositionHolder)
            } catch (e: Exception) {
                listener.onRelayFailed(e.message ?: "Koneksi terputus dari PC")
                break
            }
            if (result == androidx.media3.extractor.Extractor.RESULT_END_OF_INPUT) {
                listener.onRelayDisconnected()
                break
            }

            if (!consumersStarted && output.tracksEnded) {
                consumersStarted = true
                output.videoTrack()?.let { startVideoConsumer(it) }
                output.audioTrack()?.let { startAudioConsumer(it) }
            }
        }
    }

    private fun startVideoConsumer(track: RelayTrackOutput) {
        videoThread = Thread {
            while (running.get()) {
                val sample = track.sampleQueue.take()
                try {
                    if (!videoInfoSent) {
                        val sps = AnnexBUtil.sps(sample.data)
                        val pps = AnnexBUtil.pps(sample.data)
                        if (sps != null && pps != null) {
                            rtmpClient.setVideoInfo(ByteBuffer.wrap(sps), ByteBuffer.wrap(pps), null)
                            videoInfoSent = true
                        }
                    }
                    val info = MediaCodec.BufferInfo().apply {
                        presentationTimeUs = sample.timeUs
                        size = sample.data.size
                        offset = 0
                        flags = if (sample.isKeyFrame || AnnexBUtil.containsKeyFrame(sample.data)) {
                            MediaCodec.BUFFER_FLAG_KEY_FRAME
                        } else 0
                    }
                    rtmpClient.sendVideo(ByteBuffer.wrap(sample.data), info)
                } catch (_: Exception) {
                    // sample rusak/parsial, skip -- lanjut ke frame berikutnya
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun startAudioConsumer(track: RelayTrackOutput) {
        audioThread = Thread {
            while (running.get()) {
                val sample = track.sampleQueue.take()
                try {
                    if (!audioInfoSent) {
                        val format = track.format
                        if (format != null && format.sampleRate > 0) {
                            rtmpClient.setAudioInfo(format.sampleRate, format.channelCount >= 2)
                            audioInfoSent = true
                        }
                    }
                    val info = MediaCodec.BufferInfo().apply {
                        presentationTimeUs = sample.timeUs
                        size = sample.data.size
                        offset = 0
                        flags = 0
                    }
                    rtmpClient.sendAudio(ByteBuffer.wrap(sample.data), info)
                } catch (_: Exception) {
                }
            }
        }.apply { isDaemon = true; start() }
    }

    // ---------- ConnectChecker (status koneksi RTMP) ----------
    override fun onConnectionStarted(url: String) {}
    override fun onConnectionSuccess() = listener.onRelayConnected()
    override fun onConnectionFailed(reason: String) = listener.onRelayFailed(reason)
    override fun onNewBitrate(bitrate: Long) {}
    override fun onDisconnect() = listener.onRelayDisconnected()
    override fun onAuthError() = listener.onRelayFailed("Autentikasi RTMP gagal (cek stream key)")
    override fun onAuthSuccess() {}
}
