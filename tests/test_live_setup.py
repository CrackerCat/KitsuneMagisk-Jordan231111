"""Exercise bootstrap discovery with an ordinary-shell ADB transport."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveSetupTest(unittest.TestCase):
    def test_path_su_receives_command_and_preserves_failure(self):
        source = (ROOT / "scripts/live_setup.sh").read_text()
        start = source.index('if [ -z "$FIRST_STAGE" ]; then')
        end = source.index('\npm install ', start)
        with tempfile.TemporaryDirectory(prefix="kitsune-live-setup-") as directory:
            root = Path(directory)
            (root / "busybox").write_text('#!/bin/sh\necho 2000\n')
            (root / "su").write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 37\n')
            for name in ("busybox", "su"):
                (root / name).chmod(0o755)
            script = root / "setup.sh"
            script.write_text(source[start:end])
            env = dict(os.environ, PATH=str(root), FIRST_STAGE="")
            result = subprocess.run(["/bin/sh", str(script)], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(37, result.returncode)
            self.assertEqual(["-c", "FIRST_STAGE=1 ASH_STANDALONE=1 /data/local/tmp/busybox sh /data/local/tmp/live_setup.sh"], result.stdout.splitlines())
            (root / "su").unlink()
            result = subprocess.run(["/bin/sh", str(script)], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(1, result.returncode)
            self.assertIn("Bootstrap root is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
