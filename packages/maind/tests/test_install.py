"""install.sh creates registry.json from the example only when no registry source exists."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


class InstallRegistryStep(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.mono = self.tmp / "mono"
        self.pkg = self.mono / "packages" / "maind"
        (self.pkg / "bin").mkdir(parents=True)
        (self.pkg / "configs").mkdir()
        shutil.copyfile(PACKAGE / "install.sh", self.pkg / "install.sh")
        shutil.copyfile(PACKAGE / "configs" / "registry.example.json",
                        self.pkg / "configs" / "registry.example.json")
        stub = self.pkg / "bin" / "maind"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.skm = self.tmp / "skm"
        self.registry = self.skm / "state" / "maind" / "registry.json"

    def install(self, script=None, isolated=True, **extra):
        script = script or self.pkg / "install.sh"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "XDG_"))}
        env.update(HOME=str(self.home), **extra)
        if isolated:
            env["SKM_HOME"] = str(self.skm)
        subprocess.run(["bash", str(script), "--bin-dir", str(self.tmp / "bin")],
                       env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_the_machine_home_holds_the_registry_without_skm_home(self):
        self.install(isolated=False)
        self.assertTrue((self.home / ".local/share/swissknifeman/state/maind/registry.json").is_file())
        self.assertFalse((self.home / ".local/state/swissknifeman").exists())

    def test_the_old_xdg_state_folder_is_kept_while_the_new_one_does_not_exist(self):
        old = self.home / ".local/state/swissknifeman"
        old.mkdir(parents=True)
        self.install(isolated=False)
        self.assertTrue((old / "maind/registry.json").is_file())
        self.assertFalse((self.home / ".local/share/swissknifeman/state").exists())
        moved = self.home / "xdg-state"
        (moved / "swissknifeman").mkdir(parents=True)
        self.install(isolated=False, XDG_STATE_HOME=str(moved))
        self.assertTrue((moved / "swissknifeman/maind/registry.json").is_file())

    def test_the_environment_snippet_is_added_when_aicore_is_next_to_the_module(self):
        shutil.copytree(PACKAGE.parent / "aicore", self.mono / "packages" / "aicore",
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))
        profile = self.home / ".bashrc"
        for _ in range(2):  # idempotent
            self.install(SHELL="/bin/bash", AICORE_ROOT="")
        text = profile.read_text(encoding="utf-8")
        self.assertEqual(text.count("# >>> swissknifeman environment"), 1)
        self.assertIn(f"SKM_HOME={self.skm}\n", text)
        self.install(SHELL="/bin/zsh", SKM_NO_SHELL_ENV="1")
        self.assertFalse((self.home / ".zshrc").exists())

    def test_without_aicore_the_snippet_step_is_skipped_and_the_install_goes_on(self):
        self.install(SHELL="/bin/bash", AICORE_ROOT="")
        self.assertFalse((self.home / ".bashrc").exists())
        self.assertTrue(self.registry.is_file())

    def test_creates_the_registry_when_there_is_no_source(self):
        self.install()
        self.assertTrue(self.registry.is_file())

    def test_legacy_node_files_are_sources_and_nothing_is_created(self):
        for legacy in (self.mono / "config.json", self.mono / ".maind.json",
                       self.pkg / ".maind.json"):
            with self.subTest(legacy=str(legacy.relative_to(self.tmp))):
                legacy.write_text("{}", encoding="utf-8")
                self.install()
                self.assertFalse(self.registry.exists())
                legacy.unlink()

    def test_a_plugin_cache_copy_never_reads_the_folders_above_it(self):
        cache = self.tmp / "cache" / "swissknifeman"
        copy = cache / "maind" / "1.0.0"
        shutil.copytree(self.pkg, copy)
        (cache / "packages").mkdir()  # what a stranger's two-levels-up folder could hold
        (cache / "config.json").write_text("{}", encoding="utf-8")
        self.install(copy / "install.sh")
        self.assertTrue(self.registry.is_file())

    def test_legacy_state_directory_is_a_source(self):
        (self.home / ".maind").mkdir()
        self.install()
        self.assertFalse(self.registry.exists())


if __name__ == "__main__":
    unittest.main()
