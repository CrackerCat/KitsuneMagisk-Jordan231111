# PR15 qualification contract

PR15 uses the available Android Studio AVDs, MuMuPlayer Pro **Android Device-1**, and a newly
created BlueStacks Air instance. LDPlayer and Nox are outside this run's requested scope.
Physical phones are unavailable. The [generated table](../compatibility/TESTED.md) reports exact
observations; it does not confer production status or physical-device support.

## What a virtual device proves

An AVD hardware profile changes the simulated screen, memory and peripherals. It still boots an
emulator kernel and SDK system image. Renaming it Pixel, Samsung or RedMagic does not simulate
the named phone's bootloader, device tree, partition layout, firmware, encryption or recovery.
An OEM kernel release alone cannot supply those missing components or make that kernel boot on
the emulator's virtual hardware. Custom AOSP kernels/images must target the emulator or Cuttlefish.
See [Android's AVD model](https://developer.android.com/studio/run/managing-avds) and
[Cuttlefish](https://source.android.com/docs/devices/cuttlefish).

The matrix therefore separates real emulator boots, synthetic boot-image fixtures, unsupported
installation routes and unqualified physical targets. Two matching boot IDs cannot count as two
cold boots. Build-only ABIs, permissive SELinux and fixture headers cannot substitute for matching
runtime evidence. Each accepted run names the exact APK digest and clean source identity.

The [module compatibility matrix](module-compatibility.md) separately records pinned third-party
ZIPs, ordinary lifecycle checks, selected functional probes and official Magisk controls. A successful
installation is not proof of working hiding, audio processing, charging control or hardware attestation.

## Reproducing the checks

Use the repository environment wrapper and a disposable SDK device. `scripts/avd.sh test API TYPE`
patches a copy of the SDK ramdisk, runs debug and release setup, closes and restarts the owned
emulator process, and exercises SU, modules, Hide/SuList, provider, manager migration and recovery.
`MAGISK_AVD_DEVICE` selects an installed hardware profile; `MAGISK_AVD_NAME` and
`MAGISK_AVD_PORT` isolate the instance. `AVD_QUALIFICATION_DIR` retains exact guest/boot records.
Set `AVD_BOOT_FIXTURES=1` to run the APK's MagiskBoot tests. No shared SDK ramdisk is overwritten.
For disposable Play Store images, `AVD_DISABLE_STORE_UPDATES=1` disables the Store updater
and records that choice in `store-updater-state.txt`. A Play Services update terminated a
running hidden-manager suite through Android's package-dependency handling. Pinning the guest
software prevents that environmental change during acceptance; it is not a crash exemption
or an instruction to disable updates on users' devices. Those temporary AVDs are deleted afterward.

`scripts/env.py python3 tools/boot_qualification.py --serial SERIAL --apk APK --output REPORT`
tests boot headers v0–v4, init_boot, vendor_boot v3/v4, original-init restoration, unchanged kernels,
Vivo and Samsung patch signatures, and compressed-kernel `split -n`. OpenSSL independently signs
and verifies RSA/P-256/P-384/P-521 AVB1 records; tampered and nonstandard raw EC signatures fail.
Temporary private keys and guest fixture files are removed. These fixtures do not boot OEM kernels.
The expanded corpus also rejects truncated gzip/XZ/bzip2 inputs, removes partial outputs,
preserves empty streams, Samsung signing trailers and AVB2 descriptors, and checks ARM32 zImage
payload relocation against an independent gzip decoder and the exact header pointers.

`scripts/env.py python3 tools/device_qualification.py render` generates both public compatibility
outputs from `docs/device-pr15.json`. CI checks for stale output and rejects unsupported status
promotion, missing evidence, reused boot IDs, dirty source and incomplete acceptance records.

MuMu lifecycle operations use its `mumutool` CLI and an explicitly pinned ADB serial. Save both
stopped-instance disks, verify restore bytes, and cold start by closing and reopening the player.
Do not use `adb reboot`. Preserve the user's original instance and restore it after testing.

BlueStacks bootstrap uses the separately supplied `blueStackRoot.command` on the new instance.
Its legacy root and shared host-initramfs hook are bootstrap evidence, not a claim that the current
Kitsune Direct-System transaction supports BlueStacks. A read-only system remains a refusal even
after bootstrap root succeeds. Live setup is temporary and must be identified separately.

The experimental host-initramfs route stages an offline copy with
`tools/system_mode/host_image.py`. It replaces only the owned payload and bootstrap script,
checks the APK identity and ARM binaries, and preserves unrelated archive entries. Its controller
must select the disposable instance, flush guest writes before closing it, stop players before
publishing the image, verify the result and retain a verified factory restore. Root/unroot use the
existing per-instance RootMac gate. The supplied tool is external and is not redistributed here.
This route starts at post-fs-data; it does not provide magiskinit pre-init mounting or qualify the
ordinary in-app Direct Install, inactive-slot, OTA or recovery routes on BlueStacks.

## Compatibility changes and remaining boundaries

- PR15 retains the v31.0 baseline plus [verified fixes](device-pr15/upstream-fixes.json), as selected
  by the user. It preserves interactive SU consent and Kitsune Hide/SuList. Candidate `31015`
  corrects primary-group precedence, compressed-image error handling, Samsung trailer preservation,
  AVB2 descriptor preservation, ARM32 payload detection/relocation and module filename controls.
  Unreleased upstream feature and UI rewrites are outside this qualification candidate.
- The maintained manager now uses `io.github.jordan231111.magisk`; the home page retains its
  existing layout and contributors, with Jordan231111 as the fork owner's name and GitHub link.
  [Namespace migration](build-info.md#pr15-namespace-migration) requires an explicit installation
  transition. MuMu also required its own per-app bootstrap-root grant for the newly installed package.
  The same-package `31011` to `31012` System Mode upgrade preserved the test sentinel and module whiteout.
- Concurrent update clients can share a newly created state directory. Losing the `mkdirs()` race
  no longer reports a false storage error; the existing `lstat` check still rejects redirected paths.
  Android instrumentation exercises repeated concurrent first-use construction.
- Pre-init budget parsing uses its own field separator. ViPER's installer leaves `IFS` set to
  newline; inherited parsing incorrectly treated its 790-byte policy and entry count as one
  integer, then triggered the existing safety fallback. The new parser accepts that valid input
  while retaining the same size/count limits and rejecting an oversized sparse policy. Candidate
  `31013` passes the paired ViPER AVD check and the [MuMu lifecycle](device-pr15/mumu-31013-lifecycle.json),
  including removal and original-image restoration. Earlier records retain their exact artifact IDs.
- Manager package lookup tolerates unrelated directories removed during Android package migration.
  The previous traversal could abort during original-manager removal and clear the hidden manager's
  registration. A failed scan now preserves that registration without authorizing an unverified app;
  the certificate and dynamic-APK checks remain required. The host regression reproduces the old
  `ENOENT` failure and checks the repaired lookup, package-prefix bounds and other I/O errors.
- AVB1 ECDSA now uses Android's DER encoding, following
  [upstream 87e72a582](https://github.com/topjohnwu/Magisk/commit/87e72a582e019ae1bb3e65c90c259e994ecd66fa).
  Earlier raw `r || s` EC signatures were not Android-compatible. Repatch and re-sign the matching
  original image; do not treat an old MagiskBoot self-verification result as bootloader acceptance.
  The image algorithm now comes from its signing key rather than the certificate issuer's digest.
  Mismatched keys/certificates and unsupported signature versions or algorithms fail before writing.
- Restore the exact historical Vivo `do_mount_check` encoded `/system` replacement. Matching bytes
  are required; this is not a manufacturer-name bypass. Samsung PROCA remains an independent patch.
- Live setup discovers bootstrap `su` through PATH and uses its command interface. A missing
  `/system/xbin/su` must not prevent a rooted emulator with `/system/bin/su` from being tested.
  An elevated worker reports completion independently of the bootstrap SU connection, since
  replacing that daemon can close its own caller's socket. Bootstrap denial and worker failure
  remain failures; an overdue worker retains its diagnostic directory. The
  [live-setup record](device-pr15/live-setup.json) covers stock cold boot, reinjection, the full
  release suite and an ordinary-shell PATH bootstrap followed by the API v5/root stress checks.
- Select-and-Patch on managed System Mode uses a separate workspace and cleans it after success
  or failure. A subsequent boot must not import file-patching tools over the transaction-owned
  runtime. The daemon also preserves that runtime when an old ordinary update inbox remains.
  A previously damaged installation still requires its verified recovery/restore path.
- System Mode snapshots preserve module whiteouts (character device `0:0`) and module symlinks.
  The same rules cover restore and rollback cleanup. FIFOs, sockets, other device nodes and
  whiteouts outside module content remain unsupported; they are never opened to calculate a hash.
- SU consent launches allow up to fifteen seconds per framework-start attempt, within the existing
  seventy-second request deadline. A launch never grants consent; stalled children are killed and
  reaped, and the authenticated response is still required. Cuttlefish exposed the earlier three-second
  cutoff killing ART before ActivityManager received the request.
- Normal zygote SELinux-domain authentication remains authoritative. On a permissive image whose
  init and peer both remain in the kernel domain, the fallback requires UID 0, four root UID fields,
  a system `app_process` image and verified init-owned zygote ancestry. Pre-specialization fork and
  USAP children must run the same image as their root zygote parent. Non-root peers, wrong images,
  unrelated ancestry, enforcing mode and unreadable/malformed state fail. BlueStacks exercises this
  unusual **permissive** case; it does not prove SELinux-disabled or Waydroid coverage.
- Managed Direct-System remains an explicit, authorized debug capability. Recovery ZIP
  `SYSTEMMODE` and automatic System Mode `addon.d` replay are not supported: recovery lacks the
  live target/host recovery authorization, and an OTA changes the bound image. Use normal image
  patching where available, or restore/requalify the changed writable image before reinstalling.
  Ordinary Magisk recovery and ordinary `addon.d` remain separate inherited routes.
- Retire the historical Android 6/API 23–24 System Mode availability claim. The maintained
  transaction requires API 25 or later and the exact target qualification; ordinary Android 6
  boot-image installation remains covered by its separate CI lanes. Legacy System Mode users
  need the matching legacy uninstall/recovery procedure and an ordinary installation on that OS.
- Physical OEM boot, encrypted pre-init storage, A/B OTA, hardware recovery and GrapheneOS device
  claims require actual matching devices. No available emulator result clears these release gates.
  Retain the implementation and existing historical line; do not remove useful compatibility
  code merely because hardware is unavailable.

## Retained CI investigation

[Run 39015915833](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39015915833)
timed out in Cuttlefish's hidden-manager application-PATH root check after the native SU request
was granted. The last child diagnostic was namespace setup; the existing logs do not identify
which later operation stopped progressing. This is not claimed as a fixed runtime bug or dismissed
as an emulator fault. Two complete subsequent Cuttlefish attempts in
[run 39019753847](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39019753847) passed,
including normal/hidden manager checks and Direct Install. Their exact boot records are linked
from the compatibility table. Cuttlefish timeouts now collect bounded native worker stacks and
syscall state before teardown, without reading process environments or arguments. A recurrence
still fails the test; no timeout or acceptance condition was relaxed.

[Run 39024117895](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39024117895) passed
Cuttlefish but exposed the package-removal race on API 36.1. API 29/x86 also failed to observe a
consent dialog; its next run retains the window hierarchy on failure. API 23/x86_64 completed the
app suites but failed the native-crash gate on a SurfaceFlinger `eglMakeCurrent` crash. Stock
framework-restart controls now include that image; the crash has not been exempted. A local ARM64
API 36.1 run passed hidden-manager tests, then the restored manager's final test process crashed;
that attempt remains failed. Corrected emulator log filtering and bounded failure log capture
retain evidence for the next run. Candidate `31014` requires fresh runtime acceptance.

The Android 6 x86/x86_64 stock controls in
[run 39048129575](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39048129575) and
[run 39051364678](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39051364678)
failed a framework-only stop/start before any Magisk payload was installed. Waiting for init
to reap the old services fixed the observed shutdown/start race, but the restarted stock
framework still did not complete boot on emulator 37.3.4. Those targets retain four stock
**cold-boot** controls and the full patched-image suites; that warm-restart configuration is unqualified.
The native-crash gate on tested Magisk boots remains unchanged. API 29/x86's consent failure
in the first run was obscured by a Quickstep ANR dialog; subsequent failures also retain Android's
ANR stacks rather than dismissing the dialog. API 27/x86 exhausted that run's time limit after
a slow SDK image download, so downloads now have a separate bounded step from device tests.

The latter run's API 25/x86 timeout was a guest-kernel panic in
`goldfish_pipe_dma_clear_lock`, called from `goldfish_interrupt_task`; all ten consent requests
had been denied before the guest stopped responding. The legacy CI lanes now disable the
emulator's optional `GLDMA`/`GLDMA2` features, using its ordinary graphics-copy path. This is
an emulator configuration, not a Magisk or phone-kernel patch. API 24/25 x86 and x86_64 passed
their full suites in [run 39055905296](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/39055905296).
The API 23 stock warm restart still timed out with DMA disabled, so its current qualification
uses four stock cold boots followed by the full patched-image suites. The
[emulator feature mapping](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/android-emu/android/opengles.cpp)
and [Goldfish driver](https://android.googlesource.com/kernel/goldfish-modules/+/ca47ac740d16ecf731be3fecdd051d26932f9bdd/goldfish_pipe_v2.c)
describe the affected transport.

That run's Android 17/API 37.0 16 KiB preview completed the app suites but failed the native-crash
gate: an `app_process` consent launcher aborted during ART `DestroyJavaVM` with an invalid
`pthread_join` handle. This is not attributed to the emulator without a matching control.
The preview lanes now run fifty stock `app_process` AM startup/shutdown checks before installing
Magisk and retain those results. Their native-crash gate remains active.
