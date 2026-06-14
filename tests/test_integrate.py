"""Тесты визарда integrate: dry-run ничего не пишет, minimal-бандл подключает
скиллы, блоки auto-approve/memory пишут per-project конфиг merge-only.

Гоняются против синтетического реестра (tests/fixtures) во временных каталогах;
env.home указывает в tmp — реальные ~/.swissknifeman и ~/.claude не трогаются.
Шелл-блок permissions пропускается (в фикстуре нет scripts/apply-permissions.sh)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from swissknifeman.integrate import (
    cmd_integrate, _block_autoapprove, _block_memory,
)
from swissknifeman.config import load_config
import tests.fixtures as fx


def run(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


class IntegrateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.root, self.env = fx.make_registry(self.tmp)
        self.proj = fx.make_laravel_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    # --- dry-run ------------------------------------------------------------
    def test_dry_run_writes_nothing(self):
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "full", "--yes", "--dry-run"])
        self.assertFalse((self.proj / ".claude").exists())
        self.assertFalse((self.proj / ".swissknife.json").exists())

    # --- minimal bundle = connect only --------------------------------------
    def test_minimal_connects_skills(self):
        run(cmd_integrate, self.env,
            ["--target", str(self.proj), "--bundle", "minimal", "--yes"])
        settings = json.loads(
            (self.proj / ".claude" / "settings.local.json").read_text())
        self.assertIn("swissknifeman", settings.get("extraKnownMarketplaces", {}))
        self.assertTrue(any(k.endswith("@swissknifeman")
                            for k in settings.get("enabledPlugins", {})))
        # зарегистрирован в projects.json (в tmp home, не в реальном)
        db = json.loads((self.env.home / ".swissknifeman" / "projects.json").read_text())
        self.assertTrue(any(p["path"] == str(self.proj) for p in db["projects"]))

    # --- auto-approve block: env.ini + hooks, merge-only --------------------
    def test_autoapprove_writes_envini_and_hooks_idempotent(self):
        ch = {"autoapprove": "strict", "settings_file": "settings.json"}
        run(_block_autoapprove, self.proj, ch, False)
        self.assertEqual(
            (self.proj / ".claude" / "auto-approve.env.ini").read_text().strip(),
            "MODE=strict")
        s = json.loads((self.proj / ".claude" / "settings.json").read_text())
        matchers = [e.get("matcher") for e in s["hooks"]["PreToolUse"]]
        self.assertEqual(sorted(matchers), ["Bash", "ExitPlanMode"])
        # повтор не плодит дубли (merge-only)
        run(_block_autoapprove, self.proj, ch, False)
        s2 = json.loads((self.proj / ".claude" / "settings.json").read_text())
        self.assertEqual(len(s2["hooks"]["PreToolUse"]), 2)

    def test_autoapprove_off_no_hook(self):
        ch = {"autoapprove": "off", "settings_file": "settings.json"}
        run(_block_autoapprove, self.proj, ch, False)
        self.assertEqual(
            (self.proj / ".claude" / "auto-approve.env.ini").read_text().strip(),
            "MODE=off")
        self.assertFalse((self.proj / ".claude" / "settings.json").exists())

    def test_autoapprove_preserves_existing_settings(self):
        cdir = self.proj / ".claude"; cdir.mkdir(parents=True)
        (cdir / "settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}) + "\n")
        run(_block_autoapprove, self.proj, {"autoapprove": "permissive",
                                            "settings_file": "settings.json"}, False)
        s = json.loads((cdir / "settings.json").read_text())
        self.assertEqual(s["permissions"]["allow"], ["Bash(ls *)"])  # не затёрто
        self.assertIn("PreToolUse", s["hooks"])

    # --- memory block: .swissknife.json + env.ini ---------------------------
    def test_memory_writes_brain_membership(self):
        ch = {"memory": "federation", "memory_brain": "core"}
        run(_block_memory, self.env, self.proj, ch, False)
        cfg = json.loads((self.proj / ".swissknife.json").read_text())
        self.assertEqual(cfg["memory_brain"], "core")
        self.assertEqual(
            (self.proj / ".claude" / "memory.env.ini").read_text().strip(),
            "MODE=federation")
        # memory_brain — валидный ключ .swissknife.json (CONFIG_KEYS расширен)
        self.assertEqual(load_config(self.env, self.proj).get("memory_brain"), "core")

    # --- guards -------------------------------------------------------------
    def test_unknown_bundle_exits(self):
        with self.assertRaises(SystemExit):
            run(cmd_integrate, self.env,
                ["--target", str(self.proj), "--bundle", "nope", "--yes"])

    def test_refuses_registry_root(self):
        with self.assertRaises(SystemExit):
            run(cmd_integrate, self.env, ["--target", str(self.root), "--yes"])

    def test_help(self):
        out = run(cmd_integrate, self.env, ["--help"])
        self.assertIn("integrate", out)


if __name__ == "__main__":
    unittest.main()
