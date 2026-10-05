"""Markdown carrier execution preserves every required command and its failures."""
import subprocess
import unittest

from task.plan_work import WorkError, _validation_argv


class ValidationCarrierTests(unittest.TestCase):
    def test_plain_shell_command_is_unchanged(self):
        self.assertEqual(_validation_argv("pnpm -r test"), ["bash", "-lc", "pnpm -r test"])

    def test_plain_shell_command_substitution_is_preserved(self):
        carrier = "printf `printf substituted`"
        result = subprocess.run(_validation_argv(carrier), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "substituted")

    def test_every_markdown_command_executes_without_result_prose(self):
        carrier = "- `printf first` → exit 0; `printf second` → passed."
        result = subprocess.run(_validation_argv(carrier), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "firstsecond")

    def test_red_command_cannot_be_masked_by_later_success(self):
        carrier = "- `exit 7` → exit 0; `printf must-not-run` → passed."
        result = subprocess.run(_validation_argv(carrier), capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "")

    def test_extra_prose_cannot_hide_an_inferred_command(self):
        with self.assertRaisesRegex(WorkError, "PLAN_WORK_CHECKS_INVALID"):
            _validation_argv("- `printf first` → passed; also inspect `other-file`.")


if __name__ == "__main__":
    unittest.main()
