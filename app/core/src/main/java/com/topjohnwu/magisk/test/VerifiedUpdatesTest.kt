package com.topjohnwu.magisk.test

import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.topjohnwu.magisk.core.repository.VerifiedUpdates
import okhttp3.Call
import okhttp3.EventListener
import okhttp3.MediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody
import okio.Buffer
import okio.ForwardingSource
import okio.buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import java.io.IOException
import java.io.InterruptedIOException
import java.net.URL

@Keep
@RunWith(AndroidJUnit4::class)
class VerifiedUpdatesTest {
    private fun checkResponseCleanup(consume: Boolean, interrupted: Boolean = false) {
        var cancellations = 0
        var closes = 0
        val body = object : ResponseBody() {
            private val content = object : ForwardingSource(Buffer().writeUtf8("test")) {
                override fun read(sink: Buffer, byteCount: Long): Long {
                    if (interrupted) throw InterruptedIOException("expected interruption")
                    return super.read(sink, byteCount)
                }

                override fun close() {
                    closes++
                    super.close()
                }
            }.buffer()

            override fun contentType(): MediaType? = null
            override fun contentLength() = 4L
            override fun source() = content
        }
        val client = OkHttpClient.Builder().eventListener(object : EventListener() {
            override fun canceled(call: Call) { cancellations++ }
        }).addInterceptor { chain ->
            Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                .code(200).message("OK").body(body).build()
        }.build()
        val connection = VerifiedUpdates.Connection(URL("https://example.invalid/"), client)
        assertEquals(200, connection.responseCode)
        if (consume) {
            try {
                connection.inputStream.use { assertEquals("test", it.reader().readText()) }
                if (interrupted) fail("The read interruption must propagate")
            } catch (e: InterruptedIOException) {
                if (!interrupted) throw e
            }
        }
        connection.disconnect()
        connection.disconnect()
        assertEquals("The body must have one cleanup owner", 1, closes)
        assertEquals("A completed response must not cancel a pooled call", 0, cancellations)
    }

    @Test
    fun testConsumedResponseIsNotCancelled() = checkResponseCleanup(true)

    @Test
    fun testUnreadResponseIsClosedOnce() = checkResponseCleanup(false)

    @Test
    fun testInterruptedResponseIsClosedOnce() = checkResponseCleanup(true, true)

    @Test
    fun testFailedExecutionIsNotCancelledAgain() {
        var cancellations = 0
        val client = OkHttpClient.Builder().eventListener(object : EventListener() {
            override fun canceled(call: Call) { cancellations++ }
        }).addInterceptor { throw IOException("expected test failure") }.build()
        val connection = VerifiedUpdates.Connection(URL("https://example.invalid/"), client)
        try {
            connection.responseCode
            fail("The failed exchange must propagate its error")
        } catch (_: IOException) {
            connection.disconnect()
            connection.disconnect()
        }
        assertEquals(0, cancellations)
    }
}
