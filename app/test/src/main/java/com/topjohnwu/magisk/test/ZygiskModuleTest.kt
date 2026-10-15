package com.topjohnwu.magisk.test

import android.system.Os
import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@Keep
@RunWith(AndroidJUnit4::class)
class ZygiskModuleTest {
    @Test
    fun testInjected() {
        assertEquals("API v5 module directory and root companion", "ok", Os.getenv("KITSUNE_ZYGISK_PROBE"))
        assertEquals("postAppSpecialize", "ok", Os.getenv("KITSUNE_ZYGISK_POST"))
        assertNotNull(Os.getenv("KITSUNE_ZYGISK_FLAGS")?.toUIntOrNull())
    }

    @Test
    fun testNotInjected() {
        assertNull(Os.getenv("KITSUNE_ZYGISK_PROBE"))
        assertNull(Os.getenv("KITSUNE_ZYGISK_POST"))
    }
}
