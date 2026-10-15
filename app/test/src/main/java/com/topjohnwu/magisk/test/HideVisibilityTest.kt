package com.topjohnwu.magisk.test

import android.app.Service
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Message
import android.os.Messenger
import android.os.Process
import androidx.annotation.Keep
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

private const val MARKER = "/system/etc/kitsune_pr12_marker"

@Keep
open class HideProbeService : Service() {
    private val messenger = Messenger(Handler(Looper.getMainLooper()) { message ->
        val result = Message.obtain(null, 1)
        result.data = Bundle().apply {
            putBoolean("visible", File(MARKER).exists())
            putInt("uid", Process.myUid())
        }
        message.replyTo.send(result)
        true
    })
    override fun onBind(intent: Intent): IBinder = messenger.binder
}

@Keep
class HideIsolatedService : HideProbeService()

@Keep
class HideAppZygoteService : HideProbeService()

@Keep
@RunWith(AndroidJUnit4::class)
class HideVisibilityTest {
    @Test
    fun testModuleVisibility() {
        val arguments = InstrumentationRegistry.getArguments()
        val visible = arguments.getString("visible", "true").toBoolean()
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (File(MARKER).exists() != visible && System.nanoTime() < deadline) Thread.sleep(10)
        assertEquals("Module file in this app's namespace", visible, File(MARKER).exists())
    }

    @Test
    fun testServiceVisibility() {
        val arguments = InstrumentationRegistry.getArguments()
        val visible = arguments.getString("visible", "true").toBoolean()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val service = when (arguments.getString("service", "isolated")) {
            "appzygote" -> HideAppZygoteService::class.java
            "remote" -> HideProbeService::class.java
            else -> HideIsolatedService::class.java
        }
        val latch = CountDownLatch(1)
        var result: Bundle? = null
        val receiver = Messenger(Handler(Looper.getMainLooper()) {
            result = it.data
            latch.countDown()
            true
        })
        val connection = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName, binder: IBinder) {
                val message = Message.obtain(null, 1)
                message.replyTo = receiver
                Messenger(binder).send(message)
            }
            override fun onServiceDisconnected(name: ComponentName) = Unit
        }
        assertTrue(context.bindService(Intent(context, service), connection, Context.BIND_AUTO_CREATE))
        try {
            assertTrue("Service reply", latch.await(10, TimeUnit.SECONDS))
            assertEquals("Module file in service namespace", visible, result?.getBoolean("visible"))
        } finally {
            context.unbindService(connection)
        }
    }
}
