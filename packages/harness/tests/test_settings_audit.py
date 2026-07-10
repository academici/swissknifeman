"""Ядро settings-doctor: слои настроек CC и эффективная конфигурация (P1.1).

Реальные tmpdir-деревья `.claude/settings*.json` — никаких моков ФС и никаких
готовых `values`-словарей, подсунутых напрямую (анти-самообман: ядро обязано САМО
прочитать слои)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import effective_config, load_layers


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class SettingsAuditCoreCase(unittest.TestCase):
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

    # (а) скаляр из local перекрывает user
    def test_scalar_local_overrides_user(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"defaultMode": "bypassPermissions"}})
        layers = load_layers(self.env, self.target)
        values, provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["defaultMode"], "bypassPermissions")
        self.assertEqual(provenance["permissions"]["defaultMode"], "local")

    # (б) permissions.allow из user+project+local — union с дедупом
    def test_permissions_allow_union_with_dedup(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(ls *)"]}})
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(git status)", "Bash(ls *)"]}})
        _write(self.target / ".claude" / "settings.local.json",
               {"permissions": {"allow": ["Read(**)"]}})
        layers = load_layers(self.env, self.target)
        values, _provenance = effective_config(layers)
        self.assertEqual(
            values["permissions"]["allow"],
            ["Bash(ls *)", "Bash(git status)", "Read(**)"])

    # (в) битый settings.local.json не ломает merge остальных слоёв, даёт Layer.error
    def test_broken_local_layer_reported_not_fatal(self):
        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"allow": ["Bash(ls *)"]}})
        local = self.target / ".claude" / "settings.local.json"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text("{не json", encoding="utf-8")
        layers = load_layers(self.env, self.target)
        local_layer = next(l for l in layers if l.name == "local")
        self.assertIsNone(local_layer.data)
        self.assertIsNotNone(local_layer.error)
        # остальные слои по-прежнему сливаются
        values, _provenance = effective_config(layers)
        self.assertEqual(values["permissions"]["allow"], ["Bash(ls *)"])

    # (г) env — пер-ключевой override
    def test_env_per_key_override(self):
        _write(self.home / ".claude" / "settings.json",
               {"env": {"FOO": "user-foo", "BAR": "user-bar"}})
        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"FOO": "local-foo"}})
        layers = load_layers(self.env, self.target)
        values, provenance = effective_config(layers)
        self.assertEqual(values["env"], {"FOO": "local-foo", "BAR": "user-bar"})
        self.assertEqual(provenance["env"]["FOO"], "local")
        self.assertEqual(provenance["env"]["BAR"], "user")

    # (д) hooks мержатся по событию с дедупом
    def test_hooks_merge_by_event_with_dedup(self):
        _write(self.home / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]}]}})
        _write(self.target / ".claude" / "settings.json", {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "a.sh"}]},
            {"matcher": "Read", "hooks": [{"type": "command", "command": "b.sh"}]}]}})
        layers = load_layers(self.env, self.target)
        values, _provenance = effective_config(layers)
        entries = values["hooks"]["PreToolUse"]
        self.assertEqual(len(entries), 2)  # дубль (Bash, a.sh) не размножился
        pairs = {(e["matcher"], e["command"]) for e in entries}
        self.assertEqual(pairs, {("Bash", "a.sh"), ("Read", "b.sh")})

    # (е) провенанс правила указывает верный слой
    def test_provenance_points_to_correct_layer(self):
        _write(self.target / ".claude" / "settings.json",
               {"permissions": {"deny": ["Bash(sudo *)"]}})
        layers = load_layers(self.env, self.target)
        _values, provenance = effective_config(layers)
        rules = dict(provenance["permissions"]["deny"])
        self.assertEqual(rules["Bash(sudo *)"], "project")

    # --- дополнительно: отсутствующие слои — норма, без ошибок ---------------
    def test_absent_layers_are_normal_no_errors(self):
        layers = load_layers(self.env, self.target)
        for layer in layers:
            if layer.name != "managed":
                self.assertIsNone(layer.data)
                self.assertIsNone(layer.error)
        values, provenance = effective_config(layers)
        self.assertEqual(values, {})
        self.assertEqual(provenance, {})


if __name__ == "__main__":
    unittest.main()
