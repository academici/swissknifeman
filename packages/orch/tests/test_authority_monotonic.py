"""Every authority floor has an explicit weakening attempt; a new floor needs a table row."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from aicore.config import ConfigError

from orch.conductor import options, risk
from orch.conductor.stages import advice
from tests.test_settings import SettingsCase


# Explicit expectations, deliberately not generated from the implementation's floor values.
OPTION_CASES = {
    "instructions.sandbox": ("require", "off"),
    "instructions.sandbox_domains": (["trusted.example"], ["untrusted.example"]),
    "instructions.isolate_roles": (["executor", "reviewer"], ["executor"]),
    "scope.fence": ("plan", "project"),
    "scope.outside": ("block", "deviation"),
    "scope.outside_module": ("block", "deviation"),
    "scope.extra_paths": (["/srv/allowed"], ["/srv/untrusted"]),
    "scope.runtime_paths": (["build/**", "logs/**"], ["build/**"]),
}
CONFIG_KEYS = ["advisor.human_gate", "advisor.human_gate_extra", "advisor.min_confidence", "access"]
CONFIG_CASES = {
    "advisor.human_gate": ('[orch.advisor]\nhuman_gate = ["other"]\n',
                          '[orch.advisor]\nhuman_gate = []\n', "human_gate", ["other"], "CONFIG_LAYER_FORBIDDEN"),
    "advisor.human_gate_extra": ('[orch.advisor]\nhuman_gate = []\nhuman_gate_extra = ["other"]\n',
                                '[orch.advisor]\nhuman_gate_extra = []\n', "human_gate", ["other"], None),
    "advisor.min_confidence": ('[orch.advisor]\nmin_confidence = "high"\n',
                               '[orch.advisor]\nmin_confidence = "low"\n', "min_confidence", "high", None),
    # The public setting is access; its configuration path is launch.access.
    "access": ('[orch.launch]\naccess = "confined"\n', '[orch.launch]\naccess = "open"\n',
               "access", "confined", None),
}
ACCESS_WEAKENINGS = (
    ("project open", '[orch.launch]\naccess = "open"\n', {}, None),
    ("project unset leaf", '[orch]\n_unset = ["launch.access"]\n', {}, None),
    ("project unset table", '[orch]\n_unset = ["launch"]\n', {}, "CONFIG_LAYER_FORBIDDEN"),
    ("environment open", "", {"SKM_ORCH_LAUNCH__ACCESS": "open"}, None),
    ("project reset and environment open", '[orch]\n_unset = ["launch.access"]\n',
     {"SKM_ORCH_LAUNCH__ACCESS": "open"}, None),
)


class AuthorityTableTests(unittest.TestCase):
    def test_every_authority_key_has_an_explicit_expectation(self):
        floor = {".".join(key) for key in set(options.FLOOR_ORDER) | set(options.FLOOR_NARROW) | set(options.FLOOR_WIDEN)}
        self.assertEqual(floor, set(OPTION_CASES), "a changed authority floor needs a monotonicity test row")
        self.assertEqual(set(CONFIG_KEYS), set(CONFIG_CASES))

    def test_a_plan_layer_cannot_weaken_any_option_floor(self):
        for key, (strong, weak) in OPTION_CASES.items():
            with self.subTest(key=key):
                group, name = key.split(".")
                base = {group: {name: strong}}
                attack = {group: {name: weak}}
                # merge is structural; effective owns validation of source authority at every merge.
                self.assertEqual(options.merge(base, attack)[group][name], weak)
                with self.assertRaises(options.OptionsError) as raised:
                    options.effective({}, {}, [
                        {"source": "invocation:--options", "trusted": True, "options": base},
                        {"source": "plan", "options": attack},
                    ])
                self.assertEqual(raised.exception.code, "OPTIONS_UNTRUSTED")
                self.assertIn(key, raised.exception.message)

    def test_config_authority_keys_cannot_be_injected_through_plan_options(self):
        for key, value in (("advisor.human_gate", []), ("advisor.human_gate_extra", []),
                           ("advisor.min_confidence", "low"), ("launch.access", "open")):
            with self.subTest(key=key):
                group, name = key.split(".")
                with self.assertRaises(options.OptionsError) as raised:
                    options.effective({}, {}, [{"source": "plan", "options": {group: {name: value}}}])
                # These keys have no run-options surface: schema validation rejects them before the floor merge.
                self.assertEqual(raised.exception.code, "OPTIONS_INVALID")


class ConfigAuthorityTests(SettingsCase):
    def reading(self, loaded, path):
        conductor = SimpleNamespace(settings=loaded, _advisor_cfg=lambda: loaded.advisor,
                                    _changed=lambda item: [path], _outside=lambda item: [], progress=mock.Mock())
        item = SimpleNamespace(ref="W1", input_doc={"scope": {"write_set": [path]}})
        return advice.reading(conductor, {"options": [{"id": "go"}], "recommendation": "go",
                                          "category": "other", "confidence": "high", "needs_owner": False}, item)[1]

    def test_builtin_categories_survive_empty_replacement_and_reset_patterns(self):
        for feature, path, category in (("security", "src/auth/check.py", "security"),
                                         ("public_cli", "src/cli.py", "public-api"),
                                         ("schema", "api/schemas/request.json", "public-api")):
            for project in (f'[orch.conductor.risk.patterns]\n{feature} = []\n',
                            f'[orch.conductor.risk.patterns]\n{feature} = ["unrelated/**"]\n',
                            f'[orch]\n_unset = ["conductor.risk.patterns.{feature}"]\n',
                            '[orch]\n_unset = ["conductor.risk.patterns"]\n'):
                with self.subTest(feature=feature, project=project):
                    self.project_file(project)
                    self.assertIn(f"code: {category} ({path})", self.reading(self.load(project=self.project), path))

    def test_trusted_custom_categories_survive_project_and_environment_weakening(self):
        for feature, category in (("security", "security"), ("public_cli", "public-api"), ("schema", "public-api")):
            path = f"custom/{feature}/protected.py"
            self.machine(f'[orch.conductor.risk.patterns]\n{feature} = ["{path}"]\n')
            attacks = [(f'[orch.conductor.risk.patterns]\n{feature} = []\n', {}),
                       (f'[orch.conductor.risk.patterns]\n{feature} = ["unrelated/**"]\n', {}),
                       (f'[orch]\n_unset = ["conductor.risk.patterns.{feature}"]\n', {}),
                       ('[orch]\n_unset = ["conductor.risk.patterns"]\n', {}),
                       ('[orch]\n_unset = ["conductor.risk"]\n', {}),
                       ('', {f"SKM_ORCH_CONDUCTOR__RISK__PATTERNS__{feature.upper()}": "[]"}),
                       (f'[orch]\n_unset = ["conductor.risk.patterns.{feature}"]\n',
                        {f"SKM_ORCH_CONDUCTOR__RISK__PATTERNS__{feature.upper()}": '["unrelated/**"]'})]
            for project, env in attacks:
                with self.subTest(feature=feature, project=project, env=env):
                    self.project_file(project)
                    loaded = self.load(project=self.project, env={**self.env, **env})
                    self.assertIn(f"code: {category} ({path})", self.reading(loaded, path))

    def test_trusted_invocation_and_flags_retain_established_pattern_history(self):
        self.machine('[orch.conductor.risk.patterns]\nsecurity = ["custom/machine.py"]\n')
        self.project_file('[orch.conductor.risk.patterns]\nsecurity = []\n')
        config = self.config_file('[orch.conductor.risk.patterns]\nsecurity = ["custom/invocation.py"]\n')
        loaded = self.load(project=self.project, config_file=config,
                           flags={"conductor.risk.patterns.security": ["custom/flag.py"]})
        for path in ("custom/machine.py", "custom/invocation.py", "custom/flag.py", "src/auth/check.py"):
            with self.subTest(path=path):
                self.assertIn(f"code: security ({path})", self.reading(loaded, path))
        # A trusted reset also retains established patterns; builtin authority never disappears.
        config = self.config_file('[orch]\n_unset = ["conductor.risk.patterns.security"]\n')
        self.assertIn("code: security", self.reading(self.load(config_file=config), "custom/machine.py"))

    def test_project_patterns_can_strengthen_categories_without_freezing_the_risk_score(self):
        self.project_file('[orch.conductor.risk.patterns]\nsecurity = ["custom/project.py"]\n'
                          '[orch.conductor.risk.weights]\nsecurity = 7\n')
        loaded = self.load(project=self.project)
        self.assertIn("code: security", self.reading(loaded, "custom/project.py"))
        self.assertIsNone(self.reading(loaded, "src/plain.py"))
        self.assertEqual(risk.score({"changed": ["custom/project.py"]}, loaded.conductor["risk"])["score"], 7)
        self.assertEqual(risk.score({"changed": ["src/auth/check.py"]}, loaded.conductor["risk"])["score"], 0)
        self.project_file('[orch.conductor.risk.patterns]\nsecurity = []\n')
        loaded = self.load(project=self.project)
        self.assertIn("code: security", self.reading(loaded, "src/auth/check.py"))
        self.assertEqual(risk.score({"changed": ["src/auth/check.py"]}, loaded.conductor["risk"])["score"], 0)

    def test_access_floor_survives_project_resets_and_environment_overrides(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        for name, project, env, error in ACCESS_WEAKENINGS:
            with self.subTest(case=name):
                self.project_file(project)
                if error:
                    with self.assertRaises(ConfigError) as raised:
                        self.load(project=self.project, env={**self.env, **env})
                    self.assertEqual(raised.exception.code, error)
                else:
                    found = self.load(project=self.project, env={**self.env, **env})
                    self.assertEqual(found.launch["access"], "confined")

    def test_project_weakening_is_refused_or_keeps_the_same_effective_authority(self):
        for key, (machine, project, field, expected, error) in CONFIG_CASES.items():
            with self.subTest(key=key):
                self.machine(machine)
                self.project_file(project)
                if error:
                    with self.assertRaises(ConfigError) as raised:
                        self.load(project=self.project)
                    self.assertEqual(raised.exception.code, error)
                else:
                    loaded = self.load(project=self.project)
                    actual = loaded.launch[field] if key == "access" else loaded.advisor[field]
                    self.assertEqual(actual, expected)

    def test_unset_does_not_remove_extra_gates_or_lower_confidence(self):
        for key, field, expected in (("advisor.human_gate_extra", "human_gate", ["other"]),
                                     ("advisor.min_confidence", "min_confidence", "high")):
            with self.subTest(key=key):
                self.machine('[orch.advisor]\nhuman_gate = []\nhuman_gate_extra = ["other"]\nmin_confidence = "high"\n')
                self.project_file(f'[orch]\n_unset = ["{key}"]\n')
                self.assertEqual(self.load(project=self.project).advisor[field], expected)


if __name__ == "__main__":
    unittest.main()
