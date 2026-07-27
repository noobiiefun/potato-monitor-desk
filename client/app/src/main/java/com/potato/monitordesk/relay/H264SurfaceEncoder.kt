package com.potato.monitordesk.relay

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.view.Surface
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Encoder H.264 pakai hardware encoder bawaan Android (MediaCodec), MURAH
 * di CPU/baterai karena ini chip khusus, bukan software encode kayak x264
 * di PC. Terima frame lewat sebuah Surface (kita gambar JPEG yang sudah
 * di-decode ke situ pakai Canvas), keluarannya H.264 Annex-B siap kirim
 * ke RTMP.
 */
class H264SurfaceEncoder(
    width: Int,
    height: Int,
    bitrate: Int = 3_000_000,
    fps: Int = 30,
    private val onEncoded: (data: ByteArray, presentationTimeUs: Long, isKeyFrame: Boolean) -> Unit,
    private val onConfig: (sps: ByteArray, pps: ByteArray) -> Unit
) {
    private val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, width, height).apply {
        setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
        setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
        setInteger(MediaFormat.KEY_FRAME_RATE, fps)
        setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1) // keyframe tiap 1 detik, penting buat RTMP
    }

    private val codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
    val inputSurface: Surface
    private val running = AtomicBoolean(false)
    private var drainThread: Thread? = null
    private var configSent = false

    init {
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        inputSurface = codec.createInputSurface()
    }

    fun start() {
        codec.start()
        running.set(true)
        drainThread = Thread {
            val bufferInfo = MediaCodec.BufferInfo()
            while (running.get()) {
                val outIndex = try {
                    codec.dequeueOutputBuffer(bufferInfo, 100_000)
                } catch (e: Exception) {
                    break
                }
                when {
                    outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                        val newFormat = codec.outputFormat
                        val sps = newFormat.getByteBuffer("csd-0")
                        val pps = newFormat.getByteBuffer("csd-1")
                        if (sps != null && pps != null && !configSent) {
                            configSent = true
                            onConfig(byteBufferToArray(sps), byteBufferToArray(pps))
                        }
                    }
                    outIndex >= 0 -> {
                        val outBuf = codec.getOutputBuffer(outIndex)
                        if (outBuf != null && bufferInfo.size > 0 &&
                            (bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) == 0
                        ) {
                            outBuf.position(bufferInfo.offset)
                            outBuf.limit(bufferInfo.offset + bufferInfo.size)
                            val data = ByteArray(bufferInfo.size)
                            outBuf.get(data)
                            val isKey = (bufferInfo.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0
                            onEncoded(data, bufferInfo.presentationTimeUs, isKey)
                        }
                        codec.releaseOutputBuffer(outIndex, false)
                    }
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun byteBufferToArray(buf: ByteBuffer): ByteArray {
        val dup = buf.duplicate()
        val arr = ByteArray(dup.remaining())
        dup.get(arr)
        return arr
    }

    fun stop() {
        running.set(false)
        drainThread?.interrupt()
        try {
            codec.stop()
        } catch (_: Exception) {
        }
        try {
            codec.release()
        } catch (_: Exception) {
        }
        try {
            inputSurface.release()
        } catch (_: Exception) {
        }
    }
}
