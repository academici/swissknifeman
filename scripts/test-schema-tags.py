#!/usr/bin/env python3
"""Every schema tag literal in package code resolves to a schema ``$id``.

    test-schema-tags.py [--root DIR] [--allow-pending OWNER ...]

The walk is an AST of ``packages/*/lib/**/*.py`` (``_vendor`` excluded):

- a dict key ``schema`` or ``$schema`` whose value is any string literal (a value that is not a document tag is
  listed in ``NON_DOCUMENT_TAGS`` with a reason; every other string must resolve);
- an assignment to a name containing ``SCHEMA`` whose value looks like ``<name>/v<N>`` or ``urn:swissknifeman:``.

The string must be a ``$id`` under ``packages/*/schemas``, ``configs`` or ``bridges``, or an alias in
``configs/schema-tags.json``. ``--allow-pending orch`` prints tags whose alias points at an orch ``$id`` that does not
exist yet and does not fail them (P4.3 creates those schemas). With no arguments this file runs its unittest,
including the repository check.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A document tag is a published short name ``<name>/v<N>`` or a complete versioned URN. Namespace prefixes
# (``urn:swissknifeman:aicore:``) and format templates (``...:{name}:v1``) are not tags.
TAG = re.compile(r"^(?:[a-z0-9.-]+/v\d+|urn:swissknifeman:[a-z0-9-]+(?::[a-z0-9-]+)+:v\d+)$")
SKIP_PARTS = {"_vendor", "tests", "fixtures", "examples", "node_modules"}
# Dict values of ``schema`` / ``$schema`` that are not document tags. U5 collects every such string; these are the
# other uses of the key, each with the reason it is not resolved to a ``$id``.
NON_DOCUMENT_TAGS = {
    "https://json-schema.org/draft/2020-12/schema":
        "dialect identifier of a schema document, not a product document tag",
    "the document is valid contribution/v1":
        "prose for the contribution check id 'schema', not a document tag",
    "read-catalog": "planner catalog nickname of the schema verb, not a document tag",
    "read": "planner catalog mode of the schema verb, not a document tag",
    "https://github.com/academici/swissknifeman/blob/main/SKILL_TEMPLATE.md":
        "skill registry schema field, a template URL, not a document tag",
}


def schema_ids(root: Path) -> set:
    found = set()
    for pattern in ("packages/*/schemas/**/*.schema.json", "packages/*/configs/**/*.schema.json",
                    "configs/**/*.schema.json", "bridges/**/*.schema.json"):
        for path in root.glob(pattern):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            schema_id = document.get("$id") if isinstance(document, dict) else None
            if isinstance(schema_id, str):
                found.add(schema_id)
    return found


def aliases(root: Path) -> dict:
    path = root / "configs" / "schema-tags.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = document.get("aliases") if isinstance(document, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)}


def _string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def literals(path: Path) -> list:
    """``(line, text)`` of the tag literals this file publishes."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if _string(key) in ("schema", "$schema"):
                    text = _string(value)
                    # Every string is a tag candidate. Assignments below stay limited to the tag shape.
                    if text and text not in NON_DOCUMENT_TAGS:
                        found.append((getattr(value, "lineno", node.lineno), text))
        elif isinstance(node, ast.Assign):
            text = _string(node.value)
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if text and TAG.match(text) and any("SCHEMA" in name for name in names):
                found.append((node.lineno, text))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            text = _string(node.value)
            if text and TAG.match(text) and "SCHEMA" in node.target.id:
                found.append((node.lineno, text))
    return found


def python_files(root: Path) -> list:
    found = []
    for path in sorted((root / "packages").glob("*/lib/**/*.py")):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        found.append(path)
    return found


def check(root: Path, pending_owners: set) -> tuple:
    """``(failures, pending)`` as lists of ``path:line: tag`` strings."""
    known = schema_ids(root)
    table = aliases(root)
    failures, pending = [], []
    for path in python_files(root):
        rel = path.relative_to(root).as_posix()
        for line, tag in literals(path):
            if tag in known:
                continue
            target = table.get(tag)
            if target in known:
                continue
            owner = target.split(":")[2] if isinstance(target, str) and target.startswith("urn:swissknifeman:") else ""
            if target and owner in pending_owners:
                pending.append(f"pending: {rel}:{line}: {tag} -> {target}")
                continue
            failures.append(f"{rel}:{line}: {tag}" + (f" -> {target} (missing)" if target else " (unknown)"))
    return failures, pending


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Resolve schema tag literals to schema $ids.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allow-pending", action="append", default=[], metavar="OWNER",
                        help="owner whose not-yet-existing $ids are pending rather than failures (repeatable)")
    args = parser.parse_args(argv)
    failures, pending = check(args.root.resolve(), set(args.allow_pending))
    for line in pending:
        print(line)
    for line in failures:
        print(line, file=sys.stderr)
    if failures:
        print(f"schema-tags: {len(failures)} unresolved, {len(pending)} pending", file=sys.stderr)
        return 1
    print(f"schema-tags: ok ({len(pending)} pending)")
    return 0


class SchemaTagTests(unittest.TestCase):
    def write(self, root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_an_unknown_tag_fails_and_an_alias_passes(self):
        root = Path(tempfile.mkdtemp(prefix="skm-tags-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        self.write(root, "configs/schema-tags.json", json.dumps({"aliases": {
            "known/v1": "urn:swissknifeman:demo:known:v1"}}))
        self.write(root, "packages/demo/schemas/known/v1/known.schema.json", json.dumps({
            "$id": "urn:swissknifeman:demo:known:v1"}))
        self.write(root, "packages/demo/lib/demo/tags.py", textwrap.dedent("""\
            KNOWN_SCHEMA = "known/v1"
            OTHER_SCHEMA = "missing/v1"
            def build():
                return {"schema": "known/v1", "$schema": "urn:swissknifeman:demo:known:v1"}
        """))
        failures, pending = check(root, set())
        self.assertEqual(pending, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("missing/v1", failures[0])

    def test_allow_pending_orch_prints_and_does_not_fail(self):
        root = Path(tempfile.mkdtemp(prefix="skm-tags-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        target = "urn:swissknifeman:orch:records:provider-gates:v1"
        self.write(root, "configs/schema-tags.json", json.dumps({"aliases": {"provider-gates/v1": target}}))
        self.write(root, "packages/orch/lib/orch/gates.py", 'SCHEMA = "provider-gates/v1"\n')
        code = main(["--root", str(root), "--allow-pending", "orch"])
        self.assertEqual(code, 0)

    def test_repository_tags_resolve_with_none_pending(self):
        # orch records/v1 (P4.3, P4.9) holds the $ids of the five published short tags: nothing is pending any more
        failures, pending = check(ROOT, set())
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertEqual(pending, [])
        tags = aliases(ROOT)
        ids = schema_ids(ROOT)
        for short in ("provider-gates/v1", "orch-conductor-observer/v1", "orch-conductor-review-verdict/v1",
                      "prompt-diff/v1", "orch-conformance/v1"):
            self.assertIn(tags[short], ids, short)

    def test_a_schema_string_outside_the_tag_pattern_is_reported(self):
        for value, reason in NON_DOCUMENT_TAGS.items():
            self.assertTrue(str(reason).strip(), value)
            self.assertIsNone(TAG.match(value), value)
        root = Path(tempfile.mkdtemp(prefix="skm-tags-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        self.write(root, "packages/demo/lib/demo/tags.py", textwrap.dedent("""\
            PREFIX_SCHEMA = "urn:swissknifeman:demo:"
            DIALECT = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
            def build():
                return {"schema": "not-a-tag", "$schema": "urn:swissknifeman:demo:note"}
        """))
        failures, pending = check(root, set())
        self.assertEqual(pending, [])
        joined = "\n".join(failures)
        self.assertIn("not-a-tag", joined)
        self.assertIn("urn:swissknifeman:demo:note", joined)
        self.assertNotIn("draft/2020-12", joined)
        self.assertFalse(any(line.endswith("urn:swissknifeman:demo: (unknown)") for line in failures), failures)
        self.assertEqual(len(failures), 2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(main())
    unittest.main()
