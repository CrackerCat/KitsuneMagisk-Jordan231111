from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.system_mode.authorization import stable_regular_file
from tools.system_mode.host_identity import mumu_identity
from tools.system_mode.qualification import qualify_target, verify_instance_identity
from tools.system_mode.schema_validation import SchemaValidationError, validate_schema_instance


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "host evidence requires POSIX no-follow APIs")
class MuMuIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="kitsune-mumu-identity-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.path = self.root / "vms/MuMuPlayerGlobal-12.0-2/MuMuPlayerGlobal-12.0-2.nemu"
        self.path.parent.mkdir(parents=True)
        self.config = self.path.parent / "configs/vm_config.json"
        self.config.parent.mkdir()
        self.controller = self.root / "nx_main/MuMuManager.exe"
        self.controller.parent.mkdir()
        self.controller.write_bytes(b"vendor controller fixture")
        self.base = self.root / "nx_device/12.0/vms/MuMuPlayerGlobal-12.0-base/system.vdi"
        self.base.parent.mkdir(parents=True)
        self.base.write_bytes(b"immutable shared base fixture")
        for name in ("system-diff.vdi", "ota.vdi", "data.vdi"):
            (self.path.parent / name).write_bytes(b"private disk fixture")
        self.mac = self.path.parent / "macaddress"
        self.mac.write_text("001122334455")
        self.settings = {"vm": {
            "system_vdi": {"sharable": "Writable"}, "root": "true",
            "phone": dict(imei="123456789012345", vdid="fixture-device", brand="Asus",
                          model="AI2501", manufacturer="Asus", code="AI2501"),
            "nat": {"port_forward": {"adb": {"host_port": "16448"}}},
        }}
        self.config.write_text(json.dumps(self.settings))
        self.xml = f'''<VirtualBox xmlns="http://www.virtualbox.org/">
<Machine uuid="{{1c107147-c0a3-cf56-1000-000000000002}}" name="MuMuPlayerGlobal-12.0-2">
<MediaRegistry><HardDisks>
<HardDisk uuid="{{1c107147-c0a3-cf56-0000-100000000000}}" location="{self.base}" format="VDI" type="Readonly">
<HardDisk uuid="{{1c107147-c0a3-cf56-0000-000000000002}}" location="system-diff.vdi" format="VDI"/>
</HardDisk>
<HardDisk uuid="{{1c107147-c0a3-cf56-0001-000000000002}}" location="ota.vdi" format="VDI" type="Normal"/>
<HardDisk uuid="{{1c107147-c0a3-cf56-0002-000000000002}}" location="data.vdi" format="VDI" type="Normal"/>
</HardDisks></MediaRegistry><Hardware>
<Network><Adapter enabled="true" MACAddress="001122334455"><NAT>
<Forwarding name="ADB_PORT" proto="1" hostip="127.0.0.1" hostport="16448" guestport="5555"/>
</NAT></Adapter></Network>
<StorageControllers><StorageController>
<AttachedDevice port="0" device="0"><Image uuid="{{1c107147-c0a3-cf56-0000-000000000002}}"/></AttachedDevice>
<AttachedDevice port="1" device="0"><Image uuid="{{1c107147-c0a3-cf56-0001-000000000002}}"/></AttachedDevice>
<AttachedDevice port="2" device="0"><Image uuid="{{1c107147-c0a3-cf56-0002-000000000002}}"/></AttachedDevice>
</StorageController></StorageControllers></Hardware></Machine></VirtualBox>'''
        self.path.write_text(self.xml)

    def test_boot_rewrites_and_vendor_root_switch_keep_identity(self) -> None:
        expected = mumu_identity(self.path)
        replacement = self.path.with_suffix(".new")
        replacement.write_text(self.xml.replace("<Machine ", '<Machine lastStateChange="later" '))
        replacement.replace(self.path)
        self.mac.write_text("001122334455")
        self.settings["vm"]["root"] = "false"
        self.settings["android"] = {"startup": {"recent_launch_durations_ms": "5000"}}
        self.config.write_text(json.dumps(self.settings))
        self.assertEqual(expected, mumu_identity(self.path))
        verify_instance_identity(expected)

    def test_controller_base_and_hardware_changes_invalidate_identity(self) -> None:
        expected = mumu_identity(self.path)
        for path in (self.controller, self.base):
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "identity changed"):
                verify_instance_identity(expected)
            path.write_bytes(original)
        self.settings["vm"]["phone"]["imei"] = "543210987654321"
        self.config.write_text(json.dumps(self.settings))
        with self.assertRaisesRegex(ValueError, "identity changed"):
            verify_instance_identity(expected)

    def test_foreign_chain_attachment_network_and_entities_are_rejected(self) -> None:
        for old, new in (
            ('name="MuMuPlayerGlobal-12.0-2"', 'name="MuMuPlayerGlobal-15.0-2"'),
            ('location="data.vdi"', 'location="../MuMuPlayerGlobal-12.0-1/data.vdi"'),
            ('type="Readonly"', 'type="Normal"'),
            ('port="2"', 'port="1"'), ('hostport="16448"', 'hostport="16416"'),
            ('hostip="127.0.0.1"', 'hostip="0.0.0.0"'),
            ('MACAddress="001122334455"', 'MACAddress="554433221100"'),
            ('<VirtualBox ', '<!DOCTYPE VirtualBox [<!ENTITY x "bad">]><VirtualBox '),
        ):
            self.path.write_text(self.xml.replace(old, new))
            with self.subTest(old=old), self.assertRaises(ValueError):
                mumu_identity(self.path)

    def test_android_15_redirected_files_and_read_only_settings_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Android 12"):
            mumu_identity(self.root / "vms/MuMuPlayerGlobal-15.0-0/MuMuPlayerGlobal-15.0-0.nemu")
        disk = self.path.parent / "data.vdi"
        disk.unlink()
        disk.symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, "redirected"):
            mumu_identity(self.path)
        disk.unlink()
        disk.write_bytes(b"disk")
        self.settings["vm"]["system_vdi"]["sharable"] = "Readonly"
        self.config.write_text(json.dumps(self.settings))
        with self.assertRaisesRegex(ValueError, "writable"):
            mumu_identity(self.path)

    def test_metadata_replacement_during_capture_is_rejected(self) -> None:
        def capture(path, **kwargs):
            result = stable_regular_file(path, **kwargs)
            if path == self.controller:
                self.mac.write_text("554433221100")
            return result
        with mock.patch("tools.system_mode.host_identity.stable_regular_file", side_effect=capture):
            with self.assertRaisesRegex(ValueError, "changed while"):
                mumu_identity(self.path)

    def test_schema_requires_complete_identity_without_mixed_fields(self) -> None:
        schema = json.loads((ROOT / "tools/system_mode/schemas/qualification-v1.schema.json").read_text())
        identity = mumu_identity(self.path)
        validate_schema_instance(identity, schema["properties"]["instance_identity"], root_schema=schema)
        for key in identity:
            incomplete = copy.deepcopy(identity)
            del incomplete[key]
            with self.subTest(key=key), self.assertRaises(SchemaValidationError):
                validate_schema_instance(incomplete, schema["properties"]["instance_identity"], root_schema=schema)
        with self.assertRaises(SchemaValidationError):
            validate_schema_instance(dict(identity, inode=1), schema["properties"]["instance_identity"], root_schema=schema)

    def test_wrong_adb_instance_is_rejected_before_any_guest_probe(self) -> None:
        client = mock.Mock()
        client.resolve_serial.return_value = "127.0.0.1:16416"
        command = self.root / "lifecycle"
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o700)
        with mock.patch("tools.system_mode.qualification.collect_report") as probe:
            with self.assertRaisesRegex(ValueError, "selected MuMu"):
                qualify_target(
                    client, output=self.root / "qualification.json",
                    backup_location=self.root / "backup", snapshot_id="fixture",
                    backup_command=f"{command} {{backup}}", restore_command=f"{command} {{backup}}",
                    cold_boot_command=str(command), instance_identity_path=self.path,
                    instance_kind="mumu-v1", seal_key_path=self.root / "key",
                )
            probe.assert_not_called()
