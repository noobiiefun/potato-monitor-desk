package com.potato.monitordesk

import android.net.Uri
import androidx.media3.common.C
import androidx.media3.datasource.BaseDataSource
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DataSpec
import java.io.InputStream
import java.net.InetSocketAddress
import java.net.Socket

/**
 * DataSource yang connect langsung ke TCP socket (bukan HTTP) untuk membaca
 * stream MPEG-TS mentah dari server PC (lewat adb reverse via kabel USB).
 * Server dianggap live/unbounded, sehingga length selalu C.LENGTH_UNSET.
 */
class TcpDataSource(
    private val host: String,
    private val port: Int,
    private val connectTimeoutMs: Int = 5000
) : BaseDataSource(true) {

    private var socket: Socket? = null
    private var inputStream: InputStream? = null
    private var opened = false

    override fun open(dataSpec: DataSpec): Long {
        val s = Socket()
        s.connect(InetSocketAddress(host, port), connectTimeoutMs)
        s.tcpNoDelay = true
        socket = s
        inputStream = s.getInputStream()
        opened = true
        transferInitializing(dataSpec)
        transferStarted(dataSpec)
        return C.LENGTH_UNSET.toLong()
    }

    override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
        val stream = inputStream ?: return C.RESULT_END_OF_INPUT
        val bytesRead = stream.read(buffer, offset, length)
        if (bytesRead == -1) return C.RESULT_END_OF_INPUT
        bytesTransferred(bytesRead)
        return bytesRead
    }

    override fun getUri(): Uri? = Uri.parse("tcp://$host:$port")

    override fun close() {
        try {
            inputStream?.close()
        } finally {
            inputStream = null
            try {
                socket?.close()
            } finally {
                socket = null
                if (opened) {
                    opened = false
                    transferEnded()
                }
            }
        }
    }
}

class TcpDataSourceFactory(
    private val host: String,
    private val port: Int
) : DataSource.Factory {
    override fun createDataSource(): DataSource = TcpDataSource(host, port)
}
