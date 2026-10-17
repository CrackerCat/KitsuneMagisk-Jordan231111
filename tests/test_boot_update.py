"""Exercise the native guard against ordinary imports over managed state."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((Path(os.environ.get("ANDROID_HOME", "")) / "ndk/magisk/ONDK_VERSION").is_file(), "Requires ONDK")
class ManagedBootUpdateTest(unittest.TestCase):
    def test_existing_redirected_and_unreadable_receipts_protect_runtime(self):
        source = (ROOT / "native/src/core/bootstages.rs").read_text()
        start = source.index("fn managed_runtime()")
        end = source.index("\n}\n", start) + 2
        function = source[start:end].replace("fn managed_runtime()", "fn managed_runtime(root: &std::path::Path)")
        function = function.replace('"/data/adb/kitsune/system-mode/transaction.env"', 'root.join("receipt")')
        with tempfile.TemporaryDirectory(prefix="kitsune-boot-update-") as temporary:
            root = Path(temporary)
            program = root / "test.rs"
            program.write_text(function + r'''
fn main() {
    use std::fs;
    let root = std::path::PathBuf::from(std::env::args().nth(1).expect("root"));
    fs::create_dir(&root).expect("directory");
    assert!(!managed_runtime(&root));
    let receipt = root.join("receipt");
    fs::write(&receipt, "STATE=BOOT_VERIFIED\n").expect("receipt");
    assert!(managed_runtime(&root));
    fs::write(&receipt, "malformed").expect("receipt");
    assert!(managed_runtime(&root));
    fs::remove_file(&receipt).expect("remove");
    std::os::unix::fs::symlink("missing", &receipt).expect("symlink");
    assert!(managed_runtime(&root));
    fs::remove_file(&receipt).expect("remove");
    fs::create_dir(&receipt).expect("directory receipt");
    assert!(managed_runtime(&root));
    fs::remove_dir(&receipt).expect("remove");
    fs::remove_dir(&root).expect("remove");
    fs::write(&root, "not a directory").expect("invalid parent");
    assert!(managed_runtime(&root));
}
''')
            binary = root / "test"
            subprocess.run([str(ROOT / "scripts/env.py"), "rustc", "--edition=2024", str(program), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary), str(root / "fs")], check=True, capture_output=True, timeout=10)
