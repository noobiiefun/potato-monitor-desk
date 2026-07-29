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

    /** Connect ke server, server langsung kirim balik JSON {"rtmp_url": "..."}
     * begitu HP connect -- jadi RTMP URL+key cukup diisi sekali di window
     * server, tidak perlu diketik manual di HP. */
    fun fetchRtmpUrl(onResult: (String?) -> Unit) {
        executor.execute {
            val url = try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress(HOST, PORT), 3000)
                    val line = socket.getInputStream().bufferedReader(Charsets.UTF_8).readLine()
                    val json = JSONObject(line ?: "{}")
                    json.optString("rtmp_url", "").ifBlank { null }
                }
            } catch (_: Exception) {
                null
            }
            onResult(url)
        }
    }

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
