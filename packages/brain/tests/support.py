"""Shared test helpers: a throwaway HOME, a private copy of the fixture vault and the machine layer."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aicore.state import machine_config_file

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vault"
EVENTS = Path(__file__).resolve().parent / "fixtures" / "events" / "planner.plan.closed"
MODULE_ROOT = Path(__file__).resolve().parents[1]
# Tests never start the background deliverer: emit would otherwise follow the configured default.
DELIVERY_OFF = {"SKM_AICORE_EVENTS__DELIVERY": "off"}


def load_event(name: str) -> dict:
    """A contract fixture of ``planner.plan.closed`` by file name without the suffix."""
    return json.loads((EVENTS / f"{name}.json").read_text(encoding="utf-8"))


class TempCase(unittest.TestCase):
    """``self.home`` is an empty home, ``self.vault`` a copy of the fixture vault, ``self.env`` isolates aicore."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "SKM_HOME": str(self.root / "skm"), **DELIVERY_OFF}
        self.vault = self.root / "vault"
        shutil.copytree(FIXTURE, self.vault)
        self.project = self.root / "demo"
        (self.project / ".git").mkdir(parents=True)

    def machine_config(self, body: str) -> Path:
        path = machine_config_file(env=self.env, home=self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + body, encoding="utf-8")
        return path

    def project_config(self, body: str) -> Path:
        path = self.project / ".swissknifeman" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("schema_version = 1\n" + body, encoding="utf-8")
        return path

    def legacy(self, block) -> None:
        (self.project / ".swissknife.json").write_text(json.dumps({"memory_brain": block}), encoding="utf-8")

    def claim_project(self, repo: Path) -> Path:
        """Point the fixture control note at ``repo``."""
        note = self.vault / "05-Projects" / "03-Packages" / "Demo" / "Demo.md"
        note.write_text(f"---\ntype: project\nrepo: {repo}\n---\n# Demo\n", encoding="utf-8")
        return note
