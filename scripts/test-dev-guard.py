#!/usr/bin/env python3
"""Tests of the dev-clone guard block and scripts/dev-clone.sh (PLAN3 D10, D13).

Real installers and CLIs are never run here: the guard behaviour is checked on a synthetic script.
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
START = "# --- swissknifeman dev-clone guard"
END = "# --- end dev-clone guard ---"
ENTRY_POINTS = [
    "bin/swissknifeman",
    "packages/analyst/bin/analyst",
    "packages/brain/bin/brain",
    "packages/gui/bin/gui",
    "packages/harness/bin/harness",
    "packages/maind/bin/maind",
    "packages/skiller/bin/skiller",
    "install.sh",
    "packages/analyst/install.sh",
    "packages/harness/install.sh",
    "packages/maind/install.sh",
    "packages/skiller/install.sh",
    "scripts/bootstrap-machine.sh",
]
REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir


def blocks(text: str) -> list[str]:
    return re.findall(re.escape(START) + r".*?" + re.escape(END), text, re.S)


def executable_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip() and not line.lstrip().startswith("#")]


class EntryPointBlockTests(unittest.TestCase):
    def test_exactly_one_identical_block_per_file(self) -> None:
        found = {}
        for name in ENTRY_POINTS:
            found[name] = blocks((ROOT / name).read_text(encoding="utf-8"))
            self.assertEqual(len(found[name]), 1, f"{name}: expected exactly one guard block")
        self.assertEqual(len({b[0] for b in found.values()}), 1, "guard blocks differ between files")

    def test_block_follows_set_euo_pipefail(self) -> None:
        for name in ENTRY_POINTS:
            lines = (ROOT / name).read_text(encoding="utf-8").split("\n")
            index = next(i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("#"))
            self.assertEqual(lines[index], "set -euo pipefail", f"{name}: first executable line")
            self.assertTrue(lines[index + 1].startswith(START), f"{name}: guard must follow set -euo pipefail")
            self.assertEqual(len(executable_lines("\n".join(lines[: index + 1]))), 1, name)


class GuardBehaviourTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-guard-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        block = blocks((ROOT / "install.sh").read_text(encoding="utf-8"))[0]
        self.repo = self.tmp / "repo"
        tool = self.repo / "pkg" / "bin" / "tool"
        tool.parent.mkdir(parents=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + block + "\necho PASSED\n", encoding="utf-8")
        tool.chmod(0o755)
        self.tool = tool
        self.marker = self.repo / ".swissknifeman-dev"

    def run_tool(self, path: Path, home: str, **env: str) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if k not in {"HOME", "SKM_DEV_ALLOW_LIVE"}}
        return subprocess.run([str(path)], env={**base, "HOME": home, **env},
                              capture_output=True, text=True, check=False)

    def test_marker_and_real_home_refuses(self) -> None:
        self.marker.write_text("branch=x\n", encoding="utf-8")
        result = self.run_tool(self.tool, REAL_HOME)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("SKM_DEV_GUARD", result.stderr)
        self.assertNotIn("PASSED", result.stdout)

    def test_marker_and_tmp_home_passes(self) -> None:
        self.marker.write_text("branch=x\n", encoding="utf-8")
        home = self.tmp / "home"
        home.mkdir()
        result = self.run_tool(self.tool, str(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_allow_live_override_passes(self) -> None:
        self.marker.write_text("branch=x\n", encoding="utf-8")
        result = self.run_tool(self.tool, REAL_HOME, SKM_DEV_ALLOW_LIVE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_no_marker_real_home_passes(self) -> None:
        result = self.run_tool(self.tool, REAL_HOME)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_symlink_resolves_to_real_path(self) -> None:
        self.marker.write_text("branch=x\n", encoding="utf-8")
        link_dir = self.tmp / "elsewhere" / "bin"
        link_dir.mkdir(parents=True)
        link = link_dir / "tool"
        link.symlink_to(self.tool)
        result = self.run_tool(link, REAL_HOME)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("SKM_DEV_GUARD", result.stderr)


class DevCloneScriptTests(unittest.TestCase):
    SCRIPT = ROOT / "scripts" / "dev-clone.sh"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skm-devclone-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update({"HOME": str(self.tmp / "home"), "GIT_CONFIG_NOSYSTEM": "1",
                         "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})
        (self.tmp / "home").mkdir()
        self.remote = self.tmp / "remote.git"
        self.repo = self.tmp / "repo"
        self.git(self.tmp, "init", "--bare", "-b", "main", str(self.remote))
        self.git(self.tmp, "init", "-b", "main", str(self.repo))
        self.git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / ".gitignore").write_text("/.swissknifeman-dev\n", encoding="utf-8")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-m", "base")
        self.git(self.repo, "push", "-u", "origin", "main")

    def git(self, cwd: Path, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, check=True)
        return done.stdout

    def dev(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.SCRIPT), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, check=False)

    def test_init_refused_on_main(self) -> None:
        result = self.dev("init")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DEV_CLONE_ON_MAIN", result.stderr)
        self.assertFalse((self.repo / ".swissknifeman-dev").exists())

    def test_init_is_idempotent_and_status_reports(self) -> None:
        self.git(self.repo, "checkout", "-b", "feature")
        first = self.dev("init")
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = self.repo / ".swissknifeman-dev"
        content = marker.read_text(encoding="utf-8")
        self.assertRegex(content, r"^branch=feature\ncreated=\d{4}-\d\d-\d\dT[\d:]+Z\n$")
        second = self.dev("init")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), content)
        status = self.dev("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("branch: feature", status.stdout)
        self.assertIn("marker: present", status.stdout)
        self.assertIn("vs origin/main: ahead 0 / behind 0", status.stdout)
        self.assertIn("vs origin/feature: n/a", status.stdout)

    def test_init_sets_upstream_when_remote_branch_exists(self) -> None:
        self.git(self.repo, "checkout", "-b", "feature")
        self.git(self.repo, "push", "origin", "feature")
        result = self.dev("init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.repo, "rev-parse", "--abbrev-ref", "feature@{upstream}").strip(),
                         "origin/feature")

    def test_unknown_command_is_usage_error(self) -> None:
        self.assertEqual(self.dev("nope").returncode, 2)
        self.assertEqual(subprocess.run(["bash", str(self.SCRIPT)], cwd=self.repo, env=self.env,
                                        capture_output=True, text=True, check=False).returncode, 2)

    def test_sync_main_refuses_dirty_tree(self) -> None:
        self.git(self.repo, "checkout", "-b", "feature")
        (self.repo / "a.txt").write_text("dirty\n", encoding="utf-8")
        result = self.dev("sync-main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DEV_CLONE_DIRTY", result.stderr)

    def test_sync_main_merges_origin_main(self) -> None:
        self.git(self.repo, "checkout", "-b", "feature")
        other = self.tmp / "other"
        self.git(self.tmp, "clone", str(self.remote), str(other))
        (other / "b.txt").write_text("b\n", encoding="utf-8")
        self.git(other, "add", "-A")
        self.git(other, "commit", "-m", "from main")
        self.git(other, "push", "origin", "main")
        result = self.dev("sync-main")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / "b.txt").exists())

    def test_sync_main_reports_conflict_and_leaves_merge(self) -> None:
        self.git(self.repo, "checkout", "-b", "feature")
        (self.repo / "a.txt").write_text("feature\n", encoding="utf-8")
        self.git(self.repo, "commit", "-am", "feature change")
        other = self.tmp / "other"
        self.git(self.tmp, "clone", str(self.remote), str(other))
        (other / "a.txt").write_text("main\n", encoding="utf-8")
        self.git(other, "commit", "-am", "main change")
        self.git(other, "push", "origin", "main")
        result = self.dev("sync-main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DEV_CLONE_CONFLICT", result.stderr)
        self.assertIn("a.txt", result.stderr)
        self.assertEqual(self.git(self.repo, "diff", "--name-only", "--diff-filter=U").strip(), "a.txt")


if __name__ == "__main__":
    unittest.main()
