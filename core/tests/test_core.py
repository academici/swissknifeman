"""Smoke-тесты пакета core — общий фундамент монорепо (stdlib-only).

Запуск: PYTHONPATH=<корень монорепо> python3 -m unittest discover -s core/tests"""
import json
import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from core import (BaseEnv, atomic_write_json, atomic_write_text,
                  find_monorepo_root, find_repo_root, now_iso, parse_args,
                  parse_flags, run_cmd, safe_load_json, sanitize)


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

    def test_base_env_home_reads_current_env(self):
        # default_factory зовёт Path.home() при создании (не модульный снимок) —
        # подменённый $HOME подхватывается (нужно для тестируемости).
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"HOME": tmp}):
                self.assertEqual(BaseEnv("/r").home, Path(tmp))

    def test_base_env_is_frozen(self):
        env = BaseEnv("/tmp/x")
        with self.assertRaises(FrozenInstanceError):
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

    def test_write_text_cleans_tmp_on_failure(self):
        # Если replace падает (кросс-устройство/нет места), осиротевший .tmp не
        # должен оставаться на диске — иначе мусор копится в долгоживущих процессах.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "f.txt"
            with mock.patch("core.io.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    atomic_write_text(p, "data")
            self.assertEqual(list(Path(tmp).rglob("*.tmp")), [])
            self.assertFalse(p.exists())

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


class TestParseFlags(unittest.TestCase):
    def test_bool_and_str_flags(self):
        out = parse_flags(["--name", "x", "--force"],
                          {"--name": "str", "--force": "bool"})
        self.assertEqual(out["name"], "x")
        self.assertIs(out["force"], True)
        self.assertIs(out["help"], False)

    def test_defaults_when_absent(self):
        out = parse_flags([], {"--name": "str", "--force": "bool"})
        self.assertEqual(out["name"], "")
        self.assertIs(out["force"], False)

    def test_dash_to_underscore_key(self):
        out = parse_flags(["--dry-run"], {"--dry-run": "bool"})
        self.assertIs(out["dry_run"], True)

    def test_help_flag(self):
        self.assertIs(parse_flags(["-h"], {})["help"], True)

    def test_unknown_flag_dies(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--nope"], {})

    def test_missing_value_dies(self):
        with self.assertRaises(SystemExit):
            parse_flags(["--name"], {"--name": "str"})


class TestParseArgs(unittest.TestCase):
    def test_positionals_collected(self):
        opts, pos = parse_args(["a", "--force", "b"],
                               {"--force": "bool"}, max_pos=2)
        self.assertEqual(pos, ["a", "b"])
        self.assertIs(opts["force"], True)

    def test_too_many_positionals_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["a", "b"], {}, max_pos=1)

    def test_unknown_flag_dies(self):
        with self.assertRaises(SystemExit):
            parse_args(["--x"], {}, max_pos=0)


class TestRunCmd(unittest.TestCase):
    def test_success_capture(self):
        r = run_cmd([sys.executable, "-c", "print('hi')"], capture=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "hi")

    def test_nonzero_with_check_dies(self):
        with self.assertRaises(SystemExit):
            run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"])

    def test_nonzero_without_check_returns(self):
        r = run_cmd([sys.executable, "-c", "import sys; sys.exit(3)"],
                    check=False)
        self.assertEqual(r.returncode, 3)

    def test_missing_binary_dies(self):
        with self.assertRaises(SystemExit):
            run_cmd(["definitely-no-such-binary-xyz"])


class TestSafeLoadJson(unittest.TestCase):
    def test_loads_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text('{"k": 1}', encoding="utf-8")
            self.assertEqual(safe_load_json(p), {"k": 1})

    def test_missing_returns_default(self):
        self.assertEqual(safe_load_json("/no/such/file.json", default={}), {})

    def test_corrupt_returns_default_and_calls_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            seen = []
            out = safe_load_json(p, default=[], on_error=seen.append)
            self.assertEqual(out, [])
            self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
