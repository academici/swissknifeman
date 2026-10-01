"""Tests mem0-consolidation: taxonomy ADD/UPDATE/NOOP/CONFLICT (clean),
flag-and-ask on the contradiction in promote, supersedes like soft-invalidate."""
import os
import tempfile
import unittest
from contextlib import contextmanager

from analyst import lessons
from analyst.common import Env
from analyst.promote import cmd_promote


@contextmanager
def chdir(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _L(trigger, action, state="curated"):
    return dict(lessons.new_lesson(trigger=trigger, action=action,
                                   scope="project:test", session_id="s"), state=state)


class TestClassify(unittest.TestCase):
    """classify_consolidation — pure function over a list of similar ones."""

    def _similar(self, *lessons_):
        return [(L, L["state"], 0.9) for L in lessons_]

    def test_add_when_no_similar(self):
        c = lessons.classify_consolidation("t", "a", [])
        self.assertEqual(c["action"], "ADD")

    def test_noop_duplicate(self):
        active = _L("deploy laravel migrations production database", "run migrate force always")
        c = lessons.classify_consolidation(
            "deploy laravel migrations production database", "run migrate force always",
            self._similar(active))
        self.assertEqual(c["action"], "NOOP")
        self.assertEqual(c["target"], active["id"])

    def test_update_evolved_action(self):
        active = _L("configure testbench sqlite for package tests",
                    "configure testbench sqlite null driver")
        c = lessons.classify_consolidation(
            "configure testbench sqlite for package tests",
            "configure testbench sqlite memory database", self._similar(active))
        self.assertEqual(c["action"], "UPDATE")

    def test_conflict_same_trigger_diverged_action(self):
        active = _L("deploy laravel migrations production database schema", "force")
        c = lessons.classify_consolidation(
            "deploy laravel migrations production database schema", "never",
            self._similar(active))
        self.assertEqual(c["action"], "CONFLICT")
        self.assertEqual(c["target"], active["id"])


class TestPromoteConsolidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name
        self.env = Env(self.proj, "promote")
        # active (curated) lesson with which there will be a conflict
        self.active = lessons.new_lesson(
            trigger="deploy laravel migrations production database schema", action="force",
            scope="project:test", session_id="s0")
        lessons.save_lesson(self.proj, self.active, "curated")
        # new candidate: same situation, opposite action
        self.cand = lessons.new_lesson(
            trigger="deploy laravel migrations production database schema", action="never",
            scope="project:test", session_id="s1")
        lessons.save_lesson(self.proj, self.cand, "ephemeral")

    def tearDown(self):
        self._tmp.cleanup()

    def test_conflict_blocks_promote_flag_and_ask(self):
        with chdir(self.proj):
            cmd_promote(self.env, [self.cand["id"]])   # without --force/--supersedes
        _l, st = lessons.find_lesson(self.proj, self.cand["id"])
        self.assertEqual(st, "ephemeral")              # NOT progressed: flag-and-ask

    def test_force_overrides_conflict(self):
        with chdir(self.proj):
            cmd_promote(self.env, [self.cand["id"], "--force"])
        _l, st = lessons.find_lesson(self.proj, self.cand["id"])
        self.assertEqual(st, "candidate")

    def test_supersedes_soft_invalidates(self):
        with chdir(self.proj):
            cmd_promote(self.env, [self.cand["id"], "--supersedes", self.active["id"]])
        # new has advanced and carries supersedes
        newl, st = lessons.find_lesson(self.proj, self.cand["id"])
        self.assertEqual(st, "candidate")
        self.assertEqual(newl["supersedes"], self.active["id"])
        # old — soft-deprikate: in deprecated, file saved (not deleted)
        oldl, ost = lessons.find_lesson(self.proj, self.active["id"])
        self.assertEqual(ost, "deprecated")
        self.assertEqual(oldl["superseded_by"], self.cand["id"])
        p = lessons.state_dir(self.proj, "deprecated") / f"{self.active['id']}.json"
        self.assertTrue(p.is_file())
        audit = lessons.read_audit(self.proj)
        self.assertTrue(any(r["action"] == "supersede" for r in audit))


if __name__ == "__main__":
    unittest.main()
