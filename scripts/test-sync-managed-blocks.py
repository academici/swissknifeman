#!/usr/bin/env python3
"""Managed-blocks tool conformance tests (tmpdir, stdlib)."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync-managed-blocks.py"
SPEC = importlib.util.spec_from_file_location("sync_managed_blocks", SCRIPT)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

TEXT = "Line one.\n\nLine two."
SOURCE = f"# Source\n<!-- export:begin m -->\n{TEXT}\n<!-- export:end m -->\nafter\n"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def target_file(text, block_id="b", source="src.md", anchor="m", tail="tail\n"):
    return (
        f"head\n<!-- managed:begin id={block_id} source={source}#{anchor} sha256={sha(text)} -->\n"
        f"{text}\n<!-- managed:end id={block_id} -->\n{tail}"
    )


class ManagedBlocksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "configs").mkdir()
        self.set_blocks([{"id": "b", "source": "src.md", "anchor": "m", "target": "dst.md"}])

    def set_blocks(self, blocks):
        (self.root / "configs/managed-blocks.json").write_text(
            json.dumps({"version": 1, "blocks": blocks}), encoding="utf-8"
        )

    def put(self, name, text):
        (self.root / name).write_bytes(text.encode("utf-8"))

    def get(self, name):
        return (self.root / name).read_bytes().decode("utf-8")

    def run_tool(self, mode):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(["--root", str(self.root), mode])
        return code, out.getvalue()

    def test_in_sync_is_ok(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file(TEXT))
        self.assertEqual(self.run_tool("--check"), (0, "managed-blocks: OK\n"))

    def test_empty_block_list_is_ok(self):
        self.set_blocks([])
        self.assertEqual(self.run_tool("--check"), (0, "managed-blocks: OK\n"))

    def test_changed_source_is_drift(self):
        self.put("src.md", SOURCE.replace("Line two.", "Line two changed."))
        self.put("dst.md", target_file(TEXT))
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT b: dst.md", out)

    def test_hand_edited_target_is_drift(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file(TEXT).replace("Line one.", "Edited."))
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT b:", out)

    def test_stale_sha_in_header_is_drift(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file(TEXT).replace(sha(TEXT), "0" * 64))
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT b:", out)

    def test_missing_export_marker_in_source(self):
        self.put("src.md", "# no markers\n")
        self.put("dst.md", target_file(TEXT))
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("MISSING b:", out)

    def test_missing_block_in_target(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", "head\nno block here\n")
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("MISSING b:", out)

    def test_missing_source_file(self):
        self.put("dst.md", target_file(TEXT))
        code, out = self.run_tool("--check")
        self.assertEqual(code, 1)
        self.assertIn("MISSING b:", out)

    def test_write_then_check_is_ok_and_keeps_the_rest(self):
        self.put("src.md", SOURCE.replace("Line two.", "Line two changed."))
        self.put("dst.md", target_file(TEXT, tail="tail\nmore\n"))
        code, out = self.run_tool("--write")
        self.assertEqual(code, 0)
        self.assertIn("WRITE b: dst.md", out)
        new_text = "Line one.\n\nLine two changed."
        self.assertEqual(self.get("dst.md"), target_file(new_text, tail="tail\nmore\n"))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_write_is_idempotent(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file("stale"))
        self.run_tool("--write")
        first = self.get("dst.md")
        code, out = self.run_tool("--write")
        self.assertEqual((code, self.get("dst.md")), (0, first))
        self.assertNotIn("WRITE", out)

    def test_write_without_block_in_target_fails_and_writes_nothing(self):
        self.set_blocks(
            [
                {"id": "b", "source": "src.md", "anchor": "m", "target": "dst.md"},
                {"id": "c", "source": "src.md", "anchor": "m", "target": "other.md"},
            ]
        )
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file("stale"))
        self.put("other.md", "no block\n")
        code, out = self.run_tool("--write")
        self.assertEqual(code, 1)
        self.assertIn("MISSING c:", out)
        self.assertEqual(self.get("dst.md"), target_file("stale"))

    def test_crlf_source_is_normalized(self):
        self.put("src.md", SOURCE.replace("\n", "\r\n"))
        self.put("dst.md", target_file(TEXT))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_crlf_target_keeps_its_line_endings_on_write(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file("stale").replace("\n", "\r\n"))
        self.assertEqual(self.run_tool("--write")[0], 0)
        self.assertEqual(self.get("dst.md"), target_file(TEXT).replace("\n", "\r\n"))
        self.assertEqual(self.run_tool("--check")[0], 0)

    def test_two_blocks_in_one_target(self):
        self.set_blocks(
            [
                {"id": "b", "source": "src.md", "anchor": "m", "target": "dst.md"},
                {"id": "c", "source": "src.md", "anchor": "n", "target": "dst.md"},
            ]
        )
        self.put("src.md", SOURCE + "<!-- export:begin n -->\nSecond.\n<!-- export:end n -->\n")
        second = "<!-- managed:begin id=c source=src.md#n sha256={} -->\nold\n<!-- managed:end id=c -->\n".format(sha("old"))
        self.put("dst.md", target_file("stale") + second)
        self.assertEqual(self.run_tool("--write")[0], 0)
        self.assertEqual(self.run_tool("--check")[0], 0)
        self.assertIn("\nSecond.\n", self.get("dst.md"))

    def test_invalid_config_exits_with_message(self):
        (self.root / "configs/managed-blocks.json").write_text('{"version": 2, "blocks": []}', encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("--check")
        self.assertIn("ERROR config", str(caught.exception))

    def test_path_escaping_root_is_rejected(self):
        self.set_blocks([{"id": "b", "source": "../src.md", "anchor": "m", "target": "dst.md"}])
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("--check")
        self.assertIn("escapes the root", str(caught.exception))

    def test_cli_exit_codes(self):
        self.put("src.md", SOURCE)
        self.put("dst.md", target_file("stale"))
        cmd = [sys.executable, str(SCRIPT), "--root", str(self.root), "--check"]
        failed = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual((failed.returncode, failed.stdout.strip()), (1, "DRIFT b: dst.md"))
        subprocess.run(cmd[:-1] + ["--write"], check=True, capture_output=True)
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 0)

    def test_repo_config_is_in_sync(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(["--root", str(ROOT), "--check"]), 0)


if __name__ == "__main__":
    unittest.main()
