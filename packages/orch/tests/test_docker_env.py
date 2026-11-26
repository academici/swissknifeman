"""The optional Docker environment rows of ``orch doctor``: what each fact of the machine says, and nothing about Docker
when it is not installed."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from aicore.util import schema

from orch import docker_env
from orch.cli import doctor_checks

ROOTFUL = {"installed": True, "endpoint": "unix:///var/run/docker.sock", "reachable": True, "server_version": "29.0",
           "security_options": ["name=seccomp,profile=builtin"], "compose": "2.30",
           "socket": {"path": "/var/run/docker.sock", "exists": True, "is_socket": True, "owner_uid": 0, "group": "docker",
                      "group_gid": 984, "mode": 0o660, "user_in_group": True, "owned_by_user": False},
           "credentials": {"store": None, "helpers": {}}}


def rows_of(facts: dict) -> dict:
    return {row["check_id"]: row for row in docker_env.assess(facts)}


class AssessTests(unittest.TestCase):
    def test_without_the_cli_everything_is_skipped(self):
        rows = docker_env.assess({"installed": False})
        self.assertEqual([(row["check_id"], row["status"]) for row in rows], [("orch.docker", "skip")])

    def test_a_rootful_daemon_reached_through_the_docker_group_is_a_warning_naming_the_authority(self):
        row = rows_of(ROOTFUL)["orch.docker"]
        self.assertEqual(row["status"], "warn")
        self.assertIn("controls the host as root", row["observed"])
        self.assertIn("rootless", row["remediation"])
        self.assertTrue(any("sandbox of the executor cannot reach" in line for line in row["evidence"]))

    def test_a_rootless_daemon_is_ok(self):
        facts = {**ROOTFUL, "security_options": ["name=seccomp,profile=builtin", "name=rootless"],
                 "socket": {**ROOTFUL["socket"], "owner_uid": 1000, "group": "user", "owned_by_user": True}}
        row = rows_of(facts)["orch.docker"]
        self.assertEqual(row["status"], "ok")
        self.assertIn("rootless", row["observed"])

    def test_a_rootless_daemon_of_another_account_is_ok_without_the_own_account_remark(self):
        facts = {**ROOTFUL, "security_options": ["name=rootless"],
                 "socket": {**ROOTFUL["socket"], "owner_uid": 1500, "owned_by_user": False}}
        row = rows_of(facts)["orch.docker"]
        self.assertEqual(row["status"], "ok")
        self.assertNotIn("belongs to this user", row["observed"])

    def test_an_unreachable_daemon_is_a_warning_with_the_cause(self):
        facts = {"installed": True, "endpoint": "unix:///var/run/docker.sock", "reachable": False,
                 "error": "permission denied while trying to connect to the docker API"}
        rows = rows_of(facts)
        self.assertEqual(list(rows), ["orch.docker"])  # nothing else to check without a daemon
        self.assertEqual(rows["orch.docker"]["status"], "warn")
        self.assertIn("permission denied", rows["orch.docker"]["observed"])

    def test_a_missing_credential_helper_fails_and_names_it(self):
        facts = {**ROOTFUL, "credentials": {"store": "desktop", "helpers": {"desktop": False, "pass": True}}}
        row = rows_of(facts)["orch.docker-credentials"]
        self.assertEqual(row["status"], "fail")
        self.assertIn("docker-credential-desktop", row["observed"])
        self.assertNotIn("docker-credential-pass", row["observed"])

    def test_a_missing_compose_plugin_is_a_warning(self):
        self.assertEqual(rows_of({**ROOTFUL, "compose": None})["orch.docker-compose"]["status"], "warn")

    def test_every_row_is_a_check_result(self):
        folder = Path(schema.__file__).resolve().parents[3] / "schemas" / "check-result" / "v1"
        registry = schema.load_contract_set(folder)[0]
        for facts in (ROOTFUL, {"installed": False}, {**ROOTFUL, "credentials": {"store": "x", "helpers": {"x": False}}}):
            for row in docker_env.assess(facts):
                with self.subTest(row=row["check_id"], status=row["status"]):
                    issues = schema.validate(row, "check-result", registry)
                    self.assertEqual([i.message for i in issues], [])


class CollectTests(unittest.TestCase):
    def test_without_the_cli_nothing_else_is_asked(self):
        with mock.patch("orch.docker_env.shutil.which", return_value=None), \
                mock.patch("orch.docker_env._run") as run:
            self.assertEqual(docker_env.collect({}), {"installed": False})
        run.assert_not_called()

    def test_credential_helpers_are_read_from_the_docker_config(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".docker").mkdir()
            (Path(home) / ".docker" / "config.json").write_text(
                json.dumps({"credsStore": "desktop", "credHelpers": {"ghcr.io": "pass"}}), encoding="utf-8")
            with mock.patch("orch.docker_env.shutil.which",
                            side_effect=lambda name: "/bin/x" if name.endswith("pass") else None):
                found = docker_env._credential_helpers(Path(home))
        self.assertEqual(found, {"store": "desktop", "helpers": {"desktop": False, "pass": True}})

    def test_orch_doctor_and_the_runs_never_ask_docker(self):
        with mock.patch("orch.docker_env.collect", side_effect=AssertionError("docker was asked")), \
                mock.patch("orch.docker_env._run", side_effect=AssertionError("docker was asked")):
            rows = {row["check_id"] for row in doctor_checks(None)}
        self.assertFalse({row for row in rows if row.startswith("orch.docker")})

    def test_the_probe_of_the_environment_doctor_is_the_script_apart_from_orch_doctor(self):
        unit = json.loads((Path(docker_env.__file__).resolve().parents[2] / "unit.json").read_text(encoding="utf-8"))
        probes = {row["id"]: row["probe"] for row in unit["provides"]["doctor"]}
        for name in ("orch.docker", "orch.docker-credentials", "orch.docker-compose"):
            self.assertEqual(probes[name], ["scripts/docker-env-check.py", "--json"])
        self.assertEqual(probes["orch.sandbox"], ["scripts/orch.py", "doctor", "--json"])

    def test_every_command_it_runs_is_short(self):
        calls = []
        with mock.patch("orch.docker_env.shutil.which", return_value="/usr/bin/docker"), \
                mock.patch("orch.docker_env._run", side_effect=lambda argv, timeout=5: calls.append(timeout) or (1, "", "x")):
            docker_env.collect({})
        self.assertTrue(calls and max(calls) <= 5, calls)

    def test_a_row_that_needs_action_points_to_the_instruction_once(self):
        row = rows_of(ROOTFUL)["orch.docker"]
        self.assertIn(docker_env.DOC, row["remediation"])
        self.assertNotIn("remediation", rows_of({**ROOTFUL, "security_options": ["name=rootless"],
                                                  "socket": {**ROOTFUL["socket"], "owned_by_user": True}})["orch.docker"])


if __name__ == "__main__":
    unittest.main()
