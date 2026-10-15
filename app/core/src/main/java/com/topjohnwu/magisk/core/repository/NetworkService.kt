package com.topjohnwu.magisk.core.repository

import com.topjohnwu.magisk.core.Config
import com.topjohnwu.magisk.core.Config.Value.BETA_CHANNEL
import com.topjohnwu.magisk.core.Config.Value.CUSTOM_CHANNEL
import com.topjohnwu.magisk.core.Config.Value.DEBUG_CHANNEL
import com.topjohnwu.magisk.core.Config.Value.DEFAULT_CHANNEL
import com.topjohnwu.magisk.core.Config.Value.STABLE_CHANNEL
import com.topjohnwu.magisk.core.Info
import com.topjohnwu.magisk.core.data.RawUrl
import com.topjohnwu.magisk.core.model.UpdateInfo
import retrofit2.HttpException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import timber.log.Timber
import java.io.IOException

class NetworkService(
    private val raw: RawUrl,
) {
    suspend fun fetchUpdate() = withContext(Dispatchers.IO) { safe {
        val client = VerifiedUpdates.client(com.topjohnwu.magisk.core.AppContext)
        val channel = when (Config.updateChannel) {
            STABLE_CHANNEL -> "stable"
            BETA_CHANNEL -> "beta"
            CUSTOM_CHANNEL -> com.topjohnwu.magisk.update.UpdateClient.channelForUrl(Config.customChannelUrl)
            DEFAULT_CHANNEL -> client.defaultChannel
            DEBUG_CHANNEL -> throw IOException("Debug builds have no public update channel")
            else -> throw IOException("Unknown update channel")
        }
        val url = if (Config.updateChannel == CUSTOM_CHANNEL) Config.customChannelUrl
            else client.metadataBase + channel + ".json"
        val metadata = client.fetch(url, channel)
        UpdateInfo(metadata.versionName, metadata.versionCode, metadata.manager.url,
            metadata.notes, metadata.envelope, metadata.channel, metadata.expiresAt)
    } }

    // Release notes are part of the authenticated envelope, not another unchecked URL.
    suspend fun fetchUpdate(version: Int): UpdateInfo? = fetchUpdate()?.takeIf { it.versionCode == version }

    private inline fun <T> safe(factory: () -> T): T? {
        return try {
            if (Info.isConnected.value == true)
                factory()
            else
                null
        } catch (e: Exception) {
            Timber.e(e)
            null
        }
    }

    private inline fun <T> wrap(factory: () -> T): T {
        return try {
            factory()
        } catch (e: HttpException) {
            throw IOException(e)
        }
    }

    // Fetch files
    suspend fun fetchFile(url: String) = wrap { raw.fetchFile(url) }
    suspend fun fetchString(url: String) = wrap { raw.fetchString(url) }
    suspend fun fetchModuleJson(url: String) = wrap { raw.fetchModuleJson(url) }
}
