#!/usr/bin/env python3
"""Tests of scripts/dev-sandbox.sh (PLAN3 D10): isolation, copies, guarded removal.

Every sandbox lives under a TMPDIR owned by the test; the real /tmp and the real HOME are not touched.
"""
from __future__ import annotations

import os
import pwd
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev-sandbox.sh"
START = "# --- swissknifeman dev-clone guard"
END = "# --- end dev-clone guard ---"
REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-sandbox-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tmpdir = self.tmp / "tmp"
        self.tmpdir.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k not in {"SKM_SANDBOX", "SKM_DEV_ALLOW_LIVE"}}
        self.env["TMPDIR"] = str(self.tmpdir)
        self.pid = os.getpid()

    def sandbox(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SCRIPT), *args], env=self.env, capture_output=True, text=True,
                              check=False)

    def new(self, *args: str) -> Path:
        result = self.sandbox("new", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(result.stdout.strip().splitlines()[-1])

    def make_project(self, name: str = "proj") -> Path:
        project = self.tmp / name
        project.mkdir()
        (project / "a.txt").write_text("a\n", encoding="utf-8")
        (project / "node_modules").mkdir()
        (project / "node_modules" / "skip.js").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        return project

    def snapshot(self, path: Path) -> list[tuple[str, int]]:
        return sorted((str(p.relative_to(path)), p.stat().st_size) for p in path.rglob("*") if p.is_file())

    def test_new_creates_isolated_environment_and_copies_project(self) -> None:
        project = self.make_project()
        before = self.snapshot(project)
        status_before = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True,
                                       text=True).stdout
        directory = self.new("--name", f"t{self.pid}", "--copy", str(project))
        self.assertEqual(directory, self.tmpdir / f"skm-sandbox-t{self.pid}")
        marker = (directory / ".skm-sandbox").read_text(encoding="utf-8")
        self.assertRegex(marker, r"^created=\d{4}-\d\d-\d\dT[\d:]+Z\nclone=" + re.escape(str(ROOT)) + r"\n$")
        for sub in (".config", ".local/state", ".local/share", ".cache", ".local/bin"):
            self.assertTrue((directory / "home" / sub).is_dir(), sub)
        self.assertTrue((directory / "env.sh").is_file())
        self.assertEqual((directory / "projects" / "proj" / "a.txt").read_text(encoding="utf-8"), "a\n")
        self.assertFalse((directory / "projects" / "proj" / "node_modules").exists() and
                         shutil.which("rsync") is not None, "node_modules must be excluded when rsync is present")
        self.assertEqual(self.snapshot(project), before, "the original project changed")
        status_after = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True,
                                      text=True).stdout
        self.assertEqual(status_after, status_before)

    def test_new_without_name_picks_unique_directory(self) -> None:
        first, second = self.new(), self.new()
        self.assertNotEqual(first, second)
        self.assertTrue(first.name.startswith("skm-sandbox-") and first.parent == self.tmpdir)

    def test_new_refuses_existing_name_and_bad_names(self) -> None:
        self.new("--name", "dup")
        again = self.sandbox("new", "--name", "dup")
        self.assertEqual(again.returncode, 1)
        self.assertIn("SANDBOX_EXISTS", again.stderr)
        for bad in ("../x", "a/b", ".hidden", "sp ace"):
            result = self.sandbox("new", "--name", bad)
            self.assertEqual(result.returncode, 1, bad)
            self.assertIn("SANDBOX_INVALID", result.stderr)

    def test_new_refuses_missing_copy_source_and_duplicate_basenames(self) -> None:
        missing = self.sandbox("new", "--name", "m", "--copy", str(self.tmp / "nope"))
        self.assertEqual(missing.returncode, 1)
        self.assertIn("SANDBOX_COPY", missing.stderr)
        one = self.make_project("one")
        other = self.tmp / "sub"
        other.mkdir()
        (other / "one").mkdir()
        clash = self.sandbox("new", "--name", "c", "--copy", str(one), "--copy", str(other / "one"))
        self.assertEqual(clash.returncode, 1)
        self.assertIn("SANDBOX_COPY", clash.stderr)

    def test_run_uses_sandbox_home_and_returns_exit_code(self) -> None:
        directory = self.new("--name", f"r{self.pid}")
        result = self.sandbox("run", str(directory), "--", "bash", "-c", "echo $HOME; echo $SKM_SANDBOX; "
                              "echo $XDG_CONFIG_HOME; echo $GIT_CONFIG_GLOBAL")
        self.assertEqual(result.returncode, 0, result.stderr)
        home, sandbox_var, xdg, git_global = result.stdout.splitlines()
        self.assertEqual(home, str(directory / "home"))
        self.assertEqual(sandbox_var, str(directory))
        self.assertEqual(xdg, str(directory / "home" / ".config"))
        self.assertEqual(git_global, str(directory / "home" / ".gitconfig"))
        self.assertEqual(self.sandbox("run", str(directory), "--", "bash", "-c", "exit 7").returncode, 7)
        self.assertEqual(self.sandbox("run", str(directory), "--", "bash", "-c", "echo $PATH").stdout.split(":")[1:2],
                         [str(ROOT / "bin")])

    def test_run_without_marker_is_refused(self) -> None:
        bare = self.tmpdir / "skm-sandbox-bare"
        bare.mkdir()
        result = self.sandbox("run", str(bare), "--", "bash", "-c", "echo SHOULD-NOT-RUN")
        self.assertEqual(result.returncode, 1)
        self.assertIn("SANDBOX_INVALID", result.stderr)
        self.assertNotIn("SHOULD-NOT-RUN", result.stdout)

    def test_dev_clone_guard_passes_inside_sandbox(self) -> None:
        block = re.search(re.escape(START) + r".*?" + re.escape(END),
                          (ROOT / "install.sh").read_text(encoding="utf-8"), re.S).group(0)
        repo = self.tmp / "devrepo"
        tool = repo / "pkg" / "bin" / "tool"
        tool.parent.mkdir(parents=True)
        (repo / ".swissknifeman-dev").write_text("branch=x\n", encoding="utf-8")
        tool.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + block + "\necho PASSED\n", encoding="utf-8")
        tool.chmod(0o755)
        outside = subprocess.run([str(tool)], env={**self.env, "HOME": REAL_HOME}, capture_output=True, text=True)
        self.assertEqual(outside.returncode, 3, "the synthetic tool must be guarded against the real HOME")
        directory = self.new("--name", f"g{self.pid}")
        inside = self.sandbox("run", str(directory), "--", str(tool))
        self.assertEqual(inside.returncode, 0, inside.stderr)
        self.assertIn("PASSED", inside.stdout)

    def test_list_shows_only_marked_sandboxes(self) -> None:
        project = self.make_project()
        directory = self.new("--name", "l1", "--copy", str(project))
        (self.tmpdir / "skm-sandbox-unmarked").mkdir()
        (self.tmpdir / "other").mkdir()
        listing = self.sandbox("list")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        lines = listing.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, listing.stdout)
        self.assertTrue(lines[0].startswith(str(directory)))
        self.assertIn("projects=proj", lines[0])

    def test_remove_deletes_sandbox_only(self) -> None:
        keep = self.tmpdir / "keep"
        keep.mkdir()
        directory = self.new("--name", "x1")
        result = self.sandbox("remove", str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(directory.exists())
        self.assertTrue(keep.exists())

    def test_remove_refuses_everything_that_is_not_a_sandbox(self) -> None:
        unmarked = self.tmpdir / "skm-sandbox-unmarked"
        unmarked.mkdir()
        (unmarked / "keep.txt").write_text("k\n", encoding="utf-8")
        wrong_name = self.tmpdir / "other-name"
        wrong_name.mkdir()
        (wrong_name / ".skm-sandbox").write_text("created=x\n", encoding="utf-8")
        nested_parent = self.tmpdir / "holder"
        nested_parent.mkdir()
        nested = nested_parent / "skm-sandbox-nested"
        nested.mkdir()
        (nested / ".skm-sandbox").write_text("created=x\n", encoding="utf-8")
        real = self.new("--name", "real")
        link = self.tmpdir / "skm-sandbox-link"
        link.symlink_to(real)
        for target in (unmarked, wrong_name, nested, link, self.tmpdir, Path("/"), self.tmp / "missing"):
            result = self.sandbox("remove", str(target))
            self.assertEqual(result.returncode, 1, f"{target}: {result.stdout}{result.stderr}")
            self.assertIn("SANDBOX_INVALID", result.stderr, str(target))
        self.assertTrue((unmarked / "keep.txt").exists())
        self.assertTrue(wrong_name.exists() and nested.exists() and real.exists() and self.tmpdir.exists())

    def test_usage_errors_exit_2(self) -> None:
        self.assertEqual(self.sandbox().returncode, 2)
        self.assertEqual(self.sandbox("bogus").returncode, 2)
        self.assertEqual(self.sandbox("run", "dir").returncode, 2)
        self.assertEqual(self.sandbox("remove").returncode, 2)
        self.assertEqual(self.sandbox("--help").returncode, 0)


if __name__ == "__main__":
    unittest.main()
