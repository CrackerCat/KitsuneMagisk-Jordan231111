from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

BRIDGE = r'''
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <sys/wait.h>
#include <unistd.h>

static atomic_int interrupted;
static pthread_t waiter, interrupter;
static void handle_signal(int signal) { (void) signal; }
static void *interrupt_wait(void *unused) {
    (void) unused;
    for (int i = 0; i < 100 && !atomic_load(&interrupted); ++i) {
        usleep(10000);
        pthread_kill(waiter, SIGUSR1);
    }
    return 0;
}
void test_arm_interrupt(void) {
    struct sigaction action = {0};
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGUSR1, &action, 0);
    atomic_store(&interrupted, 0);
    waiter = pthread_self();
    pthread_create(&interrupter, 0, interrupt_wait, 0);
}
int test_finish_interrupt(void) {
    pthread_join(interrupter, 0);
    return atomic_load(&interrupted);
}
int test_waitpid(int pid, int *status, int flags) {
    int result = waitpid(pid, status, flags);
    if (result < 0 && errno == EINTR) atomic_store(&interrupted, 1);
    return result;
}
int test_interrupted_errno(void) { return errno == EINTR; }
int test_exited(int status) { return WIFEXITED(status); }
int test_exit_status(int status) { return WEXITSTATUS(status); }
int test_signaled(int status) { return WIFSIGNALED(status); }
int test_signal(int status) { return WTERMSIG(status); }
int test_spawn(int mode) {
    if (mode == 5) return getpid();  // Not a child: waitpid must fail.
    if (mode == 6) return -1;        // Simulate fork failure.
    int pid = fork();
    if (pid == 0) {
        if (mode == 2) kill(getpid(), SIGKILL);
        if (mode == 3) kill(getpid(), SIGTERM);
        if (mode == 4) {
            usleep(500000);
            _exit(7);
        }
        _exit(mode == 1 ? 23 : 0);
    }
    return pid;
}
'''

RUST = r'''
use base::LibcReturn;
use nix::errno::Errno;
mod nix {
    pub mod errno {
        #[allow(clippy::upper_case_acronyms)]
        pub enum Errno { EINTR, Other }
    }
}
mod base {
    use crate::{libc, nix::errno::Errno};
    pub trait LibcReturn { fn check_err(self) -> Result<i32, Errno>; }
    impl LibcReturn for i32 {
        fn check_err(self) -> Result<i32, Errno> {
            if self >= 0 { Ok(self) }
            else if unsafe { libc::test_interrupted_errno() } != 0 { Err(Errno::EINTR) }
            else { Err(Errno::Other) }
        }
    }
}
#[allow(non_snake_case)]
mod libc {
    unsafe extern "C" {
        #[link_name = "test_waitpid"] pub fn waitpid(pid: i32, status: *mut i32, flags: i32) -> i32;
        fn test_exited(status: i32) -> i32;
        fn test_exit_status(status: i32) -> i32;
        fn test_signaled(status: i32) -> i32;
        fn test_signal(status: i32) -> i32;
        pub fn test_interrupted_errno() -> i32;
        pub fn test_spawn(mode: i32) -> i32;
        pub fn test_arm_interrupt();
        pub fn test_finish_interrupt() -> i32;
    }
    pub fn WIFEXITED(status: i32) -> bool { unsafe { test_exited(status) != 0 } }
    pub fn WEXITSTATUS(status: i32) -> i32 { unsafe { test_exit_status(status) } }
    pub fn WIFSIGNALED(status: i32) -> bool { unsafe { test_signaled(status) != 0 } }
    pub fn WTERMSIG(status: i32) -> i32 { unsafe { test_signal(status) } }
}
fn main() {
    for (mode, expected) in [(0, 0), (1, 23), (2, 137), (3, 143), (5, -1)] {
        let child = unsafe { libc::test_spawn(mode) };
        assert!(child > 0);
        assert_eq!(wait_for_child(child), expected, "child mode {mode}");
    }
    let child = unsafe { libc::test_spawn(4) };
    assert!(child > 0);
    unsafe { libc::test_arm_interrupt() };
    assert_eq!(wait_for_child(child), 7);
    assert_eq!(unsafe { libc::test_finish_interrupt() }, 1, "waitpid was not interrupted");
    println!("SU exit, signal, wait-error and EINTR checks passed");
}
'''

CPP = r'''
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <sys/wait.h>
extern "C" {
    int test_spawn(int mode);
    int test_waitpid(int pid, int *status, int flags);
    void test_arm_interrupt(void);
    int test_finish_interrupt(void);
}
struct exec_t { int mode; };
int exec_command(exec_t &exec) {
    int pid = test_spawn(exec.mode);
    if (exec.mode == 4 && pid > 0) test_arm_interrupt();
    return pid;
}
#define waitpid test_waitpid
'''

CPP_MAIN = r'''
int main() {
    const int modes[] = {0, 1, 2, 3, 5, 6};
    const int expected[] = {0, 23, 137, 143, -1, -1};
    for (unsigned i = 0; i < sizeof(modes) / sizeof(modes[0]); ++i) {
        exec_t exec{modes[i]};
        assert(exec_command_sync(exec) == expected[i]);
    }
    exec_t exec{4};
    assert(exec_command_sync(exec) == 7);
    assert(test_finish_interrupt() == 1);
    puts("Command exit, signal, wait-error and EINTR checks passed");
}
'''


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ChildStatusTest(unittest.TestCase):
    def test_native_waiters_preserve_signals_and_retry_interruptions(self):
        # Execute the production wait blocks against real children and signals.
        # The C bridge supplies platform wait macros without duplicating them.
        su = (ROOT / 'native/src/core/su/daemon.rs').read_text()
        start = su.index('        let mut status = 0;', su.index('// Wait result'))
        end = su.index('        debug!("su: return code=', start)
        rust = RUST + '\nfn wait_for_child(child: i32) -> i32 {\n' + su[start:end] + '\ncode\n}\n'
        cpp = CPP + function((ROOT / 'native/src/base/base.cpp').read_text(),
                             'int exec_command_sync(exec_t &exec)') + CPP_MAIN
        with tempfile.TemporaryDirectory(prefix='kitsune-child-status-') as temporary:
            root = Path(temporary)
            (root / 'bridge.c').write_text(BRIDGE)
            (root / 'test.rs').write_text(rust)
            (root / 'test.cpp').write_text(cpp)
            bridge = root / 'bridge.o'
            subprocess.run(['cc', '-pthread', '-c', str(root / 'bridge.c'), '-o', str(bridge)], check=True)
            subprocess.run(['rustc', '--edition=2024', str(root / 'test.rs'), '-C',
                            'link-arg=' + str(bridge), '-C', 'link-arg=-lpthread',
                            '-o', str(root / 'rust-test')], check=True)
            subprocess.run(['c++', '-std=c++20', '-pthread', str(root / 'test.cpp'),
                            str(bridge), '-o', str(root / 'cpp-test')], check=True)
            for binary in ['rust-test', 'cpp-test']:
                subprocess.run([str(root / binary)], check=True, timeout=15)
