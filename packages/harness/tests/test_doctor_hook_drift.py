"""harness doctor: the installed auto-approve hook is compared with the shipped one (audit 2026-10-17 §5.5)."""
import dataclasses
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness import doctor  # noqa: E402
from harness.common import Env  # noqa: E402

PACKAGE = Path(__file__).resolve().parents[1]
SHIPPED = PACKAGE / "configs" / "claude-code" / "hooks"


class HookDriftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hooks = Path(tmp.name) / ".claude" / "hooks"
        self.hooks.mkdir(parents=True)
        for name in ("notify", "memory", "auto-approve", "run-report", "review-gate"):
            shutil.copytree(SHIPPED / name, self.hooks / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(SHIPPED / "log-bash-command.sh", self.hooks / "log-bash-command.sh")
        self.env = dataclasses.replace(Env(PACKAGE, "test"), home=Path(tmp.name))

    def check(self):
        return doctor._hooks_check(self.env)

    def test_an_identical_copy_is_ok(self):
        self.assertEqual(self.check()["status"], "ok")

    def test_a_changed_code_file_warns_and_names_it(self):
        (self.hooks / "auto-approve" / "lib" / "analyze.sh").write_text("# old\n", encoding="utf-8")
        result = self.check()
        self.assertEqual(result["status"], "warn")
        self.assertIn("auto-approve/lib/analyze.sh", result["observed"])

    def test_a_missing_new_file_warns(self):
        (self.hooks / "auto-approve" / "lib" / "shellscan.py").unlink()
        self.assertIn("shellscan.py", self.check()["observed"])

    def test_a_local_config_is_kept_and_only_noted(self):
        (self.hooks / "auto-approve" / "config.json").write_text("{}", encoding="utf-8")
        (self.hooks / "auto-approve" / "env.ini").write_text("MODE=off\n", encoding="utf-8")
        result = self.check()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any("config.json" in line for line in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
