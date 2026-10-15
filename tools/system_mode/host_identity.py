"""Stable vendor identities for rewritten emulator instance metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

from .authorization import stable_regular_file


LDPLAYER_IDENTITY = "ldplayer-v1"
MAX_METADATA_BYTES = 1024 * 1024
VBOX = "{http://www.virtualbox.org/}"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("ascii")).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate vendor configuration field: {key}")
        result[key] = value
    return result


def ldplayer_identity(path: Path) -> dict[str, object]:
    """Bind the vendor UUID, hardware identifiers, disk layout and controller.

    LDPlayer rewrites the .vbox file and restoring a verified image replaces
    its inode. These operations must not erase the identity of the instance.
    GUI position and file timestamps are not instance identifiers. The generic
    file identity remains exact; this projection requires explicit opt-in.
    """

    if not path.is_absolute() or path.name != "leidian.vbox":
        raise ValueError("LDPlayer identity requires an absolute leidian.vbox path")
    match = re.fullmatch(r"leidian(0|[1-9][0-9]*)", path.parent.name)
    if match is None or path.parent.parent.name != "vms":
        raise ValueError("LDPlayer metadata is outside a vendor instance directory")
    index = int(match[1])
    if index > 999:
        raise ValueError("LDPlayer instance index is outside the supported range")
    configuration = path.parent.parent / "config" / f"leidian{index}.config"
    controller = path.parent.parent.parent / "ldconsole.exe"
    captured = []

    def read(file: Path, *, capture: bool = True):
        identity, content = stable_regular_file(file, purpose="LDPlayer instance metadata",
                                               capture=capture,
                                               max_bytes=MAX_METADATA_BYTES if capture else None)
        # Reject redirected ancestors too: the vendor layout must identify the
        # actual instance rather than a convenient link to another directory.
        if Path(identity["path"]) != file:
            raise ValueError("LDPlayer instance metadata contains a redirected path")
        captured.append((file, identity))
        return identity, content

    metadata, xml = read(path)
    config_metadata, raw = read(configuration)
    executable, _ = read(controller, capture=False)
    if xml is None or raw is None:
        raise ValueError("invalid LDPlayer metadata document")
    try:
        xml_text = xml.decode("utf-8")
        if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
            raise ValueError("LDPlayer metadata must not declare entities")
        tree = ET.fromstring(xml_text)
        machines = tree.findall(f"{VBOX}Machine")
        if tree.tag != f"{VBOX}VirtualBox" or len(machines) != 1:
            raise ValueError("LDPlayer metadata must contain exactly one machine")
        machine = machines[0]
        machine_uuid = str(uuid.UUID(machine.attrib["uuid"]))
        if machine.attrib["name"] != f"leidian{index}":
            raise ValueError("LDPlayer machine name does not match its directory")
        settings = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(settings, dict):
            raise ValueError("LDPlayer configuration must be an object")
    except (ET.ParseError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot parse LDPlayer vendor metadata") from exc
    if settings.get("basicSettings.standaloneSysVmdk") is not True:
        raise ValueError("LDPlayer qualification requires a private writable system disk")
    properties = {key: value for key, value in settings.items() if key.startswith("propertySettings.")}
    for required in ("phoneAndroidId", "phoneIMEI", "macAddress"):
        if not isinstance(properties.get(f"propertySettings.{required}"), str) or not properties[f"propertySettings.{required}"]:
            raise ValueError(f"LDPlayer configuration lacks {required}")
    if not all(isinstance(value, (str, int, bool)) for value in properties.values()):
        raise ValueError("unexpected LDPlayer hardware identity value")

    media = []
    for disk in machine.findall(f"{VBOX}MediaRegistry/{VBOX}HardDisks/{VBOX}HardDisk"):
        try:
            location = disk.attrib["location"]
            # Only the per-instance data disk is registered on the qualified
            # standalone-system layout. Shared, nested and redirected media
            # need a different adapter with a complete backing-chain contract.
            if location != "data.vdi" or disk.attrib["format"] != "VDI" or disk.attrib["type"] != "Normal" or list(disk):
                raise ValueError("unsupported LDPlayer backing disk layout")
            media.append({"location": location, "uuid": str(uuid.UUID(disk.attrib["uuid"]))})
        except KeyError as exc:
            raise ValueError("incomplete LDPlayer media registry") from exc
    if len(media) != 1:
        raise ValueError("LDPlayer identity requires exactly one registered data disk")
    for name in ("system.vdi", "data.vdi", "sdcard.vdi"):
        disk_path = path.parent / name
        if disk_path.is_symlink() or not disk_path.is_file() or disk_path.resolve() != disk_path:
            raise ValueError(f"LDPlayer private disk is missing or redirected: {name}")
    attached = machine.findall(f"{VBOX}StorageControllers/{VBOX}StorageController/{VBOX}AttachedDevice")
    if len(attached) != 1 or attached[0].attrib.get("port") != "1" or attached[0].attrib.get("device") != "0":
        raise ValueError("unexpected LDPlayer storage attachment")
    images = attached[0].findall(f"{VBOX}Image")
    if len(images) != 1 or str(uuid.UUID(images[0].attrib.get("uuid", ""))) != media[0]["uuid"]:
        raise ValueError("LDPlayer storage attachment does not match its data disk")

    result = {
        "kind": LDPLAYER_IDENTITY,
        "path": str(metadata["path"]),
        "configuration_path": str(config_metadata["path"]),
        "controller_path": str(executable["path"]),
        "controller_sha256": executable["sha256"],
        "index": index,
        "machine_uuid": machine_uuid,
        "hardware_sha256": _digest(properties),
        "media_sha256": _digest(media),
    }
    # Read each small metadata file again so a cross-file replacement cannot
    # combine the identity of one instance with another instance's settings.
    for file, expected in captured:
        current, _ = stable_regular_file(file, purpose="LDPlayer identity revalidation")
        if current != expected:
            raise ValueError("LDPlayer metadata changed while its identity was read")
    result["sha256"] = _digest(result)
    return result


def ldplayer_serials(identity: dict[str, object]) -> set[str]:
    index = int(identity["index"])
    return {f"127.0.0.1:{5555 + 2 * index}", f"emulator-{5554 + 2 * index}"}


def mumu_identity(path: Path) -> dict[str, object]:
    """Bind the observed Global Android 12 private-difference disk layout.

    MuMu rewrites even its macaddress file on boot. Bind the vendor identifiers,
    attachments and immutable backing image, while retaining exact file checks
    during capture. Android 15 uses a different root implementation and layout.
    """
    match = re.fullmatch(r"MuMuPlayerGlobal-12\.0-(0|[1-9][0-9]*)", path.parent.name)
    if (not path.is_absolute() or match is None or path.parent.parent.name != "vms"
            or path.name != f"{path.parent.name}.nemu"):
        raise ValueError("MuMu identity requires an absolute Global Android 12 .nemu path")
    index = int(match[1])
    if index > 999:
        raise ValueError("MuMu instance index is outside the supported range")
    install = path.parent.parent.parent
    configuration = path.parent / "configs/vm_config.json"
    controller = install / "nx_main/MuMuManager.exe"
    base = install / "nx_device/12.0/vms/MuMuPlayerGlobal-12.0-base/system.vdi"
    captured = []

    def read(file: Path, *, capture: bool = True):
        identity, content = stable_regular_file(
            file, purpose="MuMu instance metadata", capture=capture,
            max_bytes=MAX_METADATA_BYTES if capture else None,
        )
        if Path(identity["path"]) != file:
            raise ValueError("MuMu instance metadata contains a redirected path")
        captured.append((file, identity))
        return identity, content

    metadata, xml = read(path)
    config_metadata, raw = read(configuration)
    _, mac = read(path.parent / "macaddress")
    executable, _ = read(controller, capture=False)
    backing, _ = read(base, capture=False)
    try:
        xml_text = xml.decode("utf-8")
        if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
            raise ValueError("MuMu metadata must not declare entities")
        tree = ET.fromstring(xml_text)
        machines = tree.findall(f"{VBOX}Machine")
        if tree.tag != f"{VBOX}VirtualBox" or len(machines) != 1:
            raise ValueError("MuMu metadata must contain exactly one machine")
        machine = machines[0]
        machine_uuid = str(uuid.UUID(machine.attrib["uuid"]))
        if machine.attrib["name"] != path.parent.name:
            raise ValueError("MuMu machine name does not match its directory")
        settings = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)["vm"]
        if settings["system_vdi"]["sharable"] != "Writable":
            raise ValueError("MuMu qualification requires a writable private difference disk")
        phone = settings["phone"]
        for field in ("imei", "vdid", "brand", "model", "manufacturer", "code"):
            if not isinstance(phone[field], str) or not phone[field]:
                raise ValueError(f"MuMu configuration lacks {field}")
        hardware = {field: phone[field] for field in
                    ("imei", "vdid", "brand", "model", "manufacturer", "code")}
        hardware["mac"] = mac.decode("ascii").strip().lower()
        if re.fullmatch(r"[0-9a-f]{12}", hardware["mac"]) is None:
            raise ValueError("invalid MuMu MAC address")
        network = machine.findall(f"{VBOX}Hardware/{VBOX}Network/{VBOX}Adapter")
        if (len(network) != 1 or network[0].attrib.get("enabled") != "true"
                or network[0].attrib.get("MACAddress", "").lower() != hardware["mac"]):
            raise ValueError("MuMu network identity does not match its MAC file")
        forwards = [item for item in network[0].findall(f"{VBOX}NAT/{VBOX}Forwarding")
                    if item.attrib.get("name") == "ADB_PORT"]
        if (len(forwards) != 1 or forwards[0].attrib.get("hostip") != "127.0.0.1"
                or forwards[0].attrib.get("guestport") != "5555"
                or forwards[0].attrib.get("proto") != "1"):
            raise ValueError("unexpected MuMu ADB forwarding")
        port = int(forwards[0].attrib["hostport"])
        if not 1024 <= port <= 65535 or str(port) != settings["nat"]["port_forward"]["adb"]["host_port"]:
            raise ValueError("MuMu ADB endpoint does not match its configuration")

        disks = machine.findall(f"{VBOX}MediaRegistry/{VBOX}HardDisks/{VBOX}HardDisk")
        if len(disks) != 3:
            raise ValueError("unsupported MuMu backing disk layout")
        base_path = str(base).replace("\\", "/")
        # The vendor XML stores a Windows path even under MSYS2's POSIX view.
        if re.match(r"^/[a-zA-Z]/", base_path):
            base_path = base_path[1] + ":" + base_path[2:]
        if (disks[0].attrib["location"].replace("\\", "/").lower() != base_path.lower()
                or disks[0].attrib.get("type") != "Readonly"
                or disks[0].attrib.get("format") != "VDI"):
            raise ValueError("MuMu system base is not the expected read-only image")
        children = list(disks[0])
        if len(children) != 1 or children[0].tag != f"{VBOX}HardDisk":
            raise ValueError("MuMu requires one private system difference disk")
        media = [{"location": str(base), "uuid": str(uuid.UUID(disks[0].attrib["uuid"])),
                  "sha256": backing["sha256"]}]
        for disk, name in zip((children[0], disks[1], disks[2]),
                              ("system-diff.vdi", "ota.vdi", "data.vdi")):
            if (disk.attrib["location"] != name or disk.attrib.get("format") != "VDI"
                    or disk.attrib.get("type", "Normal") != "Normal" or list(disk)):
                raise ValueError("unsupported MuMu private disk layout")
            disk_path = path.parent / name
            if disk_path.is_symlink() or not disk_path.is_file() or disk_path.resolve() != disk_path:
                raise ValueError(f"MuMu private disk is missing or redirected: {name}")
            media.append({"location": name, "uuid": str(uuid.UUID(disk.attrib["uuid"]))})
        attached = machine.findall(
            f"{VBOX}Hardware/{VBOX}StorageControllers/{VBOX}StorageController/{VBOX}AttachedDevice")
        if len(attached) != 3:
            raise ValueError("unexpected MuMu storage attachment count")
        for slot, (attachment, disk) in enumerate(zip(attached, media[1:])):
            images = attachment.findall(f"{VBOX}Image")
            if (attachment.attrib.get("port") != str(slot) or attachment.attrib.get("device") != "0"
                    or len(images) != 1 or str(uuid.UUID(images[0].attrib["uuid"])) != disk["uuid"]):
                raise ValueError("MuMu storage attachment does not match its private disk")
    except (ET.ParseError, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot parse MuMu vendor metadata") from exc

    result = {
        "kind": "mumu-v1", "path": metadata["path"],
        "configuration_path": config_metadata["path"], "controller_path": executable["path"],
        "controller_sha256": executable["sha256"], "index": index, "machine_uuid": machine_uuid,
        "hardware_sha256": _digest(hardware), "media_sha256": _digest(media), "adb_port": port,
    }
    for file, expected in captured:
        current, _ = stable_regular_file(file, purpose="MuMu identity revalidation")
        if current != expected:
            raise ValueError("MuMu metadata changed while its identity was read")
    result["sha256"] = _digest(result)
    return result
