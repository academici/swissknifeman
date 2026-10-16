"""Basic machine installation regressions: Codex and Grok plugins come from the host config.

The installer runs from a copy of this package nested in a synthetic host repository,
so host discovery (Git root -> configs/skiller-host.json) is the real one. Fake `codex`
and `grok` binaries first in PATH log their argv; the machine CLIs are never touched.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
# scripts/test.sh exports the located foundation; the installer copy in the synthetic host has no sibling.
AICORE_ROOT = Path(os.environ.get("AICORE_ROOT") or PACKAGE_ROOT.parent / "aicore")
HOST_CONFIG = {
    "schema_version": 1,
    "default_command_plugins": ["plugin-a"],
    "machine_plugins": {"grok": [{"name": "plugin-a", "path": "vendor/plugin-a",
                                  "holds": ["vendor/plugin-a/adapters/grok/hold"]}]},
}


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


class InstallScriptCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_class = tempfile.TemporaryDirectory()
        cls.host = Path(cls.temp_class.name) / "host"
        package = cls.host / "vendor" / "skiller"
        ignore = shutil.ignore_patterns("__pycache__")
        for folder in ("bin", "lib", "configs"):
            shutil.copytree(PACKAGE_ROOT / folder, package / folder, ignore=ignore)
        shutil.copy2(PACKAGE_ROOT / "install.sh", package / "install.sh")
        cls.installer = package / "install.sh"
        subprocess.run(["git", "init", "-q", str(cls.host)], check=True)
        _write(cls.host / ".agents/plugins/marketplace.json", {"name": "swissknifeman", "plugins": []})
        _write(cls.host / "vendor/plugin-a/.claude-plugin/plugin.json", {"name": "plugin-a"})
        _write(cls.host / "vendor/plugin-a/adapters/grok/hold/.grok-plugin/plugin.json", {"name": "hold"})
        cls.set_host(HOST_CONFIG)

    @classmethod
    def tearDownClass(cls):
        cls.temp_class.cleanup()

    @classmethod
    def set_host(cls, config):
        _write(cls.host / "configs/skiller-host.json", config)

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
        self.addCleanup(self.set_host, HOST_CONFIG)

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
            "    echo \"Error: repo 'plugin-a-199de6ad' already installed\" >&2\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        grok.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_installer(self, *args, stdin=None, timeout=None, **extra_env):
        env = {k: v for k, v in os.environ.items()
               if k not in {"SKILLER_HOST_CONFIG", "SKILLER_MARKETPLACE_ROOT"}}
        env.update({
            "HOME": str(self.home),
            "PATH": f"{self.fake_bin}:{env['PATH']}",
            "AICORE_ROOT": str(AICORE_ROOT),
            "CODEX_STUB_LOG": str(self.log),
            "GROK_STUB_LOG": str(self.grok_log),
            **extra_env,
        })
        return subprocess.run(
            ["bash", str(self.installer), "--bin-dir", str(self.install_bin), *args],
            cwd=self.host,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            stdin=stdin,
            timeout=timeout,
        )

    def lines(self, path):
        return path.read_text(encoding="utf-8").splitlines()

    def test_force_on_a_terminal_does_not_wait_for_the_topology_question(self):
        import pty
        master, slave = pty.openpty()  # a terminal on stdin, no answer will ever come
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        result = self.run_installer("--force", stdin=slave, timeout=120)  # a prompt would end in TimeoutExpired
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("skiller topology init", result.stdout + result.stderr)

    def test_install_does_not_seed_the_legacy_registry(self):
        import sys
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / ".swissknifeman" / "projects.json").exists())

        sys.path.insert(0, str(PACKAGE_ROOT / "lib"))
        try:
            from skiller.common import Env
            from skiller.state import save_db
            env = Env(root=PACKAGE_ROOT, home=self.home)
            save_db(env, {"version": 1, "projects": []})
            self.assertEqual(env.db_file, env.state_dir / "projects.json")
            self.assertTrue((env.state_dir / "projects.json").exists())
            self.assertFalse((self.home / ".swissknifeman" / "projects.json").exists())
        finally:
            sys.path.remove(str(PACKAGE_ROOT / "lib"))

    def test_default_install_adds_core_and_host_command_plugins(self):
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines(self.log), [
            f"plugin marketplace add {self.host}",
            "plugin add core@swissknifeman",
            "plugin add plugin-a@swissknifeman",
        ])
        self.assertIn("Codex plugins installed: core plugin-a", result.stdout)
        self.assertEqual(self.lines(self.grok_log), [
            f"plugin marketplace add {self.host}",
            f"plugin install {self.host}/vendor/plugin-a --trust",
            f"plugin install {self.host}/vendor/plugin-a/adapters/grok/hold --trust",
        ])
        self.assertIn("Grok plugins installed: plugin-a hold", result.stdout)
        self.assertNotIn("plugin install " + str(self.host) + " --trust", result.stdout)

    def test_repeat_grok_install_treats_already_present_as_success(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.grok_log.write_text("", encoding="utf-8")
        result = self.run_installer("--no-codex-plugins", GROK_STUB_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Grok plugins installed: plugin-a hold", result.stdout)
        self.assertNotIn("ERROR: grok", result.stderr)

    def test_no_grok_plugins_is_an_explicit_opt_out(self):
        result = self.run_installer("--no-grok-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.grok_log.exists())
        self.assertIn("Grok plugins: pass (--no-grok-plugins)", result.stdout)
        self.assertIn("Codex plugins installed: core plugin-a", result.stdout)

    def test_no_codex_plugins_is_an_explicit_opt_out(self):
        result = self.run_installer("--no-codex-plugins")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertIn("Codex plugins: pass (--no-codex-plugins)", result.stdout)
        self.assertIn("Grok plugins installed: plugin-a hold", result.stdout)

    def test_explicit_codex_plugin_survives_default_opt_out(self):
        result = self.run_installer(
            "--no-codex-plugins", "--codex-plugin", "ai")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines(self.log), [
            f"plugin marketplace add {self.host}",
            "plugin add ai@swissknifeman",
        ])
        self.assertIn("Codex plugins installed: ai", result.stdout)

    def test_marketplace_root_override_serves_codex_and_grok(self):
        market = self.root / "market"
        _write(market / ".agents/plugins/marketplace.json", {"plugins": []})
        result = self.run_installer(SKILLER_MARKETPLACE_ROOT=str(market))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines(self.log)[0], f"plugin marketplace add {market}")
        self.assertEqual(self.lines(self.grok_log)[0], f"plugin marketplace add {market}")
        # Plugin paths stay relative to the host root.
        self.assertEqual(self.lines(self.grok_log)[1],
                         f"plugin install {self.host}/vendor/plugin-a --trust")

    def test_empty_host_installs_core_only_and_no_grok_plugin(self):
        self.set_host({"schema_version": 1})
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lines(self.log), [
            f"plugin marketplace add {self.host}",
            "plugin add core@swissknifeman",
        ])
        self.assertFalse(self.grok_log.exists())
        self.assertIn("INFO: no host grok plugins", result.stdout)

    def test_missing_grok_plugin_fails_before_any_grok_call(self):
        self.set_host({"schema_version": 1, "machine_plugins": {"grok": [
            {"name": "plugin-z", "path": "vendor/plugin-z"}]}})
        result = self.run_installer("--no-codex-plugins")

        self.assertEqual(result.returncode, 1)
        self.assertIn(f"ERROR: Grok plugin plugin-z not found: {self.host}/vendor/plugin-z",
                      result.stderr)
        self.assertFalse(self.grok_log.exists())


if __name__ == "__main__":
    unittest.main()
