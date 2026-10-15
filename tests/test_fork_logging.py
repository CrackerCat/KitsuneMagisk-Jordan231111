"""Exercise the daemon's actual fork helper while another thread owns its log lock."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ForkLoggingTest(unittest.TestCase):
    def test_child_does_not_inherit_another_threads_log_lock(self):
        source = (ROOT / "native/src/core/logging.rs").read_text()
        helper = source[source.index("pub fn fork_with_logging_lock()"):
                        source.index("\nfn with_logd_fd")]
        support = r'''
mod libc {
    #[allow(non_camel_case_types)] pub type pid_t = i32;
    unsafe extern "C" {
        pub fn fork() -> pid_t;
        pub fn waitpid(pid: pid_t, status: *mut i32, options: i32) -> pid_t;
        pub fn _exit(status: i32) -> !;
    }
}
static MAGISK_LOGD_FD: std::sync::Mutex<()> = std::sync::Mutex::new(());
'''
        main = r'''
fn main() {
    let (tx, rx) = std::sync::mpsc::channel();
    let holder = std::thread::spawn(move || {
        let guard = MAGISK_LOGD_FD.lock().expect("log lock");
        tx.send(()).expect("ready");
        std::thread::sleep(std::time::Duration::from_millis(100));
        drop(guard);
    });
    rx.recv().expect("holder ready");
    let child = fork_with_logging_lock();
    assert!(child >= 0);
    if child == 0 {
        let unlocked = MAGISK_LOGD_FD.try_lock().is_ok();
        unsafe { libc::_exit(if unlocked { 0 } else { 91 }); }
    }
    let mut status = -1;
    assert_eq!(unsafe { libc::waitpid(child, &mut status, 0) }, child);
    assert_eq!(status, 0, "child inherited the held log lock");
    holder.join().expect("holder");
}
'''
        with tempfile.TemporaryDirectory(prefix="kitsune-fork-") as temp:
            path = Path(temp)
            rust = path / "fork.rs"
            binary = path / "fork"
            rust.write_text(support + helper + main)
            subprocess.run(["rustc", "--edition=2024", str(rust), "-o", str(binary)],
                           check=True, capture_output=True, timeout=30)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
