"""Тесты команды topology: схема ~/.swissknifeman/topology.json, init/show,
сохранение created_at, бэкап, авто-детект базы проектов.

Гоняются против синтетического реестра в tmpdir (tests/fixtures), реальный
~/.swissknifeman не трогается (Env.home указывает на tmp)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from swissknifeman.state import upsert_project
from swissknifeman.topology import (
    cmd_topology, detect_projects_base, load_topology, save_topology,
    TOPOLOGY_VERSION,
)
import tests.fixtures as fx


def capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


class TopologyCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

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
        # бэкап предыдущего конфига
        bak = self.env.topology_file.with_suffix(".json.bak")
        self.assertTrue(bak.exists())
        self.assertEqual(json.loads(bak.read_text())["nodes"]["brain"]["path"], "/a")

    def test_init_no_tmp_left(self):
        capture(cmd_topology, self.env, ["init", "--yes"])
        leftovers = list(self.env.state_dir.glob("*.tmp"))
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
        upsert_project(self.env, {"path": "/home/u/projects/a", "channel": "vendor"})
        upsert_project(self.env, {"path": "/home/u/projects/pkg/b",
                                  "channel": "vendor"})
        self.assertEqual(detect_projects_base(self.env), "/home/u/projects")

    def test_detect_projects_base_default_when_empty(self):
        self.assertEqual(detect_projects_base(self.env),
                         str(self.env.home / "projects"))

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
