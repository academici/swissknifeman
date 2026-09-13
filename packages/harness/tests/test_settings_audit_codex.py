"""Internal documentation."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import (
    _load_codex_toml_layer,
    codex_check_1_layers_readable, codex_check_2_project_overrides_machine_local_key,
    codex_check_3_hooks_feature_disabled, counts, exit_code, load_codex_layers,
    render_codex_text, run_codex_checks,
)


@unittest.skipIf(sys.version_info < (3, 11), "Codex TOML parsing requires stdlib tomllib (Python 3.11+)")
class CodexSettingsAuditCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.target = self.tmp / "proj"
        self.home.mkdir()
        self.target.mkdir()
        self.env = Env(self.tmp, "test", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_project_toml(self, text):
        cfg = self.target / ".codex"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(text, encoding="utf-8")


    def test_no_layers_present_is_clean(self):
        layers = load_codex_layers(self.env, self.target)
        self.assertEqual(run_codex_checks(layers), [])
        self.assertEqual(exit_code(run_codex_checks(layers)), 0)


    def test_project_layer_is_read(self):
        self._write_project_toml('trust_level = "trusted"\n')
        layers = load_codex_layers(self.env, self.target)
        project = next(l for l in layers if l.name == "project")
        self.assertEqual(project.data, {"trust_level": "trusted"})
        self.assertIsNone(project.error)


    def test_malformed_toml_is_reported_not_raised(self):
        self._write_project_toml("this is not = valid [[[ toml")
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_1_layers_readable(layers)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "warn")
        self.assertEqual(next(layer for layer in layers if layer.name == "project").error_kind,
                         "malformed")
        self.assertIn("не распарсен", findings[0].title)


    def test_unreadable_toml_is_distinct_from_malformed(self):
        path = self.target / ".codex" / "config.toml"
        path.parent.mkdir()
        path.write_text('trust_level = "trusted"\n', encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            layer = _load_codex_toml_layer("project", path)
        self.assertEqual(layer.error_kind, "unreadable")
        findings = codex_check_1_layers_readable([layer])
        self.assertEqual(len(findings), 1)
        self.assertIn("не читается", findings[0].title)


    def test_project_override_of_notify_is_error(self):
        self._write_project_toml('notify = "custom-notify"\n')
        layers = load_codex_layers(self.env, self.target)
        findings = run_codex_checks(layers)
        errors = [f for f in findings if f.level == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("notify", errors[0].detail)


    def test_project_layer_with_legal_key_is_clean(self):
        self._write_project_toml('trust_level = "trusted"\n[features]\nhooks = true\n')
        layers = load_codex_layers(self.env, self.target)
        self.assertEqual(codex_check_2_project_overrides_machine_local_key(layers), [])


    def test_hooks_feature_disabled_is_info(self):
        self._write_project_toml("[features]\nhooks = false\n")
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_3_hooks_feature_disabled(layers)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "info")


    def test_user_layer_merges_with_project(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text("[features]\nhooks = false\n",
                                                           encoding="utf-8")
        self._write_project_toml('trust_level = "trusted"\n')
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_3_hooks_feature_disabled(layers)
        self.assertEqual(len(findings), 1)


    def test_render_and_counts_share_claude_side_contract(self):
        self._write_project_toml('notify = "x"\n')
        layers = load_codex_layers(self.env, self.target)
        findings = run_codex_checks(layers)
        text = render_codex_text(self.target, findings)
        self.assertIn("--provider codex", text)
        self.assertEqual(counts(findings)["error"], 1)
        self.assertEqual(exit_code(findings), 2)


if __name__ == "__main__":
    unittest.main()
