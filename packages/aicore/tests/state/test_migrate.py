"""``aicore config migrate-home``: the old XDG folders move into the machine home."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from aicore.config import cli
from aicore.state import MigrationError, migrate_home


class MigrateHomeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.base = self.home / ".local" / "share" / "swissknifeman"

    def make(self, path, text="x"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_config_state_and_cache_move_into_the_machine_home(self):
        self.make(self.home / ".config" / "swissknifeman" / "config.toml")
        self.make(self.home / ".local" / "state" / "swissknifeman" / "maind" / "registry.json")
        self.make(self.home / ".cache" / "swissknifeman" / "blob")
        moves = migrate_home({}, home=self.home)
        self.assertEqual([(move.kind, move.status) for move in moves],
                         [("config", "moved"), ("state", "moved"), ("cache", "moved")])
        self.assertTrue((self.base / "config" / "config.toml").is_file())
        self.assertTrue((self.base / "state" / "maind" / "registry.json").is_file())
        self.assertTrue((self.base / "cache" / "blob").is_file())
        self.assertFalse((self.home / ".config" / "swissknifeman").exists())
        self.assertFalse((self.home / ".local" / "state" / "swissknifeman").exists())

    def test_a_dry_run_changes_nothing(self):
        self.make(self.home / ".config" / "swissknifeman" / "config.toml")
        moves = migrate_home({}, home=self.home, dry_run=True)
        self.assertEqual(moves[0].status, "planned")
        self.assertTrue((self.home / ".config" / "swissknifeman" / "config.toml").is_file())
        self.assertFalse(self.base.exists())

    def test_a_second_run_finds_nothing(self):
        self.make(self.home / ".config" / "swissknifeman" / "config.toml")
        migrate_home({}, home=self.home)
        self.assertEqual({move.status for move in migrate_home({}, home=self.home)}, {"absent"})

    def test_a_target_that_holds_data_is_a_conflict_and_stays_untouched(self):
        old = self.make(self.home / ".config" / "swissknifeman" / "config.toml", "old")
        new = self.make(self.base / "config" / "config.toml", "new")
        moves = migrate_home({}, home=self.home)
        self.assertEqual(moves[0].status, "conflict")
        self.assertEqual((old.read_text(), new.read_text()), ("old", "new"))

    def test_an_empty_target_folder_is_replaced(self):
        self.make(self.home / ".config" / "swissknifeman" / "config.toml")
        (self.base / "config").mkdir(parents=True)
        self.assertEqual(migrate_home({}, home=self.home)[0].status, "moved")
        self.assertTrue((self.base / "config" / "config.toml").is_file())

    def test_the_children_of_a_moved_xdg_data_folder_join_the_machine_home(self):
        data = self.home / "xdg-data" / "swissknifeman"
        self.make(data / "maind" / "graph.db")
        self.make(data / "workspaces" / "axioma" / "workspace.json")
        self.make(self.base / "workspaces" / "other" / "workspace.json")
        moves = migrate_home({"XDG_DATA_HOME": str(self.home / "xdg-data")}, home=self.home)
        by_target = {move.target.name: move.status for move in moves if move.kind == "data"}
        self.assertEqual(by_target, {"maind": "moved", "workspaces": "conflict"})
        self.assertTrue((self.base / "maind" / "graph.db").is_file())
        self.assertTrue((data / "workspaces" / "axioma" / "workspace.json").is_file())

    def test_a_relative_symlink_keeps_pointing_at_the_same_place(self):
        self.make(self.home / ".config" / "dotfiles" / "skm" / "config.toml")
        (self.home / ".config" / "swissknifeman").symlink_to("dotfiles/skm")
        moves = migrate_home({}, home=self.home)
        self.assertEqual(moves[0].status, "moved")
        moved = self.base / "config"
        self.assertTrue(moved.is_symlink())
        self.assertTrue((moved / "config.toml").is_file())
        self.assertEqual(moved.resolve(), (self.home / ".config" / "dotfiles" / "skm").resolve())
        self.assertFalse((self.home / ".config" / "swissknifeman").is_symlink())

    def test_coinciding_state_and_data_folders_are_refused_untouched(self):
        xdg = self.home / "xdg"
        self.make(xdg / "swissknifeman" / "maind" / "graph.db")
        env = {"XDG_STATE_HOME": str(xdg), "XDG_DATA_HOME": str(xdg)}
        with self.assertRaises(MigrationError) as caught:
            migrate_home(env, home=self.home)
        self.assertIn("same folder", str(caught.exception))
        self.assertTrue((xdg / "swissknifeman" / "maind" / "graph.db").is_file())
        self.assertFalse(self.base.exists())

    def test_skm_home_refuses(self):
        with self.assertRaises(MigrationError):
            migrate_home({"SKM_HOME": str(self.home / "sb")}, home=self.home)


class MigrateHomeCommandTests(unittest.TestCase):
    def run_cli(self, *argv, env):
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(["migrate-home", *argv], env=env, cwd=Path(env["HOME"]), out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        (self.home / ".config" / "swissknifeman").mkdir(parents=True)
        (self.home / ".config" / "swissknifeman" / "config.toml").write_text("x")
        self.env = {"HOME": str(self.home)}

    def test_the_command_moves_and_reports(self):
        code, out, _ = self.run_cli("--json", env=self.env)
        doc = json.loads(out)
        self.assertEqual((code, doc["dry_run"], doc["moves"][0]["status"]), (0, False, "moved"))
        self.assertTrue((self.home / ".local/share/swissknifeman/config/config.toml").is_file())
        code, out, _ = self.run_cli(env=self.env)
        self.assertEqual(code, 0)
        self.assertIn("nothing to move", out)

    def test_a_conflict_exits_1(self):
        target = self.home / ".local/share/swissknifeman/config/config.toml"
        target.parent.mkdir(parents=True)
        target.write_text("new")
        code, _, err = self.run_cli(env=self.env)
        self.assertEqual(code, 1)
        self.assertIn("already holds data", err)

    def test_skm_home_is_refused_with_exit_1(self):
        code, _, err = self.run_cli(env=dict(self.env, SKM_HOME=str(self.home / "sb")))
        self.assertEqual(code, 1)
        self.assertIn("SKM_HOME", err)


if __name__ == "__main__":
    unittest.main()
