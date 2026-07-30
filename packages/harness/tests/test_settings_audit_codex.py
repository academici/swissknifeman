"""Codex settings audit — bounded closure (P2.4, codex-parity-verdicts-v1.md §3.11).

Отдельный, МЕНЬШИЙ набор проверок над документированными слоями Codex
(~/.codex/config.toml -> .codex/config.toml -> profile). Реальные tmpdir-деревья,
никаких моков ФС — то же правило, что у test_settings_audit.py."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import (
    codex_check_1_layers_readable, codex_check_2_project_overrides_machine_local_key,
    codex_check_3_hooks_feature_disabled, counts, exit_code, load_codex_layers,
    render_codex_text, run_codex_checks,
)


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

    # (a) отсутствующие слои — норма, ни одной находки.
    def test_no_layers_present_is_clean(self):
        layers = load_codex_layers(self.env, self.target)
        self.assertEqual(run_codex_checks(layers), [])
        self.assertEqual(exit_code(run_codex_checks(layers)), 0)

    # (b) проектный слой читается и парсится корректно.
    def test_project_layer_is_read(self):
        self._write_project_toml('trust_level = "trusted"\n')
        layers = load_codex_layers(self.env, self.target)
        project = next(l for l in layers if l.name == "project")
        self.assertEqual(project.data, {"trust_level": "trusted"})
        self.assertIsNone(project.error)

    # (c) битый TOML — Finding (fail-soft), не исключение.
    def test_malformed_toml_is_reported_not_raised(self):
        self._write_project_toml("this is not = valid [[[ toml")
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_1_layers_readable(layers)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "warn")

    # (d) Ф10: проектный слой не вправе переопределять machine-local ключи.
    def test_project_override_of_notify_is_error(self):
        self._write_project_toml('notify = "custom-notify"\n')
        layers = load_codex_layers(self.env, self.target)
        findings = run_codex_checks(layers)
        errors = [f for f in findings if f.level == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("notify", errors[0].detail)

    # (e) легальный проектный ключ (не в списке machine-local) — без находки.
    def test_project_layer_with_legal_key_is_clean(self):
        self._write_project_toml('trust_level = "trusted"\n[features]\nhooks = true\n')
        layers = load_codex_layers(self.env, self.target)
        self.assertEqual(codex_check_2_project_overrides_machine_local_key(layers), [])

    # (f) features.hooks=false — info, не error/warn.
    def test_hooks_feature_disabled_is_info(self):
        self._write_project_toml("[features]\nhooks = false\n")
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_3_hooks_feature_disabled(layers)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "info")

    # (g) user-слой сливается с project (эффективная конфигурация), так же, как Claude-сторона.
    def test_user_layer_merges_with_project(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text("[features]\nhooks = false\n",
                                                           encoding="utf-8")
        self._write_project_toml('trust_level = "trusted"\n')
        layers = load_codex_layers(self.env, self.target)
        findings = codex_check_3_hooks_feature_disabled(layers)
        self.assertEqual(len(findings), 1)

    # (h) render/counts/exit_code — общий контракт с Claude-стороной.
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
