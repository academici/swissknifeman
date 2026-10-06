"""Read-only resolution of registry identities, dependency closure and diagnostics."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from skiller.registry import build_registry
from tests.fixtures import make_registry


class ResolveCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root, self.env = make_registry(Path(temporary.name))
        self.registry, _, _ = build_registry(self.env)
        self._write_registry()

    def _write_registry(self):
        (self.root / "skills.json").write_text(json.dumps(self.registry), encoding="utf-8")

    def _entry(self, name):
        return next(s for s in self.registry["skills"] if s["name"] == name)

    def _invoke(self, *args):
        from skiller.cli import main
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                main([str(self.root), "resolve", *args])
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def _json(self, *args):
        code, stdout, stderr = self._invoke(*args, "--json")
        return code, json.loads(stdout), stderr

    def test_requested_only_and_read_only(self):
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        code, data, stderr = self._json("quality/test-writer")
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(data, {
            "schema": "skiller.resolve/v1", "requested": ["quality/test-writer"],
            "provider": None, "skills": [{
                "name": "test-writer", "id": "quality/test-writer", "bucket": "quality",
                "path": "skills/quality/test-writer/SKILL.md", "requested": True,
                "required_by": [],
            }], "diagnostics": [],
        })
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})

    def test_transitive_closure_and_required_by(self):
        self._entry("code-style")["requires"] = ["quality:test-writer"]
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions")
        self.assertEqual(code, 0)
        self.assertEqual([s["name"] for s in data["skills"]],
                         ["code-style", "laravel-conventions", "test-writer"])
        by_id = {s["id"]: s for s in data["skills"]}
        self.assertEqual(by_id["php/code-style"]["required_by"], ["php/laravel-conventions"])
        self.assertEqual(by_id["quality/test-writer"]["required_by"], ["php/code-style"])
        self.assertFalse(by_id["php/code-style"]["requested"])

    def test_diamond_collects_all_immediate_requesters(self):
        self._entry("test-writer")["requires"] = ["code-style"]
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions", "test-writer")
        self.assertEqual(code, 0)
        style = next(s for s in data["skills"] if s["name"] == "code-style")
        self.assertEqual(style["required_by"], ["php/laravel-conventions", "quality/test-writer"])
        self.assertEqual(len(data["skills"]), 3)

    def test_cycles_are_bounded_and_requested_dependency_keeps_its_flag(self):
        self._entry("code-style")["requires"] = ["laravel-conventions"]
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions")
        self.assertEqual(code, 0)
        self.assertEqual(len(data["skills"]), 2)
        code, data, _ = self._json("php/laravel-conventions", "php:code-style")
        self.assertEqual(code, 0)
        self.assertEqual(len(data["skills"]), 2)
        self.assertTrue(all(s["requested"] for s in data["skills"]))

    def test_colon_slash_and_unique_bare_name_are_equivalent(self):
        outputs = [self._json(token)[1] for token in
                   ("php/code-style", "php:code-style", "code-style")]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_repeated_requests_normalize_and_deduplicate(self):
        code, data, _ = self._json("code-style", "php:code-style", "php/code-style")
        self.assertEqual(code, 0)
        self.assertEqual(data["requested"], ["php/code-style"])
        self.assertEqual(len(data["skills"]), 1)

    def test_ambiguous_bare_name_reports_sorted_candidates(self):
        self.registry["skills"].append({
            "name": "code-style", "bucket": "quality",
            "path": "skills/quality/code-style/SKILL.md",
        })
        self._write_registry()
        code, data, _ = self._json("code-style")
        self.assertEqual(code, 1)
        self.assertEqual(data["skills"], [])
        self.assertEqual(data["diagnostics"], [{
            "code": "SKILL_AMBIGUOUS", "severity": "error", "skill": "code-style",
            "candidates": ["php/code-style", "quality/code-style"],
        }])
        self.assertEqual(self._json("quality/code-style")[0], 0)

    def test_ambiguous_transitive_name_requires_explicit_identity(self):
        self.registry["skills"].append({
            "name": "code-style", "bucket": "quality",
            "path": "skills/quality/code-style/SKILL.md",
        })
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions")
        self.assertEqual(code, 1)
        self.assertEqual([d["code"] for d in data["diagnostics"]], ["SKILL_AMBIGUOUS"])
        self._entry("laravel-conventions")["requires"] = ["php:code-style"]
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions")
        self.assertEqual(code, 0)
        self.assertEqual([s["id"] for s in data["skills"]],
                         ["php/code-style", "php/laravel-conventions"])

    def test_registry_order_does_not_change_output(self):
        first = self._json("php/laravel-conventions", "quality/test-writer")[1]
        self.registry["skills"].reverse()
        self._write_registry()
        self.assertEqual(first, self._json("php/laravel-conventions", "quality/test-writer")[1])

    def test_unknown_requested_skill_is_error_with_json_and_partial_result(self):
        code, data, _ = self._json("quality/no-such-skill", "test-writer")
        self.assertEqual(code, 1)
        self.assertEqual(data["diagnostics"], [{
            "code": "SKILL_UNKNOWN", "severity": "error", "skill": "quality/no-such-skill",
        }])
        self.assertEqual(len(data["skills"]), 1)

    def test_unknown_transitive_skill_is_warning_and_success(self):
        self._entry("code-style")["requires"] = ["missing", "missing"]
        self._write_registry()
        code, data, stderr = self._json("php/laravel-conventions")
        self.assertEqual(code, 0)
        self.assertEqual(data["diagnostics"], [{
            "code": "SKILL_REQUIRED_UNKNOWN", "severity": "warning",
            "required_skill": "missing", "affected_identities": ["php/code-style"],
        }])
        self.assertIn("requires unknown skill", stderr)

    def test_provider_without_adapter_metadata_is_echo_only(self):
        code, data, _ = self._json("test-writer", "--provider", "codex")
        self.assertEqual(code, 0)
        self.assertEqual(data["provider"], "codex")
        self.assertEqual(data["diagnostics"], [])

    def test_provider_warning_preserves_unsupported_skill(self):
        self._entry("code-style")["adapters"] = ["claude"]
        self._write_registry()
        code, data, _ = self._json("php/laravel-conventions", "--provider", "codex")
        self.assertEqual(code, 0)
        self.assertEqual(len(data["skills"]), 2)
        self.assertEqual(data["diagnostics"], [{
            "code": "SKILL_PROVIDER_UNSUPPORTED", "severity": "warning",
            "skill": "php/code-style", "provider": "codex",
        }])
        self.assertEqual(self._json("code-style", "--provider", "claude-code")[1]["diagnostics"], [])

    def test_no_skills_and_invalid_provider_are_usage_errors(self):
        self.assertEqual(self._invoke()[0], 2)
        self.assertEqual(self._invoke("test-writer", "--provider", "invalid")[0], 2)

    def test_help_and_text_output(self):
        code, stdout, _ = self._invoke("--help")
        self.assertEqual(code, 0)
        self.assertIn("skiller resolve", stdout)
        code, stdout, _ = self._invoke("php/laravel-conventions")
        self.assertEqual(code, 0)
        self.assertIn("php/laravel-conventions", stdout)
        self.assertIn("required_by", stdout)

    def test_real_registry_through_shell_launcher(self):
        package = Path(__file__).resolve().parents[1]
        result = subprocess.run([str(package / "bin/skiller"), "resolve",
                                 "quality/code-review", "--json"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["schema"], "skiller.resolve/v1")
        self.assertTrue(any(s["id"] == "quality/code-review" for s in data["skills"]))
