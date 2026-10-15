import json
import os
from pathlib import Path
import re
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ZygiskSignaturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                cls.generator = runpy.run_path(str(ROOT / "native/src/core/zygisk/gen_jni_hooks.py"))
                cls.header = Path("jni_hooks.hpp").read_text()
            finally:
                os.chdir(previous)

    def test_published_graphene_signatures_and_argument_order(self):
        fixtures = json.loads((ROOT / "tests/fixtures/zygisk-signatures.json").read_text())
        for fixture in fixtures["signatures"]:
            with self.subTest(method=fixture["method"]):
                method = self.generator[fixture["method"]]
                self.assertEqual(fixture["signature"], method.jni_sig())
                self.assertEqual(fixture["arguments"], [arg.type.cpp for arg in method.args])
                self.assertEqual(1, self.header.count('"' + fixture["signature"] + '"'))
                # The added trailing array is passed to the original specialization method.
                self.assertIn(method.arg_list_name(), self.header)

    def test_no_ambiguous_dispatch_signatures(self):
        for field in ("fork_app_methods", "specialize_app_methods", "fork_server_methods"):
            table = self.header.split(f" {field} = ", 1)[1].split("}};", 1)[0]
            signatures = re.findall(r'"(\([^\"]+\)[IV])"', table)
            self.assertTrue(signatures)
            self.assertEqual(len(signatures), len(set(signatures)))

    def test_compiled_header_matches_generator(self):
        self.assertEqual(self.header, (ROOT / "native/src/core/zygisk/jni_hooks.hpp").read_text())

    def test_runtime_contract_tracks_module_api(self):
        api = (ROOT / "native/src/core/zygisk/api.hpp").read_text()
        version = re.search(r"#define ZYGISK_API_VERSION ([0-9]+)", api).group(1)
        provider = (ROOT / "native/src/core/zygisk/provider.rs").read_text()
        self.assertIn('module_api\\\":' + version, provider)


if __name__ == "__main__":
    unittest.main()
