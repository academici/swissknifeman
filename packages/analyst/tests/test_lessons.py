"""Тесты хранилища уроков: схема, atomic write, переходы, append-only аудит, Jaccard."""
import tempfile
import unittest
from pathlib import Path

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
        # id детерминирован
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
        # файл реально на диске в каталоге состояния
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
        # старый файл исчез, новый есть — урок не двоится
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
        # второй вызов не затирает первый — файл только растёт
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
        # не находит себя при exclude_id
        sim2 = lessons.similar_lessons(self.proj, "Laravel DDD service", "put services",
                                       threshold=0.1, exclude_id=L["id"])
        self.assertEqual(sim2, [])


if __name__ == "__main__":
    unittest.main()
