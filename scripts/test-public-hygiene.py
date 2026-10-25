#!/usr/bin/env python3
"""Tests scripts/public-hygiene.py — synthetic list of paths, without real git ls-files."""
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    "public_hygiene",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "public-hygiene.py"),
)
public_hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(public_hygiene)


class TestPublicHygiene(unittest.TestCase):
    def test_forbidden_suffix(self):
        violations = public_hygiene.check(["dump.sqlite"])
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], "dump.sqlite")

    def test_example_suffix_exempt(self):
        violations = public_hygiene.check([".env.example", "config.example"])
        self.assertEqual(violations, [])

    def test_dotenv_forbidden(self):
        violations = public_hygiene.check([".env", "packages/x/.env"])
        self.assertEqual(len(violations), 2)

    def test_clean_list_zero_violations(self):
        violations = public_hygiene.check(["README.md", "packages/aicore/lib/aicore/io.py", "docs/status.md"])
        self.assertEqual(violations, [])

    def test_component_rules(self):
        violations = public_hygiene.check(
            ["a/__pycache__/x.pyc", "a/.venv/bin/python", "a/node_modules/x/index.js"]
        )
        self.assertEqual(len(violations), 3)

    def test_content_rule_flags_real_environment_paths_only(self):
        # Built from parts so this test file does not trip the very rule it checks.
        files = {
            "a.md": "cd /home/" + "ivan/projects/app && make",
            "b.json": '{"p": "/Users/' + 'maria/.claude/settings.json"}',
            "c.md": "example /home/user/projects/x and `~/projects/app` and <REPO_ROOT>/plans",
            "d.md": "C:" + "\\Users\\" + "ivan\\proj",
        }
        found = public_hygiene.content_violations(sorted(files), read=files.get)
        self.assertEqual(sorted(path.split(" ")[0] for path, _ in found), ["a.md", "b.json", "d.md"])

    def test_working_directories_must_not_be_tracked(self):
        found = public_hygiene.plan_reference_violations(
            ["plans/ACTIVE.md", "road" + "map/x.md", "tas" + "ks/y/README.md", ".cursor/plans/z.md", "docs/a.md"],
            read=lambda _p: "")
        self.assertEqual(sorted(path for path, _ in found),
                         [".cursor/plans/z.md", "plans/ACTIVE.md", "road" + "map/x.md", "tas" + "ks/y/README.md"])

    def test_plan_reference_rules_flag_concrete_identity_only(self):
        # Built from parts so this test file does not trip the rules it checks.
        date = "2026" + ".07.24"
        files = {
            "a.md": f"see {date}-AGENT-RELIABILITY for details",
            "b.md": "cite PLAN" + "1.D35 here",
            "c.md": "link roadmap" + "/slug.md",
            "d.md": f"plans/{date}-X/phases",
            "ok1.md": f"fixture {date}-DEMO-ONE and plans/{date}-DEMO/phases",
            "ok2.md": "generic plans/<PLAN-ID>/journal.jsonl and PLAN<N>.D35 and product-roadmap/SKILL.md",
        }
        found = public_hygiene.plan_reference_violations(sorted(files), read=files.get)
        self.assertEqual(sorted({path.split(" ")[0] for path, _ in found}), ["a.md", "b.md", "c.md", "d.md"])

    def test_plan_syntax_test_trees_are_exempt_from_plan_rules_only(self):
        date = "2026" + ".07.24"
        tree = next(iter(public_hygiene.PLAN_SYNTAX_TEST_TREES))
        files = {f"{tree}t.py": f"id {date}-GOLD and PLAN" + "1.P1", "src/t.py": f"id {date}-GOLD"}
        found = public_hygiene.plan_reference_violations(sorted(files), read=files.get)
        self.assertEqual([path.split(" ")[0] for path, _ in found], ["src/t.py"])
        leak = {f"{tree}t.py": "/home/" + "vostrikov/projects/x"}
        self.assertEqual(len(public_hygiene.content_violations(sorted(leak), read=leak.get)), 1)

    def test_plan_syntax_test_trees_are_live_directories(self):
        tracked = public_hygiene.list_tracked_files()
        for tree, reason in public_hygiene.PLAN_SYNTAX_TEST_TREES.items():
            self.assertTrue(reason)
            self.assertTrue(tree.endswith("/"), tree)
            self.assertTrue(any(path.startswith(tree) for path in tracked), f"dead exemption: {tree}")

    def test_no_sealed_measurement_exemption_remains(self):
        self.assertEqual(public_hygiene.CONTENT_PLAN_EXEMPT, {})
        self.assertEqual(public_hygiene.CONTENT_PLAN_EXEMPT_SHA256, {})

    def test_binary_or_unreadable_files_are_skipped(self):
        self.assertEqual(public_hygiene.content_violations(["x.bin"], read=lambda _p: None), [])

    def test_reason_named_in_output(self):
        violations = public_hygiene.check(["secret.pem"])
        self.assertEqual(violations, [("secret.pem", "private key/certificate")])


class TestNeutrality(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / "neutrality.json"
        self.baseline_path = Path(self.directory.name) / "neutrality-baseline.json"
        self.data = json.loads(public_hygiene.NEUTRALITY_FILE.read_text(encoding="utf-8"))
        self.org = "acade" + "mici"
        self.workspace = "axio" + "ma"
        self.path = "packages/x/lib/y.py"
        self.key = "owner-org|" + self.path
        self.write_rules()
        self.write_baseline({})

    def write_rules(self):
        self.config_path.write_text(json.dumps(self.data), encoding="utf-8")

    def write_baseline(self, counts):
        self.baseline_path.write_text(json.dumps({"schema_version": 1, "counts": counts}), encoding="utf-8")

    def rules(self):
        return public_hygiene.neutrality_rules(self.config_path)

    def run_main(self, files, *flags):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(public_hygiene, "NEUTRALITY_FILE", self.config_path), \
                patch.object(public_hygiene, "BASELINE_FILE", self.baseline_path), \
                patch.object(public_hygiene, "list_tracked_files", return_value=list(files)), \
                patch.object(public_hygiene, "_read_text", side_effect=files.get), \
                redirect_stdout(output), redirect_stderr(errors):
            exit_code = public_hygiene.main(["public-hygiene.py", *flags])
        return exit_code, output.getvalue(), errors.getvalue()

    def test_a_strict_rejects_runtime_term_at_physical_line(self):
        files = {self.path: "# header\n" + self.org + " " + "x" * 100}
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual(hits[0][:3], ("owner-org", self.path, 2))
        self.assertLessEqual(len(hits[0][3]), 80)
        self.assertIn(self.org, hits[0][3])
        exit_code, output, _errors = self.run_main(files, "--neutrality-strict")
        self.assertEqual(exit_code, 1)
        self.assertIn(f"{self.path}:2 — neutrality «owner-org»:", output)

    def test_b_ratchet_permits_existing_count_and_rejects_growth(self):
        files = {self.path: self.org}
        baseline = {"schema_version": 1, "counts": {self.key: 1}}
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual(public_hygiene.ratchet(hits, baseline), ([], []))
        files[self.path] += "\n" + self.org
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        violations, improved = public_hygiene.ratchet(hits, baseline)
        self.assertEqual([hit[2] for hit in violations], [2])
        self.assertEqual(improved, [])
        self.write_baseline({self.key: 1})
        self.assertEqual(self.run_main(files)[0], 1)
        self.assertEqual(self.run_main({self.path: self.org})[:2], (0, "public-hygiene: 0 violations\n"))

    def test_c_excluded_trees_are_not_read(self):
        paths = ["packages/x/tests/a.py", "packages/x/fixtures/a.txt", "tests/a.py", "fixtures/a.py",
                 "packages/x/examples/a.md", "packages/" + self.workspace + "/lib/a.py", "CHANGELOG.md",
                 "releases/a.md", "plans/a.md", "audits/a.md", ".swissknifeman/a.md", "docs/reference.md"]
        def unexpected_read(path):
            self.fail("excluded path was read: " + path)
        self.assertEqual(public_hygiene.neutrality_hits(paths, self.rules(), read=unexpected_read), [])

    def test_d_json_allowance_only_covers_attribution_values(self):
        path = "packages/x/configs/plugin.json"
        files = {path: json.dumps({"author": self.org, "description": self.org}, indent=2)}
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual([hit[:3] for hit in hits], [("owner-org", path, 3)])
        files[path] = json.dumps({"author": {"name": self.org}, "description": self.org})
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 1)
        files[path] = json.dumps({self.org: "author", "description": {"author": self.org}})
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 1)
        files[path] = '{"author": "' + self.org + '", broken}'
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 1)
        files = {"packages/x/lib/a.py": 'author = "' + self.org + '"'}
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 1)

    def test_json_decodes_escaped_values_without_losing_line_numbers(self):
        encoded = "\\u0061" + self.org[1:]
        path = "packages/x/configs/plugin.json"
        files = {path: '{\n  "author": "' + encoded + '",\n  "description": "' + encoded + '"\n}'}
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual([hit[:3] for hit in hits], [("owner-org", path, 3)])
        files[path] = json.dumps({"author": [self.org], "description": self.org + " " + self.org})
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 2)

    def test_e_research_allowance_does_not_cover_other_docs(self):
        files = {"packages/orch/docs/research/a.md": self.org, "packages/x/docs/audits/a.md": self.org,
                 "packages/orch/docs/researcher/a.md": self.org}
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual([hit[1] for hit in hits], ["packages/orch/docs/researcher/a.md"])

    def test_f_update_refuses_growth_and_preserves_baseline_bytes(self):
        self.write_baseline({self.key: 1})
        before = self.baseline_path.read_bytes()
        files = {self.path: self.org + "\n" + self.org}
        exit_code, output, _errors = self.run_main(files, "--neutrality-update-baseline")
        self.assertEqual(exit_code, 1)
        self.assertIn(f"NEUTRALITY_BASELINE_GROWTH: {self.key} 1→2", output)
        self.assertEqual(before, self.baseline_path.read_bytes())
        exit_code, output, errors = self.run_main(files, "--neutrality-update-baseline", "--json")
        self.assertEqual((exit_code, errors), (1, ""))
        self.assertIn("NEUTRALITY_BASELINE_GROWTH", json.loads(output)["violations"][0]["reason"])
        self.write_baseline({})
        self.assertEqual(self.run_main({self.path: self.org}, "--neutrality-update-baseline")[0], 1)

    def test_g_name_boundaries(self):
        project = "co" + "rex"
        files = {self.path: " ".join([self.workspace + "tic", project + "yz", "x" + self.org,
                                     "pre-" + self.org, "_" + self.org, self.org + "_id", self.org + "2"])}
        self.assertEqual(public_hygiene.neutrality_hits(files, self.rules(), read=files.get), [])
        files[self.path] = "(" + self.workspace.upper() + ") " + project + "-tool"
        self.assertEqual(len(public_hygiene.neutrality_hits(files, self.rules(), read=files.get)), 2)

    def test_h_invalid_config_returns_exit_two_with_pointer(self):
        for data in ["{broken", '[]', json.dumps({**self.data, "unexpected": True}),
                     json.dumps({**self.data, "terms": [{"id": "bad", "pattern": "[", "reason": "test"}]})]:
            with self.subTest(data=data[:30]):
                self.config_path.write_text(data, encoding="utf-8")
                exit_code, output, errors = self.run_main({})
                self.assertEqual(exit_code, 2)
                self.assertEqual(output, "")
                self.assertIn("NEUTRALITY_CONFIG_INVALID: /", errors)
        self.config_path.unlink()
        self.assertEqual(self.run_main({})[0], 2)

    def test_invalid_allowances_fail_closed(self):
        cases = [{"path_glob": "packages/*/" + folder + "/**", "term": "*", "reason": "test"}
                 for folder in public_hygiene.RUNTIME_FOLDERS]
        cases += [{"path_glob": "packages/harness/configs/common/agent-packs/**", "term": "*", "reason": "test"},
                  {"json_fields": ["description"], "term": "*", "reason": "test"},
                  {"path_glob": "docs/**", "term": "unknown", "reason": "test"},
                  {"path_glob": "docs/**", "term": "*", "reason": "  "}]
        for allow in cases:
            with self.subTest(allow=allow):
                original = self.data["allow"]
                self.data["allow"] = [allow]
                self.write_rules()
                with self.assertRaisesRegex(public_hygiene.NeutralityConfigError, "/allow/0"):
                    self.rules()
                self.data["allow"] = original

    def test_term_ids_are_unique_and_reasons_are_required(self):
        self.data["terms"].append(dict(self.data["terms"][0]))
        self.write_rules()
        with self.assertRaisesRegex(public_hygiene.NeutralityConfigError, "duplicate term id"):
            self.rules()
        self.data["terms"].pop()
        self.data["terms"][0]["reason"] = "  "
        self.write_rules()
        with self.assertRaisesRegex(public_hygiene.NeutralityConfigError, "reason must not be blank"):
            self.rules()

    def test_broad_allowances_cannot_hide_runtime_content(self):
        self.data["allow"] = [{"path_glob": "**", "term": "*", "reason": "test broad historical rule"}]
        self.write_rules()
        files = {"packages/x/" + folder + "/a.txt": self.org for folder in public_hygiene.RUNTIME_FOLDERS}
        files["bootstrap/agent-packs/a.md"] = self.org
        files["docs/a.md"] = self.org
        hits = public_hygiene.neutrality_hits(files, self.rules(), read=files.get)
        self.assertEqual(sorted(hit[1] for hit in hits), sorted(path for path in files if path != "docs/a.md"))

    def test_update_initializes_only_absent_baseline_then_is_deterministic(self):
        self.baseline_path.unlink()
        files = {self.path: self.org, "packages/a/lib/z.py": self.workspace}
        self.assertEqual(self.run_main(files)[0], 2)
        self.assertEqual(self.run_main(files, "--neutrality-update-baseline")[0], 0)
        expected = {"schema_version": 1, "counts": {self.key: 1, "owner-workspace|packages/a/lib/z.py": 1}}
        before = self.baseline_path.read_bytes()
        self.assertEqual(before.decode(), json.dumps(expected, sort_keys=True, indent=2) + "\n")
        self.assertEqual(self.run_main(files, "--neutrality-update-baseline")[0], 0)
        self.assertEqual(before, self.baseline_path.read_bytes())

    def test_decreases_include_removed_keys_and_update_drops_zero_counts(self):
        removed = "owner-workspace|packages/a/lib/z.py"
        self.write_baseline({self.key: 2, removed: 1})
        files = {self.path: self.org}
        exit_code, output, _errors = self.run_main(files)
        self.assertEqual(exit_code, 0)
        self.assertIn(f"neutrality: improved {self.key} 2→1", output)
        self.assertIn(removed + " 1→0", output)
        self.assertEqual(self.run_main(files, "--neutrality-update-baseline")[0], 0)
        self.assertEqual(json.loads(self.baseline_path.read_text())["counts"], {self.key: 1})

    def test_invalid_existing_baseline_never_bootstraps(self):
        for document in [{"schema_version": 2, "counts": {}}, {"schema_version": 1, "counts": {self.key: -1}},
                         {"schema_version": 1, "counts": {self.key: True}}, {"schema_version": 1, "counts": {}, "extra": 0}]:
            self.baseline_path.write_text(json.dumps(document), encoding="utf-8")
            before = self.baseline_path.read_bytes()
            self.assertEqual(self.run_main({}, "--neutrality-update-baseline")[0], 2)
            self.assertEqual(before, self.baseline_path.read_bytes())

    def test_json_is_only_a_report_for_neutrality_legacy_and_errors(self):
        files = {self.path: self.org, "private.pem": "key"}
        exit_code, output, errors = self.run_main(files, "--neutrality-strict", "--json")
        self.assertEqual(exit_code, 1)
        self.assertEqual(errors, "")
        report = json.loads(output)
        self.assertEqual(set(report), {"violations", "improved", "counts"})
        self.assertEqual(report["counts"], {self.key: 1})
        self.assertEqual({row["term"] for row in report["violations"]}, {"path", "owner-org"})
        public_hygiene._validate_neutrality(report, "report")
        self.config_path.write_text("{}", encoding="utf-8")
        exit_code, output, errors = self.run_main({}, "--json")
        self.assertEqual((exit_code, errors), (2, ""))
        report = json.loads(output)
        self.assertIn("NEUTRALITY_CONFIG_INVALID", report["violations"][0]["reason"])
        public_hygiene._validate_neutrality(report, "report")

    def test_out_of_scope_and_unreadable_files_are_skipped(self):
        files = {"outside/a.py": self.org, "packages/x/lib/a.bin": None}
        self.assertEqual(public_hygiene.neutrality_hits(files, self.rules(), read=files.get), [])

    def test_default_reader_skips_binary_and_oversized_files(self):
        binary = Path(self.directory.name) / "binary"
        large = Path(self.directory.name) / "large"
        binary.write_bytes(self.org.encode() + b"\0")
        large.write_bytes(self.org.encode() * (public_hygiene.CONTENT_MAX_BYTES // len(self.org) + 1))
        rules = self.rules()
        for path in [binary, large]:
            self.assertEqual(public_hygiene.neutrality_hits([self.path], rules,
                             read=lambda _p, source=path: public_hygiene._read_text(source)), [])

    def test_policy_schema_examples_accept_valid_and_reject_additional_fields(self):
        directory = public_hygiene.ROOT / "configs/examples/neutrality"
        valid = json.loads((directory / "valid/document.json").read_text(encoding="utf-8"))
        public_hygiene._validate_neutrality(valid)
        invalid = json.loads((directory / "invalid/additional-document.json").read_text(encoding="utf-8"))
        self.assertEqual(invalid, {**valid, "not-a-field": 1})
        with self.assertRaisesRegex(public_hygiene.NeutralityConfigError, "NEUTRALITY_CONFIG_INVALID"):
            public_hygiene._validate_neutrality(invalid)


if __name__ == "__main__":
    unittest.main()
