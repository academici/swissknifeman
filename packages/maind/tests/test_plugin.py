"""Plugin artifact tests Claude Code: manifest, marketplace, .mcp.json, slash-commands.

Plugin - thin face over CLI (commands/*.md name `maind`). The test verifies that
static artifacts in the repository are valid and consistent with each other (names,
paths, links), so that a broken manifest is caught before installing the plugin."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / ".claude-plugin"
COMMANDS = ["maind", "onboard", "sync", "status", "health", "doctor"]


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter(text):
    """Body YAML-frontmatter (between the first two '---') or None."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    return parts[1] if len(parts) >= 3 else None


class TestPluginManifest(unittest.TestCase):
    def test_plugin_json_valid_and_links_exist(self):
        m = _load_json(PLUGIN_DIR / "plugin.json")
        self.assertEqual(m["name"], "maind")
        # Claude Code plugin schema: commands — array of paths.
        self.assertIsInstance(m.get("commands"), list, "commands must be an array of paths")
        self.assertTrue((ROOT / "commands").is_dir(), "no directory commands/")
        # Plugin - ONLY skills/commands (slash → CLI). MCP-there is no server in the plugin:
        # per-project `maind` comes from .mcp.json project (project-lens), a ecosystem-fact
        # is written explicitly scope:"global". Otherwise the plugin would duplicate the toolset `maind_*` in each
        # session second `maind-hub`-server (--scope global) — confusion cleared.
        self.assertNotIn("mcpServers", m, "plugin maind = commands only, without MCP-server")

    def test_marketplace_valid_and_consistent(self):
        # In monorepo marketplace.json — single, in the ROOT of the repo (generates it swissknifeman
        # registry, adding maind like sibling-package). Own marketplace y maind no.
        repo_root = next((c for c in (ROOT, *ROOT.parents) if (c / ".git").exists()), None)
        mk_file = (repo_root / ".claude-plugin" / "marketplace.json") if repo_root else None
        if not mk_file or not mk_file.is_file():
            self.skipTest("root marketplace.json not found (standalone-layout)")
        mk = _load_json(mk_file)
        entry = next((p for p in mk["plugins"] if p["name"] == "maind"), None)
        self.assertIsNotNone(entry, "maind is missing from root marketplace")
        self.assertEqual(entry["source"], "./packages/maind")
        # plugin name in marketplace matches plugin.json (install: maind@<marketplace>)
        self.assertEqual(entry["name"], _load_json(PLUGIN_DIR / "plugin.json")["name"])


class TestPluginCommands(unittest.TestCase):
    def test_all_commands_present_with_frontmatter(self):
        for name in COMMANDS:
            path = ROOT / "commands" / f"{name}.md"
            self.assertTrue(path.is_file(), f"no command: {path}")
            fm = _frontmatter(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(fm, f"{name}.md without YAML-frontmatter")
            self.assertIn("description:", fm, f"{name}.md without description")
            # YAML-value with unquoted colon is not parsed Claude Code
            # (catch before installing the plugin - monorepo migration lesson).
            for line in fm.splitlines():
                if line.startswith("description:"):
                    val = line[len("description:"):].strip()
                    if ":" in val and not (val.startswith('"') or val.startswith("'")):
                        self.fail(f"{name}.md: description c with a colon without quotes - "
                                  f"broken YAML-frontmatter")

    def test_action_commands_preview_then_apply(self):
        # the mutating command must first dry-run, then non-interactive --yes
        onboard = (ROOT / "commands" / "onboard.md").read_text(encoding="utf-8")
        self.assertIn("--dry-run", onboard)
        self.assertIn("--yes", onboard)


if __name__ == "__main__":
    unittest.main()
