"""gui-orch commands: the argv the host builds from the descriptors, and what run.py runs for it (a fake orch)."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .test_queries import BRIDGE, FIXTURES, GUI_DOC, SKM_GUI_LIB  # noqa: F401

COMMANDS = {command["id"]: command for command in GUI_DOC["commands"]}
argv_mod = importlib.import_module("gui.core.argv")
inputs_mod = importlib.import_module("gui.core.inputs")
errors_mod = importlib.import_module("gui.errors")
PLAN = "PLAN1"
RUN = "cnd-new"


class CommandCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(os.path.realpath(self.tmp.name))
        self.project = self.home / "project"
        self.project.mkdir()

    def build(self, command_id, values, dry_run=False):
        command = COMMANDS[command_id]
        checked = inputs_mod.validate(command.get("input", ()), values, str(self.project), pointer="/input")
        return list(argv_mod.build(command, BRIDGE, checked, dry_run=dry_run).argv)

    def host_argv(self, command_id, values, dry_run=False):
        """The argv without the realpath of the program: what the host would run after ``run.py``."""
        built = self.build(command_id, values, dry_run)
        self.assertEqual(os.path.realpath(BRIDGE / "run.py"), built[0])
        return built[1:]

    def run_py(self, args, umbrella="umbrella-ok"):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "SKM_UMBRELLA": str(FIXTURES / umbrella)}
        return subprocess.run([sys.executable, str(BRIDGE / "run.py"), *args], cwd=str(self.project), env=env,
                              capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)

    def logged(self):
        log = self.home / "umbrella.log"
        return [json.loads(line)["argv"] for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class TestDescriptors(CommandCase):
    def test_policy_of_the_commands(self):
        ready, resume, release = (COMMANDS[f"gui-orch.{name}"] for name in ("run-ready", "resume", "release"))
        self.assertEqual(("high", "always"), (ready["risk"], ready["confirmation"]))
        self.assertEqual({"process.spawn", "plan.write", "project.write"}, set(ready["effects"]))
        self.assertEqual({"stream", "cancel", "dry-run"}, set(ready["supports"]))
        self.assertEqual(("medium", "risk-based"), (resume["risk"], resume["confirmation"]))
        self.assertEqual("always", release["confirmation"])
        for command in COMMANDS.values():
            with self.subTest(command=command["id"]):
                self.assertEqual("argv", command["exec"]["kind"])
                self.assertEqual("project", command["exec"]["cwd"])
                self.assertEqual("run.py", command["exec"]["argv"][0])
                self.assertTrue(all(isinstance(part, str) for part in command["exec"]["argv"]), "no input in the argv parts")
                self.assertNotIn("sh", command["exec"]["argv"][:1])
                self.assertTrue(os.access(BRIDGE / "run.py", os.X_OK))

    def test_run_ready_argv_is_exact(self):
        self.assertEqual(["run-ready", "--plan", PLAN, "--max-items", "3"],
                         self.host_argv("gui-orch.run-ready", {"plan": PLAN, "max_items": 3}))
        self.assertEqual(["run-ready", "--plan", PLAN, "--max-items", "3", "--dry-run"],
                         self.host_argv("gui-orch.run-ready", {"plan": PLAN, "max_items": 3}, dry_run=True))

    def test_resume_and_release_argv_are_exact(self):
        self.assertEqual(["resume", "--run", RUN], self.host_argv("gui-orch.resume", {"run_id": RUN}))
        self.assertEqual(["release", "--run", RUN, "--item", "P2.1"],
                         self.host_argv("gui-orch.release", {"run_id": RUN, "item": "P2.1"}))

    def test_bad_values_are_refused_by_the_host_before_any_argv(self):
        cases = [("gui-orch.run-ready", {"plan": "P1.1", "max_items": 3}),
                 ("gui-orch.run-ready", {"plan": PLAN, "max_items": 0}),
                 ("gui-orch.run-ready", {"plan": PLAN, "max_items": 21}),
                 ("gui-orch.run-ready", {"plan": PLAN, "max_items": "P1.1 P1.2"}),
                 ("gui-orch.run-ready", {"plan": PLAN}),
                 ("gui-orch.run-ready", {"plan": f"{PLAN} --items P1.1", "max_items": 2}),
                 ("gui-orch.resume", {"run_id": "../x"}), ("gui-orch.resume", {"run_id": "cnd-a b"}),
                 ("gui-orch.resume", {"run_id": "--run"}), ("gui-orch.release", {"run_id": RUN, "item": "-x"}),
                 ("gui-orch.release", {"run_id": RUN, "item": "P1.1 P1.2"}), ("gui-orch.release", {"run_id": RUN})]
        for command_id, values in cases:
            with self.subTest(command=command_id, values=values), self.assertRaises(errors_mod.GuiError):
                self.build(command_id, values)

    def test_dry_run_is_a_literal_flag_not_user_text(self):
        self.assertEqual({"argv_append": ["--dry-run"]}, COMMANDS["gui-orch.run-ready"]["dry_run"])
        self.assertNotIn("dry_run", {field["name"] for field in COMMANDS["gui-orch.run-ready"]["input"]})


class TestRunPy(CommandCase):
    def test_run_ready_runs_orch_with_ready_and_a_count(self):
        result = self.run_py(["run-ready", "--plan", PLAN, "--max-items", "3"])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([["orch", "conduct", "run", "--plan", PLAN, "--ready", "--max-items", "3"]], self.logged())

    def test_run_ready_dry_run_resume_release(self):
        self.assertEqual(0, self.run_py(["run-ready", "--plan", PLAN, "--max-items", "20", "--dry-run"]).returncode)
        self.assertEqual(0, self.run_py(["resume", "--run", RUN]).returncode)
        self.assertEqual(0, self.run_py(["release", "--run", RUN, "--item", "P2.1"]).returncode)
        self.assertEqual([["orch", "conduct", "run", "--plan", PLAN, "--ready", "--max-items", "20", "--dry-run"],
                          ["orch", "conduct", "resume", "--run", RUN],
                          ["orch", "conduct", "release", "--run", RUN, "--item", "P2.1"]], self.logged())

    def test_anything_else_exits_2_without_running_orch(self):
        for args in ([], ["status"], ["run-ready"], ["run-ready", "--plan", PLAN], ["run-ready", "--plan", PLAN, "--max-items", "0"],
                     ["run-ready", "--plan", PLAN, "--max-items", "99"], ["run-ready", "--plan", PLAN, "--max-items", "3x"],
                     ["run-ready", "--plan", PLAN, "--max-items", "3", "--items", "P1.1"],
                     ["run-ready", "--max-items", "3", "--plan", PLAN], ["run-ready", "--plan", "P1.1", "--max-items", "2"],
                     ["resume"], ["resume", "--run", "../x"], ["resume", "--run", RUN, "--retry", "P1.1"],
                     ["release", "--run", RUN], ["release", "--run", RUN, "--all"], ["release", "--run", RUN, "--item", "-x"],
                     ["release", "--run", RUN, "--item", "P1.1", "--reason", "x"]):
            with self.subTest(args=args):
                result = self.run_py(args)
                self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual([], self.logged())

    def test_a_missing_hub_command_line_is_reported(self):
        env = {"PATH": "/nonexistent", "HOME": str(self.home)}
        result = subprocess.run([sys.executable, str(BRIDGE / "run.py"), "resume", "--run", RUN], cwd=str(self.project),
                                env=env, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        self.assertEqual(1, result.returncode)
        self.assertIn("ORCH_UNAVAILABLE", result.stderr)


class TestBoundaries(unittest.TestCase):
    def test_the_bridge_names_no_module_folder_and_reads_no_state_folder(self):
        for name in ("adapter.py", "run.py", "gui.json", "extension.json", "unit.json"):
            text = (BRIDGE / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertNotIn("packages/", text)
                self.assertNotIn("state/orch", text)
                self.assertNotIn("import orch", text)
                self.assertNotIn("from orch", text)


if __name__ == "__main__":
    unittest.main()
