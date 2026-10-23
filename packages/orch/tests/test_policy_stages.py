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


class PureRuleTests(unittest.TestCase):
    """The rules of policies/ take their facts as arguments (P5.2): the probes and lookups are the caller's and asked
    only when a rule needs them."""

    ENTRY = {"model_class": "implementation", "effort": "high", "model_set": "supported", "transport": "text",
             "timeout_s": 5}

    def test_the_route_rules_take_values_step_by_step(self):
        cfg = {"provider": "codex", "argv": {"executor": ["fake", "{model}", "{effort}"]}}
        target = routing.route_target(role="executor", item_options={"stages": []}, conductor_cfg=cfg, override=None,
                                      reviewer=None)
        self.assertEqual((target["provider"], target["model"], target["effort"]), ("codex", None, None))
        chosen = routing.route_model(target, role="executor", entry=dict(self.ENTRY), claim={"route": {"effort": "xhigh"}},
                                     launch_plan={})
        self.assertEqual((chosen["model_class"], chosen["effort"], chosen["needs_model"]), ("implementation", "xhigh", True))
        planned = routing.route_model(target, role="executor", entry=dict(self.ENTRY), claim={},
                                      launch_plan={"stages": [{"role": "executor", "provider": "codex", "model": "p-1"}]})
        self.assertEqual((planned["model"], planned["needs_model"]), ("p-1", False))
        self.assertFalse(routing.builds_argv("executor", "xhigh", cfg))  # [orch.conductor.argv]: no launch catalog
        self.assertTrue(routing.builds_argv("executor", "high", {}))
        self.assertFalse(routing.builds_argv("executor", "warp", {}))  # refused by route, without the catalog
        found = routing.route(role="executor", item_options={"limits": {}}, chosen=dict(chosen, model="m-1"),
                              entry=dict(self.ENTRY), conductor_cfg=cfg, project=Path("/p"), launch_catalog=None,
                              access=None)
        self.assertEqual((found["provider"], found["model"], found["effort"], found["argv"]),
                         ("codex", "m-1", "xhigh", ["fake", "m-1", "xhigh"]))
        with self.assertRaises(routing.Stop) as caught:
            routing.route(role="executor", item_options={"limits": {}}, chosen=dict(chosen, effort="warp"),
                          entry=dict(self.ENTRY), conductor_cfg={}, project=Path("/p"), launch_catalog=None, access=None)
        self.assertEqual(caught.exception.code, "ROUTE_UNDERSHOOT")

    def test_route_minimum_and_acp_raise_their_stop(self):
        route = {"model_class": "economy", "effort": "high"}
        routing.route_minimum({}, route, "W1")
        with self.assertRaises(routing.Stop) as caught:
            routing.route_minimum({"class": "implementation"}, route, "W1")
        self.assertEqual(caught.exception.code, "ROUTE_UNDERSHOOT")
        self.assertIn("required by W1", caught.exception.message)
        routing.refuse_acp({"context-scout": {"transport": "acp", "provider": "grok"}})  # optional: only skipped
        with self.assertRaises(routing.Stop) as caught:
            routing.refuse_acp({"executor": {"transport": "acp", "provider": "grok"}})
        self.assertEqual(caught.exception.code, "TRANSPORT_UNSUPPORTED")
        self.assertIsNone(routing.provider_disabled(None, "codex"))

    def test_the_sandbox_rules_take_the_probe_results(self):
        from orch.conductor.policies import sandbox as sandbox_rules
        bash = {"provider": "claude-code", "argv": ["claude", "--tools", "Read,Bash", "-p"]}
        prefer = {"instructions": {"sandbox": "prefer"}}
        require = {"instructions": {"sandbox": "require"}}
        self.assertFalse(sandbox_rules.claude_confinement_required(prefer, bash))
        self.assertTrue(sandbox_rules.claude_confinement_required(require, bash))
        self.assertIsNone(sandbox_rules.claude_sandbox_problem(prefer, bash, probe=None, settings_listed=None))
        down = sandbox_rules.claude_sandbox_problem(require, bash, probe={"available": False, "reason": "no bwrap"},
                                                    settings_listed=None)
        self.assertEqual(down, "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the sandbox cannot start "
                               "(no bwrap)")
        self.assertIn("does not list --settings", sandbox_rules.claude_sandbox_problem(
            require, bash, probe={"available": True, "reason": None}, settings_listed=False))
        self.assertIsNone(sandbox_rules.claude_sandbox_problem(require, bash, probe={"available": True, "reason": None},
                                                               settings_listed=True))
        self.assertEqual(sandbox_rules.sandbox_args({"instructions": {"sandbox": "off"}}, "executor", bash,
                                                    extra_paths=[], network="none"), [])

    def test_the_cli_probe_reads_the_run_progress_only_for_an_unlisted_flag(self):
        from orch.conductor import engine
        from orch.conductor.infrastructure import cli_probe
        bare = engine.Conductor.__new__(engine.Conductor)  # no __init__: a facade without progress (pitfall 4)
        help_text = mock.Mock(stdout="usage: claude --listed")
        with mock.patch.dict(cli_probe._KNOWN, clear=True), \
                mock.patch.object(cli_probe.subprocess, "run", return_value=help_text) as ran:
            self.assertTrue(bare._knows(["/opt/claude", "-p"], ["--listed"]))
            noted = engine.Conductor.__new__(engine.Conductor)
            noted.progress = mock.Mock()
            for _ in range(2):  # the probe and the line are once per process
                self.assertFalse(noted._knows(["/opt/claude", "-p"], ["--missing"]))
        self.assertEqual(ran.call_count, 2)
        noted.progress.emit.assert_called_once_with(
            "info", reason_code="ISOLATION_PARTIAL",
            message="/opt/claude does not list --missing; roles are isolated by the environment only")

    def test_budget_admission_returns_its_stop(self):
        from orch.conductor.policies import budget
        facts = dict(item_ref="W1", run_id="R", item_tokens={"input": 90, "output": 10}, run_tokens={"input": 90},
                     limits={"tokens_hard_max": 100, "run_tokens_hard_max": 0}, item_limits={},
                     usage_incomplete=False, usage_unmetered=[])
        self.assertIsNone(budget.admission(scope="run", **facts))
        stop = budget.admission(scope="item", **facts)
        self.assertEqual((stop.code, stop.message.split(";")[0]), ("TOKEN_BUDGET",
                                                                  "W1 used 100 fresh tokens >= tokens_hard_max 100"))
        raises = [{"key": "tokens_hard_max", "to": 600, "item": "W2"}]
        self.assertEqual(budget.effective_limit("tokens_hard_max", limit_raises=raises, limits_run=None,
                                                item_options={"limits": {"tokens_hard_max": 5}}, item_ref="W1"), 5)
        self.assertEqual(budget.effective_limit("run_tokens_hard_max", limit_raises=raises,
                                                limits_run={"run_tokens_hard_max": {"value": 7}}, item_options={},
                                                item_ref="W1"), 7)


def _policy_frames() -> list:
    """The rules of ``policies/`` on the stack now (a probe or a catalog load made inside a rule shows here)."""
    import inspect
    return [frame.function for frame in inspect.stack()
            if frame.frame.f_globals.get("__name__", "").startswith("orch.conductor.policies.")]


class FactsBeforeRulesTests(unittest.TestCase):
    """The facade gathers the facts (the sandbox probe, the flags of the CLI, the launch and model catalogs) before a
    rule of ``policies/`` runs: no probe or catalog load happens inside a rule, and the calls keep their old conditions,
    count and order (review F1, P5.2)."""

    BASH = {"provider": "claude-code", "argv": ["claude", "--tools", "Read,Bash", "-p"]}
    UP, DOWN = {"available": True, "reason": None}, {"available": False, "reason": "fixture sandbox unavailable"}

    def owner(self):
        from orch.conductor import engine
        owner = engine.Conductor.__new__(engine.Conductor)  # no __init__ and no settings: the tolerant reads hold
        owner.settings, owner.conductor, owner.project, owner.progress = None, {}, Path.cwd(), mock.Mock()
        return owner

    def item(self, sandbox: str = "require", stages=None):
        from types import SimpleNamespace
        return SimpleNamespace(options={"instructions": {"sandbox": sandbox}, "limits": {}, "scope": {},
                                        "stages": stages or []}, claim={}, launch_plan={})

    def instrumented(self, result):
        seen = []

        def call(*args, **kwargs):
            seen.append(_policy_frames())
            return result(*args, **kwargs) if callable(result) else result
        return call, seen

    def test_the_claude_sandbox_facts_are_probed_outside_the_rule(self):
        from orch.conductor import engine
        cases = (("require", self.BASH, self.DOWN, True, 1, 0,
                  "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the sandbox cannot start "
                  "(fixture sandbox unavailable)"),
                 ("require", self.BASH, self.UP, False, 1, 1,
                  "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the claude CLI does not list --settings"),
                 ("require", self.BASH, self.UP, True, 1, 1, None),
                 ("prefer", self.BASH, self.DOWN, True, 0, 0, None),
                 ("off", self.BASH, self.DOWN, True, 0, 0, None),
                 ("require", {"provider": "claude-code", "argv": ["claude", "-p"]}, self.DOWN, True, 0, 0, None))
        for mode, route, probed, listed, probes, asks, expected in cases:
            with self.subTest(mode=mode, route=route["argv"], sandbox=probed["available"], listed=listed):
                probe, probe_frames = self.instrumented(probed)
                knows, knows_frames = self.instrumented(listed)
                with mock.patch.object(engine.sandbox, "probe", side_effect=probe), \
                        mock.patch.object(engine.Conductor, "_knows", side_effect=knows):
                    problem = self.owner()._claude_sandbox_problem(self.item(mode), route)
                self.assertEqual(problem, expected)
                self.assertEqual((len(probe_frames), len(knows_frames)), (probes, asks))
                self.assertFalse(any(probe_frames) or any(knows_frames), (probe_frames, knows_frames))

    def test_the_sandbox_args_facts_are_probed_outside_the_rule(self):
        from orch.conductor import engine
        cases = (("prefer", self.UP, True, 1, 1, True), ("prefer", self.UP, False, 1, 1, False),
                 ("prefer", self.DOWN, True, 1, 0, False), ("off", self.UP, True, 0, 0, False))
        for mode, probed, listed, probes, asks, confined in cases:
            with self.subTest(mode=mode, sandbox=probed["available"], listed=listed):
                probe, probe_frames = self.instrumented(probed)
                knows, knows_frames = self.instrumented(listed)
                owner = self.owner()
                owner._sandbox_noted = False
                with mock.patch.object(engine.sandbox, "probe", side_effect=probe), \
                        mock.patch.object(engine.Conductor, "_knows", side_effect=knows):
                    args = owner._sandbox_args(self.item(mode), "executor", self.BASH)
                self.assertEqual(args[:1], ["--settings"] if confined else [])
                self.assertEqual((len(probe_frames), len(knows_frames)), (probes, asks))
                self.assertFalse(any(probe_frames) or any(knows_frames), (probe_frames, knows_frames))

    def test_the_catalogs_are_loaded_outside_the_route_rules(self):
        from orch import launch
        from orch.conductor.application import route_service
        catalog = launch.load_catalog()
        load, load_frames = self.instrumented(lambda settings: catalog)
        owner = self.owner()
        named = self.item(stages=[{"role": "executor", "provider": "claude-code", "model": "fixture-model"}])
        with mock.patch.object(route_service.launch, "effective_catalog", side_effect=load):
            cold = owner._route(named, "executor")
            self.assertIs(owner._launch_cache, catalog)  # the cold cache is filled by the facade, once
            warm = owner._route(named, "executor")
        self.assertEqual(cold, warm)
        self.assertEqual((cold["provider"], cold["model"]), ("claude-code", "fixture-model"))
        self.assertEqual(len(load_frames), 1)
        self.assertFalse(any(load_frames), load_frames)
        resolve, resolve_frames = self.instrumented(lambda provider, model_class: "resolved-model")
        owner._catalog = mock.Mock(resolve_model=mock.Mock(side_effect=resolve))
        unnamed = self.item(stages=[{"role": "executor", "provider": "claude-code"}])
        self.assertEqual(owner._route(unnamed, "executor")["model"], "resolved-model")
        self.assertEqual(len(resolve_frames), 1)
        self.assertFalse(any(resolve_frames), resolve_frames)


if __name__ == "__main__":
    unittest.main()
