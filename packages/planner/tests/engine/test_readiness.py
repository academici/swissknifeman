"""Semantic material table, certificate refusal atomicity and status invalidation."""
import copy
import io
import json
from pathlib import Path
import sys
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import check, cli, lifecycle, ops, readiness, schema, views  # noqa: E402

try:
    from . import demo, test_lifecycle
except ImportError:
    import demo
    import test_lifecycle


class ReadinessTests(test_lifecycle.LifeCase):
    def setUp(self):
        super().setUp()
        ops.add_document(self.root, {"id": "audit-p1-test", "title": "Audit", "applies_to": ["P1"],
                                     "sections": [{"id": "verdict", "title": "Verdict", "text": "GREEN"}]})

    def record(self, **kw):
        return readiness.record(self.root, "P1", **{"verdict": "ready", "audit": "knowledge/audit-p1-test",
                                "actor": test_lifecycle.OPUS, **kw})

    def test_semantic_material_inclusions_each_change_the_digest(self):
        base = self.load()
        base.decisions["D1"] = {"id": "D1", "applies_to": ["P1"], "decision": "one"}
        base.documents["design"] = {"id": "design", "sections": [{"text": "one"}]}
        base.items["P1.1"]["reads"] = [{"ref": "knowledge/design#section"}]
        base.units["P1.1/U1"] = demo.fixture("unit-e3a-u1")
        cases = {
            "plan.rules": lambda p: p.plan.update(rules=["new"]),
            "brief.requirements": lambda p: p.brief.update(requirements=["new"]),
            "phase.batches": lambda p: p.phases["P1"]["batches"][0].update(mode="required"),
            "phase.scope": lambda p: p.phases["P1"].update(scope={"include": ["new"]}),
            "item.scope": lambda p: p.items["P1.1"]["scope"].update(include=["new"]),
            "item.validation": lambda p: p.items["P1.1"]["validation"][0].update(cmd="false"),
            "item.depends_on": lambda p: p.items["P1.1"].update(depends_on=["P2.1"]),
            "item.task_files": lambda p: p.items["P1.1"].update(task_files=[{"path": "new"}]),
            "item.route": lambda p: p.items["P1.1"]["route"].update(effort="max"),
            "item.review": lambda p: p.items["P1.1"].update(review={"mode": "requested"}),
            "item.authority": lambda p: p.items["P1.1"].update(authority={"kind": "owner_gate"}),
            "item.authored_input": lambda p: p.items["P1.1"].update(artifacts=[{"role": "input", "path": "research.json"}]),
            "item.authored_output": lambda p: p.items["P1.1"].update(artifacts=[{"role": "output", "path": "result.json"}]),
            "item.output_in_inputs": lambda p: p.items["P1.1"].update(artifacts=[{"role": "output", "path": "@plan/inputs/result.json"}]),
            "unit.instructions": lambda p: p.units["P1.1/U1"].update(instructions="new"),
            "decision.phase": lambda p: p.decisions["D1"].update(decision="new"),
            "document.read": lambda p: p.documents["design"]["sections"][0].update(text="new"),
        }
        digest = readiness.semantic_digest(base, "P1")
        for field, mutate in cases.items():
            with self.subTest(field=field):
                candidate = copy.deepcopy(base)
                mutate(candidate)
                self.assertNotEqual(digest, readiness.semantic_digest(candidate, "P1"))

    def test_every_owned_field_and_runtime_exclusion_is_stable(self):
        base = self.load()
        base.units["P1.1/U1"] = demo.fixture("unit-e3a-u1")
        digest = readiness.semantic_digest(base, "P1")
        for kind, doc in (("plan", base.plan), ("brief", base.brief), ("phase", base.phases["P1"]),
                          ("item", base.items["P1.1"]), ("unit", base.units["P1.1/U1"])):
            for field in ops.OWNED_FIELDS[kind]:
                with self.subTest(kind=kind, field=field):
                    old = copy.deepcopy(doc)
                    doc[field] = "runtime"
                    self.assertEqual(digest, readiness.semantic_digest(base, "P1"))
                    doc.clear()
                    doc.update(old)
        cases = {
            "plan.pause": lambda p: p.plan.update(pause={"reason": "pause"}),
            "plan.phases": lambda p: p.plan.update(phases=["P2", "P1"]),
            "plan.settings": lambda p: p.plan["settings"].update(design_audit="required"),
            "item.role_input": lambda p: p.items["P1.1"].update(artifacts=[{"role": "input", "path": "@plan/inputs/brief.json"}]),
            "rag.status": lambda p: p.items["P1.1"]["rag"].update(status="done"),
            "rag.captures": lambda p: p.items["P1.1"]["rag"].update(captures=["capture"]),
            "audit-document": lambda p: p.documents.update({"audit-p1-new": {"global": True}}),
            "readiness-document": lambda p: p.documents.update({"readiness-p1-new": {"global": True}}),
            "unrelated-doc": lambda p: p.documents.update({"other": {"applies_to": ["P2"]}}),
            "unrelated-decision": lambda p: p.decisions.update({"D99": {"applies_to": ["P2"]}}),
        }
        for field, mutate in cases.items():
            with self.subTest(field=field):
                candidate = copy.deepcopy(base)
                mutate(candidate)
                self.assertEqual(digest, readiness.semantic_digest(candidate, "P1"))

    def test_decision_and_document_reachability(self):
        for kind, name in (("decisions", "D1"), ("documents", "design")):
            for scope in ({"global": True}, {"applies_to": ["P1"]}, {"applies_to": ["P1.1"]}, {}):
                with self.subTest(kind=kind, scope=scope):
                    p = self.load()
                    if not scope:
                        p.items["P1.1"]["decisions" if kind == "decisions" else "reads"] = (
                            [name] if kind == "decisions" else [{"ref": f"knowledge/{name}"}])
                    getattr(p, kind)[name] = {"id": name, **scope, "title": "old"}
                    old = readiness.semantic_digest(p, "P1")
                    getattr(p, kind)[name]["title"] = "new"
                    self.assertNotEqual(old, readiness.semantic_digest(p, "P1"))

    def test_status_missing_ready_stale_record_and_policy(self):
        self.assertEqual(readiness.status(self.load(), "P1")["phases"][0]["status"], "missing")
        self.record()
        row = readiness.status(self.load(), "P1")["phases"][0]
        self.assertEqual(row["status"], "ready")
        self.assertFalse(row["certificate"]["independent"])
        self.assertEqual(self.events()[-1]["type"], "readiness_recorded")
        ops.patch(self.root, "P1.1", {"summary": "changed"})
        row = readiness.status(self.load(), "P1")["phases"][0]
        self.assertEqual((row["status"], row["changed"]), ("stale", ["digest"]))
        self.record()
        self.assertEqual(readiness.status(self.load(), "P1")["phases"][0]["status"], "ready")
        p = self.load()
        digest = readiness.policy_digest(p)
        p.plan["settings"]["design_audit"] = "required"
        self.assertNotEqual(digest, readiness.policy_digest(p))
        self.assertEqual(readiness.status(p, "P1")["phases"][0]["changed"], ["policy"])
        with mock.patch.object(readiness.plugins, "planner_version", return_value="future"):
            self.assertNotEqual(digest, readiness.policy_digest(self.load()))

    def test_record_refuses_errors_and_blockers_without_writes(self):
        for verdict in readiness.READY:
            self.refused("READINESS_STRUCTURAL_ERRORS", readiness.record, "P1", verdict=verdict,
                         audit="knowledge/audit-p1-test", actor=test_lifecycle.OPUS,
                         external=lambda p: [check.Issue("error", "BRIEF_INCOMPLETE", "P1.1", "bad brief")])
            finding = {"id": "F1", "severity": "major", "blocking": True, "ref": "P1.1", "text": "too costly"}
            self.refused("READINESS_BLOCKING_FINDINGS", readiness.record, "P1", verdict=verdict,
                         audit="knowledge/audit-p1-test", actor=test_lifecycle.OPUS, findings=[finding])
            self.refused("READINESS_BLOCKING_FINDINGS", readiness.record, "P1", verdict=verdict,
                         audit="knowledge/audit-p1-test", actor=test_lifecycle.OPUS,
                         findings=[{**finding, "blocking": False}])
        self.record(verdict="not_ready", findings=[finding])
        self.assertEqual(readiness.status(self.load(), "P1")["phases"][0]["status"], "not_ready")
        self.refused("REF_UNKNOWN", readiness.record, "P1", verdict="ready", audit="knowledge/missing",
                     actor=test_lifecycle.OPUS)
        self.refused("PHASE_NOT_DETAILED", readiness.record, "P2", verdict="ready", audit="knowledge/audit-p1-test",
                     actor=test_lifecycle.OPUS)
        demo.rewrite(self.root, "phases/P1/P1.1.json", lambda d: d.update(validation=[]))
        self.refused("READINESS_STRUCTURAL_ERRORS", readiness.record, "P1", verdict="ready",
                     audit="knowledge/audit-p1-test", actor=test_lifecycle.OPUS)

    def test_runtime_operations_do_not_stale_certificate(self):
        ops.patch(self.root, "plan", {"settings": {"design_audit": "required"}})
        self.record()
        before = readiness.semantic_digest(self.load(), "P1")
        self.start("P1.1", "P1.2", scout=False)
        inputs = self.root / "inputs"
        inputs.mkdir()
        for name in ("brief.txt", "research.txt"):
            (inputs / name).write_text("runtime input")
            ops.add_artifact(self.root, "P1.1", f"@plan/inputs/{name}", "input")
            self.assertEqual(before, readiness.semantic_digest(self.load(), "P1"))
            self.assertEqual(readiness.status(self.load(), "P1")["phases"][0]["status"], "ready")
        evidence = self.root / "artifacts/evidence/V1.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps({
            "$schema": "urn:swissknifeman:task:plan:check-evidence:v1", "evidence_id": "runtime-evidence",
            "check_id": "V1", "subject": f"{self.load().plan['short_id']}.P1.1", "procedure": {"cmd": "true"},
            "candidate": {"head": "0123456"}, "exit": 0, "started_at": "2026-10-24T00:00:00Z",
            "finished_at": "2026-10-24T00:00:01Z", "producer": {"kind": "executor"}}))
        self.finish("P1.1", evidence={"V1": "@plan/artifacts/evidence/V1.json"})
        self.assertEqual(self.load().items["P1.1"]["result"]["checks"][0]["evidence"],
                         "@plan/artifacts/evidence/V1.json")
        self.assertEqual(before, readiness.semantic_digest(self.load(), "P1"))
        self.finish("P1.2")
        lifecycle.log(self.root, "P1", "note", "runtime log")
        lifecycle.reconcile(self.root)
        views.render_all(self.load())
        self.assertEqual(before, readiness.semantic_digest(self.load(), "P1"))

    def test_advisories_and_phase_filtered_external_counts(self):
        finding = {"id": "F1", "severity": "minor", "blocking": False, "ref": "P1.1", "text": "advisory"}
        result = self.record(verdict="ready_with_advisories", findings=[finding],
                             actor={"provider": "codex", "model": "gpt-6-astra"},
                             external=lambda p: [check.Issue("error", "OTHER_PHASE", "P2.1", "other phase"),
                                                 check.Issue("warning", "ADVISORY", "P1.1", "warning")])
        self.assertTrue(result["independent"])
        self.assertEqual(result["structural"]["external"], {"errors": 0, "warnings": 1})

    def test_malformed_findings_refuse_before_writing(self):
        self.refused("SCHEMA_INVALID", readiness.record, "P1", verdict="ready", audit="knowledge/audit-p1-test",
                     actor=test_lifecycle.OPUS, findings=[{"id": "incomplete"}])

    def test_status_refuses_invalid_stored_certificate(self):
        for invalid in (None, {}, "ready", {"status": "ready"}):
            p = self.load()
            p.phases["P1"]["readiness"] = invalid
            with self.assertRaises(readiness.PlanError) as caught:
                readiness.status(p, "P1")
            self.assertEqual(caught.exception.code, "SCHEMA_INVALID")

    def test_status_is_read_only_and_cli_validates_output(self):
        before = self.tree()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["readiness", "status", str(self.root), "P1", "--json"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(schema.validate(json.loads(out.getvalue()), "read-readiness"), [])
        self.assertEqual(before, self.tree())

    def test_plans_root_is_retained_on_either_side_of_subcommand(self):
        for argv in (["readiness", "--plans-root", str(self.plans), "status", "PLAN1", "--json"],
                     ["readiness", "status", "PLAN1", "--json", "--plans-root", str(self.plans)]):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(argv), 0)
            self.assertEqual(json.loads(out.getvalue())["phases"][0]["status"], "missing")

    def test_cli_record_accepts_json_findings_and_writes_certificate(self):
        finding = {"id": "F1", "severity": "minor", "blocking": False, "ref": "P1.1", "text": "advisory"}
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["readiness", "record", str(self.root), "P1", "--verdict", "ready_with_advisories",
                             "--audit", "knowledge/audit-p1-test", "--actor", "codex/gpt-6-astra/xhigh",
                             "--finding", json.dumps(finding)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(self.load().phases["P1"]["readiness"]["findings"], [finding])

    def test_readiness_stale_and_economy_warnings_have_negative_controls(self):
        ops.patch(self.root, "plan", {"settings": {"design_audit": "required"}})
        self.record()
        self.assertNotIn("readiness_stale", {i.code for i in check.check(self.load())})
        ops.patch(self.root, "P1.1", {"guidance": "only targeted tests; commit after each step " + "x" * 20000})
        codes = {i.code for i in check.check(self.load())}
        self.assertTrue({"readiness_stale", "execution_prompt_heavy", "execution_rules_conflict",
                         "execution_commit_instruction"} <= codes, codes)

    def test_whole_read_file_weight_and_empty_write_set_warn(self):
        p = self.load()
        before = {i.code for i in check.check(p)}
        self.assertNotIn("execution_prompt_heavy", before)
        self.assertNotIn("execution_write_set_empty", before)
        source = self.plans.parent / "large.txt"
        source.write_text("x" * 20000)
        p.items["P1.1"]["reads"] = [{"path": "large.txt", "required": False}]
        p.items["P1.1"]["task_files"] = []
        codes = {i.code for i in check.check(p)}
        self.assertTrue({"execution_prompt_heavy", "execution_write_set_empty"} <= codes, codes)
        source.write_text("small")
        self.assertNotIn("execution_prompt_heavy", {i.code for i in check.check(p)})
