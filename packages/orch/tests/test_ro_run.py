from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ro-run.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


def landlock_available() -> bool:
    return run("--no-default-rw", "--", "true").returncode == 0


@unittest.skipUnless(sys.platform.startswith("linux") and landlock_available(), "needs Linux Landlock")
class ReadOnlyRunTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.writable = self.base / "rw"
        self.closed = self.base / "ro"
        self.writable.mkdir()
        self.closed.mkdir()
        (self.closed / "kept.txt").write_text("kept", encoding="utf-8")

    def tearDown(self):
        for path in sorted(self.base.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.base.rmdir()

    def shell(self, script: str) -> subprocess.CompletedProcess[str]:
        return run("--no-default-rw", "--rw", str(self.writable), "--", "sh", "-c", script)

    def test_writes_only_inside_granted_directories(self):
        self.assertEqual(self.shell(f"echo ok > {self.writable}/new.txt").returncode, 0)
        self.assertEqual((self.writable / "new.txt").read_text(encoding="utf-8"), "ok\n")
        denied = self.shell(f"echo no > {self.closed}/new.txt")
        self.assertNotEqual(denied.returncode, 0)
        self.assertFalse((self.closed / "new.txt").exists())

    def test_reads_everywhere_and_cannot_delete_or_rename(self):
        self.assertEqual(self.shell(f"cat {self.closed}/kept.txt").stdout, "kept")
        self.assertNotEqual(self.shell(f"rm {self.closed}/kept.txt").returncode, 0)
        self.assertNotEqual(self.shell(f"mv {self.closed}/kept.txt {self.writable}/moved.txt").returncode, 0)
        self.assertEqual((self.closed / "kept.txt").read_text(encoding="utf-8"), "kept")

    def test_children_inherit_the_restriction(self):
        nested = self.shell(f"sh -c 'python3 -c \"open(\\\"{self.closed}/child.txt\\\", \\\"w\\\")\"'")
        self.assertNotEqual(nested.returncode, 0)
        self.assertFalse((self.closed / "child.txt").exists())

    def test_usage_errors(self):
        self.assertEqual(run("true").returncode, 2)
        self.assertEqual(run("--bogus", "--", "true").returncode, 2)
        missing = run("--no-default-rw", "--", "definitely-not-a-command-xyz")
        self.assertEqual(missing.returncode, 127)
        self.assertTrue(missing.stderr.startswith("EXEC_FAILED:"))


if __name__ == "__main__":
    unittest.main()
