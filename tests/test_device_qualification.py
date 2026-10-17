"""Prevent boot or fixture observations from becoming unsupported support claims."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.device_qualification import SCHEMA, render


class QualificationTest(unittest.TestCase):
    def test_evidence_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = {"schema": SCHEMA, "artifact": {"sha256": "a" * 64,
                      "build": {"source_dirty": False, "source_commit": "b" * 40}},
                      "boots": [{"id": "a1d3e14b-a145-4e5a-8de3-6ae2afc4e771", "phase": "setup"},
                                {"id": "fd8ab3f1-4290-4c4a-8c88-e42c1dd3f604", "phase": "accepted"}]}
            target = {"id": "sdk-test", "name": "SDK image", "route": "patched ramdisk",
                      "status": "experimental", "evidence": ["run.json"], "runs": ["run.json"],
                      "limits": "No physical device claim."}
            manifest = {"schema": 1, "targets": [target]}
            path = root / "run.json"
            path.write_text(json.dumps(record))
            result, table = render(manifest, root)
            self.assertFalse(result["production_qualified"])
            self.assertIn("experimental", table)
            for change in ("reused-boot", "no-acceptance", "dirty", "no-hash", "fixture"):
                invalid = copy.deepcopy(record)
                if change == "reused-boot":
                    invalid["boots"][1]["id"] = invalid["boots"][0]["id"]
                elif change == "no-acceptance":
                    invalid["boots"][1]["phase"] = "cold-boot"
                elif change == "dirty":
                    invalid["artifact"]["build"]["source_dirty"] = True
                elif change == "no-hash":
                    invalid["artifact"]["sha256"] = ""
                else:
                    invalid["schema"] = "synthetic-boot-fixtures"
                path.write_text(json.dumps(invalid))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    render(manifest, root)
            path.write_text(json.dumps(record))
            for status in ("supported", "production", "passed"):
                target["status"] = status
                with self.assertRaises(ValueError):
                    render(manifest, root)
            target["status"] = "unqualified"
            target["evidence"] = ["../outside.json"]
            with self.assertRaises(ValueError):
                render(manifest, root)


if __name__ == "__main__":
    unittest.main()
