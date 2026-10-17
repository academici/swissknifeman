"""Machine and project locations, SKM_HOME isolation and the legacy lookup."""
import os
import tempfile
import unittest
from pathlib import Path

from aicore.state import locations as loc


class MachineLocationsTests(unittest.TestCase):
    def test_defaults_come_from_the_home_directory(self):
        got = loc.machine_locations({}, home="/h")
        self.assertEqual(got.config, Path("/h/.config/swissknifeman"))
        self.assertEqual(got.state, Path("/h/.local/state/swissknifeman"))
        self.assertEqual(got.data, Path("/h/.local/share/swissknifeman"))
        self.assertEqual(got.cache, Path("/h/.cache/swissknifeman"))
        self.assertFalse(got.isolated)

    def test_home_comes_from_env_when_not_passed(self):
        self.assertEqual(loc.config_dir(env={"HOME": "/e"}), Path("/e/.config/swissknifeman"))

    def test_absolute_xdg_variables_win(self):
        env = {"XDG_CONFIG_HOME": "/x/c", "XDG_STATE_HOME": "/x/s",
               "XDG_DATA_HOME": "/x/d", "XDG_CACHE_HOME": "/x/k"}
        got = loc.machine_locations(env, home="/h")
        self.assertEqual((got.config, got.state, got.data, got.cache),
                         (Path("/x/c/swissknifeman"), Path("/x/s/swissknifeman"),
                          Path("/x/d/swissknifeman"), Path("/x/k/swissknifeman")))

    def test_relative_or_empty_xdg_is_ignored(self):
        env = {"XDG_CONFIG_HOME": "rel/dir", "XDG_STATE_HOME": ""}
        got = loc.machine_locations(env, home="/h")
        self.assertEqual(got.config, Path("/h/.config/swissknifeman"))
        self.assertEqual(got.state, Path("/h/.local/state/swissknifeman"))

    def test_skm_home_moves_everything_and_isolates(self):
        env = {"SKM_HOME": "/sb", "XDG_CONFIG_HOME": "/x/c"}
        got = loc.machine_locations(env, home="/h")
        self.assertEqual((got.config, got.state, got.data, got.cache),
                         (Path("/sb/config"), Path("/sb/state"), Path("/sb/data"), Path("/sb/cache")))
        self.assertTrue(got.isolated)

    def test_relative_skm_home_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            loc.machine_locations({"SKM_HOME": "sandbox"}, home="/h")
        self.assertIn("SKM_HOME", str(caught.exception))

    def test_empty_skm_home_is_not_set(self):
        self.assertFalse(loc.machine_locations({"SKM_HOME": ""}, home="/h").isolated)

    def test_wrappers_and_application_subdirectories(self):
        env = {"SKM_HOME": "/sb"}
        self.assertEqual(loc.state_dir(env=env), Path("/sb/state"))
        self.assertEqual(loc.state_dir("analyst", env=env), Path("/sb/state/analyst"))
        self.assertEqual(loc.data_dir("maind", env=env), Path("/sb/data/maind"))
        self.assertEqual(loc.cache_dir("skiller", env=env), Path("/sb/cache/skiller"))
        self.assertEqual(loc.machine_config_file(env=env), Path("/sb/config/config.toml"))

    def test_location_functions_create_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            loc.machine_locations({"SKM_HOME": tmp + "/sb"})
            loc.state_dir("x", env={"SKM_HOME": tmp + "/sb"})
            self.assertEqual(os.listdir(tmp), [])

    def test_ensure_dir_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = loc.ensure_dir(Path(tmp) / "a" / "b")
            self.assertTrue(target.is_dir())
            self.assertEqual(target.stat().st_mode & 0o777, 0o700 & ~_umask())
            self.assertEqual(loc.ensure_dir(target), target)


def _umask():
    current = os.umask(0)
    os.umask(current)
    return current


class WorkspaceLocationsTests(unittest.TestCase):
    def test_workspace_root_follows_the_data_directory(self):
        self.assertEqual(loc.workspace_root({"SKM_HOME": "/sb"}), Path("/sb/data/workspace"))
        self.assertEqual(loc.workspace_root({"XDG_DATA_HOME": "/x/d"}, home="/h"), Path("/x/d/swissknifeman/workspace"))
        self.assertEqual(loc.workspace_root({}, home="/h"), Path("/h/.local/share/swissknifeman/workspace"))
        self.assertEqual(loc.workspace_root({"HOME": "/e"}), Path("/e/.local/share/swissknifeman/workspace"))

    def test_skm_home_wins_over_xdg_data_home(self):
        self.assertEqual(loc.workspace_root({"SKM_HOME": "/sb", "XDG_DATA_HOME": "/x/d"}), Path("/sb/data/workspace"))

    def test_override_wins_over_everything(self):
        env = {"SKM_WORKSPACE_ROOT": "/ws", "SKM_HOME": "/sb", "XDG_DATA_HOME": "/x/d"}
        self.assertEqual(loc.workspace_root(env), Path("/ws"))
        self.assertEqual(loc.workspace_state_dir(env), Path("/sb/state/workspace"))

    def test_empty_override_is_not_set(self):
        self.assertEqual(loc.workspace_root({"SKM_WORKSPACE_ROOT": "", "SKM_HOME": "/sb"}), Path("/sb/data/workspace"))

    def test_relative_override_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            loc.workspace_root({"SKM_WORKSPACE_ROOT": "ws", "SKM_HOME": "/sb"})
        self.assertIn("SKM_WORKSPACE_ROOT", str(caught.exception))

    def test_state_directory_is_the_workspace_application_directory(self):
        self.assertEqual(loc.workspace_state_dir({"SKM_HOME": "/sb"}), Path("/sb/state/workspace"))
        self.assertEqual(loc.workspace_state_dir({}, home="/h"), Path("/h/.local/state/swissknifeman/workspace"))

    def test_nothing_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"SKM_HOME": tmp + "/sb", "SKM_WORKSPACE_ROOT": tmp + "/ws"}
            loc.workspace_root(env)
            loc.workspace_state_dir(env)
            self.assertEqual(os.listdir(tmp), [])

    def test_package_exports(self):
        from aicore import state
        self.assertIs(state.workspace_root, loc.workspace_root)
        self.assertIs(state.workspace_state_dir, loc.workspace_state_dir)


class ProjectLocationsTests(unittest.TestCase):
    def test_project_paths(self):
        root = Path("/p")
        self.assertEqual(loc.project_dir(root), Path("/p/.swissknifeman"))
        self.assertEqual(loc.project_config_file(root), Path("/p/.swissknifeman/config.toml"))
        self.assertEqual(loc.project_state_dir(root), Path("/p/.swissknifeman/state"))
        self.assertEqual(loc.project_state_dir(root, "orch"), Path("/p/.swissknifeman/state/orch"))
        self.assertEqual(loc.project_backups_dir(root), Path("/p/.swissknifeman/backups"))

    def test_find_project_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            git_project = base / "a"
            (git_project / ".git").mkdir(parents=True)
            deep = git_project / "src" / "pkg"
            deep.mkdir(parents=True)
            self.assertEqual(loc.find_project_root(deep, home=base / "nohome"), git_project)
            self.assertEqual(loc.find_project_root(git_project, home=base / "nohome"), git_project)
            marked = base / "b"
            (marked / ".swissknifeman").mkdir(parents=True)
            self.assertEqual(loc.find_project_root(marked / "x", home=base / "nohome"), marked)
            loose = base / "c" / "d"
            loose.mkdir(parents=True)
            self.assertEqual(loc.find_project_root(loose, home=base / "nohome"), loose)

    def test_git_file_marks_a_worktree_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            (base / "w").mkdir()
            (base / "w" / ".git").write_text("gitdir: elsewhere\n")
            self.assertEqual(loc.find_project_root(base / "w", home=base / "nohome"), base / "w")

    def test_machine_state_directory_in_home_is_not_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp).resolve()
            (home / ".swissknifeman").mkdir()
            work = home / "scratch"
            work.mkdir()
            self.assertEqual(loc.find_project_root(work, home=home), work)


class ResolveProjectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.project = self.base / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.deep = self.project / "src" / "pkg"
        self.deep.mkdir(parents=True)

    def resolve(self, start=None, **kwargs):
        kwargs.setdefault("env", {})
        return loc.resolve_project(start or self.deep, home=self.home, **kwargs)

    def test_a_flag_wins_over_the_environment_and_markers(self):
        other = self.base / "other"
        other.mkdir()
        context = self.resolve(explicit=other, env={"SKM_PROJECT_ROOT": str(self.base)})
        self.assertEqual((context.root, context.resolution), (other, "flag"))

    def test_the_environment_wins_over_markers(self):
        context = self.resolve(env={"SKM_PROJECT_ROOT": str(self.base)})
        self.assertEqual((context.root, context.resolution), (self.base, "environment"))

    def test_a_git_directory_and_a_marker_are_told_apart(self):
        context = self.resolve()
        self.assertEqual((context.root, context.resolution, context.marker), (self.project, "git", ".git"))
        marked = self.base / "marked"
        (marked / ".swissknifeman").mkdir(parents=True)
        context = self.resolve(marked / "x")
        self.assertEqual((context.root, context.resolution, context.marker), (marked, "marker", ".swissknifeman"))

    def test_without_a_project_there_is_no_context(self):
        loose = self.base / "loose" / "dir"
        loose.mkdir(parents=True)
        self.assertIsNone(self.resolve(loose))

    def test_the_machine_state_directory_in_home_is_not_a_project(self):
        (self.home / ".swissknifeman").mkdir()
        work = self.home / "scratch"
        work.mkdir()
        self.assertIsNone(self.resolve(work))
        (self.home / ".git").mkdir()
        self.assertEqual(self.resolve(work).root, self.home)

    def test_a_relative_flag_is_made_absolute_and_a_blank_environment_is_ignored(self):
        context = loc.resolve_project(self.deep, explicit=self.deep.parent, env={"SKM_PROJECT_ROOT": ""}, home=self.home)
        self.assertEqual(context.root, self.deep.parent)
        previous = os.getcwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, previous)
        self.assertEqual(loc.resolve_project(self.deep, explicit="proj", env={}, home=self.home).root, self.project)
        self.assertEqual(self.resolve(env={"SKM_PROJECT_ROOT": ""}).resolution, "git")

    def test_own_markers_and_the_stop_at_home(self):
        (self.home / ".claude").mkdir()
        work = self.home / "scratch"
        work.mkdir()
        markers = (".swissknifeman/config.toml", ".claude", ".git")
        context = self.resolve(work, markers=markers, stop_at_home=True)
        self.assertEqual((context.root, context.marker), (self.home, ".claude"))
        self.assertIsNone(self.resolve(self.home.parent, markers=(".nothing",), stop_at_home=True))
        (self.project / ".swissknifeman").mkdir()
        (self.project / ".swissknifeman" / "config.toml").write_text("x")
        self.assertEqual(self.resolve(markers=markers, stop_at_home=True).marker, ".swissknifeman/config.toml")

    def test_a_named_project_that_is_not_a_directory_is_refused_not_searched_around(self):
        file = self.base / "file.txt"
        file.write_text("x")
        for kwargs in ({"explicit": file}, {"env": {"SKM_PROJECT_ROOT": str(file)}},
                       {"explicit": self.base / "missing"}):
            with self.assertRaises(loc.ProjectContextRequired) as caught:
                self.resolve(**kwargs)
            self.assertIn("is not a directory", str(caught.exception))
        # the wrapper never raises: a stale SKM_PROJECT_ROOT is ignored and the markers decide
        self.assertEqual(loc.find_project_root(self.deep, env={"SKM_PROJECT_ROOT": str(file)}, home=self.home),
                         self.project)

    def test_typed_markers_tell_a_file_from_a_directory(self):
        mid = self.project / "mid"
        mid.mkdir()
        (mid / ".claude").write_text("a file, not a settings folder")
        markers = ((".claude", "dir"), (".git", "any"))
        self.assertEqual(self.resolve(mid, markers=markers).root, self.project)
        (mid / ".claude").unlink()
        (mid / ".claude").mkdir()
        self.assertEqual(self.resolve(mid, markers=markers).root, mid)

    def test_find_project_root_is_the_wrapper(self):
        self.assertEqual(loc.find_project_root(self.deep, env={}, home=self.home), self.project)
        loose = self.base / "loose"
        loose.mkdir()
        self.assertEqual(loc.find_project_root(loose, env={}, home=self.home), loose)
        self.assertEqual(loc.find_project_root(self.deep, env={"SKM_PROJECT_ROOT": str(loose)}, home=self.home), loose)

    def test_the_error_names_the_flag(self):
        error = loc.ProjectContextRequired(self.base)
        self.assertEqual(error.code, "PROJECT_CONTEXT_REQUIRED")
        self.assertIn("--project DIR", str(error))
        self.assertIn(str(self.base), str(error))


class ResolveWithLegacyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.new = self.root / "new" / "config.toml"
        self.old = self.root / "old.json"
        self.other = self.root / "older.json"
        self.messages = []
        self.env = {}

    def resolve(self, legacy=None, env=None):
        return loc.resolve_with_legacy(self.new, self.old if legacy is None else legacy,
                                       env=self.env if env is None else env, home=self.root,
                                       warn=self.messages.append)

    def make(self, *paths):
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x")

    def test_existing_new_location_wins_silently(self):
        self.make(self.new, self.old)
        self.assertEqual(self.resolve(), self.new)
        self.assertEqual(self.messages, [])

    def test_only_legacy_warns_once_per_process(self):
        self.make(self.old)
        self.assertEqual(self.resolve(), self.old)
        self.assertEqual(self.resolve(), self.old)
        self.assertEqual(len(self.messages), 1)
        self.assertIn(f"{self.old} is a legacy location", self.messages[0])
        self.assertIn(str(self.new), self.messages[0])
        self.assertTrue(self.messages[0].startswith("warning: "))

    def test_first_existing_legacy_path_is_used(self):
        self.make(self.other)
        self.assertEqual(self.resolve([self.old, self.other]), self.other)
        self.assertEqual(len(self.messages), 1)

    def test_nothing_exists_gives_the_new_location(self):
        self.assertEqual(self.resolve(), self.new)
        self.assertEqual(self.messages, [])

    def test_skm_home_never_looks_at_legacy(self):
        self.make(self.old)
        self.assertEqual(self.resolve(env={"SKM_HOME": str(self.root / "sb")}), self.new)
        self.assertEqual(self.messages, [])

    def test_nothing_is_copied_or_removed(self):
        self.make(self.old)
        self.resolve()
        self.assertFalse(self.new.parent.exists())
        self.assertTrue(self.old.exists())

    def test_default_warning_goes_to_stderr(self):
        import contextlib
        import io
        self.make(self.old)
        fresh = self.root / "fresh.toml"
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            loc.resolve_with_legacy(fresh, self.old, env={}, home=self.root)
        self.assertIn("legacy location", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
