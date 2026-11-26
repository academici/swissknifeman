"""aicore.content.eval: the moved grader, validators, benchmark builders, runner, viewers and scaffold.

The skill library's tests of `skiller eval` stay as the integration tests; these run the same
functions on synthetic data in a temporary directory."""
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from aicore.content import eval as ev

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class GraderCase(unittest.TestCase):
    def test_assertion_types(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / "out.txt").write_text("x", encoding="utf-8")
            checks = [
                ({"type": "contains", "value": "ABC"}, "x abc y", True),
                ({"type": "contains", "value": "ABC", "flags": {"case_sensitive": True}}, "x abc y", False),
                ({"type": "not_contains", "value": "zzz"}, "abc", True),
                ({"type": "regex", "value": r"\d+\.\d+"}, "v1.2", True),
                ({"type": "not_regex", "value": r"\d+\.\d+"}, "none", True),
                ({"type": "min_words", "value": 3}, "a b", False),
                ({"type": "file_exists", "value": "out.txt"}, "", True),
                ({"type": "file_absent", "value": "out.txt"}, "", False),
                ({"type": "bogus", "value": "x"}, "x", False),
            ]
            for assertion, output, expected in checks:
                with self.subTest(assertion=assertion):
                    self.assertEqual(ev.grade_assertion(assertion, output, ws)[0], expected)

    def test_file_assertions_stay_inside_the_workspace(self):
        with tempfile.TemporaryDirectory() as ws:
            ok, _ = ev.grade_assertion({"type": "file_exists", "value": "../escape"}, "", ws)
            self.assertFalse(ok)

    def test_grade_case(self):
        case = {"id": 1, "assertions": [{"type": "contains", "value": "ok"},
                                        {"type": "not_contains", "value": "bad"}]}
        graded = ev.grade_case(case, "all ok")
        self.assertTrue(graded["passed"])
        self.assertFalse(ev.grade_case(case, "ok but bad")["passed"])


class ValidatorCase(unittest.TestCase):
    def test_evals_pressure_triggers(self):
        good = {"skill": "s", "cases": [{"id": 1, "prompt": "p",
                                         "assertions": [{"type": "contains", "value": "x"}]}]}
        self.assertEqual(ev.validate_evals(good), [])
        self.assertNotEqual(ev.validate_evals({"skill": "s", "cases": [{"id": 1}]}), [])
        pressure = {"skill": "s", "scenarios": [{"id": 1, "tempts": "t", "prompt": "p",
                                                 "assertions": [{"type": "contains", "value": "x"}]}]}
        self.assertEqual(ev.validate_pressure(pressure), [])
        self.assertNotEqual(ev.validate_pressure({"skill": "s", "scenarios": []}), [])
        triggers = {"skill": "s", "should_trigger": ["a"], "should_not": ["b"]}
        self.assertEqual(ev.validate_triggers(triggers), [])
        self.assertNotEqual(ev.validate_triggers({"skill": "s"}), [])

    def test_system_documents(self):
        bank = json.loads((FIXTURES / "system-reliability-bank-v1.json").read_text())
        graders = json.loads((FIXTURES / "system-reliability-graders-v1.json").read_text())
        self.assertEqual(ev.validate_system_graders(graders), [])
        ids = {g["id"] for g in graders["graders"]}
        self.assertEqual(ev.validate_system_cases(bank, ids), [])
        self.assertNotEqual(ev.validate_system_graders({"graders": []}), [])


class BenchmarkCase(unittest.TestCase):
    def test_aggregate_and_delta(self):
        with_skill = [{"passed": True, "tokens": 50, "duration_s": Fraction(2)},
                      {"passed": False, "tokens": 70, "duration_s": Fraction(4)}]
        baseline = [{"passed": False, "tokens": 40}, {"passed": False, "tokens": 40}]
        agg = ev.aggregate_runs(with_skill)
        self.assertEqual((agg["total"], agg["graded"], agg["passed"]), (2, 2, 1))
        self.assertEqual(agg["pass_rate"], Fraction(1, 2))
        self.assertEqual(agg["tokens_mean"], Fraction(60))
        bench = ev.build_benchmark("s", with_skill, baseline)
        self.assertEqual(bench["delta"]["pass_rate"], Fraction(1, 2))
        self.assertEqual(bench["delta"]["tokens_mean"], Fraction(20))
        self.assertNotIn("baseline", ev.build_benchmark("s", with_skill))

    def test_stringify_fractions(self):
        out = ev._stringify_fractions({"a": Fraction(1, 3), "b": [Fraction(2), None]})
        self.assertEqual(out, {"a": "0.333", "b": ["2.000", None]})

    def test_description_scoring_and_selection(self):
        triggers = {"should_trigger": ["yes one", "yes two"], "should_not": ["no one"]}

        def judge(description, query):
            return query.startswith("yes") and "good" in description

        score = ev.score_description("good one", triggers, judge)
        self.assertEqual((score["tp"], score["fn"], score["fp"], score["tn"]), (2, 0, 0, 1))
        self.assertEqual(score["f1"], Fraction(1))
        picked = ev.select_best_description(["bad", "good", "x" * (ev.DESC_MAX + 1), " "], triggers, judge)
        self.assertEqual(picked["best"], "good")
        self.assertEqual(len(picked["rejected"]), 2)


class RunnerCase(unittest.TestCase):
    def test_run_command(self):
        cmd = ev.build_run_cmd("claude", "do it", "SKILL BODY")
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--append-system-prompt") + 1], "SKILL BODY")
        self.assertNotIn("--append-system-prompt", ev.build_run_cmd("claude", "do it"))

    def test_run_case_without_a_binary_is_refused(self):
        saved = ev.claude_bin
        ev.claude_bin = lambda: None
        try:
            with self.assertRaises(RuntimeError):
                ev.run_case("skill", {"id": 1, "prompt": "p"}, with_skill=False, workspace="ws")
        finally:
            ev.claude_bin = saved


class SystemBankCase(unittest.TestCase):
    def setUp(self):
        self.bank = json.loads((FIXTURES / "system-reliability-bank-v1.json").read_text())
        self.graders = json.loads((FIXTURES / "system-reliability-graders-v1.json").read_text())
        self.by_id = {g["id"]: g for g in self.graders["graders"]}

    def test_operators(self):
        events = [{"seq": 1, "type": "block", "reason_code": "X"}]
        self.assertTrue(ev.apply_system_operator("event_present", {"type": "block"}, events, {})[0])
        self.assertFalse(ev.apply_system_operator("event_absent", {"type": "block"}, events, {})[0])
        self.assertTrue(ev.apply_system_operator(
            "outcome_field_equals", {"path": "status", "value": "ok"}, [], {"status": "ok"})[0])
        self.assertFalse(ev.apply_system_operator("nope", {}, [], {})[0])

    def test_cases_grade_and_metrics(self):
        cases = self.bank["cases"]
        graded = [ev.grade_system_case(c, self.by_id, c["baseline"]["transcript"], c["baseline"]["outcome"])
                  for c in cases]
        self.assertEqual([g["case_id"] for g in graded], [c["case_id"] for c in cases])
        records = {c["case_id"]: c["baseline"] for c in cases}
        metrics = ev.compute_system_metrics(cases, graded, records)
        self.assertIn("first_pass_success", metrics)

    def test_sample_is_seeded_and_stable(self):
        ids = [f"c{i}" for i in range(10)]
        first = ev.seeded_system_sample("seed", ids, 4)
        self.assertEqual(first, ev.seeded_system_sample("seed", ids, 4))
        self.assertEqual(len(set(first)), 4)

    def test_portability_tier(self):
        self.assertEqual(ev.classify_portability_tier({"sessions": "multi"}), ("committed-bundle", None))
        self.assertEqual(ev.classify_portability_tier({"sessions": "single", "risk": "low"}),
                         ("brief-acceptance", None))

    def test_pair_metric(self):
        baseline = {"metric": "m", "value": 1, "baseline_proof_class": "recomputed"}
        self.assertEqual(ev.pair_system_metric(baseline, None)["status"], "deferred")
        paired = ev.pair_system_metric(baseline, {"metric": "m", "value": 3})
        self.assertEqual((paired["status"], paired["delta"]), ("paired", 2))
        with self.assertRaises(ValueError):
            ev.pair_system_metric({**baseline, "baseline_proof_class": "pinned"}, {"metric": "m", "value": 3})

    def test_provider_capability_probe_uses_the_lookups(self):
        matrix = ev.provider_capability_matrix(claude_lookup=lambda: "/x/claude", codex_lookup=lambda: None)
        self.assertEqual(matrix, {"claude": {"capability": "native"}, "codex": {"capability": "unsupported"}})


class ViewerAndScaffoldCase(unittest.TestCase):
    def test_markdown_and_html(self):
        bench = ev.build_benchmark("my-skill", [{"passed": True, "tokens": 50}], [{"passed": False}])
        text = ev.render_markdown(bench)
        for expected in ("# Eval: my-skill", "with-skill", "baseline"):
            self.assertIn(expected, text)
        self.assertNotIn("Context:", text)
        html = ev.render_html({"skill": "a<b", "with_skill": {}})
        self.assertIn("<!doctype html>", html)
        self.assertIn("a&lt;b", html)

    def test_scaffold_and_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            skill = Path(root) / "skills" / "b" / "demo"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
            created = ev.scaffold_evals(skill)
            self.assertEqual(sorted(p.name for p in created), ["evals.json", "pressure.json", "triggers.json"])
            self.assertEqual(ev.scaffold_evals(skill), [])
            self.assertEqual(ev.evals_coverage(root), (1, 1))
            (skill / "upstream.json").write_text("{}", encoding="utf-8")
            self.assertEqual(ev.evals_coverage(root), (0, 0))


if __name__ == "__main__":
    unittest.main()
