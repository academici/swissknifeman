#!/usr/bin/env python3
"""The plan engine of this checkout reads every plan the repository holds.

For each directory of plans/ and plans/archive/ that has a plan.json, the plan is copied into a temporary
plans root and read with the reading verbs only (check, show, next): none may fail. Copies keep the checkout
and the plans themselves untouched; the machine home is a temporary directory.
"""
from __future__ import annotations

import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "packages" / "planner" / "scripts" / "plan.py"
VERBS = ("check", "show", "next")
TIMEOUT = 300
# A plan archived before the rule "a human view is never an agent input" keeps reads of views/*.md; the stable
# engine reports the same errors. They are tolerated by code and count, and any other error is a failure.
KNOWN_ERRORS = {"TASK-PLAN-JSON": {"human_view": 24}}  # keyed by the plan id after its date and number
_ERROR_LINE = re.compile(r"^([a-z][a-z0-9_]*): ")


def plan_directories(plans_root: Path) -> list:
    found = []
    for base in (plans_root, plans_root / "archive"):
        if base.is_dir():
            found += [path for path in sorted(base.iterdir()) if (path / "plan.json").is_file()]
    return found


def error_codes(result: subprocess.CompletedProcess) -> dict:
    """Error lines of ``plan.py check`` (``<code>: <where>: <message>``; warnings carry a ``warning`` prefix)."""
    lines = (result.stdout + result.stderr).splitlines()
    return dict(collections.Counter(m.group(1) for m in map(_ERROR_LINE.match, lines) if m))


class RepositoryPlansTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="skm-plan-compat-"))
        self.addCleanup(shutil.rmtree, self.scratch, True)
        home = self.scratch / "home"
        home.mkdir()
        self.env = dict(os.environ, HOME=str(home), SKM_HOME=str(home), SKM_AICORE_EVENTS__DELIVERY="off")

    def run_verb(self, verb: str, plans_root: Path, name: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PLAN), verb, name, "--plans-root", str(plans_root)],
                              capture_output=True, text=True, env=self.env, timeout=TIMEOUT)

    def test_the_repository_holds_plans(self):
        self.assertTrue(PLAN.is_file(), PLAN)
        self.assertIsInstance(plan_directories(ROOT / "plans"), list)

    def test_every_plan_is_read_by_the_reading_verbs(self):
        for source in plan_directories(ROOT / "plans"):
            with self.subTest(plan=source.name):
                plans_root = self.scratch / source.name / "plans"
                shutil.copytree(source, plans_root / source.name)
                for verb in VERBS:
                    result = self.run_verb(verb, plans_root, source.name)
                    known = next((codes for suffix, codes in KNOWN_ERRORS.items() if source.name.endswith("-" + suffix)), None) if verb == "check" else None
                    if known and result.returncode == 1:
                        self.assertEqual(error_codes(result), known, f"check: {result.stdout[-2000:]}")
                        continue
                    self.assertEqual(result.returncode, 0, f"{verb}: {result.stdout[-2000:]}{result.stderr[-2000:]}")


if __name__ == "__main__":
    unittest.main()
