"""Write confinement: preparing, testing policies, checking conformance and explaining write only to the output
directory and the run state directory, and never create provider directories."""
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest import mock

from tests.test_cli_prepare import INPUT, MODEL_CATALOG, POLICY, CliCase

PROVIDER_DIRS = (".claude", ".codex", ".grok")


def snapshot(*roots: Path) -> dict:
    found = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            info = path.lstat()
            found[str(path)] = (path.is_dir(), info.st_size, info.st_mtime_ns)
    return found


class WriteConfinementTests(CliCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        self.out = self.root / "out"
        self.project = self.root / "project"
        self.project.mkdir()
        os.chdir(self.project)
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root / "state"),
                                               "XDG_CONFIG_HOME": str(self.root / "config")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self):
        return self.run_cli("prepare", "--provider", "claude-code", "--input", INPUT, "--policy", POLICY,
                            "--out", self.out, "--dry-run", "--model-catalog", MODEL_CATALOG)

    def allowed(self, path: str) -> bool:
        inside = Path(path)
        runs = Path(os.environ["SKM_HOME"]) / "orch" / "runs"
        return (self.out in (inside, *inside.parents) or runs in (inside, *inside.parents)
                or (inside in runs.parents and inside.is_dir()))

    def changed(self, before: dict) -> list:
        after = snapshot(self.home, self.project, self.root / "state", self.root / "config", self.out)
        return sorted(path for path, value in after.items() if before.get(path) != value and not self.allowed(path))

    def test_prepare_dry_run_writes_only_to_out(self):
        before = snapshot(self.home, self.project)
        code, out, err = self.prepare()
        self.assertEqual((code, err), (0, ""), out)
        self.assertTrue(self.out.is_dir())
        self.assertEqual(self.changed(before), [])
        for name in PROVIDER_DIRS:
            self.assertFalse((self.home / name).exists(), name)
            self.assertFalse((self.project / name).exists(), name)

    def test_every_read_only_command_leaves_the_tree_alone(self):
        code, out, _ = self.prepare()
        self.assertEqual(code, 0)
        plan_file = self.root / "launch-plan.json"
        plan_file.write_text(out, encoding="utf-8")
        before = snapshot(self.home, self.project, self.root / "state", self.root / "config", self.out)
        for argv in (("policy", "test"), ("policy", "list"), ("conformance",), ("conformance", "--json"),
                     ("explain", plan_file), ("explain", plan_file, "--json")):
            with self.subTest(argv=[str(a) for a in argv]):
                code, _, err = self.run_cli(*argv)
                self.assertEqual((code, err), (0, ""))
        after = snapshot(self.home, self.project, self.root / "state", self.root / "config", self.out)
        self.assertEqual(sorted(path for path in after if after[path] != before.get(path)), [])
        self.assertEqual(sorted(path for path in before if path not in after), [])
        for name in PROVIDER_DIRS:
            self.assertFalse((self.home / name).exists(), name)

    def test_the_guard_reports_a_stray_file(self):
        before = snapshot(self.home, self.project)
        (self.home / ".claude").mkdir()
        (self.project / "stray.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.changed(before), sorted([str(self.home / ".claude"), str(self.project / "stray.txt")]))

    def test_the_run_state_directory_is_allowed(self):
        before = snapshot(self.home, self.project)
        runs = Path(os.environ["SKM_HOME"]) / "orch" / "runs" / "dry-x"
        runs.mkdir(parents=True)
        (runs / "events.jsonl").write_text(json.dumps({}) + "\n", encoding="utf-8")
        self.assertEqual(self.changed(before), [])


if __name__ == "__main__":
    unittest.main()
