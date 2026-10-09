#!/usr/bin/env python3
"""Root installers in this monorepo: umbrella flag forwarding and Skiller's host-driven argv.

The Skiller package tests its installer against a synthetic host; this root test pins
the monorepo values from configs/skiller-host.json. Fake `codex` and `grok` first in
PATH log their argv, so the machine CLIs and the real HOME are never touched.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLER_INSTALLER = ROOT / "packages/skiller/install.sh"
UMBRELLA_INSTALLER = ROOT / "install.sh"


class RootInstallCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.fake_bin = self.root / "fake-bin"
        self.install_bin = self.root / "install-bin"
        self.log = self.root / "codex.log"
        self.grok_log = self.root / "grok.log"
        self.home.mkdir()
        self.fake_bin.mkdir()
        for name, log in (("codex", "CODEX_STUB_LOG"), ("grok", "GROK_STUB_LOG")):
            stub = self.fake_bin / name
            stub.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"${log}\"\n",
                            encoding="utf-8")
            stub.chmod(0o755)

    def run_installer(self, installer, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in {"SKILLER_HOST_CONFIG", "SKILLER_MARKETPLACE_ROOT"}}
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
            "GROK_STUB_LOG": str(self.grok_log),
        })
        return subprocess.run(
            ["bash", str(installer), "--bin-dir", str(self.install_bin), *args],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False)

    def test_skiller_installer_uses_monorepo_host_plugins(self):
        result = self.run_installer(SKILLER_INSTALLER)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(encoding="utf-8").splitlines(), [
            f"plugin marketplace add {ROOT}",
            "plugin add core@swissknifeman",
            "plugin add planner@swissknifeman",
        ])
        self.assertEqual(self.grok_log.read_text(encoding="utf-8").splitlines(), [
            f"plugin marketplace add {ROOT}",
            f"plugin install {ROOT}/packages/planner --trust",
            f"plugin install {ROOT}/packages/planner/adapters/grok/prefix-hold --trust",
        ])
        self.assertIn("Codex plugins installed: core planner", result.stdout)
        self.assertIn("Grok plugins installed: planner prefix-hold", result.stdout)

    def test_umbrella_installer_forwards_plugin_opt_outs_only_to_skiller(self):
        result = self.run_installer(UMBRELLA_INSTALLER, "--no-codex-plugins", "--no-grok-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.grok_log.exists())
        self.assertIn("Codex plugins: pass (--no-codex-plugins)", result.stdout)
        self.assertIn("Grok plugins: pass (--no-grok-plugins)", result.stdout)


if __name__ == "__main__":
    unittest.main()
