package com.topjohnwu.magisk.core.repository

import android.content.Context
import com.topjohnwu.magisk.core.BuildConfig
import com.topjohnwu.magisk.core.di.ServiceLocator
import com.topjohnwu.magisk.update.UpdateClient
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

object VerifiedUpdates {
    fun client(context: Context): UpdateClient =
        UpdateClient.create(context, BuildConfig.APP_VERSION_CODE) {
            Connection(it, ServiceLocator.okhttp)
        }

    // Keep the manager's DNS-over-HTTPS preference. The shared verifier still owns
    // every redirect decision; the stub uses the platform HTTPS implementation.
    internal class Connection(url: URL, private val client: OkHttpClient) : HttpURLConnection(url) {
        private var response: Response? = null

        private fun response(): Response {
            response?.let { return it }
            val request = Request.Builder().url(url)
            requestProperties.forEach { (name, values) -> values.forEach { request.addHeader(name, it) } }
            val requestClient = client.newBuilder()
                .followRedirects(false).followSslRedirects(false).cache(null)
                .connectTimeout(connectTimeout.toLong(), TimeUnit.MILLISECONDS)
                .readTimeout(readTimeout.toLong(), TimeUnit.MILLISECONDS)
                .build()
            return requestClient.newCall(request.build()).execute().also {
                response = it
                connected = true
            }
        }

        override fun connect() { response() }
        override fun disconnect() {
            // execute() owns failed-call cleanup; a returned response owns its body.
            // Cancelling after closing that body can race pooled TLS socket teardown
            // on older Android providers. Close this response exactly once instead.
            val completed = response
            response = null
            connected = false
            completed?.close()
        }
        override fun usingProxy() = false
        override fun getResponseCode() = response().code
        override fun getHeaderField(name: String?) = name?.let { response().header(it) }
        override fun getContentEncoding() = response().header("Content-Encoding")
        override fun getContentLength() = response().body.contentLength().toInt()
        override fun getInputStream() = response().body.byteStream()
    }
}
