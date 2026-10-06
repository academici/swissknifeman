"""Check evidence for finish and unit accept (T6): Task check-evidence field contract and plan.settings.evidence."""
import copy
import io
import itertools
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import cli, lifecycle, ops, schema, store, units  # noqa: E402
from task.plan.model import PlanError  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evidence"
OPUS = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}
SONNET = {"provider": "claude-code", "model": "claude-sonnet-5-5", "effort": "high"}
DETAIL = {
    "summary": "s", "why": "w", "scope": {"include": ["x"]}, "deliverables": ["d"],
    "task_files": [{"path": "lib/**", "change": "any"}],
    "route": {"class": "frontier", "effort": "high"},
    "validation": [{"id": "V1", "cmd": "true", "expect": "exit 0", "kind": "acceptance"},
                   {"id": "V2", "cmd": "true", "expect": "exit 0", "kind": "impact"}],
}
UNIT = {"goal": "Piece", "files": ["lib/piece.py"], "route": {"class": "implementation", "effort": "high"},
        "mode": "delegate"}


def _cli(actor):
    return "/".join(actor[k] for k in ("provider", "model", "effort") if k in actor)


class EvidenceCase(unittest.TestCase):
    """Plan EVD (PLAN1): P1.1 and P1.2 (frontier/high, V1 acceptance, V2 impact) in one detailed phase."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        clock = itertools.count()

        def tick():
            n = next(clock)
            return f"2026-10-07T{n // 3600:02d}:{n // 60 % 60:02d}:{n % 60:02d}Z"

        patcher = mock.patch.object(store, "now", tick)
        patcher.start()
        self.addCleanup(patcher.stop)
        plans = Path(tmp.name) / "plans"
        plans.mkdir()
        plan = ops.new_plan("EVD", "Evidence", plans_root=plans, repository="r", owner="o", authoring=OPUS,
                            message="m", date="2026.10.07")
        self.root, self.repo = plan.root, plan.repo_root
        self.assertEqual(plan.plan["short_id"], "PLAN1")  # the fixtures name PLAN1 subjects
        ops.add_phase(plan, "One")
        ops.patch(plan, "P1", {"goal": "g"})
        ops.add_item(plan, "P1", "First")
        ops.add_item(plan, "P1", "Second")
        ops.patch(plan, "P1.1", copy.deepcopy(DETAIL))
        ops.patch(plan, "P1.2", copy.deepcopy(DETAIL))
        lifecycle.design_done(self.root, "P1", actor=OPUS)
        lifecycle.start(self.root, ["P1.1"], OPUS)

    def load(self):
        return store.load_plan(self.root)

    def tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def evidence(self, fixture, name=None, **changes):
        """Copy ``fixture`` (with top-level ``changes``; None deletes) into the plan; return its ``@plan/`` path."""
        doc = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
        for key, value in changes.items():
            if value is None:
                doc.pop(key, None)
            else:
                doc[key] = value
        target = self.root / "artifacts" / "evidence" / f"{name or fixture}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc), encoding="utf-8")
        return f"@plan/artifacts/evidence/{target.name}"

    def refused(self, code, call, *args, **kwargs):
        before = self.tree()
        with self.assertRaises(PlanError) as caught:
            call(self.root, *args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception)
        self.assertEqual(self.tree(), before, f"{code} refusal changed the plan directory")
        return caught.exception

    def require_evidence(self):
        plan_path = self.root / "plan.json"
        doc = json.loads(plan_path.read_text(encoding="utf-8"))
        doc.setdefault("settings", {})["evidence"] = "required"
        plan_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def result(self, item="P1.1"):
        return self.load().items[item]["result"]

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main([argv[0], str(self.root), *argv[1:]])
        return code, out.getvalue() + err.getvalue()


class FinishEvidenceTests(EvidenceCase):
    def test_command_evidence_records_its_exit_and_path(self):
        path = self.evidence("cmd-pass")
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": path})
        result = self.result()
        self.assertEqual(result["checks"], [{"id": "V1", "exit": 0, "at": result["checks"][0]["at"], "evidence": path}])
        self.assertEqual(result["evidence"], [path])
        self.assertEqual(self.load().items["P1.1"]["status"], "done")
        finish_event = [e for e in store.read_log(self.root) if e["type"] == "finish"][0]
        self.assertEqual(finish_event["data"]["checks"], {"V1": 0})
        self.assertNotIn("evidence", finish_event)

    def test_repository_relative_path_is_accepted(self):
        target = self.repo / "evidence" / "V1.json"
        target.parent.mkdir(parents=True)
        shutil.copy(FIXTURES / "cmd-pass.json", target)
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": "evidence/V1.json"})
        self.assertEqual(self.result()["checks"][0]["evidence"], "evidence/V1.json")

    def test_procedure_pass_is_exit_zero(self):
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": self.evidence("procedure-pass")})
        self.assertEqual(self.result()["checks"][0]["exit"], 0)

    def test_procedure_fail_is_exit_one_and_refuses_done(self):
        path = self.evidence("procedure-fail")
        self.refused("CHECKS_RED", lifecycle.finish, "P1.1", "done", evidence={"V1": path})
        lifecycle.finish(self.root, "P1.1", "done_with_deviations", evidence={"V1": path}, deviations=["V1 fails"])
        self.assertEqual(self.result()["checks"][0]["exit"], 1)

    def test_command_fail_refuses_done(self):
        self.refused("CHECKS_RED", lifecycle.finish, "P1.1", "done", evidence={"V1": self.evidence("cmd-fail")})

    def test_evidence_of_another_item_is_refused(self):
        path = self.evidence("cmd-pass", subject="PLAN1.P1.2")
        error = self.refused("EVIDENCE_SUBJECT", lifecycle.finish, "P1.1", "done", evidence={"V1": path})
        self.assertIn("PLAN1.P1.1", str(error))

    def test_evidence_of_another_check_is_refused(self):
        path = self.evidence("cmd-pass", check_id="V2")
        self.refused("EVIDENCE_SUBJECT", lifecycle.finish, "P1.1", "done", evidence={"V1": path})

    def test_procedure_with_an_exit_is_invalid(self):
        path = self.evidence("procedure-pass", exit=0)
        error = self.refused("EVIDENCE_INVALID", lifecycle.finish, "P1.1", "done", evidence={"V1": path})
        self.assertIn("exit", str(error))

    def test_structural_violations_are_invalid(self):
        cases = {
            "no-schema": {"$schema": None},
            "empty-schema": {"$schema": " "},
            "head": {"candidate": {"head": "ABC1234"}},
            "short-head": {"candidate": {"head": "abc12"}},
            "both": {"procedure": {"cmd": "true", "procedure": "look"}},
            "neither": {"procedure": {"cwd": "lib"}},
            "string-exit": {"exit": "0"},
            "bool-exit": {"exit": True},
            "cmd-verdict": {"verdict": "pass"},
            "no-producer": {"producer": None},
            "no-evidence-id": {"evidence_id": None},
        }
        for name, changes in cases.items():
            with self.subTest(name):
                doc = json.loads((FIXTURES / "cmd-pass.json").read_text(encoding="utf-8"))
                for key, value in changes.items():
                    if value is None:
                        doc.pop(key)
                    else:
                        doc[key] = value
                target = self.root / "artifacts" / "evidence" / f"{name}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(doc), encoding="utf-8")
                self.refused("EVIDENCE_INVALID", lifecycle.finish, "P1.1", "done",
                             evidence={"V1": f"@plan/artifacts/evidence/{name}.json"})
        manual = {"no-verdict": {"verdict": None}, "bad-verdict": {"verdict": "ok"}, "no-observation": {"observation": None}}
        for name, changes in manual.items():
            with self.subTest(name):
                path = self.evidence("procedure-pass", name=name, **changes)
                self.refused("EVIDENCE_INVALID", lifecycle.finish, "P1.1", "done", evidence={"V1": path})

    def test_any_schema_marker_and_contract_version_pass(self):
        """D19: Task checks the key fields only; a producer's own ``$schema`` and ``contract_version`` pass."""
        path = self.evidence("cmd-pass", name="foreign", **{"$schema": "urn:example:check-evidence:v9",
                                                            "contract_version": "x/v9"})
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": path})

    def test_missing_unreadable_or_escaping_files_are_invalid(self):
        (self.root / "artifacts").mkdir(exist_ok=True)
        (self.root / "artifacts" / "broken.json").write_text("{", encoding="utf-8")
        (self.root / "artifacts" / "list.json").write_text("[]", encoding="utf-8")
        for path in ("@plan/artifacts/none.json", "@plan/artifacts/broken.json", "@plan/artifacts/list.json",
                     "@plan/../outside.json", "/etc/hostname", "@plan/artifacts"):
            with self.subTest(path):
                self.refused("EVIDENCE_INVALID", lifecycle.finish, "P1.1", "done", evidence={"V1": path})

    def test_check_exit_that_disagrees_with_evidence_is_a_conflict(self):
        path = self.evidence("cmd-fail")
        error = self.refused("EVIDENCE_CONFLICT", lifecycle.finish, "P1.1", "done", checks={"V1": 0},
                             evidence={"V1": path})
        self.assertIn("V1=0", str(error))

    def test_check_exit_that_agrees_with_evidence_is_fine(self):
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0, "V2": 0}, evidence={"V1": self.evidence("cmd-pass")})
        checks = {c["id"]: c for c in self.result()["checks"]}
        self.assertIn("evidence", checks["V1"])
        self.assertNotIn("evidence", checks["V2"])

    def test_evidence_for_an_undeclared_check_is_unknown(self):
        path = self.evidence("cmd-pass", check_id="V9")
        self.refused("CHECK_UNKNOWN", lifecycle.finish, "P1.1", "done", evidence={"V9": path})

    def test_without_evidence_the_result_keeps_its_old_keys(self):
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0})
        result = self.result()
        self.assertNotIn("evidence", result)
        self.assertEqual(set(result["checks"][0]), {"id", "exit", "at"})


class RequiredEvidenceTests(EvidenceCase):
    def test_required_refuses_check_only_finish(self):
        self.require_evidence()
        error = self.refused("EVIDENCE_REQUIRED", lifecycle.finish, "P1.1", "done", checks={"V1": 0})
        self.assertIn("V1", str(error))
        self.refused("EVIDENCE_REQUIRED", lifecycle.finish, "P1.1", "done_with_deviations", checks={"V1": 0},
                     deviations=["d"])

    def test_required_accepts_evidence_for_every_acceptance_check(self):
        self.require_evidence()
        lifecycle.finish(self.root, "P1.1", "done", checks={"V2": 0}, evidence={"V1": self.evidence("cmd-pass")})
        self.assertEqual(self.load().items["P1.1"]["status"], "done")

    def test_required_does_not_touch_blocked(self):
        self.require_evidence()
        lifecycle.finish(self.root, "P1.1", "blocked", checks={"V1": 1}, escalation="needs a key")
        self.assertEqual(self.load().items["P1.1"]["status"], "blocked")

    def test_optional_setting_keeps_the_old_behaviour(self):
        plan_path = self.root / "plan.json"
        doc = json.loads(plan_path.read_text(encoding="utf-8"))
        doc.setdefault("settings", {})["evidence"] = "optional"
        plan_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lifecycle.finish(self.root, "P1.1", "done", checks={"V1": 0})
        self.assertEqual(self.load().items["P1.1"]["status"], "done")


class FinishAttemptEvidenceTests(EvidenceCase):
    def test_repeat_with_same_attempt_and_evidence_is_already_registered(self):
        path = self.evidence("cmd-pass")
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": path}, attempt_id="a1")
        lines = (self.root / "log.jsonl").read_text(encoding="utf-8")
        again = lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": path}, attempt_id="a1")
        self.assertTrue(again.already_registered)
        self.assertEqual((self.root / "log.jsonl").read_text(encoding="utf-8"), lines)

    def test_repeat_with_other_evidence_is_a_conflict(self):
        lifecycle.finish(self.root, "P1.1", "done", evidence={"V1": self.evidence("cmd-pass")}, attempt_id="a1")
        other = self.evidence("procedure-pass")
        self.refused("ATTEMPT_CONFLICT", lifecycle.finish, "P1.1", "done", evidence={"V1": other}, attempt_id="a1")


class UnitEvidenceTests(EvidenceCase):
    def setUp(self):
        super().setUp()
        self.unit_id = units.add_unit(self.root, "P1.1", "Piece", copy.deepcopy(UNIT))
        self.assertEqual(self.unit_id, "U1")  # the unit fixture names PLAN1.P1.1/U1
        units.dispatch(self.root, "P1.1", self.unit_id, _cli(SONNET))
        units.return_unit(self.root, "P1.1", self.unit_id, notes="done", changed=["lib/piece.py"])

    def unit(self):
        return self.load().units[f"P1.1/{self.unit_id}"]

    def test_accept_writes_outcome_evidence(self):
        path = self.evidence("unit-cmd-pass")
        self.assertFalse(units.accept(self.root, "P1.1", self.unit_id, notes="ok", evidence={"V1": path}))
        unit = self.unit()
        self.assertEqual(unit["status"], "accepted")
        self.assertEqual(unit["outcome"]["evidence"], [path])
        self.assertNotIn("checks", self.result())  # unit checks are never recorded as item exits

    def test_accept_refuses_item_evidence(self):
        path = self.evidence("cmd-pass")
        self.refused("EVIDENCE_SUBJECT", units.accept, "P1.1", self.unit_id, evidence={"V1": path})

    def test_accept_refuses_failing_evidence(self):
        path = self.evidence("unit-cmd-pass", name="unit-cmd-fail", exit=2)
        self.refused("CHECKS_RED", units.accept, "P1.1", self.unit_id, evidence={"V1": path})

    def test_repeat_with_same_attempt_and_evidence_is_already_registered(self):
        path = self.evidence("unit-cmd-pass")
        self.assertFalse(units.accept(self.root, "P1.1", self.unit_id, evidence={"V1": path}, attempt_id="u1"))
        lines = (self.root / "log.jsonl").read_text(encoding="utf-8")
        self.assertTrue(units.accept(self.root, "P1.1", self.unit_id, evidence={"V1": path}, attempt_id="u1"))
        self.assertEqual((self.root / "log.jsonl").read_text(encoding="utf-8"), lines)
        self.refused("ATTEMPT_CONFLICT", units.accept, "P1.1", self.unit_id, attempt_id="u1")

    def test_accept_without_evidence_keeps_the_old_outcome_keys(self):
        units.accept(self.root, "P1.1", self.unit_id, notes="ok")
        self.assertNotIn("evidence", self.unit()["outcome"])


class CliEvidenceTests(EvidenceCase):
    def test_finish_flag(self):
        path = self.evidence("cmd-pass")
        code, _ = self.run_cli("finish", "P1.1", "--status", "done", "--evidence", f"V1={path}")
        self.assertEqual(code, 0)
        self.assertEqual(self.result()["evidence"], [path])

    def test_finish_flag_refuses_a_repeated_check(self):
        path = self.evidence("cmd-pass")
        before = self.tree()
        code, _ = self.run_cli("finish", "P1.1", "--status", "done", "--evidence", f"V1={path}",
                               "--evidence", f"V1={path}")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.tree(), before)

    def test_unit_accept_flag(self):
        units.add_unit(self.root, "P1.1", "Piece", copy.deepcopy(UNIT))
        units.dispatch(self.root, "P1.1", "U1", _cli(SONNET))
        units.return_unit(self.root, "P1.1", "U1", notes="done")
        path = self.evidence("unit-cmd-pass")
        code, _ = self.run_cli("unit", "P1.1", "U1", "accept", "--evidence", f"V1={path}")
        self.assertEqual(code, 0)
        self.assertEqual(self.load().units["P1.1/U1"]["outcome"]["evidence"], [path])

    def test_evidence_belongs_to_unit_accept_only(self):
        units.add_unit(self.root, "P1.1", "Piece", copy.deepcopy(UNIT))
        units.dispatch(self.root, "P1.1", "U1", _cli(SONNET))
        code, _ = self.run_cli("unit", "P1.1", "U1", "return", "--evidence", f"V1={self.evidence('unit-cmd-pass')}")
        self.assertNotEqual(code, 0)


class FixtureTests(unittest.TestCase):
    def test_every_fixture_is_loadable_by_task(self):
        """Each fixture passes ``_load_evidence`` for its own subject and the check-evidence schema."""
        plan = mock.Mock(plan={"short_id": "PLAN1"})
        for fixture in sorted(FIXTURES.glob("*.json")):
            with self.subTest(fixture.name):
                doc = json.loads(fixture.read_text(encoding="utf-8"))
                self.assertEqual(schema.validate(doc, "check-evidence"), [])
                item_ref = doc["subject"].split(".", 1)[1]
                with mock.patch("task.plan.context._resolve", return_value=fixture):
                    code = lifecycle._load_evidence(plan, item_ref, doc["check_id"], f"@plan/{fixture.name}")
                expected = doc["exit"] if "exit" in doc else {"pass": 0, "fail": 1}[doc["verdict"]]
                self.assertEqual(code, expected)


if __name__ == "__main__":
    unittest.main()
