from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from aicore.provider import models

from orch import catalog, contracts, launch
from orch.catalog import CLASS_RANK
from orch.bindings import BINDINGS, Cao, ClaudeOnly, Native, load_capabilities, prepare_common
from orch.cli import main
from orch.port import PortError

ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "fixtures" / "exec" / "v1" / "valid"
MODEL_CATALOG = ROOT / "fixtures" / "model-catalog" / "test.json"


def fixture(kind: str, name: str) -> dict:
    return json.loads((VALID / kind / f"{name}.json").read_text(encoding="utf-8"))


def roles() -> dict:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted((ROOT / "roles").glob("*.json"))}


def with_review(policy: dict, provider: str | None = None, required: bool = False) -> dict:
    policy = copy.deepcopy(policy)
    stage = {"id": "review", "kind": "review", "role": "reviewer", "required": required,
             "on_unavailable": "refuse" if required else "skip"}
    if provider:
        stage["provider"] = provider
    policy["stages"].append(stage)
    policy["review"].update(enabled=True, independent_provider=True)
    return policy


class PrepareCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out"
        self.catalog = catalog.Catalog.load(MODEL_CATALOG)

    def prepare(self, binding: str, provider: str, policy: str | dict = "solo", input_name: str = "plan-bound"):
        doc = fixture("run-policy", policy) if isinstance(policy, str) else policy
        engine = BINDINGS[binding](self.out, catalog=self.catalog)
        return engine.prepare(fixture("execution-input", input_name), doc, roles(), provider=provider)

    def refusal(self, *args, **kwargs) -> PortError:
        with self.assertRaises(PortError) as raised:
            self.prepare(*args, **kwargs)
        return raised.exception

    def assertValid(self, plan: dict) -> None:
        errors = [i for i in contracts.validate(plan, "launch-plan") if i.level == "error"]
        self.assertEqual(errors, [])


class NativeTests(PrepareCase):
    def test_claude_code_solo_plan_uses_mapped_model(self):
        plan = self.prepare("native", "claude-code")
        self.assertValid(plan)
        self.assertEqual(plan["binding"], "native")
        self.assertTrue(plan["dry_run"] and plan["run_id"].startswith("dry-"))
        (stage,) = plan["stages"]
        self.assertEqual((stage["model"], stage["effort"], stage["transport"]), ("m-mid", "high", "jsonl"))
        self.assertEqual(stage["argv"][stage["argv"].index("--model") + 1], "m-mid")
        self.assertTrue(Path(os.path.relpath(self.out / "prompt-primary.md")).samefile(self.out / "prompt-primary.md"))
        self.assertIn("# Executor", (self.out / "prompt-primary.md").read_text(encoding="utf-8"))

    def test_codex_takes_first_model_of_the_class(self):
        (stage,) = self.prepare("native", "codex")["stages"]
        self.assertEqual(stage["model"], "x-mid")
        self.assertEqual(stage["argv"][0], "codex")

    def test_scout_stage_uses_its_own_role_and_class(self):
        plan = self.prepare("native", "claude-code", "scout-solo")
        self.assertValid(plan)
        scout = next(stage for stage in plan["stages"] if stage["stage_id"] == "scout")
        self.assertEqual((scout["role"], scout["model"], scout["transport"]), ("scout", "m-small", "none"))
        self.assertEqual([s["stage_id"] for s in plan["stages"]], ["scout", "primary"])

    def test_adhoc_input_prepares(self):
        self.assertValid(self.prepare("native", "claude-code", input_name="adhoc"))

    def test_grok_model_set_unknown_is_unsupported(self):
        caps = load_capabilities()
        caps[("native", "grok")]["model"]["set"] = "unknown"
        engine = Native(self.out, catalog=self.catalog, capabilities=caps)
        with self.assertRaises(PortError) as raised:
            engine.prepare(fixture("execution-input", "plan-bound"), fixture("run-policy", "solo"), roles(), provider="grok")
        error = raised.exception
        self.assertEqual(error.code, "CAPABILITY_UNSUPPORTED")
        report = error.data["launch_plan"]
        self.assertValid(report)
        self.assertEqual(report["stages"], [])
        self.assertEqual([(r["stage_id"], r["capability"]) for r in report["refusals"]], [("primary", "model.set")])
        self.assertFalse(self.out.exists(), "a refused preparation writes nothing")

    def test_production_grok_prepares_jsonl_with_model_and_effort_under_landlock(self):
        plan = self.prepare("native", "grok")
        self.assertValid(plan)
        (stage,) = plan["stages"]
        self.assertEqual(stage["transport"], "jsonl")
        argv = stage["argv"]
        self.assertTrue(argv[1].endswith("/scripts/ro-run.py"))
        self.assertEqual(argv[2], "--rw")
        self.assertEqual(Path(argv[3]).resolve(), Path.cwd())
        self.assertEqual(argv[argv.index("--model") + 1], stage["model"])
        self.assertEqual(argv[argv.index("--effort") + 1], stage["effort"])

    def test_missing_mapping_is_a_refusal_not_a_guess(self):
        self.catalog = catalog.Catalog.load(MODEL_CATALOG.with_name("grok-only.json"))
        error = self.refusal("native", "claude-code")
        self.assertEqual(error.code, "CAPABILITY_UNSUPPORTED")
        self.assertIn("class_selectors", error.data["launch_plan"]["refusals"][0]["reason"])

    def test_unknown_capability_record_counts_as_unknown(self):
        engine = Native(self.out, catalog=self.catalog, capabilities={})
        with self.assertRaises(PortError) as raised:
            engine.prepare(fixture("execution-input", "plan-bound"), fixture("run-policy", "solo"), roles(),
                           provider="claude-code")
        self.assertEqual(raised.exception.code, "CAPABILITY_UNSUPPORTED")
        self.assertIn("no capability record", raised.exception.data["launch_plan"]["refusals"][0]["reason"])


class CaoTests(PrepareCase):
    def test_profile_has_frontmatter_and_task_block(self):
        plan = self.prepare("cao", "claude-code")
        self.assertValid(plan)
        (stage,) = plan["stages"]
        self.assertEqual((stage["transport"], stage["argv"][:3]), ("tui", ["cao", "launch", "--agents"]))
        text = (self.out / "profile-primary.md").read_text(encoding="utf-8")
        head, _, body = text[4:].partition("\n---\n")
        self.assertTrue(text.startswith("---\n"))
        front = dict(line.split(": ", 1) for line in head.splitlines())
        for key in ("name", "description", "provider"):
            self.assertIn(key, front)
        self.assertEqual(json.loads(front["provider"]), "claude_code")
        self.assertEqual(json.loads(front["model"]), "m-mid")
        self.assertEqual(json.loads(front["claudeConfig"]), {"effort": "high"})
        self.assertEqual(json.loads(front["name"]), stage["argv"][-1])
        self.assertIn("## Goal", body)

    def test_codex_profile_uses_codex_config(self):
        self.prepare("cao", "codex")
        text = (self.out / "profile-primary.md").read_text(encoding="utf-8")
        self.assertIn('provider: "codex"', text)
        self.assertIn('codexConfig: {"model_reasoning_effort": "high"}', text)
        self.assertNotIn("claudeConfig", text)


class ClaudeOnlyTests(PrepareCase):
    def test_prompt_without_model_or_argv(self):
        plan = self.prepare("claude-only", "claude-code")
        self.assertValid(plan)
        (stage,) = plan["stages"]
        self.assertEqual(stage["transport"], "prompt")
        for key in ("model", "effort", "argv"):
            self.assertNotIn(key, stage)
        self.assertIn("# Executor", (self.out / "prompt-primary.md").read_text(encoding="utf-8"))

    def test_other_provider_has_no_record(self):
        self.assertEqual(self.refusal("claude-only", "codex").code, "CAPABILITY_UNSUPPORTED")


class RefusalTests(PrepareCase):
    def test_primary_below_input_minimum(self):
        policy = fixture("run-policy", "solo")
        next(s for s in policy["stages"] if s["kind"] == "primary")["model_class"] = "economy"
        self.assertEqual(self.refusal("native", "claude-code", policy).code, "ROUTE_UNDERSHOOT")

    def test_an_unpinned_primary_follows_the_route_minimum_of_the_piece(self):
        engine = Native(self.out, catalog=self.catalog)
        policy, doc = fixture("run-policy", "solo"), fixture("execution-input", "plan-bound")
        self.assertIsNone(next(s for s in policy["stages"] if s["kind"] == "primary").get("model_class"))
        doc["route"]["minimum"]["class"] = "frontier"
        from orch import contracts
        doc["digest"] = contracts.canonical_digest(doc)
        doc["input_id"] = doc["input_id"].split("@")[0] + "@" + doc["digest"][:12]
        plan = engine.prepare(doc, policy, roles(), provider="claude-code")
        primary = next(stage for stage in plan["stages"] if stage["stage_id"] == "primary")
        self.assertEqual(primary["model"], "m-big")  # the frontier model of the test catalog

    def test_role_without_manifest(self):
        self.assertEqual(self.refusal("native", "claude-code", "frontend-bounded").code, "ROLE_UNKNOWN")

    def test_invalid_input_and_policy(self):
        engine = Native(self.out, catalog=self.catalog)
        policy, doc = fixture("run-policy", "solo"), fixture("execution-input", "plan-bound")
        with self.assertRaises(PortError) as raised:
            engine.prepare({**doc, "goal": "changed"}, policy, roles(), provider="claude-code")
        self.assertEqual(raised.exception.code, "INPUT_INVALID")
        self.assertTrue(raised.exception.data["issues"])
        with self.assertRaises(PortError) as raised:
            engine.prepare(doc, {**policy, "git_action": "none", "commit": {}}, roles(), provider="claude-code")
        self.assertEqual(raised.exception.code, "POLICY_INVALID")

    def test_optional_review_on_the_primary_provider_is_dropped(self):
        plan = self.prepare("native", "claude-code", with_review(fixture("run-policy", "solo")))
        self.assertValid(plan)
        self.assertEqual([s["stage_id"] for s in plan["stages"]], ["primary"])
        self.assertEqual([(r["stage_id"], r["capability"]) for r in plan["refusals"]], [("review", "independent_provider")])

    def test_review_on_another_provider_is_kept(self):
        plan = self.prepare("native", "claude-code", with_review(fixture("run-policy", "solo"), "codex"))
        self.assertEqual([(s["stage_id"], s["provider"]) for s in plan["stages"]],
                         [("primary", "claude-code"), ("review", "codex")])
        self.assertEqual(plan["refusals"], [])

    def test_required_review_on_the_primary_provider_refuses(self):
        error = self.refusal("native", "claude-code", with_review(fixture("run-policy", "solo"), required=True))
        self.assertEqual(error.code, "CAPABILITY_UNSUPPORTED")
        self.assertEqual(error.data["launch_plan"]["refusals"][0]["capability"], "independent_provider")

    def test_read_only_role_needs_enforcement(self):
        capabilities = copy.deepcopy(load_capabilities())
        capabilities[("native", "codex")]["restrictions"]["tools_native"] = "unknown"
        policy = with_review(fixture("run-policy", "solo"), "codex", required=True)
        with self.assertRaises(PortError) as raised:
            Native(self.out, catalog=self.catalog, capabilities=capabilities).prepare(
                fixture("execution-input", "plan-bound"), policy, roles(), provider="claude-code")
        self.assertEqual(raised.exception.data["launch_plan"]["refusals"][0]["capability"], "read_only_enforcement")

    def test_required_skills_need_a_delivery_mode(self):
        manifests = roles()
        manifests["executor"]["skills"] = [{"name": "demo-skill", "required": True, "why": "needed"}]
        capabilities = copy.deepcopy(load_capabilities())
        capabilities[("native", "claude-code")]["skill_delivery"]["mode"] = "unknown"
        with self.assertRaises(PortError) as raised:
            Native(self.out, catalog=self.catalog, capabilities=capabilities).prepare(
                fixture("execution-input", "plan-bound"), fixture("run-policy", "solo"), manifests,
                provider="claude-code")
        self.assertEqual(raised.exception.data["launch_plan"]["refusals"][0]["capability"], "skill_delivery")

    def test_no_provider_is_a_refusal(self):
        with self.assertRaises(PortError) as raised:
            Native(self.out, catalog=self.catalog).prepare(
                fixture("execution-input", "plan-bound"), fixture("run-policy", "solo"), roles())
        self.assertEqual(raised.exception.code, "INPUT_INVALID")

    def test_unknown_binding_name(self):
        with self.assertRaises(ValueError):
            prepare_common("nowhere", {}, {}, {}, {}, provider=None, catalog=self.catalog)


class PortTests(PrepareCase):
    def test_not_implemented_operations(self):
        engine = Native(self.out, catalog=self.catalog)
        for call in (lambda: engine.prepare({}, {}, {}, dry_run=False), lambda: engine.run({}),
                     lambda: next(engine.watch("r")), lambda: engine.cancel("r"), lambda: engine.resume("r"),
                     lambda: engine.results("r")):
            with self.subTest(call=call), self.assertRaises(PortError) as raised:
                call()
            self.assertEqual(raised.exception.code, "NOT_IMPLEMENTED")

    def test_bindings_implement_the_port(self):
        from orch.port import EnginePort
        for name, cls in BINDINGS.items():
            with self.subTest(binding=name):
                engine = cls(self.out, catalog=self.catalog)
                self.assertIsInstance(engine, EnginePort)
                self.assertEqual(engine.binding, name)
                self.assertTrue(engine.capabilities())
                self.assertTrue(all(record["binding"] == name for record in engine.capabilities()))
        self.assertEqual((Native.binding, Cao.binding, ClaudeOnly.binding), ("native", "cao", "claude-only"))

    def test_no_bare_in_any_argv(self):
        for binding in BINDINGS:
            for provider in ("claude-code", "codex"):
                with self.subTest(binding=binding, provider=provider):
                    try:
                        plan = self.prepare(binding, provider)
                    except PortError:
                        continue
                    for stage in plan["stages"]:
                        self.assertNotIn("--bare", stage.get("argv", []))


class CatalogTests(unittest.TestCase):
    def test_substitute(self):
        self.assertEqual(catalog.substitute(["a", "--m={model}", "{cwd}"], {"model": "x", "cwd": "."}), ["a", "--m=x", "."])
        with self.assertRaises(launch.LaunchError):
            catalog.substitute(["{effort}"], {})

    def test_resolve_model_and_effort(self):
        found = catalog.Catalog.load(MODEL_CATALOG)
        self.assertEqual(found.resolve_model("codex", "implementation"), "x-mid")
        self.assertEqual(found.resolve_effort("grok", "xhigh"), "xhigh")
        for call in (lambda: found.resolve_model("cursor", "economy"), lambda: found.resolve_effort("grok", "ultra")):
            with self.assertRaises(catalog.CatalogError) as raised:
                call()
            self.assertEqual(raised.exception.code, "CATALOG_UNKNOWN")

    def test_launch_entry(self):
        self.assertEqual(catalog.Catalog.load(MODEL_CATALOG).launch_entry("executor", "grok")["model_set"], "supported")

    def test_default_catalog_is_the_aicore_one(self):
        found = catalog.Catalog.load()
        for provider in ("claude-code", "codex", "grok"):
            for model_class in CLASS_RANK:
                self.assertTrue(found.resolve_model(provider, model_class))
            for effort in ("low", "medium", "high", "xhigh"):
                self.assertTrue(found.resolve_effort(provider, effort))

    def test_default_catalog_matches_the_packaged_file(self):
        packaged = models.load_model_catalog()
        found = catalog.Catalog.load()
        for provider in packaged.providers:
            for model_class in CLASS_RANK:
                self.assertEqual(found.resolve_model(provider.provider_id, model_class),
                                 provider.class_selectors[model_class][0])

    def test_unreadable_or_invalid_catalog_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory, "r.json")
            invalid.write_text("{}", encoding="utf-8")
            for path in (invalid, Path(directory, "missing.json")):
                with self.subTest(path=path.name), self.assertRaises(catalog.CatalogError) as raised:
                    catalog.Catalog.load(path)
                self.assertEqual(raised.exception.code, "MODEL_CATALOG_UNAVAILABLE")

    def test_removed_routing_discovery(self):
        for name in ("ROUTING_ENV", "find_routing", "load_routing", "_from_bridges", "BRIDGES_DIR", "UNAVAILABLE"):
            self.assertFalse(hasattr(catalog, name), name)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def arguments(self, directory: str, binding: str = "native", policy: str = "solo") -> list[str]:
        return ["prepare", "--binding", binding, "--provider", "claude-code", "--model-catalog", str(MODEL_CATALOG),
                "--input", str(VALID / "execution-input" / "plan-bound.json"),
                "--policy", str(VALID / "run-policy" / f"{policy}.json"), "--out", str(Path(directory, "out"))]

    def test_dry_run_prints_a_valid_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            code, out, _ = self.run_cli(*self.arguments(directory), "--dry-run")
            self.assertEqual(code, 0)
            plan = json.loads(out)
            self.assertEqual([i for i in contracts.validate(plan, "launch-plan") if i.level == "error"], [])
            self.assertTrue(Path(directory, "out", "prompt-primary.md").is_file())

    def test_without_dry_run_is_not_implemented(self):
        with tempfile.TemporaryDirectory() as directory:
            code, out, err = self.run_cli(*self.arguments(directory))
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("NOT_IMPLEMENTED:"))
            self.assertFalse(Path(directory, "out").exists())

    def test_refusal_prints_code_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            code, out, err = self.run_cli(*self.arguments(directory, policy="frontend-bounded"), "--dry-run")
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("ROLE_UNKNOWN:"))
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.arguments(directory)
            arguments[arguments.index("--provider") + 1] = "grok"
            caps = load_capabilities()
            caps[("native", "grok")]["model"]["set"] = "unknown"
            with mock.patch("orch.bindings.load_capabilities", return_value=caps):
                code, out, err = self.run_cli(*arguments, "--dry-run")
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("CAPABILITY_UNSUPPORTED:"))
            self.assertEqual(json.loads(out)["refusals"][0]["capability"], "model.set")

    def test_missing_model_catalog_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.arguments(directory, "claude-only")
            arguments[arguments.index("--model-catalog") + 1] = str(Path(directory, "missing.json"))
            code, _, err = self.run_cli(*arguments, "--dry-run")
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("MODEL_CATALOG_UNAVAILABLE:"))


if __name__ == "__main__":
    unittest.main()
