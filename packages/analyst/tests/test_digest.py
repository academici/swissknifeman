"""Tests digest: clean extractors (signals A/B/C/D) + protective degradation + entry in ephemeral."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from analyst import digest, lessons


def _run_report(**over):
    rr = {
        "schema": 1,
        "session_id": "sid-123",
        "generated_at": "2026-07-01T10:00:00Z",
        "tools": {"total": 5, "by_name": {"Bash": 5}},
        "files_changed": ["src/Service.php", "tests/ServiceTest.php"],
        "tool_failures": [],
        "bash": {"tests": [], "lints": [], "failed": []},
        "workflows": [],
        "devloop": None,
        "maind": None,
    }
    rr.update(over)
    return rr


class TestExtractors(unittest.TestCase):
    def test_resolved_failure(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": True},
        ], "lints": [], "failed": []})
        cands = digest.extract_resolved_failures(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["kind"], "gotcha")
        self.assertEqual(c["provenance"]["detector"], "resolved-failure")
        self.assertIn("test-pass", c["evidence"])
        self.assertIn("attempts:2", c["evidence"])
        # files/counters are located in meta (action — pure semantic text, S11)
        self.assertIn("ServiceTest.php", c["meta"]["files"])
        self.assertEqual(c["meta"]["attempts"], 2)
        self.assertNotIn("Specify", c["action"])
        self.assertIn("Specify", c["review_hint"])

    def test_failure_without_pass_is_ignored(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_dissimilar_pass_not_matched(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest tests/ServiceTest.php", "ok": False},
            {"command": "npm run build --production", "ok": True},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_diagnostic_command_is_not_a_resolved_failure(self):
        """The hook puts intelligence in bash.tests by runner substring (`grep vitest`, `... ||`),
        but the lesson from «fell→passed» such a pair is trash (trigger≈action). Filtering."""
        # the same field case from vaulter: `ls .bin | grep vitest ||` (fail) + add. sample (pass)
        rr = _run_report(bash={"tests": [
            {"command": "ls node_modules/.bin/ | grep -E 'vue-tsc|vitest|vite$' ||", "ok": False},
            {"command": "ls node_modules/.bin/ | grep -E 'vue-tsc|vitest|vite$' 2>/dev/null", "ok": True},
        ], "lints": [], "failed": []})
        self.assertEqual(digest.extract_resolved_failures(rr, scope="s", project="p"), [])

    def test_real_runner_still_extracted_alongside_diagnostic(self):
        """The actual running of a runner remains a lesson, even if diagnostic-noise."""
        rr = _run_report(bash={"tests": [
            {"command": "grep -rn vitest package.json", "ok": False},        # reconnaissance - ignore
            {"command": "vendor/bin/pest tests/FooTest.php", "ok": False},   # real run
            {"command": "vendor/bin/pest tests/FooTest.php", "ok": True},
        ], "lints": [], "failed": []})
        cands = digest.extract_resolved_failures(rr, scope="s", project="p")
        self.assertEqual(len(cands), 1)
        self.assertIn("FooTest", cands[0]["trigger"])

    def test_is_real_check_helper(self):
        self.assertTrue(digest._is_real_check("vendor/bin/pest 2>&1 | tail -4"))
        self.assertTrue(digest._is_real_check("cd x && npm test"))
        self.assertTrue(digest._is_real_check("bash scripts/validate.sh"))
        self.assertFalse(digest._is_real_check("ls .bin | grep vitest || echo NO"))
        self.assertFalse(digest._is_real_check("grep -rn pest packages/"))
        self.assertFalse(digest._is_real_check("git status --short"))

    def test_is_real_check_laravel_runners(self):
        """N2a: `php artisan test`/`sail test` — dominant runner Laravel-stack
        ecosystems; until fixed `_RUNNER_EXEC` did not resolve them, the signal A was blind."""
        self.assertTrue(digest._is_real_check("php artisan test"))
        self.assertTrue(digest._is_real_check("php artisan test --filter Foo"))
        self.assertTrue(digest._is_real_check("sail test"))

    def test_is_real_check_guarded_pipe_is_still_a_real_run(self):
        """N2b: `||`/`| xargs` guard-patterns actually execute the runner and carry it
        exit-code - blind refusal after the fact `||` in the team lost such resolved-failure."""
        self.assertTrue(digest._is_real_check("pytest tests/ || exit 1"))
        self.assertTrue(digest._is_real_check("printf '%s' tests/*_test.py | xargs pytest"))

    def test_workarounds(self):
        rr = _run_report(devloop={"workarounds": [
            "hardcoded limit 100, no config yet",
            "hardcoded limit 100, no config yet",  # double - collapse
        ]})
        cands = digest.extract_workarounds(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["provenance"]["detector"], "workaround")
        self.assertIn("workaround", cands[0]["evidence"])
        self.assertIn("hardcoded", cands[0]["action"])

    def test_extract_candidates_combines_and_degrades(self):
        self.assertEqual(digest.extract_candidates(None, scope="s", project="p"), [])
        self.assertEqual(digest.extract_candidates({}, scope="s", project="p"), [])
        rr = _run_report(
            bash={"tests": [
                {"command": "pytest test_x.py -k slow", "ok": False},
                {"command": "pytest test_x.py -k slow", "ok": True}],
                "lints": [], "failed": []},
            devloop={"workarounds": ["workaround X"]})
        cands = digest.extract_candidates(rr, scope="s", project="p")
        self.assertEqual(len(cands), 2)

    def test_workflow_relaunch(self):
        rr = _run_report(workflow_relaunch=[
            {"name": "wf-dterema-site-p3-api", "count": 11,
             "statuses": {"async_launched": 11}}])
        cands = digest.extract_workflow_relaunch(rr, scope="project:proj", project="proj")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["provenance"]["detector"], "workflow-relaunch")
        self.assertIn("11", cands[0]["trigger"])
        self.assertIn("wf-dterema-site-p3-api", cands[0]["trigger"])
        self.assertIn("count:11", cands[0]["evidence"])

    def test_workflow_relaunch_empty_no_lesson(self):
        rr = _run_report(workflow_relaunch=[])
        self.assertEqual(digest.extract_workflow_relaunch(rr, scope="s", project="p"), [])

    def test_workflow_relaunch_via_extract_candidates(self):
        rr = _run_report(workflow_relaunch=[
            {"name": "wf-x", "count": 3, "statuses": {"async_launched": 3}}])
        cands = digest.extract_candidates(rr, scope="s", project="p")
        detectors = {c["provenance"]["detector"] for c in cands}
        self.assertIn("workflow-relaunch", detectors)


class TestExtractPathologies(unittest.TestCase):
    """Signal C: core.pathology.detect + relapse rule (≥2 from the last 5 runs).
    detector "protected-write" — most deterministic (fires when the list is not empty,
    without thresholds/shares), is useful as a control code for checking the recurrence rule itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        self.runs = self.proj / ".claude" / "runs"
        self.runs.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, sid, mtime, hit=False):
        """Synthetic run-report on disk.claude/runs/<sid>.json with fix. mtime
        (os.utime) — deterministic order «last 5» without races in recording time."""
        rr = {"session_id": sid, "protected_writes": (["/pack/skills/x/SKILL.md"] if hit else [])}
        p = self.runs / f"{sid}.json"
        p.write_text(json.dumps(rr), encoding="utf-8")
        os.utime(p, (mtime, mtime))
        return rr

    def test_no_findings_no_lesson(self):
        current = {"session_id": "cur", "protected_writes": []}
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_single_occurrence_out_of_five_no_lesson(self):
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self._write(sid, base + i, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        # pathology only in the current run (1 out of 5) — no relapse, lesson not created
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_two_occurrences_out_of_five_creates_lesson(self):
        base = 1_800_000_000
        self._write("h1", base, hit=False)
        self._write("h2", base + 1, hit=True)   # the same code has already been seen
        self._write("h3", base + 2, hit=False)
        self._write("h4", base + 3, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        cands = digest.extract_pathologies(current, self.proj)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c["kind"], "gotcha")
        self.assertEqual(c["provenance"]["detector"], "protected-write")
        self.assertIn("overrides", c["action"])
        self.assertIn(".claude/rules/*-overrides.md", c["action"])
        self.assertIn("recurred:2/5", c["evidence"])
        self.assertIn("session:cur", c["evidence"])

    def test_window_excludes_reports_beyond_last_five(self):
        base = 1_800_000_000
        # oldest run (outside the window of 5) — with pathology, but should not be seen
        self._write("stale", base, hit=True)
        self._write("h1", base + 10, hit=False)
        self._write("h2", base + 11, hit=False)
        self._write("h3", base + 12, hit=False)
        self._write("h4", base + 13, hit=False)
        current = {"session_id": "cur", "protected_writes": ["/pack/skills/x/SKILL.md"]}
        # without the window there would be 2 matches (stale+cur); in the last 5 window "stale" not included →
        # no relapse
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_code_without_remediation_stays_signal_even_if_recurring(self):
        # no-op-run — code WITHOUT ready-made remediation (is not included _PATHOLOGY_REMEDIATIONS):
        # even persistent relapse (5 out of 5) should not give rise to a lesson - it is a signal for analyze.
        base = 1_800_000_000
        noop = {"tools": {"total": 25}, "files_changed": [],
                "bash": {"tests": [], "lints": [], "failed": []}, "retrieval": {"calls": 0}}
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self.runs.joinpath(f"{sid}.json").write_text(
                json.dumps(dict(noop, session_id=sid)), encoding="utf-8")
            os.utime(self.runs / f"{sid}.json", (base + i, base + i))
        current = dict(noop, session_id="cur")
        self.assertEqual(digest.extract_pathologies(current, self.proj), [])

    def test_non_dict_input_degrades(self):
        self.assertEqual(digest.extract_pathologies(None, self.proj), [])
        self.assertEqual(digest.extract_pathologies("trash", self.proj), [])


class TestDigestCmd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self._tmp.name)
        (self.proj / ".claude" / "runs").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_rr(self, rr, mtime=None):
        p = self.proj / ".claude" / "runs" / f"{rr['session_id']}.json"
        p.write_text(json.dumps(rr), encoding="utf-8")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_digest_writes_ephemeral_and_is_idempotent(self):
        rr = _run_report(bash={"tests": [
            {"command": "vendor/bin/pest", "ok": False},
            {"command": "vendor/bin/pest", "ok": True}], "lints": [], "failed": []})
        self._write_rr(rr)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = lessons.list_lessons(str(self.proj), "ephemeral")
            self.assertEqual(len(eph), 1)
            # audit recorded
            audit = lessons.read_audit(str(self.proj))
            self.assertTrue(any(r.get("action") == "digest" for r in audit))
            # repeated digest does not create a duplicate
            main([str(self.proj), "digest"])
            self.assertEqual(len(lessons.list_lessons(str(self.proj), "ephemeral")), 1)
        finally:
            os.chdir(cwd)

    def test_recurring_pathology_becomes_lesson_via_cli_and_dedups_on_rerun(self):
        # 5 project runs (relapse rule reads .claude/runs in full): 3 clean + 1
        # old with the same pathology + current (latest by mtime) — also with pathology →
        # 2 out of 5 → digest should create a lesson-gotcha with detector="protected-write".
        # files_changed=[] — otherwise template _run_report() (files_changed is not empty, tests empty)
        # simultaneously triggers YOUR relapse "no-verify" and clogs assert on a clean signal.
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3"]):
            self._write_rr(_run_report(session_id=sid, protected_writes=[], files_changed=[]),
                           mtime=base + i)
        self._write_rr(_run_report(session_id="h4", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 10)
        self._write_rr(_run_report(session_id="cur", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 20)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = [L for L, _st in lessons.list_lessons(str(self.proj), "ephemeral")]
            self.assertEqual(len(eph), 1)
            pw = eph[0]
            self.assertEqual(pw["provenance"]["detector"], "protected-write")
            self.assertEqual(pw["kind"], "gotcha")
            self.assertIn("overrides", pw["action"])
            # repeated digest on the same history run - NOOP-dedup (does not produce the second lesson)
            main([str(self.proj), "digest"])
            self.assertEqual(len(lessons.list_lessons(str(self.proj), "ephemeral")), 1)
        finally:
            os.chdir(cwd)

    def test_single_pathology_occurrence_via_cli_creates_no_lesson(self):
        # only the current run is pathological (1 out of 5) — there is no relapse, there should be no lesson.
        # files_changed=[] — exclude incidental relapse "no-verify" from template _run_report()
        # (otherwise the test would stop checking the recurrence rule for a single code).
        base = 1_800_000_000
        for i, sid in enumerate(["h1", "h2", "h3", "h4"]):
            self._write_rr(_run_report(session_id=sid, protected_writes=[], files_changed=[]),
                           mtime=base + i)
        self._write_rr(_run_report(session_id="cur", files_changed=[],
                                   protected_writes=["/pack/skills/x/SKILL.md"]), mtime=base + 20)
        cwd = os.getcwd()
        try:
            os.chdir(self.proj)
            from analyst.cli import main
            main([str(self.proj), "digest"])
            eph = lessons.list_lessons(str(self.proj), "ephemeral")
            self.assertEqual(eph, [])
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
