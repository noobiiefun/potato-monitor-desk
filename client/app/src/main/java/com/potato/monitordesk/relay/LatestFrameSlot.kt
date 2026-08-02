package com.potato.monitordesk.relay

/**
 * Penampung 1 slot: kalau ada frame baru masuk sebelum yang lama sempat
 * diproses, yang LAMA dibuang begitu saja (bukan diantrikan). Ini yang
 * mencegah delay numpuk terus-menerus -- HP selalu proses frame TERBARU
 * yang tersedia, bukan mengejar semua frame secara berurutan.
 *
 * Dipakai khusus untuk VIDEO (JPEG) -- karena tiap JPEG berdiri sendiri
 * (bukan seperti H.264 yang butuh referensi antar-frame), aman dibuang
 * kapan saja tanpa merusak apa pun.
 */
class LatestFrameSlot {
    private val lock = Object()
    private var pending: ByteArray? = null

    fun put(data: ByteArray) {
        synchronized(lock) {
            pending = data
            lock.notifyAll()
        }
    }

    /** Blok sampai ada frame, lalu kembalikan yang PALING BARU (dan kosongkan slot).
     * Return null kalau thread di-interrupt (mis. pas stop()) -- caller harus
     * berhenti loop begitu dapat null, JANGAN biarkan InterruptedException lolos
     * ke luar: exception yang tidak ketangkep di thread MANA PUN akan mematikan
     * SELURUH proses app di Android, bukan cuma thread itu saja. */
    fun take(): ByteArray? {
        synchronized(lock) {
            try {
                while (pending == null) lock.wait()
            } catch (e: InterruptedException) {
                Thread.currentThread().interrupt()
                return null
            }
            val data = pending!!
            pending = null
            return data
        }
    }

    fun wakeUp() {
        synchronized(lock) { lock.notifyAll() }
    }
}
