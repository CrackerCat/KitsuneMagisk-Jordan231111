package com.topjohnwu.magisk.test

import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.topjohnwu.magisk.core.BuildConfig
import com.topjohnwu.magisk.core.RuntimeIdentity
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@Keep
@RunWith(AndroidJUnit4::class)
class BuildInfoTest : BaseTest {
    @Test
    fun testPackagedIdentity() {
        val json = appContext.assets.open("build-info.json").bufferedReader().use { it.readText() }
        assertEquals(BuildConfig.BUILD_INFO_JSON, json.trim())
        val identity = RuntimeIdentity.parse(json)
        assertNotNull(identity)
        assertTrue(identity!!.matchesApp)
        assertEquals(BuildConfig.APP_VERSION_CODE, identity.appVersionCode)
        assertTrue(BuildConfig.APP_VERSION_CODE > 31000)
        assertEquals(31000, BuildConfig.MAGISK_COMPAT_VERSION_CODE)
    }

    @Test
    fun testProtocolAndBuildMatching() {
        val json = JSONObject(BuildConfig.BUILD_INFO_JSON)
        json.put("build_id", "0".repeat(64))
        assertTrue(RuntimeIdentity.parse(json.toString())!!.isCompatible)
        assertFalse(RuntimeIdentity.parse(json.toString())!!.matchesApp)
        json.put("protocol_version", BuildConfig.PROTOCOL_VERSION + 1)
        assertFalse(RuntimeIdentity.parse(json.toString())!!.isCompatible)
        assertNull(RuntimeIdentity.parse("legacy version output"))
        json.put("build_id", "invalid")
        assertNull(RuntimeIdentity.parse(json.toString()))
    }
}
