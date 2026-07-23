package com.potato.monitordesk

import org.json.JSONObject
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors

/**
 * Mengirim perintah ganti resolusi/bitrate ke server PC lewat TCP,
 * di port kontrol terpisah (diteruskan via adb reverse yang sama seperti stream).
 */
object ControlClient {
    private const val HOST = "127.0.0.1"
    private const val PORT = 9998
    private val executor = Executors.newSingleThreadExecutor()

    fun sendQuality(resolution: String, videoBitrate: String, onResult: ((Boolean) -> Unit)? = null) {
        executor.execute {
            val success = try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(HOST, PORT), 3000)
                    val json = JSONObject()
                        .put("resolution", resolution)
                        .put("video_bitrate", videoBitrate)
                    socket.getOutputStream().apply {
                        write(json.toString().toByteArray(Charsets.UTF_8))
                        flush()
                    }
                }
                true
            } catch (_: Exception) {
                false
            }
            onResult?.invoke(success)
        }
    }
}
