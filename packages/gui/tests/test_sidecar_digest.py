"""The digest of the frozen sidecar tree: write, verify, tamper detection, speed and the start-up refusal."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from gui import cli, sidecar, sidecar_digest


def make_tree(root, count=5):
    for index in range(count):
        folder = root / f"pkg{index % 7}" / "sub"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"f{index}.bin").write_bytes(os.urandom(64) + bytes([index % 256]) * 4000)
    (root / "gui-backend").write_bytes(b"#!exe\n")


class DigestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        make_tree(self.root)
        sidecar_digest.write(self.root, "0.1.0")


class TestDigest(DigestCase):
    def test_file_format(self):
        document = json.loads((self.root / sidecar_digest.DIGEST_NAME).read_text())
        paths = [entry["path"] for entry in document["files"]]
        self.assertEqual(sorted(paths), paths)
        self.assertNotIn(sidecar_digest.DIGEST_NAME, paths)
        self.assertEqual(6, len(paths))
        self.assertEqual(64, len(document["tree"]))
        self.assertEqual("0.1.0", document["version"])

    def test_untouched_tree_verifies(self):
        self.assertTrue(sidecar_digest.verify(self.root))
        self.assertIsNone(sidecar.check_digest(self.root))

    def test_no_digest_file_is_skipped(self):
        (self.root / sidecar_digest.DIGEST_NAME).unlink()
        self.assertFalse(sidecar_digest.verify(self.root))
        self.assertIsNone(sidecar.check_digest(self.root))

    def test_changed_file(self):
        target = self.root / "pkg0" / "sub" / "f0.bin"
        target.write_bytes(target.read_bytes() + b"x")
        with self.assertRaises(sidecar_digest.SidecarTampered) as caught:
            sidecar_digest.verify(self.root)
        self.assertEqual("pkg0/sub/f0.bin", caught.exception.path)
        message = sidecar.check_digest(self.root)
        self.assertTrue(message.startswith("SIDECAR_TAMPERED: pkg0/sub/f0.bin"), message)

    def test_elf_files_are_checked_by_name_not_by_bytes(self):
        elf = self.root / "lib.so"
        elf.write_bytes(b"\x7fELF" + b"a" * 100)
        sidecar_digest.write(self.root, "0.1.0")
        elf.write_bytes(b"\x7fELF" + b"b" * 100)  # a bundler patched it
        self.assertTrue(sidecar_digest.verify(self.root))
        elf.unlink()
        with self.assertRaises(sidecar_digest.SidecarTampered):
            sidecar_digest.verify(self.root)

    def test_added_file(self):
        (self.root / "evil.so").write_bytes(b"x")
        with self.assertRaises(sidecar_digest.SidecarTampered) as caught:
            sidecar_digest.verify(self.root)
        self.assertEqual("evil.so", caught.exception.path)

    def test_removed_file(self):
        (self.root / "gui-backend").unlink()
        with self.assertRaises(sidecar_digest.SidecarTampered) as caught:
            sidecar_digest.verify(self.root)
        self.assertEqual("gui-backend", caught.exception.path)

    def test_symlink_swap(self):
        link = self.root / "lib.so"
        link.symlink_to("pkg0/sub/f0.bin")
        sidecar_digest.write(self.root, "0.1.0")
        self.assertTrue(sidecar_digest.verify(self.root))
        link.unlink()
        link.symlink_to("/etc/passwd")
        with self.assertRaises(sidecar_digest.SidecarTampered) as caught:
            sidecar_digest.verify(self.root)
        self.assertEqual("lib.so", caught.exception.path)

    def test_edited_digest_file(self):
        digest_file = self.root / sidecar_digest.DIGEST_NAME
        document = json.loads(digest_file.read_text())
        document["files"][0]["sha256"] = "0" * 64
        digest_file.write_text(json.dumps(document))
        with self.assertRaises(sidecar_digest.SidecarTampered) as caught:
            sidecar_digest.verify(self.root)
        self.assertEqual(sidecar_digest.DIGEST_NAME, caught.exception.path)

    def test_malformed_digest_file(self):
        (self.root / sidecar_digest.DIGEST_NAME).write_text("{not json")
        self.assertIn("SIDECAR_TAMPERED", sidecar.check_digest(self.root))

    def test_five_hundred_files_are_fast(self):
        big = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, big, True)
        for index in range(500):
            folder = big / f"d{index % 20}"
            folder.mkdir(exist_ok=True)
            (folder / f"f{index}").write_bytes(bytes([index % 256]) * 4096)
        sidecar_digest.write(big, "0.1.0")
        started = time.monotonic()
        self.assertTrue(sidecar_digest.verify(big))
        self.assertLess(time.monotonic() - started, 2.0)
        (big / "d3" / "f3").write_bytes(b"changed")
        with self.assertRaises(sidecar_digest.SidecarTampered):
            sidecar_digest.verify(big)

    def test_reads_in_blocks(self):
        big = self.root / "big.bin"
        with open(big, "wb") as handle:
            handle.write(os.urandom(1024) * (2 * sidecar_digest.BLOCK // 1024 + 3))
        sidecar_digest.write(self.root, "0.1.0")
        self.assertTrue(sidecar_digest.verify(self.root))

    def test_frozen_root_is_none_from_sources(self):
        self.assertIsNone(sidecar_digest.frozen_root())
        self.assertIsNone(sidecar.check_digest())

    def test_command_line(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(0, sidecar_digest.main(["verify", str(self.root)]))
            (self.root / "gui-backend").write_bytes(b"other")
            self.assertEqual(3, sidecar_digest.main(["verify", str(self.root)]))
        self.assertIn("SIDECAR_TAMPERED: gui-backend", err.getvalue())


class TestStartRefusal(unittest.TestCase):
    def test_serve_sidecar_exits_3_before_reading_stdin_or_binding(self):
        err = io.StringIO()
        message = "SIDECAR_TAMPERED: x.so (changed)"
        with mock.patch.object(sidecar, "check_digest", return_value=message), \
                mock.patch.object(sidecar, "stdin_stream", side_effect=AssertionError("stdin read")), \
                contextlib.redirect_stderr(err):
            code = cli.main(["serve", "--sidecar"])
        self.assertEqual(3, code)
        self.assertIn(message, err.getvalue())


if __name__ == "__main__":
    unittest.main()
