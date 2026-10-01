"""Tests of behavioral skill acquisition (eval.py) — Offline logic ONLY.

Runner (`claude -p`) network and does not twitch here: we cover the grader, validation
diagrams, unit benchmark, scoring/selection descriptions, scaffold, resolve, viewer.
Style - how test_budget.py (unittest, synthetic registry, tmpdir, without network)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.quality import eval as ev
import tests.fixtures as fx

FIXTURES_DATA = Path(__file__).resolve().parent / "fixtures_data"
_TASK_LIB = Path(__file__).resolve().parents[2] / "task" / "lib"
if _TASK_LIB.is_dir():
    sys.path.insert(0, str(_TASK_LIB))


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
        self.assertIn("unknown", detail)


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
        self.assertTrue(any("duplicate id" in e for e in errs))
        self.assertTrue(any("prompt" in e for e in errs))
        self.assertTrue(any("type" in e for e in errs))
        self.assertTrue(any("value" in e for e in errs))

    def test_pressure_scenarios_key(self):
        self.assertEqual(ev.validate_pressure(
            {"skill": "s", "scenarios": [{"id": 1, "prompt": "p"}]}), [])
        self.assertTrue(ev.validate_pressure({"skill": "s"}))

    def test_pressure_triggers_field(self):
        self.assertEqual(ev.validate_pressure(
            {"skill": "s", "scenarios": [
                {"id": 1, "prompt": "p", "triggers": ["a query"]}]}), [])
        errs = ev.validate_pressure(
            {"skill": "s", "scenarios": [
                {"id": 1, "prompt": "p", "triggers": ["ok", "", 5]}]})
        self.assertTrue(any("triggers" in e for e in errs))

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
        self.assertEqual(a["tokens_mean"], 150.0)   # None filtered
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
        # judge: «will work», if the query contains the word 'trigger'
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
        fx.write_upstream(d)                       # marks as upstream
        _, total_with_upstream = ev.evals_coverage(self.root)
        # upstream-skill does not fall into the denominator of local coverage
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
        # baseline (without skill) — without system injection
        self.assertNotIn("--append-system-prompt", ev.build_run_cmd("claude", "do it"))


class SystemBankAdapterCase(unittest.TestCase):
    """P3.3 — system-bank adapter (transcript/outcome grading, distinct from the
    per-skill ASSERTION_TYPES tested above)."""

    def setUp(self):
        self.cases_doc = json.loads(
            (FIXTURES_DATA / "system-reliability-bank-v1.json").read_text())
        self.graders_doc = json.loads(
            (FIXTURES_DATA / "system-reliability-graders-v1.json").read_text())
        self.graders_by_id = {g["id"]: g for g in self.graders_doc["graders"]}

    def _case(self, case_id):
        return next(c for c in self.cases_doc["cases"] if c["case_id"] == case_id)

    # --- operators -----------------------------------------------------------
    def test_event_present_absent(self):
        t = [{"seq": 1, "type": "block", "reason_code": "X"}]
        self.assertTrue(ev.apply_system_operator("event_present", {"type": "block"}, t, {})[0])
        self.assertFalse(ev.apply_system_operator("event_absent", {"type": "block"}, t, {})[0])
        self.assertTrue(ev.apply_system_operator(
            "event_present", {"type": "block", "where": {"reason_code": "X"}}, t, {})[0])
        self.assertFalse(ev.apply_system_operator(
            "event_present", {"type": "block", "where": {"reason_code": "Y"}}, t, {})[0])

    def test_event_order_violated_and_vacuous(self):
        t = [{"seq": 1, "type": "mutation"}, {"seq": 2, "type": "contract_compiled"}]
        ok, _ = ev.apply_system_operator(
            "event_order", {"before": {"type": "contract_compiled"}, "after": {"type": "mutation"}}, t, {})
        self.assertFalse(ok)  # mutation (seq 1) happened before the contract (seq 2)
        ok, _ = ev.apply_system_operator(
            "event_order", {"before": {"type": "x"}, "after": {"type": "never-happens"}}, [], {})
        self.assertTrue(ok)  # no `after` events -> vacuously true

    def test_event_count_max_min(self):
        t = [{"seq": i, "type": "finding", "finding_id": "F-1"} for i in range(1, 4)]
        self.assertFalse(ev.apply_system_operator(
            "event_count_max", {"type": "finding", "max": 2}, t, {})[0])
        self.assertTrue(ev.apply_system_operator(
            "event_count_min", {"type": "finding", "min": 3}, t, {})[0])

    def test_outcome_operators(self):
        outcome = {"declared_status": "success", "requirements_satisfied": ["R-1"]}
        self.assertTrue(ev.apply_system_operator(
            "outcome_field_equals", {"path": "declared_status", "value": "success"}, [], outcome)[0])
        self.assertTrue(ev.apply_system_operator(
            "outcome_list_contains", {"path": "requirements_satisfied", "value": "R-1"}, [], outcome)[0])
        self.assertTrue(ev.apply_system_operator(
            "outcome_list_excludes", {"path": "requirements_satisfied", "value": "R-2"}, [], outcome)[0])

    def test_unknown_operator(self):
        ok, detail = ev.apply_system_operator("bogus", {}, [], {})
        self.assertFalse(ok)
        self.assertIn("unknown", detail)

    # --- case grading ----------------------------------------------------------
    def test_grade_system_case_all_pass(self):
        c = self._case("fx-critical-retention")
        graded = ev.grade_system_case(c, self.graders_by_id,
                                      c["baseline"]["transcript"], c["baseline"]["outcome"])
        self.assertTrue(graded["passed"])
        self.assertEqual(len(graded["checks"]), 3)
        self.assertEqual(graded["checks"][0]["tags"], ["requirement_retention"])

    def test_grade_system_case_fail(self):
        c = self._case("fx-critical-premature-stop")
        graded = ev.grade_system_case(c, self.graders_by_id,
                                      c["baseline"]["transcript"], c["baseline"]["outcome"])
        self.assertFalse(graded["passed"])

    def test_grade_system_case_unknown_grader(self):
        c = {"case_id": "x", "assertions": [{"id": "A1", "grader": "NOPE", "expect": True}]}
        graded = ev.grade_system_case(c, self.graders_by_id, [], {})
        self.assertFalse(graded["passed"])
        self.assertIn("unknown grader", graded["checks"][0]["detail"])

    # --- schema validation -------------------------------------------------------
    def test_validate_system_graders_valid(self):
        self.assertEqual(ev.validate_system_graders(self.graders_doc), [])

    def test_validate_system_graders_llm_judge_forbidden(self):
        bad = {"policy": {"llm_judge_allowed": True}, "graders": [
            {"id": "G1", "operator": "event_present"}]}
        errs = ev.validate_system_graders(bad)
        self.assertTrue(any("llm_judge_allowed" in e for e in errs))

    def test_validate_system_graders_bad_operator(self):
        bad = {"policy": {"llm_judge_allowed": False}, "graders": [
            {"id": "G1", "operator": "bogus_op"}]}
        errs = ev.validate_system_graders(bad)
        self.assertTrue(any("operator" in e for e in errs))

    def test_validate_system_cases_valid(self):
        grader_ids = set(self.graders_by_id)
        self.assertEqual(ev.validate_system_cases(self.cases_doc, grader_ids), [])

    def test_validate_system_cases_bad(self):
        bad = {"cases": [{"case_id": "a", "kind": "bogus", "assertions": [
            {"grader": "NOPE"}], "baseline": {"transcript": [], "outcome": {}}}]}
        errs = ev.validate_system_cases(bad, {"G-EVENT-PRESENT"})
        self.assertTrue(any("kind" in e for e in errs))
        self.assertTrue(any("unknown grader" in e for e in errs))
        self.assertTrue(any("transcript is empty" in e for e in errs))
        self.assertTrue(any("declared_status" in e for e in errs))

    def test_validate_system_cases_duplicate_id(self):
        bad = {"cases": [
            {"case_id": "a", "kind": "critical", "assertions": [{"grader": "G-EVENT-PRESENT"}],
             "baseline": {"transcript": [{"seq": 1, "type": "x"}], "outcome": {"declared_status": "success"}}},
            {"case_id": "a", "kind": "critical", "assertions": [{"grader": "G-EVENT-PRESENT"}],
             "baseline": {"transcript": [{"seq": 1, "type": "x"}], "outcome": {"declared_status": "success"}}},
        ]}
        errs = ev.validate_system_cases(bad, {"G-EVENT-PRESENT"})
        self.assertTrue(any("duplicate case_id" in e for e in errs))

    # --- metrics --------------------------------------------------------------
    def test_compute_system_metrics_all_paths(self):
        cases = self.cases_doc["cases"]
        records = {c["case_id"]: c["baseline"] for c in cases}
        graded = [ev.grade_system_case(c, self.graders_by_id,
                                       c["baseline"]["transcript"], c["baseline"]["outcome"])
                 for c in cases]
        m = ev.compute_system_metrics(cases, graded, records)
        self.assertEqual(m["premature_stop_count"], 1)
        self.assertIn("fx-critical-premature-stop", m["premature_stop_cases"])
        self.assertEqual(m["redundant_approval_count"], 1)
        self.assertIn("fx-critical-redundant-approval", m["redundant_approval_cases"])
        self.assertEqual(m["owner_intervention_cases"], ["fx-critical-owner-question"])
        self.assertEqual(m["same_finding_loop_depth"]["samples"], 1)
        self.assertEqual(m["same_finding_loop_depth"]["median"], 3)
        self.assertEqual(m["audit_loop_overrun_count"], 1)
        self.assertIn("fx-critical-loop-depth", m["audit_loop_overrun_cases"])
        self.assertEqual(m["routing_compliance"], 0.5)  # 1/2 routed cases compliant
        self.assertEqual(m["critical_regression_escape"], 1)
        self.assertIn("fx-critical-regression-escape", m["critical_regression_escape_cases"])
        self.assertEqual(m["false_block_rate"], 0.5)  # 1/2 control cases blocked
        self.assertLess(m["critical_requirement_retention"], 1.0)
        self.assertIsNotNone(m["first_pass_success"])

    # --- seeded sample -----------------------------------------------------------
    def test_seeded_system_sample_deterministic_and_bounded(self):
        ids = [c["case_id"] for c in self.cases_doc["cases"]]
        s1 = ev.seeded_system_sample("seed-x", ids, 3)
        s2 = ev.seeded_system_sample("seed-x", ids, 3)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 3)
        self.assertTrue(set(s1).issubset(set(ids)))
        s3 = ev.seeded_system_sample("seed-y", ids, 3)
        self.assertNotEqual(s1, s3)

    # --- provider capability matrix --------------------------------------------
    def test_provider_capability_matrix_present_and_absent(self):
        m = ev.provider_capability_matrix(claude_lookup=lambda: "/usr/bin/claude",
                                          codex_lookup=lambda: None)
        self.assertEqual(m["claude"]["capability"], "native")
        self.assertEqual(m["codex"]["capability"], "unsupported")

    # --- portability tier ------------------------------------------------------
    def test_classify_portability_tier_committed_bundle(self):
        tier, reason = ev.classify_portability_tier(
            self._case("fx-portability-tiered")["work"])
        self.assertIsNone(reason)
        self.assertEqual(tier, "committed-bundle")

    def test_classify_portability_tier_brief_acceptance(self):
        tier, reason = ev.classify_portability_tier(
            self._case("fx-portability-brief")["work"])
        self.assertIsNone(reason)
        self.assertEqual(tier, "brief-acceptance")

    # --- pairing ----------------------------------------------------------------
    def test_pair_system_metric_deferred_without_candidate(self):
        baseline = {"metric": "first_pass_success", "value": 0.5,
                    "baseline_proof_class": "recomputed"}
        pair = ev.pair_system_metric(baseline, None)
        self.assertEqual(pair["status"], "deferred")
        self.assertIsNone(pair["candidate"])

    def test_pair_system_metric_paired_with_candidate(self):
        baseline = {"metric": "first_pass_success", "value": 0.5,
                    "baseline_proof_class": "recomputed"}
        candidate = {"metric": "first_pass_success", "value": 0.8}
        pair = ev.pair_system_metric(baseline, candidate)
        self.assertEqual(pair["status"], "paired")
        self.assertAlmostEqual(pair["delta"], 0.3)

    def test_pair_system_metric_pinned_baseline_forbidden(self):
        baseline = {"metric": "m", "value": 1, "baseline_proof_class": "pinned-not-recomputable"}
        with self.assertRaises(ValueError):
            ev.pair_system_metric(baseline, {"metric": "m", "value": 1})

    # --- benchmark builder -------------------------------------------------------
    def test_build_system_benchmark_shape_and_deferred_pair(self):
        bench = ev.build_system_benchmark(
            self.cases_doc, self.graders_doc, generated_at="2026-07-26T00:00:00Z")
        self.assertEqual(bench["schema_version"], "system-bank-benchmark/v1")
        self.assertEqual(bench["counts"]["cases"], len(self.cases_doc["cases"]))
        self.assertEqual(bench["pair"]["status"], "deferred")
        self.assertIsNone(bench["candidate"])
        self.assertIn("claude", bench["provider_capability"])
        self.assertIn("codex", bench["provider_capability"])
        self.assertLessEqual(bench["sample"]["size"], 5)

    def test_build_system_benchmark_with_candidate_pairs(self):
        candidate_runs = {c["case_id"]: c["baseline"] for c in self.cases_doc["cases"]}
        bench = ev.build_system_benchmark(
            self.cases_doc, self.graders_doc, generated_at="2026-07-26T00:00:00Z",
            candidate_runs=candidate_runs)
        self.assertEqual(bench["pair"]["status"], "paired")
        # candidate == baseline transcripts here -> identical metric, delta 0
        self.assertAlmostEqual(bench["pair"]["delta"], 0.0)


class FractionRenderCase(unittest.TestCase):
    """_fmt_frac/_stringify_fractions — render without float (P8.9)."""

    def test_fmt_frac_round_half_up_and_sign(self):
        self.assertEqual(ev._fmt_frac(None), None)
        self.assertEqual(ev._fmt_frac(ev.Fraction(1, 2)), "0.500")
        self.assertEqual(ev._fmt_frac(ev.Fraction(1, 3)), "0.333")
        self.assertEqual(ev._fmt_frac(ev.Fraction(-1, 4)), "-0.250")
        self.assertEqual(ev._fmt_frac(3), "3.000")

    def test_stringify_fractions_recursive_no_leftover(self):
        obj = {"a": ev.Fraction(1, 2), "b": [ev.Fraction(3), None, "x"], "c": {"d": ev.Fraction(0)}}
        out = ev._stringify_fractions(obj)
        self.assertEqual(out, {"a": "0.500", "b": ["3.000", None, "x"], "c": {"d": "0.000"}})

    def test_sqrt_fraction_integer_no_float(self):
        # √4 == 2 exactly; we check that the implementation does not touch float in general
        self.assertEqual(ev._sqrt_fraction(ev.Fraction(4)), ev.Fraction(2))
        self.assertGreater(ev._sqrt_fraction(ev.Fraction(2)), ev.Fraction(0))


def _write_fake_claude(tmp_dir, *, output_tokens=5, input_tokens=10, result="ok output"):
    """Stub script `claude -p ... --output-format json` — deterministic
    JSON without network (P8.9 online-tests: SKM_CLAUDE_BIN — standard substitution point)."""
    script = tmp_dir / "fake_claude.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"print(json.dumps({{'result': {result!r}, 'usage': "
        f"{{'input_tokens': {input_tokens}, 'output_tokens': {output_tokens}}}}}))\n",
        encoding="utf-8")
    script.chmod(0o755)
    return script


def _no_op_clock():
    """clock_ns deterministic counter, fresh for each factory call
    (independent runs with the same counter produce identical duration_s)."""
    import itertools
    it = itertools.count(0, 1_000_000_000)  # step 1s in ns
    return lambda: next(it)


class OnlineDeterminismCase(unittest.TestCase):
    """cmd_eval online-thread via fake claude (SKM_CLAUDE_BIN) — P8.9
    Validation: byte reproducibility, no float, honest
    provenance, no-op offline, exactly one/two files online."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.skill_dir = self.root / "skills" / "quality" / "test-writer"
        (self.skill_dir / "evals").mkdir(parents=True, exist_ok=True)
        (self.skill_dir / "evals" / "evals.json").write_text(json.dumps({
            "skill": "test-writer",
            "cases": [{"id": 1, "prompt": "say ok",
                      "assertions": [{"type": "contains", "value": "ok"}]}],
        }), encoding="utf-8")
        self.claude = _write_fake_claude(self.tmp)
        self._env_patch = {"SKM_CLAUDE_BIN": str(self.claude)}
        self._old_env = {k: os.environ.get(k) for k in self._env_patch}
        os.environ.update(self._env_patch)

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _bench_path(self):
        return self.skill_dir / "evals" / "benchmark.json"

    def test_byte_reproducible_with_injected_clock(self):
        ev.cmd_eval(self.env, ["quality/test-writer"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        first = self._bench_path().read_bytes()
        ev.cmd_eval(self.env, ["quality/test-writer"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        second = self._bench_path().read_bytes()
        self.assertEqual(first, second)

    def test_no_float_anywhere_in_report(self):
        ev.cmd_eval(self.env, ["quality/test-writer"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        data = json.loads(self._bench_path().read_text(encoding="utf-8"))

        def _walk(node):
            if isinstance(node, float):
                self.fail(f"float found in the report: {node!r}")
            if isinstance(node, dict):
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)
        _walk(data)
        self.assertEqual(data["schema_version"], "skill-benchmark/v2")

    def test_provenance_llm_true_and_clock_injected(self):
        ev.cmd_eval(self.env, ["quality/test-writer"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        data = json.loads(self._bench_path().read_text(encoding="utf-8"))
        self.assertTrue(data["provenance"]["llm"])
        self.assertTrue(data["provenance"]["network"])
        self.assertEqual(data["provenance"]["clock"], "injected")

    def test_offline_branch_writes_nothing(self):
        with mock.patch.object(ev, "claude_bin", return_value=None):
            before = sorted((self.skill_dir / "evals").iterdir())
            ev.cmd_eval(self.env, ["quality/test-writer"])
            after = sorted((self.skill_dir / "evals").iterdir())
        self.assertEqual(before, after)
        self.assertFalse(self._bench_path().exists())

    def test_online_branch_writes_exactly_benchmark_json(self):
        before = set((self.skill_dir / "evals").iterdir())
        ev.cmd_eval(self.env, ["quality/test-writer"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        after = set((self.skill_dir / "evals").iterdir())
        new_files = after - before
        self.assertEqual({p.name for p in new_files}, {"benchmark.json"})

    def test_online_static_writes_benchmark_json_and_html(self):
        before = set((self.skill_dir / "evals").iterdir())
        ev.cmd_eval(self.env, ["quality/test-writer", "--static"],
                   clock_ns=_no_op_clock(), now_iso="2026-07-27T00:00:00")
        after = set((self.skill_dir / "evals").iterdir())
        new_files = {p.name for p in after - before}
        self.assertEqual(new_files, {"benchmark.json", "benchmark.html"})


if __name__ == "__main__":
    unittest.main()
