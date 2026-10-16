"""Backups with rotation: layout, collisions, rotation safety, listing."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aicore.state import backups as bk

T0 = datetime(2026, 10, 8, 12, 0, 0, 123456, tzinfo=timezone.utc)


class BackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "home"
        self.project = self.root / "proj"
        self.home.mkdir()
        self.project.mkdir()
        self.env = {"SKM_HOME": str(self.root / "sb")}

    def write(self, path, text="v1"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def machine_backups(self):
        return self.root / "sb" / "state" / "backups"

    def test_missing_file_gives_none(self):
        self.assertIsNone(bk.backup(self.project / "none.toml", project=self.project, env=self.env))
        self.assertEqual(list(self.root.glob("sb/**/*")), [])

    def test_project_file_goes_below_the_project_backups(self):
        source = self.write(self.project / "sub" / "config.toml", "data")
        copy = bk.backup(source, project=self.project, now=T0, env=self.env)
        self.assertEqual(copy, self.project / ".swissknifeman" / "backups" / "20261008T120000123456Z"
                         / "sub" / "config.toml")
        self.assertEqual(copy.read_text(), "data")
        self.assertEqual(source.read_text(), "data")

    def test_machine_file_inside_home_uses_a_home_relative_path(self):
        source = self.write(self.home / ".config" / "x.toml")
        copy = bk.backup(source, now=T0, env=self.env, home=self.home)
        self.assertEqual(copy, self.machine_backups() / "20261008T120000123456Z" / ".config" / "x.toml")

    def test_machine_file_outside_home_uses_the_absolute_path(self):
        source = self.write(self.root / "elsewhere" / "y.toml")
        copy = bk.backup(source, now=T0, env=self.env, home=self.home)
        expected = self.machine_backups() / "20261008T120000123456Z" / Path(*source.parts[1:])
        self.assertEqual(copy, expected)

    def test_project_given_but_file_outside_goes_to_machine_backups(self):
        source = self.write(self.home / "z.toml")
        copy = bk.backup(source, project=self.project, now=T0, env=self.env, home=self.home)
        self.assertTrue(str(copy).startswith(str(self.machine_backups())))

    def test_relative_paths_are_made_absolute(self):
        import os
        source = self.write(self.project / "r.toml", "rel")
        previous = os.getcwd()
        os.chdir(self.project)
        try:
            copy = bk.backup("r.toml", project=self.project, now=T0, env=self.env)
        finally:
            os.chdir(previous)
        self.assertEqual(copy.read_text(), "rel")
        self.assertEqual(copy.name, source.name)

    def test_symlink_backs_up_the_target_content(self):
        target = self.write(self.root / "real.toml", "real")
        link = self.project / "link.toml"
        link.symlink_to(target)
        copy = bk.backup(link, project=self.project, now=T0, env=self.env)
        self.assertFalse(copy.is_symlink())
        self.assertEqual(copy.read_text(), "real")

    def test_same_instant_gets_a_numeric_suffix(self):
        source = self.write(self.project / "c.toml")
        names = [bk.backup(source, project=self.project, now=T0, env=self.env).parts[-2]
                 for _ in range(3)]
        self.assertEqual(names, ["20261008T120000123456Z", "20261008T120000123456Z-1",
                                 "20261008T120000123456Z-2"])

    def test_naive_and_foreign_zone_times_are_normalised_to_utc(self):
        source = self.write(self.project / "c.toml")
        zone = timezone(timedelta(hours=3))
        local = datetime(2026, 10, 8, 15, 0, 0, 123456, tzinfo=zone)
        self.assertEqual(bk.backup(source, project=self.project, now=local, env=self.env).parts[-2],
                         "20261008T120000123456Z")
        naive = datetime(2026, 10, 8, 12, 0, 1)
        self.assertEqual(bk.backup(source, project=self.project, now=naive, env=self.env).parts[-2],
                         "20261008T120001000000Z")

    def test_rotation_keeps_the_newest_stamps(self):
        source = self.write(self.project / "c.toml")
        for index in range(4):
            bk.backup(source, project=self.project, now=T0 + timedelta(seconds=index),
                      keep=2, env=self.env)
        listing = bk.list_backups(self.project)
        self.assertEqual([stamp for stamp, _ in listing],
                         ["20261008T120003123456Z", "20261008T120002123456Z"])

    def test_rotation_orders_suffixes_numerically(self):
        source = self.write(self.project / "c.toml")
        for _ in range(12):
            bk.backup(source, project=self.project, now=T0, keep=2, env=self.env)
        self.assertEqual([stamp for stamp, _ in bk.list_backups(self.project)],
                         ["20261008T120000123456Z-11", "20261008T120000123456Z-10"])

    def test_rotation_never_touches_foreign_entries(self):
        base = self.project / ".swissknifeman" / "backups"
        (base / "my-notes").mkdir(parents=True)
        (base / "my-notes" / "keep.txt").write_text("mine")
        (base / "README").write_text("mine")
        (base / "20261008T120000123456Z.old").mkdir()
        (base / "2026-01-01").mkdir()
        source = self.write(self.project / "c.toml")
        for index in range(4):
            bk.backup(source, project=self.project, now=T0 + timedelta(seconds=index),
                      keep=1, env=self.env)
        self.assertTrue((base / "my-notes" / "keep.txt").is_file())
        self.assertTrue((base / "README").is_file())
        self.assertTrue((base / "20261008T120000123456Z.old").is_dir())
        self.assertTrue((base / "2026-01-01").is_dir())
        self.assertEqual(len(bk.list_backups(self.project)), 1)

    def test_rotation_ignores_a_symlinked_stamp_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "data").write_text("precious")
        base = self.project / ".swissknifeman" / "backups"
        base.mkdir(parents=True)
        (base / "20200101T000000000000Z").symlink_to(outside, target_is_directory=True)
        source = self.write(self.project / "c.toml")
        bk.backup(source, project=self.project, now=T0, keep=1, env=self.env)
        self.assertTrue((outside / "data").is_file())

    def test_keep_below_one_is_rejected_before_anything_is_written(self):
        source = self.write(self.project / "c.toml")
        for keep in (0, -1):
            with self.assertRaises(ValueError):
                bk.backup(source, project=self.project, keep=keep, env=self.env)
        self.assertFalse((self.project / ".swissknifeman").exists())

    def test_default_keep_is_ten(self):
        self.assertEqual(bk.DEFAULT_KEEP, 10)
        source = self.write(self.project / "c.toml")
        for index in range(12):
            bk.backup(source, project=self.project, now=T0 + timedelta(seconds=index), env=self.env)
        self.assertEqual(len(bk.list_backups(self.project)), 10)

    def test_list_backups_lists_files_newest_first(self):
        first = self.write(self.project / "a.toml")
        second = self.write(self.project / "d" / "b.toml")
        bk.backup(first, project=self.project, now=T0, env=self.env)
        bk.backup(second, project=self.project, now=T0 + timedelta(seconds=1), env=self.env)
        listing = bk.list_backups(self.project)
        self.assertEqual([stamp for stamp, _ in listing],
                         ["20261008T120001123456Z", "20261008T120000123456Z"])
        self.assertEqual([path.name for path in listing[0][1]], ["b.toml"])

    def test_list_backups_without_a_directory_is_empty(self):
        self.assertEqual(bk.list_backups(self.project), [])
        self.assertEqual(bk.list_backups(env=self.env), [])

    def test_machine_listing_uses_the_state_directory(self):
        source = self.write(self.home / "m.toml")
        bk.backup(source, now=T0, env=self.env, home=self.home)
        self.assertEqual(len(bk.list_backups(env=self.env, home=self.home)), 1)


if __name__ == "__main__":
    unittest.main()
