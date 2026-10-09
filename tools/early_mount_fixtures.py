#!/usr/bin/env python3
"""Build inert early-mount payloads for PR14's route/timing qualification.

This creates archives, never installs them or selects an Android init hook.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TARGET = "system/etc/kitsune-pr8-early"
CONSUMER = b'''#!/system/bin/sh
# Run this dedicated consumer at the route's measured pre-post-fs-data hook.
# Capture stdout externally; /data may still be encrypted or unavailable.
set -eu
case "${1-}" in first-consumer|post-fs-data-control|after-disable|after-restore) ;;
    *) echo "invalid capture stage" >&2; exit 2 ;;
esac
target=/system/etc/kitsune-pr8-early
printf 'stage=%s\\n' "$1"
printf 'boot_id=%s\\n' "$(cat /proc/sys/kernel/random/boot_id)"
printf 'uptime=%s\\n' "$(cat /proc/uptime)"
printf 'namespace=%s\\n' "$(readlink /proc/self/ns/mnt)"
printf 'context=%s\\n' "$(cat /proc/self/attr/current 2>/dev/null || echo unavailable)"
for file in value deleted replaced/value replaced/base-only sibling link; do
    path="$target/$file"
    if [ -L "$path" ]; then
        printf 'link=%s:%s\\n' "$file" "$(readlink "$path")"
    elif [ -f "$path" ]; then
        printf 'file=%s:' "$file"
        cat "$path"
    else
        printf 'absent=%s\\n' "$file"
    fi
done
cat /proc/self/mountinfo
'''


def module(name: str) -> dict[str, tuple[bytes, int]]:
    files = {
        "module.prop": (f"id=kitsune_pr8_early_{name}\nname=PR8 early-mount fixture {name}\n"
                        f"version=1\nversionCode=1\nauthor=KitsuneMagisk\n"
                        "description=Disposable PR14 qualification fixture\n").encode(),
        f"{TARGET}/value": f"ordinary-{name}\n".encode(),
        f"early-mount/{TARGET}/value": f"early-{name}\n".encode(),
        f"early-mount/{TARGET}/replaced/.replace": b"",
        f"early-mount/{TARGET}/replaced/value": f"early-replacement-{name}\n".encode(),
        "customize.sh": b"#!/system/bin/sh\n# Ordinary whiteout control; early whiteouts are in early-tree.tar.\n"
                        b"REMOVE='/system/etc/kitsune-pr8-early/deleted'\n",
    }
    result = {path: (data, 0o100755 if path.endswith(".sh") else 0o100644)
              for path, data in files.items()}
    result[f"early-mount/{TARGET}/link"] = (b"value", 0o120777)
    return result


def write_zip(path: Path, files: dict[str, tuple[bytes, int]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, (data, mode) in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def write_tree(path: Path, *, early: bool) -> None:
    # Tar can faithfully encode a 0:0 whiteout; ZIP cannot carry its device ID.
    # Keep these inert archives for the qualified adapter to stage, never extract
    # device nodes on the developer's host as part of fixture generation.
    files = ({"value": b"global-early\n", "replaced/.replace": b"",
              "replaced/value": b"global-replacement\n"} if early else
             {"value": b"base\n", "deleted": b"base-deleted\n",
              "replaced/value": b"base-replacement\n", "replaced/base-only": b"base-only\n",
              "sibling": b"preserve\n"})
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(f"{TARGET}/{name}")
            info.mode, info.size = 0o644, len(data)
            archive.addfile(info, io.BytesIO(data))
        if early:
            link = tarfile.TarInfo(f"{TARGET}/link")
            link.type, link.linkname, link.mode = tarfile.SYMTYPE, "value", 0o777
            archive.addfile(link)
            whiteout = tarfile.TarInfo(f"{TARGET}/deleted")
            whiteout.type, whiteout.devmajor, whiteout.devminor = tarfile.CHRTYPE, 0, 0
            archive.addfile(whiteout)


def build(output: Path) -> dict:
    contract = json.loads((ROOT / "docs/early-mount-pr8.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    write_zip(output / "module-a.zip", module("a"))
    write_zip(output / "module-b.zip", module("b"))
    write_tree(output / "base-tree.tar", early=False)
    write_tree(output / "early-tree.tar", early=True)
    (output / "consumer.sh").write_bytes(CONSUMER)
    plan = {
        "schema": 1, "kind": "unexecuted-fixture-plan",
        "target": "/" + TARGET,
        "cases": [{"route": route, **case, "result": "not_run"}
                  for route in contract["routes"] for case in contract["cases"]],
        "controls": {
            "base": "base", "ordinary": ["ordinary-a", "ordinary-b"],
            "early": ["early-a", "early-b", "global-early"],
            "conflict": "Capture the historical winner in both installation orders; no winner is assumed.",
            "hook": "A qualified route adapter must place the consumer before the measured target reader. Running it after post-fs-data is only the late control.",
        },
        "artifacts": [{"path": path.name, "size": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in sorted(output.iterdir())],
    }
    (output / "plan.json").write_bytes((json.dumps(plan, indent=2) + "\n").encode())
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    args = parser.parse_args()
    plan = build(args.output)
    print(f"Created {len(plan['artifacts'])} inert artifacts and {len(plan['cases'])} unexecuted route cases")


if __name__ == "__main__":
    main()
