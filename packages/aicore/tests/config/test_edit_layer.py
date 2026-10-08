"""edit_layer_file: parse, edit, check against the schema, back up, write atomically; errors change nothing."""
import os
import stat
import unittest
from unittest import mock

from aicore import config
from aicore.config import ConfigError, toml, toml_edit
from aicore.state import list_backups

from tests.config.support import Workspace

COMMENTED = """\
# Machine configuration of demo
schema_version = 1

[demo]
mode = "safe"   # keep this comment

[demo.recompute]
candidate_min_n = 18
"""


class EditCase(Workspace):
    def edit(self, key, value=None, path=None, **kwargs):
        kwargs.setdefault("layer", "machine")
        kwargs.setdefault("env", self.env)
        return config.edit_layer_file(path or self.machine_file, "demo", key, value, schema=self.schema, **kwargs)

    def snapshot(self, path):
        return path.read_bytes() if path.exists() else None

    def assertUnchanged(self, path, before, action):
        with self.assertRaises((ConfigError, toml_edit.TomlEditError)):
            action()
        self.assertEqual(self.snapshot(path), before)
        self.assertEqual(sorted(path.parent.glob("*.tmp")) if path.parent.exists() else [], [])


class TestSetAndUnset(EditCase):
    def test_new_file_gets_version_section_and_key(self):
        result = self.edit("mode", "fast")
        self.assertEqual((result.changed, result.backup), (True, None))
        self.assertEqual(self.machine_file.read_text(encoding="utf-8"), 'schema_version = 1\n\n[demo]\nmode = "fast"\n')
        self.assertEqual(self.resolve().get("mode"), "fast")

    def test_existing_file_keeps_comments_and_other_lines(self):
        self.write(self.machine_file, COMMENTED)
        self.edit("recompute.candidate_min_n", 25)
        text = self.machine_file.read_text(encoding="utf-8")
        self.assertEqual(text, COMMENTED.replace("candidate_min_n = 18", "candidate_min_n = 25"))
        self.assertIn('mode = "safe"   # keep this comment', text)

    def test_new_key_in_an_existing_table_and_a_new_table(self):
        self.write(self.machine_file, COMMENTED)
        self.edit("verbose", True)
        self.edit("recompute.window.days", 30)
        data = toml.loads(self.machine_file.read_text(encoding="utf-8"))
        self.assertEqual(data["demo"]["verbose"], True)
        self.assertEqual(data["demo"]["recompute"]["window"], {"days": 30})
        self.assertEqual(data["demo"]["recompute"]["candidate_min_n"], 18)

    def test_arrays_and_numbers(self):
        self.edit("sources", ["a", "b"])
        self.edit("recompute.ratio", 0.25)
        resolved = self.resolve()
        self.assertEqual((resolved.get("sources"), resolved.get("recompute.ratio")), (["a", "b"], 0.25))

    def test_unset_removes_the_line(self):
        self.write(self.machine_file, COMMENTED)
        result = self.edit("recompute.candidate_min_n", remove=True)
        self.assertTrue(result.changed)
        self.assertNotIn("candidate_min_n", self.machine_file.read_text(encoding="utf-8"))
        self.assertEqual(self.resolve().get("recompute.candidate_min_n"), 15)

    def test_unset_of_an_absent_key_changes_nothing(self):
        self.write(self.machine_file, COMMENTED)
        before = self.snapshot(self.machine_file)
        result = self.edit("verbose", remove=True)
        self.assertEqual((result.changed, result.backup), (False, None))
        self.assertEqual(self.snapshot(self.machine_file), before)
        self.assertEqual(list_backups(env=self.env), [])

    def test_unset_in_a_missing_file_does_not_create_it(self):
        self.assertFalse(self.edit("mode", remove=True).changed)
        self.assertFalse(self.machine_file.exists())

    def test_setting_the_same_value_changes_nothing(self):
        self.write(self.machine_file, COMMENTED)
        before = self.snapshot(self.machine_file)
        self.assertFalse(self.edit("mode", "safe").changed)
        self.assertEqual(self.snapshot(self.machine_file), before)
        self.assertEqual(list_backups(env=self.env), [])

    def test_empty_and_comment_only_files_get_their_version_line(self):
        for text in ("", "# only a comment\n"):
            with self.subTest(text=text):
                self.write(self.machine_file, text)
                self.edit("mode", "fast")
                data = toml.loads(self.machine_file.read_text(encoding="utf-8"))
                self.assertEqual(data, {"schema_version": 1, "demo": {"mode": "fast"}})
                if text:
                    self.assertIn("# only a comment", self.machine_file.read_text(encoding="utf-8"))

    def test_project_and_invocation_layers(self):
        self.edit("mode", "fast", path=self.project_file, layer="project", project=self.project)
        self.assertEqual(self.resolve().get("mode"), "fast")
        other = self.root / "run.toml"
        self.edit("verbose", True, path=other, layer="invocation")
        self.assertEqual(self.resolve(config_file=other).get("verbose"), True)

    def test_layer_name_is_checked(self):
        with self.assertRaises(ValueError):
            self.edit("mode", "fast", layer="env")


class TestBackup(EditCase):
    def test_machine_file_is_backed_up_in_machine_state(self):
        self.write(self.machine_file, COMMENTED)
        result = self.edit("mode", "fast")
        self.assertIsNotNone(result.backup)
        self.assertEqual(result.backup.read_text(encoding="utf-8"), COMMENTED)
        self.assertTrue(str(result.backup).startswith(str(self.root / "skm" / "state" / "backups")))
        self.assertEqual(len(list_backups(env=self.env)), 1)

    def test_project_file_is_backed_up_in_the_project(self):
        self.proj("[demo]\nmode = \"safe\"\n")
        result = self.edit("mode", "fast", path=self.project_file, layer="project", project=self.project)
        self.assertTrue(str(result.backup).startswith(str(self.project / ".swissknifeman" / "backups")))
        self.assertIn('mode = "safe"', result.backup.read_text(encoding="utf-8"))

    def test_new_file_has_nothing_to_back_up(self):
        self.assertIsNone(self.edit("mode", "fast").backup)
        self.assertEqual(list_backups(env=self.env), [])

    def test_backups_rotate(self):
        self.write(self.machine_file, COMMENTED)
        for number in range(1, 14):
            self.edit("recompute.candidate_min_n", 100 + number)
        self.assertEqual(len(list_backups(env=self.env)), 10)

    def test_machine_directory_is_private_when_created(self):
        self.edit("mode", "fast")
        self.assertEqual(stat.S_IMODE(self.machine_file.parent.stat().st_mode), 0o700)

    def test_file_mode_is_kept(self):
        self.write(self.machine_file, COMMENTED)
        os.chmod(self.machine_file, 0o600)
        self.edit("mode", "fast")
        self.assertEqual(stat.S_IMODE(self.machine_file.stat().st_mode), 0o600)


class TestErrorsChangeNothing(EditCase):
    def setUp(self):
        super().setUp()
        self.write(self.machine_file, COMMENTED)
        self.before = self.snapshot(self.machine_file)

    def refuse(self, code, *args, **kwargs):
        with self.assertRaises(ConfigError) as caught:
            self.edit(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.snapshot(self.machine_file), self.before)
        self.assertEqual(list_backups(env=self.env), [])
        self.assertEqual(sorted(self.machine_file.parent.glob("*.tmp")), [])
        return caught.exception

    def test_unknown_key(self):
        self.refuse("CONFIG_UNKNOWN_KEY", "bogus", 1)
        self.refuse("CONFIG_UNKNOWN_KEY", "recompute", 1)  # a table is not a key

    def test_wrong_type_and_range(self):
        self.refuse("CONFIG_TYPE", "recompute.candidate_min_n", "many")
        self.refuse("CONFIG_TYPE", "recompute.candidate_min_n", 0)
        self.refuse("CONFIG_TYPE", "mode", "slow")
        self.refuse("CONFIG_TYPE", "sources", ["a", "a"])

    def test_forbidden_layer(self):
        self.edit("cache_dir", "/var/cache")  # the machine layer may set it
        with self.assertRaises(ConfigError) as caught:
            self.edit("cache_dir", "/elsewhere", path=self.project_file, layer="project", project=self.project)
        self.assertEqual(caught.exception.code, "CONFIG_LAYER_FORBIDDEN")
        self.assertFalse(self.project_file.exists())

    def test_secret_key_takes_only_a_reference(self):
        error = self.refuse("SECRET_REF_INVALID", "token", "plain-secret-value")
        self.assertNotIn("plain-secret-value", str(error))
        self.edit("token", "env://DEMO_TOKEN")
        self.assertEqual(self.resolve().get("token"), "env://DEMO_TOKEN")

    def test_broken_existing_file_is_not_touched(self):
        for text in ("schema_version = 1\n[demo\n", "[demo]\nmode = \"fast\"\n", "schema_version = 9\n",
                     "schema_version = 1\n[demo]\nbogus = 1\n"):
            with self.subTest(text=text):
                self.write(self.machine_file, text)
                before = self.snapshot(self.machine_file)
                self.assertUnchanged(self.machine_file, before, lambda: self.edit("mode", "fast"))
                self.assertEqual(list_backups(env=self.env), [])

    def test_editor_refusal_is_not_a_write(self):
        self.write(self.machine_file, 'schema_version = 1\n[demo]\nsources = [\n  "a",\n  "b",\n]\n')
        before = self.snapshot(self.machine_file)
        self.assertUnchanged(self.machine_file, before, lambda: self.edit("sources", ["c"]))
        self.assertEqual(list_backups(env=self.env), [])

    def test_failed_write_leaves_the_file_and_no_temp_file(self):
        with mock.patch("aicore.util.io.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.edit("mode", "fast")
        self.assertEqual(self.snapshot(self.machine_file), self.before)
        self.assertEqual(sorted(self.machine_file.parent.glob("*.tmp")), [])

    def test_unreadable_file(self):
        self.machine_file.write_bytes(b"\xff\xfe\x00bad")
        before = self.snapshot(self.machine_file)
        self.assertUnchanged(self.machine_file, before, lambda: self.edit("mode", "fast"))


class TestSymlink(EditCase):
    def test_the_link_stays_and_its_target_changes(self):
        target = self.write(self.root / "dotfiles" / "config.toml", COMMENTED)
        self.machine_file.parent.mkdir(parents=True)
        os.symlink(target, self.machine_file)
        result = self.edit("mode", "fast")
        self.assertTrue(self.machine_file.is_symlink())
        self.assertIn('mode = "fast"', target.read_text(encoding="utf-8"))
        self.assertEqual(result.backup.read_text(encoding="utf-8"), COMMENTED)


if __name__ == "__main__":
    unittest.main()
