"""CLI harness safe-dirs: init/add/remove/list по machine-owned state (tmp,
через эксклюзивный $SKM_SAFE_DIRS_CONFIG — иначе _state_file нашёл бы реальный
монорепо), миграция legacy из home, гарды опасных корней, prune-ask снимает
ровно «свои» ask-правила rm."""
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
        # env указывает на реальный пакет (configs с хуком), но home — tmp
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
        # повторный init — no-op
        out = run(self.env, ["init"])
        self.assertIn("уже существует", out)

        run(self.env, ["add", str(self.home / "projects")])
        self.assertEqual(self.cfg()["dirs"], [str(self.home / "projects")])
        # дубль по resolved-пути не плодится
        out = run(self.env, ["add", str(self.home / "projects")])
        self.assertIn("уже в dirs", out)
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
            with self.assertRaises(SystemExit, msg=f"должен отказать: {bad}"):
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
        self.assertIn("итого снято правил: 3", out)
        after = json.loads((proj / ".claude" / "settings.json").read_text())
        self.assertEqual(after["permissions"]["ask"], ["Bash(git push *)"])
        self.assertEqual(after["permissions"]["deny"], ["Bash(sudo *)"])
        g = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertNotIn("ask", g["permissions"])
        # повторный прогон — чисто
        out = run(self.env, ["prune-ask", "--global", "--target", str(proj)])
        self.assertIn("не найдены", out)

    def test_init_migrates_legacy_home_config(self):
        # env-override снят: фейковый монорепо (маркеры packages/+core/) — цель init,
        # legacy-конфиг в home должен переехать туда с сохранением содержимого
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
        self.assertIn("мигрировано из legacy", out)
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
        self.assertIn("итого снято правил: 1", out)
        after = json.loads((proj / ".claude" / "settings.local.json").read_text())
        self.assertNotIn("ask", after["permissions"])


if __name__ == "__main__":
    unittest.main()
