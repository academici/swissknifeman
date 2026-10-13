#!/usr/bin/env python3
"""Tests of scripts/smoke-installed.sh: arguments, the sandbox refusal and the plugin-root checks on fixtures."""
import json
import os
import pwd
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "smoke-installed.sh"


class SmokeInstalledTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), SKM_HOME=str(self.home / ".swissknifeman-home"))

    def run_script(self, *args, env=None):
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=120,
                              env=self.env if env is None else env)

    def plugin(self, files, manifest=None):
        root = Path(self.tmp.name) / "plugin"
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        meta = root / ".claude-plugin"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "plugin.json").write_text(json.dumps(manifest or {"name": "fx"}),
                                          encoding="utf-8")
        return root

    def test_help_prints_usage_and_exits_two(self):
        result = self.run_script("--help")
        self.assertEqual(2, result.returncode)
        self.assertIn("smoke-installed.sh", result.stderr)

    def test_unknown_argument_exits_two(self):
        result = self.run_script("--bogus")
        self.assertEqual(2, result.returncode)
        self.assertIn("unknown argument", result.stderr)

    def test_refuses_without_skm_home(self):
        env = {k: v for k, v in self.env.items() if k != "SKM_HOME"}
        result = self.run_script(env=env)
        self.assertEqual(3, result.returncode)
        self.assertIn("SKM_HOME", result.stderr)

    def test_refuses_skm_home_outside_the_temporary_directory(self):
        env = dict(self.env, SKM_HOME=str(Path.home() / ".swissknifeman-home-not-used"))
        result = self.run_script(env=env)
        self.assertEqual(3, result.returncode)

    def test_refuses_the_real_home(self):
        real = pwd.getpwuid(os.getuid()).pw_dir
        result = self.run_script(env=dict(self.env, HOME=real))
        self.assertEqual(3, result.returncode)
        self.assertIn("real HOME", result.stderr)

    def test_clean_plugin_passes(self):
        root = self.plugin({"commands/a.md": "run ${CLAUDE_PLUGIN_ROOT}/bin/tool\n", "bin/tool": "#!/bin/sh\n"})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_reference_leaving_the_root_fails(self):
        root = self.plugin({"commands/a.md": "run ${CLAUDE_PLUGIN_ROOT}/../aicore/bin/x\n"})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(1, result.returncode)
        self.assertIn("FAIL fx: commands/a.md reference leaves the plugin root", result.stdout)

    def test_missing_referenced_path_fails(self):
        root = self.plugin({"commands/a.md": "run ${CLAUDE_PLUGIN_ROOT}/bin/absent\n"})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(1, result.returncode)
        self.assertIn("references a missing path", result.stdout)

    def test_manifest_path_outside_the_root_fails(self):
        root = self.plugin({"commands/a.md": "x\n"}, manifest={"name": "fx", "skills": ["./../skills"]})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(1, result.returncode)
        self.assertIn("leaves the plugin root", result.stdout)

    def test_hook_with_a_missing_script_fails_and_a_present_one_passes(self):
        hooks = {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
                                                       "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run.sh"}]}]}}
        bad = self.plugin({"hooks/hooks.json": json.dumps(hooks)})
        result = self.run_script("--check-plugin", str(bad), "--name", "fx")
        self.assertEqual(1, result.returncode)
        self.assertIn("references a missing path", result.stdout)
        script = bad / "hooks" / "run.sh"
        script.write_text("#!/usr/bin/env bash\ncat >/dev/null\n", encoding="utf-8")
        script.chmod(0o755)
        result = self.run_script("--check-plugin", str(bad), "--name", "fx")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_bin_script_climbing_out_of_the_root_fails(self):
        root = self.plugin({"bin/tool": '#!/bin/sh\nROOT="$(cd "$(dirname "$0")" && pwd)"\ncd "$ROOT/../.."\n'})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("bin/tool:3 leaves the plugin root", result.stdout)

    def test_escape_inside_the_locator_markers_passes(self):
        body = ('#!/bin/sh\nR="$(cd "$(dirname "$0")/.." && pwd)"\n# --- aicore locator ---\n'
                'if [ -d "$R/../aicore" ]; then X="$R/../aicore"; fi\n# --- end aicore locator ---\n')
        root = self.plugin({"bin/tool": body})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_installer_climb_is_only_a_warning(self):
        root = self.plugin({"install.sh": 'R=.\nC="$(cd "$R/../.." && pwd)"\n'})
        result = self.run_script("--check-plugin", str(root), "--name", "fx")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("WARN fx: install.sh:2", result.stdout)


if __name__ == "__main__":
    unittest.main()
