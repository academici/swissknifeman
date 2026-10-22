"""Characterization of the conductor (P11.1): normalized ``progress.jsonl`` and ``state.json`` of scenarios on fake roles.

Each scenario runs the conductor on the fake roles of ``tests/fixtures/conductor/fake_role.py`` and compares the run
with a snapshot in ``tests/golden/characterization/<scenario>.json``. The snapshot holds the journal and the state of
the run without what changes from run to run: times, durations, the run id, the temporary paths. Tokens stay as the
fixtures give them. A refactoring of the conductor must leave every snapshot as it is.

Recapture a snapshot only on purpose, with the reason::

    python3 tests/test_characterization.py --recapture --reason "why the behaviour changed"

The coverage test lists every stop code and beacon of ``docs/conductor.md`` and names the scenario or the test that
meets it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

if __name__ == "__main__":  # run as a script: the package root is the parent of tests/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "aicore" / "lib"))

from orch import adhoc
from orch.conductor import engine
from orch.conductor.infrastructure import clock
from tests import test_conductor as tc
from tests.test_conductor import FINDING, FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report
from tests.test_conductor_advisor import ENABLED, advice
from tests.test_conductor_questions import ASK, asking

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "characterization"
DOCS = ROOT / "docs" / "conductor.md"
TESTS = ROOT / "tests"
RECAPTURE = "CHARACTERIZATION_RECAPTURE_REASON"  # set by --recapture --reason; a bare environment never recaptures
VOLATILE = {"ts", "run", "duration_s", "started", "finished", "created", "updated", "at", "last_ts", "active_s", "wait_s", "retry_after_s"}
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{6}")
DIGEST = re.compile(r"(?<![0-9a-f])[0-9a-f]{24,64}(?![0-9a-f])")  # git commits, content digests, orch run ids
WAITING = re.compile(r"waiting \d+ s")  # the reset of a fake quota is "now + 3 s": the wait is rounded by the clock
SHORT_DIGEST = re.compile(r"(?<=@)[0-9a-f]{12}\b")  # the digest suffix of an input id
SHORT_FINGERPRINT = re.compile(r"(?<=fingerprint=)[0-9a-f]{12}\b")  # reuse_miss names the environment hash


def normalize(value, paths: dict):
    """A copy of a journal or state document without times, durations, run ids and temporary paths.

    ``paths`` maps a text that varies (the run id, the temporary folders) to a stable name; longer texts go first."""
    if isinstance(value, dict):
        return {key: normalize(item, paths) for key, item in sorted(value.items()) if key not in VOLATILE}
    if isinstance(value, list):
        return [normalize(item, paths) for item in value]
    if isinstance(value, str):
        for text in sorted(paths, key=len, reverse=True):
            value = value.replace(text, paths[text])
        value = TIME.sub("<time>", value)
        value = WAITING.sub("waiting <n> s", RUN_ID.sub("<run>", value))
        return SHORT_FINGERPRINT.sub("<digest>", SHORT_DIGEST.sub("<digest>", DIGEST.sub("<digest>", value)))
    return value


class CharacterizationCase(ConductorCase):
    """Runs a scenario and keeps the normalized journal and state under its name."""

    def setUp(self):
        super().setUp()
        self.slept = []
        for name, value in (("sleep", self.slept.append), ("unit_random", lambda: 0.5)):
            patcher = mock.patch.object(clock, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.captured = {}

    def options(self, **layer) -> None:
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": layer}]}})

    def snapshot(self, name: str, err: str) -> None:
        """Compare (or recapture) the run whose first call wrote ``err``; a resume appends to the same run."""
        run = self.run_dir(err)
        paths = {run.name: "<run>", str(self.project.parent): "<tmp>", str(self.project): "<project>",
                 str(self.home): "<home>"}
        resolved = {str(Path(key).resolve()): value for key, value in paths.items() if key.startswith("/")}
        paths.update(resolved)
        journal = [normalize(line, paths) for line in json.loads("[" + ",".join(
            (run / "progress.jsonl").read_text(encoding="utf-8").splitlines()) + "]")]
        state_doc = json.loads((run / engine.STATE_FILE).read_text(encoding="utf-8"))
        state_doc.pop("ended", None)  # volatile UTC bound of the run segment, tested in test_observer
        state_doc.pop("$schema", None)  # the records/v1 tag (P4.3), tested in test_records_contract
        for item in state_doc.get("items", {}).values():
            item.pop("usage_by_agent", None)  # replay bookkeeping; totals are covered here, receipts in test_usage_normalization
        state = normalize(state_doc, paths)
        compare(self, name, {"progress": journal, "state": state})


def compare(case: unittest.TestCase, name: str, document: dict) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    reason = os.environ.get(RECAPTURE, "").strip()
    if reason:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    case.assertTrue(path.exists(), f"no snapshot {path.name}: capture it with --recapture --reason")
    case.assertEqual(text, path.read_text(encoding="utf-8"),
                     f"{name} differs from its snapshot; a change on purpose is recaptured with --reason")


def repro(cmd="cat out/W1.txt", observed="ok") -> dict:
    return {"cmd": cmd, "exit": 0, "observed": observed}


class ScenarioTests(CharacterizationCase):
    def test_green(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("green", err)

    def test_red_check_correction(self):
        self.script({"executor": [{"result": report("W1")}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("red-check-correction", err)

    def test_finding_triage_correction(self):
        triage = {"result": {"confirmed": [{"finding": "F1", "reproduction": repro(), "fix": "write done"}],
                             "rejected": []}}
        fixed = {"write": {"out/W1.txt": "done\n"}, "result": report("W1")}
        self.script({"executor": [executor_ok("W1"), fixed], "reviewer": [FINDING, GREEN], "triager": [triage]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("finding-triage-correction", err)

    def test_quota_wait(self):
        self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("quota-wait", err)

    def test_route_fallback(self):
        self.options(fallback_routes=[{"role": "executor", "provider": "codex", "model_class": "implementation"}])
        self.script({"executor": [tc.quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("route-fallback", err)

    def test_resume_after_stop(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        missing = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        missing["reviewer"] = [str(self.project / "no-such-grok")]
        self.write_config(missing)
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "PROVIDER_UNAVAILABLE")), err)
        self.write_config()
        code, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.snapshot("resume-after-stop", err)

    def test_input_rebuilt(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.snapshot("input-rebuilt", err)

    def test_question_answer_resume(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        run = self.run_dir(err).name
        code, out, _ = self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename",
                                    "--by", "owner")
        self.assertEqual(code, 0, out)
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err2 = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err2)), (0, ("finished", None)), err2)
        self.snapshot("question-answer-resume", err)

    def test_adhoc_input(self):
        doc = adhoc.build_adhoc_input("Make out/adhoc.txt", ["out/adhoc.txt"], checks=["V1=test -f out/adhoc.txt"])
        path = self.project.parent / "input.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        done = {**report("adhoc"), "checks_run": [{"id": "V1", "cmd": "test -f out/adhoc.txt", "exit": 0}]}
        self.script({"executor": [{"write": {"out/adhoc.txt": "ok\n"}, "result": done}], "reviewer": [GREEN]})
        code, _, err = self.conduct("run", "--input", path, "--json-lines", "--scenario", "full")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("adhoc-input", err)

    def test_dynamic_review(self):
        self.write_config(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "out/schemas/*.json"]}}, )
        doc = self.source()
        doc["items"]["W1"]["scenario"] = "scout-solo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        schema = {"write": {"out/W1.txt": "ok\n", "out/schemas/W1.json": "{}\n"},
                  "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"])}
        self.script({"executor": [schema], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("dynamic-review", err)

    def test_advisor(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in (*ROLES, "advisor")},
                          extra=ENABLED)
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "advisor": [advice("question:Q1@1")],
                     "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.snapshot("advisor", err)


class EventSequenceTests(CharacterizationCase):
    """The ``orch.*`` events that stand next to a beacon (knowledge/p12-observability#types), in the order of a scenario.
    The run and agent events are left out: they are the subject of the contract tests of ``test_events``."""

    SKIPPED = ("orch.run.started", "orch.run.stage.finished", "orch.run.finished", "orch.run.refused")

    def sequence(self) -> list:
        from aicore.ext import events as journal
        stored, problems = journal.read_events(self.project)
        self.assertEqual(problems, [])
        return [event.type for event in stored
                if event.type not in self.SKIPPED and not event.type.startswith("orch.agent.") or
                event.type == "orch.agent.questioned"]

    def test_green_has_no_beacon_event(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), [])

    def test_quota_wait(self):
        self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.provider.quota-exhausted"])

    def test_route_fallback(self):
        self.options(fallback_routes=[{"role": "executor", "provider": "codex", "model_class": "implementation"}])
        self.script({"executor": [tc.quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.provider.fallback"])

    def test_input_rebuilt(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.input.rebuilt"])

    def test_question_blocks_the_piece(self):
        self.script({"executor": [asking(dict(ASK))], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        self.assertEqual(self.sequence(), ["orch.agent.questioned", "orch.run.waiting", "orch.work.blocked"])

    def test_dynamic_review(self):
        self.write_config(extra="[orch.conductor.risk.weights]\nschema = 70")
        self.set_items({"W1": {"write_set": ["out/W1.txt", "out/schemas/*.json"]}}, )
        doc = self.source()
        doc["items"]["W1"]["scenario"] = "scout-solo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        schema = {"write": {"out/W1.txt": "ok\n", "out/schemas/W1.json": "{}\n"},
                  "result": report("W1", changed_paths=["out/W1.txt", "out/schemas/W1.json"])}
        self.script({"executor": [schema], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.sequence(), ["orch.review.added"])


class CodeScenarioTests(CharacterizationCase):
    """Stops and beacons that no other test of the conductor reaches by name; each runs on the fake roles."""

    def stops(self, err: str, code: str) -> None:
        self.assertEqual(self.outcome(err), ("stopped", code), err)

    def beacons(self, err: str) -> set:
        return {line.get("reason_code") for line in self.lines(err) if line["event"] == "info"}

    def test_an_empty_answer_stops_as_role_output_empty(self):
        self.options(limits={"retries": 0, "repairs": 0})
        self.script({"executor": [{"text": ""}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "ROLE_OUTPUT_EMPTY")

    def test_a_refused_operation_stops_as_provider_authz(self):
        failed = {"stream": [tc.api_retry("permission_denied", 403)], "is_error": True, "text": "403",
                  "api_error_status": 403, "exit": 1}
        self.script({"executor": [failed, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "PROVIDER_AUTHZ")

    def test_a_silent_role_prints_stage_slow(self):
        from orch.conductor import process
        old = process.POLL_S
        process.POLL_S = 0.2
        self.addCleanup(setattr, process, "POLL_S", old)
        self.options(limits={"stage_warn_s": 1})
        self.script({"executor": [dict(executor_ok("W1"), sleep=2.5)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("STAGE_SLOW", self.beacons(err))

    def test_a_report_the_fixer_cannot_mend_prints_repair_failed(self):
        self.write_config({role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES + ("report-fixer",)})
        broken = {"write": {"out/W1.txt": "ok\n"},
                  "result": report("W1", checks_run=[{"id": "V1", "cmd": "test -f out/W1.txt", "exit": "zero"}])}
        self.script({"executor": [broken, executor_ok("W1")], "reviewer": [GREEN],
                     "report-fixer": [{"result": broken["result"], "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("REPAIR_FAILED", self.beacons(err))

    def test_a_gate_that_cannot_be_written_prints_gate_not_written(self):
        failure = tc.gates.GateError("GATE_WRITE", "read-only")
        with mock.patch.object(tc.gates, "set_gate", side_effect=failure):
            self.script({"executor": [tc.quota_failure(3), executor_ok("W1")], "reviewer": [GREEN]})
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("GATE_NOT_WRITTEN", self.beacons(err))

    def test_a_role_that_outlives_its_answer_prints_role_lingered(self):
        real = engine.process.run_role

        def lingering(*args, **kwargs):
            run = real(*args, **kwargs)
            run.lingered = True
            return run

        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(engine.process, "run_role", lingering):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertIn("ROLE_LINGERED", self.beacons(err))

    def refuse(self, verb: str, answer, err_text: str = "refused"):
        real = engine.Conductor._orch

        def orch(conductor, *args):
            if args[:2] == ("source", verb):
                return answer[0], answer[1], err_text
            return real(conductor, *args)

        return mock.patch.object(engine.Conductor, "_orch", orch)

    def test_a_blocked_claim_stops_as_claim_blocked(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with self.refuse("claim", (0, {"status": "blocked", "ref": "W1", "reason_code": "ITEM_OWNED", "message": "held"})):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.assertIn("CLAIM_BLOCKED", err)

    def test_a_refused_brief_stops_as_brief_refused(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with self.refuse("brief", (1, None)):
            code, _, err = self.run_items("W1")
        self.stops(err, "BRIEF_REFUSED")

    def test_a_refused_prepare_stops_as_prepare_refused(self):
        """Prepare is bound in-process, so a refusal is the conductor call, not the public ``source prepare`` verb."""
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})

        def refuse_prepare(*_args, **_kwargs):
            print("refused", file=sys.stderr)
            return 1

        with mock.patch("orch.cli._source_prepare", refuse_prepare):
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        self.stops(err, "PREPARE_REFUSED")


C = "test_characterization.py"
T = "test_conductor.py"
# every stop code and beacon of docs/conductor.md -> where it is met: ``snapshot:<scenario>`` (the code is a value in that
# snapshot) or ``test:<file>`` (the file of tests/ that names it). WORK_SOURCE_* stands for the whole family.
COVERAGE = {
    # Stops
    "RUN_BUSY": "test:test_run_lease.py", "WORKTREE_BUSY": "test:test_run_lease.py",
    "QUESTIONS_LOCKED": "test:test_run_lease.py",
    "QUESTION_ANSWERED_NOT_RETRIED": "test:test_conductor_questions.py",
    "CONDUCTOR_CRASHED": "test:test_observer.py",
    "STAGE_RECOVERY_UNKNOWN": "test:test_resume_reconcile.py",
    "REVIEW_LIMIT": f"test:{T}", "RUN_TIMEOUT": f"test:{T}", "ITEM_BLOCKED": "snapshot:question-answer-resume",
    "ROUTE_UNDERSHOOT": f"test:{T}", "SANDBOX_UNAVAILABLE": f"test:{T}",
    "PROVIDER_UNAVAILABLE": "snapshot:resume-after-stop", "TRANSPORT_UNSUPPORTED": f"test:{T}",
    "LAUNCH_UNKNOWN": "test:test_launch.py", "ROLE_FAILED": f"test:{T}", "ROLE_OUTPUT_EMPTY": f"test:{C}",
    "LAUNCH_REFUSED": f"test:{T}",
    "ROLE_OUTPUT_INVALID": f"test:{T}", "PROVIDER_AUTH": f"test:{T}", "PROVIDER_AUTHZ": f"test:{C}",
    "PROVIDER_QUOTA": "snapshot:quota-wait", "PROVIDER_REFUSED": f"test:{T}", "PROVIDER_CONTEXT": f"test:{T}",
    "MODEL_UNAVAILABLE": f"test:{T}", "TIMEOUT": f"test:{T}", "WORKTREE_DIRTY": f"test:{T}",
    "CLAIM_BLOCKED": f"test:{C}", "BRIEF_REFUSED": f"test:{C}", "PREPARE_REFUSED": f"test:{C}",
    "REGISTER_REFUSED": f"test:{T}", "COMMIT_REFUSED": f"test:{T}", "WORK_SOURCE_*": "test:test_worksource.py",
    "OPTIONS_INVALID": f"test:{T}", "POLICY_UNKNOWN": "test:test_policies.py",
    "POLICY_STAGE_UNSUPPORTED": "test:test_policy_stages.py",
    "OPTIONS_UNTRUSTED": f"test:{T}", "OPTIONS_UNSAFE_PATH": f"test:{T}", "STATE_CORRUPT": "test:test_durable_state.py",
    "STUBS_INVALID": "test:test_conductor_stubs.py",
    "GROUP_REVIEW_BLOCKER": "test:test_conductor_review_plan.py", "GROUP_REVIEW_FAILED": "test:test_conductor_review_plan.py",
    "GROUP_UNKNOWN": "test:test_conductor_review_plan.py", "GROUP_FOLLOWUP_MISMATCH": "test:test_conductor_review_plan.py",
    "GROUP_FOLLOWUP_NOT_DONE": "test:test_conductor_review_plan.py",
    "TOKEN_BUDGET": "test:test_budget_hard.py", "TOKEN_BUDGET_UNMETERED": "test:test_budget_hard.py",
    "BRIEF_TOO_LARGE": "test:test_budget_hard.py",
    "MODEL_CATALOG_UNAVAILABLE": "test:test_prepare.py",
    "OUTSIDE_MODULE": "test:test_write_fence.py", "OUTSIDE_RUNTIME_ARTIFACT": "test:test_write_fence.py",
    "CHECKS_MUTATED": "test:test_write_fence.py",
    "RUN_INVALID": "test:test_records_migration.py", "STATE_INVALID": "test:test_records_migration.py",
    "QUESTIONS_INVALID": "test:test_records_contract.py", "RECORD_INVALID": "test:test_records_contract.py",
    "BRIEF_INVALID": "test:test_worksource.py", "REGISTER_REPORT_INVALID": "test:test_worksource.py",
    # Beacons
    "RUN_ORPHANED": "test:test_run_lease.py",
    "STAGE_SLOW": f"test:{C}", "STAGE_IDLE": f"test:{T}", "CHECK_SLOW": f"test:{T}", "RUN_SLOW": f"test:{T}",
    "BUDGET_OVER": f"test:{T}", "LIMIT_OVER": f"test:{T}", "RESULT_HEALED": "snapshot:green",
    "RESULT_REPAIRED": f"test:{T}", "REPAIR_FAILED": f"test:{C}", "REPAIR_SEMANTIC_DRIFT": "test:test_repair_semantics.py",
    "INPUT_REBUILT": "snapshot:input-rebuilt",
    "PROVIDER_WAIT": "snapshot:quota-wait", "ROUTE_FALLBACK": "snapshot:route-fallback",
    "ROUTE_UPGRADED": "test:test_conductor_focus.py", "CAPACITY_GATED": f"test:{T}",
    "RESULT_SILENT_DENIAL": "test:test_conductor_agents.py", "GATE_NOT_WRITTEN": f"test:{C}", "DISK_LOW": "test:test_polish.py",
    "SESSION_ROUTE_CHANGED": "test:test_polish.py", "DEPENDENCY_BLOCKED": "test:test_conductor_session.py",
    "ROLE_LINGERED": f"test:{C}", "ISOLATION_PARTIAL": f"test:{T}", "CHECK_CHANGED_TREE": "test:test_conductor_checks.py",
    "STUBS_CHANGED": "test:test_conductor_stubs.py",
    "SKILL_PATH_INVALID": "test:test_instruction_paths.py", "RULES_PATH_INVALID": "test:test_instruction_paths.py",
    "TRIAGE_REPRO_TRIVIAL": "test:test_triage_repro.py", "TRIAGE_REPRO_MISMATCH": "test:test_triage_repro.py",
    "TRIAGE_REPRO_UNVERIFIED": "test:test_triage_repro.py", "REVIEW_MODE_NONE_SKIPPED": "test:test_conductor_review_plan.py",
    "GROUP_REVIEW_RESOLVED": "test:test_conductor_review_plan.py",
    "RUNTIME_ARTIFACT_RELOCATED": "test:test_write_fence.py",
    "QUESTION_OWNER_ONLY": "test:test_conductor_questions.py",
    "ADVICE_HELD": "test:test_conductor_advisor.py",
    "POLICY_STAGE_SKIPPED": "test:test_policy_stages.py",
    "CONCURRENT_RUN": f"test:{T}", "RESULT_INCOMPLETE": f"test:{T}", "REVIEW_DEBT": f"test:{T}",
    "ANSWER_SCHEMA_IGNORED": "test:test_records_contract.py",
}


def documented_codes() -> list:
    """The codes in the first column of the tables of ``### Stops`` and ``### Beacons`` of docs/conductor.md."""
    text = DOCS.read_text(encoding="utf-8")
    codes = []
    for start, end in (("### Stops", "### Beacons"), ("### Beacons", "### Provider availability")):
        body = text[text.index(start):text.index(end, text.index(start))]
        for line in body.splitlines():
            if line.startswith("|") and not line.startswith(("| ---", "| Code")):
                codes += re.findall(r"`([A-Z][A-Z_*]+)`", line.split("|")[1])
    return list(dict.fromkeys(codes))


class CoverageTests(unittest.TestCase):
    def test_every_documented_code_is_listed_and_every_listed_code_is_documented(self):
        documented = documented_codes()
        self.assertGreater(len(documented), 40, documented)
        self.assertEqual(sorted(documented), sorted(COVERAGE), "docs/conductor.md and COVERAGE differ: list the new code")

    def test_every_code_is_met_where_the_list_says(self):
        for code, where in COVERAGE.items():
            kind, _, name = where.partition(":")
            with self.subTest(code=code):
                if kind == "snapshot":
                    self.assertIn(f'"{code}"', (GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
                else:
                    self.assertEqual(kind, "test")
                    self.assertIn(code.rstrip("*"), (TESTS / name).read_text(encoding="utf-8"))

    def test_every_snapshot_belongs_to_a_scenario_and_back(self):
        wanted = {name[len("test_"):].replace("_", "-") for name in dir(ScenarioTests) if name.startswith("test_")}
        self.assertEqual({path.stem for path in GOLDEN.glob("*.json")}, wanted)


def main() -> int:
    argv = sys.argv[1:]
    if "--recapture" in argv:
        argv.remove("--recapture")
        reason = ""
        if "--reason" in argv:
            at = argv.index("--reason")
            reason = argv[at + 1] if at + 1 < len(argv) else ""
            del argv[at:at + 2]
        if not reason.strip():
            print("recapture needs --reason TEXT", file=sys.stderr)
            return 2
        os.environ[RECAPTURE] = reason
        print(f"recapturing the snapshots: {reason}")
    unittest.main(argv=[sys.argv[0], *argv], module=__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
