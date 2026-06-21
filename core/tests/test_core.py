"""Smoke-тесты пакета core — общий фундамент монорепо (stdlib-only).

Запуск: PYTHONPATH=<корень монорепо> python3 -m unittest discover -s core/tests"""
import json
import tempfile
import unittest
from pathlib import Path

from core import (BaseEnv, atomic_write_json, atomic_write_text,
                  find_monorepo_root, find_repo_root, now_iso, sanitize)


class TestText(unittest.TestCase):
    def test_sanitize_slug(self):
        self.assertEqual(sanitize("Hello World_Foo"), "hello-world-foo")
        self.assertEqual(sanitize("  A--B  "), "a-b")
        self.assertEqual(sanitize("Ωmega!!"), "mega")


class TestEnv(unittest.TestCase):
    def test_base_env_normalizes_paths(self):
        env = BaseEnv("/tmp/x", "cmd", home="/tmp/h")
        self.assertEqual(str(env.root), "/tmp/x")
        self.assertEqual(str(env.home), "/tmp/h")
        self.assertEqual(env.cmd, "cmd")

    def test_base_env_is_frozen(self):
        env = BaseEnv("/tmp/x")
        with self.assertRaises(Exception):
            env.root = "/other"  # frozen dataclass

    def test_subclass_keeps_frozen_and_core(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Sub(BaseEnv):
            @property
            def state(self):
                return self.home / ".thing"

        s = Sub("/tmp/x", home="/tmp/h")
        self.assertEqual(str(s.state), "/tmp/h/.thing")


class TestTerm(unittest.TestCase):
    def test_now_iso_format(self):
        # YYYY-MM-DDTHH:MM:SSZ
        self.assertRegex(now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestAtomicIO(unittest.TestCase):
    def test_write_text_creates_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a" / "b" / "f.txt"
            atomic_write_text(p, "привет")
            self.assertEqual(p.read_text(encoding="utf-8"), "привет")
            # tmp-файл не остаётся после успешной записи
            self.assertEqual(list(Path(tmp).rglob("*.tmp")), [])

    def test_write_json_version_first_and_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "db.json"
            atomic_write_json(p, {"a": 1, "version": 9}, version=2)
            text = p.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            data = json.loads(text)
            self.assertEqual(data["version"], 2)            # version переписан
            self.assertEqual(list(data.keys())[0], "version")  # первым ключом
            self.assertEqual(data["a"], 1)

    def test_write_json_indent_param(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.json"
            atomic_write_json(p, {"k": "v"}, indent=4)
            self.assertIn('\n    "k"', p.read_text(encoding="utf-8"))


class TestRepoRoot(unittest.TestCase):
    def test_find_repo_root_walks_up_to_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            deep = root / "packages" / "x" / "lib"
            deep.mkdir(parents=True)
            self.assertEqual(find_repo_root(deep), root)

    def test_find_repo_root_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_repo_root(Path(tmp)))

    def test_find_monorepo_root_by_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "packages").mkdir()
            deep = root / "packages" / "maind"
            deep.mkdir()
            self.assertEqual(find_monorepo_root(deep), root)

    def test_find_monorepo_root_none_standalone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_monorepo_root(Path(tmp) / "lonely"))


if __name__ == "__main__":
    unittest.main()
