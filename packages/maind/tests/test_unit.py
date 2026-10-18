"""Unit tests common.py: Env, parse_args, now_iso, atomic JSON, sanitize."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from maind.common import Env, load_json_db
from aicore.util.io import atomic_write_json
from aicore.util.term import now_iso
from aicore.util.cli import parse_args
from aicore.util.text import sanitize


class TestEnvPaths(unittest.TestCase):
    def test_paths(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in ("SKM_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
                os.environ.pop(name, None)
            env = Env("/srv/maind", home="/h")
            # aicore.state places (the machine home under the home directory)
            self.assertEqual(env.state_dir, Path("/h/.local/share/swissknifeman/state/maind"))
            self.assertEqual(env.agents_db, Path("/h/.local/share/swissknifeman/state/maind/agents.json"))
            self.assertEqual(env.registry_file,
                             Path("/h/.local/share/swissknifeman/state/maind/registry.json"))
            self.assertEqual(env.data_dir, Path("/h/.local/share/swissknifeman/maind"))
            self.assertEqual(env.graph_db, Path("/h/.local/share/swissknifeman/maind/graph.db"))
            self.assertEqual(env.memory_pidfile,
                             Path("/h/.local/share/swissknifeman/maind/agentmemory.pid"))
            self.assertEqual(env.memory_config,
                             Path("/srv/maind/config/memory/iii-config.yaml"))
            self.assertFalse(hasattr(env, "projects_db"))
            # legacy node file: config.json in root monorepo; standalone (no packages/ nearby)
            # → himself root
            self.assertEqual(env.legacy_node_config, Path("/srv/maind/config.json"))
            self.assertEqual(env.example_config, Path("/srv/maind/configs/registry.example.json"))

    def test_skm_home_moves_state_and_data(self):
        with mock.patch.dict(os.environ, {"SKM_HOME": "/iso"}):
            env = Env("/srv/maind", home="/h")
            self.assertEqual(env.state_dir, Path("/iso/state/maind"))
            self.assertEqual(env.data_dir, Path("/iso/maind"))

    def test_legacy_places_used_until_new_ones_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, root = Path(tmp) / "home", Path(tmp) / "maind"
            (home / ".maind").mkdir(parents=True)
            (root / "data").mkdir(parents=True)
            env = Env(root, home=home)
            with mock.patch.dict(os.environ, {}, clear=False):
                for name in ("SKM_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
                    os.environ.pop(name, None)
                self.assertEqual(env.state_dir, home / ".maind")
                self.assertEqual(env.data_dir, root / "data")
                self.assertEqual(env.agents_db, home / ".maind" / "agents.json")
                new_state = home / ".local/share/swissknifeman/state/maind"
                new_state.mkdir(parents=True)
                self.assertEqual(env.state_dir, new_state)   # the new place wins once it exists


class TestParseArgs(unittest.TestCase):
    def test_str_and_bool(self):
        opts, pos = parse_args(["--from", "brain", "--json"],
                               {"--from": "str", "--json": "bool"})
        self.assertEqual(opts["from"], "brain")
        self.assertTrue(opts["json"])
        self.assertEqual(pos, [])

    def test_positionals(self):
        opts, pos = parse_args(["kill", "abc", "--force"],
                               {"--force": "bool"}, max_pos=2)
        self.assertEqual(pos, ["kill", "abc"])
        self.assertTrue(opts["force"])

    def test_help(self):
        opts, _ = parse_args(["-h"], {})
        self.assertTrue(opts["help"])

    def test_unknown_flag_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["--nope"], {})

    def test_missing_value_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["--from"], {"--from": "str"})

    def test_overflow_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["a", "b"], {}, max_pos=1)


class TestNowIso(unittest.TestCase):
    def test_format(self):
        self.assertRegex(now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestJsonDb(unittest.TestCase):
    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sub" / "db.json"
            atomic_write_json(p, {"a": 1}, version=1)
            text = p.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            data = load_json_db(p, {})
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["a"], 1)

    def test_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            p.write_text("{ broken", encoding="utf-8")
            data = load_json_db(p, {"version": 1, "items": []})
            self.assertEqual(data["items"], [])
            self.assertEqual(len(list(Path(tmp).glob("db.json.corrupt.*"))), 1)

    def test_newer_version_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            p.write_text('{"version": 999}', encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_json_db(p, {})


class TestSanitize(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(sanitize("Hello World"), "hello-world")
        self.assertEqual(sanitize("A__B  C"), "a-b-c")
        self.assertEqual(sanitize("Weird!@#Name"), "weirdname")


class TestEnvOverrides(unittest.TestCase):
    def test_memory_config_default(self):
        env = Env("/srv/maind", home="/h")
        self.assertEqual(env.memory_config,
                         Path("/srv/maind/config/memory/iii-config.yaml"))

    def test_memory_config_env_override(self):
        env = Env("/srv/maind", home="/h")
        os.environ["MAIND_III_CONFIG"] = "/custom/iii.yaml"
        try:
            self.assertEqual(env.memory_config, Path("/custom/iii.yaml"))
        finally:
            del os.environ["MAIND_III_CONFIG"]


if __name__ == "__main__":
    unittest.main()
