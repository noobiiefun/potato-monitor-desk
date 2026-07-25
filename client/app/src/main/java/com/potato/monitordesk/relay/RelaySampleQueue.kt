package com.potato.monitordesk.relay

import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.common.util.ParsableByteArray
import androidx.media3.datasource.DataReader
import androidx.media3.extractor.ExtractorOutput
import androidx.media3.extractor.SeekMap
import androidx.media3.extractor.TrackOutput
import java.io.ByteArrayOutputStream
import java.util.concurrent.LinkedBlockingQueue

/**
 * Satu access unit (1 frame video H.264 Annex-B, atau 1 frame audio AAC raw)
 * yang sudah di-demux dari TS -- MASIH TERKOMPRESI, belum di-decode.
 */
data class RelaySample(
    val data: ByteArray,
    val timeUs: Long,
    val isKeyFrame: Boolean
)

/**
 * TrackOutput yang menampung sample mentah (bukan meneruskannya ke decoder
 * seperti biasa dipakai ExoPlayer). Setiap track (video/audio) yang
 * dideteksi TsExtractor dapat instance-nya sendiri.
 */
class RelayTrackOutput(val trackType: Int) : TrackOutput {

    val sampleQueue = LinkedBlockingQueue<RelaySample>()

    @Volatile
    var format: Format? = null
        private set

    private val pending = ByteArrayOutputStream()

    override fun format(format: Format) {
        this.format = format
    }

    override fun sampleData(input: DataReader, length: Int, allowEndOfInput: Boolean): Int {
        val buf = ByteArray(length)
        var readTotal = 0
        while (readTotal < length) {
            val n = input.read(buf, readTotal, length - readTotal)
            if (n == -1) {
                if (allowEndOfInput) break
                throw java.io.EOFException()
            }
            readTotal += n
        }
        pending.write(buf, 0, readTotal)
        return readTotal
    }

    override fun sampleData(data: ParsableByteArray, length: Int) {
        pending.write(data.data, data.position, length)
        data.setPosition(data.position + length)
    }

    override fun sampleMetadata(
        timeUs: Long,
        flags: Int,
        size: Int,
        offset: Int,
        cryptoData: TrackOutput.CryptoData?
    ) {
        val all = pending.toByteArray()
        val end = all.size - offset
        val start = (end - size).coerceAtLeast(0)
        if (start >= end) return
        val sampleBytes = all.copyOfRange(start, end)
        val isKey = (flags and C.BUFFER_FLAG_KEY_FRAME) != 0
        sampleQueue.put(RelaySample(sampleBytes, timeUs, isKey))

        // buang bagian yang sudah dipakai, sisakan bagian yang masih "offset" dari akhir
        if (end < all.size) {
            val remainder = all.copyOfRange(end, all.size)
            pending.reset()
            pending.write(remainder)
        } else {
            pending.reset()
        }
    }
}

/**
 * ExtractorOutput yang membuatkan RelayTrackOutput untuk tiap track yang
 * ditemukan TsExtractor (biasanya 1 video + 1 audio).
 */
class RelayExtractorOutput : ExtractorOutput {
    val tracks = mutableMapOf<Int, RelayTrackOutput>()

    @Volatile
    var tracksEnded = false
        private set

    override fun track(id: Int, type: Int): TrackOutput {
        return tracks.getOrPut(id) { RelayTrackOutput(type) }
    }

    override fun endTracks() {
        tracksEnded = true
    }

    override fun seekMap(seekMap: SeekMap) {
        // live stream, tidak butuh seek table
    }

    fun videoTrack(): RelayTrackOutput? = tracks.values.firstOrNull { it.trackType == androidx.media3.common.C.TRACK_TYPE_VIDEO }
    fun audioTrack(): RelayTrackOutput? = tracks.values.firstOrNull { it.trackType == androidx.media3.common.C.TRACK_TYPE_AUDIO }
}
