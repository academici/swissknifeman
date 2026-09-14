"""Project selection is explicit, lossless and independent of native cache install."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
try:
    import tomllib
except ImportError:
    tomllib = None
from types import SimpleNamespace
import unittest
from unittest import mock

from skiller.native_codex import (_fallback_toml_loads, apply_selection, native_inventory,
                                  plan_selection)


class NativeCodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.env = SimpleNamespace(home=self.root / "home")
        self.codex = self.env.home / ".codex"
        self.codex.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"CODEX_HOME": str(self.codex)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_python_310_fallback_reads_plugin_and_legacy_skill_selection(self):
        data = _fallback_toml_loads(
            '[plugins."quality@swissknifeman"]\n'
            'enabled = true\n\n'
            '[[skills.config]]\n'
            'path = "/tmp/skill/SKILL.md"\n'
            'enabled = false\n')
        self.assertTrue(data["plugins"]["quality@swissknifeman"]["enabled"])
        self.assertEqual(data["skills"]["config"], [{"path": "/tmp/skill/SKILL.md", "enabled": False}])

    def test_python_310_fallback_rejects_invalid_or_inline_plugin_layout(self):
        for text in ("[broken", 'plugins = { "php@swissknifeman" = {enabled = true} }\n'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    _fallback_toml_loads(text)

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_selection_preserves_foreign_bytes_and_user_defaults(self):
        user = '[plugins."system@swissknifeman"]\nenabled = true\n'
        (self.codex / "config.toml").write_text(user)
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        before = ('# author\nmodel = "test"\n\n[plugins."php@swissknifeman"] # comment\n'
                  'enabled = false # keep\ncustom = "x"\n\n[plugins."foreign@other"]\nenabled = true\n')
        config.write_text(before)
        plan = plan_selection(self.env, self.project, {"php"}, {"php", "quality"})
        apply_selection(self.project, plan, dry_run=True)
        self.assertEqual(config.read_text(), before)
        self.assertFalse(config.with_suffix(".toml.bak").exists())
        apply_selection(self.project, plan)
        after = config.read_text()
        self.assertIn('enabled = true # keep\ncustom = "x"', after)
        self.assertIn('[plugins."foreign@other"]\nenabled = true\n', after)
        parsed = tomllib.loads(after)
        self.assertFalse(parsed["plugins"]["system@swissknifeman"]["enabled"])
        self.assertFalse(parsed["plugins"]["quality@swissknifeman"]["enabled"])
        self.assertEqual((self.codex / "config.toml").read_text(), user)
        backups = list(config.parent.glob("config.toml.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), before)
        repeat = plan_selection(self.env, self.project, {"php"}, {"php", "quality"})
        self.assertFalse(apply_selection(self.project, repeat))
        self.assertEqual(list(config.parent.glob("config.toml.*.bak")), backups)
        self.assertEqual(backups[0].read_text(), before)

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_existing_backup_survives_multiple_selection_changes(self):
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text('model = "local"\n')
        foreign = config.with_suffix(".toml.bak")
        foreign.write_text("owner's existing backup\n")
        preimages = []
        for selected in ({"php"}, set()):
            preimages.append(config.read_bytes())
            apply_selection(self.project, plan_selection(self.env, self.project, selected, {"php"}))
        self.assertEqual(foreign.read_text(), "owner's existing backup\n")
        self.assertCountEqual([p.read_bytes() for p in config.parent.glob("config.toml.*.bak")], preimages)

    def test_invalid_or_inline_layout_fails_without_writes(self):
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        for before in ('[broken', 'plugins = { "php@swissknifeman" = {enabled = true} }\n'):
            with self.subTest(before=before):
                config.write_text(before)
                with self.assertRaises(ValueError):
                    plan_selection(self.env, self.project, {"php"}, {"php"})
                self.assertEqual(config.read_text(), before)
                self.assertFalse(config.with_suffix(".toml.bak").exists())

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_preserves_crlf_and_foreign_multiline_string_bytes(self):
        config = self.project / ".codex/config.toml"
        config.parent.mkdir()
        before = (b'# local\r\nnotes = """\r\n[plugins."php@swissknifeman"]\r\n'
                  b'enabled = true\r\n"""\r\n[plugins."php@swissknifeman"]\r\nenabled = true # own\r\n')
        config.write_bytes(before)
        plan = plan_selection(self.env, self.project, set(), {"php"})
        apply_selection(self.project, plan)
        self.assertEqual(config.read_bytes(), before.replace(b'true # own', b'false # own'))

    @unittest.skipUnless(tomllib, "native activation requires stdlib tomllib (Python 3.11+)")
    def test_changed_preimage_and_symlink_are_rejected(self):
        plan = plan_selection(self.env, self.project, {"php"}, {"php"})
        config = plan["path"]
        config.parent.mkdir()
        config.write_text('model = "concurrent"\n')
        with self.assertRaisesRegex(ValueError, "PREIMAGE_CHANGED"):
            apply_selection(self.project, plan)
        config.unlink()
        config.symlink_to(self.codex / "config.toml")
        with self.assertRaises(ValueError):
            plan_selection(self.env, self.project, {"php"}, {"php"})

    def test_discovery_distinguishes_native_cache_from_local_duplicates(self):
        cache = self.codex / "plugins/cache/swissknifeman/php/0.4.0"
        text = ('<skills_instructions>\n- `r0` = `' + str(cache) + '`\n'
                '- php:code-style: Style (file: r0/code-style/SKILL.md)\n'
                '- local-rule: Local (file: ' + str(self.project / '.agents/skills/local-rule/SKILL.md') + ')\n'
                '</skills_instructions>')
        responses = [subprocess.CompletedProcess([], 0, json.dumps({"installed": [
            {"name": "php", "enabled": True, "marketplaceName": "swissknifeman"}]}), ""),
            subprocess.CompletedProcess([], 0, json.dumps([{"content": [{"text": text}]}]), "")]
        runner = mock.Mock(side_effect=responses)
        result = native_inventory(self.env, self.project, runner=runner)
        self.assertTrue(result["ok"])
        self.assertEqual(result["names"], {"code-style", "local-rule"})
        self.assertEqual(result["native_names"], {"code-style"})
        self.assertEqual(result["enabled"], ["php"])
        self.assertEqual(runner.call_args.kwargs["cwd"], str(self.project))
        self.assertEqual(result["paths"]["code-style"], [str(cache / "code-style/SKILL.md")])

    def test_discovery_failure_never_confirms_skills(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 1, "", "offline failure"))
        result = native_inventory(self.env, self.project, runner=runner)
        self.assertFalse(result["ok"])
        self.assertEqual(result["names"], set())
        self.assertTrue(result["notes"])
