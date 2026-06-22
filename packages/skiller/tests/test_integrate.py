"""Тесты визарда integrate (после выноса окружения в пакет harness).

Здесь остаётся ОРКЕСТРАЦИЯ и политика выбора: dry-run ничего не пишет,
minimal-бандл подключает скиллы, `_gather`/`_default_mcp` резолвят набор MCP.
Само ИСПОЛНЕНИЕ окружения (permissions/MCP/auto-approve/memory) делегируется
пакету harness через subprocess — его блоки покрыты тестами в packages/harness/tests.
В фикстуре harness не установлен → env-блоки мягко пропускаются (graceful skip).

Гоняются против синтетического реестра (tests/fixtures) во временных каталогах;
env.home указывает в tmp — реальные ~/.swissknifeman и ~/.claude не трогаются."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from skiller.integrate import cmd_integrate, _default_mcp, _gather
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
        self.assertFalse((self.proj / ".mcp.json").exists())

    # --- minimal bundle = connect only (env-блоки выключены) ----------------
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

    # --- MCP choice policy (остаётся в визарде; исполнение — в harness) ------
    def test_default_mcp_dev_vs_vault(self):
        self.assertEqual(_default_mcp(self.proj), ["context7"])   # laravel = dev
        vault = self.tmp / "vault"; (vault / ".obsidian").mkdir(parents=True)
        self.assertEqual(_default_mcp(vault), [])                 # vault ≠ dev

    def test_bundle_resolves_dev_mcp(self):
        # recommended/full на dev-проекте → context7; minimal → пусто
        rec = _gather(self.env, self.proj, {"file": None}, "recommended", False)
        self.assertEqual(rec["mcp"], ["context7"])
        mn = _gather(self.env, self.proj, {"file": None}, "minimal", False)
        self.assertEqual(mn["mcp"], [])
        # тот же bundle на obsidian-vault → пусто (не dev-среда)
        vault = self.tmp / "vault"; (vault / ".obsidian").mkdir(parents=True)
        rv = _gather(self.env, vault, {"file": None}, "recommended", False)
        self.assertEqual(rv["mcp"], [])

    def test_mcp_flag_unions_with_default(self):
        # --mcp добавляет opt-in пресеты поверх dev-дефолта, без дублей
        rec = _gather(self.env, self.proj,
                      {"file": None, "mcp": "playwright"}, "recommended", False)
        self.assertEqual(rec["mcp"], ["context7", "playwright"])
        # minimal: context7 нет, но явный --mcp ставится
        mn = _gather(self.env, self.proj,
                     {"file": None, "mcp": "playwright"}, "minimal", False)
        self.assertEqual(mn["mcp"], ["playwright"])
        # дубль context7 не плодится
        dup = _gather(self.env, self.proj,
                      {"file": None, "mcp": "context7,playwright"}, "recommended", False)
        self.assertEqual(dup["mcp"], ["context7", "playwright"])
        # на obsidian-vault явный --mcp бьёт dev-гейт
        vault = self.tmp / "vault2"; (vault / ".obsidian").mkdir(parents=True)
        rv = _gather(self.env, vault,
                     {"file": None, "mcp": "playwright"}, "recommended", False)
        self.assertEqual(rv["mcp"], ["playwright"])

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
