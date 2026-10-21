"""Batch fixture validation preserves public CLI verdicts without spawning one process per input."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-fixtures.py"
spec = importlib.util.spec_from_file_location("validate_fixtures", SCRIPT)
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class ValidateFixturesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for category in ("valid", "invalid"):
            (self.root / category / "check-evidence").mkdir(parents=True)
        shutil.copyfile(ROOT / "fixtures/exec/v1/valid/check-evidence/cmd-pass.json",
                        self.root / "valid/check-evidence/ok.json")
        bad = json.loads((self.root / "valid/check-evidence/ok.json").read_text())
        bad.pop("check_id")
        (self.root / "invalid/check-evidence/bad.json").write_text(json.dumps(bad))

    def run_batch(self, *directories):
        out = io.StringIO()
        with redirect_stdout(out):
            code = batch.main([str(p) for p in directories or [self.root]])
        return code, out.getvalue()

    def test_valid_and_invalid_verdicts_then_misplaced_invalid_fixture(self):
        self.assertEqual(self.run_batch(), (0, "fixtures: 2 checked, 0 mismatched\n"))
        (self.root / "invalid/check-evidence/bad.json").rename(self.root / "valid/check-evidence/bad.json")
        code, output = self.run_batch()
        self.assertEqual(code, 1)
        self.assertIn("bad.json: exit 1, expected 0", output)
        self.assertIn("fixtures: 2 checked, 1 mismatched", output)

    def test_system_exit_is_a_verdict_and_multiple_directories_share_entrypoint(self):
        with patch.object(batch.cli, "main", side_effect=[SystemExit(1), SystemExit(0)]) as validate:
            code, output = self.run_batch(self.root, self.root / "empty")
        self.assertEqual(code, 1)
        self.assertEqual(validate.call_count, 2)
        self.assertIn("ok.json: exit 1, expected 0", output)
        self.assertIn("bad.json: exit 0, expected 1", output)

    def test_script_subprocess_preserves_exit_and_summary(self):
        done = subprocess.run([sys.executable, str(SCRIPT), str(self.root)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "fixtures: 2 checked, 0 mismatched\n")

    def test_all_real_fixture_verdicts_match_without_child_processes(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("unexpected child process")):
            code, output = self.run_batch(ROOT / "fixtures/exec/v1", ROOT / "fixtures/conductor/v1")
        expected = sum(len(list((ROOT / directory / category).glob("*/*.json")))
                       for directory in ("fixtures/exec/v1", "fixtures/conductor/v1") for category in ("valid", "invalid"))
        self.assertGreater(expected, 0)
        self.assertEqual(code, 0, output)
        self.assertEqual(output, f"fixtures: {expected} checked, 0 mismatched\n")
