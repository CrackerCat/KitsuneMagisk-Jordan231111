package com.topjohnwu.magisk.test

import android.os.Process
import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.topjohnwu.magisk.StubApk
import com.topjohnwu.magisk.core.BuildConfig
import com.topjohnwu.superuser.Shell
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

@Keep
@RunWith(AndroidJUnit4::class)
class HidePolicyTest : BaseTest {
    private fun status(): JSONObject {
        val result = Shell.cmd("magisk --hide status").exec()
        assertEquals(0, result.code)
        return JSONObject(result.out.joinToString("\n"))
    }

    @Test
    fun testModeIsLatchedUntilBoot() {
        val before = status()
        assertEquals(1, before.getInt("schema"))
        assertEquals(12, before.getInt("database_version"))
        assertTrue(before.getBoolean("boot_ready"))
        assertEquals(if (before.getBoolean("enabled")) 0 else 1,
            Shell.cmd("magisk magiskhide status").exec().code)
        assertEquals(if (before.getString("mode") == "sulist") 0 else 1,
            Shell.cmd("magisk magiskhide sulist").exec().code)
        val original = before.getString("configured_mode")
        try {
            val next = if (original == "hide") "sulist" else "hide"
            assertEquals(0, Shell.cmd("magisk --hide mode $next").exec().code)
            val changed = status()
            assertEquals(next, changed.getString("configured_mode"))
            assertEquals(before.getString("mode"), changed.getString("mode"))
            assertEquals(next != changed.getString("mode"), changed.getBoolean("reboot_required"))
        } finally {
            assertEquals(0, Shell.cmd("magisk --hide mode $original").exec().code)
        }
    }

    @Test
    fun testSelectionPersistenceAndInvalidInput() {
        val pkg = "io.github.kitsune.pr12.fixture"
        val process = "$pkg:worker"
        assertEquals(listOf("value="), Shell.cmd("magisk --sqlite 'SELECT NULL AS value'").exec().out)
        try {
            Shell.cmd("magisk --denylist rm $pkg").exec()
            assertEquals(0, Shell.cmd("magisk --denylist add $pkg $process").exec().code)
            assertEquals(1, Shell.cmd("magisk --denylist add $pkg $process").exec().code)
            assertTrue(Shell.cmd("magisk --denylist ls").exec().out.contains("$pkg|$process"))
            assertTrue(Shell.cmd("magisk --sqlite \"SELECT process FROM denylist WHERE package_name='$pkg'\"")
                .exec().out.contains("process=$process"))
            assertEquals(5, Shell.cmd("magisk --hide add 'bad/pkg' 'bad;process'").exec().code)
            assertEquals(2, Shell.cmd("magisk --hide enable extra").exec().code)
            assertEquals(0, Shell.cmd("magisk --denylist rm $pkg").exec().code)
            assertFalse(Shell.cmd("magisk --denylist ls").exec().out.contains("$pkg|$process"))
        } finally {
            Shell.cmd("magisk --denylist rm $pkg").exec()
        }
    }

    @Test
    fun testManagerIsAlwaysEligibleAndExecPreservesExit() {
        val result = Shell.cmd("magisk --hide check ${Process.myUid()} manager").exec()
        assertEquals(0, result.code)
        val decision = JSONObject(result.out.joinToString("\n"))
        assertFalse(decision.getBoolean("unmount"))
        assertTrue(decision.getBoolean("su_eligible"))
        assertEquals(23, Shell.cmd("magisk --hide exec sh -c 'exit 23'").exec().code)
        assertEquals(127, Shell.cmd("magisk --hide exec /does/not/exist").exec().code)
    }

    @Test
    fun testHiddenBootstrapDoesNotGrantSuBeforeVerification() {
        assumeTrue(appContext.packageName != BuildConfig.APP_PACKAGE_NAME)
        assumeTrue(status().getString("mode") == "sulist")
        val apk = StubApk.current(appContext).path
        val saved = "$apk.pr12-test"
        // The established root shell restores the payload even if the query
        // fails. No app code is loaded while its backing APK is absent.
        val result = Shell.cmd(
            "test ! -e '$saved' && mv '$apk' '$saved' || exit 1; " +
                "trap \"mv '$saved' '$apk'\" EXIT; " +
                "magisk --hide check ${Process.myUid()} ${appContext.packageName}; " +
                "mv '$saved' '$apk'; trap - EXIT"
        ).exec()
        assertEquals(0, result.code)
        val decision = JSONObject(result.out.joinToString("\n"))
        assertFalse(decision.getBoolean("unmount"))
        assertFalse(decision.getBoolean("manager"))
        assertFalse(decision.getBoolean("su_eligible"))
    }
}
