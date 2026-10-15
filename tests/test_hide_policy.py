"""Compile the native name/matching policy, including hostile persisted inputs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HidePolicyTest(unittest.TestCase):
    def test_native_process_boundaries(self):
        source = r'''
#include "deny/policy.hpp"
#include <cassert>
#include <string>
int main() {
    using namespace hide;
    assert(valid_pair("com.example", "com.example:worker"));
    assert(valid_pair("isolated", "com.example:service"));
    assert(valid_pair("isolated", "com.example:service:com.example.Container$Service"));
    assert(valid_pair("isolated", "com.example:service:com.example.服务"));
    assert(valid_pair("webview_zygote", "webview_zygote"));
    for (auto bad : {"", "'", "a;b", "a/b", "a b", "a\\b", "a%", "a\n"}) {
        assert(!valid_pair("com.example", bad));
        assert(!valid_pair(bad, "com.example"));
    }
    assert(!valid_pair("webview_zygote", "other"));
    assert(!valid_name(std::string(1025, 'a'), true));
    assert(!valid_name(std::string("app\0evil", 8), true));
    assert(isolated_match("com.example:service:Class", "com.example:service"));
    assert(isolated_match("com.example:service", "com.example:"));
    assert(!isolated_match("com.example.evil:service", "com.example"));
    assert(!isolated_match("com.example:service2", "com.example:service"));
    assert(!isolated_match("com.example", ""));
    assert(!unmount(false, false, false));
    assert(unmount(false, true, false));
    assert(unmount(true, false, false));
    assert(!unmount(true, true, false));
    assert(!unmount(true, false, true));
}
'''
        with tempfile.TemporaryDirectory(prefix="kitsune-hide-policy-") as temp:
            cpp = Path(temp) / "policy.cpp"
            binary = Path(temp) / "policy"
            cpp.write_text(source)
            subprocess.run(["c++", "-std=c++20",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "native/src/core"),
                            str(cpp), "-o", str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
