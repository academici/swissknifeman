from __future__ import annotations

from pathlib import Path
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ro-run.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


def landlock_available() -> bool:
    return run("--no-default-rw", "--", "true").returncode == 0


def load_script():
    spec = importlib.util.spec_from_file_location("ro_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProtectValidationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script()

    def refusal(self, argv, code):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            self.module._parse(argv + ["--", "true"])
        self.assertEqual(raised.exception.code, 3)
        self.assertTrue(stderr.getvalue().startswith(code + ": "), stderr.getvalue())
        return stderr.getvalue().strip()

    def test_default_writable_roots_and_their_children_are_refused(self):
        roots = [os.path.realpath(os.path.expanduser(root)) for root in self.module.DEFAULT_WRITABLE]
        for root in roots:
            for directory in (root, os.path.join(root, "checkout")):
                with self.subTest(directory=directory):
                    message = self.refusal(["--protect", directory], "RO_RUN_PROTECT_OVERLAP")
                    prefix = f"RO_RUN_PROTECT_OVERLAP: {directory} is inside writable "
                    self.assertTrue(message.startswith(prefix), message)
                    # HOME can be under /tmp: either overlapping default root is valid.
                    reported_root = message[len(prefix):]
                    self.assertIn(reported_root, roots)
                    self.assertEqual(os.path.commonpath((directory, reported_root)), reported_root)

    def test_symlinked_protected_directory_is_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "checkout"
            link.symlink_to(tmp, target_is_directory=True)
            message = self.refusal(["--protect", str(link)], "RO_RUN_PROTECT_OVERLAP")
            self.assertIn(os.path.realpath(tmp), message)

    def test_overlapping_checkout_stops_before_the_command_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run("--protect", tmp, "--", sys.executable, "-I", "-c", "raise AssertionError('command started')")
            self.assertEqual(done.returncode, 3)
            self.assertTrue(done.stderr.startswith("RO_RUN_PROTECT_OVERLAP:"), done.stderr)

    def test_vendor_symlink_and_parent_symlink_escape_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            checkout, outside = base / "checkout", base / "outside"
            checkout.mkdir()
            outside.mkdir()
            (outside / "cache").mkdir()
            vendor = checkout / "vendor"
            vendor.symlink_to(outside, target_is_directory=True)
            # Neutral roots let this path-validation test run without a kernel sandbox or a home write.
            with mock.patch.object(self.module, "DEFAULT_WRITABLE", ("/dev",)):
                for grant in (vendor, str(vendor) + "/", str(vendor) + "/.", vendor / "cache"):
                    self.assertEqual(self.refusal(["--protect", str(checkout), "--rw", str(grant)],
                                                 "RO_RUN_RW_ESCAPE"), f"RO_RUN_RW_ESCAPE: {grant}")
                vendor.unlink()
                vendor.symlink_to(checkout, target_is_directory=True)
                for grant in (vendor, str(vendor) + "/", str(vendor) + "/."):
                    self.refusal(["--protect", str(checkout), "--rw", str(grant)], "RO_RUN_RW_ESCAPE")

    def test_protect_is_repeatable_and_resolves_all_grants(self):
        with mock.patch.object(self.module, "DEFAULT_WRITABLE", ("/dev",)):
            writable, command, protected = self.module._parse([
                "--no-default-rw", "--protect", "/work/one/../one", "--protect", "/work/two",
                "--rw", "/work/one/vendor/../vendor", "--", "true"])
        self.assertEqual(writable, ["/work/one/vendor"])
        self.assertEqual(protected, ["/work/one", "/work/two"])
        self.assertEqual(command, ["true"])

    def test_protect_requires_abi_three_before_creating_a_ruleset(self):
        for abi in (0, 1, 2):
            stderr = io.StringIO()
            with mock.patch.object(self.module.platform, "system", return_value="Linux"), \
                    mock.patch.object(self.module, "_landlock_abi", return_value=abi), \
                    contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                self.module.restrict([], ["/work"])
            self.assertEqual(raised.exception.code, 3)
            self.assertEqual(stderr.getvalue().strip(), f"LANDLOCK_ABI_TOO_OLD: {abi}")


class ProtectedRunTests(unittest.TestCase):
    def setUp(self):
        # A repository-local checkout avoids both /tmp and HOME (the test runner puts HOME in /tmp).
        tmp = tempfile.TemporaryDirectory(prefix=".ro-run-test-", dir=SCRIPT.parents[3])
        self.addCleanup(tmp.cleanup)
        self.checkout = Path(tmp.name)
        self.vendor = self.checkout / "vendor"
        self.vendor.mkdir()
        self.kept = self.checkout / "kept.txt"
        self.kept.write_text("kept", encoding="utf-8")
        probe = self.python("pass")
        if probe.returncode == 3 and ("LANDLOCK_UNAVAILABLE:" in probe.stderr or "LANDLOCK_ABI_TOO_OLD:" in probe.stderr):
            self.skipTest("LANDLOCK_UNAVAILABLE: needs Linux Landlock ABI >= 3; " + probe.stderr.strip())
        self.assertEqual(probe.returncode, 0, probe.stderr)

    def python(self, code):
        return run("--protect", str(self.checkout), "--rw", str(self.vendor), "--",
                   sys.executable, "-I", "-c", "from pathlib import Path; import os; " + code)

    def test_protected_writes_are_eacces_but_vendor_remains_writable(self):
        denied = self.python(f"Path({str(self.checkout / 'new')!r}).write_text('no')")
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("PermissionError: [Errno 13]", denied.stderr)
        self.assertFalse((self.checkout / "new").exists())
        allowed = self.python(f"Path({str(self.vendor / 'new')!r}).write_text('ok')")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual((self.vendor / "new").read_text(), "ok")

    def test_truncate_rename_delete_and_symlink_are_denied(self):
        for code in (f"os.truncate({str(self.kept)!r}, 0)",
                     f"os.rename({str(self.kept)!r}, {str(self.vendor / 'moved')!r})",
                     f"os.unlink({str(self.kept)!r})",
                     f"os.symlink('/tmp', {str(self.checkout / 'link')!r})"):
            with self.subTest(code=code):
                denied = self.python(code)
                self.assertNotEqual(denied.returncode, 0, denied.stderr)
                self.assertIn("PermissionError", denied.stderr)
                self.assertEqual(self.kept.read_text(), "kept")

    def test_no_protect_preserves_default_writes_and_symlink_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "vendor"
            link.symlink_to(self.vendor, target_is_directory=True)
            done = run("--rw", str(link), "--", sys.executable, "-I", "-c",
                       f"from pathlib import Path; Path({str(link / 'legacy')!r}).write_text('ok'); "
                       f"Path({str(Path(tmp) / 'default')!r}).write_text('ok')")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((self.vendor / "legacy").read_text(), "ok")

    def test_vendor_symlink_stops_before_the_command_starts(self):
        with tempfile.TemporaryDirectory() as outside:
            self.vendor.rmdir()
            self.vendor.symlink_to(outside, target_is_directory=True)
            done = self.python("raise AssertionError('command started')")
            self.assertEqual(done.returncode, 3)
            self.assertEqual(done.stderr.strip(), f"RO_RUN_RW_ESCAPE: {self.vendor}")


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
