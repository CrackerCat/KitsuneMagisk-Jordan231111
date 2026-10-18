#!/usr/bin/env python3
"""Confirm an SDK adbd root transition by its identity after reconnecting."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def transition(serial: str, action: str, adb: str = "adb", timeout: float = 20) -> dict:
    if action not in {"root", "unroot"} or not serial or timeout <= 0:
        raise ValueError("a serial, root/unroot action and positive timeout are required")
    expected = "0" if action == "root" else "2000"
    command = [adb, "-s", serial]
    deadline = time.monotonic() + timeout
    report = {"action": action, "expected_uid": int(expected), "identity_attempts": 0}
    try:
        request = subprocess.run(command + [action], capture_output=True, text=True,
                                 errors="replace", timeout=min(10, timeout))
        report.update(request_returncode=request.returncode,
                      request_output=(request.stdout + request.stderr)[-2048:])
    except subprocess.TimeoutExpired:
        report.update(request_returncode=None, request_output="ADB request timed out")

    # Restarting adbd can close the request connection before it reports success.
    # Neither a closed connection nor a successful client exit proves the UID.
    while (remaining := deadline - time.monotonic()) > 0:
        report["identity_attempts"] += 1
        try:
            probe = subprocess.run(command + ["exec-out", "id", "-u"],
                                   capture_output=True, text=True, errors="replace",
                                   timeout=min(3, remaining))
            uid = probe.stdout.strip()
            report["last_probe"] = {"returncode": probe.returncode, "stdout": uid[-256:],
                                    "stderr": probe.stderr[-2048:]}
            if probe.returncode == 0 and uid == expected:
                report["verified_uid"] = int(uid)
                return report
        except subprocess.TimeoutExpired:
            report["last_probe"] = {"error": "identity query timed out"}
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise RuntimeError("ADB identity transition not confirmed: " + json.dumps(report))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("action", choices=("root", "unroot"))
    args = parser.parse_args()
    try:
        print(json.dumps(transition(args.serial, args.action, args.adb)))
    except RuntimeError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
