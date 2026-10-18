"""Shared test helpers: a throwaway HOME, SKM_HOME and SKM_WORKSPACES_ROOT, and temporary git checkouts."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Sequence, Tuple
from unittest import mock

MODULE_ROOT = Path(__file__).resolve().parents[1]
HUB_ROOT = MODULE_ROOT.parents[1]
BRIDGE_ROOT = HUB_ROOT / "bridges" / "workspace-planner"  # the bridge that fills workspace:plans-migrator (hub layout)


_CODES = iter(range(1, 1_000_000))


def new_code(prefix: str = "proj") -> str:
    """A fresh project code (``proj-1``, ``proj-2``, ...)."""
    return f"{prefix}-{next(_CODES)}"


def git(cwd, *args: str) -> str:
    """Run git in ``cwd`` (a list of arguments, no shell); the stdout of a successful call."""
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return done.stdout


class TempCase(unittest.TestCase):
    """``self.root`` is a real temporary folder; ``os.environ`` is replaced for the test by a sandbox whose machine
    folders, workspace and units path are inside it, and the background delivery of events is off."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.home = self.root / "home"
        self.home.mkdir()
        self.ws = self.root / "wss" / "axioma"
        self.ws.parent.mkdir()
        units = os.pathsep.join(str(path) for path in (MODULE_ROOT, BRIDGE_ROOT) if path.is_dir())
        self.env = {"HOME": str(self.home), "SKM_HOME": str(self.root / "skm"), "SKM_WORKSPACES_ROOT": str(self.ws.parent),
                    "SKM_WORKSPACE": "axioma",
                    "SKM_UNITS_PATH": units, "SKM_AICORE_EVENTS__DELIVERY": "off",
                    "PATH": os.environ.get("PATH", ""), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    @property
    def state(self) -> Path:
        return self.root / "skm" / "state" / "workspaces" / "axioma"

    def checkout(self, name: str, remotes: Sequence[Tuple[str, str]] = (), plans: Sequence[str] = ()) -> Path:
        """A git checkout ``name`` under the temporary folder, with remotes ``(name, url)`` and plan folders."""
        path = self.root / "src" / name
        path.mkdir(parents=True)
        git(path, "init", "-q")
        for remote, url in remotes:
            git(path, "remote", "add", remote, url)
        for plan in plans:
            (path / "plans" / plan).mkdir(parents=True)
            (path / "plans" / plan / "plan.json").write_text("{}\n", encoding="utf-8")
        return path

    def run_cli(self, *args: str, stdin: str = "") -> Tuple[int, str, str]:
        """Run ``workspace.cli.main`` with the sandbox environment; ``(exit code, stdout, stderr)``."""
        import sys
        from workspace import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def json_cli(self, *args: str) -> dict:
        code, out, err = self.run_cli(*args, "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)
