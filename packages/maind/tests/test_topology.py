"""Command tests `maind topology`: <state>/maind/topology.json, the legacy
~/.swissknifeman/topology.json (file by file), init/show, created_at, backup, detection.

Runs in a tmp HOME (Env.home), the real machine state is never touched."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from aicore.state import list_backups

from maind.topology import (
    cmd_topology, detect_brain, detect_projects_base, load_topology, save_topology,
    TOPOLOGY_VERSION,
)
import tests.fixtures as fx
from maind.projects import write_registry
from maind.config import Config


def capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


class TopologyCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_repo(self.tmp)
        patcher = mock.patch("maind.topology.brain_path", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _register(self, *paths):
        config = Config({"projects": [{"id": f"p{i}", "name": f"P{i}", "local_path": p}
                                      for i, p in enumerate(paths)]})
        write_registry(self.env, config)

    def tearDown(self):
        self._tmp.cleanup()

    # -- show ----------------------------------------------------------------
    def test_show_when_absent_hints_init(self):
        self.assertIsNone(load_topology(self.env))
        _, out = capture(cmd_topology, self.env, ["show"])
        self.assertIn("topology init", out)

    # -- init ----------------------------------------------------------------
    def test_init_writes_three_nodes_with_roles(self):
        capture(cmd_topology, self.env,
                ["init", "--yes", "--brain", "/opt/brain",
                 "--swissknifeman", str(self.root), "--projects-base", "/opt/code"])
        data = load_topology(self.env)
        self.assertEqual(data["version"], TOPOLOGY_VERSION)
        self.assertEqual(set(data["nodes"]),
                         {"brain", "swissknifeman", "projects_base"})
        self.assertEqual(data["nodes"]["brain"]["role"], "docs-hub")
        self.assertEqual(data["nodes"]["swissknifeman"]["role"], "skills-hub")
        self.assertEqual(data["nodes"]["projects_base"]["role"], "workspace")
        self.assertEqual(data["nodes"]["brain"]["path"], "/opt/brain")
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    def test_reinit_preserves_created_at_and_backs_up(self):
        capture(cmd_topology, self.env, ["init", "--yes", "--brain", "/a"])
        first = load_topology(self.env)
        capture(cmd_topology, self.env, ["init", "--yes", "--brain", "/b"])
        second = load_topology(self.env)
        self.assertEqual(first["created_at"], second["created_at"])
        self.assertEqual(second["nodes"]["brain"]["path"], "/b")
        copies = [f for _, files in list_backups(home=self.env.home) for f in files]
        self.assertEqual(len(copies), 1)
        self.assertEqual(json.loads(copies[0].read_text())["nodes"]["brain"]["path"], "/a")

    def test_init_no_tmp_left(self):
        capture(cmd_topology, self.env, ["init", "--yes"])
        leftovers = list(self.env.topology_file.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    # -- show --json ---------------------------------------------------------
    def test_show_json_round_trips(self):
        capture(cmd_topology, self.env,
                ["init", "--yes", "--brain", "/x", "--projects-base", "/y"])
        _, out = capture(cmd_topology, self.env, ["show", "--json"])
        parsed = json.loads(out)
        self.assertEqual(parsed["nodes"]["brain"]["path"], "/x")
        self.assertEqual(parsed["nodes"]["projects_base"]["path"], "/y")

    # -- detection -----------------------------------------------------------
    def test_detect_projects_base_common_ancestor(self):
        self._register("/home/u/projects/a", "/home/u/projects/pkg/b")
        self.assertEqual(detect_projects_base(self.env), "/home/u/projects")

    def test_detect_projects_base_default_when_empty(self):
        self.assertEqual(detect_projects_base(self.env),
                         str(self.env.home / "projects"))

    def test_detect_brain_uses_the_known_vault_then_the_default(self):
        self.assertEqual(detect_brain(self.env), str(self.env.home / "Vaults" / "Brain"))
        with mock.patch("maind.topology.brain_path", return_value="/vault"):
            self.assertEqual(detect_brain(self.env), "/vault")

    # -- places --------------------------------------------------------------
    def test_new_file_lives_in_the_maind_state_place(self):
        capture(cmd_topology, self.env, ["init", "--yes"])
        self.assertEqual(self.env.topology_file.name, "topology.json")
        self.assertEqual(self.env.topology_file.parent.name, "maind")
        self.assertTrue(self.env.topology_file.is_file())

    def test_legacy_file_is_read_per_file_and_stays_the_write_target(self):
        legacy_dir = self.env.home / ".swissknifeman"
        legacy_dir.mkdir()
        (legacy_dir / "projects.json").write_text("{}")   # another module's file: untouched
        legacy = legacy_dir / "topology.json"
        legacy.write_text(json.dumps({"version": 1, "nodes": {
            "brain": {"path": "/old", "role": "docs-hub"}}}))
        self.assertEqual(self.env.topology_file, legacy)
        _, out = capture(cmd_topology, self.env, ["show", "--json"])
        self.assertEqual(json.loads(out)["nodes"]["brain"]["path"], "/old")
        capture(cmd_topology, self.env, ["init", "--yes", "--brain", "/new"])
        self.assertEqual(json.loads(legacy.read_text())["nodes"]["brain"]["path"], "/new")
        self.assertEqual((legacy_dir / "projects.json").read_text(), "{}")

    def test_init_keeps_the_legacy_state_dir_active(self):
        legacy = self.env.home / ".maind"
        legacy.mkdir()
        (legacy / "registry.json").write_text('{"projects": []}')
        (legacy / "agents.json").write_text("{}")
        before = self.env.state_dir
        self.assertEqual(before, legacy)
        capture(cmd_topology, self.env, ["init", "--yes"])
        self.assertEqual(self.env.state_dir, legacy)
        self.assertTrue(self.env.registry_file.is_file())
        self.assertTrue(self.env.agents_db.is_file())
        self.assertEqual(self.env.topology_file, legacy / "topology.json")
        _, out = capture(cmd_topology, self.env, ["show", "--json"])
        self.assertIn("brain", json.loads(out)["nodes"])

    def test_show_json_without_a_file_is_an_empty_map(self):
        _, out = capture(cmd_topology, self.env, ["show", "--json"])
        self.assertEqual(json.loads(out)["nodes"], {})

    # -- robustness ----------------------------------------------------------
    def test_bad_subcommand_exits(self):
        with self.assertRaises(SystemExit):
            cmd_topology(self.env, ["frobnicate"])

    def test_load_rejects_newer_version(self):
        save_topology(self.env, {"version": TOPOLOGY_VERSION + 1, "nodes": {}})
        with self.assertRaises(SystemExit):
            load_topology(self.env)

    def test_help(self):
        _, out = capture(cmd_topology, self.env, ["--help"])
        self.assertIn("topology", out)


if __name__ == "__main__":
    unittest.main()
