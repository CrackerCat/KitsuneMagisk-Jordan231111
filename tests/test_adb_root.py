"""An ADB transport result cannot substitute for the requested guest UID."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from tools.adb_root import transition


@unittest.skipIf(os.name == "nt", "POSIX executable fixture")
class AdbRootTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.adb = Path(self.directory.name) / "adb"
        self.adb.write_text(f"#!{sys.executable}\n" + r'''
import json
from pathlib import Path
import sys
import time
p = Path(__file__)
config = json.loads(p.with_suffix('.json').read_text())
with p.with_suffix('.calls').open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\n')
if sys.argv[-1] in ('root', 'unroot'):
    print('adb: unable to connect: closed', file=sys.stderr)
    raise SystemExit(config['request_status'])
assert sys.argv[-3:] == ['exec-out', 'id', '-u']
if config.get('hang'):
    time.sleep(10)
state = p.with_suffix('.state')
index = int(state.read_text()) if state.exists() else 0
state.write_text(str(index + 1))
uids = config['uids']
print(uids[min(index, len(uids) - 1)])
raise SystemExit(config.get('probe_status', 0))
''')
        self.adb.chmod(0o700)

    def configure(self, **values):
        self.adb.with_suffix(".json").write_text(json.dumps(values))

    def test_closed_client_waits_for_verified_root(self):
        self.configure(request_status=1, uids=["2000", "0"])
        report = transition("owned-serial", "root", str(self.adb), timeout=2)
        self.assertEqual(0, report["verified_uid"])
        self.assertEqual(1, report["request_returncode"])
        calls = [json.loads(line) for line in self.adb.with_suffix(".calls").read_text().splitlines()]
        self.assertEqual(1, sum(call[-1] == "root" for call in calls))
        self.assertTrue(all(call[:2] == ["-s", "owned-serial"] for call in calls))

    def test_successful_client_without_root_fails(self):
        self.configure(request_status=0, uids=["2000"])
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            transition("owned-serial", "root", str(self.adb), timeout=0.3)

    def test_unroot_requires_shell_uid(self):
        self.configure(request_status=1, uids=["0", "2000"])
        report = transition("owned-serial", "unroot", str(self.adb), timeout=2)
        self.assertEqual(2000, report["verified_uid"])

    def test_unroot_does_not_accept_a_root_identity(self):
        self.configure(request_status=0, uids=["0"])
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            transition("owned-serial", "unroot", str(self.adb), timeout=0.3)

    def test_failed_identity_query_cannot_confirm_root(self):
        self.configure(request_status=1, uids=["0"], probe_status=1)
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            transition("owned-serial", "root", str(self.adb), timeout=0.3)

    def test_identity_query_timeout_fails(self):
        self.configure(request_status=1, uids=["0"], hang=True)
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            transition("owned-serial", "root", str(self.adb), timeout=0.3)
