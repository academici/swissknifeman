"""The isolation floor of the run options: a layer of the work source (plan, phase, item, overlay, input file) may
tighten the sandbox, the network allowlist, the role isolation and the write fence, never loosen them; only the
configuration, the run-policy pack and the invocation (marked ``trusted`` by the conductor) may. Extra writable paths
are canonical and never a system, home or ancestor folder."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from orch.conductor import options


def run(*layers, conductor=None):
    return options.effective(conductor or {}, {}, list(layers))[0]


def source(opts: dict, name: str = "item:W1") -> dict:
    return {"source": name, "options": opts}


def trusted(opts: dict) -> dict:
    return {"source": "invocation:--options", "options": opts, "trusted": True}


class FloorTests(unittest.TestCase):
    def refused(self, *layers) -> str:
        with self.assertRaises(options.OptionsError) as caught:
            run(*layers)
        self.assertEqual(caught.exception.code, "OPTIONS_UNTRUSTED")
        return caught.exception.message

    def test_a_source_layer_may_tighten_every_floor_key(self):
        found = run(source({"instructions": {"sandbox": "require", "sandbox_domains": [],
                                             "isolate_roles": list(options.MODEL_ROLES)},
                            "scope": {"fence": "plan", "outside": "block"}}))
        self.assertEqual((found["instructions"]["sandbox"], found["scope"]["fence"], found["scope"]["outside"]),
                         ("require", "plan", "block"))

    def test_a_source_layer_cannot_loosen_the_ordered_keys(self):
        for group, key, value in (("instructions", "sandbox", "off"), ("scope", "fence", "project"),
                                  ("scope", "outside", "deviation")):
            with self.subTest(key=key):
                tight = {"instructions": {"sandbox": "require"}, "scope": {"fence": "plan", "outside": "block"}}
                message = self.refused(trusted(tight), source({group: {key: value}}))
                self.assertIn(f"{group}.{key} {value}", message)
                self.assertIn("invocation:--options", message)

    def test_outside_module_and_runtime_paths_are_floor_keys(self):
        self.assertEqual(options.DEFAULTS["scope"]["outside_module"], "deviation")
        self.assertIn(("scope", "outside_module"), options.FLOOR_ORDER)
        self.assertIn(("scope", "runtime_paths"), options.FLOOR_WIDEN)
        self.assertIn("scope.outside_module deviation is weaker than block", self.refused(
            trusted({"scope": {"outside_module": "block"}}), source({"scope": {"outside_module": "deviation"}})))
        self.assertEqual(run(source({"scope": {"outside_module": "block"}}))["scope"]["outside_module"], "block")
        self.assertIn("scope.runtime_paths drops", self.refused(source({"scope": {"runtime_paths": ["build/**"]}})))
        found = run(trusted({"scope": {"outside_module": "deviation"}}), source({"scope": {"outside_module": "block"}}))
        self.assertEqual(found["scope"]["outside_module"], "block")

    def test_off_is_refused_against_the_default_prefer(self):
        self.assertIn("defaults", self.refused(source({"instructions": {"sandbox": "off"}})))

    def test_the_isolation_mode_is_an_ordered_floor_key(self):
        self.assertEqual(options.FLOOR_ORDER[("instructions", "isolation")], ("off", "prefer", "require"))
        self.assertEqual(options.DEFAULTS["instructions"]["isolation"], "prefer")
        self.assertIn("instructions.isolation off is weaker than prefer of defaults",
                      self.refused(source({"instructions": {"isolation": "off"}})))
        self.assertIn("instructions.isolation prefer is weaker than require of invocation:--options",
                      self.refused(trusted({"instructions": {"isolation": "require"}}),
                                   source({"instructions": {"isolation": "prefer"}})))
        self.assertEqual(run(source({"instructions": {"isolation": "require"}}))["instructions"]["isolation"], "require")
        self.assertEqual(run(trusted({"instructions": {"isolation": "off"}}))["instructions"]["isolation"], "off")

    def test_a_source_layer_cannot_add_domains_or_extra_paths_or_drop_isolated_roles(self):
        self.refused(source({"instructions": {"sandbox_domains": ["evil.example"]}}))
        self.refused(source({"scope": {"extra_paths": ["/srv/work"]}}))
        self.refused(source({"instructions": {"isolate_roles": ["executor"]}}))

    def test_a_source_layer_may_keep_or_narrow_what_a_trusted_layer_opened(self):
        found = run(trusted({"instructions": {"sandbox_domains": ["a.example", "b.example"]},
                             "scope": {"extra_paths": ["/srv/work"]}}),
                    source({"instructions": {"sandbox_domains": ["a.example"]}, "scope": {"extra_paths": ["/srv/work"]}}))
        self.assertEqual(found["instructions"]["sandbox_domains"], ["a.example"])

    def test_trusted_layers_may_loosen(self):
        found = run(source({"instructions": {"sandbox": "require"}}), trusted({"instructions": {"sandbox": "off"}}))
        self.assertEqual(found["instructions"]["sandbox"], "off")

    def test_the_label_of_a_layer_gives_no_trust(self):
        self.refused(source({"instructions": {"sandbox": "off"}}, name="invocation:--options"))
        self.refused(source({"instructions": {"sandbox": "off"}}, name="config:orch.conductor"))

    def test_limits_and_review_stay_free_for_the_plan(self):
        found = run(source({"limits": {"check_timeout_s": 3600, "check_fixes": 2}, "review": {"dynamic": False}}))
        self.assertEqual(found["limits"]["check_timeout_s"], 3600)

    def test_work_source_cannot_disable_or_raise_the_skill_ceiling(self):
        for value in (0, 5001):
            with self.subTest(value=value):
                message = self.refused(source({"limits": {"skill_tokens_max": value}}))
                self.assertIn("limits.skill_tokens_max", message)
                self.assertIn("defaults", message)
        for value in (0, 2001):
            with self.subTest(machine=value):
                with self.assertRaises(options.OptionsError) as caught:
                    run(source({"limits": {"skill_tokens_max": value}}),
                        conductor={"limits": {"skill_tokens_max": 2000}})
                self.assertEqual(caught.exception.code, "OPTIONS_UNTRUSTED")
                self.assertIn("config:orch.conductor", caught.exception.message)

    def test_work_source_may_keep_or_lower_but_not_restore_a_previous_skill_ceiling(self):
        for value in (1, 2000):
            with self.subTest(value=value):
                found = run(source({"limits": {"skill_tokens_max": value}}),
                            conductor={"limits": {"skill_tokens_max": 2000}})
                self.assertEqual(found["limits"]["skill_tokens_max"], value)
        self.refused(source({"limits": {"skill_tokens_max": 1000}}),
                     source({"limits": {"skill_tokens_max": 1001}}, name="item:W2"))

    def test_only_trusted_options_may_disable_or_raise_the_skill_ceiling(self):
        for value in (0, 9000):
            with self.subTest(value=value):
                found = run(trusted({"limits": {"skill_tokens_max": value}}))
                self.assertEqual(found["limits"]["skill_tokens_max"], value)
        self.assertEqual(run(source({"limits": {"skill_tokens_max": 8000}}),
                             conductor={"limits": {"skill_tokens_max": 0}})["limits"]["skill_tokens_max"], 8000)


class ExtraPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(os.path.realpath(self.tmp.name))
        self.home, self.project = root / "home" / "me", root / "home" / "me" / "work" / "project"
        self.project.mkdir(parents=True)

    def check(self, *paths) -> list:
        return options.checked_extra_paths(list(paths), self.project, home=self.home)

    def unsafe(self, path: str) -> str:
        with self.assertRaises(options.OptionsError) as caught:
            self.check(path)
        self.assertEqual(caught.exception.code, "OPTIONS_UNSAFE_PATH")
        return caught.exception.message

    def test_a_sibling_folder_is_taken_as_its_real_path(self):
        sibling = self.home / "work" / "shared"
        sibling.mkdir()
        link = self.home / "work" / "link"
        link.symlink_to(sibling)
        self.assertEqual(self.check(str(link)), [str(sibling)])

    def test_unsafe_folders_are_refused(self):
        for path, why in (("/", "root"), ("/etc", "system"), ("/usr/lib", "system"), (str(self.home), "HOME"),
                          (str(self.home.parent), "HOME"), (str(self.project), "project"),
                          (str(self.project.parent), "project"), (str(self.home / ".ssh"), "secrets"),
                          (str(self.home / "work" / "repo" / ".git" / "hooks"), ".git"), ("relative/dir", "relative")):
            with self.subTest(path=path):
                self.assertIn(why, self.unsafe(path))

    def test_a_symlink_to_home_is_refused(self):
        link = self.home / "work" / "escape"
        link.symlink_to(self.home)
        self.assertIn("HOME", self.unsafe(str(link)))

    def test_a_folder_inside_the_project_is_allowed(self):
        inside = self.project / "build"
        self.assertEqual(self.check(str(inside)), [str(inside)])


if __name__ == "__main__":
    unittest.main()
