"""The SKM environment variables: the table, the shell-profile snippet (install, uninstall, idempotency), a fresh shell,
the ``aicore shell-env`` command, the doctor checks and the project launcher with and without the variables."""
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aicore import cli as aicore_cli
from aicore.project import cli as project_cli
from aicore.project import artifacts
from aicore.state import envtable, shellenv
from aicore.state import locations as loc
from aicore.state.shellenv_cli import main as shell_env_main

WORKSPACE_JSON = {"$schema": "urn:swissknifeman:aicore:workspace:v1"}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.skm = self.tmp / "skm"
        self.bashrc = self.home / ".bashrc"
        self.env = {"HOME": str(self.home), "SHELL": "/bin/bash", "SKM_HOME": str(self.skm), "PATH": os.environ.get("PATH", "")}

    def workspace(self, code="axioma"):
        folder = self.skm / "workspaces" / code
        folder.mkdir(parents=True)
        (folder / loc.WORKSPACE_FILE).write_text("{}", encoding="utf-8")
        return folder

    def planned(self, **extra):
        return shellenv.planned_values(dict(self.env, **extra))


class TableTests(unittest.TestCase):
    def test_the_names_are_fixed_in_one_table(self):
        self.assertEqual(envtable.NAMES, ("SKM_HOME", "SKM_WORKSPACES", "SKM_WORKSPACE"))
        self.assertEqual([item.name for item in envtable.TABLE], list(envtable.NAMES))
        self.assertEqual(loc.ENV_WORKSPACE, envtable.ENV_WORKSPACE)
        self.assertEqual(loc.ENV_WORKSPACES, envtable.ENV_WORKSPACES)
        self.assertEqual(loc.ENV_WORKSPACES_ROOT, envtable.ENV_WORKSPACES_ROOT)

    def test_a_plugin_environment_passes_the_variables_of_the_table(self):
        from aicore.ext.environment import BASE_ALLOW
        for name in envtable.NAMES:
            self.assertIn(name, BASE_ALLOW)

    def test_the_workspaces_folder_is_read_from_skm_workspaces_after_the_older_name(self):
        env = {"SKM_HOME": "/sb", "SKM_WORKSPACES": "/data/ws"}
        self.assertEqual(loc.workspaces_root(env), Path("/data/ws"))
        self.assertEqual(loc.workspaces_root(dict(env, SKM_WORKSPACES_ROOT="/older")), Path("/older"))
        self.assertEqual(loc.workspaces_root({"SKM_HOME": "/sb", "SKM_WORKSPACES": ""}), Path("/sb/workspaces"))
        with self.assertRaises(ValueError) as caught:
            loc.workspaces_root({"SKM_WORKSPACES": "relative"})
        self.assertIn("SKM_WORKSPACES", str(caught.exception))


class ValuesTests(Base):
    def test_a_machine_exports_its_home_the_workspaces_folder_and_the_only_workspace(self):
        self.workspace()
        values, notes = self.planned()
        self.assertEqual(values, {"SKM_HOME": str(self.skm), "SKM_WORKSPACES": str(self.skm / "workspaces"),
                                  "SKM_WORKSPACE": "axioma"})
        self.assertEqual(notes, [])

    def test_no_workspace_leaves_the_code_out_with_a_note(self):
        values, notes = self.planned()
        self.assertNotIn("SKM_WORKSPACE", values)
        self.assertIn("no workspace", notes[0])

    def test_several_workspaces_need_a_choice_and_the_environment_is_the_choice(self):
        self.workspace("axioma")
        self.workspace("other")
        values, notes = self.planned()
        self.assertNotIn("SKM_WORKSPACE", values)
        self.assertIn("several workspaces", notes[0])
        self.assertEqual(self.planned(SKM_WORKSPACE="other")[0]["SKM_WORKSPACE"], "other")

    def test_the_workspaces_folder_follows_the_overrides(self):
        self.assertEqual(self.planned(SKM_WORKSPACES="/data/ws")[0]["SKM_WORKSPACES"], "/data/ws")
        self.assertEqual(self.planned(SKM_WORKSPACES="/data/ws", SKM_WORKSPACES_ROOT="/older")[0]["SKM_WORKSPACES"], "/older")

    def test_the_home_is_not_exported_while_a_kind_still_lives_in_an_old_xdg_folder(self):
        env = {"HOME": str(self.home), "SHELL": "/bin/bash"}
        (self.home / ".config" / "swissknifeman").mkdir(parents=True)
        values, notes = shellenv.planned_values(env)
        self.assertNotIn("SKM_HOME", values)
        self.assertIn("migrate-home", notes[0])
        self.assertIn("SKM_WORKSPACES", values)
        # an explicit SKM_HOME is the owner's choice and is kept
        self.assertEqual(shellenv.planned_values(dict(env, SKM_HOME=str(self.skm)))[0]["SKM_HOME"], str(self.skm))

    def test_a_default_machine_exports_the_default_home(self):
        values, _ = shellenv.planned_values({"HOME": str(self.home)})
        self.assertEqual(values["SKM_HOME"], str(self.home / ".local/share/swissknifeman"))

    def test_a_relative_home_is_refused(self):
        with self.assertRaises(shellenv.ShellEnvError) as caught:
            shellenv.planned_values({"HOME": str(self.home), "SKM_HOME": "relative"})
        self.assertEqual(caught.exception.code, "SKM_ENV_INVALID")


class SnippetTests(Base):
    def values(self):
        self.workspace()
        return self.planned()[0]

    def test_the_profile_follows_the_shell(self):
        self.assertEqual(shellenv.profile_path(self.env), self.bashrc)
        self.assertEqual(shellenv.profile_path(dict(self.env, SHELL="/usr/bin/zsh")), self.home / ".zshrc")
        self.assertIsNone(shellenv.profile_path(dict(self.env, SHELL="/usr/bin/fish")))
        self.assertEqual(shellenv.profile_path(self.env, explicit=self.tmp / "p"), self.tmp / "p")

    def test_install_creates_the_profile_with_one_block(self):
        values = self.values()
        self.assertEqual(shellenv.install(self.bashrc, values)["action"], "added")
        text = self.bashrc.read_text()
        self.assertEqual(text.count(shellenv.BEGIN), 1)
        self.assertEqual(text.count(shellenv.END), 1)
        for name in envtable.NAMES:
            self.assertIn(f"export {name}\n", text)
        self.assertEqual(shellenv.block_values(text), values)

    def test_install_twice_is_a_no_op(self):
        values = self.values()
        shellenv.install(self.bashrc, values)
        first = self.bashrc.read_bytes()
        stamp = self.bashrc.stat().st_mtime_ns
        self.assertEqual(shellenv.install(self.bashrc, values)["action"], "unchanged")
        self.assertEqual(self.bashrc.read_bytes(), first)
        self.assertEqual(self.bashrc.stat().st_mtime_ns, stamp)

    def test_install_keeps_the_rest_of_the_file_and_updates_the_block_in_place(self):
        values = self.values()
        self.bashrc.write_text("export A=1\n\nalias x=y\n")
        shellenv.install(self.bashrc, values)
        self.bashrc.write_text(self.bashrc.read_text() + "export AFTER=1\n")
        changed = dict(values, SKM_WORKSPACE="other")
        self.assertEqual(shellenv.install(self.bashrc, changed)["action"], "updated")
        text = self.bashrc.read_text()
        self.assertTrue(text.startswith("export A=1\n\nalias x=y\n\n" + shellenv.BEGIN))
        self.assertTrue(text.endswith("export AFTER=1\n"))
        self.assertEqual(text.count(shellenv.BEGIN), 1)
        self.assertEqual(shellenv.block_values(text)["SKM_WORKSPACE"], "other")

    def test_uninstall_restores_the_file_and_is_idempotent(self):
        values = self.values()
        for original in ("export A=1\n", "export A=1\n\n", "# only a comment\n\n\n"):
            with self.subTest(original=original):
                self.bashrc.write_text(original)
                shellenv.install(self.bashrc, values)
                self.assertEqual(shellenv.uninstall(self.bashrc)["action"], "removed")
                self.assertEqual(self.bashrc.read_text(), original)
                self.assertEqual(shellenv.uninstall(self.bashrc)["action"], "absent")
                self.assertEqual(self.bashrc.read_text(), original)

    def test_uninstall_deletes_a_profile_that_held_nothing_else(self):
        shellenv.install(self.bashrc, self.values())
        shellenv.uninstall(self.bashrc)
        self.assertFalse(self.bashrc.exists())
        self.assertEqual(shellenv.uninstall(self.bashrc)["action"], "absent")

    def test_dry_run_writes_nothing(self):
        values = self.values()
        self.assertEqual(shellenv.install(self.bashrc, values, dry_run=True)["action"], "added")
        self.assertFalse(self.bashrc.exists())
        shellenv.install(self.bashrc, values)
        before = self.bashrc.read_bytes()
        self.assertEqual(shellenv.uninstall(self.bashrc, dry_run=True)["action"], "removed")
        self.assertEqual(self.bashrc.read_bytes(), before)

    def test_a_symlinked_profile_is_written_through_and_keeps_its_mode(self):
        real = self.tmp / "dotfiles" / "bashrc"
        real.parent.mkdir()
        real.write_text("export A=1\n")
        real.chmod(0o640)
        self.bashrc.symlink_to(real)
        shellenv.install(self.bashrc, self.values())
        self.assertTrue(self.bashrc.is_symlink())
        self.assertIn(shellenv.BEGIN, real.read_text())
        self.assertEqual(stat.S_IMODE(real.stat().st_mode), 0o640)
        shellenv.uninstall(self.bashrc)
        self.assertEqual(real.read_text(), "export A=1\n")

    def test_markers_that_do_not_pair_up_are_refused_and_nothing_is_written(self):
        values = self.values()
        for broken in (shellenv.BEGIN + "\nexport X=1\n", shellenv.END + "\n",
                       shellenv.BEGIN + "\n" + shellenv.BEGIN + "\n" + shellenv.END + "\n"):
            with self.subTest(broken=broken[:30]):
                self.bashrc.write_text(broken)
                for action in (lambda: shellenv.install(self.bashrc, values), lambda: shellenv.uninstall(self.bashrc)):
                    with self.assertRaises(shellenv.ShellEnvError) as caught:
                        action()
                    self.assertEqual(caught.exception.code, "SHELL_PROFILE_BLOCK_BROKEN")
                self.assertEqual(self.bashrc.read_text(), broken)

    def test_a_value_with_a_space_or_a_quote_survives(self):
        values = dict(self.values(), SKM_HOME="/tmp/a b/it's")
        shellenv.install(self.bashrc, values)
        self.assertEqual(shellenv.block_values(self.bashrc.read_text())["SKM_HOME"], "/tmp/a b/it's")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class FreshShellTests(Base):
    def shell(self, script, **env):
        """A fresh interactive bash with only the given environment (HOME decides which profile it reads)."""
        clean = {"HOME": str(self.home), "PATH": os.environ.get("PATH", ""), "TERM": "dumb"}
        clean.update(env)
        done = subprocess.run(["bash", "-i", "-c", script], env=clean, capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
        return done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""

    SHOW = 'echo "${SKM_HOME-unset}|${SKM_WORKSPACES-unset}|${SKM_WORKSPACE-unset}"'

    def test_a_fresh_shell_without_the_snippet_has_no_variables(self):
        self.assertEqual(self.shell(self.SHOW), "unset|unset|unset")

    def test_a_fresh_shell_exports_the_variables_to_its_children(self):
        self.workspace()
        shellenv.install(self.bashrc, self.planned()[0])
        self.assertEqual(self.shell(self.SHOW), f"{self.skm}|{self.skm / 'workspaces'}|axioma")
        # exported, not only set: a child process (the agent's Bash) sees them
        self.assertEqual(self.shell("python3 -c \"import os; print(os.environ['SKM_WORKSPACE'])\""), "axioma")

    def test_a_value_already_in_the_environment_wins_over_the_snippet(self):
        self.workspace()
        shellenv.install(self.bashrc, self.planned()[0])
        self.assertEqual(self.shell(self.SHOW, SKM_WORKSPACE="other"), f"{self.skm}|{self.skm / 'workspaces'}|other")

    def test_after_uninstall_a_fresh_shell_is_clean_again(self):
        self.workspace()
        shellenv.install(self.bashrc, self.planned()[0])
        shellenv.uninstall(self.bashrc)
        self.assertEqual(self.shell(self.SHOW), "unset|unset|unset")


class CommandTests(Base):
    def run_cli(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        code = aicore_cli.main(["shell-env", *argv], env=env or self.env, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_the_group_is_listed(self):
        self.assertIn("shell-env", aicore_cli.usage())

    def test_install_show_doctor_uninstall(self):
        self.workspace()
        code, out, err = self.run_cli("install", "--json")
        self.assertEqual(code, 0, err)
        document = json.loads(out)
        self.assertEqual((document["action"], document["profile"]), ("added", str(self.bashrc)))
        self.assertEqual(document["variables"], sorted(envtable.NAMES))
        code, out, _ = self.run_cli("install", "--json")
        self.assertEqual(json.loads(out)["action"], "unchanged")
        code, out, _ = self.run_cli("show", "--json")
        shown = json.loads(out)
        self.assertEqual(shown["profile"]["state"], "current")
        self.assertEqual([item["name"] for item in shown["variables"]], list(envtable.NAMES))
        code, out, _ = self.run_cli("doctor", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(next(item for item in json.loads(out) if item["check_id"] == "aicore.env-snippet")["status"], "ok")
        code, out, _ = self.run_cli("uninstall", "--json")
        self.assertEqual(json.loads(out)["action"], "removed")
        self.assertFalse(self.bashrc.exists())

    def test_profile_and_dry_run_options(self):
        target = self.tmp / "custom-profile"
        code, out, _ = self.run_cli("install", "--profile", str(target), "--dry-run", "--json")
        self.assertEqual(code, 0)
        self.assertFalse(target.exists())
        self.assertEqual(json.loads(out)["profile"], str(target))
        self.assertEqual(self.run_cli("install", "--profile", str(target))[0], 0)
        self.assertTrue(target.exists())

    def test_an_unsupported_shell_needs_a_profile(self):
        code, _, err = self.run_cli("install", env=dict(self.env, SHELL="/usr/bin/fish"))
        self.assertEqual(code, 1)
        self.assertIn("SHELL_UNSUPPORTED", err)

    def test_a_broken_profile_is_exit_1_with_its_code(self):
        self.bashrc.write_text(shellenv.BEGIN + "\n")
        code, _, err = self.run_cli("install")
        self.assertEqual(code, 1)
        self.assertIn("SHELL_PROFILE_BLOCK_BROKEN", err)

    def test_usage_errors_are_exit_2(self):
        for argv in (("nope",), ("install", "--wat"), ("install", "--profile")):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 2)

    def test_main_is_importable_as_the_group_function(self):
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(shell_env_main(["--help"], env=self.env, out=out, err=err), 0)
        self.assertIn("install", out.getvalue())


class DoctorTests(Base):
    def checks(self, prefix="project", **extra):
        env = dict(self.env, **extra)
        return {item["check_id"]: item for item in shellenv.doctor_checks(prefix, env)}

    def test_no_snippet_is_a_warning_with_the_remedy(self):
        found = self.checks()
        self.assertEqual(found["project.env-snippet"]["status"], "warn")
        self.assertIn("shell-env install", found["project.env-snippet"]["remediation"])
        self.assertEqual(found["project.env-variables"]["status"], "warn")

    def test_a_current_snippet_and_the_variables_in_the_shell_are_ok(self):
        self.workspace()
        values, _ = self.planned()
        shellenv.install(self.bashrc, values)
        found = self.checks("workspace", **values)
        self.assertEqual(found["workspace.env-snippet"]["status"], "ok")
        self.assertEqual(found["workspace.env-variables"]["status"], "ok")

    def test_a_snippet_that_is_not_in_this_shell_yet_says_so(self):
        self.workspace()
        shellenv.install(self.bashrc, self.planned()[0])
        found = self.checks()
        self.assertEqual(found["project.env-snippet"]["status"], "ok")
        self.assertIn("open a new shell", found["project.env-variables"]["observed"])

    def test_a_stale_snippet_is_a_warning(self):
        self.workspace()
        values, _ = self.planned()
        shellenv.install(self.bashrc, dict(values, SKM_WORKSPACE="old"))
        self.assertEqual(self.checks(**values)["project.env-snippet"]["status"], "warn")

    def test_a_broken_snippet_is_a_failure(self):
        self.bashrc.write_text(shellenv.BEGIN + "\n")
        self.assertEqual(self.checks()["project.env-snippet"]["status"], "fail")

    def test_an_unsupported_shell_is_skipped(self):
        self.assertEqual(self.checks(SHELL="/usr/bin/fish")["project.env-snippet"]["status"], "skip")

    def test_variables_that_point_nowhere_are_warned(self):
        found = self.checks(SKM_WORKSPACES=str(self.tmp / "nowhere"), SKM_WORKSPACE="ghost")
        observed = found["project.env-variables"]["observed"]
        self.assertIn("SKM_WORKSPACES=", observed)
        self.assertIn("SKM_WORKSPACE=ghost is not a workspace", observed)
        invalid = self.checks(SKM_WORKSPACE="Not A Code")["project.env-variables"]
        self.assertEqual(invalid["status"], "fail")
        self.assertIn("must be a workspace code", invalid["observed"])

    def test_an_invalid_home_fails(self):
        self.assertEqual(self.checks(SKM_HOME="relative")["project.env-variables"]["status"], "fail")

    def test_the_project_doctor_reports_both_checks(self):
        root = self.tmp / "proj"
        (root / ".git").mkdir(parents=True)
        found = {item["check_id"]: item for item in project_cli.doctor_checks(root, self.env)}
        self.assertIn("project.env-snippet", found)
        self.assertIn("project.env-variables", found)


class LauncherTests(Base):
    """The project launcher passes the variables on to the hub unchanged and runs just as well without them."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "proj"
        (self.root / ".git").mkdir(parents=True)
        (self.root / ".swissknifeman").mkdir()
        self.launcher = self.root / ".swissknifeman" / "launcher.py"
        self.launcher.write_bytes(artifacts.template_bytes())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        hub = self.bin / "swissknifeman"
        hub.write_text("#!/bin/sh\nfor name in SKM_HOME SKM_WORKSPACES SKM_WORKSPACE SKM_LAUNCHER_ACTIVE; do\n"
                       "  eval \"printf '%s=%s\\n' $name \\\"\\${$name-unset}\\\"\"\ndone\nprintf 'args=%s\\n' \"$*\"\n")
        hub.chmod(0o755)

    def launch(self, **variables):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin"}
        env.update(variables)
        done = subprocess.run([sys.executable, "-I", str(self.launcher), "project", "context"], cwd=str(self.root), env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return dict(line.split("=", 1) for line in done.stdout.splitlines())

    def test_the_hub_sees_the_variables_of_the_shell(self):
        seen = self.launch(SKM_HOME="/m/home", SKM_WORKSPACES="/m/ws", SKM_WORKSPACE="axioma")
        self.assertEqual((seen["SKM_HOME"], seen["SKM_WORKSPACES"], seen["SKM_WORKSPACE"]), ("/m/home", "/m/ws", "axioma"))
        self.assertEqual((seen["SKM_LAUNCHER_ACTIVE"], seen["args"]), ("1", "project context"))

    def test_the_launcher_works_without_the_variables_and_invents_none(self):
        seen = self.launch()
        self.assertEqual((seen["SKM_HOME"], seen["SKM_WORKSPACES"], seen["SKM_WORKSPACE"]), ("unset", "unset", "unset"))
        self.assertEqual(seen["SKM_LAUNCHER_ACTIVE"], "1")

    def test_a_part_of_the_variables_is_passed_as_it_is(self):
        seen = self.launch(SKM_WORKSPACE="axioma")
        self.assertEqual((seen["SKM_HOME"], seen["SKM_WORKSPACE"]), ("unset", "axioma"))


if __name__ == "__main__":
    unittest.main()
