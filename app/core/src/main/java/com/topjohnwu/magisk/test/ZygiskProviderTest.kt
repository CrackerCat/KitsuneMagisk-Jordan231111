package com.topjohnwu.magisk.test

import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.topjohnwu.magisk.core.Config
import com.topjohnwu.superuser.Shell
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@Keep
@RunWith(AndroidJUnit4::class)
class ZygiskProviderTest : BaseTest {
    private fun status(): JSONObject {
        val result = Shell.cmd("magisk --zygisk-status").exec()
        assertTrue(result.isSuccess)
        return JSONObject(result.out.joinToString("\n"))
    }

    private fun awaitConfigured(value: Boolean) = runBlocking {
        withTimeout(10_000) {
            while (status().getBoolean("builtin_configured") != value) delay(50)
        }
    }

    @Test
    fun testRunningProviderContract() {
        val status = status()
        assertEquals(1, status.getInt("schema"))
        assertEquals("single-provider", status.getString("model"))
        assertEquals(5, status.getInt("module_api"))
        assertTrue(status.getBoolean("boot_ready"))
        assertEquals(
            !status.getBoolean("builtin_configured") &&
                !status.getBoolean("builtin_enabled") &&
                !status.getBoolean("injection_requested") &&
                !status.getBoolean("denylist_enforced"),
            status.getBoolean("external_preconditions_met")
        )
        assertFalse(status.getBoolean("hide_supported"))
        assertFalse(status.getBoolean("sulist_supported"))
    }

    @Test
    fun testSettingChangeRequiresAnotherBoot() {
        val before = status()
        val original = before.getBoolean("builtin_configured")
        try {
            Config.zygisk = !original
            awaitConfigured(!original)
            val changed = status()
            assertEquals(!original, changed.getBoolean("builtin_configured"))
            assertEquals(before.getBoolean("builtin_enabled"), changed.getBoolean("builtin_enabled"))
            assertEquals(before.getBoolean("injection_requested"), changed.getBoolean("injection_requested"))
            if (changed.getBoolean("builtin_configured") || changed.getBoolean("builtin_enabled")) {
                assertFalse(changed.getBoolean("external_preconditions_met"))
            }
        } finally {
            Config.zygisk = original
            awaitConfigured(original)
        }
    }

    @Test
    fun testProviderStatusRequiresRoot() {
        val path = Shell.cmd("magisk --path").exec().out.single()
        val process = ProcessBuilder("$path/magisk", "--zygisk-status")
            .redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        assertTrue(process.waitFor() != 0)
        assertFalse(output.contains("\"schema\""))
    }
}
