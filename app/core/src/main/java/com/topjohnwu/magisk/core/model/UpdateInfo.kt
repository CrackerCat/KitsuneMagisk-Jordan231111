package com.topjohnwu.magisk.core.model

import android.os.Parcelable
import com.squareup.moshi.JsonClass
import kotlinx.parcelize.Parcelize

@Parcelize
@JsonClass(generateAdapter = true)
data class UpdateInfo(
    val version: String = "",
    val versionCode: Int = -1,
    val link: String = "",
    val note: String = "",
    val signedMetadata: String = "",
    val channel: String = "",
    val expiresAt: Long = 0
) : Parcelable

@JsonClass(generateAdapter = true)
data class ModuleJson(
    val version: String,
    val versionCode: Int,
    val zipUrl: String,
    val changelog: String,
)
