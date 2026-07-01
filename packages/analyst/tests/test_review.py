"""Тесты review: группировка по state, structured diff (similar), фильтр --state, json."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout

from analyst import lessons, review


class TestReview(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self):
        a = lessons.new_lesson(trigger="laravel service placement domain", action="put in Domain",
                               scope="project:p", session_id="s1")
        lessons.save_lesson(self.proj, a, "ephemeral")
        b = lessons.new_lesson(trigger="laravel service placement layer", action="put in Domain layer",
                               scope="project:p", session_id="s2")
        lessons.save_lesson(self.proj, b, "curated")
        return a, b

    def test_build_review_groups_and_similar(self):
        a, b = self._seed()
        groups = review.build_review(self.proj)
        self.assertEqual(len(groups["ephemeral"]), 1)
        self.assertEqual(len(groups["curated"]), 1)
        # ephemeral 'a' должен видеть похожий curated 'b'
        sim_ids = [s[0]["id"] for s in groups["ephemeral"][0]["similar"]]
        self.assertIn(b["id"], sim_ids)

    def test_state_filter(self):
        self._seed()
        groups = review.build_review(self.proj, "curated")
        self.assertEqual(len(groups["curated"]), 1)
        self.assertEqual(len(groups["ephemeral"]), 0)

    def test_empty_prints_hint(self):
        out = io.StringIO()
        with redirect_stdout(out):
            review._print_human(review.build_review(self.proj))
        self.assertIn("analyst digest", out.getvalue())

    def test_human_output_shows_lesson(self):
        self._seed()
        out = io.StringIO()
        with redirect_stdout(out):
            review._print_human(review.build_review(self.proj))
        text = out.getvalue()
        self.assertIn("ephemeral", text)
        self.assertIn("curated", text)
        self.assertIn("trigger:", text)


if __name__ == "__main__":
    unittest.main()
