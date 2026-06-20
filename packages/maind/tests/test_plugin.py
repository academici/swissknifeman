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
        self.assertEqual(m.get("commands"), "commands/")
        self.assertTrue((ROOT / "commands").is_dir(), "нет каталога commands/")
        self.assertTrue((ROOT / m["mcpServers"]).is_file(), "manifest.mcpServers → нет файла")

    def test_marketplace_valid_and_consistent(self):
        mk = _load_json(PLUGIN_DIR / "marketplace.json")
        entry = next(p for p in mk["plugins"] if p["name"] == "maind")
        self.assertEqual(entry["source"], "./")
        # имя плагина в marketplace совпадает с plugin.json (install: maind@<marketplace>)
        self.assertEqual(entry["name"], _load_json(PLUGIN_DIR / "plugin.json")["name"])

    def test_mcp_server_points_to_launcher(self):
        srv = _load_json(ROOT / ".mcp.json")["mcpServers"]["maind-hub"]
        self.assertIn("bin/maind", srv["command"])  # абсолютный путь через ${CLAUDE_PLUGIN_ROOT}
        self.assertIn("mcp", srv["args"])


class TestPluginCommands(unittest.TestCase):
    def test_all_commands_present_with_frontmatter(self):
        for name in COMMANDS:
            path = ROOT / "commands" / f"{name}.md"
            self.assertTrue(path.is_file(), f"нет команды: {path}")
            fm = _frontmatter(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(fm, f"{name}.md без YAML-фронтматтера")
            self.assertIn("description:", fm, f"{name}.md без description")

    def test_action_commands_preview_then_apply(self):
        # мутирующая команда обязана сперва dry-run, затем неинтерактивный --yes
        onboard = (ROOT / "commands" / "onboard.md").read_text(encoding="utf-8")
        self.assertIn("--dry-run", onboard)
        self.assertIn("--yes", onboard)


if __name__ == "__main__":
    unittest.main()
