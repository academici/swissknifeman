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

    def install(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "XDG_"))}
        env.update(HOME=str(self.home), SKM_HOME=str(self.skm))
        subprocess.run(["bash", str(self.pkg / "install.sh"), "--bin-dir", str(self.tmp / "bin")],
                       env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

    def test_legacy_state_directory_is_a_source(self):
        (self.home / ".maind").mkdir()
        self.install()
        self.assertFalse(self.registry.exists())


if __name__ == "__main__":
    unittest.main()
