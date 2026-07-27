package com.potato.monitordesk.relay

import java.io.EOFException
import java.io.InputStream

/**
 * Protokol super sederhana dari server (ganti total dari MPEG-TS lama):
 *   [1 byte type: 'V' atau 'A'][4 byte length, big-endian][payload]
 * 'V' payload = 1 JPEG utuh (frame video mentah, belum di-encode H.264).
 * 'A' payload = 1 frame ADTS AAC utuh (7 byte header ADTS + data).
 *
 * PC sengaja TIDAK encode H.264 (mahal di CPU tua) -- itu tugas HP lewat
 * H264SurfaceEncoder, memakai hardware encoder bawaan Android.
 */
object FrameProtocol {
    const val TYPE_VIDEO = 'V'.code.toByte()
    const val TYPE_AUDIO = 'A'.code.toByte()

    interface Listener {
        fun onVideoFrame(jpeg: ByteArray)
        fun onAudioFrame(adts: ByteArray)
    }

    /** Loop blocking -- panggil dari background thread. Berhenti kalau socket
     * ditutup / exception (readFully melempar EOFException). */
    fun readLoop(input: InputStream, listener: Listener, isRunning: () -> Boolean) {
        val header = ByteArray(5)
        while (isRunning()) {
            readFully(input, header, 5)
            val type = header[0]
            val length = ((header[1].toInt() and 0xFF) shl 24) or
                    ((header[2].toInt() and 0xFF) shl 16) or
                    ((header[3].toInt() and 0xFF) shl 8) or
                    (header[4].toInt() and 0xFF)
            if (length < 0 || length > 32 * 1024 * 1024) {
                throw IllegalStateException("Panjang frame tidak masuk akal: $length (protokol desync?)")
            }
            val payload = ByteArray(length)
            readFully(input, payload, length)
            when (type) {
                TYPE_VIDEO -> listener.onVideoFrame(payload)
                TYPE_AUDIO -> listener.onAudioFrame(payload)
            }
        }
    }

    private fun readFully(input: InputStream, buffer: ByteArray, length: Int) {
        var read = 0
        while (read < length) {
            val n = input.read(buffer, read, length - read)
            if (n == -1) throw EOFException("Koneksi ke PC terputus")
            read += n
        }
    }
}
