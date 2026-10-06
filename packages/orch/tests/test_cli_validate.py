from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from orch import cli, contracts, schema
from tests.test_contracts_input import fixture, signed

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts/orch.py"


class CliValidateTests(unittest.TestCase):
    def run_cli(self, kind, document, *options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "input.json")
            path.write_text(json.dumps(document), encoding="utf-8")
            return subprocess.run([sys.executable, str(LAUNCHER), "validate", kind, str(path), *options],
                                  cwd=directory, capture_output=True, text=True, check=False)

    def test_incompatible_contract_version(self):
        result = self.run_cli("execution-input", {"contract_version": "exec/v2"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("CONTRACT_VERSION:", result.stderr)
        issues = json.loads(result.stdout)
        self.assertEqual(issues[0]["code"], "CONTRACT_VERSION")
        self.assertEqual(issues[0]["path"], "/contract_version")

    def test_unknown_kind_is_refusal(self):
        result = self.run_cli("not-a-kind", {"contract_version": "exec/v1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("SCHEMA_PROFILE: unknown schema kind", result.stderr)

    def test_quiet_keeps_error_and_status(self):
        result = self.run_cli("run-policy", {"contract_version": "exec/v2"}, "--quiet")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("CONTRACT_VERSION:", result.stderr)

    def test_warning_only_input_succeeds_and_preserves_level(self):
        doc = fixture("execution-input", "plan-bound")
        doc["constraints"] = [{"text": "Avoid task:plan-run", "source": "plan.rules[2]"}]
        for options in ((), ("--quiet",)):
            with self.subTest(options=options):
                result = self.run_cli("execution-input", signed(doc), *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("LIFECYCLE_LEAK:", result.stderr)
                if options:
                    self.assertEqual(result.stdout, "")
                else:
                    issues = json.loads(result.stdout)
                    self.assertEqual([(i["code"], i["level"]) for i in issues],
                                     [("LIFECYCLE_LEAK", "warning")])

    def test_warning_does_not_mask_errors(self):
        doc = fixture("execution-input", "plan-bound")
        doc["constraints"] = [{"text": "Avoid task:plan-run", "source": "plan.rules[2]"}]
        del doc["goal"]
        result = self.run_cli("execution-input", signed(doc))
        self.assertEqual(result.returncode, 1)
        issues = {i["code"]: i["level"] for i in json.loads(result.stdout)}
        self.assertEqual(issues, {"required": "error", "LIFECYCLE_LEAK": "warning"})

    def test_missing_schema_fails_closed(self):
        with self.assertRaises(schema.SchemaProfileError):
            schema.Registry({}, urn_prefix=contracts.URN_PREFIX, kinds=contracts.KINDS).for_kind("run-policy")

    def test_valid_output_and_schema_errors(self):
        kind = "execution-input"
        # Document schemas belong to P1.2/P1.3; exercise the CLI with a small test registry.
        registry = schema.Registry({contracts.URN_PREFIX + kind + ":v1": {
            "type": "object", "required": ["goal"],
        }}, urn_prefix=contracts.URN_PREFIX, kinds=contracts.KINDS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "input.json")
            for doc, expected in (({"contract_version": "exec/v1", "goal": "x"}, 0),
                                  ({"contract_version": "exec/v1"}, 1)):
                path.write_text(json.dumps(doc), encoding="utf-8")
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch("orch.contracts.load_registry", return_value=registry), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    result = cli.main(["validate", kind, str(path)])
                self.assertEqual(result, expected)
                output = json.loads(stdout.getvalue())
                if expected == 0:
                    self.assertEqual(output, {"valid": True})
                    self.assertEqual(stderr.getvalue(), "")
                else:
                    self.assertEqual(output[0]["code"], "required")
                    self.assertIn("required:", stderr.getvalue())

    def test_file_and_usage_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "input.json")
            for content in (None, "{"):
                if content is not None:
                    path.write_text(content)
                result = subprocess.run([sys.executable, str(LAUNCHER), "validate", "run-policy", str(path)],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn("INPUT_INVALID:", result.stderr)
        result = subprocess.run([sys.executable, str(LAUNCHER), "validate"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
