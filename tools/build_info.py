#!/usr/bin/env python3
"""Generate Kitsune identity once for Gradle, native code and installer scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]*")


def encoded(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def read_spec(root: Path = ROOT) -> dict:
    data = json.loads((root / "kitsune-build.json").read_text())
    required = {
        "schema", "product_version", "app_version_code", "application_id", "product_name",
        "channel", "upstream_version", "upstream_commit", "compat_version_code",
        "protocol_version", "capabilities", "debug_capabilities",
    }
    if set(data) != required or data["schema"] != 1:
        raise ValueError("Unsupported Kitsune build specification")
    for key in ("product_version", "application_id", "channel", "upstream_version"):
        if not isinstance(data[key], str) or not TOKEN.fullmatch(data[key]):
            raise ValueError(f"Invalid build field: {key}")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?", data["product_version"]):
        raise ValueError("Product version must use Kitsune semantic versioning")
    if not HEX40.fullmatch(data["upstream_commit"]):
        raise ValueError("Upstream base must be a full commit")
    for key in ("app_version_code", "compat_version_code", "protocol_version"):
        if type(data[key]) is not int or not 0 < data[key] <= 2100000000:
            raise ValueError(f"Invalid build integer: {key}")
    if data["app_version_code"] <= 31000:
        raise ValueError("Android upgrade code must exceed the inherited 31000")
    if not isinstance(data["product_name"], str) or not re.fullmatch(r"[a-zA-Z0-9 ._-]+", data["product_name"]):
        raise ValueError("Missing product name")
    for key in ("capabilities", "debug_capabilities"):
        values = data[key]
        if not isinstance(values, list) or any(
            not isinstance(v, str) or not re.fullmatch(r"[a-z0-9.-]+\.v[1-9][0-9]*", v)
            for v in values
        ) or len(values) != len(set(values)):
            raise ValueError(f"Invalid capabilities: {key}")
    return data


def source_state(root: Path = ROOT) -> dict:
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    if not HEX40.fullmatch(commit):
        raise ValueError("Cannot determine source commit")
    status = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if entry.startswith(b"160000 "):
            path = root / os.fsdecode(entry.split(b"\t", 1)[1])
            if (path / ".git").exists() and git(path, "status", "--porcelain=v1").strip():
                raise ValueError(f"Cannot identify locally modified submodule: {path}")
    # Hash content, not just dirty filenames: two edits at one HEAD are different builds.
    digest = hashlib.sha256(git(root, "rev-parse", "HEAD^{tree}"))
    digest.update(git(root, "diff", "--binary", "HEAD", "--"))
    for name in sorted(git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        if not name:
            continue
        path = root / os.fsdecode(name)
        content = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        digest.update(name + b"\0" + (b"link" if path.is_symlink() else b"file") + b"\0")
        digest.update(hashlib.sha256(content).digest())
    return {"source_commit": commit, "source_dirty": bool(status.strip()),
            "source_digest": digest.hexdigest()}


def identity(root: Path = ROOT) -> dict:
    data = read_spec(root)
    git(root, "merge-base", "--is-ancestor", data["upstream_commit"], "HEAD")
    upstream_props = git(root, "show", f'{data["upstream_commit"]}:app/gradle.properties').decode()
    match = re.search(r"(?m)^magisk.versionCode=([0-9]+)$", upstream_props)
    if match is None or int(match[1]) != data["compat_version_code"]:
        raise ValueError("Compatibility epoch must match the selected upstream base")
    tag = git(root, "rev-parse", f'v{data["upstream_version"]}^{{commit}}').decode().strip()
    if tag != data["upstream_commit"]:
        raise ValueError("Upstream version does not identify the selected source")
    data.update(source_state(root))
    data["version_name"] = (f'{data["product_version"]}-kitsune.{data["source_commit"][:8]}'
                            + ("-dirty" if data["source_dirty"] else ""))
    data["release_tag"] = (f'kitsune-canary-{data["source_commit"]}'
                           if data["product_version"].endswith("-dev")
                           else f'kitsune-v{data["product_version"]}')
    return data


def variant_info(data: dict, variant: str) -> dict:
    if variant not in ("debug", "release"):
        raise ValueError("Unknown build variant")
    result = dict(data)
    extra = result.pop("debug_capabilities")
    result["capabilities"] = sorted(set(result["capabilities"] + (extra if variant == "debug" else [])))
    result["variant"] = variant
    result["build_id"] = hashlib.sha256(encoded(result).encode()).hexdigest()
    return result


def shell_info(data: dict) -> str:
    values = {
        "MAGISK_VER": data["version_name"],
        "MAGISK_VER_CODE": data["compat_version_code"],
        "KITSUNE_APP_VERSION_CODE": data["app_version_code"],
        "KITSUNE_PRODUCT_VERSION": data["product_version"],
        "KITSUNE_SOURCE_COMMIT": data["source_commit"],
        "KITSUNE_SOURCE_DIRTY": str(data["source_dirty"]).lower(),
        "KITSUNE_UPSTREAM_BASE": data["upstream_commit"],
        "KITSUNE_UPSTREAM_VERSION": data["upstream_version"],
        "KITSUNE_CHANNEL": data["channel"],
        "KITSUNE_PROTOCOL_VERSION": data["protocol_version"],
        "KITSUNE_BUILD_ID": data["build_id"],
        "KITSUNE_CAPABILITIES": " ".join(data["capabilities"]),
    }
    return "\n".join(f"{key}={value}" if type(value) is int or key == "KITSUNE_SOURCE_DIRTY"
                     else f"{key}='{value}'" for key, value in values.items())


def write_if_changed(path: Path, text: str) -> None:
    if path.exists() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def generate(root: Path = ROOT) -> dict:
    data = identity(root)
    output = root / "native/out/generated"
    write_if_changed(output / "build-info.json", encoded(data) + "\n")
    for variant in ("debug", "release"):
        info = variant_info(data, variant)
        write_if_changed(output / f"build-info-{variant}.json", encoded(info) + "\n")
        write_if_changed(output / f"build-info-{variant}.sh", shell_info(info))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--release-tag", action="store_true")
    args = parser.parse_args()
    data = generate(args.root)
    if args.release_tag:
        if data["source_dirty"]:
            parser.error("Release tags require a clean, committed source tree")
        print(data["release_tag"])


if __name__ == "__main__":
    main()
