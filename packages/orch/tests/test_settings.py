from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from aicore.config import ConfigError

from orch import contracts, settings
from orch.conductor import questions
from orch.settings import SettingsError


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.project = self.root / "project"
        (self.home / "skm" / "config").mkdir(parents=True)
        (self.project / ".swissknifeman").mkdir(parents=True)
        self.env = {"SKM_HOME": str(self.home / "skm"), "HOME": str(self.home)}

    def machine(self, text: str) -> None:
        (self.home / "skm" / "config" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    def project_file(self, text: str) -> None:
        (self.project / ".swissknifeman" / "config.toml").write_text("schema_version = 1\n" + text, encoding="utf-8")

    def config_file(self, text: str) -> Path:
        path = self.root / "invocation.toml"
        path.write_text("schema_version = 1\n" + text, encoding="utf-8")
        return path

    def load(self, **kwargs) -> settings.Settings:
        kwargs.setdefault("env", self.env)
        kwargs.setdefault("home", self.home)
        return settings.load(**kwargs)


class LoadTests(SettingsCase):
    def test_defaults(self):
        found = self.load()
        self.assertEqual((found.engine, found.default_profile, found.work_source), ("native", "solo", "planner-orch"))
        self.assertEqual((found.engine_by_role, found.capabilities_stale), ({}, "warn"))
        self.assertEqual((found.profiles_dirs, found.events_enabled), ((), True))

    def test_the_project_layer_overrides_the_machine_layer(self):
        self.machine('[orch]\nengine = "cao"\ndefault_profile = "full"\n')
        self.project_file('[orch]\nengine = "claude-only"\n[orch.engine_by_role]\nreviewer = "native"\n')
        found = self.load(project=self.project)
        self.assertEqual((found.engine, found.default_profile), ("claude-only", "full"))
        self.assertEqual(found.engine_by_role, {"reviewer": "native"})
        self.assertIn("project", found.explain_text("engine"))

    def test_the_environment_beats_the_files(self):
        self.project_file('[orch]\nengine = "claude-only"\n')
        found = self.load(project=self.project, env={**self.env, "SKM_ORCH_ENGINE": "cao"})
        self.assertEqual(found.engine, "cao")

    def test_the_config_file_beats_the_environment(self):
        path = self.config_file('[orch]\nengine = "claude-only"\n')
        found = self.load(config_file=path, env={**self.env, "SKM_ORCH_ENGINE": "cao"})
        self.assertEqual(found.engine, "claude-only")

    def test_an_unknown_engine_is_refused(self):
        self.machine('[orch]\nengine = "tmux"\n')
        with self.assertRaises(ConfigError):
            self.load()

    def test_profile_folders_from_the_project_are_refused(self):
        self.project_file('[orch.profiles]\ndirs = ["/tmp/elsewhere"]\n')
        with self.assertRaises(ConfigError) as raised:
            self.load(project=self.project)
        self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_profile_folders_from_the_environment_are_refused(self):
        with self.assertRaises(ConfigError) as raised:
            self.load(env={**self.env, "SKM_ORCH_PROFILES__DIRS": '["/tmp/elsewhere"]'})
        self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_profile_folders_from_the_machine_file_expand_the_home_folder(self):
        self.machine('[orch.profiles]\ndirs = ["~/packs", "/opt/packs"]\n')
        previous = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(lambda: os.environ.__setitem__("HOME", previous) if previous else os.environ.pop("HOME"))
        found = self.load()
        self.assertEqual(found.profiles_dirs, (self.home / "packs", Path("/opt/packs")))

    def test_a_relative_profile_folder_is_refused(self):
        path = self.config_file('[orch.profiles]\ndirs = ["packs"]\n')
        with self.assertRaises(SettingsError) as raised:
            self.load(config_file=path)
        self.assertEqual(raised.exception.code, "PROFILES_DIR_RELATIVE")

    def test_an_appended_folder_cannot_retarget_a_relative_one_of_a_lower_layer(self):
        self.machine('[orch.profiles]\ndirs = ["team-policies"]\n')
        path = self.config_file('[orch]\n_append = {"profiles.dirs" = ["/opt/extra"]}\n')
        with self.assertRaises(SettingsError) as raised:
            self.load(config_file=path)
        self.assertEqual(raised.exception.code, "PROFILES_DIR_RELATIVE")

    def test_an_appended_absolute_folder_follows_the_lower_one(self):
        self.machine('[orch.profiles]\ndirs = ["/opt/a"]\n')
        path = self.config_file('[orch]\n_append = {"profiles.dirs" = ["/opt/b"]}\n')
        self.assertEqual(self.load(config_file=path).profiles_dirs, (Path("/opt/a"), Path("/opt/b")))


class ConductorLimitsTests(SettingsCase):
    """The keys of ``[orch.conductor.limits]`` reach the run options (a key settings drops is lost silently)."""

    def test_question_modes_match_the_config_schema(self):
        schema = json.loads((settings.ORCH_ROOT / "configs/config.schema.json").read_text())
        self.assertEqual(list(questions.MODES), schema["properties"]["conductor"]["properties"]["questions"]["enum"])
        for mode in questions.MODES:
            self.machine(f'[orch.conductor]\nquestions = "{mode}"\n')
            self.assertEqual(self.load().conductor["questions"], mode)

    def test_an_unknown_question_mode_is_refused(self):
        self.machine('[orch.conductor]\nquestions = "silently-answer"\n')
        with self.assertRaises(ConfigError):
            self.load()

    def test_the_budget_and_wall_keys_of_the_machine_layer_reach_the_limits(self):
        self.machine('[orch.conductor.limits]\nunmetered = "charge"\nunmetered_charge_tokens = 7\n'
                     '[orch.conductor.limits.role_timeout_s]\nreviewer = 5\n')
        limits = self.load(project=self.project).conductor["limits"]
        self.assertEqual((limits["unmetered"], limits["unmetered_charge_tokens"], limits["role_timeout_s"]),
                         ("charge", 7, {"reviewer": 5}))

    def test_the_defaults_of_the_new_keys(self):
        limits = self.load().conductor["limits"]
        self.assertEqual((limits["unmetered"], limits["unmetered_charge_tokens"], limits["check_timeout_s"]),
                         ("stop", 50000, 7200))
        self.assertEqual(limits["role_timeout_s"], {})  # the walls of the roles are those of options.DEFAULT_LIMITS

    def test_an_unknown_unmetered_policy_is_refused(self):
        self.machine('[orch.conductor.limits]\nunmetered = "ignore"\n')
        with self.assertRaises(ConfigError):
            self.load()

    def test_the_layers_reach_the_run_options_and_a_role_wall_merges_by_role(self):
        from orch.conductor import options
        self.machine('[orch.conductor.limits]\nunmetered = "charge"\n[orch.conductor.limits.role_timeout_s]\nreviewer = 5\n')
        merged, sources = options.effective(self.load().conductor, {}, [])
        self.assertEqual(merged["limits"]["unmetered"], "charge")
        self.assertEqual(merged["limits"]["role_timeout_s"]["reviewer"], 5)
        self.assertEqual(merged["limits"]["role_timeout_s"]["triager"], 1800)  # the wall of a role no layer names stays
        self.assertEqual(sources["limits.unmetered"], "config:orch.conductor")


class AccessAuthorityTests(SettingsCase):
    def test_project_leaf_reset_keeps_the_machine_access_floor(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.project_file('[orch]\n_unset = ["launch.access"]\n')
        found = self.load(project=self.project)
        self.assertEqual(found.resolved.explain("launch.access")[0].layer, "defaults")
        self.assertEqual(found.launch["access"], "confined")

    def test_project_parent_reset_is_refused(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.project_file('[orch]\n_unset = ["launch"]\n')
        with self.assertRaises(ConfigError) as raised:
            self.load(project=self.project)
        self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_environment_open_cannot_weaken_machine_or_project_confinement(self):
        for machine, project in (("confined", ""), ("open", '[orch.launch]\naccess = "confined"\n')):
            with self.subTest(machine=machine, project=project):
                self.machine(f'[orch.launch]\naccess = "{machine}"\n')
                self.project_file(project)
                found = self.load(project=self.project, env={**self.env, "SKM_ORCH_LAUNCH__ACCESS": "open"})
                self.assertEqual(found.launch["access"], "confined")

    def test_untrusted_layers_can_tighten_open_access(self):
        for project, env in (('[orch.launch]\naccess = "confined"\n', {}),
                             ("", {"SKM_ORCH_LAUNCH__ACCESS": "confined"})):
            with self.subTest(project=project, env=env):
                self.machine('[orch.launch]\naccess = "open"\n')
                self.project_file(project)
                self.assertEqual(self.load(project=self.project, env={**self.env, **env}).launch["access"], "confined")

    def test_machine_reset_and_explicit_caller_values_can_reopen_access(self):
        self.machine('[orch]\n_unset = ["launch.access"]\n')
        self.project_file('[orch.launch]\naccess = "open"\n')
        self.assertEqual(self.load(project=self.project).launch["access"], "open")
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.project_file('[orch]\n_unset = ["launch.access"]\n')
        invocation = self.config_file('[orch.launch]\naccess = "open"\n')
        self.assertEqual(self.load(project=self.project, config_file=invocation).launch["access"], "open")
        reset = self.config_file('[orch]\n_unset = ["launch.access"]\n')
        self.assertEqual(self.load(project=self.project, config_file=reset).launch["access"], "open")
        self.assertEqual(self.load(project=self.project, flags={"launch.access": "open"}).launch["access"], "open")


class AdvisorAuthorityTests(SettingsCase):
    def test_a_project_cannot_replace_or_unset_the_base_human_gate(self):
        for text in ('[orch.advisor]\nhuman_gate = []\n', '[orch]\n_unset = ["advisor.human_gate"]\n'):
            with self.subTest(text=text):
                self.project_file(text)
                with self.assertRaises(ConfigError) as raised:
                    self.load(project=self.project)
                self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_the_environment_cannot_replace_the_base_human_gate(self):
        with self.assertRaises(ConfigError) as raised:
            self.load(env={**self.env, "SKM_ORCH_ADVISOR__HUMAN_GATE": "[]"})
        self.assertEqual(raised.exception.code, "CONFIG_LAYER_FORBIDDEN")

    def test_the_machine_and_caller_can_set_the_base_human_gate(self):
        self.machine('[orch.advisor]\nhuman_gate = []\n')
        self.assertEqual(self.load().advisor["human_gate"], [])
        invocation = self.config_file('[orch.advisor]\nhuman_gate = ["other"]\n')
        self.assertEqual(self.load(config_file=invocation).advisor["human_gate"], ["other"])
        self.assertEqual(self.load(config_file=invocation, flags={"advisor.human_gate": []}).advisor["human_gate"], [])

    def test_extra_gates_accumulate_across_all_layers_even_after_unset(self):
        self.machine('[orch.advisor]\nhuman_gate = []\nhuman_gate_extra = ["other"]\n')
        invocation = self.config_file('[orch.advisor]\nhuman_gate_extra = ["scope-expansion"]\n')
        for project in ('[orch.advisor]\nhuman_gate_extra = []\n',
                        '[orch]\n_unset = ["advisor.human_gate_extra"]\n'):
            with self.subTest(project=project):
                self.project_file(project)
                found = self.load(project=self.project, config_file=invocation,
                                  env={**self.env, "SKM_ORCH_ADVISOR__HUMAN_GATE_EXTRA": '["public-api"]'},
                                  flags={"advisor.human_gate_extra": ["security"]})
                self.assertEqual(found.advisor["human_gate"], ["other", "public-api", "scope-expansion", "security"])

    def test_confidence_uses_the_strictest_layer_including_defaults_and_unset(self):
        for machine, project, expected in (("high", "low", "high"), ("medium", "high", "high"),
                                           ("low", "low", "medium"), ("high", None, "high")):
            with self.subTest(machine=machine, project=project):
                self.machine(f'[orch.advisor]\nmin_confidence = "{machine}"\n')
                self.project_file(f'[orch.advisor]\nmin_confidence = "{project}"\n' if project else
                                  '[orch]\n_unset = ["advisor.min_confidence"]\n')
                found = self.load(project=self.project, flags={"advisor.min_confidence": "low"})
                self.assertEqual(found.advisor["min_confidence"], expected)


class DigestTests(SettingsCase):
    def test_the_digest_follows_the_values_that_affect_preparation(self):
        base = settings.digest(self.load())
        self.assertRegex(base, r"^[0-9a-f]{64}$")
        self.assertEqual(base, settings.digest(self.load()))
        for text in ('engine = "cao"', 'default_profile = "full"', "capabilities.stale"):
            with self.subTest(text=text):
                if text == "capabilities.stale":
                    path = self.config_file('[orch.capabilities]\nstale = "refuse"\n')
                else:
                    path = self.config_file(f"[orch]\n{text}\n")
                self.assertNotEqual(base, settings.digest(self.load(config_file=path)))
        path = self.config_file('[orch.engine_by_role]\nreviewer = "cao"\n')
        self.assertNotEqual(base, settings.digest(self.load(config_file=path)))

    def test_the_digest_ignores_the_other_keys(self):
        base = settings.digest(self.load())
        path = self.config_file('[orch]\nwork_source = "other"\n[orch.events]\nenabled = false\n')
        changed = self.load(config_file=path)
        self.assertEqual(changed.work_source, "other")
        self.assertEqual(base, settings.digest(changed))

    def test_affecting_lists_exactly_the_affecting_keys(self):
        self.assertEqual(sorted(settings.affecting(self.load())),
                         ["capabilities.stale", "default_profile", "engine", "engine_by_role"])


class SelectEngineTests(SettingsCase):
    def select(self, role="reviewer", **kwargs):
        path = self.config_file('[orch]\nengine = "native"\n[orch.engine_by_role]\nreviewer = "cao"\n')
        return settings.select_engine(self.load(config_file=path), role, **kwargs)

    def test_the_configured_engine_is_the_default(self):
        binding, decision = self.select("executor")
        self.assertEqual(binding, "native")
        self.assertEqual(decision["considered"],
                         [{"candidate": "native", "accepted": True, "reason_codes": ["ENGINE_FROM_CONFIG"]}])

    def test_the_role_table_beats_the_default(self):
        binding, decision = self.select()
        self.assertEqual(binding, "cao")
        self.assertEqual(decision["considered"][0]["reason_codes"], ["ENGINE_FROM_ROLE"])
        self.assertEqual(decision["considered"][1],
                         {"candidate": "native", "accepted": False, "reason_codes": ["ENGINE_OVERRIDDEN"]})

    def test_the_flag_beats_everything(self):
        binding, decision = self.select(flag="claude-only", stage_id="review")
        self.assertEqual(binding, "claude-only")
        self.assertEqual((decision["stage_id"], decision["kind"], decision["chosen"]),
                         ("review", "binding", "claude-only"))
        self.assertEqual([c["candidate"] for c in decision["considered"]], ["claude-only", "cao", "native"])

    def test_the_decision_is_a_valid_launch_plan_decision(self):
        _, decision = self.select(flag="cao")
        path = Path(__file__).resolve().parents[1] / "fixtures" / "exec" / "v1" / "valid" / "launch-plan"
        plan = json.loads((path / "dry-run-proof.json").read_text(encoding="utf-8"))
        plan["decisions"] = [decision]
        plan["digest"] = contracts.canonical_digest(plan)
        self.assertEqual([i for i in contracts.validate(plan, "launch-plan") if i.level == "error"], [])

    def test_an_unknown_flag_engine_is_refused_not_replaced(self):
        with self.assertRaises(SettingsError) as raised:
            self.select(flag="tmux")
        self.assertEqual(raised.exception.code, "ENGINE_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
