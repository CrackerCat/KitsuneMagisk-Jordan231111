package com.topjohnwu.magisk.update;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.SystemClock;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InterruptedIOException;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Private staging and platform APK verification; never executes downloaded code. */
public final class UpdateFiles {
    private UpdateFiles() {}

    public static byte[] read(InputStream in, int maximum) throws IOException {
        return read(in, maximum, Long.MAX_VALUE);
    }

    public static byte[] read(InputStream in, int maximum, long deadline) throws IOException {
        try (in; var out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted() || SystemClock.elapsedRealtime() > deadline)
                    throw new InterruptedIOException("Update read interrupted or timed out");
                if (out.size() > maximum - n) throw new IOException("Update data exceeds its size limit");
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }

    public static byte[] asset(File apk, String name, int limit) throws IOException {
        try (ZipFile zip = new ZipFile(apk)) {
            ZipEntry entry = zip.getEntry("assets/" + name);
            if (entry == null || entry.getSize() > limit) throw new IOException("Missing update identity: " + name);
            return read(zip.getInputStream(entry), limit);
        }
    }

    public static byte[] ownAsset(Context context, String name, int limit) throws IOException {
        // Read the installed outer APK, including when a hidden manager supplies dynamic resources.
        return asset(new File(context.getApplicationInfo().sourceDir), name, limit);
    }

    public static String digest(File file) throws IOException {
        try (FileInputStream in = new FileInputStream(file)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            int n;
            while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
            return UpdateMetadata.toHex(digest.digest());
        } catch (GeneralSecurityException e) {
            throw new IOException(e);
        }
    }

    public static void regular(File file) throws IOException {
        try {
            if (!OsConstants.S_ISREG(Os.lstat(file.getPath()).st_mode))
                throw new IOException("Update file is missing or redirected");
        } catch (ErrnoException e) {
            throw new IOException("Cannot inspect update file", e);
        }
    }

    @SuppressWarnings("deprecation")
    public static PackageInfo verifyManager(Context context, File file, String pkg, int minimumCode,
                                            String certificate, UpdateMetadata metadata) throws IOException {
        regular(file);
        if (file.length() > UpdateMetadata.MAX_APK) throw new IOException("APK exceeds its size limit");
        // GET_SIGNATURES/GET_SIGNING_CERTIFICATES request full platform signature verification,
        // not just manifest parsing or an unverified certificate copied from a ZIP entry.
        int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
        PackageInfo info = context.getPackageManager().getPackageArchiveInfo(file.getPath(), flags);
        if (info == null || !pkg.equals(info.packageName)) throw new IOException("Invalid APK or wrong package");
        var signers = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null
                ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if (signers == null || signers.length != 1 ||
                !certificate.equals(UpdateMetadata.sha256(signers[0].toByteArray())))
            throw new IOException("APK has the wrong signing certificate");
        long code = Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
        if (code < minimumCode || code > 2100000000L) throw new IOException("APK would downgrade the manager");
        if (metadata != null) {
            if (Build.VERSION.SDK_INT >= 24 &&
                    (info.applicationInfo == null || info.applicationInfo.minSdkVersion != metadata.minSdk))
                throw new IOException("APK Android requirement differs from signed metadata");
            if (code != metadata.versionCode || !metadata.versionName.equals(info.versionName))
                throw new IOException("APK version differs from signed metadata");
            if (file.length() != metadata.manager.size || !digest(file).equals(metadata.manager.sha256))
                throw new IOException("APK length or digest differs from signed metadata");
            try {
                JSONObject build = new JSONObject(UpdateMetadata.utf8(asset(file, "build-info.json", 65536)));
                if (!metadata.fields.get("build_channel").equals(build.getString("channel")))
                    throw new IOException("APK build channel differs from signed metadata");
                for (String key : new String[]{"application_id", "product_version", "version_name",
                        "source_commit", "source_digest", "upstream_version", "upstream_commit", "build_id", "variant"}) {
                    if (!metadata.fields.get(key).equals(build.getString(key)))
                        throw new IOException("APK build identity mismatch: " + key);
                }
                if (build.getInt("app_version_code") != metadata.versionCode ||
                        build.getLong("protocol_version") != (Long) metadata.fields.get("protocol_version") ||
                        build.getBoolean("source_dirty") != (Boolean) metadata.fields.get("source_dirty"))
                    throw new IOException("APK build numbers differ from signed metadata");
                byte[] stub = asset(file, "stub.apk", 8 * 1024 * 1024);
                if (stub.length != metadata.stub.size || !UpdateMetadata.sha256(stub).equals(metadata.stub.sha256))
                    throw new IOException("Embedded stub differs from signed metadata");
            } catch (JSONException e) {
                throw new IOException("Missing APK build identity", e);
            }
        }
        return info;
    }

    public static void syncDirectory(File directory) throws IOException {
        try {
            var fd = Os.open(directory.getPath(), OsConstants.O_RDONLY, 0);
            try {
                if (!OsConstants.S_ISDIR(Os.fstat(fd).st_mode)) throw new IOException("Not an update directory");
                Os.fsync(fd);
            } finally {
                Os.close(fd);
            }
        } catch (ErrnoException e) {
            throw new IOException("Cannot sync update directory", e);
        }
    }

    public static void publish(File temporary, File destination) throws IOException {
        if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Update cancelled");
        regular(temporary);
        if (!temporary.getParentFile().getCanonicalFile().equals(destination.getParentFile().getCanonicalFile()))
            throw new IOException("Update publication requires one private directory");
        if (destination.exists()) regular(destination);
        try {
            if (!temporary.setReadOnly()) throw new IOException("Cannot protect downloaded code");
            if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Update cancelled");
            Os.rename(temporary.getPath(), destination.getPath());
            syncDirectory(destination.getParentFile());
        } catch (ErrnoException e) {
            throw new IOException("Cannot publish verified update", e);
        }
    }

    public static File copyVerified(Context context, File source, File destination, String pkg,
                                    int minimumCode, String certificate) throws IOException {
        File temporary = File.createTempFile("manager-", ".part", destination.getParentFile());
        try {
            try (var in = new FileInputStream(source); var out = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536];
                long size = 0;
                int n;
                while ((n = in.read(buffer)) != -1) {
                    size += n;
                    if (size > UpdateMetadata.MAX_APK) throw new IOException("Manager copy is too large");
                    out.write(buffer, 0, n);
                }
                out.getFD().sync();
            }
            verifyManager(context, temporary, pkg, minimumCode, certificate, null);
            publish(temporary, destination);
            return destination;
        } finally {
            temporary.delete();
        }
    }
}
