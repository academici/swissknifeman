"""The closed documents of the conductor (``schemas/conductor/v1``) and its pure parts: fixtures valid and invalid,
the merge of the run-option layers, selectors, the triage check, the triager role, the conductor settings and the
doctor's gitignore check."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from aicore.config import ConfigError

from orch import contracts, policies, render, settings
from orch.cli import doctor_checks, main
from orch.conductor import contract, options, prompts
from orch.conductor.infrastructure.files import runs_root

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "conductor" / "v1"


class FixtureTests(unittest.TestCase):
    def test_every_kind_has_valid_and_invalid_fixtures(self):
        for category in ("valid", "invalid"):
            self.assertEqual(sorted(path.name for path in (FIXTURES / category).iterdir()), sorted(contract.KINDS))

    def test_valid_fixtures_pass_and_invalid_ones_fail(self):
        for path in sorted(FIXTURES.glob("*/*/*.json")):
            category, kind = path.parts[-3], path.parts[-2]
            with self.subTest(fixture=path.relative_to(FIXTURES).as_posix()):
                issues = contract.problems(json.loads(path.read_text(encoding="utf-8")), kind)
                self.assertEqual(bool(issues), category == "invalid", issues)

    def test_json_block_reads_a_json_fence_with_trailing_blanks_and_the_json_write_set_form(self):
        for fence in ("```json\n", "```json \n", "```json\t\n", "```json  \n"):
            with self.subTest(fence=fence):
                self.assertEqual(prompts.json_block(f"x\n{fence}{{\"a\": 1}}\n```\n", "stage-report"), ({"a": 1}, None))
        text = 'x\n```json write-set\n{"paths": [], "tests": []}\n```\n```json\n{"b": 2}\n```\n'
        self.assertEqual(prompts.write_set_block(text)[0], {"paths": [], "tests": []})
        self.assertEqual(prompts.json_block(text, "stage-report"), ({"b": 2}, None))
        self.assertEqual(prompts.write_set_block("```write-set\n{\"paths\": [], \"tests\": []}\n```\n")[1], None)

    def test_the_validate_command_knows_the_conductor_kinds(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["validate", "run-options", str(FIXTURES / "valid/run-options/full.json")])
        self.assertEqual((code, json.loads(out.getvalue())), (0, {"valid": True}))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = main(["validate", "stage-report", str(FIXTURES / "invalid/stage-report/no-status.json"), "--quiet"])
        self.assertEqual(code, 1)

    def test_the_schema_profile_stays_inside_the_planner_profile(self):
        # the planner keeps a copy of run-options; its profile has numeric bounds but no patternProperties
        text = (ROOT / "schemas/conductor/v1/run-options.schema.json").read_text(encoding="utf-8")
        for keyword in ('"patternProperties"', '"propertyNames"'):
            self.assertNotIn(keyword, text)


class OptionsTests(unittest.TestCase):
    def policy(self, name="full") -> dict:
        return policies.load(name, settings.defaults(), warn=lambda message: None)

    def test_layers_merge_from_the_general_to_the_specific(self):
        config = {"reviewer": "grok/grok-4.7/high", "rules": ["global rule"], "on_blocked": "stop",
                  "limits": {"tokens_max": 0, "check_timeout_s": 1800}}
        layers = [{"source": "phase:P1", "options": {"rules": ["phase rule", "global rule"],
                                                     "limits": {"tokens_max": 1000},
                                                     "stages": [{"role": "executor", "model": "claude-opus-5-5"}],
                                                     "skills": [{"role": "reviewer", "names": ["a"]}]}},
                  {"source": "item:P1.2", "options": {"reviewer": "codex/gpt-5.6/high",
                                                      "stages": [{"role": "executor", "model_class": "frontier"}],
                                                      "skills": [{"role": "reviewer", "names": ["b"]}],
                                                      "on_blocked": "report"}}]
        merged, sources = options.effective(config, self.policy(), layers)
        self.assertEqual(merged["rules"], ["global rule", "phase rule"])
        self.assertEqual(merged["limits"]["tokens_max"], 1000)
        self.assertEqual(merged["limits"]["review_rounds"], 2)  # from the pack
        self.assertEqual(merged["limits"]["retries"], 2)  # retries_budget of full
        self.assertEqual(options.stage_route(merged, "executor"), {"role": "executor", "model_class": "frontier"})
        self.assertEqual(options.stage_route(merged, "context-scout")["model_class"], "economy")
        self.assertEqual(options.stage_route(merged, "triager")["model_class"], "implementation")
        self.assertEqual(merged["skills"], {"reviewer": ["b"]})
        self.assertEqual((merged["reviewer"], merged["on_blocked"]), ("codex/gpt-5.6/high", "report"))
        self.assertEqual((sources["reviewer"], sources["limits.tokens_max"], sources["limits.review_rounds"]),
                         ("item:P1.2", "phase:P1", "policy:full"))

    def test_a_layer_outside_the_contract_or_its_bounds_is_refused(self):
        for layer, words in (({"limits": {"review_rounds": 6}}, "review_rounds"), ({"bogus": 1}, "bogus"),
                             ({"reviewer": "nope"}, "reviewer")):
            with self.subTest(layer=layer), self.assertRaises(options.OptionsError) as caught:
                options.effective({}, self.policy(), [{"source": "item:P1.1", "options": layer}])
            self.assertEqual(caught.exception.code, "OPTIONS_INVALID")
            self.assertIn("item:P1.1", caught.exception.message)
            self.assertIn(words, caught.exception.message)

    def test_sandbox_options_default_to_prefer_and_are_checked(self):
        merged, _ = options.effective({}, self.policy(), [])
        self.assertEqual((merged["instructions"]["sandbox"], merged["instructions"]["sandbox_domains"]), ("prefer", []))
        layer = {"instructions": {"sandbox": "require", "sandbox_domains": ["pypi.org", "*.example.com"]}}
        merged, sources = options.effective({}, self.policy(), [{"source": "invocation:--options", "options": layer,
                                                                  "trusted": True}])
        self.assertEqual(merged["instructions"]["sandbox"], "require")
        self.assertEqual(sources["instructions.sandbox_domains"], "invocation:--options")
        with self.assertRaises(options.OptionsError) as caught:  # a plan item may not open the network
            options.effective({}, self.policy(), [{"source": "item:P1.6", "options": layer}])
        self.assertEqual(caught.exception.code, "OPTIONS_UNTRUSTED")
        for bad, words in (({"sandbox": "always"}, "sandbox"), ({"sandbox_domains": ["http://x.org/y"]}, "sandbox_domains"),
                           ({"sandbox_domains": ["a.org", "a.org"]}, "sandbox_domains")):
            with self.subTest(bad=bad), self.assertRaises(options.OptionsError) as caught:
                options.effective({}, self.policy(), [{"source": "item:P1.6", "options": {"instructions": bad}}])
            self.assertEqual(caught.exception.code, "OPTIONS_INVALID")
            self.assertIn(words, caught.exception.message)

    def test_provider_failure_options_merge_by_class_and_the_routes_are_replaced_as_a_list(self):
        merged, _ = options.effective({}, self.policy(), [])
        self.assertEqual((merged["on_error"], merged["limits"]["provider_wait_max_s"]), ({}, 900))
        self.assertEqual(merged["fallback_routes"], [{"role": "reviewer", "provider": "claude-code",
                                                      "model_class": "frontier", "effort": "high"}])  # the default
        route = {"role": "executor", "provider": "codex", "model_class": "implementation"}
        layers = [{"source": "phase:P2", "options": {"on_error": {"quota": {"action": "stop"}, "unknown": {"action": "retry"}},
                                                     "fallback_routes": [route, dict(route, role="reviewer")]}},
                  {"source": "item:P2.5", "options": {"on_error": {"quota": {"action": "fallback_route", "max": 1}},
                                                      "fallback_routes": [dict(route, effort="high")],
                                                      "limits": {"provider_wait_max_s": 60}}}]
        merged, sources = options.effective({}, self.policy(), layers)
        self.assertEqual(merged["on_error"], {"quota": {"action": "fallback_route", "max": 1},
                                              "unknown": {"action": "retry"}})
        self.assertEqual(merged["fallback_routes"], [dict(route, effort="high")])
        self.assertEqual((merged["limits"]["provider_wait_max_s"], sources["on_error.unknown"], sources["fallback_routes"]),
                         (60, "phase:P2", "item:P2.5"))
        merged, _ = options.effective({}, self.policy(), layers + [{"source": "item:x", "options": {"fallback_routes": []}}])
        self.assertEqual(merged["fallback_routes"], [])  # an empty list switches the routes of the layers below off
        with self.assertRaises(options.OptionsError) as caught:
            options.effective({}, self.policy(), [{"source": "item:P2.5", "options": {"limits": {"provider_wait_max_s": -1}}}])
        self.assertIn("provider_wait_max_s", caught.exception.message)

    def test_selectors(self):
        self.assertEqual(options.parse_selector("grok/grok-4.7/500k/high"),
                         {"provider": "grok", "model": "grok-4.7", "context": "500k", "effort": "high"})
        self.assertEqual(options.parse_selector("codex/gpt-5.6"), {"provider": "codex", "model": "gpt-5.6"})
        self.assertEqual(options.parse_actor("orch/conductor"), {"provider": "orch", "model": "conductor"})
        for text in ("grok", "grok/", "Grok/x", "grok/x/huge"):
            with self.subTest(text=text), self.assertRaises(options.OptionsError):
                options.parse_selector(text)

    def test_policy_layer_of_scout_solo_uses_the_role_alias(self):
        layer = options.policy_layer(self.policy("scout-solo"))
        self.assertEqual(layer["stages"][0], {"role": "context-scout", "model_class": "economy"})
        self.assertEqual(layer["limits"]["review_rounds"], 2)


class TriageAndBlocksTests(unittest.TestCase):
    def test_every_finding_is_triaged_exactly_once(self):
        findings = {"findings": [{"id": "F1"}, {"id": "F2"}]}
        good = {"confirmed": [{"finding": "F1"}], "rejected": [{"finding": "F2"}]}
        self.assertEqual(contract.triage_problems(findings, good), [])
        twice = {"confirmed": [{"finding": "F1"}], "rejected": [{"finding": "F1"}, {"finding": "F2"}]}
        self.assertIn("/: finding F1 is triaged 2 times", contract.triage_problems(findings, twice))
        missing = {"confirmed": [], "rejected": [{"finding": "F1"}, {"finding": "F9"}]}
        self.assertEqual(contract.triage_problems(findings, missing),
                         ["/rejected: finding F9 is not in the review round", "/: finding F2 is not triaged"])

    def test_json_block_takes_the_last_tagged_block(self):
        text = "```stage-report\n{\"a\": 1}\n```\nthen\n````stage-report\n{\"a\": 2, \"s\": \"```\"}\n````\n"
        self.assertEqual(prompts.json_block(text, "stage-report"), ({"a": 2, "s": "```"}, None))
        self.assertEqual(prompts.json_block("```json\n[1]\n```", "x")[1], "the `x` block is not a JSON object")
        self.assertIn("no fenced", prompts.json_block("plain", "x")[1])


class TriagerRoleTests(unittest.TestCase):
    def test_the_triager_judges_and_never_edits(self):
        manifest, text = render.load_role("triager")
        self.assertEqual(contracts.validate(manifest, "role-manifest"), [])
        self.assertEqual((manifest["write_authority"], manifest["result_shape"]), ("none", "triage-result"))
        self.assertEqual(manifest["tools"]["filesystem"], "read")
        self.assertIn("Confirm a finding without a reproduction", text)
        self.assertIn("Edit, create or delete repository files", text)


class SettingsTests(unittest.TestCase):
    def test_defaults_of_the_conductor(self):
        found = settings.defaults().conductor
        # the shipped reviewer is the default of the run options, not a choice of the configuration: a plan's review route
        # may still pick the reviewer
        self.assertEqual((found["provider"], found["reviewer"], found["registrar"], found["on_blocked"]),
                         ("claude-code", None, "orch/conductor", "stop"))
        from orch.conductor import options as opts
        self.assertEqual(opts.DEFAULTS["reviewer"], "grok/grok-4.7/high")
        self.assertEqual((found["argv"], found["limits"]["check_timeout_s"], found["limits"]["stage_idle_timeout_s"],
                          found["limits"]["check_idle_timeout_s"]),
                         ({}, 0, 5400, 3600))  # nothing long is cut by default, only a silent (hung) role or check

    def test_a_project_file_cannot_choose_the_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p"
            (project / ".swissknifeman").mkdir(parents=True)
            (project / ".swissknifeman" / "config.toml").write_text(
                'schema_version = 1\n[orch.conductor.argv]\nexecutor = ["sh", "-c", "evil"]\n', encoding="utf-8")
            with self.assertRaises(ConfigError):
                settings.load(project=project, env={}, home=Path(tmp) / "home")
            machine = Path(tmp) / "home" / ".local" / "share" / "swissknifeman" / "config" / "config.toml"
            machine.parent.mkdir(parents=True)
            machine.write_text('schema_version = 1\n[orch.conductor.argv]\nexecutor = ["fake", "{model}"]\n',
                               encoding="utf-8")
            (project / ".swissknifeman" / "config.toml").write_text("schema_version = 1\n", encoding="utf-8")
            found = settings.load(project=project, env={}, home=Path(tmp) / "home")
            self.assertEqual(found.conductor["argv"], {"executor": ["fake", "{model}"]})


class DoctorTests(unittest.TestCase):
    def git_project(self, ignore: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(tmp.name)
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        (project / ".gitignore").write_text(ignore, encoding="utf-8")
        return project

    def test_ignored_runtime_and_reports_folders_are_ok(self):
        rows = {row["check_id"]: row for row in doctor_checks(self.git_project(".swissknifeman/state/\n.swissknifeman/orch/\n"))}
        self.assertEqual((rows["orch.conductor-gitignore"]["status"], rows["orch.conductor-reports"]["status"]),
                         ("ok", "ok"))

    def test_a_runtime_folder_git_would_see_is_a_warning(self):
        rows = {row["check_id"]: row for row in doctor_checks(self.git_project(".swissknifeman/state/\n"))}
        self.assertEqual(rows["orch.conductor-gitignore"]["status"], "ok")
        self.assertEqual(rows["orch.conductor-reports"]["status"], "warn")  # the observer report would dirty the tree
        rows = {row["check_id"]: row for row in doctor_checks(self.git_project("node_modules/\n"))}
        self.assertEqual(rows["orch.conductor-gitignore"]["status"], "warn")
        self.assertIn(".swissknifeman/state/", rows["orch.conductor-gitignore"]["remediation"])

    def test_a_runtime_folder_in_the_workspace_project_is_outside_the_checkout(self):
        project = self.git_project("node_modules/\n")
        workspaces = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, workspaces, True)
        (workspaces / "ws" / "projects" / "alpha").mkdir(parents=True)
        (project / ".swissknifeman").mkdir()
        (project / ".swissknifeman" / "project.json").write_text(
            '{"workspace": "ws", "project_id": "alpha", "plans_store": "workspace"}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"SKM_WORKSPACES_ROOT": str(workspaces)}):
            rows = {row["check_id"]: row for row in doctor_checks(project)}
            runs = runs_root(project)
        self.assertEqual(rows["orch.conductor-gitignore"]["status"], "ok")
        self.assertEqual(runs, workspaces / "ws" / "projects" / "alpha" / "local" / "state" / "orch" / "conductor")

    def test_outside_git_the_check_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(doctor_checks(Path(tmp))[0]["status"], "skip")

    def test_the_sandbox_row_follows_the_probe(self):
        up = {"available": True, "reason": None, "checked": [{"name": "bwrap", "ok": True, "detail": "/usr/bin/bwrap"}]}
        down = {"available": False, "reason": "bwrap not found on PATH",
                "checked": [{"name": "bwrap", "ok": False, "detail": "bwrap not found on PATH"}]}
        with mock.patch("orch.sandbox.probe", return_value=up):
            row = {r["check_id"]: r for r in doctor_checks(None)}["orch.sandbox"]
        self.assertEqual(row["status"], "ok")
        with mock.patch("orch.sandbox.probe", return_value=down):
            row = {r["check_id"]: r for r in doctor_checks(None)}["orch.sandbox"]
        self.assertEqual(row["status"], "warn")
        self.assertIn("bwrap not found on PATH", row["observed"])
        self.assertIn("AppArmor", row["remediation"])

    def test_the_rows_are_check_results(self):
        from aicore.util import schema
        registry = schema.load_contract(Path(__import__("aicore").__file__).resolve().parents[2]
                                        / "schemas" / "check-result" / "v1")[0]
        for row in doctor_checks(self.git_project("x\n")):
            self.assertEqual(schema.validate(row, "check-result", registry), [], row)


if __name__ == "__main__":
    unittest.main()
