from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from tools.system_mode.host_identity import mumu_macos_identity
from tools.system_mode.qualification import verify_instance_identity
from tools.system_mode.schema_validation import validate_schema_instance


@unittest.skipUnless(os.name == "posix", "host evidence requires POSIX no-follow APIs")
class MuMuMacIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bundle = self.root / "bundles/mumu_1_20261014_155856.gmad"
        self.path = self.bundle / "setting/vm.json"
        self.path.parent.mkdir(parents=True)
        self.settings = dict(macAddress="001122334455", phonePropIMEI="123456789012345",
                             phonePropMiit="fixture", phonePropBrand="test", phonePropModel="test",
                             simulationProps={}, vmName="Android Device-1", vmDeviceType=0,
                             vmCpuCount=6, vmMemoryOfMB=12288, systemFilePermissionType=1,
                             vmRootEnable=True, customAdbPort=0, adbPort=26656)
        self.write_settings()
        (self.bundle / "config.json").write_text('{"app_version":"1.9.2"}')
        self.app = self.root / "MuMuPlayer Pro.app"
        self.controller = self.app / "Contents/MacOS/mumutool"
        engine = self.app / "Contents/MacOS/MuMu Android Device.app/Contents/MacOS/MuMu Android Device"
        engine.parent.mkdir(parents=True)
        self.controller.write_bytes(b"vendor-controller")
        engine.write_bytes(b"vendor-engine")
        self.patch = mock.patch("tools.system_mode.host_identity.MUMU_MAC_APP", self.app)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.header = bytearray(104)
        struct.pack_into(">IIQIIQI", self.header, 0, 0x514649fb, 3, 0, 0, 16, 2**31, 0)
        struct.pack_into(">II", self.header, 96, 4, 104)
        for name in ("system.qcow2", "data.qcow2"):
            (self.bundle / name).write_bytes(self.header)

    def write_settings(self):
        replacement = self.path.with_suffix(".new")
        replacement.write_text(json.dumps(self.settings))
        replacement.replace(self.path)

    def test_boot_rewrites_ports_and_root_switch_preserve_identity(self):
        identity = mumu_macos_identity(self.path)
        self.settings.update(adbPort=26657, frontendPort=12345, vmRootEnable=False,
                             lastWindowFrameForLandscape="changed")
        self.write_settings()
        version = self.bundle / "config.json"
        version.unlink()
        version.write_text('{"app_version":"1.9.2"}')
        disk = self.bundle / "system.qcow2"
        disk.unlink()
        disk.write_bytes(self.header)
        self.assertEqual(identity, mumu_macos_identity(self.path))
        verify_instance_identity(identity)
        schema = Path(__file__).resolve().parents[2] / "tools/system_mode/schemas/qualification-v1.schema.json"
        definition = json.loads(schema.read_text())["$defs"]["mumuMacIdentity"]
        validate_schema_instance(identity, definition)

    def test_hardware_controller_and_layout_changes_invalidate_identity(self):
        identity = mumu_macos_identity(self.path)
        for key, value in (("phonePropIMEI", "543210987654321"), ("vmMemoryOfMB", 8192)):
            old = self.settings[key]
            self.settings[key] = value
            self.write_settings()
            self.assertNotEqual(identity, mumu_macos_identity(self.path))
            self.settings[key] = old
        self.write_settings()
        self.controller.write_bytes(b"new-controller")
        self.assertNotEqual(identity, mumu_macos_identity(self.path))

    def test_custom_port_is_bound(self):
        self.settings.update(customAdbPort=37731, adbPort=37731)
        self.write_settings()
        identity = mumu_macos_identity(self.path)
        self.assertEqual([37731], identity["adb_ports"])
        self.settings["adbPort"] = 26656
        self.write_settings()
        self.assertEqual(identity, mumu_macos_identity(self.path))
        self.settings["customAdbPort"] = 37732
        self.write_settings()
        self.assertNotEqual(identity, mumu_macos_identity(self.path))

    def test_disk_replacement_during_header_read_is_rejected(self):
        disk = self.bundle / "system.qcow2"
        pread = os.pread

        def replace(fd, size, offset):
            data = pread(fd, size, offset)
            replacement = disk.with_suffix(".new")
            replacement.write_bytes(self.header)
            replacement.replace(disk)
            return data

        with mock.patch("tools.system_mode.host_identity.os.pread", side_effect=replace):
            with self.assertRaises(ValueError):
                mumu_macos_identity(self.path)

    def test_shared_redirected_truncated_and_external_disks_are_refused(self):
        disk = self.bundle / "system.qcow2"
        for offset, fmt, value in ((8, ">Q", 128), (16, ">I", 3), (32, ">I", 1),
                                   (60, ">I", 1), (72, ">Q", 2), (72, ">Q", 4)):
            header = bytearray(self.header)
            struct.pack_into(fmt, header, offset, value)
            disk.write_bytes(header)
            with self.assertRaises(ValueError):
                mumu_macos_identity(self.path)
        disk.write_bytes(b"QFI")
        with self.assertRaises(ValueError):
            mumu_macos_identity(self.path)
        disk.unlink()
        disk.symlink_to(self.bundle / "data.qcow2")
        with self.assertRaises(ValueError):
            mumu_macos_identity(self.path)
        disk.unlink()
        os.link(self.bundle / "data.qcow2", disk)
        with self.assertRaises(ValueError):
            mumu_macos_identity(self.path)

    def test_wrong_transport_readonly_and_duplicate_metadata_are_refused(self):
        for key, value in (("adbPort", 26624), ("customAdbPort", True),
                           ("systemFilePermissionType", 0), ("systemFilePermissionType", True)):
            old = self.settings[key]
            self.settings[key] = value
            self.write_settings()
            with self.assertRaises(ValueError):
                mumu_macos_identity(self.path)
            self.settings[key] = old
        self.path.write_text('{"adbPort":26656,"adbPort":26657}')
        with self.assertRaises(ValueError):
            mumu_macos_identity(self.path)
