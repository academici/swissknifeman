#!/usr/bin/env python3
"""P7.1 provider manifest/docs conformance tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("provider_docs", ROOT / "scripts/provider-docs.py")
provider_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider_docs)

MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "test_provider_manifest", ROOT / "packages/aicore/tests/provider/test_manifest.py")
manifest_snapshot = importlib.util.module_from_spec(MANIFEST_SPEC)
MANIFEST_SPEC.loader.exec_module(manifest_snapshot)


def snapshot(root):
    """Hash repository artifacts only, excluding live VCS and maind runtime state."""
    excluded = (root / ".git", root / "packages/maind/data")
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
            and "__pycache__" not in path.relative_to(root).parts
            and not any(path.is_relative_to(directory) for directory in excluded)}


class ProviderDocsTests(unittest.TestCase):
    def test_independent_exact_set_matrix_and_production_requirements_are_green(self):
        report = provider_docs.conformance(ROOT)
        self.assertTrue(report["green"], json.dumps(report, indent=2))
        for key in ("missing", "extra", "duplicates", "matrix_missing", "matrix_extra",
                    "requirement_failures", "native_extensions"):
            self.assertEqual(report[key], [])
        self.assertEqual(report["canonical_sha256"],
                         manifest_snapshot.APPROVED_CANONICAL_SHA256,
                         manifest_snapshot.REGENERATION_DIAGNOSTIC)
        self.assertEqual(report["carrier_sha256"],
                         manifest_snapshot.APPROVED_CARRIER_SHA256,
                         manifest_snapshot.REGENERATION_DIAGNOSTIC)
        self.assertTrue(report["carrier_terminal_lf"])
        self.assertEqual(sum(len(values) for values in report["contributors"].values()), 38)
        self.assertEqual(len(set().union(*map(set, report["contributors"].values()))), 38)
        self.assertTrue(report["requirements"])

    def test_committed_outputs_are_exact_and_check_is_no_write(self):
        expected = provider_docs.expected_outputs(ROOT)
        self.assertEqual({path: path.read_bytes() for path in expected}, expected)
        before = snapshot(ROOT)
        self.assertEqual(provider_docs.run("check", ROOT), 0)
        self.assertEqual(snapshot(ROOT), before)

    def test_write_preserves_bytes_outside_readme_markers_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs").mkdir()
            (root / "docs").mkdir()
            (root / "packages/planner/configs").mkdir(parents=True)
            (root / "packages/harness/configs/common/instructions").mkdir(parents=True)
            # The generator intentionally consumes these bounded sources; copy exact fixtures.
            for relative in (
                "packages/aicore/configs/provider-capabilities.json",
                "packages/planner/configs/command-routing.json",
                "packages/harness/configs/common/profile-catalog.json",
                "packages/harness/configs/common/instructions/catalog.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            prefix = b"# Fixture\n\n## Features\n\nforeign before\n\n"
            suffix = b"\nforeign after\n"
            (root / "README.md").write_bytes(prefix + suffix)
            self.assertEqual(provider_docs.run("write", root), 0)
            first = (root / "README.md").read_bytes()
            start = first.index(provider_docs.BEGIN.encode())
            finish = first.index(provider_docs.END.encode()) + len(provider_docs.END)
            self.assertEqual(first[:start] + first[finish + 2:], prefix + suffix)
            self.assertEqual(provider_docs.run("write", root), 0)
            self.assertEqual((root / "README.md").read_bytes(), first)
            self.assertEqual(provider_docs.run("check", root), 0)

    def test_manifest_is_not_an_output_of_the_generator(self):
        # packages/aicore/configs/provider-capabilities.json is the generator's INPUT (P5.2, D-provenance):
        # a hand-written SSOT with no owning generator, so `root.generated-artifacts`
        # ("regenerate through the owning tool") does not apply to it. This is a structural
        # assertion about expected_outputs(), not a text-presence check.
        expected = provider_docs.expected_outputs(ROOT)
        self.assertNotIn(ROOT / "packages/aicore/configs/provider-capabilities.json", expected)
        guide = expected[ROOT / "docs/provider-support.md"].decode()
        self.assertIn("no generator", guide)
        self.assertIn("root.generated-artifacts", guide)

    def test_internal_markdown_links_resolve_and_examples_keep_provider_syntax_separate(self):
        readme = provider_docs.expected_outputs(ROOT)[ROOT / "README.md"].decode()
        guide = provider_docs.expected_outputs(ROOT)[ROOT / "docs/provider-support.md"].decode()
        self.assertIn("Claude Code: /planner:fix <brief>", guide)
        self.assertIn("Codex:       $ planner:fix <brief>", guide)
        self.assertNotIn("Codex:       /planner:", guide)
        self.assertIn("Full access is never a project or fleet default", guide)
        import re
        for source_path, text in ((ROOT / "README.md", readme),
                                  (ROOT / "docs/provider-support.md", guide)):
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (source_path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.exists(), f"broken link {target} in {source_path}")

    def test_evidence_placeholders_do_not_become_html_tags(self):
        guide = provider_docs.expected_outputs(ROOT)[ROOT / "docs/provider-support.md"].decode()
        self.assertIn(".codex/state/&lt;session&gt;.tools.jsonl", guide)
        self.assertIn(".cursor/state/&lt;conversation&gt;.tools.jsonl", guide)


if __name__ == "__main__":
    unittest.main()
