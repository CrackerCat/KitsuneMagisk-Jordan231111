package com.topjohnwu.magisk.core

import org.json.JSONObject

data class RuntimeIdentity(
    val buildId: String,
    val protocolVersion: Int,
    val appVersionCode: Int,
    val applicationId: String,
) {
    val isCompatible get() = protocolVersion == BuildConfig.PROTOCOL_VERSION &&
        applicationId == BuildConfig.APP_PACKAGE_NAME
    val matchesApp get() = isCompatible && buildId == BuildConfig.BUILD_ID

    companion object {
        fun parse(text: String): RuntimeIdentity? = runCatching {
            val json = JSONObject(text)
            require(json.getInt("schema") == 1)
            val buildId = json.getString("build_id")
            require(buildId.matches(Regex("[0-9a-f]{64}")))
            val protocol = json.getInt("protocol_version")
            val code = json.getInt("app_version_code")
            require(protocol > 0 && code > 0)
            RuntimeIdentity(buildId, protocol, code, json.getString("application_id"))
        }.getOrNull()
    }
}
