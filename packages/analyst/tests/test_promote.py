"""Тесты promote/deprecate: конвейер, человеко-гейт curated, аудит, graceful surfacing."""
import os
import stat
import tempfile
import unittest
from contextlib import contextmanager

from analyst import lessons
from analyst.common import Env
from analyst.promote import cmd_deprecate, cmd_promote, surface_to_memory


@contextmanager
def chdir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


@contextmanager
def env_var(key, val):
    prev = os.environ.get(key)
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


class TestPromote(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name
        self.env = Env(self.proj, "promote")
        L = lessons.new_lesson(trigger="use pest for laravel package tests",
                               action="configure Testbench + SQLite",
                               scope="project:proj", session_id="s1")
        lessons.save_lesson(self.proj, L, "ephemeral")
        self.lid = L["id"]

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_maind(self, rc=0):
        p = os.path.join(self.proj, "fake-maind")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"#!/bin/sh\nexit {rc}\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def test_ephemeral_to_candidate_no_gate(self):
        with chdir(self.proj):
            cmd_promote(self.env, [self.lid])   # default next state = candidate
        _l, st = lessons.find_lesson(self.proj, self.lid)
        self.assertEqual(st, "candidate")
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "promote" and r["to"] == "candidate" for r in audit))

    def test_curated_requires_human_gate(self):
        lessons.move_lesson(self.proj, self.lid, "candidate")
        with chdir(self.proj), env_var("MAIND_BIN", "/nonexistent/maind"):
            # non-tty confirm() → False, без --yes: НЕ должно продвинуться
            cmd_promote(self.env, [self.lid, "--to", "curated"])
        _l, st = lessons.find_lesson(self.proj, self.lid)
        self.assertEqual(st, "candidate")

    def test_curated_with_yes_and_surface_ok(self):
        lessons.move_lesson(self.proj, self.lid, "candidate")
        fake = self._fake_maind(rc=0)
        with chdir(self.proj), env_var("MAIND_BIN", fake):
            cmd_promote(self.env, [self.lid, "--to", "curated", "--yes"])
        _l, st = lessons.find_lesson(self.proj, self.lid)
        self.assertEqual(st, "curated")
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "surface" and r["ok"] is True for r in audit))

    def test_surface_graceful_when_maind_absent(self):
        L, _ = lessons.find_lesson(self.proj, self.lid)
        with env_var("MAIND_BIN", "/nonexistent/maind"):
            res = surface_to_memory(self.env, L)
        self.assertFalse(res["ok"])
        self.assertIn("maind", res["reason"])

    def test_surface_graceful_on_nonzero(self):
        L, _ = lessons.find_lesson(self.proj, self.lid)
        fake = self._fake_maind(rc=3)
        with env_var("MAIND_BIN", fake):
            res = surface_to_memory(self.env, L)
        self.assertFalse(res["ok"])

    def test_cannot_promote_backward(self):
        lessons.move_lesson(self.proj, self.lid, "curated")
        with chdir(self.proj), self.assertRaises(SystemExit):
            cmd_promote(self.env, [self.lid, "--to", "candidate"])

    def test_promote_missing_dies(self):
        with chdir(self.proj), self.assertRaises(SystemExit):
            cmd_promote(self.env, ["no-such-id"])

    def test_deprecate(self):
        with chdir(self.proj):
            cmd_deprecate(self.env, [self.lid])
        _l, st = lessons.find_lesson(self.proj, self.lid)
        self.assertEqual(st, "deprecated")
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "deprecate" for r in audit))


if __name__ == "__main__":
    unittest.main()
