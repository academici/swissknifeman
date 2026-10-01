"""Hermetic checks for the gitignored aggregate docs cache."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class DocsSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "scripts").mkdir()
        source = Path(__file__).resolve().parents[3] / "scripts" / "docs-sync.sh"
        self.script = self.root / "scripts" / "docs-sync.sh"
        shutil.copy2(source, self.script)
        package_docs = self.root / "packages" / "task" / "docs"
        (package_docs / ".vitepress").mkdir(parents=True)
        (package_docs / "index.md").write_text("# Task\n", encoding="utf-8")
        (package_docs / ".vitepress" / "config.mts").write_text(
            "export default {}\n", encoding="utf-8")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.script), *args], cwd=self.root,
            text=True, capture_output=True, check=False,
        )

    def test_check_accepts_missing_gitignored_destination(self) -> None:
        result = self._run("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "docs" / "task").exists())

    def test_check_rejects_existing_stale_destination(self) -> None:
        destination = self.root / "docs" / "task"
        destination.mkdir(parents=True)
        (destination / "index.md").write_text("# Stale\n", encoding="utf-8")
        result = self._run("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/task is deprecated", result.stderr)

    def test_write_then_check_is_green_and_excludes_vitepress_config(self) -> None:
        written = self._run()
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertFalse((self.root / "docs" / "task" / ".vitepress").exists())
        checked = self._run("--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
