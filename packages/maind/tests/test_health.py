"""Тесты health.py: отчёт о связи, провиженеры health-doc/health-hook, CLI."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from maind import health
from maind.config import load_config
from tests.fixtures import FakeMemoryServer, capture, make_repo, write_maind_config

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _setup(tmp, *, with_mcp=False, memory_url=None, hook_maind=False):
    root, env = make_repo(tmp)
    shutil.copytree(_TEMPLATES, root / "templates")  # шаблоны health доступны в env.root
    proj = Path(tmp) / "flexcrm"
    proj.mkdir(parents=True, exist_ok=True)
    if with_mcp:
        (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "agentmemory": {"command": "x"}, "maind": {"command": "y"}}}), encoding="utf-8")
    if hook_maind:                            # хук памяти в режиме демона
        (proj / ".claude").mkdir(parents=True, exist_ok=True)
        (proj / ".claude" / "memory.env.ini").write_text("MODE=maind\n", encoding="utf-8")
    projects = [{"id": "flexcrm", "name": "FlexCRM", "type": "php-package",
                 "status": "active", "enabled": True, "local_path": str(proj),
                 "memory_scope": "project:flexcrm"}]
    cfg_over = {"graph": {"adapter": "federation"}, "projects": projects}
    if memory_url:
        cfg_over["memory"] = {"url": memory_url}
    write_maind_config(root, **cfg_over)
    config, _ = load_config(env)
    return env, config, config["projects"][0], proj


class TestReport(unittest.TestCase):
    def test_standalone_when_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            rep = health.health_report(env, config, proj, memory_reachable=False)
            self.assertEqual(rep["status"], "standalone")
            self.assertFalse(rep["maind_mcp"])
            self.assertTrue(any("start --only memory" in h for h in rep["hints"]))

    def test_connected_with_mcp_and_daemon(self):
        # Полностью здоровый проект: MCP + демон + MODE=maind + native off + digest-инжект + round-trip.
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=True)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)  # native off + digest hook
            rep = health.health_report(env, config, proj, memory_reachable=True)
            self.assertEqual(rep["status"], "connected")
            self.assertTrue(rep["maind_mcp"])
            self.assertEqual(rep["hook_memory_mode"], "maind")
            self.assertTrue(rep["native_memory_off"] and rep["digest_hook"])
            self.assertTrue(rep["memory_roundtrip"])      # write→recall→forget прошёл
            self.assertEqual(rep["hints"], [])

    def test_roundtrip_fails_when_split(self):
        # Демон есть, но хук не в режиме maind → подсказка про режим (ловит раскол).
        with tempfile.TemporaryDirectory() as tmp, FakeMemoryServer() as url:
            env, config, proj, _ = _setup(tmp, with_mcp=True, memory_url=url, hook_maind=False)
            rep = health.health_report(env, config, proj, memory_reachable=True)
            self.assertTrue(rep["memory_roundtrip"])       # сам демон отвечает
            self.assertNotEqual(rep["hook_memory_mode"], "maind")
            self.assertTrue(any("режиме maind" in h for h in rep["hints"]))


class TestHealthDoc(unittest.TestCase):
    def test_install_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r1 = health.apply_health_doc(env, config, proj, "auto", dry=False)
            self.assertEqual(r1["state"], "absent")
            self.assertTrue(r1["changed"])
            claude = (pdir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("ПРИОРИТЕТ №1", claude)
            self.assertIn("project:flexcrm", claude)
            r2 = health.apply_health_doc(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_install_mode_skips_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_health_doc(env, config, proj, "auto", dry=False)
            # подделать дрейф
            claude = pdir / "CLAUDE.md"
            claude.write_text(claude.read_text().replace("ПРИОРИТЕТ №1", "СТАРОЕ"),
                              encoding="utf-8")
            r = health.apply_health_doc(env, config, proj, "install", dry=False)
            self.assertEqual(r["state"], "stale")
            self.assertFalse(r["changed"])  # install НЕ обновляет устаревшее
            r2 = health.apply_health_doc(env, config, proj, "update", dry=False)
            self.assertTrue(r2["changed"])  # update — обновляет
            self.assertIn("ПРИОРИТЕТ №1", claude.read_text())

    def test_preserves_foreign_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            (pdir / "CLAUDE.md").write_text("# FlexCRM\n\nМоя документация.\n", encoding="utf-8")
            health.apply_health_doc(env, config, proj, "auto", dry=False)
            txt = (pdir / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn("Моя документация", txt)
            self.assertIn("ПРИОРИТЕТ №1", txt)


class TestHealthHook(unittest.TestCase):
    def test_creates_script_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = health.apply_health_hook(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertTrue((pdir / ".claude" / "maind-health.sh").is_file())
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            ss = settings["hooks"]["SessionStart"]
            cmds = [h["command"] for g in ss for h in g["hooks"]]
            self.assertTrue(any("maind-health" in c for c in cmds))

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            health.apply_health_hook(env, config, proj, "auto", dry=False)
            r2 = health.apply_health_hook(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_feature_log_hook_session_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = health.apply_feature_log_hook(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertTrue((pdir / ".claude" / "maind-feature-log.sh").is_file())
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            cmds = [h["command"] for g in settings["hooks"]["SessionEnd"]
                    for h in g["hooks"]]
            self.assertTrue(any("maind-feature-log" in c for c in cmds))
            # SessionEnd-хук не конфликтует с SessionStart (health) — оба сосуществуют
            health.apply_health_hook(env, config, proj, "auto", dry=False)
            s2 = json.loads((pdir / ".claude" / "settings.json").read_text())
            self.assertIn("SessionStart", s2["hooks"])
            self.assertIn("SessionEnd", s2["hooks"])


class TestMemoryHook(unittest.TestCase):
    def test_apply_wires_digest_hook_and_disables_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            r = health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self.assertTrue(r["changed"])
            self.assertTrue((pdir / ".claude" / "maind-memory.sh").is_file())
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            self.assertIs(settings["autoMemoryEnabled"], False)   # native выключена
            cmds = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
            self.assertTrue(any("maind-memory" in c for c in cmds))

    def test_apply_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, _ = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            r2 = health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self.assertEqual(r2["state"], "fresh")
            self.assertFalse(r2["changed"])

    def test_revert_restores_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            health.revert_memory_hook(env, config, proj, dry=False)
            settings = json.loads((pdir / ".claude" / "settings.json").read_text())
            self.assertNotIn("autoMemoryEnabled", settings)       # native возвращена
            cmds = [h["command"] for g in settings.get("hooks", {}).get("SessionStart", [])
                    for h in g["hooks"]]
            self.assertFalse(any("maind-memory" in c for c in cmds))


class TestHookPortability(unittest.TestCase):
    """Сгенерированные хук-скрипты НЕ содержат машинно-специфичного пути к maind:
    лаунчер резолвится в рантайме (env MAIND_BIN → PATH). Защита от утечки абс-пути."""

    def _assert_portable(self, script_path, env):
        txt = script_path.read_text(encoding="utf-8")
        self.assertNotIn(str(env.root), txt)        # нет baked абс-пути пакета maind
        self.assertNotIn("/bin/maind", txt)
        self.assertNotIn("{{MAIND_BIN}}", txt)      # плейсхолдер не утёк
        self.assertIn("MAIND_BIN", txt)             # env-override
        self.assertIn("command -v maind", txt)      # PATH-фолбэк

    def test_memory_hook_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_memory_hook(env, config, proj, "auto", dry=False)
            self._assert_portable(pdir / ".claude" / "maind-memory.sh", env)

    def test_health_hook_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_health_hook(env, config, proj, "auto", dry=False)
            self._assert_portable(pdir / ".claude" / "maind-health.sh", env)

    def test_feature_log_hook_portable_and_keeps_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, proj, pdir = _setup(tmp)
            health.apply_feature_log_hook(env, config, proj, "auto", dry=False)
            script = pdir / ".claude" / "maind-feature-log.sh"
            self._assert_portable(script, env)
            # снятие MAIND_BIN не сломало подстановку {{PROJECT}}
            self.assertIn('--project "flexcrm"', script.read_text(encoding="utf-8"))


class TestCLI(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, config, _, _ = _setup(tmp, with_mcp=True)
            _, out = capture(health.cmd_health, env, ["--project", "flexcrm", "--json"])
            rep = json.loads(out)
            self.assertEqual(rep["id"], "flexcrm")
            self.assertIn("status", rep)


if __name__ == "__main__":
    unittest.main()
