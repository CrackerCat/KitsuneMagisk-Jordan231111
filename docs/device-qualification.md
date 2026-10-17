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

## Reproducing the checks

Use the repository environment wrapper and a disposable SDK device. `scripts/avd.sh test API TYPE`
patches a copy of the SDK ramdisk, runs debug and release setup, closes and restarts the owned
emulator process, and exercises SU, modules, Hide/SuList, provider, manager migration and recovery.
`MAGISK_AVD_DEVICE` selects an installed hardware profile; `MAGISK_AVD_NAME` and
`MAGISK_AVD_PORT` isolate the instance. `AVD_QUALIFICATION_DIR` retains exact guest/boot records.
Set `AVD_BOOT_FIXTURES=1` to run the APK's MagiskBoot tests. No shared SDK ramdisk is overwritten.

`scripts/env.py python3 tools/boot_qualification.py --serial SERIAL --apk APK --output REPORT`
tests boot headers v0–v4, init_boot, vendor_boot v3/v4, original-init restoration, unchanged kernels,
Vivo and Samsung patch signatures, and compressed-kernel `split -n`. OpenSSL independently signs
and verifies RSA/P-256/P-384/P-521 AVB1 records; tampered and nonstandard raw EC signatures fail.
Temporary private keys and guest fixture files are removed. These fixtures do not boot OEM kernels.

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
- Physical OEM boot, encrypted pre-init storage, A/B OTA, hardware recovery and GrapheneOS device
  claims require actual matching devices. No available emulator result clears these release gates.
  Retain the implementation and existing historical line; do not remove useful compatibility
  code merely because hardware is unavailable.
