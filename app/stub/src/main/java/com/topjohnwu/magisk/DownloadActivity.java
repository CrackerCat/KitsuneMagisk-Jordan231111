package com.topjohnwu.magisk;

import static android.R.string.no;
import static android.R.string.ok;
import static android.R.string.yes;

import android.app.Activity;
import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.Context;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.content.res.loader.ResourcesLoader;
import android.content.res.loader.ResourcesProvider;
import android.os.AsyncTask;
import android.os.Build;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.system.Os;
import android.system.OsConstants;
import android.util.Log;
import android.view.ContextThemeWrapper;

import com.topjohnwu.magisk.net.Networking;
import com.topjohnwu.magisk.update.UpdateClient;
import com.topjohnwu.magisk.update.UpdateFiles;
import com.topjohnwu.magisk.utils.APKInstall;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.zip.InflaterInputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;
import java.util.zip.ZipOutputStream;

import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class DownloadActivity extends Activity {

    private static final String APP_NAME = "KitsuneMagisk Next";
    private static final String RES_PKG_NAME = "com.topjohnwu.magisk";

    private boolean dynLoad;

    private int dling;
    private int no_internet_msg;
    private int upgrade_msg;
    private int verification_error_msg;
    private int manual_update;
    private ProgressDialog progress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getTheme().applyStyle(android.R.style.Theme_DeviceDefault_Dialog_NoActionBar, true);

        // Only download and dynamic load full APK if hidden
        dynLoad = !getPackageName().equals(BuildConfig.APPLICATION_ID);

        // Inject resources
        try {
            loadResources();
        } catch (Exception e) {
            error(e);
            return;
        }

        ProviderInstaller.install(this);

        if (Networking.checkNetworkStatus(this)) {
            showDialog();
        } else {
            new AlertDialog.Builder(this)
                    .setCancelable(false)
                    .setTitle(APP_NAME)
                    .setMessage(getString(no_internet_msg))
                    .setNegativeButton(ok, (d, w) -> finish())
                    .show();
        }
    }

    @Override
    public void finish() {
        super.finish();
        Runtime.getRuntime().exit(0);
    }

    // BROWSABLE excludes the private ACTION_VIEW root-request activity.
    @SuppressLint("UnsafeImplicitIntentLaunch")
    private void error(Throwable e) {
        Log.e(getClass().getSimpleName(), Log.getStackTraceString(e));
        runOnUiThread(() -> {
            if (isFinishing()) return;
            if (progress != null) progress.dismiss();
            new AlertDialog.Builder(this).setTitle(APP_NAME)
                    .setMessage(verification_error_msg != 0 ? getString(verification_error_msg)
                            : "Unable to verify the update. Check your connection and device time, then retry.")
                    .setNeutralButton(manual_update != 0 ? getString(manual_update) : "Project releases", (dialog, which) -> {
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW,
                                    Uri.parse("https://github.com/Jordan231111/KitsuneMagisk/releases"))
                                    .addCategory(Intent.CATEGORY_BROWSABLE));
                        } catch (ActivityNotFoundException ignored) {
                        }
                    })
                    .setPositiveButton(ok, (dialog, which) -> finish()).show();
        });
    }

    private void showDialog() {
        new AlertDialog.Builder(this)
                .setCancelable(false)
                .setTitle(APP_NAME)
                .setMessage(getString(upgrade_msg))
                .setPositiveButton(yes, (d, w) -> dlAPK())
                .setNegativeButton(no, (d, w) -> finish())
                .show();
    }

    private void dlAPK() {
        progress = ProgressDialog.show(this, getString(dling), getString(dling) + " " + APP_NAME, true);
        AsyncTask.THREAD_POOL_EXECUTOR.execute(() -> {
            File downloaded = null;
            try {
                var client = UpdateClient.create(this, BuildConfig.MANAGER_VERSION_CODE);
                var metadata = client.fetch(client.metadataBase + client.defaultChannel + ".json", client.defaultChannel);
                downloaded = File.createTempFile("verified-manager-", ".apk", getCacheDir());
                client.download(metadata, downloaded, null);
                if (dynLoad) {
                    UpdateFiles.copyVerified(this, downloaded, StubApk.current(this), BuildConfig.APPLICATION_ID,
                            BuildConfig.MANAGER_VERSION_CODE, (String) metadata.fields.get("certificate_sha256"));
                    runOnUiThread(() -> StubApk.restartProcess(this));
                } else {
                    var session = APKInstall.startSession(this);
                    try (var in = new java.io.FileInputStream(downloaded); var out = session.openStream(this)) {
                        APKInstall.transfer(in, out);
                    }
                    Intent intent = session.waitIntent();
                    runOnUiThread(() -> {
                        if (progress != null) progress.dismiss();
                        if (intent != null) startActivity(intent);
                    });
                }
            } catch (Exception e) {
                error(e);
            } finally {
                if (downloaded != null) downloaded.delete();
            }
        });
    }

    private void decryptResources(OutputStream out) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        SecretKey key = new SecretKeySpec(Bytes.key(), "AES");
        IvParameterSpec iv = new IvParameterSpec(Bytes.iv());
        cipher.init(Cipher.DECRYPT_MODE, key, iv);
        var is = new InflaterInputStream(new CipherInputStream(
                new ByteArrayInputStream(Bytes.res()), cipher));
        try (is; out) {
            APKInstall.transfer(is, out);
        }
    }

    private void loadResources() throws Exception {
        var res = getResources();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            var fd = Os.memfd_create("res", 0);
            try {
                decryptResources(new FileOutputStream(fd));
                Os.lseek(fd, 0, OsConstants.SEEK_SET);
                var loader = new ResourcesLoader();
                try (var pfd = ParcelFileDescriptor.dup(fd)) {
                    loader.addProvider(ResourcesProvider.loadFromTable(pfd, null));
                    res.addLoaders(loader);
                }
            } finally {
                Os.close(fd);
            }
        } else {
            File apk = new File(getCodeCacheDir(), "res.apk");
            try (var out = new ZipOutputStream(new FileOutputStream(apk))) {
                // AndroidManifest.xml is required on Android 6-, and directory support is broken on Android 9-10
                out.putNextEntry(new ZipEntry("AndroidManifest.xml"));
                try (var stubApk = new ZipFile(getPackageCodePath())) {
                    APKInstall.transfer(stubApk.getInputStream(stubApk.getEntry("AndroidManifest.xml")), out);
                }
                out.putNextEntry(new ZipEntry("resources.arsc"));
                decryptResources(out);
            }
            StubApk.addAssetPath(res, apk.getPath());
        }
        dling = res.getIdentifier("dling", "string", RES_PKG_NAME);
        no_internet_msg = res.getIdentifier("no_internet_msg", "string", RES_PKG_NAME);
        upgrade_msg = res.getIdentifier("upgrade_msg", "string", RES_PKG_NAME);
        verification_error_msg = res.getIdentifier("verification_error_msg", "string", RES_PKG_NAME);
        manual_update = res.getIdentifier("manual_update", "string", RES_PKG_NAME);
    }
}
