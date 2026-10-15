"""The work-source plugin of the bridge (orch:work-source): claim, brief, register with owner fencing and the evidence
gate, each answer valid by the contract of orch, and the plugin protocol through aicore.ext.plugins.

Every test works on a temporary plan created with ``plan.py`` in a temporary folder; the plans of the repository are
never touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_BRIDGE = Path(__file__).resolve().parents[1]
for _path in (_BRIDGE, _BRIDGE / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import bridge_fixture  # noqa: E402  (skips the module without a planner)
import partners  # noqa: E402

ORCH = partners.find_orch_root()
if ORCH is None:
    raise unittest.SkipTest("orch not found (set SKM_ORCH_ROOT)")
partners.use_aicore()

from aicore.ext import plugins  # noqa: E402
from aicore.state import blobs  # noqa: E402
from aicore.util import digest, schema  # noqa: E402

import worksource  # noqa: E402

PLAN_PY = bridge_fixture.PLAN_PY
ACTOR = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
ACTOR_TEXT = "claude-code/claude-opus-5-5/high"
WORKER = {"provider": "claude-code", "model": "claude-opus-5-5"}
CONTRACT = ORCH / "schemas" / "work-source" / "v1"
ITEM = {"summary": "s", "why": "w", "scope": {"include": ["x"], "exclude": []}, "deliverables": ["d"],
        "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"}]}


def run(cwd, *argv, check=True) -> subprocess.CompletedProcess:
    done = subprocess.run([sys.executable, str(PLAN_PY), *argv], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", check=False)
    if check and done.returncode:
        raise AssertionError(f"plan.py {' '.join(argv)}: {done.stderr or done.stdout}")
    return done


class Template:
    """One temporary plan with three items in three batches, built once and copied for every test."""

    root: Path | None = None

    @classmethod
    def build(cls) -> Path:
        if cls.root is None:
            cls.root = Path(tempfile.mkdtemp(prefix="ws-template-"))
            project = cls.root / "project"
            (project / "plans").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            run(project, "new", "--plans-root", "plans", "--codename", "WS", "--title", "Work source",
                "--repository", "ws", "--owner", "ws", "--actor", ACTOR_TEXT, "--message", "m", "--date", "2026.10.07")
            plan = next((project / "plans").iterdir()).name
            run(project, "add-phase", plan, "--title", "One")
            run(project, "set", plan, "P1", "--json", json.dumps({"goal": "g"}))
            for index, title in enumerate(("A", "B", "C"), 1):
                item = dict(ITEM, task_files=[{"path": f"lib/{title}.py", "change": "any"}])
                run(project, "add-item", plan, "P1", "--title", title, "--json", json.dumps(item))
            run(project, "batches", plan, "P1", "--json", json.dumps(
                [{"id": f"B{n}", "items": [f"P1.{n}"], "mode": "recommended"} for n in (1, 2, 3)]))
            run(project, "set", plan, "P1.3", "--json", json.dumps({"orchestration": {"scenario": "nope"}}))
            run(project, "design-done", plan, "P1", "--actor", ACTOR_TEXT)
        return cls.root / "project"

    @classmethod
    def cleanup(cls) -> None:
        if cls.root is not None:
            shutil.rmtree(cls.root, ignore_errors=True)
            cls.root = None


def tearDownModule():
    Template.cleanup()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "project"
        shutil.copytree(Template.build(), self.project)
        self.plan = next((self.project / "plans").iterdir()).name
        cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)
        self.registry = schema.load_contract_set(CONTRACT)[0]

    def valid(self, doc: dict, kind: str) -> None:
        issues = schema.validate(doc, kind, self.registry)
        self.assertEqual([f"{i.path}: {i.message}" for i in issues], [], doc)

    def op(self, handler, **fields) -> dict:
        request = {key: value for key, value in fields.items() if value is not None}
        self.valid(request, "input")
        answer = handler(request)
        self.valid(answer, "output")
        return answer

    def claim(self, run_id="run-a", items=None, scenario=None) -> dict:
        return self.op(worksource.op_claim, op="claim", plan=self.plan, items=items, run_id=run_id,
                       submission_id=f"sub-{run_id}", actor=ACTOR, scenario=scenario)

    def item(self, ref: str) -> dict:
        return json.loads(run(self.project, "--output", "json", "get", self.plan, ref).stdout)["data"]["doc"]

    def evidence(self, check="V1", exit_code=0, subject="P1.1") -> str:
        path = self.project / "ev" / f"{subject}-{check}.json"
        path.parent.mkdir(exist_ok=True)
        short = json.loads((self.project / "plans" / self.plan / "plan.json").read_text())["short_id"]
        path.write_text(json.dumps({
            "$schema": "urn:swissknifeman:task:plan:check-evidence:v1", "evidence_id": f"ev-{check}",
            "check_id": check, "subject": f"{short}.{subject}", "procedure": {"cmd": "true"},
            "candidate": {"head": "0123456"}, "exit": exit_code, "started_at": "2026-10-11T00:00:00Z",
            "finished_at": "2026-10-11T00:00:01Z", "producer": {"kind": "executor"}}), encoding="utf-8")
        return path.relative_to(self.project).as_posix()

    def register(self, ref="P1.1", run_id="run-a", status="done", evidence=None, report=None) -> dict:
        return self.op(worksource.op_register, op="register", plan=self.plan, ref=ref, run_id=run_id,
                       attempt_id=f"att-{run_id}-{ref}", status=status, report=report or {"summary": "did it"},
                       evidence=evidence or {}, registrar=ACTOR, executed_by=WORKER)


class ClaimTests(Case):
    def test_claim_takes_the_next_ready_item_and_owns_it(self):
        answer = self.claim()
        self.assertEqual((answer["status"], answer["ref"], answer["title"]), ("claimed", "P1.1", "A"))
        self.assertEqual((answer["scenario"], answer["session"]), ("solo", "run-a"))
        self.assertEqual(answer["attempt_id"], "att-run-a-P1.1")
        self.assertEqual(answer["route"], {"class": "implementation", "effort": "high"})
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "run-a")

    def test_repeated_claim_of_the_same_run_gives_the_same_answer(self):
        first = self.claim()
        self.assertEqual(self.claim(), first)  # the next ready item is not taken: the run resumes its own
        self.assertEqual(self.claim(items=["P1.1"]), first)

    def test_nothing_ready_is_none(self):
        self.claim(run_id="run-other")
        answer = self.claim(run_id="run-b")
        self.assertEqual(answer["status"], "none")
        self.assertNotIn("ref", answer)

    def test_item_owned_by_another_session_is_blocked_without_take_over(self):
        self.claim(run_id="run-other")
        answer = self.claim(run_id="run-b", items=["P1.1"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "ITEM_OWNED"))
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "run-other")

    def test_a_repeat_without_items_after_the_registration_is_the_same_claim(self):
        first = self.claim()
        self.register(evidence={"V1": self.evidence()})
        self.assertEqual(self.claim(), first)  # not the next ready item
        self.assertEqual(self.item("P1.2")["status"], "todo")

    def test_run_ids_are_attempt_id_characters_with_room_for_the_reference(self):
        for run_id in ("user@host", "run/1", "r" * 101):
            request = {"op": "claim", "plan": self.plan, "run_id": run_id, "submission_id": "sub-x", "actor": ACTOR}
            self.assertNotEqual(schema.validate(request, "input", self.registry), [], run_id)

    def test_an_attempt_id_the_planner_cannot_take_is_blocked_before_start(self):
        run_id = "r" * 125  # outside the contract; the plugin still refuses before anything is written
        answer = worksource.op_claim({"op": "claim", "plan": self.plan, "items": ["P1.1"], "run_id": run_id,
                                      "submission_id": "sub-x", "actor": ACTOR})
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "ATTEMPT_ID_INVALID"))
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_the_invocation_configuration_of_orch_reaches_the_scenario_check(self):
        packs = Path(self.tmp.name) / "packs"
        shutil.copytree(ORCH / "configs" / "run-policies" / "solo", packs / "custom-scenario")
        policy = packs / "custom-scenario" / "policy.json"
        policy.write_text(policy.read_text(encoding="utf-8").replace('"solo"', '"custom-scenario"'), encoding="utf-8")
        config = Path(self.tmp.name) / "orch.toml"
        config.write_text(f"schema_version = 1\n[orch.profiles]\ndirs = [{json.dumps(str(packs))}]\n", encoding="utf-8")
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps({"orchestration": {"scenario": "custom-scenario"}}))
        without = self.claim(items=["P1.1"])
        self.assertEqual((without["status"], without["reason_code"]), ("blocked", "SCENARIO_UNKNOWN"))
        answer = self.op(worksource.op_claim, op="claim", plan=self.plan, items=["P1.1"], run_id="run-a",
                         submission_id="sub-run-a", actor=ACTOR, orch_config=str(config))
        self.assertEqual((answer["status"], answer["scenario"]), ("claimed", "custom-scenario"))

    def test_unknown_scenario_is_blocked_before_the_item_starts(self):
        answer = self.claim(items=["P1.3"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "SCENARIO_UNKNOWN"))
        self.assertEqual(answer["scenario"], "nope")
        self.assertEqual(self.item("P1.3")["status"], "todo")


class BatchClaimTests(Case):
    """A batch starts its pieces together in the work source: the dependent piece is startable, and each piece ends up
    held by its own run (the owner fence of register and commit is per piece)."""

    def test_a_dependent_piece_starts_under_its_own_run_while_the_first_is_in_progress(self):
        first, second = "P1.1", "P1.2"
        self.item_depends(second, first)
        refused = self.claim(run_id="run-b", items=[second])
        self.assertEqual((refused["status"], refused.get("reason_code")), ("blocked", "DEPENDENCY_NOT_READY"))
        one = self.op(worksource.op_claim, op="claim", plan=self.plan, items=[first], batch=True, run_id="run-a",
                      submission_id="sub-a", actor=ACTOR)
        two = self.op(worksource.op_claim, op="claim", plan=self.plan, items=[second], batch=True, run_id="run-b",
                      submission_id="sub-b", actor=ACTOR)
        self.assertEqual((one["status"], two["status"]), ("claimed", "claimed"), (one, two))
        self.assertEqual((self.item(first)["status"], self.item(second)["status"]), ("in_progress", "in_progress"))
        self.assertEqual(self.item(first)["result"]["executor"]["session"], "run-a")
        self.assertEqual(self.item(second)["result"]["executor"]["session"], "run-b")

    def test_without_batch_a_dependency_in_progress_is_not_met(self):
        self.item_depends("P1.2", "P1.1")
        self.claim(run_id="run-a", items=["P1.1"])
        refused = self.claim(run_id="run-b", items=["P1.2"])
        self.assertEqual((refused["status"], refused.get("reason_code")), ("blocked", "DEPENDENCY_NOT_READY"))

    def item_depends(self, ref: str, dependency: str) -> None:
        path = self.project / "plans" / self.plan / "phases" / ref.split(".")[0] / f"{ref}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["depends_on"] = [dependency]
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


class OrchestrationTests(Case):
    """Scenario and run options of a claim: fields of the item, its phase and the plan, and overlay documents."""

    def overlay(self, doc_id: str, applies_to, body: dict | str, **extra) -> None:
        text = body if isinstance(body, str) else "```json\n" + json.dumps(body) + "\n```"
        document = {"$schema": "urn:swissknifeman:task:plan:document:v1", "id": doc_id, "title": doc_id,
                    "sections": [{"id": "orchestration", "title": "Orchestration", "text": text}], **extra}
        if applies_to:
            document["applies_to"] = applies_to
        run(self.project, "add-document", self.plan, "--json", json.dumps(document))

    def test_overlays_carry_scenario_and_options_general_first(self):
        self.overlay("orchestration-plan", None, {"options": {"rules": ["plan rule"]}}, **{"global": True})
        self.overlay("orchestration-p1", ["P1"], {"scenario": "full", "options": {"rules": ["phase rule"]}})
        self.overlay("orchestration-p1-1", ["P1.1"], {"options": {"limits": {"review_rounds": 1}}})
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["status"], answer["scenario"], answer["scenario_source"]),
                         ("claimed", "full", "document:orchestration-p1"))
        self.assertEqual(answer["options"], [
            {"source": "document:orchestration-plan", "options": {"rules": ["plan rule"]}},
            {"source": "document:orchestration-p1", "options": {"rules": ["phase rule"]}},
            {"source": "document:orchestration-p1-1", "options": {"limits": {"review_rounds": 1}}}])

    def test_the_scenario_of_the_invocation_wins_over_the_plan(self):
        self.overlay("orchestration-p1", ["P1"], {"scenario": "full"})
        answer = self.claim(items=["P1.1"], scenario="scout-solo")
        self.assertEqual((answer["status"], answer["scenario"], answer["scenario_source"]),
                         ("claimed", "scout-solo", "invocation:--scenario"))

    def test_an_unknown_scenario_of_the_invocation_is_blocked_before_the_item_starts(self):
        answer = self.claim(items=["P1.1"], scenario="nope")
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "SCENARIO_UNKNOWN"))
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_fields_win_over_overlays_of_the_same_level(self):
        self.overlay("orchestration-p1-1", ["P1.1"], {"scenario": "full", "options": {"rules": ["overlay"]}})
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps(
            {"orchestration": {"scenario": "scout-solo", "options": {"rules": ["field"]}}}))
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["scenario"], answer["scenario_source"]), ("scout-solo", "item"))
        self.assertEqual([layer["source"] for layer in answer["options"]], ["document:orchestration-p1-1", "item:P1.1"])

    def test_an_item_field_outside_the_options_contract_is_refused_by_the_planner(self):
        done = run(self.project, "set", self.plan, "P1.1", "--json",
                   json.dumps({"orchestration": {"options": {"budget": 1}}}), check=False)
        self.assertEqual(done.returncode, 1)
        self.assertIn("unexpected property 'budget'", done.stderr)

    def test_a_broken_overlay_blocks_the_claim_before_start(self):
        self.overlay("orchestration-p1", ["P1"], "not json")
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "OVERLAY_INVALID"))
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_other_documents_are_not_overlays(self):
        self.overlay("notes-p1", ["P1"], {"scenario": "full"})
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["scenario"], answer.get("options")), ("solo", None))


class OptionsContractTests(unittest.TestCase):
    """The bridge supplies the planner's ``orchestration.options`` slot with a literal copy of orch's run-options."""

    def test_the_supplied_schema_is_the_orch_contract(self):
        manifest = json.loads((_BRIDGE / "bridge.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["extends"], {"orchestration.options": "schemas/run-options.schema.json"})
        supplied = json.loads((_BRIDGE / manifest["extends"]["orchestration.options"]).read_text(encoding="utf-8"))
        orch = json.loads((ORCH / "schemas/conductor/v1/run-options.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(supplied, orch, "the mirror is stale: run bridges/planner-orch/scripts/sync-schema.py")

    def test_the_planner_declares_a_slot_and_keeps_no_copy(self):
        defs = json.loads((PLAN_PY.parents[1] / "schemas/plan/v1/defs.schema.json").read_text(encoding="utf-8"))["$defs"]
        self.assertEqual(defs["orchestration"]["properties"]["options"]["$ref"],
                         "urn:swissknifeman:task:plan:extension:orchestration.options:v1")
        self.assertEqual([name for name in defs if name.startswith("orchestration")], ["orchestration"])

    def test_without_the_bridge_the_planner_refuses_the_options_and_keeps_the_scenario(self):
        project = Path(tempfile.mkdtemp(prefix="ws-no-bridge-"))
        self.addCleanup(shutil.rmtree, project, True)
        shutil.copytree(Template.build(), project, dirs_exist_ok=True)
        plan = next((project / "plans").iterdir()).name
        with mock.patch.dict(os.environ, {"SKM_PLANNER_BRIDGES__ROOTS": "[]"}):
            done = run(project, "--output", "json", "set", plan, "P1.1", "--json",
                       json.dumps({"orchestration": {"options": {"rules": ["r"]}}}), check=False)
            self.assertEqual(json.loads(done.stdout)["error"]["code"], "EXTENSION_UNAVAILABLE")
            run(project, "set", plan, "P1.1", "--json", json.dumps({"orchestration": {"scenario": "full"}}))
            self.assertEqual(run(project, "check", plan).returncode, 0)


class BriefTests(Case):
    def brief(self, ref="P1.1") -> dict:
        return self.op(worksource.op_brief, op="brief", plan=self.plan, ref=ref, run_id="run-a")

    def test_brief_is_a_blob_declared_as_an_input_and_a_repeat_reuses_it(self):
        self.claim()
        first = self.brief()
        self.assertFalse(first["reused"])
        stored = json.loads(blobs.read_bytes(first["input_ref"], project=self.project))
        self.assertEqual(stored["digest"], first["digest"])
        self.assertTrue(stored["input_id"].endswith("@" + first["digest"][:12]))
        self.assertEqual(first["artifact_id"], "brief-P1-1-" + first["digest"][:12])
        path = blobs.blob_path(first["input_ref"], project=self.project).relative_to(self.project).as_posix()
        self.assertEqual(self.item("P1.1")["artifacts"], [{"path": path, "role": "input"}])
        again = self.brief()
        self.assertTrue(again["reused"])
        self.assertEqual({k: again[k] for k in ("input_ref", "digest", "artifact_id")},
                         {k: first[k] for k in ("input_ref", "digest", "artifact_id")})
        self.assertEqual(len(self.item("P1.1")["artifacts"]), 1)

    def test_brief_names_the_artifact_folder_of_the_item(self):
        self.claim()
        self.assertEqual(self.brief()["artifacts_dir"], f"plans/{self.plan}/artifacts/P1.1")

    def test_brief_digest_is_the_aicore_digest(self):
        self.claim()
        doc = json.loads(blobs.read_bytes(self.brief()["input_ref"], project=self.project))
        payload = {key: value for key, value in doc.items() if key != "digest"}
        payload["input_id"] = payload["input_id"].rsplit("@", 1)[0]
        self.assertEqual(doc["digest"], digest.sha256_hex(digest.canonical_json_bytes(payload)))
        fixture = json.loads((ORCH / "fixtures/exec/v1/valid/execution-input/plan-bound.json").read_text())
        import brief
        self.assertEqual(brief.canonical_digest(fixture), fixture["digest"])


class RegisterTests(Case):
    def test_evidence_that_passes_closes_the_item_and_a_repeat_is_a_no_op(self):
        self.claim()
        answer = self.register(evidence={"V1": self.evidence()})
        self.assertEqual((answer["outcome"], answer["gate"]), ("recorded", {"verdict": "pass", "checks": {"V1": 0}}))
        self.assertEqual(self.item("P1.1")["status"], "done")
        again = self.register(evidence={"V1": self.evidence()})
        self.assertEqual(again["outcome"], "no-op")

    def test_a_claim_repeated_after_the_registration_is_the_same_claim(self):
        first = self.claim(items=["P1.1"])
        self.register(evidence={"V1": self.evidence()})
        self.assertEqual(self.claim(items=["P1.1"]), first)
        self.assertEqual(self.item("P1.1")["status"], "done")

    def test_missing_evidence_is_refused_and_nothing_is_written(self):
        self.claim()
        report = {"summary": "did it", "checks_run": [{"id": "V1", "cmd": "true", "exit": 0}],
                  "open_issues": [{"text": "a remark", "kind": "note"}]}
        answer = self.register(report=report)
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "REGISTER_EVIDENCE_MISSING"))
        self.assertEqual(answer["gate"], {"verdict": "missing", "checks": {"V1": None}})
        self.assertEqual(self.item("P1.1")["status"], "in_progress")
        events = json.loads(run(self.project, "--output", "json", "events", self.plan, "--item", "P1.1",
                                "--type", "note").stdout)["data"]
        self.assertEqual(events, [])  # the note was not logged before the refusal

    def test_a_file_that_is_not_check_evidence_is_missing_and_nothing_is_logged(self):
        self.claim()
        fake = self.project / "ev" / "fake.json"
        fake.parent.mkdir(exist_ok=True)
        fake.write_text(json.dumps({"check_id": "V1", "exit": 0}), encoding="utf-8")
        answer = self.register(evidence={"V1": "ev/fake.json"}, report={
            "summary": "did it", "open_issues": [{"text": "a remark that must not be logged", "kind": "note"}]})
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "REGISTER_EVIDENCE_MISSING"))
        self.assertIn("EVIDENCE_INVALID", answer["message"])
        events = json.loads(run(self.project, "--output", "json", "events", self.plan, "--item", "P1.1",
                                "--type", "note").stdout)["data"]
        self.assertEqual(events, [])

    def test_a_take_over_after_the_guard_is_fenced_by_finish(self):
        self.claim()
        wrapper = Path(self.tmp.name) / "plan-wrap.py"
        wrapper.write_text(
            "import subprocess, sys\n"
            f"real = {str(PLAN_PY)!r}\n"
            "argv = sys.argv[1:]\n"
            "if argv and argv[0] == 'finish':\n"
            f"    subprocess.run([sys.executable, real, 'start', {self.plan!r}, 'P1.1', '--actor', {ACTOR_TEXT!r},\n"
            "                    '--session', 'other-session', '--take-over', '--no-scout'], check=True,\n"
            "                   capture_output=True)\n"
            "raise SystemExit(subprocess.run([sys.executable, real, *argv]).returncode)\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PLANNER_PLAN_PY": str(wrapper)}):
            answer = self.register(evidence={"V1": self.evidence()})
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "REGISTER_STALE_OWNER"))
        self.assertEqual(answer["gate"]["verdict"], "stale")
        self.assertEqual(self.item("P1.1")["status"], "in_progress")
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "other-session")

    def test_red_evidence_is_refused(self):
        self.claim()
        answer = self.register(evidence={"V1": self.evidence(exit_code=2)})
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "REGISTER_EVIDENCE_RED"))
        self.assertEqual(answer["gate"], {"verdict": "red", "checks": {"V1": 2}})
        self.assertEqual(self.item("P1.1")["status"], "in_progress")

    def test_take_over_by_another_session_fences_the_old_run(self):
        self.claim()
        run(self.project, "start", self.plan, "P1.1", "--actor", ACTOR_TEXT, "--session", "run-b", "--take-over",
            "--no-scout")
        answer = self.register(evidence={"V1": self.evidence()})
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "REGISTER_STALE_OWNER"))
        self.assertEqual(answer["gate"]["verdict"], "stale")
        self.assertEqual(self.item("P1.1")["status"], "in_progress")
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "run-b")

    def test_blocked_needs_no_evidence(self):
        self.claim()
        answer = self.register(status="blocked", report={"summary": "stuck", "open_issues": [
            {"text": "the owner must choose", "kind": "escalation"}]})
        self.assertEqual((answer["outcome"], answer["gate"]["verdict"]), ("recorded", "none"))
        self.assertEqual(self.item("P1.1")["status"], "blocked")


class RetryRegisterTests(Case):
    def test_a_blocked_attempt_retried_by_its_run_registers_done_without_a_conflict(self):
        self.claim()
        blocked = self.register(status="blocked", report={"summary": "stuck", "open_issues": [
            {"text": "needs the plan widened", "kind": "escalation"}]})
        self.assertEqual(blocked["outcome"], "recorded")
        self.assertEqual(self.item("P1.1")["status"], "blocked")
        done = self.register(status="done", evidence={"V1": self.evidence()})
        self.assertEqual(done["outcome"], "recorded", done)
        self.assertEqual(self.item("P1.1")["status"], "done")


class CommitTests(Case):
    def setUp(self):
        super().setUp()
        env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
            subprocess.run(["git", "config", key, value], cwd=self.project, check=True)
        (self.project / ".gitignore").write_text(".swissknifeman/state/\n", encoding="utf-8")  # as in a real project
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.project, check=True)

    def commit(self, paths=()) -> dict:
        return self.op(worksource.op_commit, op="commit", plan=self.plan, ref="P1.1", run_id="run-a",
                       attempt_id="att-run-a-P1.1", paths=list(paths))

    def test_a_registered_item_is_committed_with_its_artifacts_and_a_repeat_is_a_no_op(self):
        self.claim()
        (self.project / "lib").mkdir(exist_ok=True)
        (self.project / "lib/A.py").write_text("A = 1\n", encoding="utf-8")
        artifacts = self.project / "plans" / self.plan / "artifacts" / "P1.1"
        artifacts.mkdir(parents=True)
        (artifacts / "stage-report.json").write_text("{}\n", encoding="utf-8")
        self.register(evidence={"V1": self.evidence()})
        subprocess.run(["git", "add", "-A", "ev"], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "evidence"], cwd=self.project, check=True)
        answer = self.commit([f"plans/{self.plan}/artifacts/P1.1/"])
        self.assertEqual(answer["outcome"], "committed", answer)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project, capture_output=True, text=True).stdout
        self.assertEqual(answer["sha"], head.strip())
        shown = subprocess.run(["git", "-c", "core.quotePath=false", "show", "--name-only", "--format=", "HEAD"],
                               cwd=self.project,
                               capture_output=True, text=True).stdout.split()
        self.assertIn("lib/A.py", shown)
        self.assertIn(f"plans/{self.plan}/artifacts/P1.1/stage-report.json", shown)
        self.assertEqual(self.commit()["outcome"], "no-op")

    def test_a_foreign_dirty_path_is_refused(self):
        self.claim()
        (self.project / "elsewhere.txt").write_text("x", encoding="utf-8")
        answer = self.commit()
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "OUTSIDE_SCOPE"))


class ReleaseTests(Case):
    def release(self, run_id="run-a", **extra) -> dict:
        return self.op(worksource.op_release, op="release", plan=self.plan, ref="P1.1", run_id=run_id, **extra)

    def test_a_claimed_item_goes_back_to_todo_and_another_run_can_claim_it(self):
        self.claim()
        self.assertEqual(self.item("P1.1")["status"], "in_progress")
        self.assertEqual(self.release(reason="the tree was dirty")["outcome"], "released")
        item = self.item("P1.1")
        self.assertEqual((item["status"], item.get("result")), ("todo", None))
        self.assertEqual(self.claim(run_id="run-b", items=["P1.1"])["status"], "claimed")

    def test_a_run_that_does_not_hold_the_item_releases_nothing(self):
        self.claim(run_id="run-other")
        self.assertEqual(self.release()["outcome"], "no-op")
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "run-other")  # still theirs
        self.assertEqual(self.release(run_id="run-other")["outcome"], "released")
        self.assertEqual(self.release(run_id="run-other")["outcome"], "no-op")  # nothing left to give back


class NoteTests(Case):
    def note(self, **extra) -> dict:
        fields = {"op": "note", "collection": self.plan, "text": "phase_support run-a (done): checked the config",
                  "refs": ["P1"], "run_id": "run-a", "actor": ACTOR, **extra}
        return self.op(worksource.op_note, **fields)

    def journal(self) -> list:
        path = self.project / "plans" / self.plan / "log.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_a_note_lands_in_the_journal_of_the_phase(self):
        self.assertEqual(self.note()["outcome"], "recorded")
        found = [event for event in self.journal() if event.get("type") == "note"
                 and event.get("summary") == "phase_support run-a (done): checked the config"]
        self.assertEqual([event.get("phase") or event.get("item") for event in found], ["P1"])

    def test_a_note_without_a_target_is_refused(self):
        answer = self.note(refs=[])
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "NOTE_NO_TARGET"))

    def test_an_unknown_phase_is_refused_with_the_planner_code(self):
        answer = self.note(refs=["P99"])
        self.assertEqual(answer["outcome"], "refused")
        self.assertTrue(answer["reason_code"])


class ResearchTests(Case):
    RESULT = {"query": "q", "claims": [{"text": "t", "sources": ["https://example.org/c"]}], "contradictions": [],
              "unknowns": [], "sources_used": ["fake"]}

    def research(self, **extra) -> dict:
        fields = {"op": "research", "plan": self.plan, "ref": "P1.1", "run_id": "run-a", "number": 1,
                  "result": self.RESULT, "actor": ACTOR, **extra}
        return self.op(worksource.op_research, **fields)

    def declared(self) -> list:
        return [entry for entry in self.item("P1.1").get("artifacts", []) if entry.get("role") == "input"
                and str(entry.get("path", "")).endswith("research/P1.1-1.json")]

    def test_the_result_lands_in_the_research_folder_and_is_declared_as_an_input(self):
        self.claim()
        answer = self.research()
        self.assertEqual(answer["outcome"], "recorded")
        path = self.project / answer["path"]
        self.assertEqual(answer["path"], f"plans/{self.plan}/research/P1.1-1.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self.RESULT)
        self.assertEqual(len(self.declared()), 1)

    def test_a_repeat_changes_nothing_and_a_changed_result_is_written_again(self):
        self.claim()
        self.research()
        self.assertEqual(self.research()["outcome"], "no-op")
        self.assertEqual(len(self.declared()), 1)
        again = self.research(result={**self.RESULT, "unknowns": ["new"]})
        self.assertEqual(again["outcome"], "recorded")
        self.assertEqual(json.loads((self.project / again["path"]).read_text())["unknowns"], ["new"])

    def test_a_number_below_one_or_a_ref_that_is_no_file_name_is_refused(self):
        self.claim()
        self.assertEqual(self.research(number=0)["reason_code"], "RESEARCH_REF_INVALID")
        self.assertEqual(self.research(ref="../x")["reason_code"], "RESEARCH_REF_INVALID")

    def test_an_unknown_item_is_refused_with_the_planner_code(self):
        answer = self.research(ref="P9.9")
        self.assertEqual(answer["outcome"], "refused")
        self.assertTrue(answer["reason_code"])
        self.assertFalse((self.project / "plans" / self.plan / "research" / "P9.9-1.json").exists())


class ProtocolTests(Case):
    """describe and invoke through aicore.ext.plugins with the plugin registered in a temporary machine config."""

    def setUp(self):
        super().setUp()
        home = Path(self.tmp.name) / "home"
        config = home / "skm" / "config" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("schema_version = 1\n\n[aicore.plugins.planner-orch]\n"
                          f"manifest = {json.dumps(str(_BRIDGE / 'extension.json'))}\ntrusted = true\n",
                          encoding="utf-8")
        self.env = {**os.environ, "HOME": str(home), "SKM_HOME": str(home / "skm")}
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_describe_matches_the_manifest_and_invoke_claims(self):
        registration = plugins.find_registration("planner-orch", self.project, env=self.env)
        self.assertTrue(registration.usable, registration.problem)
        described = plugins.describe_plugin(registration, env=self.env, project=self.project)
        self.assertEqual((described.id, described.kind, described.transport), ("planner-orch", "command", "stdio-json"))
        request = {"op": "claim", "plan": self.plan, "run_id": "run-p", "submission_id": "sub-p", "actor": ACTOR}
        result = plugins.invoke_one(registration, "orch:work-source", request, env=self.env, project=self.project)
        self.assertEqual(result.status, "ok", result.error)
        self.valid(result.output, "output")
        self.assertEqual((result.output["status"], result.output["ref"]), ("claimed", "P1.1"))

    def test_an_unknown_op_is_a_protocol_error(self):
        registration = plugins.find_registration("planner-orch", self.project, env=self.env)
        result = plugins.invoke_one(registration, "orch:work-source", {"op": "peek"}, env=self.env,
                                    project=self.project)
        self.assertEqual((result.status, result.code), ("error", "INPUT_INVALID"))


if __name__ == "__main__":
    unittest.main()


class OnlyPlanDirtTests(unittest.TestCase):
    def test_only_plan_files_among_the_foreign_dirty_paths_are_left_outside(self):
        plan_only = ("OUTSIDE_SCOPE: foreign dirty paths: 'plans/2026-X/phases/P11/P11.3.json', "
                     "'plans/2026-X/phases/P11/P11.3/stage-report.json'; use --leave-outside or --path and plan.py log")
        self.assertTrue(worksource._only_plan_dirt(plan_only))
        mixed = "OUTSIDE_SCOPE: foreign dirty paths: 'plans/2026-X/phases/P11/P11.3.json', 'src/app.py'; use --leave-outside"
        self.assertFalse(worksource._only_plan_dirt(mixed))
        self.assertFalse(worksource._only_plan_dirt("NOTHING_TO_COMMIT: no changed paths"))
