"""The host adapter stages only its owned bootstrap files in an offline copy."""

import gzip
import stat
import unittest
from unittest import mock

from tools.system_mode.host_image import Entry, decode, encode, stage


def entry(name, data=b"", mode=stat.S_IFREG | 0o700, uid=0):
    return Entry(name, [1, mode, uid, 0, 1, 123, len(data), 0, 0, 0, 0, 0, 0], data)


class HostImageTest(unittest.TestCase):
    def original(self):
        return [
            entry("boot/bsr", mode=stat.S_IFDIR | 0o755),
            entry("boot/bsr/payload", mode=stat.S_IFDIR | 0o700),
            entry("boot/stage2.sh", b"# BlueStacksRootMac managed hook BEGIN\nexec /init\n"),
            entry("boot/bsr/early.sh", b"/data/adb/.bsr_root\n/data/local/tmp/.bsr_root_request\n"),
            entry("boot/bsr/magisk_boot.sh", b"legacy bootstrap"),
            entry("boot/bsr/magisk.rc", b"owned RC"),
            entry("boot/bsr/payload/obsolete", b"old"),
            entry("vendor-unrelated", b"keep exact bytes", mode=stat.S_IFREG | 0o640, uid=1000),
        ]

    def test_staging_preserves_unowned_content_and_metadata(self):
        original = encode(self.original())
        files = {"magisk": b"current", "config": b"RECOVERYMODE=false\n"}
        staged = stage(original, files, b"new bootstrap")
        entries = {item.name: item for item in decode(staged)}
        self.assertEqual(b"new bootstrap", entries["boot/bsr/magisk_boot.sh"].data)
        self.assertNotIn("boot/bsr/payload/obsolete", entries)
        self.assertEqual(b"config\nmagisk\n", entries["boot/bsr/payload/.bsr_manifest"].data)
        before = {item.name: item for item in decode(original)}
        for name in ("vendor-unrelated", "boot/stage2.sh", "boot/bsr/early.sh", "boot/bsr/magisk.rc"):
            self.assertEqual(before[name], entries[name])
        self.assertEqual(staged, stage(staged, files, b"new bootstrap"))

    def test_rejects_wrong_ownership_links_and_missing_gate(self):
        for change in ("directory-mode", "directory-owner", "linked-script", "missing-gate"):
            entries = self.original()
            if change == "directory-mode": entries[0].fields[1] |= 0o002
            elif change == "directory-owner": entries[0].fields[2] = 2000
            elif change == "linked-script": entries[4].fields[1] = stat.S_IFLNK | 0o777
            else: entries[3].data = b"unmanaged"
            with self.subTest(change=change), self.assertRaises(ValueError):
                stage(encode(entries), {"magisk": b"current"}, b"bootstrap")

    def test_rejects_ambiguous_truncated_and_redirected_archives(self):
        for entries in ([entry("a"), entry("a")], [entry("../escape")],
                        [entry("/absolute")], [entry("boot//bsr")], [entry("boot/./bsr")]):
            with self.assertRaises(ValueError): decode(encode(entries))
        original = gzip.decompress(encode(self.original()))
        with self.assertRaises(ValueError): decode(original[:-30])
        with self.assertRaises(ValueError): decode(original + b"unexpected suffix")
        with mock.patch("tools.system_mode.host_image.MAX_IMAGE_SIZE", 32):
            with self.assertRaises(ValueError): decode(gzip.compress(original))


if __name__ == "__main__":
    unittest.main()
