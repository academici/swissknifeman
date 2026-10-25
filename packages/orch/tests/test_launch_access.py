"""``[orch.launch] access``: by default the roles that write get the widest mode of a provider CLI that has a sandbox of its own
(Codex ``danger-full-access``), so the executor can use Docker and anything else the user can; ``confined`` keeps them in the
workspace. Roles that must not write stay read-only in both. A project file can only tighten the setting."""
from __future__ import annotations

import unittest

from aicore.config import ConfigError

from orch import launch
from tests.test_settings import SettingsCase

WRITERS = {("executor", "codex"), ("bounded-implementer", "codex"), ("registrar", "codex")}


def flag(argv: list, name: str) -> list:
    return [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == name]


class BuildArgvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = launch.load_catalog()

    def test_access_sets_the_sandbox_of_the_codex_roles_that_write_and_of_no_other(self):
        for role, providers in self.catalog["launch"].items():
            if "codex" not in providers:
                continue
            for access, wide in (("open", "danger-full-access"), ("confined", "workspace-write")):
                with self.subTest(role=role, access=access):
                    argv = launch.build_argv(self.catalog, role, "codex", model="m", effort="high", cwd="/w", access=access)
                    self.assertEqual(flag(argv, "--sandbox"), [wide] if (role, "codex") in WRITERS else ["read-only"])

    def test_the_default_is_open_and_an_unknown_access_is_refused(self):
        argv = launch.build_argv(self.catalog, "executor", "codex", model="m", effort="high", cwd="/w")
        self.assertEqual(flag(argv, "--sandbox"), ["danger-full-access"])
        with self.assertRaises(launch.LaunchError):
            launch.build_argv(self.catalog, "executor", "codex", model="m", effort="high", cwd="/w", access="wide")

    def test_the_providers_without_a_sandbox_of_their_own_are_the_same_in_both_modes(self):
        for role, providers in self.catalog["launch"].items():
            for provider in providers:
                if provider == "codex":
                    continue
                with self.subTest(role=role, provider=provider):
                    one = launch.build_argv(self.catalog, role, provider, model="m", effort="high", cwd="/w", access="open")
                    two = launch.build_argv(self.catalog, role, provider, model="m", effort="high", cwd="/w",
                                            access="confined")
                    self.assertEqual(one, two)


class EnvelopeTests(unittest.TestCase):
    """P6.2: the authority envelope of each launch records the access and what it gives (``roles matrix``)."""

    @classmethod
    def setUpClass(cls):
        from orch.conductor.infrastructure import launch_plan
        cls.rows = launch_plan.authority_matrix(launch.load_catalog())

    def row(self, role: str, provider: str, access: str) -> dict:
        return next(row for row in self.rows if (row["role"], row["provider"], row["access"]) == (role, provider, access))

    def test_an_open_codex_writer_is_unconfined_and_a_confined_one_is_in_its_sandbox(self):
        for role, provider in sorted(WRITERS):
            with self.subTest(role=role):
                opened, confined = self.row(role, provider, "open"), self.row(role, provider, "confined")
                self.assertEqual((opened["guard"], opened["network"], opened["docker"]), ("none", "open", "open"))
                self.assertEqual((confined["guard"], confined["network"], confined["docker"]),
                                 ("codex-sandbox", "none", "blocked"))

    def test_the_access_changes_nothing_else_of_any_launch(self):
        keys = ("guard", "network", "enforced_by", "docker", "setting_sources", "guarantee")
        for row in self.rows:
            if row["access"] != "open" or (row["role"], row["provider"]) in WRITERS:
                continue
            with self.subTest(role=row["role"], provider=row["provider"]):
                other = self.row(row["role"], row["provider"], "confined")
                self.assertEqual({key: row[key] for key in keys}, {key: other[key] for key in keys})


class AccessSettingTests(SettingsCase):
    def test_the_default_is_open(self):
        self.assertEqual(self.load().launch["access"], "open")

    def test_the_machine_can_confine_and_open_again(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.assertEqual(self.load().launch["access"], "confined")

    def test_a_project_can_tighten_the_default(self):
        self.project_file('[orch.launch]\naccess = "confined"\n')
        self.assertEqual(self.load(project=self.project).launch["access"], "confined")

    def test_a_project_cannot_loosen_what_the_machine_confined(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.project_file('[orch.launch]\naccess = "open"\n')
        self.assertEqual(self.load(project=self.project).launch["access"], "confined")

    def test_an_invocation_file_may_open_what_the_machine_confined(self):
        self.machine('[orch.launch]\naccess = "confined"\n')
        self.project_file('[orch.launch]\naccess = "confined"\n')
        found = self.load(project=self.project, config_file=self.config_file('[orch.launch]\naccess = "open"\n'))
        self.assertEqual(found.launch["access"], "open")

    def test_another_value_is_refused(self):
        self.machine('[orch.launch]\naccess = "wide"\n')
        with self.assertRaises(ConfigError):
            self.load()


if __name__ == "__main__":
    unittest.main()
