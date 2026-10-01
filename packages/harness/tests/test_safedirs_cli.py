"""Internal documentation."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.safedirs import cmd_safedirs

PKG = Path(__file__).resolve().parents[1]


def run(env, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        cmd_safedirs(env, argv)
    return buf.getvalue()


class SafedirsCliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        (self.home / ".swissknifeman").mkdir(parents=True)
        (self.home / "projects" / "demo").mkdir(parents=True)

        self.env = Env(PKG, "safe-dirs", home=self.home)
        self.state = self.tmp / "state" / "safe-dirs.json"
        self.state.parent.mkdir()
        patcher = unittest.mock.patch.dict(
            os.environ, {"SKM_SAFE_DIRS_CONFIG": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def cfg(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def test_init_add_remove_list(self):
        run(self.env, ["init"])
        self.assertTrue(self.state.exists())
        self.assertEqual(self.cfg()["version"], 1)
        self.assertTrue(self.cfg()["include_registered_projects"])

        out = run(self.env, ["init"])
        self.assertIn("already exists", out)

        run(self.env, ["add", str(self.home / "projects")])
        self.assertEqual(self.cfg()["dirs"], [str(self.home / "projects")])

        out = run(self.env, ["add", str(self.home / "projects")])
        self.assertIn("is already in dirs", out)
        self.assertEqual(len(self.cfg()["dirs"]), 1)

        out = run(self.env, ["list"])
        self.assertIn(str((self.home / "projects").resolve()), out)

        run(self.env, ["add", str(self.home / "projects" / "demo" / "vendor"),
                       "--exclude"])
        self.assertEqual(len(self.cfg()["exclude"]), 1)

        run(self.env, ["remove", str(self.home / "projects")])
        self.assertEqual(self.cfg()["dirs"], [])

    def test_add_rejects_dangerous_roots(self):
        run(self.env, ["init"])
        for bad in ("/", str(self.home), str(self.home.parent), "relative/path"):
            with self.assertRaises(SystemExit, msg=f"should fail: {bad}"):
                run(self.env, ["add", bad])
        self.assertEqual(self.cfg()["dirs"], [])

    def test_remove_missing_dies(self):
        run(self.env, ["init"])
        with self.assertRaises(SystemExit):
            run(self.env, ["remove", "/nope"])

    def test_prune_ask_removes_exactly_our_rules(self):
        proj = self.tmp / "proj"
        (proj / ".claude").mkdir(parents=True)
        settings = {"permissions": {
            "ask": ["Bash(rm -r *)", "Bash(rm -rf *)", "Bash(git push *)"],
            "deny": ["Bash(sudo *)"]}}
        (proj / ".claude" / "settings.json").write_text(
            json.dumps(settings), encoding="utf-8")
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"permissions": {"ask": ["Bash(rm -rf *)"]}}), encoding="utf-8")

        out = run(self.env, ["prune-ask", "--global", "--target", str(proj)])
        self.assertIn("total rules removed: 3", out)
        after = json.loads((proj / ".claude" / "settings.json").read_text())
        self.assertEqual(after["permissions"]["ask"], ["Bash(git push *)"])
        self.assertEqual(after["permissions"]["deny"], ["Bash(sudo *)"])
        g = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertNotIn("ask", g["permissions"])

        out = run(self.env, ["prune-ask", "--global", "--target", str(proj)])
        self.assertIn("not found", out)

    def test_init_migrates_legacy_home_config(self):


        os.environ.pop("SKM_SAFE_DIRS_CONFIG")
        repo = self.tmp / "repo"
        (repo / "packages" / "fakepkg").mkdir(parents=True)
        (repo / "core").mkdir()
        env = Env(repo / "packages" / "fakepkg", "safe-dirs", home=self.home)
        legacy = self.home / ".swissknifeman" / "safe-dirs.json"
        legacy.write_text(json.dumps({"version": 1, "dirs": ["~/projects"],
                                      "include_registered_projects": True,
                                      "exclude": [], "protect_git": True,
                                      "allow_globs": True}), encoding="utf-8")
        out = run(env, ["init"])
        self.assertIn("migrated from legacy", out)
        moved = json.loads((repo / "safe-dirs.json").read_text(encoding="utf-8"))
        self.assertEqual(moved["dirs"], ["~/projects"])
        self.assertFalse(legacy.exists())
        self.assertTrue(legacy.with_suffix(".json.migrated").exists())

    def test_prune_ask_all_projects_via_registry(self):
        proj = self.tmp / "reg-proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude" / "settings.local.json").write_text(
            json.dumps({"permissions": {"ask": ["Bash(rm -r *)"]}}), encoding="utf-8")
        (self.home / ".swissknifeman" / "projects.json").write_text(
            json.dumps({"version": 1, "projects": [{"path": str(proj)},
                                                   {"path": "/nonexistent"}]}),
            encoding="utf-8")
        out = run(self.env, ["prune-ask", "--all-projects"])
        self.assertIn("total rules removed: 1", out)
        after = json.loads((proj / ".claude" / "settings.local.json").read_text())
        self.assertNotIn("ask", after["permissions"])


class SafedirsDeleteCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        (self.home / ".swissknifeman").mkdir(parents=True)
        self.trusted = self.home / "projects" / "demo"
        self.trusted.mkdir(parents=True)
        self.env = Env(PKG, "safe-dirs", home=self.home)
        self.state = self.tmp / "state" / "safe-dirs.json"
        self.state.parent.mkdir()
        patcher = unittest.mock.patch.dict(
            os.environ, {"SKM_SAFE_DIRS_CONFIG": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        run(self.env, ["init"])
        run(self.env, ["add", str(self.home / "projects")])

    def tearDown(self):
        self._tmp.cleanup()

    def test_delete_file_inside_trusted_root(self):
        target = self.trusted / "leftover.txt"
        target.write_text("x", encoding="utf-8")
        out = run(self.env, ["delete", str(target)])
        self.assertIn("deleted", out)
        self.assertFalse(target.exists())

    def test_delete_directory_inside_trusted_root(self):
        target = self.trusted / "skills"
        (target / "sub").mkdir(parents=True)
        (target / "sub" / "f.md").write_text("x", encoding="utf-8")
        run(self.env, ["delete", str(target)])
        self.assertFalse(target.exists())

    def test_delete_multiple_paths_one_call(self):
        a = self.trusted / "a.txt"
        b = self.trusted / "b.txt"
        a.write_text("x", encoding="utf-8")
        b.write_text("x", encoding="utf-8")
        out = run(self.env, ["delete", str(a), str(b)])
        self.assertEqual(out.count("deleted"), 2)
        self.assertFalse(a.exists())
        self.assertFalse(b.exists())

    def test_delete_dry_run_does_not_touch_disk(self):
        target = self.trusted / "keep.txt"
        target.write_text("x", encoding="utf-8")
        out = run(self.env, ["delete", str(target), "--dry-run"])
        self.assertIn("[dry-run]", out)
        self.assertTrue(target.exists())

    def test_delete_rejects_path_outside_allowlist(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            run(self.env, ["delete", str(outside)])
        self.assertTrue(outside.exists())

    def test_delete_rejects_dotgit_component(self):
        gitdir = self.trusted / ".git" / "hooks"
        gitdir.mkdir(parents=True)
        with self.assertRaises(SystemExit):
            run(self.env, ["delete", str(gitdir)])
        self.assertTrue(gitdir.exists())

    def test_delete_rejects_glob_metachars(self):
        with self.assertRaises(SystemExit):
            run(self.env, ["delete", str(self.trusted / "*.txt")])

    def test_delete_rejects_dotdot_component(self):
        with self.assertRaises(SystemExit):
            run(self.env, ["delete", str(self.trusted / ".." / "escape")])

    def test_delete_skips_absent_path(self):
        target = self.trusted / "gone.txt"
        out = run(self.env, ["delete", str(target)])
        self.assertIn("is no longer available", out)

    def test_delete_no_args_dies(self):
        with self.assertRaises(SystemExit):
            run(self.env, ["delete"])

    def test_delete_logs_jsonl(self):
        target = self.trusted / "logged.txt"
        target.write_text("x", encoding="utf-8")
        run(self.env, ["delete", str(target)])
        log_file = self.home / ".claude" / "logs" / "safe-delete-decisions.jsonl"
        self.assertTrue(log_file.exists())
        entry = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["result"], "deleted")
        self.assertFalse(entry["dry_run"])


if __name__ == "__main__":
    unittest.main()
