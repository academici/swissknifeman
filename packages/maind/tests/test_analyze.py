"""Tests analyze.py: search run-report, forensics bash-log, verdict GREEN/ATTENTION/RED,
report assembly and --json. Without network/demon - health-disable slice (with_health=False),
live memory metering is not needed for parsing logic."""
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.util.partners import partner_command
from maind.analysis.analyze import (analyze_report, analytics_slice, bash_log_forensics, compute_verdict,
                           git_status, pending_lessons, run_report_source)
from maind.config import load_config
from tests.fixtures import lookup_payload, make_fake_analyst, make_repo, write_maind_config

GREEN_RR = {"schema": 1, "tools": {"total": 3, "by_name": {"Bash": 2, "Edit": 1}},
            "files_changed": ["a.py"],
            "bash": {"tests": [{"command": "pytest", "ok": True}],
                     "lints": [{"command": "ruff", "ok": True}], "failed": []},
            "tool_failures": [], "workflows": [], "devloop": None,
            "session_id": "g1"}

ATTN_RR = {"schema": 1, "tools": {"total": 2, "by_name": {"Bash": 2}},
           "files_changed": [],
           "bash": {"tests": [{"command": "pytest", "ok": True}],
                    "lints": [{"command": "ruff", "ok": False}], "failed": ["ruff"]},
           "tool_failures": [{"tool": "Bash", "snippet": "boom"}],
           "workflows": [{"name": "dev-loop", "status": "completed", "summary": "ok"}],
           "devloop": {"deferred": ["e2e test"], "tool_failures": ["perplexity-web locked"]},
           "session_id": "a1"}

RED_RR = {"schema": 1, "tools": {"total": 1, "by_name": {"Bash": 1}}, "files_changed": [],
          "bash": {"tests": [{"command": "pytest", "ok": False}], "lints": [], "failed": ["pytest"]},
          "tool_failures": [], "workflows": [{"name": "dev-loop", "status": "failed"}],
          "devloop": None, "session_id": "r1"}

# heavy scanning (Read/Grep/Glob = 40) with zero calls to the graph + empty recall
MAIND_RR = {"schema": 1, "tools": {"total": 40, "by_name": {"Read": 25, "Grep": 10, "Glob": 5}},
            "files_changed": [], "bash": {"tests": [], "lints": [], "failed": []},
            "tool_failures": [], "workflows": [], "devloop": None,
            "maind": {"memory_recall": {"calls": 2, "results": 2, "found_total": 0, "found_max": 0}},
            "session_id": "m1"}


@contextlib.contextmanager
def partner_env(analyst_bin=None):
    """Environment where analyst is the given script, or nowhere (no variable, no PATH entry with analyst)."""
    path = os.pathsep.join(entry for entry in os.environ.get("PATH", "").split(os.pathsep)
                           if not os.access(os.path.join(entry or ".", "analyst"), os.X_OK))
    env = {"PATH": path, "SKM_ANALYST_BIN": analyst_bin or os.path.join(tempfile.gettempdir(), "no-such-analyst")}
    with mock.patch.dict(os.environ, env):
        for name in ("SKM_ANALYST_ROOT", "MAIND_ANALYST_BIN"):
            os.environ.pop(name, None)
        yield


def _write_run(projdir, report):
    runs = Path(projdir) / ".claude" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{report['session_id']}.json").write_text(json.dumps(report), encoding="utf-8")


class VerdictCase(unittest.TestCase):
    def test_green(self):
        v, conf, red, reasons, repass = compute_verdict(GREEN_RR, {"dirty": False}, None)
        self.assertEqual((v, conf), ("GREEN", "high"))
        self.assertEqual((red, reasons, repass), ([], [], []))

    def test_attention_with_repass(self):
        v, conf, red, reasons, repass = compute_verdict(ATTN_RR, {"dirty": False}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertFalse(red)
        self.assertTrue(any("lint" in r for r in reasons))
        self.assertTrue(any("deferred" in r for r in reasons))
        self.assertEqual(repass, ["perplexity-web locked"])   # dev-loop tool_failures → REPEAT PASS

    def test_red_on_failed_test_and_workflow(self):
        v, _c, red, _r, _rp = compute_verdict(RED_RR, {"dirty": False}, None)
        self.assertEqual(v, "RED")
        self.assertTrue(any("test failed" in x for x in red))
        self.assertTrue(any("work flow" in x for x in red))

    def test_dirty_tree_is_attention(self):
        v, _c, _red, reasons, _rp = compute_verdict(GREEN_RR,
                                                    {"dirty": True, "working_files": 4}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertTrue(any("tree is not clean" in r for r in reasons))

    def test_no_run_report_low_confidence(self):
        v, conf, _red, _r, _rp = compute_verdict(None, {"dirty": False}, None)
        self.assertEqual((v, conf), ("GREEN", "low"))


class RunReportSourceCase(unittest.TestCase):
    def test_reads_report_codegraph_and_events_through_analyst(self):
        with tempfile.TemporaryDirectory() as tmp:
            codegraph = {"calls": 2, "ops": 1, "by_op": {"find_symbol": 2}}
            fake, calls = make_fake_analyst(
                Path(tmp) / "bin", show=lookup_payload(tmp, report=GREEN_RR, codegraph=codegraph))
            with partner_env(fake):
                source = run_report_source(tmp, "g1", "demo")
            self.assertEqual((source["status"], source["report"]["session_id"]), ("found", "g1"))
            self.assertEqual(source["codegraph"], codegraph)
            self.assertEqual(source["diagnostics"], [])
            self.assertEqual(calls(), [["runs", "show", "--project", tmp, "--session", "g1",
                                        "--project-id", "demo", "--json"]])

    def test_missing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, calls = make_fake_analyst(Path(tmp) / "bin", show=lookup_payload(tmp))
            with partner_env(fake):
                source = run_report_source(tmp)
            self.assertEqual((source["status"], source["report"]), ("missing", None))
            self.assertEqual(calls(), [["runs", "show", "--project", tmp, "--json"]])

    def test_rejected_report_keeps_the_reason_as_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(
                Path(tmp) / "bin",
                show=lookup_payload(tmp, status="rejected", reason="RUN_REPORT_PROJECT_MISMATCH"))
            with partner_env(fake):
                source = run_report_source(tmp)
            self.assertEqual(source["diagnostics"][0]["code"], "RUN_REPORT_PROJECT_MISMATCH")

    def test_no_analyst_is_unavailable_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp, partner_env():
            source = run_report_source(tmp)
        self.assertEqual((source["status"], source["reason"], source["report"]),
                         ("unavailable", "PARTNER_UNAVAILABLE", None))
        self.assertIn("SKM_ANALYST_ROOT", source["message"])
        self.assertEqual(source["diagnostics"][0]["code"], "PARTNER_UNAVAILABLE")

    def test_failing_analyst_is_unavailable_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(Path(tmp) / "bin", exit_code=3)
            with partner_env(fake):
                source = run_report_source(tmp)
            self.assertEqual((source["status"], source["reason"]), ("unavailable", "PARTNER_FAILED"))

    def test_output_without_the_needed_fields_is_bad_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stdout in ("not json", json.dumps({"lookup": {}}), json.dumps([1])):
                fake, _ = make_fake_analyst(Path(tmp) / "bin", stdout=stdout)
                with partner_env(fake):
                    source = run_report_source(tmp)
                self.assertEqual((source["status"], source["reason"]), ("unavailable", "PARTNER_BAD_OUTPUT"), stdout)

    def test_legacy_variable_still_finds_analyst(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake, _ = make_fake_analyst(Path(tmp) / "bin", show=lookup_payload(tmp, report=GREEN_RR))
            with partner_env():
                with mock.patch.dict(os.environ, {"MAIND_ANALYST_BIN": fake}):
                    source = run_report_source(tmp)
            self.assertEqual(source["status"], "found")


class RealAnalystCase(unittest.TestCase):
    """Runs the real analyst; skipped unless SKM_ANALYST_ROOT or SKM_ANALYST_BIN names one (scripts/test-integration.sh
    sets it; an analyst that only happens to be on PATH may be an older install)."""

    def setUp(self):
        if not (os.environ.get("SKM_ANALYST_ROOT") or os.environ.get("SKM_ANALYST_BIN")) \
                or partner_command("analyst") is None:
            self.skipTest("analyst not found (set SKM_ANALYST_ROOT)")

    def test_report_found_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_report_source(tmp)["status"], "missing")
            _write_run(tmp, {**GREEN_RR, "cwd": tmp})
            source = run_report_source(tmp, "g1")
            self.assertEqual((source["status"], source["report"]["session_id"]), ("found", "g1"))


class BashLogCase(unittest.TestCase):
    def test_filters_by_cwd_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            logdir = env.home / ".claude" / "logs"
            logdir.mkdir(parents=True)
            proj = os.path.join(tmp, "proj")
            recs = [
                {"cwd": proj, "session": "s1", "command": "python3 -m pytest tests/"},
                {"cwd": proj, "session": "s1", "command": "ruff check ."},
                {"cwd": "/other", "session": "s1", "command": "pytest"},   # alien cwd — weed out
                {"cwd": proj, "session": "s2", "command": "ls"},
            ]
            (logdir / "bash-commands.jsonl").write_text(
                "\n".join(json.dumps(r) for r in recs), encoding="utf-8")
            f = bash_log_forensics(env, proj)
            self.assertEqual(f["total"], 3)                     # three with the required cwd
            self.assertEqual(len(f["tests"]), 1)
            self.assertEqual(len(f["lints"]), 1)
            f_s1 = bash_log_forensics(env, proj, session="s1")
            self.assertEqual(f_s1["total"], 2)                  # filter by session

    def test_none_without_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            self.assertIsNone(bash_log_forensics(env, tmp))


class GitCase(unittest.TestCase):
    def test_non_git_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(git_status(tmp))


class ReportAssemblyCase(unittest.TestCase):
    def test_full_report_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_alpha"
            projdir.mkdir()
            fake, _ = make_fake_analyst(Path(tmp) / "bin", show=lookup_payload(projdir, report=ATTN_RR))
            projects = [{"id": "alpha", "name": "Alpha", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            with partner_env(fake):
                rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["project"], "alpha")
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertEqual(rep["confidence"], "high")
            self.assertEqual(rep["repass"], ["perplexity-web locked"])
            self.assertIsNone(rep["health"])                    # disabled
            # JSON-serializable in its entirety
            self.assertIsInstance(json.dumps(rep, ensure_ascii=False), str)

    def test_foreign_report_is_attention_and_its_red_reasons_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "corex"
            projdir.mkdir()
            fake, _ = make_fake_analyst(
                Path(tmp) / "bin",
                show=lookup_payload(projdir, status="rejected", reason="RUN_REPORT_PROJECT_MISMATCH"))
            projects = [{"id": "corex", "name": "CoreX", "type": "php-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            with partner_env(fake):
                rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["verdict"], "ATTENTION")
            self.assertEqual(rep["red"], [])
            self.assertIsNone(rep["run_report"])
            self.assertEqual(rep["run_report_diagnostics"][0]["code"],
                             "RUN_REPORT_PROJECT_MISMATCH")


class PendingLessonsCase(unittest.TestCase):
    """analyze reminds you of unwatched lessons analyst (ephemeral+candidate)."""
    def test_counts_ephemeral_and_candidate_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".claude" / "analyst" / "lessons"
            for state, n in (("ephemeral", 2), ("candidate", 1),
                             ("curated", 3), ("deprecated", 5)):
                d = base / state
                d.mkdir(parents=True)
                for i in range(n):
                    (d / f"l{i}.json").write_text("{}", encoding="utf-8")
            self.assertEqual(pending_lessons(tmp), 3)   # curated/deprecated do not count

    def test_zero_when_no_analyst_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pending_lessons(tmp), 0)

    def test_report_carries_pending_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_beta"
            projdir.mkdir()
            fake, _ = make_fake_analyst(Path(tmp) / "bin", show=lookup_payload(projdir, report=GREEN_RR))
            eph = projdir / ".claude" / "analyst" / "lessons" / "ephemeral"
            eph.mkdir(parents=True)
            (eph / "x.json").write_text("{}", encoding="utf-8")
            projects = [{"id": "beta", "name": "Beta", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            with partner_env(fake):
                rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual(rep["pending_lessons"], 1)

    def test_without_analyst_the_report_degrades_and_does_not_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env = make_repo(tmp)
            projdir = Path(tmp) / "proj_gamma"
            projdir.mkdir()
            projects = [{"id": "gamma", "name": "Gamma", "type": "node-package",
                         "status": "active", "local_path": str(projdir)}]
            write_maind_config(root, projects=projects)
            config, _ = load_config(env)
            with partner_env():
                rep = analyze_report(env, config, config["projects"][0], with_health=False)
            self.assertEqual((rep["verdict"], rep["confidence"]), ("GREEN", "low"))
            self.assertEqual(rep["run_report_source"], {"status": "unavailable", "reason": "PARTNER_UNAVAILABLE"})
            self.assertEqual(rep["run_report_diagnostics"][0]["code"], "PARTNER_UNAVAILABLE")
            self.assertEqual(rep["analytics"]["events"], 0)


class AnalyticsConsumerCase(unittest.TestCase):
    def test_sums_the_events_analyst_returned(self):
        event = {"contract_version": "1.0.0", "provider_id": "codex", "session_id": "s",
                 "project_id": "p", "event_id": "e", "occurred_at": "2026-07-22T00:00:00Z",
                 "event_kind": "run_summary", "outcome": "ok", "metrics": {"usage": 1},
                 "provenance": {"raw_ref": "local:c", "sha256": "a" * 64,
                                "reader_id": "codex-hook-context", "reader_version": "1.0.0"}}
        slice_ = analytics_slice([event], "s")
        self.assertEqual((slice_["events"], slice_["providers"]), (1, ["codex"]))
        self.assertEqual(slice_["run_report"]["metrics"], {"usage": 1})
        self.assertEqual(slice_["run_report"]["provenance"][0]["sha256"], "a" * 64)

    def test_no_events(self):
        self.assertEqual(analytics_slice([])["events"], 0)


class MaindObservabilityCase(unittest.TestCase):
    def test_heavy_scan_no_graph_is_attention(self):
        v, _c, red, reasons, _rp = compute_verdict(MAIND_RR, {"dirty": False}, None)
        self.assertEqual(v, "ATTENTION")
        self.assertFalse(red)
        self.assertTrue(any("codegraph not used" in r for r in reasons))
        self.assertTrue(any("recall" in r for r in reasons))       # empty recall is also highlighted

    def test_old_report_without_maind_key_ok(self):
        # old run-report without key maind: heuristics do not fail, the verdict is the same, without graph noise
        v, _c, _red, reasons, _rp = compute_verdict(GREEN_RR, {"dirty": False}, None)
        self.assertEqual(v, "GREEN")
        self.assertFalse(any("graph" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
