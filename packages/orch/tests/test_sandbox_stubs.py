"""SANDBOX_STUBS_REMOVED: the empty read-only placeholders a Claude Code sandbox leaves under ``.claude/`` when a
sandboxed command is killed are removed at run start or resume; real files, tracked files and young placeholders stay."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from orch.conductor import scope


class SandboxStubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        (self.project / ".claude").mkdir()

    def stub(self, path: str, age: float = 7200) -> Path:
        target = self.project / path
        target.write_bytes(b"")
        target.chmod(0o444)
        os.utime(target, (time.time() - age, time.time() - age))
        return target

    def test_an_old_placeholder_is_removed_and_nothing_else(self):
        self.stub(".claude/settings.json")
        self.stub(".claude/hooks")
        self.stub(".claude/loop.md", age=60)  # young: a sandboxed command may still run
        (self.project / ".claude/settings.local.json").write_text("{}", encoding="utf-8")  # a real file
        empty_writable = self.project / ".mcp.json"
        empty_writable.write_bytes(b"")  # empty but writable: not a placeholder
        os.utime(empty_writable, (time.time() - 7200, time.time() - 7200))
        self.stub(".claude/other.json")  # not a protected path: never touched
        found = scope.leftover_stubs(self.project, time.time())
        self.assertEqual(found, [".claude/hooks", ".claude/settings.json"])
        self.assertEqual(scope.remove_stubs(self.project, found), found)
        self.assertFalse((self.project / ".claude/settings.json").exists())
        for kept in (".claude/loop.md", ".claude/settings.local.json", ".mcp.json", ".claude/other.json"):
            self.assertTrue((self.project / kept).exists(), kept)

    def test_a_tracked_empty_read_only_file_is_kept(self):
        self.stub(".claude/launch.json")
        subprocess.run(["git", "-C", str(self.project), "add", ".claude/launch.json"], check=True)
        self.assertEqual(scope.leftover_stubs(self.project, time.time()), [])

    def test_remove_checks_again_and_refuses_other_paths(self):
        real = self.project / ".claude/settings.json"
        real.write_text("{}", encoding="utf-8")
        self.assertEqual(scope.remove_stubs(self.project, [".claude/settings.json", "README.md"]), [])
        self.assertTrue(real.exists())


if __name__ == "__main__":
    unittest.main()
