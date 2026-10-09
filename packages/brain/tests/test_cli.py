"""CLI: exit codes, --json forms, doctor output validated against check-result/v1."""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import aicore
from aicore.util import schema

from brain import cli, doctor, settings
from tests.support import TempCase

CHECK_RESULT = Path(aicore.__file__).resolve().parents[2] / "schemas" / "check-result" / "v1"


class CliCase(TempCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        environment = {"HOME": str(self.home), "SKM_HOME": str(self.root / "skm"), "PATH": os.environ.get("PATH", "")}
        with mock.patch.dict(os.environ, environment, clear=True), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
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
        self.assertEqual({"brain.vault", "brain.config", "brain.notes-folder"}, set(by_id))

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


if __name__ == "__main__":
    unittest.main()
