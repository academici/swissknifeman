"""Basic machine installation regressions Codex-plugins."""

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
        self.grok_log = self.root / "grok.log"
        self.home.mkdir()
        self.fake_bin.mkdir()

        codex = self.fake_bin / "codex"
        codex.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$CODEX_STUB_LOG\"\n",
            encoding="utf-8",
        )
        codex.chmod(0o755)

        # PATH is fake_bin then the real PATH. Without this stub, install.sh
        # calls the machine grok CLI and mutates ~/.grok.
        grok = self.fake_bin / "grok"
        grok.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$GROK_STUB_LOG\"\n"
            "if [[ \"${GROK_STUB_FAIL:-}\" == 1 ]]; then\n"
            "  if [[ \"$*\" == plugin\\ marketplace\\ add* ]]; then\n"
            "    echo \"Error: Marketplace source already configured: dummy\" >&2\n"
            "  else\n"
            "    echo \"Error: repo 'task-199de6ad' already installed\" >&2\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        grok.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *args):
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
            "GROK_STUB_LOG": str(self.grok_log),
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
        self.assertEqual(
            self.grok_log.read_text(encoding="utf-8").splitlines(),
            [
                f"plugin marketplace add {MONOREPO_ROOT}",
                f"plugin install {MONOREPO_ROOT}/packages/task --trust",
                f"plugin install {MONOREPO_ROOT}/packages/task/adapters/grok/prefix-hold --trust",
            ],
        )
        self.assertIn("Grok plugins installed: task prefix-hold", result.stdout)
        self.assertNotIn("plugin install " + str(MONOREPO_ROOT) + " --trust", result.stdout)

    def test_repeat_grok_install_treats_already_present_as_success(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        env_fail = os.environ.copy()
        env_fail.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env_fail['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
            "GROK_STUB_LOG": str(self.grok_log),
            "GROK_STUB_FAIL": "1",
        })
        self.grok_log.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(INSTALLER), "--bin-dir", str(self.install_bin),
             "--no-codex-plugins"],
            cwd=MONOREPO_ROOT,
            env=env_fail,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Grok plugins installed: task prefix-hold", result.stdout)
        self.assertNotIn("ERROR: grok", result.stderr)

    def test_no_grok_plugins_is_an_explicit_opt_out(self):
        result = self.run_installer("--no-grok-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.grok_log.exists())
        self.assertIn("Grok plugins: pass (--no-grok-plugins)", result.stdout)
        self.assertIn("Codex plugins installed: core task", result.stdout)

    def test_no_codex_plugins_is_an_explicit_opt_out(self):
        result = self.run_installer("--no-codex-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertIn("Codex plugins: pass (--no-codex-plugins)", result.stdout)
        self.assertIn("Grok plugins installed: task prefix-hold", result.stdout)

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

    def test_umbrella_installer_forwards_plugin_opt_outs_only_to_skiller(self):
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "CODEX_STUB_LOG": str(self.log),
            "GROK_STUB_LOG": str(self.grok_log),
        })
        result = subprocess.run(
            ["bash", str(MONOREPO_ROOT / "install.sh"),
             "--bin-dir", str(self.install_bin),
             "--no-codex-plugins", "--no-grok-plugins"],
            cwd=MONOREPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.grok_log.exists())
        self.assertIn("Codex plugins: pass (--no-codex-plugins)", result.stdout)
        self.assertIn("Grok plugins: pass (--no-grok-plugins)", result.stdout)


if __name__ == "__main__":
    unittest.main()
