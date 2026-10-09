from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.system_mode.artifact_space import (
    PAYLOAD_ASSETS, PAYLOAD_BINARIES, persistent_payload_bytes,
)


@unittest.skipUnless(os.name == "posix", "host evidence requires POSIX no-follow APIs")
class ArtifactSpaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="kitsune-artifact-space-")
        self.addCleanup(self.directory.cleanup)
        self.apk = Path(self.directory.name).resolve() / "candidate.apk"
        with zipfile.ZipFile(self.apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in PAYLOAD_ASSETS:
                archive.writestr(f"assets/{name}", b"script\n")
            for name in PAYLOAD_BINARIES:
                archive.writestr(f"lib/x86_64/lib{name}.so", bytes(1024 * 1024))
            archive.writestr("lib/x86/libmagisk.so", bytes(512 * 1024))
        self.digest = hashlib.sha256(self.apk.read_bytes()).hexdigest()

    def test_compressed_apk_and_separate_rescue_copies_are_both_accounted_for(self) -> None:
        required = persistent_payload_bytes(self.apk, ["x86_64", "x86"], self.digest)
        # Five native files plus the separate rescue BusyBox already exceed
        # six MiB, although these compress to a much smaller APK.
        self.assertGreater(required, 6 * 1024 * 1024 + self.apk.stat().st_size)
        self.assertEqual(512 * 1024, required - persistent_payload_bytes(self.apk, ["x86_64"], self.digest))

    def test_artifact_replacement_unknown_abi_and_missing_payload_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "changed"):
            persistent_payload_bytes(self.apk, ["x86_64"], "0" * 64)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            persistent_payload_bytes(self.apk, ["unknown"], self.digest)
        with self.assertRaisesRegex(ValueError, "missing or duplicate"):
            persistent_payload_bytes(self.apk, ["arm64-v8a"], self.digest)

    def test_duplicate_payload_member_cannot_hide_additional_space(self) -> None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.apk, "a") as archive:
                archive.writestr("assets/stub.apk", bytes(1024))
        digest = hashlib.sha256(self.apk.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "missing or duplicate"):
            persistent_payload_bytes(self.apk, ["x86_64"], digest)
