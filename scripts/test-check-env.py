#!/usr/bin/env python3
"""Tests scripts/check-env.sh — a fake PATH decides which programs the script can see."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check-env.sh"
BASH = shutil.which("bash") or "/bin/bash"
# Programs the script itself needs for its own work (never a check subject).
TOOLS = ("uname", "sort", "head", "sed", "cat", "dirname", "grep", "tr", "cut", "timeout", "printf")


def make_path(root: Path, programs: dict) -> str:
    """PATH holding the plain tools plus `programs`: name -> shell body."""
    bin_dir = root / "bin"
    shutil.rmtree(bin_dir, ignore_errors=True)
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    for name, body in programs.items():
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
    return str(bin_dir)


class CheckEnvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, programs, *args):
        python = shutil.which("python3")
        programs = {"python3": f'exec "{python}" "$@"', "git": 'echo "git version 2.40.0"', **programs}
        path = make_path(self.root, programs)
        env = {"PATH": path, "HOME": str(self.home)}
        done = subprocess.run([BASH, str(SCRIPT), "--json", *args], capture_output=True, text=True, env=env, timeout=60)
        return done.returncode, json.loads(done.stdout)

    def items(self, report):
        return {item["name"]: item for item in report["items"]}

    def test_required_present_recommended_missing_warns_but_passes(self):
        code, report = self.run_script({})
        self.assertEqual(report["schema"], "skm-env-check/v1")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["required_missing"], 0)
        self.assertGreater(report["recommended_missing"], 0)
        items = self.items(report)
        self.assertEqual(items["python3"]["status"], "ok")
        self.assertEqual(items["jq"]["status"], "missing")
        self.assertIn("jq", items["jq"]["fix"])

    def test_strict_turns_a_missing_recommended_item_into_failure(self):
        code, report = self.run_script({}, "--strict")
        self.assertEqual(code, 1)
        self.assertEqual(report["required_missing"], 0)

    def test_missing_git_is_required_failure(self):
        python = shutil.which("python3")
        path = make_path(self.root, {"python3": f'exec "{python}" "$@"'})
        env = {"PATH": path, "HOME": str(self.home)}
        done = subprocess.run([BASH, str(SCRIPT), "--json"], capture_output=True, text=True, env=env, timeout=60)
        report = json.loads(done.stdout)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.items(report)["git"]["status"], "missing")
        self.assertGreaterEqual(report["required_missing"], 1)

    def test_old_python_is_rejected(self):
        # A fake python3 cannot print the JSON report, so read the table.
        path = make_path(self.root, {"python3": "echo 3.8.1", "git": "echo git"})
        env = {"PATH": path, "HOME": str(self.home)}
        done = subprocess.run([BASH, str(SCRIPT), "--quiet"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertIn("python3 3.8.1 (needs >= 3.9)", done.stdout)

    def test_bin_dir_on_path_is_recognised(self):
        code, report = self.run_script({}, "--bin-dir", str(self.root / "bin"))
        self.assertEqual(self.items(report)["PATH"]["status"], "ok")
        code, report = self.run_script({}, "--bin-dir", str(self.root / "elsewhere"))
        self.assertEqual(self.items(report)["PATH"]["status"], "missing")

    def test_bad_argument_exits_2(self):
        done = subprocess.run([BASH, str(SCRIPT), "--nope"], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 2)

    def test_table_names_the_fix(self):
        python = shutil.which("python3")
        path = make_path(self.root, {"python3": f'exec "{python}" "$@"', "git": "echo git"})
        env = {"PATH": path, "HOME": str(self.home)}
        done = subprocess.run([BASH, str(SCRIPT), "--quiet"], capture_output=True, text=True, env=env, timeout=60)
        self.assertIn("needed for:", done.stdout)
        self.assertIn("fix:", done.stdout)
        self.assertNotIn("python3 ", done.stdout.split("RECOMMENDED")[0].replace("REQUIRED", ""))


if __name__ == "__main__":
    unittest.main()
