"""Shared fixtures of the bridge tests: a temporary checkout with plans of every class and a temporary workspace.

Every test works in a temporary folder; the real HOME, workspace and plans are never touched (``scripts/test.sh`` sets a
temporary HOME, SKM_HOME and SKM_WORKSPACES_ROOT).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BRIDGE = Path(__file__).resolve().parents[1]
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

import partners  # noqa: E402

PLANNER = partners.planner_root()
if PLANNER is None:
    raise unittest.SkipTest("planner not found (set PLANNER_ROOT)")
partners.use_aicore()

from aicore import workspace as aicore_workspace  # noqa: E402

DEMO = PLANNER / "tests/engine/fixtures/demo-plan"
PLAN_NAME = "2026.10.05-№7-DEMO"
ARCHIVED_NAME = "archive/2026.09.01-№3-DEMO"
PROJECT_ID = "alpha"
DEVICE = "a1b2c3"
SECRET = "SECRET-CONTENT-MUST-NOT-APPEAR"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_plan(plans: Path, name: str) -> Path:
    """A copy of the demo plan of the planner at ``plans/<name>``."""
    target = plans / name
    shutil.copytree(DEMO, target)
    return target


def make_checkout(root: Path) -> Path:
    """A checkout with a v4 plan, an archived v4 plan, legacy folders, derived files and top-level files."""
    root.mkdir(parents=True, exist_ok=True)
    write(root / "lib/pkg/config.py", "DEFAULT = 1\n")  # a repository file the demo items list as a required read
    plans = root / "plans"
    live = make_plan(plans, PLAN_NAME)
    make_plan(plans, ARCHIVED_NAME)
    write(live / "artifacts/P1.1/out.txt", "artifact\n")
    for derived in ("views/roadmap.md", "context/P1.1.json", ".lock"):  # derived: never copied
        write(live / derived, "derived\n")
    write(live / "__pycache__/x.pyc", "cache\n")
    write(plans / "old-thing/notes.txt", f"legacy notes {SECRET}\n")
    write(plans / "old-thing/artifacts/data.bin", "\x00\x01 binary-ish\n")
    write(plans / "only-artifacts/artifacts/a.txt", "a\n")
    write(plans / "README.md", "top level\n")
    write(plans / "archive/NOTE.md", "archive note\n")
    return root


def read_marker(root: Path):
    return aicore_workspace.read_marker(root)


class BridgeCase(unittest.TestCase):
    """A temporary checkout, workspace and migration environment per test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.checkout = make_checkout(self.tmp / "checkout")
        self.workspace = self.tmp / "workspaces" / "axioma"
        (self.workspace / "projects").mkdir(parents=True)
        (self.workspace / ".staging").mkdir()
        self.state = self.tmp / "skm"
        saved = {key: os.environ.get(key) for key in ("SKM_HOME", "SKM_WORKSPACES_ROOT", "SKM_WORKSPACE", "SKM_MIGRATOR_FAIL_AT")}
        os.environ["SKM_HOME"] = str(self.state)
        os.environ["SKM_WORKSPACES_ROOT"] = str(self.workspace.parent)
        os.environ["SKM_WORKSPACE"] = "axioma"
        os.environ.pop("SKM_MIGRATOR_FAIL_AT", None)

        def restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.addCleanup(restore)

    @property
    def plans(self) -> Path:
        return self.checkout / "plans"

    @property
    def project_dir(self) -> Path:
        return self.workspace / "projects" / PROJECT_ID

    def request(self, **fields) -> dict:
        import inspector
        manifest = fields.pop("manifest", None) or inspector.inspect(self.checkout)
        base = {"op": "apply", "project_root": str(self.checkout), "workspace_root": str(self.workspace),
                "project_id": PROJECT_ID, "op_id": "mig_test", "manifest": manifest, "mode": "initial",
                "on_conflict": None, "device_short": DEVICE, "lock_timeout_s": 5}
        base.update(fields)
        return base

    def apply(self, **fields) -> dict:
        import apply
        return apply.run(self.request(**fields), progress=None)

    def hold(self, plan_dir: Path, seconds: float) -> subprocess.Popen:
        """``hold_plan_lock`` that is cleaned up with the test."""
        process = hold_plan_lock(plan_dir, seconds)

        def done():
            process.kill()
            process.wait()
            process.stdout.close()
        self.addCleanup(done)
        return process

    def staging_entries(self):
        return sorted(path.name for path in (self.workspace / ".staging").iterdir())


def hold_plan_lock(plan_dir: Path, seconds: float) -> subprocess.Popen:
    """A process that holds ``flock`` on ``<plan>/.lock`` (the lock of ``PlanLock``) for ``seconds``."""
    code = ("import fcntl, sys, time\n"
            "handle = open(sys.argv[1], 'a+')\n"
            "fcntl.flock(handle, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "time.sleep(float(sys.argv[2]))\n")
    process = subprocess.Popen([sys.executable, "-c", code, str(plan_dir / ".lock"), str(seconds)],
                               stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None and process.stdout.readline().strip() == "held"
    return process


def tree(root: Path):
    """``{relative path: bytes}`` of every file under ``root``."""
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def wait_for(predicate, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def dump(document) -> str:
    return json.dumps(document, ensure_ascii=False)
