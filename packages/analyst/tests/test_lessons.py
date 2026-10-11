"""Lesson repository tests: diagram, atomic write, transitions, append-only audit, Jaccard."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyst import lessons


class TestLessons(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _mk(self, trigger="Laravel DDD service placement", action="put services in Domain",
            **kw):
        return lessons.new_lesson(trigger=trigger, action=action,
                                  scope="project:test", session_id="s1", **kw)

    def test_new_lesson_schema(self):
        L = self._mk()
        self.assertEqual(L["state"], "ephemeral")
        self.assertEqual(L["scope"], "project:test")
        self.assertEqual(L["provenance"]["session_id"], "s1")
        self.assertIn(L["kind"], lessons.KINDS)
        # id deterministic
        self.assertEqual(L["id"], self._mk()["id"])

    def test_bad_kind_raises(self):
        with self.assertRaises(ValueError):
            self._mk(kind="nonsense")

    def test_save_and_find(self):
        L = self._mk()
        lessons.save_lesson(self.proj, L)
        got, st = lessons.find_lesson(self.proj, L["id"])
        self.assertEqual(st, "ephemeral")
        self.assertEqual(got["trigger"], L["trigger"])
        # file is actually on disk in the state directory
        p = lessons.state_dir(self.proj, "ephemeral") / f"{L['id']}.json"
        self.assertTrue(p.is_file())

    def test_add_candidate_idempotent(self):
        L = self._mk()
        _, created1 = lessons.add_candidate(self.proj, L)
        _, created2 = lessons.add_candidate(self.proj, L)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(len(lessons.list_lessons(self.proj, "ephemeral")), 1)

    def test_move_does_not_duplicate(self):
        L = self._mk()
        lessons.save_lesson(self.proj, L)
        moved, old, new = lessons.move_lesson(self.proj, L["id"], "candidate")
        self.assertEqual((old, new), ("ephemeral", "candidate"))
        self.assertEqual(moved["state"], "candidate")
        # the old file has disappeared, the new one is there - the lesson is not double
        self.assertFalse((lessons.state_dir(self.proj, "ephemeral") / f"{L['id']}.json").is_file())
        self.assertTrue((lessons.state_dir(self.proj, "candidate") / f"{L['id']}.json").is_file())
        all_states = [st for _, st in lessons.list_lessons(self.proj)]
        self.assertEqual(all_states.count("candidate"), 1)
        self.assertEqual(all_states.count("ephemeral"), 0)

    def test_move_missing(self):
        got, _o, _n = lessons.move_lesson(self.proj, "nope", "curated")
        self.assertIsNone(got)

    def test_audit_append_only(self):
        lessons.audit_append(self.proj, {"action": "promote", "id": "x"})
        lessons.audit_append(self.proj, {"action": "deprecate", "id": "x"})
        recs = lessons.read_audit(self.proj)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["action"], "promote")
        self.assertIn("ts", recs[0])
        # the second call does not overwrite the first - the file only grows
        raw = Path(lessons.audit_path(self.proj)).read_text(encoding="utf-8")
        self.assertEqual(raw.count("\n"), 2)

    def test_jaccard_and_similar(self):
        self.assertEqual(lessons.jaccard("", ""), 0.0)
        self.assertGreater(lessons.jaccard("laravel service domain", "laravel service layer"), 0.0)
        L = self._mk()
        lessons.save_lesson(self.proj, L)
        sim = lessons.similar_lessons(self.proj, "Laravel DDD service", "put services somewhere",
                                      threshold=0.1)
        self.assertTrue(sim)
        self.assertEqual(sim[0][0]["id"], L["id"])
        # does not find itself when exclude_id
        sim2 = lessons.similar_lessons(self.proj, "Laravel DDD service", "put services",
                                       threshold=0.1, exclude_id=L["id"])
        self.assertEqual(sim2, [])


class TestProjectDir(unittest.TestCase):
    """Project lessons live in .swissknifeman/analyst; legacy places are read and written in place."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.proj = Path(self._tmp.name)

    def _lesson(self):
        return lessons.new_lesson(trigger="trigger text", action="action text",
                                  scope="project:test", session_id="s1")

    def _save(self, legacy_stderr=None):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            path = lessons.save_lesson(self.proj, self._lesson())
        return path, err.getvalue()

    def test_new_project_uses_swissknifeman_dir(self):
        path, err = self._save()
        self.assertEqual(path.parent.parent.parent, self.proj / ".swissknifeman" / "analyst")
        self.assertEqual(err, "")
        self.assertFalse((self.proj / ".swissknife").exists() or (self.proj / ".claude").exists())

    def test_legacy_dirs_stay_active_with_a_warning(self):
        for legacy in (".swissknife", ".claude"):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                self.proj = Path(tmp)
                (self.proj / legacy / "analyst" / "lessons").mkdir(parents=True)
                with mock.patch.dict(os.environ, {"SKM_HOME": tmp + "/skm"}):
                    path, err = self._save()
                self.assertTrue(str(path).startswith(str(self.proj / legacy / "analyst")), path)
                self.assertIn("legacy location", err)
                self.assertFalse((self.proj / ".swissknifeman").exists())
                lesson, state = lessons.find_lesson(self.proj, self._lesson()["id"])
                self.assertEqual(state, "ephemeral")

    def test_swissknife_wins_over_claude_and_new_wins_over_both(self):
        (self.proj / ".swissknife" / "analyst").mkdir(parents=True)
        (self.proj / ".claude" / "analyst").mkdir(parents=True)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(lessons.project_dir(self.proj), self.proj / ".swissknife" / "analyst")
        (self.proj / ".swissknifeman" / "analyst").mkdir(parents=True)
        self.assertEqual(lessons.project_dir(self.proj), self.proj / ".swissknifeman" / "analyst")


if __name__ == "__main__":
    unittest.main()
