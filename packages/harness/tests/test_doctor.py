"""Provider-qualified public settings doctor coverage for P6.2."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.settings_audit import _load_layer, _load_codex_toml_layer, check_1_layer_json_valid, Context


PACKAGE = Path(__file__).resolve().parents[1]
HARNESS = PACKAGE / "bin" / "harness"


class ProviderSettingsDoctorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "project"
        self.home.mkdir()
        self.target.mkdir()
        self.env = dict(os.environ, HOME=str(self.home))

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        return subprocess.run(
            [str(HARNESS), "doctor", "--settings", "--target", str(self.target), *args],
            cwd=PACKAGE, env=self.env, text=True, capture_output=True, check=False,
        )

    def test_provider_readers_are_independent(self):
        claude = self.target / ".claude" / "settings.json"
        claude.parent.mkdir()
        claude.write_text("{broken json", encoding="utf-8")
        codex = self.target / ".codex" / "config.toml"
        codex.parent.mkdir()
        codex.write_text('trust_level = "trusted"\n', encoding="utf-8")

        codex_result = self._run("--provider", "codex", "--json")
        if sys.version_info < (3, 11):
            self.assertEqual(codex_result.returncode, 1, codex_result.stderr)
            self.assertEqual(json.loads(codex_result.stdout)["status"], "warning")
            layer = _load_codex_toml_layer("project", codex)
            self.assertEqual(layer.error_kind, "unreadable")
            self.assertIn("tomllib", layer.error)
        else:
            self.assertEqual(codex_result.returncode, 0, codex_result.stderr)
            self.assertEqual(json.loads(codex_result.stdout)["status"], "clean")

        claude_result = self._run("--provider", "claude-code", "--json")
        self.assertEqual(claude_result.returncode, 2, claude_result.stderr)
        report = json.loads(claude_result.stdout)
        self.assertEqual(report["provider"], "claude-code")
        self.assertEqual(report["status"], "error")

    def test_codex_malformed_layer_is_public_warning(self):
        config = self.target / ".codex" / "config.toml"
        config.parent.mkdir()
        config.write_text("broken = [[[", encoding="utf-8")
        result = self._run("--provider", "codex", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            list(report),
            ["provider", "target", "profile", "status", "counts", "findings", "exit"],
        )
        self.assertEqual(report["provider"], "codex")
        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["exit"], 1)
        self.assertEqual(report["findings"][0]["id"], 1)

    def test_cursor_provider_has_provider_qualified_json_shape(self):
        result = self._run("--provider", "cursor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            list(report),
            ["provider", "target", "profile", "status", "counts", "findings", "exit"],
        )
        self.assertEqual(report["provider"], "cursor")
        self.assertEqual(report["status"], "clean")

    def test_legacy_no_provider_json_shape_is_unchanged(self):
        result = self._run("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(list(report), ["target", "profile", "counts", "findings", "exit"])
        self.assertNotIn("provider", report)
        self.assertNotIn("status", report)

    def test_claude_unreadable_layer_has_access_diagnostic(self):
        path = self.target / ".claude" / "settings.json"
        path.parent.mkdir()
        path.write_text("{}", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            layer = _load_layer("project", path)
        context = Context(layers=[layer], values={}, provenance={}, target=self.target, env=None)
        findings = check_1_layer_json_valid(context)
        self.assertEqual(layer.error_kind, "unreadable")
        self.assertEqual(findings[0].level, "error")
        self.assertIn("не читается", findings[0].title)


if __name__ == "__main__":
    unittest.main()
