package com.topjohnwu.magisk.core.download

import android.net.Uri
import com.topjohnwu.magisk.StubApk
import com.topjohnwu.magisk.core.BuildConfig
import com.topjohnwu.magisk.core.R
import com.topjohnwu.magisk.update.UpdateClient
import com.topjohnwu.magisk.update.UpdateFiles
import com.topjohnwu.magisk.core.repository.VerifiedUpdates
import com.topjohnwu.magisk.core.isRunningAsStub
import com.topjohnwu.magisk.core.ktx.cachedFile
import com.topjohnwu.magisk.core.ktx.copyAll
import com.topjohnwu.magisk.core.ktx.copyAndClose
import com.topjohnwu.magisk.core.ktx.withInOut
import com.topjohnwu.magisk.core.ktx.writeTo
import com.topjohnwu.magisk.core.tasks.AppMigration
import com.topjohnwu.magisk.core.utils.MediaStoreUtils.outputStream
import com.topjohnwu.magisk.utils.APKInstall
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.runInterruptible
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream
import org.apache.commons.compress.archivers.zip.ZipFile
import java.io.File
import java.io.IOException
import java.io.InputStream

class DownloadProcessor(notifier: DownloadNotifier) : DownloadNotifier by notifier {

    suspend fun handle(stream: InputStream, subject: Subject) {
        when (subject) {
            is Subject.App -> {
                stream.close()
                throw IOException("App updates require authenticated metadata")
            }
            is Subject.Module -> handleModule(stream, subject.file)
            else -> stream.copyAndClose(subject.file.outputStream())
        }
    }

    suspend fun handleApp(subject: Subject.App, progress: UpdateClient.Progress) {
        val client = VerifiedUpdates.client(context)
        val metadata = client.accept(subject.json.signedMetadata, subject.json.channel)
        val downloaded = File.createTempFile("verified-update-", ".apk", context.cacheDir)
        try {
            runInterruptible {
                client.download(metadata, downloaded, progress)
                downloaded.inputStream().use { input ->
                    subject.file.outputStream().use { input.copyTo(it) }
                }
            }
            currentCoroutineContext().ensureActive()
            if (isRunningAsStub) {
                val updateApk = StubApk.update(context)
                runInterruptible {
                    UpdateFiles.copyVerified(context, downloaded, updateApk, BuildConfig.APP_PACKAGE_NAME,
                        BuildConfig.APP_VERSION_CODE, metadata.fields["certificate_sha256"] as String)
                }
                try {
                    notifyUpdate(subject.notifyId) {
                        it.setProgress(0, 0, true)
                            .setContentTitle(context.getString(R.string.hide_app_title))
                            .setContentText("")
                    }
                    val stub = File.createTempFile("verified-stub-", ".apk", context.cacheDir)
                    try {
                        stub.writeBytes(UpdateFiles.asset(downloaded, "stub.apk", 8 * 1024 * 1024))
                        subject.intent = AppMigration.upgradeStub(context, stub)
                            ?: throw IOException("Cannot upgrade hidden manager")
                    } finally {
                        stub.delete()
                    }
                } catch (e: Exception) {
                    updateApk.delete()
                    throw e
                }
            } else {
                subject.intent = runInterruptible {
                    val session = APKInstall.startSession(context)
                    downloaded.inputStream().use { input ->
                        session.openStream(context).use { input.copyTo(it) }
                    }
                    session.waitIntent()
                }
            }
        } finally {
            downloaded.delete()
        }
    }

    suspend fun handleModule(src: InputStream, file: Uri) {
        val tmp = context.cachedFile("module.zip")
        try {
            // First download the entire zip into cache so we can process it
            src.writeTo(tmp)

            val input = ZipFile.Builder().setFile(tmp).get()
            val output = ZipArchiveOutputStream(file.outputStream())
            withInOut(input, output) { zin, zout ->
                zout.putArchiveEntry(ZipArchiveEntry("META-INF/"))
                zout.closeArchiveEntry()
                zout.putArchiveEntry(ZipArchiveEntry("META-INF/com/"))
                zout.closeArchiveEntry()
                zout.putArchiveEntry(ZipArchiveEntry("META-INF/com/google/"))
                zout.closeArchiveEntry()
                zout.putArchiveEntry(ZipArchiveEntry("META-INF/com/google/android/"))
                zout.closeArchiveEntry()

                zout.putArchiveEntry(ZipArchiveEntry("META-INF/com/google/android/update-binary"))
                context.assets.open("module_installer.sh").use { it.copyAll(zout) }
                zout.closeArchiveEntry()

                zout.putArchiveEntry(ZipArchiveEntry("META-INF/com/google/android/updater-script"))
                zout.write("#MAGISK\n".toByteArray())
                zout.closeArchiveEntry()

                // Then simply copy all entries to output
                zin.copyRawEntries(zout) { entry -> !entry.name.startsWith("META-INF") }
            }
        } finally {
            tmp.delete()
        }
    }

}
