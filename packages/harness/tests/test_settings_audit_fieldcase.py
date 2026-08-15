"""Internal documentation."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from harness.common import Env
from harness.settings_audit import build_context, exit_code, run_checks

from tests.test_settings_audit import _write


class SettingsDoctorFieldCase(unittest.TestCase):
    """Internal documentation."""

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

    def test_full_field_case_caught_in_one_pass(self):

        _write(self.home / ".claude" / "settings.json",
               {"permissions": {"defaultMode": "default"}})



        dead_allow = [f"Bash(echo {i})" for i in range(400)]
        _write(self.home / ".claude" / "settings.json", {
            "permissions": {"defaultMode": "default", "allow": dead_allow},
        })

        real_dir = self.tmp / "trusted"
        real_dir.mkdir()



        _write(self.target / ".claude" / "settings.json", {
            "permissions": {
                "defaultMode": "bypassPermissions",
                "autoApprove": True,
                "additionalDirectories": [str(real_dir)],
            },
            "hooks": {"PreToolUse": [
                {"matcher": "Bash",
                 "hooks": [{"type": "command",
                            "command": str(self.target / "hooks" / "safe-dirs.sh")}]},
            ]},
        })


        _write(self.target / ".claude" / "settings.local.json",
               {"env": {"ANTHROPIC_API_KEY": "sk-ant-0123456789abcdef"}})

        ctx = build_context(self.env, self.target)
        findings = run_checks(ctx)
        by_id = {}
        for f in findings:
            by_id.setdefault(f.id, []).append(f)

        for expected_id in (2, 3, 5, 6, 9):
            self.assertIn(expected_id, by_id,
                           f"ожидалась находка id={expected_id}, получены id: "
                           f"{sorted(by_id.keys())}")


        self.assertNotIn(8, by_id)

        self.assertGreater(exit_code(findings), 0)
        error_count = sum(1 for f in findings if f.level == "error")
        self.assertGreater(error_count, 0)


if __name__ == "__main__":
    unittest.main()
