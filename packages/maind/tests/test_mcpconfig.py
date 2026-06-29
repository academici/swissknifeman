"""Тесты mcpconfig — безопасное слияние MCP-конфигов (не затирать чужие серверы)."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.mcpconfig import (EXAMPLE_SUFFIX, MCPConfigError, has_server,
                             load_mcp, merge_server, reconcile_gitignore,
                             write_example, write_mcp)


class TestMcpConfig(unittest.TestCase):
    def test_load_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, existed = load_mcp(Path(tmp) / "nope.json")
            self.assertFalse(existed)
            self.assertEqual(data, {"mcpServers": {}})

    def test_merge_into_empty(self):
        data, _ = load_mcp("/nonexistent/x.json")
        data, changed = merge_server(data, "agentmemory", {"command": "x"})
        self.assertTrue(changed)
        self.assertIn("agentmemory", data["mcpServers"])

    def test_preserves_foreign_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".cursor" / "mcp.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"mcpServers": {"laravel-boost": {"command": "php"}}}),
                         encoding="utf-8")
            data, existed = load_mcp(p)
            self.assertTrue(existed)
            data, _ = merge_server(data, "agentmemory", {"command": "x"})
            write_mcp(p, data)
            servers = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]
            self.assertIn("laravel-boost", servers)  # чужой сохранён
            self.assertIn("agentmemory", servers)

    def test_idempotent(self):
        data, _ = load_mcp("/nonexistent/x.json")
        entry = {"command": "x", "args": ["mcp"]}
        data, c1 = merge_server(data, "a", entry)
        data, c2 = merge_server(data, "a", entry)
        self.assertTrue(c1)
        self.assertFalse(c2)

    def test_broken_json_raises(self):
        # Битый JSON → MCPConfigError (вызывающий решает фатальность), файл не трогаем.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".mcp.json"
            p.write_text("{ broken", encoding="utf-8")
            with self.assertRaises(MCPConfigError):
                load_mcp(p)

    def test_non_object_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".mcp.json"
            p.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertRaises(MCPConfigError):
                load_mcp(p)

    def test_backup_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".mcp.json"
            p.write_text(json.dumps({"mcpServers": {"old": {}}}), encoding="utf-8")
            data, _ = load_mcp(p)
            data, _ = merge_server(data, "new", {"command": "x"})
            write_mcp(p, data, dry=True)  # ничего не пишет
            self.assertNotIn("new", json.loads(p.read_text())["mcpServers"])
            write_mcp(p, data)            # реальная запись + .bak
            self.assertTrue((Path(tmp) / ".mcp.json.bak").exists())
            self.assertIn("new", json.loads(p.read_text())["mcpServers"])

    def test_has_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".mcp.json"
            self.assertFalse(has_server(p, "x"))
            p.write_text(json.dumps({"mcpServers": {"x": {}}}), encoding="utf-8")
            self.assertTrue(has_server(p, "x"))
            self.assertFalse(has_server(p, "y"))

    def test_write_example_placeholders(self):
        """write_example: путь проекта → <ABS_PATH_TO_PROJECT>, домашний префикс → <HOME>;
        реальных абс. путей в .example не остаётся; индирекция ${MAIND_BIN:-maind} сохранена."""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "proj"
            proj.mkdir()
            home = os.path.expanduser("~")
            data = {"mcpServers": {
                "maind": {"command": "${MAIND_BIN:-maind}", "args": ["mcp"]},
                "serena": {"command": "uvx", "args": ["--project", str(proj)]},
                "x": {"command": f"{home}/tools/x.sh"}}}
            write_example(proj / ".mcp.json", data, proj)
            ex = json.loads((proj / (".mcp.json" + EXAMPLE_SUFFIX)).read_text())
            self.assertIn("<ABS_PATH_TO_PROJECT>", ex["mcpServers"]["serena"]["args"])
            self.assertEqual(ex["mcpServers"]["x"]["command"], "<HOME>/tools/x.sh")
            self.assertEqual(ex["mcpServers"]["maind"]["command"], "${MAIND_BIN:-maind}")
            self.assertNotIn(str(proj), json.dumps(ex))

    def test_reconcile_gitignore(self):
        """real MCP-конфиг → В .gitignore; его .example → НЕ в .gitignore (даже если был);
        чужие правила не тронуты; идемпотентно."""
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            (proj / ".gitignore").write_text(".env\n.mcp.json.example\n", encoding="utf-8")
            self.assertTrue(reconcile_gitignore(proj, ".mcp.json"))
            lines = (proj / ".gitignore").read_text().splitlines()
            self.assertIn(".mcp.json", lines)
            self.assertNotIn(".mcp.json.example", lines)
            self.assertIn(".env", lines)
            self.assertFalse(reconcile_gitignore(proj, ".mcp.json"))  # идемпотентно


if __name__ == "__main__":
    unittest.main()
