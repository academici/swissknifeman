"""aicore.content.skill: skill model, content hash, requires resolution and the skill-descriptor/v1 descriptor."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aicore.content import skill
from aicore.util import schema

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "skill-descriptor" / "v1"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_skill(root, frontmatter, body="Body.\n", name="demo"):
    directory = Path(root) / name
    write(directory / "SKILL.md", f"---\n{frontmatter}---\n{body}")
    return directory


class FrontmatterCase(unittest.TestCase):
    def test_reading_strips_bom_and_splits_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            path.write_bytes("﻿---\nname: a\nrequires: [x, y]\n---\nBody\n".encode("utf-8"))
            self.assertEqual(skill.read_frontmatter(path), {"name": "a", "requires": ["x", "y"]})
            self.assertEqual(skill.read_frontmatter_fields(path), {"name": "a", "requires": ["x", "y"]})

    def test_split_frontmatter(self):
        self.assertEqual(skill.split_frontmatter("---\na: 1\n---\nBody\n"), ("a: 1", "Body\n"))
        self.assertEqual(skill.split_frontmatter("no frontmatter\n"), ("", "no frontmatter\n"))
        self.assertEqual(skill.split_frontmatter("---\nunterminated\n"), ("", "---\nunterminated\n"))


class ContentHashCase(unittest.TestCase):
    def test_hash_covers_paths_and_bytes_in_sorted_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_skill(tmp, "name: demo\ndescription: d\n")
            write(directory / "references" / "a.md", "A")
            expected = hashlib.sha256()
            for rel, data in (("SKILL.md", (directory / "SKILL.md").read_bytes()),
                              ("references/a.md", b"A")):
                expected.update(rel.encode("utf-8"))
                expected.update(b"\0")
                expected.update(data)
            self.assertEqual(skill.skill_content_hash(directory), expected.hexdigest())
            self.assertEqual(skill.skill_digest(directory), "sha256:" + expected.hexdigest())

    def test_hash_ignores_what_is_not_vendored(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_skill(tmp, "name: demo\ndescription: d\n")
            before = skill.skill_content_hash(directory)
            write(directory / "upstream.json", "{}")
            write(directory / "SKILL.ru.md", "ru")
            write(directory / ".claude-plugin" / "plugin.json", "{}")
            write(directory / "evals" / "case.json", "{}")
            write(directory / "snippets" / "__pycache__" / "x.pyc", "x")
            write(directory / "snippets" / "y.pyc", "y")
            self.assertEqual(skill.skill_content_hash(directory), before)
            write(directory / "snippets" / "check.py", "print(1)")
            self.assertNotEqual(skill.skill_content_hash(directory), before)

    def test_ignore_list_names_the_service_files(self):
        for name in ("upstream.json", ".claude-plugin", "SKILL.*.md", "evals", "__pycache__", "*.pyc"):
            self.assertIn(name, skill.SKILL_IGNORE)


class RequiresCase(unittest.TestCase):
    def _resolve(self, seed, nodes, exclude=frozenset()):
        selected = {"root"}
        diagnostics = []
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            resolved = skill.resolve_requires_bfs(
                seed, nodes.get, selected, set(exclude), diagnostics=diagnostics)
        return resolved, diagnostics, stderr.getvalue(), selected

    def test_resolution_order_is_breadth_first_and_marks_selected(self):
        nodes = {
            "a": {"key": "a", "requires": ["c"], "exclude_tokens": set()},
            "b": {"key": "b", "requires": [], "exclude_tokens": set()},
            "c": {"key": "c", "requires": ["a"], "exclude_tokens": set()},
        }
        resolved, diagnostics, warning, selected = self._resolve([("a", "root"), ("b", "root")], nodes)
        self.assertEqual([(node["key"], requester) for node, requester in resolved],
                         [("a", "root"), ("b", "root"), ("c", "a")])
        self.assertEqual(selected, {"root", "a", "b", "c"})
        self.assertEqual((diagnostics, warning), ([], ""))

    def test_unknown_transitive_requirement_is_stable_and_emitted_once(self):
        nodes = {"middle": {"key": "middle", "requires": ["missing", "missing"], "exclude_tokens": {"middle"}}}
        _resolved, diagnostics, warning, _selected = self._resolve([("middle", "root")], nodes)
        self.assertEqual(diagnostics, [{
            "code": "SKILL_REQUIRED_UNKNOWN", "severity": "warning",
            "required_skill": "missing", "affected_identities": ["middle"],
        }])
        self.assertEqual(warning.count("'middle' requires unknown skill 'missing' — pass"), 2)

    def test_excluded_requirement_aggregates_requesters_deterministically(self):
        nodes = {"blocked": {"key": "blocked", "requires": [], "exclude_tokens": {"blocked", "bucket/blocked"}}}
        resolved, diagnostics, warning, _selected = self._resolve(
            [("blocked", "zeta"), ("blocked", "alpha")], nodes, exclude={"blocked"})
        self.assertEqual(resolved, [])
        self.assertEqual(diagnostics, [{
            "code": "SKILL_REQUIRED_EXCLUDED", "severity": "warning",
            "required_skill": "blocked", "affected_identities": ["alpha", "zeta"],
        }])
        self.assertEqual(
            warning.count("requires 'blocked', but he's in exclude — dependency missing"), 2)

    def test_aggregate_drops_malformed_records_and_merges_requesters(self):
        records = [
            {"code": "SKILL_REQUIRED_UNKNOWN", "required_skill": "x", "requester": "b"},
            {"code": "SKILL_REQUIRED_UNKNOWN", "required_skill": "x", "requester": "a"},
            {"code": "OTHER", "required_skill": "x", "requester": "a"},
            {"code": "SKILL_REQUIRED_EXCLUDED", "required_skill": "", "requester": "a"},
            {"code": "SKILL_REQUIRED_EXCLUDED", "required_skill": "y"},
        ]
        self.assertEqual(skill.aggregate_dependency_diagnostics(records), [{
            "code": "SKILL_REQUIRED_UNKNOWN", "severity": "warning",
            "required_skill": "x", "affected_identities": ["a", "b"],
        }])
        self.assertEqual(skill.DEPENDENCY_DIAGNOSTIC_CODES,
                         {"SKILL_REQUIRED_EXCLUDED", "SKILL_REQUIRED_UNKNOWN"})


class DescriptorCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.registry, self.kind = schema.load_contract(CONTRACT)

    def assert_valid(self, document):
        self.assertEqual(schema.validate(document, self.kind, self.registry), [])

    def test_local_skill(self):
        directory = make_skill(self.root, (
            "name: demo\ndescription: A demo skill.\nversion: 1.2.0\nadapters: [claude, codex]\n"
            "requires: [pm/a, pm/b]\nrisk: low\n"))
        descriptor = skill.describe_skill(directory, skill_id="pm/demo")
        document = descriptor.to_json()
        self.assertEqual(document, {
            "schema": "skill-descriptor/v1", "id": "pm/demo", "name": "demo", "description": "A demo skill.",
            "version": "1.2.0", "digest": skill.skill_digest(directory), "license": None,
            "compatibility": None, "allowed_tools": [], "adapters": ["claude", "codex"],
            "requires": ["pm/a", "pm/b"], "risk": "low", "metadata": {}, "provenance": {"source": "local"},
        })
        self.assert_valid(document)

    def test_minimal_skill_has_nulls_and_empties(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\n")
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        for key in ("version", "license", "compatibility", "risk"):
            self.assertIsNone(document[key], key)
        for key in ("allowed_tools", "adapters", "requires"):
            self.assertEqual(document[key], [], key)
        self.assertEqual(document["metadata"], {})
        self.assert_valid(document)

    def test_upstream_provides_license_and_provenance(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\n")
        write(directory / "upstream.json", json.dumps({
            "schema_version": 1, "source": "github", "repo": "o/r", "strategy": "notify", "license": "MIT",
            "notes": "dropped",
            "files": [{"path": "SKILL.md", "url": "https://example.com/SKILL.md", "sha256": "a" * 64,
                       "fetched_at": "2026-06-17", "extra": "dropped"}],
            "audit": {"verdict": "pass", "at": "2026-06-17", "by": "dropped", "upstream_sha": "abc"},
        }))
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        self.assertEqual(document["license"], "MIT")
        self.assertEqual(document["provenance"], {
            "source": "github", "repo": "o/r", "strategy": "notify", "license": "MIT",
            "files": [{"path": "SKILL.md", "url": "https://example.com/SKILL.md", "sha256": "a" * 64,
                       "fetched_at": "2026-06-17"}],
            "audit": {"verdict": "pass", "at": "2026-06-17", "upstream_sha": "abc"},
        })
        self.assert_valid(document)

    def test_reference_only_upstream_record_is_passed_through(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\n")
        record = {"path": "", "url": "https://example.com/spec", "sha256": "", "fetched_at": "2026-07-03"}
        write(directory / "upstream.json", json.dumps({"source": "web", "files": [dict(record, notes="x")]}))
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        self.assertEqual(document["provenance"], {"source": "web", "files": [record]})
        self.assert_valid(document)

    def test_frontmatter_license_wins_over_upstream(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\nlicense: Apache-2.0\n")
        write(directory / "upstream.json", json.dumps({"source": "github", "license": "MIT"}))
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        self.assertEqual(document["license"], "Apache-2.0")
        self.assertEqual(document["provenance"]["license"], "MIT")

    def test_allowed_tools_split_on_spaces(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\nallowed-tools: Read Grep Bash\n")
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        self.assertEqual(document["allowed_tools"], ["Read", "Grep", "Bash"])

    def test_metadata_map_is_read_from_the_block(self):
        directory = make_skill(self.root, (
            "name: demo\ndescription: d\nmetadata:\n  author: Example Author\n  version: \"2026.05.01\"\n"
            "license: MIT\n"))
        document = skill.describe_skill(directory, skill_id="x/demo").to_json()
        self.assertEqual(document["metadata"], {"author": "Example Author", "version": "2026.05.01"})
        self.assertEqual(document["license"], "MIT")
        self.assert_valid(document)

    def test_compatibility_length_is_checked(self):
        ok = make_skill(self.root, "name: demo\ndescription: d\ncompatibility: " + "x" * 500 + "\n", name="ok")
        self.assertEqual(len(skill.describe_skill(ok, skill_id="x/ok").compatibility), 500)
        too_long = make_skill(self.root, "name: demo\ndescription: d\ncompatibility: " + "x" * 501 + "\n", name="long")
        with self.assertRaisesRegex(ValueError, "^SKILL_DESCRIPTOR_INVALID: .*compatibility"):
            skill.describe_skill(too_long, skill_id="x/long")

    def test_missing_name_or_description_is_an_error(self):
        for index, frontmatter in enumerate(("description: d\n", "name: demo\n", "")):
            directory = make_skill(self.root, frontmatter, name=f"bad{index}")
            with self.assertRaisesRegex(ValueError, "^SKILL_DESCRIPTOR_INVALID: .*(name|description) is missing"):
                skill.describe_skill(directory, skill_id="x/bad")

    def test_missing_skill_md_and_broken_upstream_are_errors(self):
        with self.assertRaisesRegex(ValueError, "^SKILL_DESCRIPTOR_INVALID: .*SKILL.md is missing"):
            skill.describe_skill(self.root / "nothing", skill_id="x/nothing")
        directory = make_skill(self.root, "name: demo\ndescription: d\n")
        write(directory / "upstream.json", "{broken")
        with self.assertRaisesRegex(ValueError, "^SKILL_DESCRIPTOR_INVALID: .*upstream.json"):
            skill.describe_skill(directory, skill_id="x/demo")

    def test_digest_matches_the_hash_and_ignores_service_files(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\n")
        digest = skill.describe_skill(directory, skill_id="x/demo").digest
        self.assertEqual(digest, "sha256:" + skill.skill_content_hash(directory))
        write(directory / "upstream.json", json.dumps({"source": "github"}))
        write(directory / "evals" / "case.json", "{}")
        write(directory / "__pycache__" / "x.pyc", "x")
        self.assertEqual(skill.describe_skill(directory, skill_id="x/demo").digest, digest)

    def test_descriptor_is_frozen_and_to_json_does_not_alias(self):
        directory = make_skill(self.root, "name: demo\ndescription: d\nmetadata:\n  a: b\n")
        descriptor = skill.describe_skill(directory, skill_id="x/demo")
        with self.assertRaises(Exception):
            descriptor.name = "other"
        document = descriptor.to_json()
        document["metadata"]["a"] = "changed"
        document["provenance"]["source"] = "changed"
        self.assertEqual(descriptor.metadata, {"a": "b"})
        self.assertEqual(descriptor.provenance, {"source": "local"})


if __name__ == "__main__":
    unittest.main()
