"""Тесты поведенческого харнеса скиллов (eval.py) — ТОЛЬКО офлайн-логика.

Раннер (`claude -p`) сетевой и здесь не дёргается: покрываем грейдер, валидацию
схемы, агрегат benchmark, scoring/selection описания, скаффолд, резолв, viewer.
Стиль — как test_budget.py (unittest, синтетический реестр, tmpdir, без сети)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.quality import eval as ev
import tests.fixtures as fx


class GradeAssertionCase(unittest.TestCase):
    def test_contains_case_insensitive(self):
        ok, _ = ev.grade_assertion({"type": "contains", "value": "ABC"}, "x abc y", None)
        self.assertTrue(ok)

    def test_contains_case_sensitive_flag(self):
        ok, _ = ev.grade_assertion(
            {"type": "contains", "value": "ABC", "flags": {"case_sensitive": True}},
            "x abc y", None)
        self.assertFalse(ok)

    def test_not_contains(self):
        ok, _ = ev.grade_assertion({"type": "not_contains", "value": "zzz"}, "abc", None)
        self.assertTrue(ok)

    def test_regex_and_not_regex(self):
        self.assertTrue(ev.grade_assertion(
            {"type": "regex", "value": r"\d+\.\d+"}, "v1.2", None)[0])
        self.assertTrue(ev.grade_assertion(
            {"type": "not_regex", "value": r"\d+\.\d+"}, "no versions", None)[0])

    def test_min_words(self):
        self.assertTrue(ev.grade_assertion({"type": "min_words", "value": 2}, "a b c", None)[0])
        self.assertFalse(ev.grade_assertion({"type": "min_words", "value": 5}, "a b", None)[0])

    def test_file_exists_absent(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / "out.txt").write_text("x")
            self.assertTrue(ev.grade_assertion(
                {"type": "file_exists", "value": "out.txt"}, "", ws)[0])
            self.assertTrue(ev.grade_assertion(
                {"type": "file_absent", "value": "nope.txt"}, "", ws)[0])

    def test_unknown_type(self):
        ok, detail = ev.grade_assertion({"type": "bogus", "value": "x"}, "x", None)
        self.assertFalse(ok)
        self.assertIn("неизвестн", detail)


class GradeCaseCase(unittest.TestCase):
    def test_all_pass(self):
        c = {"id": 1, "assertions": [{"type": "contains", "value": "ok"}]}
        self.assertTrue(ev.grade_case(c, "ok!", None)["passed"])

    def test_one_fail(self):
        c = {"id": 1, "assertions": [{"type": "contains", "value": "ok"},
                                     {"type": "contains", "value": "missing"}]}
        self.assertFalse(ev.grade_case(c, "ok", None)["passed"])

    def test_no_assertions_is_none(self):
        self.assertIsNone(ev.grade_case({"id": 1}, "whatever", None)["passed"])


class ValidateSchemaCase(unittest.TestCase):
    def test_valid_evals(self):
        data = {"skill": "s", "cases": [
            {"id": 1, "prompt": "p", "assertions": [{"type": "contains", "value": "x"}]}]}
        self.assertEqual(ev.validate_evals(data), [])

    def test_evals_missing_skill_and_empty_cases(self):
        errs = ev.validate_evals({"cases": []})
        self.assertTrue(any("skill" in e for e in errs))
        self.assertTrue(any("cases" in e for e in errs))

    def test_evals_dup_id_and_missing_prompt_and_bad_assertion(self):
        data = {"skill": "s", "cases": [
            {"id": 1, "prompt": "p", "assertions": [{"type": "contains"}]},
            {"id": 1, "assertions": [{"value": 1}]}]}
        errs = ev.validate_evals(data)
        self.assertTrue(any("дубликат id" in e for e in errs))
        self.assertTrue(any("prompt" in e for e in errs))
        self.assertTrue(any("type" in e for e in errs))
        self.assertTrue(any("value" in e for e in errs))

    def test_pressure_scenarios_key(self):
        self.assertEqual(ev.validate_pressure(
            {"skill": "s", "scenarios": [{"id": 1, "prompt": "p"}]}), [])
        self.assertTrue(ev.validate_pressure({"skill": "s"}))

    def test_triggers(self):
        self.assertEqual(ev.validate_triggers(
            {"should_trigger": ["a"], "should_not": ["b"]}), [])
        self.assertTrue(ev.validate_triggers({"should_trigger": [], "should_not": ["b"]}))


class AggregateCase(unittest.TestCase):
    def test_pass_rate_and_stats(self):
        runs = [{"passed": True, "duration_s": 1.0, "tokens": 100},
                {"passed": False, "duration_s": 3.0, "tokens": 200},
                {"passed": None, "duration_s": 2.0, "tokens": None}]
        a = ev.aggregate_runs(runs)
        self.assertEqual(a["total"], 3)
        self.assertEqual(a["graded"], 2)
        self.assertEqual(a["passed"], 1)
        self.assertEqual(a["pass_rate"], 0.5)
        self.assertEqual(a["tokens_mean"], 150.0)   # None отфильтрован
        self.assertGreater(a["duration_std"], 0)

    def test_no_graded_pass_rate_none(self):
        self.assertIsNone(ev.aggregate_runs([{"passed": None}])["pass_rate"])

    def test_build_benchmark_delta(self):
        b = ev.build_benchmark("s", [{"passed": True, "tokens": 100}],
                               [{"passed": False, "tokens": 80}])
        self.assertEqual(b["delta"]["pass_rate"], 1.0)
        self.assertEqual(b["delta"]["tokens_mean"], 20.0)

    def test_build_benchmark_no_baseline(self):
        b = ev.build_benchmark("s", [{"passed": True}])
        self.assertNotIn("baseline", b)
        self.assertNotIn("delta", b)


class DescriptionTuningCase(unittest.TestCase):
    def setUp(self):
        # judge: «сработает», если в запросе есть слово 'trigger'
        self.judge = lambda desc, q: "trigger" in q.lower()
        self.ts = {"should_trigger": ["please trigger this", "trigger now"],
                   "should_not": ["unrelated ask", "another miss"]}

    def test_score_perfect(self):
        s = ev.score_description("desc", self.ts, self.judge)
        self.assertEqual(s["accuracy"], 1.0)
        self.assertEqual(s["f1"], 1.0)
        self.assertFalse(s["over_limit"])

    def test_over_limit_flag(self):
        s = ev.score_description("x" * (ev.DESC_MAX + 1), self.ts, self.judge)
        self.assertTrue(s["over_limit"])

    def test_select_rejects_too_long_and_empty(self):
        res = ev.select_best_description(
            ["good description", "x" * 200, ""], self.ts, self.judge)
        self.assertEqual(res["best"], "good description")
        self.assertEqual(len(res["rejected"]), 2)

    def test_select_all_rejected(self):
        res = ev.select_best_description(["x" * 200], self.ts, self.judge)
        self.assertIsNone(res["best"])


class ScaffoldResolveCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scaffold_creates_valid_stubs_idempotent(self):
        d = self.root / "skills" / "quality" / "test-writer"
        created = ev.scaffold_evals(d, "test-writer")
        self.assertEqual(len(created), 3)
        evals = json.loads((d / "evals" / "evals.json").read_text())
        self.assertEqual(ev.validate_evals(evals), [])
        pressure = json.loads((d / "evals" / "pressure.json").read_text())
        self.assertEqual(ev.validate_pressure(pressure), [])
        triggers = json.loads((d / "evals" / "triggers.json").read_text())
        self.assertEqual(ev.validate_triggers(triggers), [])
        self.assertEqual(ev.scaffold_evals(d, "test-writer"), [])  # idempotent

    def test_resolve_skill_by_name_and_path(self):
        self.assertEqual(ev.resolve_skill(self.env, "code-style").name, "code-style")
        self.assertEqual(ev.resolve_skill(self.env, "php/code-style").name, "code-style")

    def test_resolve_skill_not_found_dies(self):
        with self.assertRaises(SystemExit):
            ev.resolve_skill(self.env, "no-such-skill")

    def test_resolve_skill_ambiguous_dies(self):
        fx.write_skill(self.root / "skills" / "devops" / "code-style", "code-style",
                       description="dup")
        with self.assertRaises(SystemExit):
            ev.resolve_skill(self.env, "code-style")

    def test_evals_coverage(self):
        before, total = ev.evals_coverage(self.root)
        self.assertEqual(before, 0)
        self.assertGreater(total, 0)
        ev.scaffold_evals(self.root / "skills" / "quality" / "test-writer", "test-writer")
        after, _ = ev.evals_coverage(self.root)
        self.assertEqual(after, 1)

    def test_coverage_excludes_upstream(self):
        d = self.root / "skills" / "devops" / "ext-skill"
        fx.write_skill(d, "ext-skill", description="x")
        fx.write_upstream(d)                       # помечает как upstream
        _, total_with_upstream = ev.evals_coverage(self.root)
        # upstream-скилл не попадает в знаменатель локального покрытия
        names = {p.parent.name for p in (self.root / "skills").glob("*/*/SKILL.md")
                 if not (p.parent / "upstream.json").exists()}
        self.assertEqual(total_with_upstream, len(names))


class ViewerCmdBuildCase(unittest.TestCase):
    def test_render_markdown(self):
        b = ev.build_benchmark("my-skill", [{"passed": True, "tokens": 50}],
                               [{"passed": False, "tokens": 40}])
        md = ev.render_markdown(b)
        self.assertIn("my-skill", md)
        self.assertIn("with-skill", md)
        self.assertIn("baseline", md)

    def test_render_html_escapes(self):
        html = ev.render_html(ev.build_benchmark("s", [{"passed": True}]))
        self.assertIn("<!doctype html>", html)

    def test_build_run_cmd_flags(self):
        cmd = ev.build_run_cmd("claude", "do it", "SKILL BODY")
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertIn("--output-format", cmd)
        self.assertIn("--append-system-prompt", cmd)
        self.assertIn("SKILL BODY", cmd)
        # baseline (без скилла) — без инъекции системного промта
        self.assertNotIn("--append-system-prompt", ev.build_run_cmd("claude", "do it"))


if __name__ == "__main__":
    unittest.main()
