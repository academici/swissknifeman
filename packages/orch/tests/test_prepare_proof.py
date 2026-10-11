"""Preparation records what it decided and why: digests, configuration, decisions, policy decision and proof."""
from __future__ import annotations

import copy
import dataclasses
import json
import os
from pathlib import Path
import tempfile
import unittest

import aicore

import orch
from orch import catalog, contracts, settings
from orch.bindings import BINDINGS, load_capabilities
from orch.port import PortError, RunState
from orch.resume import verify_resume

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "fixtures" / "exec" / "v1" / "valid"
MODEL_CATALOG = ROOT / "fixtures" / "model-catalog" / "test.json"
NOW = "2026-10-11T00:00:00Z"
SKILL = {"name": "code-review", "digest": "sha256:" + "ab" * 32}


def fixture(kind: str, name: str) -> dict:
    return json.loads((VALID / kind / f"{name}.json").read_text(encoding="utf-8"))


def roles() -> dict:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted((ROOT / "roles").glob("*.json"))}


def with_stage(policy: dict, **stage) -> dict:
    policy = copy.deepcopy(policy)
    policy["stages"].append(stage)
    return policy


class ProofCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.catalog = catalog.Catalog.load(MODEL_CATALOG)
        self.settings = settings.defaults()
        self.input = fixture("execution-input", "plan-bound")
        self.policy = fixture("run-policy", "solo")
        self.caps = load_capabilities()

    def primary_on(self, provider: str) -> dict:
        policy = copy.deepcopy(self.policy)
        next(stage for stage in policy["stages"] if stage["kind"] == "primary")["provider"] = provider
        return policy

    def prepare(self, binding="native", provider="claude-code", **kwargs) -> dict:
        input_doc, policy = kwargs.pop("input_doc", self.input), kwargs.pop("policy", self.policy)
        kwargs.setdefault("now", NOW)
        kwargs.setdefault("settings", self.settings)
        kwargs.setdefault("capabilities", self.caps)
        kwargs.setdefault("catalog", self.catalog)
        engine = BINDINGS[binding](self.out, **kwargs)
        return engine.prepare(input_doc, policy, roles(), provider=provider)

    def refusal(self, **kwargs) -> PortError:
        with self.assertRaises(PortError) as raised:
            self.prepare(**kwargs)
        return raised.exception

    def stale_caps(self) -> dict:
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["fresh_until"] = "2026-01-01T00:00:00Z"
        return caps


class Determinism(ProofCase):
    def test_same_inputs_and_now_give_the_same_bytes(self):
        policy = with_stage(self.policy, id="scout", kind="scout", role="scout", required=False, on_unavailable="skip")
        first, second = self.prepare(policy=policy), self.prepare(policy=policy)
        self.assertEqual(json.dumps(first), json.dumps(second))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual([d["stage_id"] for d in first["decisions"]], [d["stage_id"] for d in second["decisions"]])

    def test_paths_are_relative_to_the_working_directory(self):
        # The working directory is an input of preparation: the same one gives the same bytes, and from any
        # directory the refs resolve to the same files.
        found = {}
        for name in ("", "a/b"):
            cwd = Path(self.tmp.name) / name
            cwd.mkdir(parents=True, exist_ok=True)
            before = Path.cwd()
            os.chdir(cwd)
            try:
                first, again = self.prepare(), self.prepare()
                found[name] = [Path(first["stages"][0][key]).resolve() for key in ("capability_ref", "prompt_ref")]
            finally:
                os.chdir(before)
            self.assertEqual(json.dumps(first), json.dumps(again))
        self.assertEqual(found[""], found["a/b"])

    def test_plan_is_valid_and_its_digest_is_last(self):
        plan = self.prepare()
        self.assertEqual([i for i in contracts.validate(plan, "launch-plan") if i.level == "error"], [])
        self.assertEqual(list(plan)[-1], "digest")
        self.assertEqual(plan["digest"], contracts.canonical_digest(plan))

    def test_modules_and_default_config(self):
        plan = self.prepare(settings=None)
        self.assertEqual(plan["modules"], [{"id": "aicore", "version": aicore.__version__},
                                           {"id": "orch", "version": orch.__version__}])
        self.assertEqual(plan["config"]["digest"], settings.digest(settings.defaults()))
        self.assertEqual(plan["digests"]["config"], plan["config"]["digest"])

    def test_every_input_has_its_digest(self):
        plan = self.prepare()
        digests = plan["digests"]
        self.assertEqual(digests["input"], self.input["digest"])
        self.assertEqual(digests["policy"], contracts.canonical_digest(self.policy))
        self.assertEqual(set(digests), {"input", "policy", "roles", "launch_catalog", "model_catalog", "capabilities",
                                        "config"})
        self.assertEqual(plan["policy_decision"]["policy_digest"], digests["policy"])

    def test_a_changed_input_changes_only_its_digest(self):
        base = self.prepare()["digests"]
        caps = copy.deepcopy(self.caps)
        caps[("native", "codex")]["cli"]["name"] = "codex-next"
        launch_doc = copy.deepcopy(self.catalog.launch)
        launch_doc["launch"]["executor"]["codex"]["timeout_s"] += 1
        other = copy.deepcopy(self.catalog.model_document())
        other["catalog_version"] = "9.9.9"
        for name, kwargs in (("capabilities", {"capabilities": caps}), ("launch_catalog", {"launch_catalog_doc": launch_doc}),
                             ("model_catalog", {"model_catalog_doc": other})):
            with self.subTest(name=name):
                changed = self._digests(**kwargs)
                self.assertEqual([key for key in base if base[key] != changed[key]], [name])
        policy = copy.deepcopy(self.policy)
        policy["description"] = "other"
        self.assertEqual([key for key, value in self._digests(policy=policy).items() if base[key] != value], ["policy"])

    def _digests(self, **kwargs) -> dict:
        from orch.bindings import prepare_common
        policy = kwargs.pop("policy", self.policy)
        caps = kwargs.pop("capabilities", self.caps)
        return prepare_common("native", self.input, policy, roles(), caps, provider="claude-code", catalog=self.catalog,
                              now=NOW, settings=self.settings, project=lambda *_: {"transport": "none"},
                              **kwargs)["digests"]

    def test_model_catalog_digest_is_the_same_from_the_file_or_the_parsed_catalog(self):
        from_file = self.prepare()["digests"]["model_catalog"]
        rebuilt = catalog.Catalog(self.catalog.models, self.catalog.launch)
        self.assertEqual(self.prepare(catalog=rebuilt)["digests"]["model_catalog"], from_file)

    def test_a_changed_engine_changes_the_config_digest(self):
        base = self.prepare()["config"]
        other = self.prepare(settings=dataclasses.replace(self.settings, engine="cao"))["config"]
        self.assertNotEqual(base["digest"], other["digest"])
        self.assertEqual(other["values"]["engine"], "cao")
        again = self.prepare(settings=dataclasses.replace(self.settings, work_source="elsewhere"))["config"]
        self.assertEqual(again["digest"], base["digest"])


class Decisions(ProofCase):
    def test_route_decision_lists_the_candidate_and_the_tie_break(self):
        decisions = self.prepare()["decisions"]
        route = next(d for d in decisions if d["kind"] == "route")
        self.assertEqual((route["stage_id"], route["chosen"], route["tie_break"]), ("primary", "claude-code/m-mid", "policy-order"))
        self.assertEqual(route["considered"], [{"candidate": "claude-code", "accepted": True, "reason_codes": []}])

    def test_a_stage_provider_is_the_only_candidate(self):
        policy = self.primary_on("codex")
        route = next(d for d in self.prepare(policy=policy)["decisions"] if d["kind"] == "route")
        self.assertEqual((route["chosen"], [c["candidate"] for c in route["considered"]]), ("codex/x-mid", ["codex"]))

    def test_binding_decision_defaults_to_an_explicit_flag(self):
        binding = next(d for d in self.prepare()["decisions"] if d["kind"] == "binding")
        self.assertEqual((binding["stage_id"], binding["chosen"]), ("*", "native"))
        self.assertEqual(binding["considered"][0]["reason_codes"], ["ENGINE_FROM_FLAG"])

    def test_binding_decision_of_the_caller_is_kept(self):
        _, decision = settings.select_engine(self.settings, "executor")
        plan = self.prepare(engine_decision=decision)
        self.assertEqual([d for d in plan["decisions"] if d["kind"] == "binding"], [decision])

    def test_condense_is_a_model_stage(self):
        policy = with_stage(self.policy, id="condense", kind="condense", role="context-scout", required=False,
                            model_class="economy", on_unavailable="skip")
        plan = self.prepare(policy=policy)
        stage = next(s for s in plan["stages"] if s["stage_id"] == "condense")
        self.assertEqual((stage["role"], stage["model"]), ("context-scout", "m-small"))
        route = next(d for d in plan["decisions"] if d["stage_id"] == "condense")
        self.assertEqual(route["chosen"], "claude-code/m-small")

    def test_a_refused_stage_has_no_chosen_candidate_and_the_engine_is_not_replaced(self):
        caps = copy.deepcopy(self.caps)
        del caps[("native", "codex")]
        error = self.refusal(provider="codex", capabilities=caps)
        refused = error.data["launch_plan"]
        self.assertEqual(error.code, "CAPABILITY_UNSUPPORTED")
        self.assertEqual(refused["binding"], "native")
        route = next(d for d in refused["decisions"] if d["kind"] == "route")
        self.assertEqual((route["chosen"], route["considered"][0]["accepted"], route["considered"][0]["reason_codes"]),
                         ("none", False, ["CAP_RECORD_MISSING"]))


class Refusals(ProofCase):
    def test_reason_codes_of_a_required_stage(self):
        cases = {
            "MODEL_SET_UNKNOWN": lambda c: c[("native", "claude-code")]["model"].update(set="unknown"),
            "MODEL_SET_UNSUPPORTED": lambda c: c[("native", "claude-code")]["model"].update(set="unsupported"),
            "CAP_RECORD_MISSING": lambda c: c.pop(("native", "claude-code")),
        }
        for code, change in cases.items():
            with self.subTest(code=code):
                caps = copy.deepcopy(self.caps)
                change(caps)
                refused = self.refusal(capabilities=caps).data["launch_plan"]
                self.assertEqual([item["reason_code"] for item in refused["refusals"]], [code])

    def test_read_only_role_without_enforcement(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["restrictions"].update(tools_native="unsupported", prompt_only=False)
        policy = with_stage(self.policy, id="scout", kind="scout", role="scout", required=False, on_unavailable="skip")
        plan = self.prepare(capabilities=caps, policy=policy)
        self.assertEqual([(r["stage_id"], r["reason_code"]) for r in plan["refusals"]],
                         [("scout", "READ_ONLY_UNENFORCEABLE")])
        self.assertEqual(plan["policy_decision"]["decision"], "allow")

    def test_independent_provider(self):
        policy = with_stage(self.policy, id="review", kind="review", role="reviewer", required=False,
                            on_unavailable="skip")
        policy["review"].update(enabled=True, independent_provider=True)
        plan = self.prepare(policy=policy)
        self.assertEqual([(r["stage_id"], r["reason_code"]) for r in plan["refusals"]],
                         [("review", "INDEPENDENT_PROVIDER")])
        self.assertEqual(plan["policy_decision"], {"decision": "allow", "reason_codes": [],
                                                   "policy_digest": plan["digests"]["policy"]})

    def test_skill_delivery_unavailable(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "codex")]["skill_delivery"]["mode"] = "unsupported"
        manifests = roles()
        manifests["reviewer"]["skills"] = [{"name": "code-review", "required": True, "why": "test"}]
        policy = with_stage(self.policy, id="review", kind="review", role="reviewer", required=False,
                            on_unavailable="skip", provider="codex")
        policy["review"].update(enabled=True, independent_provider=True)
        engine = BINDINGS["native"](self.out, catalog=self.catalog, capabilities=caps, settings=self.settings, now=NOW)
        plan = engine.prepare(self.input, policy, manifests, provider="claude-code")
        self.assertEqual([r["reason_code"] for r in plan["refusals"]], ["SKILL_DELIVERY_UNAVAILABLE"])

    def test_catalog_unknown(self):
        policy = copy.deepcopy(self.policy)
        next(stage for stage in policy["stages"] if stage["kind"] == "primary")["effort"] = "max"
        refused = self.refusal(policy=policy).data["launch_plan"]
        self.assertEqual([(r["capability"], r["reason_code"]) for r in refused["refusals"]],
                         [("effort.set", "CATALOG_UNKNOWN")])

    def test_launch_catalog_refusal_keeps_its_own_code(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "grok")]["model"]["set"] = "supported"
        refused = self.refusal(provider="grok", capabilities=caps, policy=self.primary_on("grok")).data["launch_plan"]
        self.assertEqual([r["reason_code"] for r in refused["refusals"]], ["LAUNCH_MODEL_UNSETTABLE"])

    def test_refusal_chain_follows_depends_on(self):
        caps = copy.deepcopy(self.caps)
        record = caps[("native", "claude-code")]
        record["model"]["set"] = "unknown"
        record["stream"] = "unsupported"
        record["depends_on"] = ["stream", "model.observe", "cancel", "missing.thing"]
        (item,) = self.refusal(capabilities=caps).data["launch_plan"]["refusals"]
        self.assertEqual(item["reason_code"], "MODEL_SET_UNKNOWN")
        self.assertEqual(item["chain"], [
            {"capability": "model.set", "reason": "model selection is unknown; the route is not guaranteed"},
            {"capability": "stream", "reason": "stream is unsupported"},
            {"capability": "missing.thing", "reason": "missing.thing is not recorded"}])

    def test_refusal_chain_without_dependencies_is_the_requested_capability(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["model"]["set"] = "unknown"
        (item,) = self.refusal(capabilities=caps).data["launch_plan"]["refusals"]
        self.assertEqual([link["capability"] for link in item["chain"]], ["model.set"])

    def test_required_refusal_refuses_the_policy(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["model"]["set"] = "unknown"
        plan = self.refusal(capabilities=caps).data["launch_plan"]
        self.assertEqual(plan["policy_decision"]["decision"], "refuse")
        self.assertEqual(plan["policy_decision"]["reason_codes"], ["MODEL_SET_UNKNOWN"])
        self.assertEqual(plan["digest"], contracts.canonical_digest(plan))


class Freshness(ProofCase):
    def test_a_stale_record_warns_and_is_marked(self):
        plan = self.prepare(capabilities=self.stale_caps())
        self.assertEqual([w["code"] for w in plan["proof"]["warnings"]], ["CAPABILITY_STALE"])
        (entry,) = plan["proof"]["capabilities"]
        self.assertEqual((entry["binding"], entry["provider"], entry["stale"]), ("native", "claude-code", True))
        self.assertEqual(entry["fresh_until"], "2026-01-01T00:00:00Z")
        route = next(d for d in plan["decisions"] if d["kind"] == "route")
        self.assertEqual((route["considered"][0]["accepted"], route["considered"][0]["reason_codes"]),
                         (True, ["CAPABILITY_STALE"]))

    def test_a_fresh_record_has_no_warning(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["fresh_until"] = "2027-01-01T00:00:00Z"
        plan = self.prepare(capabilities=caps)
        self.assertEqual(plan["proof"]["warnings"], [])
        self.assertFalse(plan["proof"]["capabilities"][0]["stale"])

    def test_a_stale_record_is_refused_when_configured(self):
        refuse = dataclasses.replace(self.settings, capabilities_stale="refuse")
        error = self.refusal(capabilities=self.stale_caps(), settings=refuse)
        refused = error.data["launch_plan"]
        self.assertEqual([r["reason_code"] for r in refused["refusals"]], ["CAPABILITY_STALE"])
        self.assertEqual(refused["stages"], [])
        self.assertTrue(refused["proof"]["capabilities"][0]["stale"])
        self.assertEqual(refused["policy_decision"]["reason_codes"], ["CAPABILITY_STALE"])

    def test_a_fraction_of_a_second_counts(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["fresh_until"] = "2026-10-11T12:00:00.100Z"
        self.assertEqual(self.prepare(capabilities=caps, now="2026-10-11T12:00:00.050Z")["proof"]["warnings"], [])
        self.assertEqual(len(self.prepare(capabilities=caps, now="2026-10-11T12:00:00.900Z")["proof"]["warnings"]), 1)
        refuse = dataclasses.replace(self.settings, capabilities_stale="refuse")
        error = self.refusal(capabilities=caps, settings=refuse, now="2026-10-11T12:00:00.900Z")
        self.assertEqual([r["reason_code"] for r in error.data["launch_plan"]["refusals"]], ["CAPABILITY_STALE"])

    def test_staleness_follows_now(self):
        caps = copy.deepcopy(self.caps)
        caps[("native", "claude-code")]["fresh_until"] = "2026-10-11T12:00:00Z"
        self.assertEqual(self.prepare(capabilities=caps, now="2026-10-11T11:59:59Z")["proof"]["warnings"], [])
        self.assertEqual(len(self.prepare(capabilities=caps, now="2026-10-11T12:00:01Z")["proof"]["warnings"]), 1)

    def test_proof_names_the_source_and_when_it_was_observed(self):
        (entry,) = self.prepare()["proof"]["capabilities"]
        self.assertEqual((entry["source"], entry["observed_at"], entry["stale"]),
                         ("declared", "2026-10-07T10:20:25Z", False))


class Submission(ProofCase):
    def test_submission_id_is_recorded(self):
        self.assertEqual(self.prepare(submission_id="sub-1")["submission_id"], "sub-1")
        self.assertNotIn("submission_id", self.prepare())

    def test_submission_id_equal_to_the_run_id_is_refused(self):
        run_id = "dry-" + self.input["digest"][:12]
        error = self.refusal(submission_id=run_id)
        self.assertEqual(error.code, "INPUT_INVALID")
        self.assertIn("KEY_REUSED", [issue["code"] for issue in error.data["issues"]])


class Skills(ProofCase):
    def test_skills_reach_the_delivery_of_the_role(self):
        (stage,) = self.prepare(skills={"executor": [SKILL]})["stages"]
        self.assertEqual(stage["delivery"]["skills"], [SKILL])

    def test_skills_of_the_manifest_role_id_serve_an_aliased_role(self):
        policy = with_stage(self.policy, id="scout", kind="scout", role="scout", required=False, on_unavailable="skip")
        plan = self.prepare(policy=policy, skills={"context-scout": [SKILL]})
        scout = next(s for s in plan["stages"] if s["stage_id"] == "scout")
        self.assertEqual(scout["delivery"]["skills"], [SKILL])
        self.assertNotIn("skills", next(s for s in plan["stages"] if s["stage_id"] == "primary")["delivery"])

    def test_a_skill_without_a_digest_is_invalid(self):
        error = self.refusal(skills={"executor": [{"name": "code-review"}]})
        self.assertEqual(error.code, "INPUT_INVALID")

    def test_an_empty_list_of_the_manifest_role_does_not_fall_through(self):
        policy = with_stage(self.policy, id="scout", kind="scout", role="scout", required=False, on_unavailable="skip")
        plan = self.prepare(policy=policy, skills={"context-scout": [], "scout": [SKILL]})
        scout = next(s for s in plan["stages"] if s["stage_id"] == "scout")
        self.assertNotIn("skills", scout["delivery"])

    def test_malformed_skills_are_input_invalid(self):
        for skills in ([], {"executor": SKILL}, {"executor": [1]}, {"executor": ["x"]}, {1: []}):
            with self.subTest(skills=skills):
                self.assertEqual(self.refusal(skills=skills).code, "INPUT_INVALID")

    def test_skills_change_the_plan_digest(self):
        self.assertNotEqual(self.prepare()["digest"], self.prepare(skills={"executor": [SKILL]})["digest"])


class Resume(ProofCase):
    def current(self, plan: dict) -> dict:
        digests = plan["digests"]
        return {"input_digest": digests["input"], "policy_digest": digests["policy"],
                "roles_digest": digests["roles"], "config_digest": digests["config"], "binding": plan["binding"]}

    def test_nothing_drifted(self):
        plan = self.prepare()
        self.assertEqual(verify_resume(plan, **self.current(plan)), [])

    def test_each_kind_of_drift_is_named(self):
        plan = self.prepare()
        for name, key in (("input", "input_digest"), ("policy", "policy_digest"), ("roles", "roles_digest"),
                          ("config", "config_digest"), ("binding", "binding")):
            with self.subTest(drift=name):
                current = self.current(plan)
                current[key] = "cao" if name == "binding" else "0" * 64
                self.assertEqual(verify_resume(plan, **current), [name])

    def test_drifts_come_in_a_fixed_order(self):
        plan = self.prepare()
        current = {"input_digest": "0" * 64, "policy_digest": "1" * 64, "roles_digest": "2" * 64,
                   "config_digest": "3" * 64, "binding": "cao"}
        self.assertEqual(verify_resume(plan, **current), ["input", "policy", "roles", "config", "binding"])

    def test_a_plan_that_recorded_nothing_has_drifted(self):
        plan = self.prepare()
        current = self.current(plan)
        for key in ("digests", "binding"):
            plan.pop(key)
        self.assertEqual(verify_resume(plan, **current), ["input", "policy", "roles", "config", "binding"])


class StageResult(unittest.TestCase):
    def result(self, **extra) -> dict:
        state = RunState("run-1")
        base = {"contract_version": "exec/v1", "run_id": "run-1", "stage_id": "primary", "attempt": 1,
                "ts": "2026-10-11T00:00:00Z"}
        for seq, kind in enumerate(("started", "completed")):
            state.apply({"$schema": contracts.URN_PREFIX + "run-event:v1", **base, "seq": seq, "kind": kind})
        return state.stage_result("primary", role="executor", requested_route={"class": "implementation", "effort": "high"},
                                  input_digest="0" * 64, instructions_digest="1" * 64, **extra)

    def test_default_result_has_none_of_the_new_fields(self):
        result = self.result()
        for key in ("skills", "modules", "attempt_id", "owner_epoch"):
            self.assertNotIn(key, result)

    def test_skills_modules_attempt_and_epoch_are_carried(self):
        modules = [{"id": "orch", "version": orch.__version__}]
        result = self.result(skills=[SKILL], modules=modules, attempt_id="att-1", owner_epoch=2)
        self.assertEqual((result["skills"], result["modules"], result["attempt_id"], result["owner_epoch"]),
                         ([SKILL], modules, "att-1", 2))
        self.assertEqual([i for i in contracts.validate(result, "stage-result") if i.level == "error"], [])

    def test_the_result_does_not_alias_the_arguments(self):
        skills = [dict(SKILL)]
        result = self.result(skills=skills)
        skills[0]["name"] = "other"
        self.assertEqual(result["skills"], [SKILL])

    def test_invalid_skill_ref_is_refused(self):
        with self.assertRaises(PortError) as raised:
            self.result(skills=[{"name": "x"}])
        self.assertEqual(raised.exception.code, "INPUT_INVALID")


if __name__ == "__main__":
    unittest.main()
