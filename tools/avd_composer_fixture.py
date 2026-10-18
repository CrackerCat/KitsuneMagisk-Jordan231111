#!/usr/bin/env python3
"""Backport AOSP's composer restart rule in one disposable API28 SDK image.

This is a lab image fixture, never an installer or a production-device patch.
Equal-length replacement leaves the partition table and filesystem metadata
unchanged. A guest-side read verifies the actual init file on every cold boot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
from pathlib import Path
import shutil
import stat
import subprocess
import uuid

VENDOR_SHA256 = "543ce1633b00d48d728bc039555e835304f1d4c9966a8daa2d174fa1f0bbf9bf"
RC_PATH = "/vendor/etc/init/android.hardware.graphics.composer@2.1-service.rc"
UPSTREAM = ("https://android.googlesource.com/platform/hardware/interfaces/+/"
            "android-10.0.0_r1/graphics/composer/2.1/default/"
            "android.hardware.graphics.composer@2.1-service.rc")
OLD_RC = b"""service vendor.hwcomposer-2-1 /vendor/bin/hw/android.hardware.graphics.composer@2.1-service
    class hal animation
    user system
    group graphics drmrpc
    capabilities SYS_NICE
    writepid /dev/cpuset/system-background/tasks

# Restart HWC when SurfaceFlinger stops. This turns off the display and prpares
# a new HWC instance for when SurfaceFlinger gets started again
on property:init.svc.surfaceflinger=stopped
    restart vendor.hwcomposer-2-1
"""
NEW_RC = b"""service vendor.hwcomposer-2-1 /vendor/bin/hw/android.hardware.graphics.composer@2.1-service
    class hal animation
    user system
    group graphics drmrpc
    capabilities SYS_NICE
    onrestart restart surfaceflinger
    writepid /dev/cpuset/system-background/tasks
"""
# Keep the original inode size and data-block allocation, including its label.
PATCHED_RC = NEW_RC + b"#" + b" " * (len(OLD_RC) - len(NEW_RC) - 2) + b"\n"
RC_SHA256 = hashlib.sha256(PATCHED_RC).hexdigest()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def create(source: Path, output: Path, record: Path) -> None:
    if len({p.resolve() for p in (source, output, record)}) != 3:
        raise ValueError("fixture input, output and record must be different paths")
    if source.is_symlink() or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("fixture input must be a regular SDK image")
    if output.exists() or output.is_symlink() or record.exists() or record.is_symlink():
        raise ValueError("refusing to replace an existing fixture or record")
    if digest(source) != VENDOR_SHA256:
        raise ValueError("SDK vendor image changed; review and requalify the fixture")

    created = False
    try:
        with source.open("rb") as src, output.open("xb") as dst:
            created = True
            shutil.copyfileobj(src, dst)
        if digest(output) != VENDOR_SHA256:
            raise ValueError("SDK image changed while copying")
        with output.open("r+b") as stream, mmap.mmap(stream.fileno(), 0) as image:
            offset = image.find(OLD_RC)
            if offset < 0 or offset % 4096 or image.find(OLD_RC, offset + 1) >= 0:
                raise ValueError("expected one block-aligned composer init file")
            image[offset:offset + len(OLD_RC)] = PATCHED_RC
            image.flush()
        if digest(source) != VENDOR_SHA256:
            raise ValueError("installed SDK input changed during fixture preparation")
        report = {
            "schema": 1,
            "scope": "Disposable API28 Google APIs x86_64 vendor fixture; no stock-image or phone qualification",
            "sdk_package": "system-images;android-28;google_apis;x86_64",
            "sdk_revision": 11,
            "upstream_rule": UPSTREAM,
            "original_vendor_sha256": VENDOR_SHA256,
            "fixture_vendor_sha256": digest(output),
            "image_size": output.stat().st_size,
            "changed_offset": offset,
            "changed_length": len(OLD_RC),
            "guest_rc_path": RC_PATH,
            "guest_rc_sha256": RC_SHA256,
            "verified_boots": [],
        }
        record.parent.mkdir(parents=True, exist_ok=True)
        with record.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise


def verify_guest(record: Path, adb: str, serial: str, boot_id: str) -> None:
    report = json.loads(record.read_text())
    if report.get("schema") != 1 or report.get("original_vendor_sha256") != VENDOR_SHA256 \
            or report.get("guest_rc_sha256") != RC_SHA256:
        raise ValueError("unrecognized composer fixture record")
    command = [adb, "-s", serial, "exec-out", "cat"]
    actual_boot = subprocess.check_output(command + ["/proc/sys/kernel/random/boot_id"],
                                          timeout=20).decode().strip()
    if str(uuid.UUID(actual_boot)) != boot_id or boot_id in report["verified_boots"]:
        raise ValueError("fixture verification requires the current new cold boot")
    observed = subprocess.check_output(command + [RC_PATH], timeout=20)
    if observed != PATCHED_RC:
        record.with_name("api28-composer-observed.rc").write_bytes(observed)
        record.with_name("api28-composer-mismatch.json").write_text(json.dumps({
            "boot_id": boot_id,
            "expected_sha256": RC_SHA256,
            "observed_sha256": hashlib.sha256(observed).hexdigest(),
            "observed_length": len(observed),
            "matches_unmodified_sdk_file": observed == OLD_RC,
        }, indent=2) + "\n")
        raise ValueError("guest did not load the expected composer fixture")
    report["verified_boots"].append(boot_id)
    temporary = record.with_suffix(".tmp")
    with temporary.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    temporary.replace(record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    patch = commands.add_parser("create")
    patch.add_argument("--input", required=True, type=Path)
    patch.add_argument("--output", required=True, type=Path)
    patch.add_argument("--record", required=True, type=Path)
    verify = commands.add_parser("verify-guest")
    verify.add_argument("--record", required=True, type=Path)
    verify.add_argument("--adb", default="adb")
    verify.add_argument("--serial", required=True)
    verify.add_argument("--boot-id", required=True)
    args = parser.parse_args()
    if args.command == "create":
        create(args.input, args.output, args.record)
    else:
        verify_guest(args.record, args.adb, args.serial, args.boot_id)


if __name__ == "__main__":
    main()
