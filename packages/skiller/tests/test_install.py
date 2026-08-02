"""Регрессии машинной установки базовых Codex-плагинов."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = PACKAGE_ROOT.parents[1]
INSTALLER = PACKAGE_ROOT / "install.sh"


class InstallScriptCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.fake_bin = self.root / "fake-bin"
        self.install_bin = self.root / "install-bin"
        self.log = self.root / "codex.log"
        self.home.mkdir()
        self.fake_bin.mkdir()

        codex = self.fake_bin / "codex"
        codex.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$CODEX_STUB_LOG\"\n",
            encoding="utf-8",
        )
        codex.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *args):
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
        })
        return subprocess.run(
            ["bash", str(INSTALLER), "--bin-dir", str(self.install_bin), *args],
            cwd=MONOREPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_install_adds_core_and_task_codex_plugins(self):
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.log.read_text(encoding="utf-8").splitlines(),
            [
                f"plugin marketplace add {MONOREPO_ROOT}",
                "plugin add core@swissknifeman",
                "plugin add task@swissknifeman",
            ],
        )
        self.assertIn("Codex plugins installed: core task", result.stdout)

    def test_no_codex_plugins_is_an_explicit_opt_out(self):
        result = self.run_installer("--no-codex-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertIn("Codex plugins: пропуск (--no-codex-plugins)", result.stdout)

    def test_explicit_codex_plugin_survives_default_opt_out(self):
        result = self.run_installer(
            "--no-codex-plugins", "--codex-plugin", "ai")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.log.read_text(encoding="utf-8").splitlines(),
            [
                f"plugin marketplace add {MONOREPO_ROOT}",
                "plugin add ai@swissknifeman",
            ],
        )
        self.assertIn("Codex plugins installed: ai", result.stdout)

    def test_umbrella_installer_forwards_codex_opt_out_only_to_skiller(self):
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
        })
        result = subprocess.run(
            ["bash", str(MONOREPO_ROOT / "install.sh"),
             "--bin-dir", str(self.install_bin), "--no-codex-plugins"],
            cwd=MONOREPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertIn("Codex plugins: пропуск (--no-codex-plugins)", result.stdout)


if __name__ == "__main__":
    unittest.main()
