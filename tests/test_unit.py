"""Юнит-тесты common.py: Env, parse_args, now_iso, atomic JSON, sanitize."""
import tempfile
import unittest
from pathlib import Path

from maind.common import (Env, atomic_write_json, load_json_db, now_iso,
                          parse_args, sanitize)


class TestEnvPaths(unittest.TestCase):
    def test_paths(self):
        env = Env("/srv/maind", home="/h")
        self.assertEqual(env.state_dir, Path("/h/.maind"))
        self.assertEqual(env.agents_db, Path("/h/.maind/agents.json"))
        self.assertEqual(env.projects_db, Path("/h/.maind/projects.json"))
        self.assertEqual(env.data_dir, Path("/srv/maind/data"))
        self.assertEqual(env.graph_db, Path("/srv/maind/data/graph.db"))
        self.assertEqual(env.memory_pidfile, Path("/srv/maind/data/agentmemory.pid"))
        self.assertEqual(env.memory_config,
                         Path("/srv/maind/config/memory/iii-config.yaml"))
        self.assertEqual(env.default_config, Path("/srv/maind/.maind.json"))


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


if __name__ == "__main__":
    unittest.main()
