"""run.py: a fixed set of verbs, each checked before `workspace ... --json` starts; gui.json declares them with the
confirmations the plan requires and argv descriptors the GUI broker accepts."""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1]
FIXTURES = BRIDGE / "tests" / "fixtures"
GUI_DOC = json.loads((BRIDGE / "gui.json").read_text(encoding="utf-8"))
COMMANDS = {command["id"].split(".", 1)[1]: command for command in GUI_DOC["commands"]}
ALWAYS = {"migrate-apply", "migrate-cleanup", "sync-push", "sync-resolve", "connect", "init-remote", "project-remove"}


class TestDescriptors(unittest.TestCase):
    def test_confirmation_levels(self):
        self.assertEqual(ALWAYS, {name for name, c in COMMANDS.items() if c["confirmation"] == "always"})
        self.assertEqual({"migrate-plan", "migrate-verify"}, {n for n, c in COMMANDS.items() if c["confirmation"] == "none"})
        self.assertEqual({"init", "project-add", "project-attach", "project-link", "project-unlink", "project-scan",
                          "project-rebind", "sync-commit", "sync-pull", "sync-resolve-reset"}, {n for n, c in COMMANDS.items() if c["confirmation"] == "risk-based"})

    def test_every_command_is_a_fixed_argv_of_run_py(self):
        for name, command in COMMANDS.items():
            with self.subTest(command=name):
                self.assertEqual("argv", command["exec"]["kind"])
                self.assertEqual(["run.py", name], command["exec"]["argv"][:2])
                self.assertTrue((BRIDGE / "run.py").is_file())
                fields = {f["name"]: f for f in command.get("input", ())}
                for part in command["exec"]["argv"][2:]:
                    self.assertIn(part["input"], fields)
                    self.assertNotIn("flag", fields[part["input"]])
                for field in fields.values():
                    self.assertIn(field["type"], ("string", "enum", "project-path", "boolean"))
                    if field["type"] == "boolean":  # a switch is a flag without a value
                        self.assertTrue(field["flag"].startswith("--"))
                        self.assertFalse(field["required"])
                self.assertIn("stream", command["supports"])
                self.assertIn("cancel", command["supports"])

    def test_forms_of_the_workspace_pages(self):
        """D4: create a workspace (alone and bound to a remote), connect a remote, add a project, bind a checkout."""
        routes = {r["id"]: r["actions"] for r in GUI_DOC["routes"]}
        self.assertEqual(["gui-workspace.init", "gui-workspace.init-remote", "gui-workspace.connect"],
                         routes["gui-workspace.overview"])
        self.assertEqual(["gui-workspace.project-add", "gui-workspace.project-remove", "gui-workspace.project-attach",
                          "gui-workspace.project-link", "gui-workspace.project-unlink", "gui-workspace.project-scan",
                          "gui-workspace.project-rebind"], routes["gui-workspace.projects"])
        required = lambda name: {f["name"] for f in COMMANDS[name]["input"] if f["required"]}
        self.assertEqual({"code", "remote"}, required("init-remote"))
        self.assertEqual({"path"}, required("project-add"))
        toggle = {f["name"]: f for f in COMMANDS["project-add"]["input"]}["link_folders"]
        self.assertEqual(("boolean", "--link-folders", False), (toggle["type"], toggle["flag"], toggle["required"]))
        self.assertIn("link_folders", {f["name"] for f in COMMANDS["project-attach"]["input"]})
        self.assertEqual({"project"}, required("project-link"))
        self.assertEqual({"project"}, required("project-unlink"))
        self.assertEqual({"project_id"}, required("project-remove"))
        self.assertEqual({"high"}, {COMMANDS[n]["risk"] for n in ("init-remote", "project-remove")})
        for name in ("init-remote", "project-add", "project-remove"):
            self.assertEqual("gui-workspace:workspace", COMMANDS[name]["concurrency_key"])
        self.assertIn("network", COMMANDS["init-remote"]["effects"])

    def test_long_commands_have_time(self):
        self.assertGreaterEqual(COMMANDS["migrate-apply"]["timeout_s"], 3600)
        self.assertGreaterEqual(COMMANDS["migrate-cleanup"]["timeout_s"], 3600)

    def test_every_verb_of_run_py_is_declared(self):
        sys.path.insert(0, str(BRIDGE))
        run = importlib.import_module("run")
        self.assertEqual(set(COMMANDS), set(run.SPEC))

    def test_routes_and_widget(self):
        routes = {r["id"]: r for r in GUI_DOC["routes"]}
        # The contract asks for the section `workspace` (orders 10..50); the schema of the GUI knows no such section
        # yet, so the pages sit in `fleet` after gui-hub (orders 110..150).
        self.assertEqual({"gui-workspace." + n: v for n, v in (("overview", 110), ("projects", 120), ("migration", 130),
                                                               ("sync", 140), ("conflicts", 150))},
                         {i: r["nav"]["order"] for i, r in routes.items()})
        self.assertEqual({"fleet"}, {r["nav"]["section"] for r in routes.values()})
        widget = GUI_DOC["widgets"][0]
        self.assertEqual(("gui-workspace.summary", "metric-group", "fleet"),
                         (widget["id"], widget["view"], widget["scope"]))


class RunCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        (self.home / "proj").mkdir()
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
                    "SKM_WORKSPACE_MODULE_ROOT": str(FIXTURES / "module")}

    def run_py(self, *argv, **env):
        return subprocess.run([sys.executable, str(BRIDGE / "run.py"), *argv], cwd=str(self.home),
                              env={**self.env, **env}, capture_output=True, text=True, timeout=60)

    def calls(self):
        log = self.home / "workspace.log"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def ran(self, *argv, **env):
        result = self.run_py(*argv, **env)
        self.assertEqual(0, result.returncode, result.stderr)
        return self.calls()[-1]


class TestRun(RunCase):
    def test_argv_of_each_verb(self):
        proj = str(self.home / "proj")
        self.assertEqual(["init", "--code", "axioma", "--json"], self.ran("init", "axioma"))
        self.assertEqual(["project", "attach", "--project", proj, "--json"], self.ran("project-attach", proj))
        self.assertEqual(["init", "--code", "axioma", "--remote", "ssh://git@example.com/team/ws.git", "--json"],
                         self.ran("init-remote", "axioma", "ssh://git@example.com/team/ws.git"))
        self.assertEqual(["project", "add", "--path", proj, "--json"], self.ran("project-add", proj))
        self.assertEqual(["project", "add", "--path", proj, "--name", "Alpha app", "--code", "alpha", "--json"],
                         self.ran("project-add", proj, "--name", "Alpha app", "--code", "alpha"))
        self.assertEqual(["project", "add", "--path", proj, "--link-folders", "--json"],
                         self.ran("project-add", proj, "--link-folders"))
        self.assertEqual(["project", "add", "--path", proj, "--link-folders", "--name", "Alpha", "--json"],
                         self.ran("project-add", proj, "--link-folders", "--name", "Alpha"))
        self.assertEqual(["project", "attach", "--project", proj, "--link-folders", "--json"],
                         self.ran("project-attach", proj, "--link-folders"))
        self.assertEqual(["project", "link", "--project", proj, "--json"], self.ran("project-link", proj))
        self.assertEqual(["project", "unlink", "--project", proj, "--json"], self.ran("project-unlink", proj))
        self.assertEqual(["project", "remove", "alpha", "--json"], self.ran("project-remove", "alpha"))
        self.assertEqual(["project", "scan", proj, "--json"], self.ran("project-scan", proj))
        self.assertEqual(["project", "rebind", "p-alpha", "--path", proj, "--json"],
                         self.ran("project-rebind", "p-alpha", proj))
        self.assertEqual(["migrate", "plan", "--project", proj, "--on-conflict", "import-copy", "--json"],
                         self.ran("migrate-plan", proj, "--on-conflict", "import-copy"))
        self.assertEqual(["migrate", "apply", "--project", proj, "--yes", "--json"], self.ran("migrate-apply", proj))
        self.assertEqual(["migrate", "verify", "--project", proj, "--json"], self.ran("migrate-verify", proj))
        self.assertEqual(["sync", "--commit", "--json"], self.ran("sync-commit"))
        self.assertEqual(["sync", "--pull", "--json"], self.ran("sync-pull"))
        self.assertEqual(["sync", "--resolve", "a/b.json=remote", "--json"], self.ran("sync-resolve", "a/b.json", "remote"))
        self.assertEqual(["sync", "--resolve-reset", "--json"], self.ran("sync-resolve-reset"))
        self.assertEqual(["connect", "--remote", "git@example.com:team/plans.git", "--branch", "main", "--json"],
                         self.ran("connect", "git@example.com:team/plans.git", "--branch", "main"))

    def test_nothing_else_runs(self):
        proj = str(self.home / "proj")
        bad = [(), ("rm",), ("sync-push", "--force"), ("sync-commit", "x"), ("init", "--root"), ("init", "--root", proj), ("init", "--yes", "x"),
               ("init-remote", "axioma"), ("init-remote", "Axioma", "git@example.com:t/w.git"),
               ("init-remote", "axioma", "https://user:token123@example.com/w.git"),
               ("init-remote", "axioma", "https://token123@example.com/w.git"), ("init-remote", "axioma", "-x"),
               ("init-remote", "axioma", "git@example.com:t/w.git", "--root", proj),
               ("project-add",), ("project-add", "relative/dir"), ("project-add", str(self.home / "missing")),
               ("project-add", proj, "--name", "-x"), ("project-add", proj, "--name", "a\nb"),
               ("project-add", proj, "--name", ""), ("project-add", proj, "--code", "Bad Code"),
               ("project-add", proj, "--yes"), ("project-add", proj, "--path", proj),
               ("project-remove",), ("project-remove", "-x"), ("project-remove", "a b"), ("project-remove", "a", "b"),
               ("project-remove", "a", "--force"),
               ("project-add", proj, "--link-folders", "yes"), ("project-add", proj, "--link-folders", "--link-folders"),
               ("project-attach", proj, "--link-folders=1"), ("project-link",), ("project-link", "relative/dir"),
               ("project-link", proj, "--link-folders"), ("project-unlink", str(self.home / "missing")), ("project-unlink", "-rf"),
               ("project-attach", "relative/dir"), ("project-attach", str(self.home / "missing")),
               ("project-attach", "-rf"), ("project-rebind", "-x", proj), ("project-rebind", "a b", proj),
               ("migrate-plan", proj, "--on-conflict", "overwrite"), ("migrate-apply", proj, "--lock-timeout", "1"),
               ("sync-resolve", "../x", "local"), ("sync-resolve", "/abs", "local"), ("sync-resolve", "a=b", "local"),
               ("sync-resolve", "a", "both"), ("connect", "--remote"), ("connect", "x", "--branch", "-d"),
               ("connect", "https://user:token123@example.com/r.git"), ("connect", "https://token@example.com/r.git"),
               ("connect", "ssh://git:secret@example.com/r.git")]
        for argv in bad:
            with self.subTest(argv=argv):
                result = self.run_py(*argv)
                self.assertEqual(2, result.returncode, result.stderr)
                self.assertNotIn("token123", result.stderr + result.stdout)
        self.assertEqual([], self.calls())

    def test_ssh_user_without_password_is_fine(self):
        self.assertEqual(["connect", "--remote", "ssh://git@example.com/r.git", "--json"],
                         self.ran("connect", "ssh://git@example.com/r.git"))

    def test_cleanup_needs_the_project_id_of_the_folder(self):
        proj = str(self.home / "proj")
        # Not bound: the fixture binds p-alpha to /work/alpha only.
        result = self.run_py("migrate-cleanup", proj, "p-alpha")
        self.assertEqual(2, result.returncode)
        self.assertIn("PROJECT_NOT_BOUND", result.stderr)
        # Bound, but the typed id is another one.
        result = self.run_py("migrate-cleanup", proj, "p-beta", FAKE_WORK=proj)
        self.assertEqual(2, result.returncode)
        self.assertIn("CONFIRM_MISMATCH", result.stderr)
        self.assertNotIn("cleanup", [c[1] for c in self.calls() if len(c) > 1])
        self.assertEqual(["migrate", "cleanup", "--project", proj, "--confirm", "p-alpha", "--json"],
                         self.ran("migrate-cleanup", proj, "p-alpha", FAKE_WORK=proj))

    def test_push_prints_remote_and_branch_first(self):
        result = self.run_py("sync-push")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(result.stdout.startswith("pushing to https://example.com/team/plans.git branch main\n"),
                        result.stdout)
        self.assertEqual(["sync", "--push", "--json"], self.calls()[-1])

    def test_push_refuses_userinfo_and_missing_remote(self):
        self.assertEqual(1, self.run_py("sync-push", FAKE_LEAK="1").returncode)
        self.assertNotIn(["sync", "--push", "--json"], self.calls())
        result = self.run_py("sync-push", FAKE_BARE="1")
        self.assertEqual(2, result.returncode)
        self.assertIn("NO_REMOTE", result.stderr)

    def test_cli_failure_is_passed_through(self):
        result = self.run_py("sync-pull", FAKE_FAIL="1")
        self.assertEqual(1, result.returncode)
        self.assertIn("WORKSPACE_FAILED", result.stderr)

    def test_missing_workspace_cli(self):
        result = self.run_py("sync-pull", SKM_WORKSPACE_MODULE_ROOT=str(self.home))
        self.assertEqual(1, result.returncode)
        self.assertIn("WORKSPACE_UNAVAILABLE", result.stderr)


if __name__ == "__main__":
    unittest.main()
