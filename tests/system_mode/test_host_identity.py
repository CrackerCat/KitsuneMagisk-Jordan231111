from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.system_mode.host_identity import ldplayer_identity, ldplayer_serials
from tools.system_mode.authorization import stable_regular_file
from tools.system_mode.doctor import _probe_digest
from tools.system_mode.qualification import instance_identity, qualify_target, verify_instance_identity
from tools.system_mode.schema_validation import SchemaValidationError, validate_schema_instance


ROOT = Path(__file__).resolve().parents[2]
XML = '''<?xml version="1.0" encoding="utf-8"?>
<VirtualBox xmlns="http://www.virtualbox.org/">
  <Machine uuid="{20160302-aaaa-aaaa-3713-000000000001}" name="leidian1">
    <MediaRegistry><HardDisks>
      <HardDisk uuid="{20160302-cccc-cccc-3713-000000000001}" location="data.vdi" format="VDI" type="Normal"/>
    </HardDisks></MediaRegistry>
    <StorageControllers><StorageController name="VirtIO" type="VirtioSCSI">
      <AttachedDevice port="1" device="0"><Image uuid="{20160302-cccc-cccc-3713-000000000001}"/></AttachedDevice>
    </StorageController></StorageControllers>
  </Machine>
</VirtualBox>
'''


@unittest.skipUnless(os.name == "posix", "host evidence requires POSIX no-follow APIs")
class LDPlayerIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="kitsune-ldplayer-identity-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.path = self.root / "vms/leidian1/leidian.vbox"
        self.path.parent.mkdir(parents=True)
        self.config = self.root / "vms/config/leidian1.config"
        self.config.parent.mkdir()
        self.controller = self.root / "ldconsole.exe"
        self.controller.write_bytes(b"vendor controller fixture")
        self.path.write_text(XML, encoding="utf-8")
        self.settings = {
            "propertySettings.phoneAndroidId": "0123456789abcdef",
            "propertySettings.phoneIMEI": "123456789012345",
            "propertySettings.macAddress": "001122334455",
            "basicSettings.standaloneSysVmdk": True,
            "basicSettings.rootMode": True,
            "basicSettings.left": 0,
        }
        self.write_settings()
        for name in ("system.vdi", "data.vdi", "sdcard.vdi"):
            (self.path.parent / name).write_bytes(b"private disk fixture")

    def write_settings(self) -> None:
        self.config.write_text(json.dumps(self.settings), encoding="utf-8")

    def test_vendor_rewrite_and_restore_preserve_semantic_identity(self) -> None:
        expected = ldplayer_identity(self.path)
        original_file = instance_identity(self.path)
        replacement = self.path.with_suffix(".new")
        replacement.write_text(XML.replace("<Machine ", "<!-- vendor rewrite -->\n  <Machine "), encoding="utf-8")
        replacement.replace(self.path)
        self.settings["basicSettings.left"] = 200
        self.write_settings()
        self.assertEqual(expected, ldplayer_identity(self.path))
        verify_instance_identity(expected)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            verify_instance_identity(original_file)
        self.assertEqual({"127.0.0.1:5557", "emulator-5556"}, ldplayer_serials(expected))

    def test_recreated_instance_hardware_controller_and_disk_registry_are_bound(self) -> None:
        expected = ldplayer_identity(self.path)
        self.settings["propertySettings.phoneAndroidId"] = "fedcba9876543210"
        self.write_settings()
        with self.assertRaisesRegex(ValueError, "identity changed"):
            verify_instance_identity(expected)
        self.settings["propertySettings.phoneAndroidId"] = "0123456789abcdef"
        self.write_settings()
        self.controller.write_bytes(b"updated controller")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            verify_instance_identity(expected)
        self.controller.write_bytes(b"vendor controller fixture")
        self.path.write_text(XML.replace("cccc-cccc", "dddd-dddd"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            verify_instance_identity(expected)

    def test_shared_disks_missing_identifiers_and_duplicate_keys_are_rejected(self) -> None:
        self.settings["basicSettings.standaloneSysVmdk"] = False
        self.write_settings()
        with self.assertRaisesRegex(ValueError, "private writable"):
            ldplayer_identity(self.path)
        self.settings["basicSettings.standaloneSysVmdk"] = True
        del self.settings["propertySettings.phoneAndroidId"]
        self.write_settings()
        with self.assertRaisesRegex(ValueError, "lacks phoneAndroidId"):
            ldplayer_identity(self.path)
        self.config.write_text('{"basicSettings.standaloneSysVmdk":true,"basicSettings.standaloneSysVmdk":false}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ldplayer_identity(self.path)

    def test_foreign_machine_backing_chain_and_entities_fail(self) -> None:
        for xml in (
            XML.replace('name="leidian1"', 'name="leidian2"'),
            XML.replace('location="data.vdi"', 'location="../leidian0/data.vdi"'),
            XML.replace('type="Normal"', 'type="Readonly"'),
            XML.replace('<VirtualBox ', '<!DOCTYPE VirtualBox [<!ENTITY x "bad">]><VirtualBox '),
            XML.replace('port="1"', 'port="0"'),
        ):
            with self.subTest(xml=xml):
                self.path.write_text(xml, encoding="utf-8")
                with self.assertRaises(ValueError):
                    ldplayer_identity(self.path)

    def test_redirected_metadata_and_private_disks_fail(self) -> None:
        original = self.path.read_bytes()
        foreign = self.root / "foreign.vbox"
        foreign.write_bytes(original)
        self.path.unlink()
        self.path.symlink_to(foreign)
        with self.assertRaises(ValueError):
            ldplayer_identity(self.path)
        self.path.unlink()
        self.path.write_bytes(original)
        disk = self.path.parent / "system.vdi"
        disk.unlink()
        disk.symlink_to(self.path.parent / "data.vdi")
        with self.assertRaisesRegex(ValueError, "redirected"):
            ldplayer_identity(self.path)

    def test_record_schema_accepts_only_one_complete_identity_kind(self) -> None:
        schema = json.loads((ROOT / "tools/system_mode/schemas/qualification-v1.schema.json").read_text())
        identity = ldplayer_identity(self.path)
        validate_schema_instance(identity, schema["properties"]["instance_identity"], root_schema=schema)
        mixed = dict(identity, inode=1)
        with self.assertRaises(SchemaValidationError):
            validate_schema_instance(mixed, schema["properties"]["instance_identity"], root_schema=schema)
        for key in identity:
            incomplete = copy.deepcopy(identity)
            del incomplete[key]
            with self.subTest(key=key), self.assertRaises(SchemaValidationError):
                validate_schema_instance(incomplete, schema["properties"]["instance_identity"], root_schema=schema)

    def test_metadata_replacement_during_capture_is_rejected(self) -> None:
        def capture(path, **kwargs):
            result = stable_regular_file(path, **kwargs)
            if path == self.controller:
                self.path.write_text(XML + "\n<!-- changed during capture -->", encoding="utf-8")
            return result

        with mock.patch("tools.system_mode.host_identity.stable_regular_file", side_effect=capture):
            with self.assertRaisesRegex(ValueError, "changed while"):
                ldplayer_identity(self.path)

    def test_another_instances_adb_transport_is_rejected_before_probing(self) -> None:
        wrapper = self.root / "lifecycle.sh"
        wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
        wrapper.chmod(0o700)
        client = mock.Mock()
        client.resolve_serial.return_value = "127.0.0.1:5555"
        with mock.patch("tools.system_mode.qualification.collect_report") as probe:
            with self.assertRaisesRegex(ValueError, "does not belong"):
                qualify_target(
                    client, output=self.root / "record.json", backup_location=self.root / "backup",
                    snapshot_id="test", backup_command=f"{wrapper} {{backup}}",
                    restore_command=f"{wrapper} {{backup}}", cold_boot_command=str(wrapper),
                    instance_identity_path=self.path, instance_kind="ldplayer-v1",
                    seal_key_path=self.root / "seal.key",
                )
            probe.assert_not_called()


class SchemaAlternativeTest(unittest.TestCase):
    def test_ambiguous_and_unmatched_alternatives_fail(self) -> None:
        schema = {"oneOf": [{"type": "integer"}, {"const": 1}]}
        validate_schema_instance(2, schema)
        for value in (1, "1", True):
            with self.subTest(value=value), self.assertRaises(SchemaValidationError):
                validate_schema_instance(value, schema)

    def test_driver_digest_covers_qualification_authorization_and_artifact_verifier(self) -> None:
        with tempfile.TemporaryDirectory(prefix="kitsune-driver-digest-") as temporary:
            root = Path(temporary) / "system_mode"
            root.mkdir()
            (root / "contracts").mkdir()
            (root / "schemas").mkdir()
            for name in ("doctor.py", "qualification.py", "authorization.py", "host_identity.py"):
                (root / name).write_text("original", encoding="ascii")
            artifact = root.parent / "next_system_baseline.py"
            artifact.write_text("original", encoding="ascii")
            with mock.patch("tools.system_mode.doctor.__file__", str(root / "doctor.py")):
                expected = _probe_digest()
                for path in (root / "qualification.py", root / "authorization.py", root / "host_identity.py", artifact):
                    with self.subTest(path=path.name):
                        path.write_text("changed", encoding="ascii")
                        self.assertNotEqual(expected, _probe_digest())
                        path.write_text("original", encoding="ascii")
