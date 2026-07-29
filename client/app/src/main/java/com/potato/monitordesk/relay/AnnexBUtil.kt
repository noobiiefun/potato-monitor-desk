package com.potato.monitordesk.relay

/**
 * Utilitas kecil untuk cari NAL unit SPS (type 7) / PPS (type 8) di dalam
 * satu access unit H.264 Annex-B (dipisah start code 0x000001 / 0x00000001).
 * Dibutuhkan karena RtmpClient.setVideoInfo() butuh SPS & PPS terpisah,
 * sedangkan yang kita terima dari demux TS adalah gabungan NAL per frame.
 */
object AnnexBUtil {

    data class NalUnit(val type: Int, val start: Int, val end: Int)

    fun findNalUnits(data: ByteArray): List<NalUnit> {
        val starts = mutableListOf<Int>()
        var i = 0
        while (i < data.size - 3) {
            if (data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte()) {
                starts.add(i + 3)
                i += 3
            } else if (i < data.size - 4 &&
                data[i] == 0.toByte() && data[i + 1] == 0.toByte() &&
                data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte()
            ) {
                starts.add(i + 4)
                i += 4
            } else {
                i++
            }
        }
        val units = mutableListOf<NalUnit>()
        for ((idx, s) in starts.withIndex()) {
            if (s >= data.size) continue
            val type = data[s].toInt() and 0x1F
            val end = if (idx + 1 < starts.size) {
                // mundur sampai sebelum start code NAL berikutnya
                var backTo = starts[idx + 1]
                while (backTo > s && data[backTo - 1] == 0.toByte()) backTo--
                if (backTo > s && data.getOrNull(backTo - 4) == 0.toByte()) backTo -= 0
                backTo - 3 // kira-kira sebelum start code (000001/00000001 sudah termasuk di atas)
            } else {
                data.size
            }
            units.add(NalUnit(type, s, end.coerceAtLeast(s)))
        }
        return units
    }

    fun sps(data: ByteArray): ByteArray? = findNalUnits(data).firstOrNull { it.type == 7 }
        ?.let { data.copyOfRange(it.start, it.end) }

    fun pps(data: ByteArray): ByteArray? = findNalUnits(data).firstOrNull { it.type == 8 }
        ?.let { data.copyOfRange(it.start, it.end) }

    fun containsKeyFrame(data: ByteArray): Boolean = findNalUnits(data).any { it.type == 5 }
}
