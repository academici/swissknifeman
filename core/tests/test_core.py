"""Smoke-тесты пакета core — общий фундамент монорепо (stdlib-only).

Запуск: PYTHONPATH=<корень монорепо> python3 -m unittest discover -s core/tests"""
import unittest

from core import BaseEnv, now_iso, sanitize


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


if __name__ == "__main__":
    unittest.main()
