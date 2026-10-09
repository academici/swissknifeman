"""CLI: exit codes, --json forms, doctor output validated against check-result/v1."""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema

from brain import cli, doctor, settings
from tests.support import EVENTS, MODULE_ROOT, TempCase

CHECK_RESULT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"


class CliCase(TempCase):
    def run_cli(self, *args, stdin=None, extra_env=None):
        out, err = io.StringIO(), io.StringIO()
        environment = {**self.env, "PATH": os.environ.get("PATH", ""), "SKM_UNITS_PATH": str(MODULE_ROOT),
                       **(extra_env or {})}
        with mock.patch.dict(os.environ, environment, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin or b""))):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def configure_vault(self):
        self.machine_config(f'[brain]\nvault_path = "{self.vault}"\n')


class TestUsage(CliCase):
    def test_help_forms(self):
        for argv in (["help"], ["-h"], ["--help"]):
            code, out, _ = self.run_cli(*argv)
            self.assertEqual(0, code)
            self.assertIn("usage: brain", out)

    def test_empty_and_unknown_command_are_usage_errors(self):
        self.assertEqual(2, self.run_cli()[0])
        code, _, err = self.run_cli("frobnicate")
        self.assertEqual(2, code)
        self.assertIn("frobnicate", err)

    def test_unknown_option_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("vault", "--nope")
        self.assertEqual(2, caught.exception.code)

    def test_version(self):
        code, out, _ = self.run_cli("version")
        self.assertEqual(0, code)
        self.assertRegex(out, r"^brain 0\.1\.0 \(.+\)\n$")


class TestVault(CliCase):
    def test_without_vault_exits_1(self):
        code, out, err = self.run_cli("vault", "--project", str(self.project))
        self.assertEqual((1, ""), (code, out))
        self.assertIn("VAULT_NOT_FOUND", err)

    def test_without_vault_json_prints_the_state(self):
        code, out, _ = self.run_cli("vault", "--json", "--project", str(self.project))
        self.assertEqual(1, code)
        self.assertEqual("none", json.loads(out)["source"])

    def test_found(self):
        self.configure_vault()
        code, out, _ = self.run_cli("vault", "--project", str(self.project))
        self.assertEqual(0, code)
        self.assertIn(str(self.vault), out)
        self.assertIn("source: config", out)

    def test_found_json(self):
        self.configure_vault()
        code, out, _ = self.run_cli("vault", "--json", "--project", str(self.project))
        self.assertEqual(0, code)
        self.assertEqual({"path": str(self.vault), "source": "config", "exists": True, "obsidian": True,
                          "warnings": []}, json.loads(out))

    def test_missing_directory_exits_1(self):
        self.machine_config('[brain]\nvault_path = "/does/not/exist"\n')
        code, _, err = self.run_cli("vault", "--project", str(self.project))
        self.assertEqual(1, code)
        self.assertIn("VAULT_MISSING", err)

    def test_legacy_warning_is_printed_once(self):
        self.legacy({"path": str(self.vault)})
        code, _, err = self.run_cli("vault", "--project", str(self.project))
        self.assertEqual(0, code)
        self.assertEqual((1, 1), (err.count(settings.LEGACY_VAULT_WARNING), err.count(settings.LEGACY_DOCS_WARNING)))

    def test_invalid_configuration_exits_1(self):
        self.project_config('[brain.docs]\ndirection = "sideways"\n')
        code, _, err = self.run_cli("vault", "--project", str(self.project))
        self.assertEqual(1, code)
        self.assertIn("direction", err)


class TestProject(CliCase):
    def test_found_by_control_note(self):
        self.configure_vault()
        self.claim_project(self.project)
        code, out, _ = self.run_cli("project", "--project", str(self.project), "--json")
        self.assertEqual(0, code)
        self.assertEqual({"project": str(self.project), "vault": str(self.vault),
                          "folder": str(self.vault / "05-Projects" / "03-Packages" / "Demo"), "name": "Demo",
                          "via": "control-note"}, json.loads(out))

    def test_text_form(self):
        self.configure_vault()
        self.claim_project(self.project)
        code, out, _ = self.run_cli("project", "--project", str(self.project))
        self.assertEqual(0, code)
        self.assertIn("Demo", out)

    def test_not_in_vault(self):
        self.configure_vault()
        code, out, err = self.run_cli("project", "--project", str(self.project), "--json")
        self.assertEqual(1, code)
        self.assertEqual({"folder": None, "name": None, "via": None},
                         {k: json.loads(out)[k] for k in ("folder", "name", "via")})
        self.assertIn("PROJECT_NOT_IN_VAULT", err)

    def test_without_vault(self):
        code, _, err = self.run_cli("project", "--project", str(self.project))
        self.assertEqual(1, code)
        self.assertIn("VAULT_NOT_FOUND", err)

    def test_default_project_is_found_from_the_working_directory(self):
        self.configure_vault()
        self.claim_project(self.project)
        nested = self.project / "src"
        nested.mkdir()
        before = os.getcwd()
        os.chdir(nested)
        self.addCleanup(os.chdir, before)
        code, out, _ = self.run_cli("project", "--json")
        self.assertEqual((0, str(self.project)), (code, json.loads(out)["project"]))


class TestDoctor(CliCase):
    def validate(self, documents):
        registry, kind = schema.load_contract(CHECK_RESULT)
        self.assertIsInstance(documents, list)
        for document in documents:
            self.assertEqual([], schema.validate(document, kind, registry), document)

    def checks(self, *extra):
        code, out, _ = self.run_cli("doctor", "--json", "--project", str(self.project), *extra)
        documents = json.loads(out)
        self.validate(documents)
        return code, {d["check_id"]: d for d in documents}

    def test_without_vault_is_a_warning_not_a_failure(self):
        code, by_id = self.checks()
        self.assertEqual(0, code)
        self.assertEqual("warn", by_id["brain.vault"]["status"])
        self.assertIn("aicore config set brain.vault_path <dir> --machine", by_id["brain.vault"]["remediation"])
        self.assertEqual({"brain.vault", "brain.config", "brain.notes-folder", "brain.subscription"}, set(by_id))

    def test_healthy(self):
        self.configure_vault()
        code, by_id = self.checks()
        self.assertEqual(0, code)
        self.assertEqual({"ok"}, {d["status"] for d in by_id.values()})

    def test_missing_vault_directory_fails(self):
        self.machine_config('[brain]\nvault_path = "/does/not/exist"\n')
        code, by_id = self.checks()
        self.assertEqual((1, "fail"), (code, by_id["brain.vault"]["status"]))

    def test_vault_without_obsidian_warns(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.machine_config(f'[brain]\nvault_path = "{plain}"\n')
        code, by_id = self.checks()
        self.assertEqual((0, "warn"), (code, by_id["brain.vault"]["status"]))

    def test_legacy_sources_warn_in_config_check(self):
        self.legacy({"path": str(self.vault)})
        code, by_id = self.checks()
        self.assertEqual((0, "warn", "ok"), (code, by_id["brain.config"]["status"], by_id["brain.vault"]["status"]))
        self.assertTrue(by_id["brain.config"]["evidence"])

    def test_legacy_warning_is_reported_once(self):
        self.legacy({"path": str(self.vault)})
        _, out, _ = self.run_cli("doctor", "--project", str(self.project))
        self.assertEqual(1, out.count(settings.LEGACY_VAULT_WARNING))

    def test_legacy_variable_warning_is_reported_once(self):
        documents = doctor.run_checks(self.project, env={**self.env, "MAIND_BRAIN_VAULT": str(self.vault)},
                                      home=self.home)
        evidence = [line for d in documents for line in d.get("evidence", []) if line.startswith("BRAIN_LEGACY_ENV")]
        self.assertEqual(1, len(evidence))

    def test_ignored_environment_variable_warns(self):
        documents = doctor.run_checks(self.project, env={**self.env, "SKM_BRAIN_NOT_A_KEY": "1"}, home=self.home)
        by_id = {d["check_id"]: d for d in documents}
        self.assertEqual("warn", by_id["brain.config"]["status"])
        self.assertTrue(any("CONFIG_ENV_UNKNOWN" in line for line in by_id["brain.config"]["evidence"]))

    def test_invalid_configuration_fails_config_check(self):
        self.project_config('[brain.docs]\ndirection = "sideways"\n')
        code, by_id = self.checks()
        self.assertEqual((1, "fail", "skip"), (code, by_id["brain.config"]["status"], by_id["brain.vault"]["status"]))

    def test_notes_folder_inside_synced_folder_fails(self):
        self.project_config('[brain.notes]\nfolder = "docs/notes"\n')
        code, by_id = self.checks()
        self.assertEqual((1, "fail"), (code, by_id["brain.notes-folder"]["status"]))

    def test_text_form(self):
        code, out, _ = self.run_cli("doctor", "--project", str(self.project))
        self.assertEqual(0, code)
        self.assertIn("[warn] brain.vault", out)
        self.assertIn("[ok] brain.config", out)


class TestNote(CliCase):
    def event(self, name):
        return (EVENTS / f"{name}.json").read_bytes()

    def test_writes_a_note_and_answers_with_one_json_object(self):
        self.configure_vault()
        self.claim_project(self.project)
        code, out, err = self.run_cli("note", "--event", "-", "--project", str(self.project),
                                      stdin=self.event("valid-full"))
        self.assertEqual((0, ""), (code, err))
        answer = json.loads(out)
        self.assertEqual(1, len(out.splitlines()))
        self.assertEqual("ok", answer["status"])
        self.assertTrue((self.vault / answer["note"]).is_file())
        code, out, _ = self.run_cli("note", "--event", "-", "--project", str(self.project),
                                    stdin=self.event("valid-full"))
        self.assertEqual((0, "DUPLICATE_EVENT"), (code, json.loads(out)["reason"]))

    def test_event_from_a_file_and_json_flag(self):
        self.configure_vault()
        code, out, _ = self.run_cli("note", "--event", str(EVENTS / "valid-minimal.json"), "--json")
        self.assertEqual((0, "ok"), (code, json.loads(out)["status"]))

    def test_project_from_the_environment_wins(self):
        self.configure_vault()
        self.claim_project(self.project)
        code, out, _ = self.run_cli("note", "--event", "-", stdin=self.event("valid-minimal"),
                                    extra_env={"SKM_PROJECT_ROOT": str(self.project)})
        self.assertEqual(0, code)
        self.assertIn("05-Projects/03-Packages/Demo/Ecosystem/Plans/", json.loads(out)["note"])

    def test_dry_run(self):
        self.configure_vault()
        code, out, _ = self.run_cli("note", "--event", "-", "--dry-run", stdin=self.event("valid-minimal"))
        self.assertEqual((0, "DRY_RUN"), (code, json.loads(out)["reason"]))
        self.assertFalse((self.vault / "Ecosystem").exists())

    def test_without_a_vault_the_event_is_skipped(self):
        code, out, _ = self.run_cli("note", "--event", "-", stdin=self.event("valid-minimal"))
        self.assertEqual((0, {"status": "skipped", "reason": "VAULT_NOT_CONFIGURED"}), (code, json.loads(out)))

    def test_other_events_are_skipped(self):
        self.configure_vault()
        code, out, _ = self.run_cli("note", "--event", "-", stdin=self.event("other-type"))
        self.assertEqual((0, "EVENT_TYPE_IGNORED"), (code, json.loads(out)["reason"]))

    def test_bad_data_exits_65_with_an_empty_stdout(self):
        self.configure_vault()
        for name in ("invalid-no-plan-id", "invalid-data-not-object", "invalid-specversion"):
            with self.subTest(fixture=name):
                code, out, err = self.run_cli("note", "--event", "-", stdin=self.event(name))
                self.assertEqual((65, ""), (code, out))
                self.assertIn("brain: EVENT_DATA_INVALID:", err)

    def test_unreadable_input_exits_65(self):
        for stdin in (b"", b"{not json", b"\xff\xfe"):
            with self.subTest(stdin=stdin):
                code, out, err = self.run_cli("note", "--event", "-", stdin=stdin)
                self.assertEqual((65, ""), (code, out))
                self.assertIn("EVENT_DATA_INVALID", err)
        code, out, err = self.run_cli("note", "--event", str(self.root / "missing.json"))
        self.assertEqual((65, ""), (code, out))

    def test_temporary_failures_exit_75(self):
        self.machine_config(f'[brain]\nvault_path = "{self.root / "gone"}"\n')
        code, out, err = self.run_cli("note", "--event", "-", stdin=self.event("valid-minimal"))
        self.assertEqual((75, ""), (code, out))
        self.assertIn("brain: VAULT_UNAVAILABLE:", err)

    def test_an_invalid_configuration_exits_75(self):
        self.project_config('[brain.notes]\nfolder = "docs/notes"\n')
        code, out, err = self.run_cli("note", "--event", "-", "--project", str(self.project),
                                      stdin=self.event("valid-minimal"))
        self.assertEqual((75, ""), (code, out))
        self.assertIn("CONFIG_NOTES_FOLDER", err)

    def test_the_event_option_is_required(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("note")
        self.assertEqual(2, caught.exception.code)


class TestSubscriptionCheck(CliCase):
    def check(self, env=None):
        documents = doctor.run_checks(self.project, env={**self.env, "SKM_UNITS_PATH": str(MODULE_ROOT), **(env or {})},
                                      home=self.home)
        return {d["check_id"]: d for d in documents}["brain.subscription"]

    def test_declared_and_enabled(self):
        self.assertEqual("ok", self.check()["status"])

    def test_switched_off_by_the_configuration_warns(self):
        self.machine_config('[aicore.subscriptions."brain:plan-notes"]\nenabled = false\n')
        result = self.check()
        self.assertEqual("warn", result["status"])
        self.assertIn("switched off", result["observed"])

    def test_not_visible_to_aicore_warns(self):
        empty = self.root / "no-units"
        empty.mkdir()
        result = self.check({"SKM_UNITS_PATH": str(empty)})
        self.assertEqual("warn", result["status"])
        self.assertIn("SKM_UNITS_PATH", result["remediation"])

    def test_notes_disabled_warns(self):
        self.machine_config('[brain.notes]\nenabled = false\n')
        self.assertEqual("warn", self.check()["status"])

    def test_listed_even_when_the_configuration_is_invalid(self):
        self.project_config('[brain.docs]\ndirection = "sideways"\n')
        documents = doctor.run_checks(self.project, env={**self.env, "SKM_UNITS_PATH": str(MODULE_ROOT)}, home=self.home)
        self.assertIn("brain.subscription", {d["check_id"] for d in documents})


if __name__ == "__main__":
    unittest.main()
