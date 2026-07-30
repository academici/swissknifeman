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


def snapshot(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


class ProviderDocsTests(unittest.TestCase):
    def test_independent_exact_set_matrix_and_production_requirements_are_green(self):
        report = provider_docs.conformance(ROOT)
        self.assertTrue(report["green"], json.dumps(report, indent=2))
        for key in ("missing", "extra", "duplicates", "matrix_missing", "matrix_extra",
                    "requirement_failures", "native_extensions",
                    "analytics_contract_missing_sections"):
            self.assertEqual(report[key], [])
        self.assertEqual(report["canonical_sha256"],
                         "2b96cd63ae049827e47708dc41c7c5a704069595b0d1aec5465b318201d30c6f")
        self.assertEqual(report["carrier_sha256"],
                         "c9c1d0137433d74373e3872f5b730da1565504c1caa48de1b2fc8034b3849718")
        self.assertTrue(report["carrier_terminal_lf"])
        self.assertEqual(sum(len(values) for values in report["contributors"].values()), 35)
        self.assertEqual(len(set().union(*map(set, report["contributors"].values()))), 35)
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
            (root / "packages/task/configs").mkdir(parents=True)
            (root / "packages/harness/configs/common/instructions").mkdir(parents=True)
            (root / "plans/2026.07.19-DUAL-PROVIDER/root/contracts").mkdir(parents=True)
            # The generator intentionally consumes these bounded sources; copy exact fixtures.
            # The analytics contract's SOURCE path resolves via `resolve_plan_dir` (live or
            # archived); the FIXTURE tree always uses the live layout (D91/D95 scope: the
            # resolver is the fix, this fixture just exercises the reader against it).
            plan_dir = provider_docs.resolve_plan_dir(ROOT, "2026.07.19-DUAL-PROVIDER")
            for relative in (
                "configs/provider-capabilities.json",
                "packages/task/configs/command-routing.json",
                "packages/harness/configs/common/profile-catalog.json",
                "packages/harness/configs/common/instructions/catalog.json",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            (root / "plans/2026.07.19-DUAL-PROVIDER/root/contracts/"
             "provider-analytics-contract.md").write_bytes(
                (plan_dir / "root/contracts/provider-analytics-contract.md").read_bytes())
            prefix = b"# Fixture\n\n## \xd0\x92\xd0\xbe\xd0\xb7\xd0\xbc\xd0\xbe\xd0\xb6\xd0\xbd\xd0\xbe\xd1\x81\xd1\x82\xd0\xb8\n\nforeign before\n\n"
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

    def test_internal_markdown_links_resolve_and_examples_keep_provider_syntax_separate(self):
        readme = provider_docs.expected_outputs(ROOT)[ROOT / "README.md"].decode()
        guide = provider_docs.expected_outputs(ROOT)[ROOT / "docs/provider-support.md"].decode()
        self.assertIn("Claude Code: /task:fix <brief>", guide)
        self.assertIn("Codex:       $ task:fix <brief>", guide)
        self.assertNotIn("Codex:       /task:", guide)
        self.assertIn("Full access is never a project or fleet default", guide)
        import re
        for source_path, text in ((ROOT / "README.md", readme),
                                  (ROOT / "docs/provider-support.md", guide)):
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (source_path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.exists(), f"broken link {target} in {source_path}")


if __name__ == "__main__":
    unittest.main()
