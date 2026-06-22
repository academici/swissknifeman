"""Тесты артефактов плагина Claude Code: манифест, marketplace, .mcp.json, slash-команды.

Плагин — тонкое лицо над CLI (commands/*.md зовут `maind`). Тест проверяет, что
статические артефакты в репозитории валидны и консистентны между собой (имена,
пути, ссылки), чтобы битый манифест ловился до установки плагина."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / ".claude-plugin"
COMMANDS = ["maind", "onboard", "sync", "status", "health", "doctor"]


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter(text):
    """Тело YAML-фронтматтера (между первыми двумя '---') или None."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    return parts[1] if len(parts) >= 3 else None


class TestPluginManifest(unittest.TestCase):
    def test_plugin_json_valid_and_links_exist(self):
        m = _load_json(PLUGIN_DIR / "plugin.json")
        self.assertEqual(m["name"], "maind")
        # Claude Code plugin schema: commands — массив путей.
        self.assertIsInstance(m.get("commands"), list, "commands должен быть массивом путей")
        self.assertTrue((ROOT / "commands").is_dir(), "нет каталога commands/")
        # Плагин — ТОЛЬКО скиллы/команды (slash → CLI). MCP-сервера в плагине нет:
        # per-project `maind` приходит из .mcp.json проекта (project-линза), а ecosystem-факт
        # пишется явным scope:"global". Иначе плагин дублировал бы тулсет `maind_*` в каждой
        # сессии вторым `maind-hub`-сервером (--scope global) — устранённая путаница.
        self.assertNotIn("mcpServers", m, "плагин maind = только команды, без MCP-сервера")

    def test_marketplace_valid_and_consistent(self):
        # В монорепо marketplace.json — единый, в КОРНЕ репо (его генерит swissknifeman
        # registry, добавляя maind как sibling-пакет). Собственного marketplace у maind нет.
        repo_root = next((c for c in (ROOT, *ROOT.parents) if (c / ".git").exists()), None)
        mk_file = (repo_root / ".claude-plugin" / "marketplace.json") if repo_root else None
        if not mk_file or not mk_file.is_file():
            self.skipTest("корневой marketplace.json не найден (standalone-раскладка)")
        mk = _load_json(mk_file)
        entry = next((p for p in mk["plugins"] if p["name"] == "maind"), None)
        self.assertIsNotNone(entry, "maind отсутствует в корневом marketplace")
        self.assertEqual(entry["source"], "./packages/maind")
        # имя плагина в marketplace совпадает с plugin.json (install: maind@<marketplace>)
        self.assertEqual(entry["name"], _load_json(PLUGIN_DIR / "plugin.json")["name"])


class TestPluginCommands(unittest.TestCase):
    def test_all_commands_present_with_frontmatter(self):
        for name in COMMANDS:
            path = ROOT / "commands" / f"{name}.md"
            self.assertTrue(path.is_file(), f"нет команды: {path}")
            fm = _frontmatter(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(fm, f"{name}.md без YAML-фронтматтера")
            self.assertIn("description:", fm, f"{name}.md без description")
            # YAML-значение с незакавыченным двоеточием не парсится Claude Code
            # (ловим до установки плагина — урок миграции монорепо).
            for line in fm.splitlines():
                if line.startswith("description:"):
                    val = line[len("description:"):].strip()
                    if ":" in val and not (val.startswith('"') or val.startswith("'")):
                        self.fail(f"{name}.md: description c двоеточием без кавычек — "
                                  f"битый YAML-frontmatter")

    def test_action_commands_preview_then_apply(self):
        # мутирующая команда обязана сперва dry-run, затем неинтерактивный --yes
        onboard = (ROOT / "commands" / "onboard.md").read_text(encoding="utf-8")
        self.assertIn("--dry-run", onboard)
        self.assertIn("--yes", onboard)


if __name__ == "__main__":
    unittest.main()
