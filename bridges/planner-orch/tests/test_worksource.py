"""The work-source plugin of the bridge (orch:work-source): claim, brief, register with owner fencing and the evidence
gate, each answer valid by the contract of orch, and the plugin protocol through aicore.ext.plugins.

Every test works on a temporary plan created with ``plan.py`` in a temporary folder; the plans of the repository are
never touched.
"""
from __future__ import annotations

import hashlib
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


class ReviewReceiptForwardingTests(unittest.TestCase):
    def test_register_forwards_receipt_to_register_cli(self):
        fields = {"plan": "PLAN1", "ref": "P1.1", "run_id": "run", "attempt_id": "att-run",
                  "status": "done", "report": {}, "registrar": ACTOR, "executed_by": ACTOR,
                  "review_receipt": "artifacts/review-receipt.json"}
        done = subprocess.CompletedProcess([], 0, json.dumps({"calls": [{"result": "recorded"}]}), "")
        with mock.patch.object(worksource, "_supersede_blocked_attempt"), \
                mock.patch.object(worksource, "_kept_evidence", return_value={}), \
                mock.patch.object(partners, "run_bounded", return_value=done) as run_register:
            self.assertEqual(worksource.op_register(fields)["outcome"], "recorded")
        argv = run_register.call_args.args[0]
        self.assertEqual(argv[argv.index("--review-receipt") + 1], fields["review_receipt"])


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
            for title in ("A", "B", "C"):
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

    def trace_planner_cli(self):
        wrapper, log = Path(self.tmp.name) / "plan-trace.py", Path(self.tmp.name) / "plan-argv.jsonl"
        wrapper.write_text(
            "import json, pathlib, subprocess, sys\n"
            f"with pathlib.Path({str(log)!r}).open('a', encoding='utf-8') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"raise SystemExit(subprocess.run([sys.executable, {str(PLAN_PY)!r}, *sys.argv[1:]]).returncode)\n",
            encoding="utf-8")
        return wrapper, log

    def evidence(self, check="V1", exit_code=0, subject="P1.1") -> str:
        path = self.project / "ev" / f"{subject}-{check}.json"
        path.parent.mkdir(exist_ok=True)
        plan_root = getattr(self, "plan_root", self.project / "plans" / self.plan)
        short = json.loads((plan_root / "plan.json").read_text())["short_id"]
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
    def test_claim_readiness_refusal_preserves_code_in_claim_blocked_message(self):
        run(self.project, "set", self.plan, "plan", "--json", '{"settings":{"design_audit":"required"}}')
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "CLAIM_BLOCKED"), answer)
        self.assertIn("READINESS_REQUIRED", answer["message"])
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_claim_start_passes_strict_route_through_cli(self):
        wrapper, log = self.trace_planner_cli()
        with mock.patch.dict(os.environ, {"PLANNER_PLAN_PY": str(wrapper)}):
            answer = self.claim(items=["P1.1"])
        self.assertEqual(answer["status"], "claimed", answer)
        starts = [argv for argv in map(json.loads, log.read_text().splitlines()) if argv[0] == "start"]
        self.assertEqual(len(starts), 1)
        self.assertIn("--strict-route", starts[0])

    def test_claim_refuses_unknown_pool_model_even_when_interactive_policy_warns(self):
        with mock.patch.dict(os.environ, {"SKM_PLANNER_ROUTING__UNKNOWN_MODEL": "warn"}):
            answer = self.op(worksource.op_claim, op="claim", plan=self.plan, items=["P1.1"], run_id="unknown",
                             submission_id="sub-unknown", actor={**ACTOR, "model": "mystery-model"})
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "ROUTE_MODEL_UNKNOWN"), answer)
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_interactive_config_refuses_unknown_model_through_cli(self):
        with mock.patch.dict(os.environ, {"SKM_PLANNER_ROUTING__UNKNOWN_MODEL": "refuse"}):
            answer = run(self.project, "start", self.plan, "P1.1", "--actor", "claude-code/mystery-model/high",
                         "--no-scout", check=False)
        self.assertEqual(answer.returncode, 1, answer.stdout)
        self.assertIn("ROUTE_MODEL_UNKNOWN", answer.stderr)
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_claim_refuses_structurally_corrupted_phase(self):
        # Model an old/external edit: the current set verb refuses this damage before it reaches start.
        path = self.project / "plans" / self.plan / "phases/P1/P1.2.json"
        doc = json.loads(path.read_text())
        doc["validation"] = []
        path.write_text(json.dumps(doc), encoding="utf-8")
        answer = self.claim(items=["P1.1"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "PLAN_INVALID"), answer)
        self.assertIn("P1.2.json/validation", answer["message"])
        self.assertEqual(self.item("P1.1")["status"], "todo")

    def test_claim_takes_the_next_ready_item_and_owns_it(self):
        answer = self.claim()
        self.assertEqual((answer["status"], answer["ref"], answer["title"]), ("claimed", "P1.1", "A"))
        self.assertEqual((answer["scenario"], answer["session"]), ("solo", "run-a"))
        self.assertEqual(answer["attempt_id"], "att-run-a-P1.1")
        self.assertEqual(answer["route"], {"class": "implementation", "effort": "high"})
        self.assertEqual(self.item("P1.1")["result"]["executor"]["session"], "run-a")

    def test_claim_answer_carries_the_route_correction_and_nothing_else_of_the_route(self):
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps({"route": {
            "correction": {"class": "economy", "effort": "medium", "provider": "claude-code"},
            "settings": {"native": True}}}))
        answer = self.claim(items=["P1.1"])  # the answer is valid by the work-source output contract
        self.assertEqual(answer["route"], {"class": "implementation", "effort": "high", "correction": {
            "class": "economy", "effort": "medium", "provider": "claude-code"}})

    def test_claim_without_route_correction_adds_none(self):
        self.assertNotIn("correction", self.claim(items=["P1.1"])["route"])

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
        self.assertEqual((one.get("depends_on"), two.get("depends_on")), (None, [first]))  # the conductor holds a piece whose dependency blocks
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

    def test_a_piece_routed_to_another_executor_starts_under_the_executor_of_its_options(self):
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps(
            {"route": {"class": "implementation", "effort": "xhigh", "provider": "codex", "model": "gpt-6.1-sol"}}))
        self.overlay("orchestration-p1-1", ["P1.1"], {"options": {"stages": [
            {"role": "executor", "provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"}]}})
        answer = self.claim(items=["P1.1"])  # the claimed default (ACTOR) is claude-code: the options name codex
        self.assertEqual(answer["status"], "claimed")
        self.assertEqual(self.item("P1.1")["result"]["executor"],
                         {"provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh", "session": "run-a"})

    def test_a_piece_routed_to_another_executor_starts_under_the_claimed_actor_without_orchestration(self):
        """The conductor claims the executor of ``--options`` (provider, model, effort): the plan needs no copy of it."""
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps(
            {"route": {"class": "implementation", "effort": "xhigh", "provider": "codex", "model": "gpt-6.1-sol"}}))
        refused = self.claim(run_id="run-d", items=["P1.1"])  # the default actor (claude-code) is not the route
        self.assertEqual((refused["status"], refused["reason_code"]), ("blocked", "ROUTE_UNDERSHOOT"), refused)
        codex = {"provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"}
        answer = self.op(worksource.op_claim, op="claim", plan=self.plan, items=["P1.1"], run_id="run-a",
                         submission_id="sub-run-a", actor=codex)
        self.assertEqual(answer["status"], "claimed", answer)
        self.assertNotIn("options", answer)
        self.assertEqual(self.item("P1.1")["result"]["executor"], {**codex, "session": "run-a"})

    def plan_codex(self, ref="P1.1"):
        """A piece whose plan pins the executor codex/gpt-6.1-sol/xhigh in ``orchestration`` (class implementation)."""
        run(self.project, "set", self.plan, ref, "--json", json.dumps({"route": {"class": "implementation", "effort": "high"}}))
        self.overlay("orchestration-p1-1", [ref], {"options": {"stages": [
            {"role": "executor", "provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"}]}})

    def claim_as(self, actor, source=None, fields=None, run_id="run-a"):
        return self.op(worksource.op_claim, op="claim", plan=self.plan, items=["P1.1"], run_id=run_id,
                       submission_id=f"sub-{run_id}", actor=actor, actor_source=source, actor_fields=fields)

    def test_without_options_of_the_run_the_plan_executor_is_claimed(self):
        self.plan_codex()
        answer = self.claim_as(ACTOR, "default")
        self.assertEqual(answer["status"], "claimed", answer)
        self.assertNotIn("actor_override", answer)
        self.assertEqual(self.item("P1.1")["result"]["executor"]["provider"], "codex")

    def test_options_with_only_a_reviewer_leave_the_plan_executor(self):
        self.plan_codex()  # the conductor sends actor_source default: its --options name no executor
        answer = self.claim_as(ACTOR)
        self.assertEqual((answer["status"], self.item("P1.1")["result"]["executor"]["provider"]), ("claimed", "codex"))

    def test_a_partial_executor_of_the_run_changes_only_what_it_names(self):
        self.plan_codex()
        answer = self.claim_as({**ACTOR, "effort": "high"}, "options", ["effort"])
        self.assertEqual(answer["status"], "claimed", answer)
        self.assertEqual(self.item("P1.1")["result"]["executor"],
                         {"provider": "codex", "model": "gpt-6.1-sol", "effort": "high", "session": "run-a"})
        self.assertEqual(answer["actor_override"]["plan"]["effort"], "xhigh")

    def test_a_full_executor_of_the_run_wins_over_the_plan_with_a_warning(self):
        self.plan_codex()
        run_actor = {"provider": "claude-code", "model": "opus", "effort": "high"}
        answer = self.claim_as(run_actor, "options", ["provider", "model", "effort"])
        self.assertEqual(answer["status"], "claimed", answer)
        self.assertEqual(self.item("P1.1")["result"]["executor"], {**run_actor, "session": "run-a"})
        override = answer["actor_override"]
        self.assertEqual((override["reason_code"], override["ref"], override["plan"]["provider"], override["run"]["provider"]),
                         ("ACTOR_OVERRIDE", "P1.1", "codex", "claude-code"))

    def test_a_provider_alone_keeps_the_model_of_the_plan(self):
        self.plan_codex()
        answer = self.claim_as({"provider": "codex", "model": "gpt-6-sol"}, "options", ["provider"])
        self.assertEqual(answer["status"], "claimed", answer)
        self.assertEqual(self.item("P1.1")["result"]["executor"]["model"], "gpt-6.1-sol")
        self.assertNotIn("actor_override", answer)

    def test_a_class_alone_takes_its_model_on_the_provider_of_the_plan(self):
        self.plan_codex()
        answer = self.op(worksource.op_claim, op="claim", plan=self.plan, items=["P1.1"], run_id="run-a",
                         submission_id="sub-run-a", actor=ACTOR, actor_source="options", actor_class="frontier")
        self.assertEqual(answer["status"], "claimed", answer)
        executor = self.item("P1.1")["result"]["executor"]
        self.assertEqual((executor["provider"], executor["model"]), ("codex", worksource.class_model("codex", "frontier")))
        self.assertEqual(answer["actor_override"]["plan"]["model"], "gpt-6.1-sol")

    def test_a_run_executor_below_the_class_of_the_piece_is_refused(self):
        self.plan_codex()
        answer = self.claim_as({"provider": "claude-code", "model": "haiku", "effort": "high"}, "options",
                               ["provider", "model", "effort"])
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "ROUTE_UNDERSHOOT"), answer)

    def test_an_unknown_plan_is_refused_with_the_planner_message_not_its_json(self):
        answer = self.op(worksource.op_claim, op="claim", plan="no-such-plan", items=["P1.1"], run_id="run-z",
                         submission_id="sub-z", actor=ACTOR)
        self.assertEqual((answer["status"], answer["reason_code"]), ("blocked", "PLAN_NOT_FOUND"))
        self.assertNotIn("{", answer["message"])

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
        blob = blobs.blob_path(first["input_ref"], project=self.project)
        path = "@plan/inputs/" + blob.name
        self.assertEqual(self.item("P1.1")["artifacts"], [{"path": path, "role": "input"}])
        self.assertEqual((self.project / "plans" / self.plan / "inputs" / blob.name).read_bytes(), blob.read_bytes())
        again = self.brief()
        self.assertTrue(again["reused"])
        self.assertEqual({k: again[k] for k in ("input_ref", "digest", "artifact_id")},
                         {k: first[k] for k in ("input_ref", "digest", "artifact_id")})
        self.assertEqual(len(self.item("P1.1")["artifacts"]), 1)

    def test_brief_reuse_reads_the_plan_copy_when_the_local_blob_is_gone(self):
        self.claim()
        first = self.brief()
        blobs.blob_path(first["input_ref"], project=self.project).unlink()
        again = self.brief()
        self.assertEqual(again["input_ref"], first["input_ref"])
        self.assertEqual(again["digest"], first["digest"])
        self.assertTrue(self.brief()["reused"])
        self.assertEqual(len(self.item("P1.1")["artifacts"]), 1)

    def test_legacy_repository_blob_declarations_remain_reusable(self):
        self.claim()
        first = self.brief()
        old_path = blobs.blob_path(first["input_ref"], project=self.project).relative_to(self.project).as_posix()
        run(self.project, "set", self.plan, "P1.1", "--json",
            json.dumps({"artifacts": [{"role": "input", "path": old_path}]}))
        again = self.brief()
        self.assertEqual((again["input_ref"], again["reused"]), (first["input_ref"], True))
        self.assertEqual(len(self.item("P1.1")["artifacts"]), 2)

    def test_corrupt_plan_copy_is_not_reused(self):
        self.claim()
        first = self.brief()
        root = self.project / "plans" / self.plan
        path = root / self.item("P1.1")["artifacts"][0]["path"].removeprefix("@plan/")
        doc = json.loads(path.read_bytes())
        doc["goal"] = "corrupted"
        path.write_text(json.dumps(doc))
        store = partners.planner_engine("plan.store")
        self.assertIsNone(worksource._previous_brief(store.load_plan(root), "P1.1", None, self.project, blobs))
        self.assertTrue(blobs.blob_path(first["input_ref"], project=self.project).is_file())

    def test_runtime_copy_refuses_an_inputs_folder_that_is_a_symlink(self):
        root = self.project / "plans" / self.plan
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (root / "inputs").symlink_to(outside, target_is_directory=True)
        source = self.project / "source.json"
        source.write_text("{}")
        store = partners.planner_engine("plan.store")
        with self.assertRaises(worksource.Blocked) as stop:
            worksource._declared_path(store.load_plan(root), source, self.project, runtime_input=True)
        self.assertEqual(stop.exception.code, "ARTIFACT_REFUSED")
        self.assertEqual(list(outside.iterdir()), [])

    def test_the_worker_view_ignores_the_conductor_notes_and_read_snapshots_but_not_the_task(self):
        doc = {"digest": "d1", "input_id": "PLAN.P1.1@d1", "goal": "g",
               "reads": [{"path": "a.py", "sha256": "s1", "content": "old", "required": True}],
               "context_refs": [{"kind": "pack", "content": {
                   "item": {"id": "P1.1", "artifacts": [], "updated_at": "t1", "rules": ["r"]},
                   "reads": [{"path": "a.py", "sha256": "s1", "content": "old"}]}}]}
        noted = json.loads(json.dumps(doc))
        noted.update(digest="d2", input_id="PLAN.P1.1@d2")
        noted["reads"][0].update(sha256="s2", content="edited by the executor")
        pack = noted["context_refs"][0]["content"]
        pack["item"].update(artifacts=[{"path": "@plan/inputs/" + "a" * 64, "role": "input"}], updated_at="t2")
        pack["reads"][0].update(sha256="s2", content="edited by the executor")
        self.assertEqual(worksource._worker_view(doc), worksource._worker_view(noted))
        amended = json.loads(json.dumps(noted))
        amended["context_refs"][0]["content"]["item"]["rules"] = ["r", "a new rule"]
        self.assertNotEqual(worksource._worker_view(doc), worksource._worker_view(amended))
        wider = json.loads(json.dumps(noted))
        wider["reads"].append({"path": "b.py", "sha256": "s3", "content": "new"})
        self.assertNotEqual(worksource._worker_view(doc), worksource._worker_view(wider))

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

    def test_a_brief_outside_exec_v1_is_refused_before_the_blob(self):
        import brief
        self.claim()
        built = brief.build

        def spoiled(*args, **kwargs):
            return {**built(*args, **kwargs), "verify": "an extra field verify() does not look at"}
        store = blobs.blob_path("sha256:" + "0" * 64, project=self.project).parent
        before = sorted(store.glob("*")) if store.is_dir() else []
        with mock.patch.object(brief, "build", side_effect=spoiled):
            with self.assertRaises(worksource.Blocked) as caught:
                worksource.op_brief({"op": "brief", "plan": self.plan, "ref": "P1.1", "run_id": "run-a"})
        self.assertEqual(caught.exception.code, "BRIEF_INVALID")
        self.assertIn("/verify", caught.exception.message)
        self.assertEqual(sorted(store.glob("*")) if store.is_dir() else [], before)
        self.assertEqual(self.item("P1.1").get("artifacts", []), [])


class ClassAuthorityTests(unittest.TestCase):
    """The planner (stdlib, ``command-routing.json``) and orch (aicore model catalog) grade a model alike (P7.3)."""

    MODELS = [("claude-code", "haiku"), ("claude-code", "claude-haiku-4-5-20251001"), ("claude-code", "sonnet"),
              ("claude-code", "claude-sonnet-5-5"), ("claude-code", "claude-opus-5-5"),
              ("codex", "gpt-5.6-luna"), ("codex", "gpt-6-sol"), ("codex", "gpt-6-astra"), ("codex", "gpt-6.1-sol"),
              ("grok", "grok-4.5"), ("grok", "grok-4.6"), ("grok", "grok-4.7"),
              ("claude-code", "mystery-model"), ("codex", "gpt-9"), ("nope", "haiku")]

    def test_planner_and_orch_agree_on_the_class_of_a_model(self):
        from aicore.provider import models
        lifecycle = partners.planner_engine("plan.lifecycle")
        catalog = models.load_model_catalog()
        for provider, model in self.MODELS:
            with self.subTest(provider=provider, model=model):
                self.assertEqual(models.admitted_class(catalog, provider, model),
                                 lifecycle.admitted_class(provider, model))
        self.assertEqual([models.admitted_class(catalog, "claude-code", model) for model in ("haiku", "sonnet", "claude-opus-5-5")],
                         ["economy", "implementation", "frontier"])


class RouteCorrectionFlowTests(Case):
    """An item with ``route.correction`` goes claim -> brief -> validate -> register like any other (P7.3)."""

    def test_claim_brief_validate_and_register_of_an_item_with_a_correction_route(self):
        run(self.project, "set", self.plan, "P1.1", "--json", json.dumps({"route": {
            "correction": {"class": "economy", "effort": "medium"}, "settings": {"native": True}}}))
        claimed = self.claim(items=["P1.1"])
        self.assertEqual(claimed["route"]["correction"], {"class": "economy", "effort": "medium"})
        brief = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")
        doc = json.loads(blobs.read_bytes(brief["input_ref"], project=self.project))
        self.assertEqual(doc["route"], {"minimum": {"class": "implementation", "effort": "high"}})
        path = Path(self.tmp.name) / "input.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        code, out = partners.orch_validate("execution-input", path)
        self.assertEqual(code, 0, out)
        answer = self.register(evidence={"V1": self.evidence()})  # the fake executor's work is done
        self.assertEqual(answer["outcome"], "recorded", answer)
        self.assertEqual(self.item("P1.1")["status"], "done")
        self.assertEqual(self.item("P1.1")["route"]["correction"], {"class": "economy", "effort": "medium"})


class CorrectionGrowthRegisterTests(Case):
    """The report the conductor writes for an executor correction that grew (P7.3) passes the registration status rule."""

    DEVIATION = {"text": "CORRECTION_SCOPE_GREW: correction round 2 changed paths beyond its findings, the tests, "
                         "CHANGELOG.md and docs: lib/b.py", "kind": "deviation", "class": "other", "outcome": "accepted",
                 "impact": "the next review round reads these paths", "next": "none", "evidence": ["lib/b.py"]}

    def test_the_deviation_goes_with_done_with_deviations_only(self):
        self.claim()
        report = {"summary": "did it", "open_issues": [self.DEVIATION]}
        refused = self.register(report=report, evidence={"V1": self.evidence()})
        self.assertEqual((refused["outcome"], refused["reason_code"]), ("refused", "REGISTER_STATUS_MISMATCH"), refused)
        self.assertEqual(self.item("P1.1")["status"], "in_progress")
        recorded = self.register(status="done_with_deviations", report=report, evidence={"V1": self.evidence()})
        self.assertEqual(recorded["outcome"], "recorded", recorded)
        self.assertEqual(self.item("P1.1")["status"], "done_with_deviations")


class RegisterTests(Case):
    def test_evidence_that_passes_closes_the_item_and_a_repeat_is_a_no_op(self):
        self.claim()
        answer = self.register(evidence={"V1": self.evidence()})
        self.assertEqual((answer["outcome"], answer["gate"]), ("recorded", {"verdict": "pass", "checks": {"V1": 0}}))
        self.assertEqual(self.item("P1.1")["status"], "done")
        again = self.register(evidence={"V1": self.evidence()})
        self.assertEqual(again["outcome"], "no-op")

    def test_lost_register_answer_repeats_without_second_finish_and_conflicts_are_refused(self):
        self.claim()
        evidence = {"V1": self.evidence()}
        self.assertEqual("recorded", self.register(evidence=evidence)["outcome"])
        folder = self.project / "plans" / self.plan
        before_item = (folder / "phases/P1/P1.1.json").read_bytes()
        before_log = (folder / "log.jsonl").read_bytes()
        self.assertEqual("no-op", self.register(evidence=evidence)["outcome"])
        self.assertEqual(before_item, (folder / "phases/P1/P1.1.json").read_bytes())
        self.assertEqual(before_log, (folder / "log.jsonl").read_bytes())
        conflict = self.register(status="done_with_deviations", evidence=evidence,
                                 report={"summary": "changed", "open_issues": [{"kind": "deviation", "text": "different"}]})
        self.assertEqual(("refused", "ATTEMPT_CONFLICT"), (conflict["outcome"], conflict["reason_code"]), conflict)
        self.assertEqual(before_item, (folder / "phases/P1/P1.1.json").read_bytes())
        # The bridge logs report issues before finish refuses the conflicting outcome.
        # The finish effect itself must still occur only once.
        after_log = (folder / "log.jsonl").read_bytes()
        before_events = [json.loads(line) for line in before_log.splitlines()]
        after_events = [json.loads(line) for line in after_log.splitlines()]
        self.assertEqual([event for event in before_events if event.get("type") != "deviation"],
                         [event for event in after_events if event.get("type") != "deviation"])

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
    def test_retry_start_passes_strict_route_through_cli(self):
        self.claim()
        blocked = self.register(status="blocked", report={"summary": "stuck", "open_issues": [
            {"text": "needs the plan widened", "kind": "escalation"}]})
        self.assertEqual(blocked["outcome"], "recorded")
        wrapper, log = self.trace_planner_cli()
        with mock.patch.dict(os.environ, {"PLANNER_PLAN_PY": str(wrapper)}):
            answer = self.register(evidence={"V1": self.evidence()})
        self.assertEqual(answer["outcome"], "recorded", answer)
        starts = [argv for argv in map(json.loads, log.read_text().splitlines()) if argv[0] == "start"]
        self.assertEqual(len(starts), 1)
        self.assertIn("--strict-route", starts[0])

    def test_a_blocked_attempt_retried_by_its_run_registers_done_without_a_conflict(self):
        self.claim()
        blocked = self.register(status="blocked", report={"summary": "stuck", "open_issues": [
            {"text": "needs the plan widened", "kind": "escalation"}]})
        self.assertEqual(blocked["outcome"], "recorded")
        self.assertEqual(self.item("P1.1")["status"], "blocked")
        done = self.register(status="done", evidence={"V1": self.evidence()}, report={"summary": "now really done"})
        self.assertEqual(done["outcome"], "recorded", done)
        self.assertEqual(self.item("P1.1")["status"], "done")
        notes = self.item("P1.1")["result"].get("notes", "")
        self.assertIn("now really done", notes)
        self.assertNotIn("stuck", notes)  # the text of the blocked attempt does not outlive the retry

    def test_a_retried_attempt_blocked_again_replaces_its_first_block(self):
        # PLAN9 P6.3 (cnd-20261025T112512Z-0d84ef): blocked on Q1/Q2, retried, blocked again on Q3 with green checks:
        # the planner refused the second block of the same attempt with ATTEMPT_CONFLICT and the run stopped
        self.claim()
        first = {"summary": "stuck", "open_issues": [{"text": "QUESTION: Q1 which version", "kind": "escalation"}]}
        self.assertEqual(self.register(status="blocked", report=first)["outcome"], "recorded")
        again = self.register(status="blocked", evidence={"V1": self.evidence()}, report={
            "summary": "stuck again", "open_issues": [{"text": "QUESTION: Q3 which boundary", "kind": "escalation"}]})
        self.assertEqual(again["outcome"], "recorded", again)
        piece = self.item("P1.1")
        self.assertEqual(piece["status"], "blocked")
        self.assertIn("stuck again", piece["result"].get("notes", ""))
        self.assertIn("Q3", piece["result"].get("escalation", ""))

    def test_a_repeated_block_of_the_same_attempt_stays_a_no_op(self):
        self.claim()
        report = {"summary": "stuck", "open_issues": [{"text": "QUESTION: Q1 which version", "kind": "escalation"}]}
        self.assertEqual(self.register(status="blocked", report=report)["outcome"], "recorded")
        self.assertEqual(self.register(status="blocked", report=report)["outcome"], "no-op")


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
        self.assertEqual("att-run-a-P1.1", answer["attempt"])
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project, capture_output=True, text=True).stdout
        self.assertEqual(answer["sha"], head.strip())
        shown = subprocess.run(["git", "-c", "core.quotePath=false", "show", "--name-only", "--format=", "HEAD"],
                               cwd=self.project,
                               capture_output=True, text=True).stdout.split()
        self.assertIn("lib/A.py", shown)
        self.assertIn(f"plans/{self.plan}/artifacts/P1.1/stage-report.json", shown)
        repeated = self.commit()
        self.assertEqual(("no-op", "att-run-a-P1.1"), (repeated["outcome"], repeated["attempt"]))

    def test_a_foreign_dirty_path_is_refused(self):
        self.claim()
        (self.project / "elsewhere.txt").write_text("x", encoding="utf-8")
        answer = self.commit()
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "OUTSIDE_SCOPE"))
        self.assertEqual("att-run-a-P1.1", answer["attempt"])


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


class DecisionTests(Case):
    """``decision``: an answered question of an item becomes an accepted D# that applies to the item, with the origin that
    lets a later run find it by ``question_key``; a repeat changes nothing."""

    KEY = "qk-" + "a1" * 8
    DIGEST = "a1" * 32

    def decision(self, **extra) -> dict:
        fields = {"op": "decision", "collection": self.plan, "ref": "P1.1", "run_id": "run-a",
                  "attempt_id": "att-run-a-P1.1",
                  "question": {"id": "Q1", "revision": 1, "kind": "decision", "text": "Keep  the old flag name?",
                               "options": [{"id": "keep", "label": "keep it"}, {"id": "rename", "label": "rename it"}]},
                  "question_key": self.KEY, "question_digest": self.DIGEST,
                  "resolution": {"value": "rename", "by": "owner", "at": "2026-10-24T00:00:00Z"}, "authority": "owner",
                  "rationale": "Answered by owner: rename: rename it", "evidence": ["plans/x/questions.json"],
                  "actor": ACTOR, **extra}
        return self.op(worksource.op_decision, **fields)

    def decisions(self) -> list:
        rows = json.loads(run(self.project, "--output", "json", "list", self.plan, "decision").stdout)["data"]
        return [self.item(row["ref"]) for row in rows]

    def test_the_answer_becomes_an_accepted_decision_that_applies_to_the_item(self):
        answer = self.decision()
        self.assertEqual((answer["outcome"], answer["decision_id"]), ("recorded", "D1"))
        (doc,) = self.decisions()
        self.assertEqual((doc["status"], doc["applies_to"], doc["answered_by"]), ("accepted", ["P1.1"], "owner"))
        self.assertEqual(doc["decision"], "rename: rename it")
        self.assertEqual(doc["question"], "Keep the old flag name?")
        self.assertEqual([(row["id"], row["text"]) for row in doc["options"]], [("A", "keep: keep it"), ("B", "rename: rename it")])
        self.assertEqual(doc["origin"], {"kind": "question", "run": "run-a", "item": "P1.1", "question_id": "Q1",
                                         "question_key": self.KEY, "question_digest": self.DIGEST, "revision": 1})
        self.assertIn({"kind": "owner", "ref": "owner", "note": "answered with orch conduct answer"}, doc["evidence"])
        self.assertIn({"kind": "repo", "ref": "plans/x/questions.json"}, doc["evidence"])
        self.assertEqual(doc["actor"]["provider"], "claude-code")
        self.assertEqual(run(self.project, "check", self.plan, check=False).returncode, 0)

    def test_a_repeat_for_the_same_question_key_and_item_is_a_no_op(self):
        self.decision()
        again = self.decision(run_id="run-b", resolution={"value": "keep", "by": "owner"})
        self.assertEqual((again["outcome"], again["decision_id"]), ("no-op", "D1"))
        self.assertEqual(len(self.decisions()), 1)
        other = self.decision(question_key="qk-" + "b2" * 8)
        self.assertEqual((other["outcome"], other["decision_id"]), ("recorded", "D2"))

    def test_the_same_key_on_another_item_is_another_decision(self):
        self.decision()
        self.assertEqual(self.decision(ref="P1.2")["outcome"], "recorded")

    def test_an_advice_and_a_panel_name_their_origin_and_are_answered_by_an_agent(self):
        advice = self.decision(authority="advisor", resolution={"value": "keep", "by": "advisor"})
        panel = self.decision(question_key="qk-" + "c3" * 8, authority="panel", resolution={"value": "keep", "by": "panel"})
        self.assertEqual((advice["outcome"], panel["outcome"]), ("recorded", "recorded"))
        first, second = self.decisions()
        self.assertEqual((first["origin"]["kind"], first["answered_by"], second["origin"]["kind"]), ("advice", "agent", "panel"))
        self.assertNotIn("owner", [row["kind"] for row in first["evidence"]])

    def test_a_free_text_and_a_json_value_are_the_text_of_the_decision(self):
        text = self.decision(question={"id": "Q2", "revision": 2, "kind": "clarification", "text": "How many retries?"},
                             resolution={"value": 3, "by": "owner"})
        self.assertEqual(text["outcome"], "recorded")
        (doc,) = self.decisions()
        self.assertEqual((doc["decision"], doc.get("options")), ("3", None))

    def test_the_next_brief_carries_the_decision_with_its_key_inside_exec_v1(self):
        self.claim()
        self.decision()
        brief = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")  # checked by orch
        stored = json.loads(blobs.read_bytes(brief["input_ref"], project=self.project))
        (entry,) = [row for row in stored["decisions"] if row.get("question_key")]
        self.assertEqual((entry["question_key"], entry["question_digest"], entry["status"], entry["decision"]),
                         (self.KEY, self.DIGEST, "accepted", "rename: rename it"))

    def test_an_unknown_item_is_refused_with_the_planner_code(self):
        answer = self.decision(ref="P9.9")
        self.assertEqual(answer["outcome"], "refused")
        self.assertTrue(answer["reason_code"])
        self.assertEqual(self.decisions(), [])


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
        path = self.project / "plans" / self.plan / answer["path"].removeprefix("@plan/")
        self.assertEqual(answer["path"], "@plan/inputs/research/P1.1-1.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self.RESULT)
        self.assertEqual(len(self.declared()), 1)

    def test_a_repeat_changes_nothing_and_a_changed_result_is_written_again(self):
        self.claim()
        self.research()
        self.assertEqual(self.research()["outcome"], "no-op")
        self.assertEqual(len(self.declared()), 1)
        again = self.research(result={**self.RESULT, "unknowns": ["new"]})
        self.assertEqual(again["outcome"], "recorded")
        path = self.project / "plans" / self.plan / again["path"].removeprefix("@plan/")
        self.assertEqual(json.loads(path.read_text())["unknowns"], ["new"])

    def test_a_number_below_one_or_a_ref_that_is_no_file_name_is_refused(self):
        self.claim()
        self.assertEqual(self.research(number=0)["reason_code"], "RESEARCH_REF_INVALID")
        self.assertEqual(self.research(ref="../x")["reason_code"], "RESEARCH_REF_INVALID")

    def test_an_unknown_item_is_refused_with_the_planner_code(self):
        answer = self.research(ref="P9.9")
        self.assertEqual(answer["outcome"], "refused")
        self.assertTrue(answer["reason_code"])
        self.assertFalse((self.project / "plans" / self.plan / "research" / "P9.9-1.json").exists())


class ReadyRuntimeTests(Case):
    """A required certificate survives actual bridge operations in both supported plan layouts."""

    def setUp(self):
        super().setUp()
        self.plan_root = self.project / "plans" / self.plan
        self.readiness, self.store, self.lifecycle, self.ops = partners.planner_engine(
            "plan.readiness", "plan.store", "plan.lifecycle", "plan.ops")

    def workspace(self):
        base = Path(self.tmp.name)
        home, workspace = base / "home", base / "workspaces" / "runtime"
        marker = self.project / ".swissknifeman" / "project.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                      "workspace": "runtime", "project_id": "runtime-test", "plans_store": "workspace"}))
        bindings = home / "state/workspaces/runtime/bindings.json"
        bindings.parent.mkdir(parents=True)
        bindings.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:workspace-bindings:v1", "projects": {
            "runtime-test": {"paths": [str(self.project)], "primary": str(self.project),
                             "bound_at": "2026-10-24T00:00:00Z"}}}))
        patcher = mock.patch.dict(os.environ, {"HOME": str(home), "SKM_HOME": str(home),
                                               "SKM_WORKSPACES_ROOT": str(workspace.parent),
                                               "SKM_AICORE_EVENTS__DELIVERY": "off"})
        patcher.start()
        self.addCleanup(patcher.stop)
        target = workspace / "projects/runtime-test/plans" / self.plan
        target.parent.mkdir(parents=True)
        shutil.move(str(self.plan_root), str(target))
        self.plan_root = target

    def assert_ready(self, digest):
        p = self.store.load_plan(self.plan_root)
        self.assertEqual(self.readiness.semantic_digest(p, "P1"), digest)
        self.assertEqual(self.readiness.status(p, "P1")["phases"][0]["status"], "ready")
        self.readiness.require(p, "P1")
        self.assertEqual(self.lifecycle.next(p).kind, "run-items")

    def runtime_cycle(self):
        run(self.project, "set", self.plan, "plan", "--json",
            '{"settings":{"design_audit":"required","evidence":"required"}}')
        self.ops.add_document(self.plan_root, {"id": "audit-p1-runtime", "title": "Runtime audit", "sections": []})
        self.readiness.record(self.plan_root, "P1", verdict="ready", audit="knowledge/audit-p1-runtime", actor=ACTOR)
        digest = self.readiness.semantic_digest(self.store.load_plan(self.plan_root), "P1")
        self.assertEqual(self.claim(items=["P1.1"])["status"], "claimed")
        self.assert_ready(digest)

        first = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")
        again = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")
        self.assertEqual((again["input_ref"], again["reused"]), (first["input_ref"], True))
        self.assert_ready(digest)

        research = {"op": "research", "plan": self.plan, "ref": "P1.1", "run_id": "run-a", "number": 1,
                    "result": ResearchTests.RESULT, "actor": ACTOR}
        saved = self.op(worksource.op_research, **research)
        self.assertEqual(saved["outcome"], "recorded")
        self.assertEqual(saved["path"], "@plan/inputs/research/P1.1-1.json")
        self.assertEqual(self.op(worksource.op_research, **research)["outcome"], "no-op")
        changed_research = {**research, "result": {**ResearchTests.RESULT, "unknowns": ["new finding"]}}
        self.assertEqual(self.op(worksource.op_research, **changed_research)["outcome"], "recorded")
        self.assert_ready(digest)
        self.assertTrue(all(a["role"] == "input" and a["path"].startswith("@plan/inputs/")
                            for a in self.item("P1.1")["artifacts"]))
        refreshed = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")
        if not self.plan_root.is_relative_to(self.project):
            self.assertNotEqual(refreshed["input_ref"], first["input_ref"])  # research remains visible in the embedded pack
        repeated = self.op(worksource.op_brief, op="brief", plan=self.plan, ref="P1.1", run_id="run-a")
        self.assertEqual((repeated["input_ref"], repeated["reused"]), (refreshed["input_ref"], True))
        self.assert_ready(digest)
        self.assertEqual(self.claim(items=["P1.1"])["status"], "claimed")  # resume after briefing/research
        self.assert_ready(digest)

        evidence = {"V1": self.evidence()}
        registered = self.register(evidence=evidence)
        self.assertEqual(registered["outcome"], "recorded", registered)
        item = self.item("P1.1")
        (proof,) = item["result"]["checks"]
        self.assertEqual((proof["id"], proof["exit"]), ("V1", 0))
        path = proof["evidence"]
        kept = self.plan_root / path.removeprefix("@plan/") if path.startswith("@plan/") else self.project / path
        self.assertEqual(json.loads(kept.read_bytes())["exit"], 0)
        self.assertFalse(any(a["role"] == "output" for a in item["artifacts"]))
        self.assert_ready(digest)
        self.assertEqual(self.register(evidence=evidence)["outcome"], "no-op")
        self.assert_ready(digest)

        second = self.claim(run_id="run-b")
        self.assertEqual((second["status"], second["ref"]), ("claimed", "P1.2"), second)
        self.assertEqual(self.claim(run_id="run-b", items=["P1.2"])["status"], "claimed")
        self.assert_ready(digest)

        # Authored artifact declarations are still semantic, including inputs outside the reserved runtime folder.
        self.ops.add_artifact(self.plan_root, "P1.2", "authored-input.json", "input")
        row = self.readiness.status(self.store.load_plan(self.plan_root), "P1")["phases"][0]
        self.assertEqual((row["status"], row["changed"]), ("stale", ["digest"]))
        refused = self.claim(run_id="run-b", items=["P1.2"])
        self.assertEqual((refused["status"], refused["reason_code"]), ("blocked", "CLAIM_BLOCKED"))
        self.assertIn("READINESS_STALE", refused["message"])

    def test_required_repository_phase_survives_runtime_cycle(self):
        self.runtime_cycle()

    def test_required_workspace_phase_survives_runtime_cycle(self):
        self.workspace()
        self.runtime_cycle()


class ReadinessOpTests(Case):
    """``readiness``: phases from ``plan.py readiness status`` and the next lane read as ``claim`` reads it."""

    def setUp(self):
        super().setUp()
        self.plan_root = self.project / "plans" / self.plan
        self.readiness, self.store, self.ops = partners.planner_engine("plan.readiness", "plan.store", "plan.ops")

    def ask(self, plan=None) -> dict:
        return self.op(worksource.op_readiness, op="readiness", collection=plan or self.plan)

    def certify(self) -> str:
        self.ops.add_document(self.plan_root, {"id": "audit-p1", "title": "Audit", "sections": []})
        self.readiness.record(self.plan_root, "P1", verdict="ready", audit="knowledge/audit-p1", actor=ACTOR)
        return self.readiness.semantic_digest(self.store.load_plan(self.plan_root), "P1")

    def test_missing_phase_and_the_first_lane_of_run_items(self):
        answer = self.ask()
        digest = self.readiness.semantic_digest(self.store.load_plan(self.plan_root), "P1")
        self.assertEqual(answer, {"op": "readiness", "outcome": "ok",
                                  "phases": [{"id": "P1", "status": "missing", "digest": digest}],
                                  "next": {"kind": "run-items", "items": ["P1.1"], "phase": "P1", "message": None}})

    def test_a_ready_phase_and_a_stale_one_after_a_change_of_its_item(self):
        digest = self.certify()
        self.assertEqual(self.ask()["phases"], [{"id": "P1", "status": "ready", "digest": digest}])
        run(self.project, "set", self.plan, "P1.2", "--json", json.dumps({"why": "a changed reason"}))
        (row,) = self.ask()["phases"]
        self.assertEqual(row["status"], "stale")
        self.assertNotEqual(row["digest"], digest)

    def test_a_required_audit_is_the_next_step_with_its_message(self):
        run(self.project, "set", self.plan, "plan", "--json", '{"settings":{"design_audit":"required"}}')
        answer = self.ask()
        self.assertEqual(answer["phases"][0]["status"], "missing")
        self.assertEqual((answer["next"]["kind"], answer["next"]["items"], answer["next"]["phase"]),
                         ("audit-phase", [], "P1"))
        self.assertTrue(answer["next"]["message"])
        self.certify()
        self.assertEqual(self.ask()["next"]["kind"], "run-items")  # the certificate opens the lane

    def test_an_item_in_progress_leaves_no_free_lane_and_claim_reads_the_same(self):
        self.assertEqual(self.claim(items=["P1.1"])["status"], "claimed")
        lane = self.ask()["next"]
        self.assertNotEqual(lane["kind"], "run-items")
        self.assertEqual(lane["items"], [])
        self.assertTrue(lane["message"])
        self.assertEqual(worksource._candidate(self.plan, "run-other", None), (None, lane["message"]))

    def test_a_refusal_of_the_planner_is_refused_with_its_code(self):
        answer = self.ask("NO-SUCH-PLAN")
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "PLAN_NOT_FOUND"), answer)
        self.assertNotIn("phases", answer)
        with mock.patch.object(worksource, "plan_json", return_value={"phases": [{"id": "P1"}]}):
            answer = self.ask()
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "READINESS_UNREADABLE"))


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

    def test_invoke_answers_readiness(self):
        registration = plugins.find_registration("planner-orch", self.project, env=self.env)
        result = plugins.invoke_one(registration, "orch:work-source", {"op": "readiness", "collection": self.plan},
                                    env=self.env, project=self.project)
        self.assertEqual(result.status, "ok", result.error)
        self.valid(result.output, "output")
        self.assertEqual((result.output["outcome"], result.output["next"]["items"]), ("ok", ["P1.1"]))

    def test_context_supplement_opt_in_survives_real_plugin_environment_and_brief_lifecycle(self):
        self.plan_root = self.project / "plans" / self.plan
        ReadyRuntimeTests.workspace(self)
        self.env = dict(os.environ, PLANNER_ORCH_CONTEXT_DELIVERY="supplement")
        self.env["SKM_WORKSPACES"] = self.env["SKM_WORKSPACES_ROOT"]  # canonical variable survives plugin isolation
        config = Path(self.env["SKM_HOME"]) / "config/config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("schema_version = 1\n[aicore.plugins.planner-orch]\n"
                          f"manifest = {json.dumps(str(_BRIDGE / 'extension.json'))}\ntrusted = true\n")
        registration = plugins.find_registration("planner-orch", self.project, env=self.env)
        result = plugins.invoke_one(registration, "orch:work-source", {
            "op": "brief", "plan": str(self.plan_root), "ref": "P1.1", "run_id": "run-p"},
            env=self.env, project=self.project)
        self.assertEqual(result.status, "ok", result.error)
        self.valid(result.output, "output")
        declaration = self.item("P1.1")["artifacts"][-1]
        saved = self.plan_root / declaration["path"].removeprefix("@plan/")
        stored = json.loads(saved.read_bytes())
        self.assertEqual(stored["provenance"]["plan_dir"], "@plan")
        self.assertEqual(stored["context_refs"][0]["delivery"], "supplement")
        self.assertEqual(stored["context_refs"][0]["content"]["item"]["id"], "P1.1")
        self.assertEqual(stored["digest"], result.output["digest"])
        self.assertEqual(declaration["role"], "input")
        self.assertEqual(saved.name, result.output["input_ref"]["digest"].removeprefix("sha256:"))
        self.assertEqual(saved.read_bytes(), blobs.read_bytes(result.output["input_ref"], project=self.project))

    def test_on_demand_required_json_survives_real_workspace_source_lifecycle(self):
        self.plan_root = self.project / "plans" / self.plan
        ReadyRuntimeTests.workspace(self)
        self.env = dict(os.environ)
        self.env["SKM_WORKSPACES"] = self.env["SKM_WORKSPACES_ROOT"]
        config = Path(self.env["SKM_HOME"]) / "config/config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("schema_version = 1\n[aicore.plugins.planner-orch]\n"
                          f"manifest = {json.dumps(str(_BRIDGE / 'extension.json'))}\ntrusted = true\n")
        raw = (json.dumps({"fixtures": list(range(10000))}) + "\n").encode()
        (self.project / "fixtures.json").write_bytes(raw)
        ops = partners.planner_engine("plan.ops")
        ops.patch(self.plan_root, "P1.1", {"reads": [{"path": "fixtures.json", "why": "fixture provenance",
                                                      "required": True, "delivery": "on-demand"}]})
        registration = plugins.find_registration("planner-orch", self.project, env=self.env)
        result = plugins.invoke_one(registration, "orch:work-source", {
            "op": "brief", "plan": str(self.plan_root), "ref": "P1.1", "run_id": "run-p"},
            env=self.env, project=self.project)
        self.assertEqual(result.status, "ok", result.error)
        self.valid(result.output, "output")
        stored = json.loads(blobs.read_bytes(result.output["input_ref"], project=self.project))
        entry, = stored["reads"]
        self.assertEqual((entry["path"], entry["required"], entry["exists"], entry["delivery"]),
                         ("fixtures.json", True, True, "on-demand"))
        self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn("content", entry)

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

    def commit_with(self, fields, refusal):
        """``op_commit`` against a planner that refuses with ``refusal`` unless ``--leave-outside`` is passed."""
        from types import SimpleNamespace
        calls = []

        def plan_py(argv, plans_root=None):
            calls.append(argv)
            if "--leave-outside" in argv:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"sha": "abc1234"}), stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr=refusal)

        with mock.patch.object(worksource, "plan_py", side_effect=plan_py):
            return worksource.op_commit({"plan": "PLAN1", "ref": "P1.1", **fields}), calls

    def test_dirt_of_another_session_stays_outside_a_commit_whose_paths_the_conductor_named(self):
        refusal = ("OUTSIDE_SCOPE: foreign dirty paths: 'ideas/other-session.md', 'plans/2026-X/phases/P1/P1.2.json'; "
                   "use --leave-outside or --path and plan.py log --type deviation")
        answer, calls = self.commit_with({"paths": ["src/a.py"]}, refusal)
        self.assertEqual((answer["outcome"], answer["sha"]), ("committed", "abc1234"))
        self.assertEqual(answer["message"], "left outside, not the work of this piece: ideas/other-session.md")
        self.assertEqual(len(calls), 2)
        answer, _ = self.commit_with({}, refusal)  # no path set from the caller: foreign work is not guessed away
        self.assertEqual((answer["outcome"], answer["reason_code"]), ("refused", "OUTSIDE_SCOPE"))
