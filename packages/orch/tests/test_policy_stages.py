"""A run policy may name a stage the conductor does not run. A refusing required stage stops the run before any
role; any other such stage is skipped once. Dry-run reports the same reason."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from orch import contracts, policies
from orch.bindings import _order
from orch.conductor.policies import routing
from orch.preparation import effective_policy
from tests.test_conductor import GREEN, ConductorCase, executor_ok

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "configs" / "run-policies"
RUNS = ("full", "solo", "review-only", "scout-solo")
MESSAGE = ("frontend-bounded: stage bounded (role bounded-implementer) is not run by the conductor; "
           "choose another scenario or run the plan natively")


def pack(name: str) -> dict:
    return json.loads((PACKS / name / "policy.json").read_text(encoding="utf-8"))


class UnsupportedStageTests(unittest.TestCase):
    def test_conductor_roles_are_the_one_list(self):
        self.assertEqual(routing.CONDUCTOR_ROLES, (
            "deterministic", "scout", "context-scout", "executor", "reviewer", "triager", "registrar",
            "report-fixer", "researcher", "advisor"))

    def test_shipped_packs_the_conductor_runs_have_no_unsupported_stage(self):
        for name in RUNS:
            with self.subTest(name=name):
                self.assertEqual(routing.unsupported_stages(pack(name)), ([], []))

    def test_frontend_bounded_requires_a_role_the_conductor_does_not_run(self):
        required, optional = routing.unsupported_stages(pack("frontend-bounded"))
        self.assertEqual(required, [("bounded", "bounded-implementer")])
        self.assertEqual(optional, [])

    def test_a_required_stage_that_does_not_refuse_is_skipped(self):
        stage = {"id": "side", "role": "side-implementer", "required": True, "on_unavailable": "skip"}
        self.assertEqual(routing.unsupported_stages({"stages": [stage]}), ([], [("side", "side-implementer")]))
        stage["required"] = False
        stage["on_unavailable"] = "refuse"
        self.assertEqual(routing.unsupported_stages({"stages": [stage]}), ([], [("side", "side-implementer")]))
        stage["required"] = True
        self.assertEqual(routing.unsupported_stages({"stages": [stage]}), ([("side", "side-implementer")], []))


def _with_side(policy: dict, *, depends_on=None, primary_depends=None) -> dict:
    stages = [dict(stage) for stage in policy["stages"]]
    side = {"id": "side", "kind": "bounded", "role": "plan9-uninstalled-side-role", "model_class": "economy",
            "required": False, "on_unavailable": "skip"}
    if depends_on is not None:
        side["depends_on"] = depends_on
    if primary_depends is not None:
        for stage in stages:
            if stage["id"] == "primary":
                stage["depends_on"] = primary_depends
    stages.insert(1, side)
    return {**policy, "stages": stages}


class EffectivePolicyTests(unittest.TestCase):
    def test_a_skipped_predecessor_keeps_a_valid_order_and_the_original_policy(self):
        policy = _with_side(pack("solo"), depends_on=["context"], primary_depends=["side"])
        before = json.dumps(policy)
        self.assertEqual([issue for issue in contracts.validate(policy, "run-policy") if issue.level == "error"], [])
        self.assertEqual([stage["id"] for stage in _order(policy["stages"])],
                         ["context", "side", "primary", "checks", "registrar", "git"])
        projected = effective_policy(policy)
        self.assertEqual(json.dumps(policy), before)
        self.assertEqual([stage["id"] for stage in projected["stages"]],
                         ["context", "primary", "checks", "registrar", "git"])
        primary = next(stage for stage in projected["stages"] if stage["id"] == "primary")
        self.assertEqual(primary["depends_on"], ["context"])
        self.assertEqual([issue for issue in contracts.validate(projected, "run-policy") if issue.level == "error"], [])
        self.assertEqual([stage["id"] for stage in _order(projected["stages"])],
                         ["context", "primary", "checks", "registrar", "git"])

    def test_a_cycle_or_an_unknown_dependency_among_kept_stages_stays_invalid(self):
        cycled = pack("solo")
        stages = [dict(stage) for stage in cycled["stages"]]
        for stage in stages:
            if stage["id"] == "context":
                stage["depends_on"] = []
            elif stage["id"] == "primary":
                stage["depends_on"] = ["checks"]
            elif stage["id"] == "checks":
                stage["depends_on"] = ["primary"]
            elif stage["id"] == "registrar":
                stage["depends_on"] = ["checks"]
            elif stage["id"] == "git":
                stage["depends_on"] = ["registrar"]
        stages.append({"id": "side", "kind": "bounded", "role": "plan9-uninstalled-side-role",
                       "model_class": "economy", "required": False, "on_unavailable": "skip",
                       "depends_on": ["context"]})
        projected = effective_policy({**cycled, "stages": stages})
        self.assertNotIn("side", [stage["id"] for stage in projected["stages"]])
        self.assertIn("POLICY_DEPENDS", [issue.code for issue in contracts.validate(projected, "run-policy")
                                         if issue.level == "error"])
        unknown = _with_side(pack("solo"), depends_on=["missing"], primary_depends=["side"])
        projected = effective_policy(unknown)
        primary = next(stage for stage in projected["stages"] if stage["id"] == "primary")
        self.assertEqual(primary["depends_on"], ["missing"])
        self.assertIn("POLICY_DEPENDS", [issue.code for issue in contracts.validate(projected, "run-policy")
                                         if issue.level == "error"])


class PolicyStageRunTests(ConductorCase):
    def test_frontend_bounded_stops_before_any_role_and_a_supported_scenario_resumes(self):
        self.set_items({"W1": {"scenario": "frontend-bounded"}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "POLICY_STAGE_UNSUPPORTED")), err)
        self.assertIn(MESSAGE, self.state(err)["stop"]["message"])
        self.assertEqual((self.calls("executor"), self.calls("context-scout"), self.calls("reviewer")), (0, 0, 0))
        doc = self.source()
        doc["items"]["W1"]["scenario"] = "full"
        if doc["items"]["W1"].get("status") not in ("todo", "in_progress"):
            doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, resumed = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertEqual(self.calls("executor"), 1)

    def test_an_optional_unknown_stage_is_skipped_once_and_the_run_continues(self):
        self.set_items({"W1": {"scenario": "solo", "review_mode": "none"},
                        "W2": {"scenario": "solo", "review_mode": "none"}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")]})
        real = policies.load

        def load(policy_id, *args, **kwargs):
            found = real(policy_id, *args, **kwargs)
            stages = list(found.get("stages") or [])
            stages.append({"id": "side", "kind": "bounded", "role": "bounded-implementer", "required": False,
                           "on_unavailable": "skip", "model_class": "economy"})
            return {**found, "stages": stages}

        with mock.patch.object(policies, "load", load):
            code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        skipped = [line for line in self.lines(err) if line.get("reason_code") == "POLICY_STAGE_SKIPPED"]
        self.assertEqual(len(skipped), 1, err)
        self.assertIn("stage side (role bounded-implementer)", skipped[0]["message"])
        self.assertIn("skipped", skipped[0]["message"])
        self.assertTrue(self.state(err).get("policy_stage_skipped"))
        self.assertEqual(self.calls("executor"), 2)

    def test_a_skipped_stage_without_a_manifest_still_runs(self):
        """The conductor reloads the pack and binds a copy without the skipped stage, so a missing manifest does not stop the run."""
        parent = self.project.parent / "profiles"
        # required + on_unavailable skip is POLICY_INVALID (required stages must refuse). The two valid skips are
        # optional, whether they say skip or refuse.
        cases = (
            ("skip-optional", False, "skip"),
            ("skip-refuse", False, "refuse"),
        )
        for name, required, unavailable in cases:
            stage = {"id": "side", "kind": "bounded", "role": "plan9-uninstalled-side-role",
                     "model_class": "economy", "required": required, "on_unavailable": unavailable}
            policy = pack("solo")
            policy["policy_id"] = name
            policy["stages"] = [*policy["stages"], stage]
            folder = parent / name
            folder.mkdir(parents=True)
            (folder / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        self.write_config(extra=f'[orch.profiles]\ndirs = [{json.dumps(str(parent))}]\n')
        for name, _required, _unavailable in cases:
            with self.subTest(name=name):
                before = self.calls("executor")
                self.set_items({"W1": {"scenario": name, "review_mode": "none"}})
                self.script({"executor": [executor_ok("W1")]})
                code, _, err = self.run_items("W1", extra=("--no-batch",))
                self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
                skipped = [line for line in self.lines(err) if line.get("reason_code") == "POLICY_STAGE_SKIPPED"]
                self.assertEqual(len(skipped), 1, err)
                self.assertIn("stage side (role plan9-uninstalled-side-role)", skipped[0]["message"])
                self.assertEqual(self.calls("executor") - before, 1)
                self.assertNotIn("ROLE_UNKNOWN", err)
                self.assertNotIn("PREPARE_REFUSED", err)

    def test_a_skipped_predecessor_without_a_manifest_still_runs(self):
        parent = self.project.parent / "profiles-predecessor"
        policy = _with_side(pack("solo"), depends_on=["context"], primary_depends=["side"])
        policy["policy_id"] = "skip-predecessor"
        folder = parent / "skip-predecessor"
        folder.mkdir(parents=True)
        (folder / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        self.write_config(extra=f'[orch.profiles]\ndirs = [{json.dumps(str(parent))}]\n')
        self.set_items({"W1": {"scenario": "skip-predecessor", "review_mode": "none"}})
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        skipped = [line for line in self.lines(err) if line.get("reason_code") == "POLICY_STAGE_SKIPPED"]
        self.assertEqual(len(skipped), 1, err)
        self.assertIn("stage side (role plan9-uninstalled-side-role)", skipped[0]["message"])
        self.assertEqual(self.calls("executor"), 1)
        self.assertNotIn("ROLE_UNKNOWN", err)
        self.assertNotIn("PREPARE_REFUSED", err)
        self.assertNotIn("POLICY_INVALID", err)

    def test_a_refusing_required_stage_without_a_manifest_stops_before_prepare(self):
        parent = self.project.parent / "profiles-refuse"
        policy = pack("solo")
        policy["policy_id"] = "refuse-required"
        policy["stages"] = [*policy["stages"], {
            "id": "side", "kind": "bounded", "role": "plan9-uninstalled-side-role",
            "model_class": "economy", "required": True, "on_unavailable": "refuse"}]
        folder = parent / "refuse-required"
        folder.mkdir(parents=True)
        (folder / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
        self.write_config(extra=f'[orch.profiles]\ndirs = [{json.dumps(str(parent))}]\n')
        self.set_items({"W1": {"scenario": "refuse-required"}})
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "POLICY_STAGE_UNSUPPORTED")), err)
        self.assertEqual(self.calls("executor"), 0)
        self.assertNotIn("ROLE_UNKNOWN", err)
        self.assertNotIn("PREPARE_REFUSED", err)

    def test_dry_run_shows_the_frontend_bounded_refusal(self):
        code, out, err = self.conduct("run", "--plan", "T", "--items", "W1", "--dry-run", "--scenario",
                                      "frontend-bounded")
        self.assertEqual(code, 0, err)
        unavailable = json.loads(out)["unavailable"]
        self.assertIn("POLICY_STAGE_UNSUPPORTED", unavailable["bounded-implementer"])
        self.assertIn(MESSAGE, unavailable["bounded-implementer"])

    def test_dry_run_of_a_scenario_the_conductor_runs_is_not_a_stage_refusal(self):
        for name in RUNS:
            with self.subTest(name=name):
                code, out, err = self.conduct("run", "--plan", "T", "--items", "W1", "--dry-run", "--scenario", name)
                self.assertEqual(code, 0, err)
                self.assertNotIn("POLICY_STAGE_UNSUPPORTED", out)
                self.assertNotIn("POLICY_STAGE_SKIPPED", out)


if __name__ == "__main__":
    unittest.main()
