"""Candidate-specific lower bound for the persistent System Mode payload."""

from __future__ import annotations

import io
from pathlib import Path
import zipfile

from .authorization import stable_regular_file


PAYLOAD_ASSETS = (
    "stub.apk", "util_functions.sh", "boot_patch.sh", "addon.d.sh",
    "app_functions.sh", "uninstaller.sh", "module_installer.sh",
    "kitsune_system_install.sh", "kitsune_system_launcher.sh", "kitsune_system_rescue.sh",
    "system_mode_transaction.sh", "system_mode_verify.sh",
)
PAYLOAD_BINARIES = ("busybox", "magisk", "magiskboot", "magiskinit", "magiskpolicy")
COMPANION = {"arm64-v8a": "armeabi-v7a", "x86_64": "x86"}


def persistent_payload_bytes(path: Path, abis: list[str], expected_sha256: str) -> int:
    """Count the exact APK, ABI payload and separate invariant rescue payload.

    Filesystem allocation and policy/journal overhead can require more space.
    This is a lower bound, not a waiver of transactional ENOSPC handling.
    """

    abi = abis[0] if abis else ""
    if abi not in {"armeabi-v7a", "arm64-v8a", "x86", "x86_64"}:
        raise ValueError("unsupported System Mode payload ABI")
    identity, data = stable_regular_file(path, purpose="System Mode space estimate", capture=True)
    if identity["sha256"] != expected_sha256 or data is None:
        raise ValueError("candidate APK changed before space estimation")
    payload = [f"assets/{name}" for name in PAYLOAD_ASSETS]
    payload += [f"lib/{abi}/lib{name}.so" for name in PAYLOAD_BINARIES]
    if COMPANION.get(abi) in abis:
        payload.append(f"lib/{COMPANION[abi]}/libmagisk.so")
    rescue = [f"lib/{abi}/libbusybox.so", "assets/system_mode_transaction.sh",
              "assets/kitsune_system_rescue.sh"]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if any(names.count(name) != 1 for name in set(payload + rescue)):
                raise ValueError("candidate has missing or duplicate System Mode payload files")
            return len(data) + sum(archive.getinfo(name).file_size for name in payload + rescue)
    except zipfile.BadZipFile as exc:
        raise ValueError("System Mode space estimate requires a valid APK") from exc
