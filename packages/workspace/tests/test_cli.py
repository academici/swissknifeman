"""The command line: exit codes, one JSON object per command, errors as CODE: message, the shipped example and unit."""
import json
import os
import subprocess
import unittest
from unittest import mock

from tests import MODULE_ROOT, TempCase
from workspace import __version__


class UsageTests(TempCase):
    def test_help_forms(self):
        for argv in (["help"], ["-h"], ["--help"]):
            code, out, _ = self.run_cli(*argv)
            self.assertEqual(code, 0)
            self.assertIn("usage: workspace", out)

    def test_no_arguments_and_unknown_commands_are_usage_errors(self):
        for argv in ([], ["bogus"], ["project"], ["project", "bogus"], ["init", "--nope"], ["project", "rebind", "prj_X"],
                     ["project", "scan"], ["status", "extra"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("usage", err)

    def test_version(self):
        for argv in (["version"], ["--version"]):
            code, out, _ = self.run_cli(*argv)
            self.assertEqual((code, out.strip()), (0, __version__))


class CommandTests(TempCase):
    def test_init_status_doctor_in_json(self):
        init = self.json_cli("init")
        self.assertEqual(set(init), {"root", "workspace_id", "device_id", "created", "already_initialized"})
        self.assertTrue(init["workspace_id"].startswith("ws_"))
        self.assertEqual(self.json_cli("init")["already_initialized"], True)
        status = self.json_cli("status")
        self.assertEqual(set(status), {"root", "workspace_id", "git", "projects", "last_sync"})
        self.assertEqual(set(status["git"]), {"branch", "dirty", "remote", "ahead", "behind", "diverged", "fetched_at"})
        doctor = self.json_cli("doctor")
        self.assertEqual(set(doctor), {"checks"})
        self.assertEqual({item["status"] for item in doctor["checks"]}, {"ok"})

    def test_json_is_one_object_on_stdout(self):
        code, out, err = self.run_cli("init", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        json.loads(out)  # the whole stdout is one document

    def test_errors_are_code_and_message_on_stderr_with_exit_one(self):
        code, out, err = self.run_cli("status")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("WORKSPACE_NOT_INITIALIZED: "), err)
        self.ws.mkdir()
        (self.ws / "x").write_text("x", encoding="utf-8")
        code, _, err = self.run_cli("init", "--json")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("WORKSPACE_ROOT_NOT_EMPTY: "), err)

    def test_a_relative_workspace_root_is_exit_two(self):
        with mock.patch.dict(os.environ, {"SKM_WORKSPACE_ROOT": "relative"}):
            code, _, err = self.run_cli("init")
        self.assertEqual(code, 2)
        self.assertIn("SKM_WORKSPACE_ROOT", err)

    def test_doctor_exits_one_only_on_a_failure(self):
        self.assertEqual(self.run_cli("doctor")[0], 0)  # no workspace: a warning
        self.run_cli("init")
        (self.ws / "workspace.json").write_text("{", encoding="utf-8")
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[fail] workspace.layout", out)

    def test_init_with_root_names_the_variable_other_commands_need(self):
        other = self.root / "elsewhere"
        code, out, err = self.run_cli("init", "--root", str(other), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["root"], str(other))
        self.assertIn("SKM_WORKSPACE_ROOT=", err)

    def test_project_commands(self):
        self.run_cli("init")
        root = self.checkout("alpha")
        attached = self.json_cli("project", "attach", "--project", str(root))
        self.assertEqual(set(attached), {"project_id", "name", "created", "marker_written", "plans_store", "binding", "next"})
        project_id = attached["project_id"]
        listed = self.json_cli("project", "list")
        self.assertEqual([row["project_id"] for row in listed["projects"]], [project_id])
        shown = self.json_cli("project", "show", project_id)
        self.assertEqual(shown["project"]["project_id"], project_id)
        scan = self.json_cli("project", "scan", str(root.parent))
        self.assertEqual([item["path"] for item in scan["bound"]], [str(root)])
        moved = self.checkout("moved")
        code, _, err = self.run_cli("project", "rebind", project_id, "--path", str(moved), "--json")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("BINDING_MARKER_MISMATCH: "), err)
        detached = self.json_cli("project", "detach", project_id)
        self.assertEqual((detached["removed"], detached["binding"]), (True, None))

    def test_attach_without_a_project_context_is_refused(self):
        self.run_cli("init")
        empty = self.root / "empty"
        empty.mkdir()
        cwd = os.getcwd()
        os.chdir(empty)
        self.addCleanup(os.chdir, cwd)
        with mock.patch.dict(os.environ, {"HOME": str(empty)}):
            code, _, err = self.run_cli("project", "attach")
        self.assertEqual(code, 1)
        self.assertIn("PROJECT_CONTEXT_REQUIRED", err)

    def test_attach_without_confirmation_and_without_a_terminal(self):
        self.run_cli("init")
        first = self.checkout("alpha", remotes=[("origin", "git@github.com:a/b.git")])
        project_id = self.json_cli("project", "attach", "--project", str(first))["project_id"]
        second = self.checkout("beta", remotes=[("origin", "https://github.com/a/b")])
        code, _, err = self.run_cli("project", "attach", "--project", str(second))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("ATTACH_CONFIRM_REQUIRED: "), err)
        self.assertIn(project_id, err)
        attached = self.json_cli("project", "attach", "--project", str(second), "--yes")
        self.assertEqual(attached["project_id"], project_id)

    def test_attach_journals_its_event(self):
        self.run_cli("init")
        project_id = self.json_cli("project", "attach", "--project", str(self.checkout("alpha")))["project_id"]
        journal = self.root / "skm" / "state" / "events" / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["type"] for e in events], ["workspace.root.initialized", "workspace.project.attached"])
        self.assertEqual(events[1]["data"], {"project_id": project_id, "created": True})

    def test_a_failing_journal_does_not_change_the_result(self):
        with mock.patch("aicore.ext.events.emit", side_effect=RuntimeError("journal down")):
            code, out, err = self.run_cli("init", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["created"], True)
        self.assertIn("WORKSPACE_EVENT_NOT_EMITTED", err)


class ModuleFilesTests(unittest.TestCase):
    def test_the_example_matches_the_schema(self):
        from aicore.config.example import render_unit as render
        from aicore.config import units
        info = units.load_unit(MODULE_ROOT)
        self.assertIsNotNone(info)
        self.assertEqual((MODULE_ROOT / "config.example.toml").read_text(encoding="utf-8"), render(info))

    def test_the_unit_declares_what_the_code_does(self):
        unit = json.loads((MODULE_ROOT / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual((unit["id"], unit["kind"], unit["execution"]["project"]), ("workspace", "capability", "optional"))
        from workspace import events
        self.assertEqual(tuple(unit["provides"]["events"]), events.EVENT_TYPES)
        self.assertEqual({"aicore"}, {item["unit"] for item in unit["requires"]})

    def test_the_launcher_runs_the_module(self):
        done = subprocess.run([str(MODULE_ROOT / "bin" / "workspace"), "version"], capture_output=True, text=True,
                              env={**os.environ, "SKM_DEV_ALLOW_LIVE": "1"})
        self.assertEqual((done.returncode, done.stdout.strip()), (0, __version__), done.stderr)


if __name__ == "__main__":
    unittest.main()
