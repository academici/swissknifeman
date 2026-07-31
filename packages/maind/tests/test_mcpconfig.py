"""Тесты mcpconfig — безопасное слияние MCP-конфигов (не затирать чужие серверы)."""
import json
import tempfile
import unittest
from pathlib import Path

from maind.mcpconfig import (EXAMPLE_SUFFIX, MCPConfigError, check_hygiene,
                             has_server, load_mcp, merge_server,
                             reconcile_gitignore, write_example, write_mcp)


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

    def test_write_example_is_idempotent_and_reports_changed(self):
        """write_example: первый прогон changed=True и пишет файл; повтор на идентичных
        данных changed=False и НЕ переписывает файл (dry на совпадении ничего не печатает);
        изменившиеся данные снова дают changed=True и переписывают файл."""
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "proj"
            proj.mkdir()
            data = {"mcpServers": {"maind": {"command": "maind", "args": ["mcp"]}}}
            self.assertTrue(write_example(proj / ".mcp.json", data, proj))
            ex_path = proj / (".mcp.json" + EXAMPLE_SUFFIX)
            before = ex_path.stat().st_mtime_ns
            self.assertFalse(write_example(proj / ".mcp.json", data, proj))
            self.assertEqual(ex_path.stat().st_mtime_ns, before)   # не переписан
            self.assertFalse(write_example(proj / ".mcp.json", data, proj, dry=True))
            other = {"mcpServers": {"maind": {"command": "maind", "args": ["mcp", "--x"]}}}
            self.assertTrue(write_example(proj / ".mcp.json", other, proj, dry=True))
            self.assertTrue(write_example(proj / ".mcp.json", other, proj))
            self.assertEqual(json.loads(ex_path.read_text())["mcpServers"]["maind"]["args"],
                             ["mcp", "--x"])

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

    def test_check_hygiene_clean(self):
        """Нет реального файла → нет проблем; есть .example + не трекается → clean."""
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            self.assertEqual(check_hygiene(proj), [])
            (proj / ".mcp.json").write_text("{}", encoding="utf-8")
            (proj / ".mcp.json.example").write_text("{}", encoding="utf-8")
            self.assertEqual(check_hygiene(proj), [])  # не git-репо → tracked=False, example есть

    def test_check_hygiene_missing_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            (proj / ".mcp.json").write_text("{}", encoding="utf-8")
            issues = check_hygiene(proj)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["file"], ".mcp.json")
            self.assertIn("missing-example", issues[0]["problems"])
            self.assertNotIn("tracked-in-git", issues[0]["problems"])

    def test_check_hygiene_tracked_in_git(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            subprocess.run(["git", "-C", str(proj), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(proj), "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", str(proj), "config", "user.name", "t"], check=True)
            (proj / ".mcp.json").write_text("{}", encoding="utf-8")
            subprocess.run(["git", "-C", str(proj), "add", ".mcp.json"], check=True)
            subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "x"], check=True)
            issues = check_hygiene(proj)
            self.assertEqual(len(issues), 1)
            self.assertIn("tracked-in-git", issues[0]["problems"])
            self.assertIn("missing-example", issues[0]["problems"])


if __name__ == "__main__":
    unittest.main()
