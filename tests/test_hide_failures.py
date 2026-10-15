"""Run the native activation function with unavailable prerequisites and failed writes."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HideActivationTest(unittest.TestCase):
    def test_failed_activation_does_not_publish_enforcement(self):
        source = (ROOT / "native/src/core/deny/utils.cpp").read_text()
        function = source[source.index("int enable_deny() {"):source.index("\nint disable_deny()")]
        support = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <unistd.h>
using namespace std;
namespace DenyResponse { enum { OK, ENFORCED, NOT_ENFORCED, ITEM_EXIST,
 ITEM_NOT_EXIST, INVALID_PKG, NO_NS, ERROR, REBOOT_REQUIRED, UNSUPPORTED_PROVIDER }; }
struct mutex_guard { explicit mutex_guard(int) {} };
int data_lock;
atomic<bool> hide_enabled=false, denylist_enforced=false, external_owner=false,
 external_at_boot=false, inverse=false;
bool namespace_present=false, monitor_available=true, write_ok=true;
int writes=0;
int fake_access(const char *, int) { return namespace_present ? 0 : -1; }
#define access fake_access
#define LOGI(...)
bool external_provider_installed() { return false; }
bool external_adapter_installed() { return false; }
bool ensure_data() { return true; }
bool start_hide_monitor() { return monitor_available; }
bool db_exec(const char *) { ++writes; return write_ok; }
struct MagiskD { static MagiskD &Get() { static MagiskD d; return d; }
 bool zygisk_enabled() { return false; } };
'''
        cases = r'''
int main() {
 assert(enable_deny()==DenyResponse::NO_NS);
 assert(!hide_enabled && !denylist_enforced && writes==0);
 namespace_present=true; monitor_available=false;
 assert(enable_deny()==DenyResponse::ERROR);
 assert(!hide_enabled && !denylist_enforced && writes==0);
 monitor_available=true; write_ok=false;
 assert(enable_deny()==DenyResponse::ERROR);
 assert(!hide_enabled && !denylist_enforced && writes==1);
 write_ok=true;
 assert(enable_deny()==DenyResponse::OK);
 assert(hide_enabled && denylist_enforced && writes==2);
}
'''
        with tempfile.TemporaryDirectory(prefix="kitsune-hide-failure-") as temp:
            cpp = Path(temp) / "activation.cpp"
            binary = Path(temp) / "activation"
            cpp.write_text(support + function + cases)
            subprocess.run(["c++", "-std=c++20", str(cpp), "-o", str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
