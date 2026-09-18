"""Tests for cross-provider MCP parity helpers."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from maind.mcp_parity import (analyze, collect_surfaces, parity_drifts,
                              repair_settings_duplicates, settings_duplicates)


class TestMcpParity(unittest.TestCase):
    def test_parity_drifts_detects_codex_subset(self):
        surfaces = {
            "claude": {"maind", "codegraph", "figma"},
            "cursor": {"maind", "codegraph", "figma"},
            "codex": {"maind", "codegraph"},
            "settings": set(),
        }
        drifts = parity_drifts(surfaces)
        self.assertTrue(any(d["only_left"] == ["figma"] for d in drifts))

    def test_settings_duplicates(self):
        surfaces = {
            "claude": {"maind", "laravel-boost"},
            "cursor": {"maind", "laravel-boost"},
            "codex": {"maind"},
            "settings": {"laravel-boost"},
        }
        self.assertEqual(settings_duplicates(surfaces), ["laravel-boost"])

    def test_repair_settings_duplicates_removes_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(json.dumps({
                "mcpServers": {"maind": {"command": "maind"},
                               "laravel-boost": {"command": "php"}}}), encoding="utf-8")
            claude = root / ".claude"
            claude.mkdir()
            (claude / "settings.json").write_text(json.dumps({
                "mcpServers": {"laravel-boost": {"command": "php"},
                               "custom": {"command": "echo"}}}), encoding="utf-8")
            removed = repair_settings_duplicates(root)
            self.assertEqual(removed, ["settings.json:laravel-boost"])
            data = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(set(data["mcpServers"]), {"custom"})

    def test_analyze_marks_undeclared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(json.dumps({
                "mcpServers": {"maind": {}, "figma": {}}}), encoding="utf-8")
            report = analyze(root, expected_ids=["maind"])
            self.assertEqual(report["undeclared"], ["figma"])
            self.assertEqual(collect_surfaces(root)["claude"], {"maind", "figma"})
