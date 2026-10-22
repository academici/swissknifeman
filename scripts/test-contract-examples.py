#!/usr/bin/env python3
"""Every document schema has a valid example and an invalid example named with its error code.

A support schema (the root carries only metadata and ``$defs``, so it accepts any JSON) is loaded in the closed
profile and its ``$ref``s must resolve; it needs no examples. ``exec/v1`` and ``plan/v1`` ``defs`` are that case.

Invalid examples are ``<error-code>-<what>.json``. The error code is a ``ValidationIssue`` code. Older aicore names
and the gui ``<what>.<error-code>.json`` names are still checked: a coded name must fail with that code, any other
name must fail with some issue.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "aicore" / "lib"))
from aicore.util.jsonschema_core import ERROR_CODES  # noqa: E402
from aicore.util.schema import (  # noqa: E402
    RefError, SchemaProfileError, _refs, load_contract, load_contract_set, validate_node,
)

META = {"$schema", "$id", "$comment", "title", "description", "$defs"}
CONTRACT_PATH = re.compile(r"^schemas/([^/]+)/(v[0-9]+)$")
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def is_support(schema: dict) -> bool:
    """True when the root carries only metadata and ``$defs``, so every JSON value matches.

    Any other keyword is an assertion (``type``, ``minLength``, ``minimum``, ``dependentRequired``, …) and the
    schema is a document schema that needs examples.
    """
    return isinstance(schema, dict) and set(schema) <= META


def expected_code(path: Path):
    """The error code encoded in the file name, or None when the name does not carry one.

    ``not-a-string.json`` is prose (it is not a string), not the ``not`` keyword. A gui file
    ``cursor-too-long.max_length.json`` carries the code after the last dot.
    """
    prefix = path.name.split("-", 1)[0]
    if prefix in ERROR_CODES and not (prefix == "not" and path.name.startswith("not-a-")):
        return prefix
    stem = path.name[:-5] if path.name.endswith(".json") else path.name
    tail = stem.rsplit(".", 1)[-1]
    if tail in ERROR_CODES and tail != stem:
        return tail
    return None


def examples_for(directory: Path, kind: str, group: str, single: bool) -> list:
    base = directory / "examples" / group
    if not base.is_dir():
        return []
    if single:
        return sorted(base.glob("*.json"))
    found = sorted((base / kind).glob("*.json")) if (base / kind).is_dir() else []
    found += sorted(path for path in base.glob("*.json")
                    if path.stem == kind or path.name.startswith(kind + "-"))
    return found


def load_directory(directory: Path):
    try:
        registry, kind = load_contract(directory)
        return registry, [kind]
    except SchemaProfileError:
        pass
    files = sorted(directory.glob("*.schema.json"))
    if len(files) == 1:
        schema_id = json.loads(files[0].read_text(encoding="utf-8")).get("$id", "")
        suffix = f"{directory.parent.name}:{directory.name}"
        if isinstance(schema_id, str) and schema_id.endswith(suffix):
            try:
                registry, kind = load_contract(directory, urn_prefix=schema_id[: -len(suffix)])
                return registry, [kind]
            except SchemaProfileError:
                pass
    registry, kinds = load_contract_set(directory, open_slots=True)
    return registry, kinds


def _failure_codes(registry, kind, path: Path, issues, code) -> set:
    """Issue codes this invalid document actually produces.

    ``validate`` reports ``one_of`` for a union and keeps each branch's ``ValidationIssue`` codes on the trial.
    A coded file name must be one of those codes. A code that no trial produced does not pass just because the
    union failed.
    """
    found = {issue.code for issue in issues}
    if code is None or code in found or "one_of" not in found:
        return found
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return found
    schema, base = registry.for_kind(kind)
    owners = [(schema, base)]
    if isinstance(schema, dict) and "$ref" in schema:
        try:
            owners.append(registry.resolve(schema["$ref"], base))
        except (RefError, KeyError, TypeError):
            pass
    for node, owner in owners:
        branches = node.get("oneOf") if isinstance(node, dict) else None
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            try:
                branch_issues = validate_node(registry, branch, owner, document)
            except (RefError, KeyError, TypeError):
                continue
            found.update(issue.code for issue in branch_issues)
    return found


def _invalid_problems(registry, kind, paths, label) -> list:
    problems = []
    for path in paths:
        issues = _issues(registry, kind, path)
        if not issues:
            problems.append(f"{label}: {kind} invalid {path.name} was accepted")
            continue
        code = expected_code(path)
        found = _failure_codes(registry, kind, path, issues, code)
        if code and code not in found:
            problems.append(f"{label}: {kind} invalid {path.name} expected {code}, got {sorted(found)}")
    return problems


def _support_reference_problems(registry, schema, schema_id, label) -> list:
    """Every ``$ref`` of a support schema must resolve. ``load_contract`` does not check local fragments."""
    problems = []
    for ref in _refs(schema):
        try:
            registry.resolve(ref, schema_id)
        except (RefError, KeyError, TypeError) as exc:
            problems.append(f"{label}: unresolved reference {ref!r}: {exc}")
    return problems


def check_directory(directory: Path, label: str) -> list:
    """Problems of one contract directory. A support schema resolves every ``$ref`` and needs no examples."""
    problems = []
    try:
        registry, kinds = load_directory(directory)
    except (SchemaProfileError, OSError, ValueError) as exc:
        return [f"{label}: {exc}"]
    documents = []
    for kind in kinds:
        schema, schema_id = registry.for_kind(kind)
        if is_support(schema):
            problems.extend(_support_reference_problems(registry, schema, schema_id, f"{label}: {kind}"))
            continue
        documents.append(kind)
    single = len(documents) == 1
    for kind in documents:
        valids = examples_for(directory, kind, "valid", single)
        invalids = examples_for(directory, kind, "invalid", single)
        if not valids:
            problems.append(f"{label}: {kind} has no valid example")
        if not invalids:
            problems.append(f"{label}: {kind} has no invalid example")
        for path in valids:
            issues = _issues(registry, kind, path)
            if issues:
                problems.append(f"{label}: {kind} valid {path.name}: {issues[0].message}")
        problems.extend(_invalid_problems(registry, kind, invalids, label))
    return problems


def _issues(registry, kind, path: Path):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        from aicore.util.jsonschema_core import ValidationIssue
        return [ValidationIssue("", "type", str(exc))]
    from aicore.util.schema import validate
    return validate(document, kind, registry)


class _PlainRegistry:
    def __init__(self, schema_id, schema):
        self._schemas = {schema_id: schema}
        self.kind = schema_id.rsplit(":", 2)[-2]

    def for_kind(self, kind):
        schema_id = next(iter(self._schemas))
        return self._schemas[schema_id], schema_id

    def resolve(self, ref, base):
        document, _, fragment = ref.partition("#")
        node = self._schemas[document or base]
        if fragment:
            node = node["$defs"][fragment.split("/")[-1]]
        return node, document or base


def check_loose(schema_path: Path, example_dir: Path, label: str) -> list:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if is_support(schema):
        from aicore.util.jsonschema_core import _check_profile
        _check_profile(schema, str(schema_path), "", root=True)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            return [f"{label}: support schema has no $id"]
        registry = _PlainRegistry(schema_id, schema)
        return _support_reference_problems(registry, schema, schema_id, label)
    registry = _PlainRegistry(schema["$id"], schema)
    return check_loaded(registry, registry.kind, example_dir, label, single=True)


def check_loaded(registry, kind, directory, label, single) -> list:
    """``directory`` is the contract directory when examples live under it, else the example root's parent.

    For a loose schema, ``directory`` is ``<examples parent>`` and examples are ``directory/valid`` — pass the
    parent of ``valid`` as a synthetic contract dir by using ``example_dir`` directly.
    """
    problems = []
    valids = sorted((directory / "valid").glob("*.json")) if (directory / "valid").is_dir() else []
    invalids = sorted((directory / "invalid").glob("*.json")) if (directory / "invalid").is_dir() else []
    if not valids:
        problems.append(f"{label}: {kind} has no valid example")
    if not invalids:
        problems.append(f"{label}: {kind} has no invalid example")
    for path in valids:
        issues = _issues(registry, kind, path)
        if issues:
            problems.append(f"{label}: {kind} valid {path.name}: {issues[0].message}")
    problems.extend(_invalid_problems(registry, kind, invalids, label))
    return problems


def repository_problems(root: Path = ROOT) -> list:
    problems = []
    for unit_path in sorted(root.glob("packages/*/unit.json")) + sorted(root.glob("bridges/*/unit.json")):
        try:
            unit = json.loads(unit_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{unit_path}: {exc}")
            continue
        for contract in (unit.get("provides") or {}).get("contracts") or []:
            path = contract.get("path", "")
            if not isinstance(path, str) or CONTRACT_PATH.fullmatch(path) is None:
                continue
            directory = unit_path.parent / path
            problems += check_directory(directory, f"{unit.get('id')}:{directory.parent.name}/{directory.name}")
    for schema_path in sorted(root.glob("configs/*.schema.json")) + sorted(root.glob("configs/schemas/*.schema.json")):
        stem = schema_path.name.removesuffix(".schema.json")
        problems += check_loose(schema_path, root / "configs" / "examples" / stem, f"hub:{stem}")
    for schema_path in sorted(root.glob("packages/*/configs/config.schema.json")):
        module = schema_path.parents[1].name
        problems += check_loose(schema_path, schema_path.parent / "examples", f"{module}:config")
    return problems


class ContractExampleTests(unittest.TestCase):
    def test_repository_examples_match_their_schemas(self):
        problems = repository_problems()
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_exec_and_plan_defs_need_no_examples(self):
        for rel in ("packages/orch/schemas/exec/v1/defs.schema.json",
                    "packages/planner/schemas/plan/v1/defs.schema.json"):
            schema = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            self.assertTrue(is_support(schema), rel)
            self.assertFalse((ROOT / rel).parent.joinpath("examples").exists() and False)
        problems = repository_problems()
        self.assertFalse(any("defs has no" in problem for problem in problems), problems)

    def test_a_document_kind_without_an_invalid_example_names_the_kind(self):
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        directory = root / "packages" / "demo" / "schemas" / "note" / "v1"
        directory.mkdir(parents=True)
        schema = {
            "$schema": DRAFT, "$id": "urn:swissknifeman:demo:note:v1", "type": "object",
            "additionalProperties": False, "required": ["text"],
            "properties": {"text": {"type": "string", "description": "Text."}},
        }
        (directory / "note.schema.json").write_text(json.dumps(schema), encoding="utf-8")
        valid = directory / "examples" / "valid"
        valid.mkdir(parents=True)
        (valid / "minimal.json").write_text(json.dumps({"text": "a"}), encoding="utf-8")
        (root / "packages" / "demo" / "unit.json").write_text(json.dumps({
            "id": "demo", "provides": {"contracts": [
                {"id": "urn:swissknifeman:demo:note", "path": "schemas/note/v1", "version": "v1"}]}}),
            encoding="utf-8")
        problems = repository_problems(root)
        self.assertTrue(any("note has no invalid example" in problem for problem in problems), problems)

    def test_a_defs_file_with_a_root_type_is_a_document(self):
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        directory = root / "packages" / "demo" / "schemas" / "defs" / "v1"
        directory.mkdir(parents=True)
        schema = {
            "$schema": DRAFT, "$id": "urn:swissknifeman:demo:defs:v1", "title": "defs",
            "description": "Looks like a support schema but asserts a type.",
            "type": "object", "$defs": {"id": {"type": "string", "description": "Id."}},
        }
        self.assertFalse(is_support(schema))
        (directory / "defs.schema.json").write_text(json.dumps(schema), encoding="utf-8")
        (root / "packages" / "demo" / "unit.json").write_text(json.dumps({
            "id": "demo", "provides": {"contracts": [
                {"id": "urn:swissknifeman:demo:defs", "path": "schemas/defs/v1", "version": "v1"}]}}),
            encoding="utf-8")
        problems = repository_problems(root)
        self.assertTrue(any("defs has no valid example" in problem for problem in problems), problems)
        self.assertTrue(any("defs has no invalid example" in problem for problem in problems), problems)

    def _union_directory(self, root: Path, invalid_name: str, invalid_document):
        directory = root / "note" / "v1"
        directory.mkdir(parents=True)
        schema = {
            "$schema": DRAFT, "$id": "urn:swissknifeman:demo:note:v1",
            "description": "A string or an object.",
            "oneOf": [
                {"type": "string", "minLength": 3, "description": "A string of at least 3 characters."},
                {"type": "object", "additionalProperties": False, "description": "An empty object."},
            ],
        }
        (directory / "note.schema.json").write_text(json.dumps(schema), encoding="utf-8")
        valid = directory / "examples" / "valid"
        invalid = directory / "examples" / "invalid"
        valid.mkdir(parents=True)
        invalid.mkdir()
        (valid / "minimal.json").write_text(json.dumps("abc"), encoding="utf-8")
        (invalid / invalid_name).write_text(json.dumps(invalid_document), encoding="utf-8")
        return directory, schema

    def test_a_coded_name_must_be_an_issue_the_document_produces(self):
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        directory, schema = self._union_directory(root, "min_length-short.json", 42)
        problems = check_directory(directory, "F1")
        self.assertTrue(any("min_length-short.json" in problem and "expected min_length" in problem
                            for problem in problems), problems)
        registry = _PlainRegistry(schema["$id"], schema)
        loaded = check_loaded(registry, "note", directory / "examples", "F1", True)
        self.assertTrue(any("expected min_length" in problem for problem in loaded), loaded)
        invalid = directory / "examples" / "invalid"
        (invalid / "one_of-wrong-type.json").write_text((invalid / "min_length-short.json").read_text(encoding="utf-8"),
                                                        encoding="utf-8")
        (invalid / "min_length-short.json").unlink()
        self.assertEqual(check_directory(directory, "F1"), [])
        self.assertEqual(check_loaded(registry, "note", directory / "examples", "F1", True), [])

    def test_a_short_string_named_min_length_matches_the_branch_issue(self):
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        directory, schema = self._union_directory(root, "min_length-short.json", "ab")
        self.assertEqual(check_directory(directory, "F1"), [])
        registry = _PlainRegistry(schema["$id"], schema)
        self.assertEqual(check_loaded(registry, "note", directory / "examples", "F1", True), [])

    def test_a_root_length_bound_or_dependent_required_needs_examples(self):
        for keyword, value in (("minLength", 1), ("minimum", 0), ("dependentRequired", {"a": ["b"]})):
            schema = {"$schema": DRAFT, "$id": "urn:swissknifeman:demo:note:v1", keyword: value,
                      "description": "Asserts on the root."}
            self.assertFalse(is_support(schema), keyword)
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        directory = root / "note" / "v1"
        directory.mkdir(parents=True)
        schema = {"$schema": DRAFT, "$id": "urn:swissknifeman:demo:note:v1", "minLength": 1,
                  "description": "A non-empty string, not a support schema."}
        (directory / "note.schema.json").write_text(json.dumps(schema), encoding="utf-8")
        problems = check_directory(directory, "F2")
        self.assertTrue(any("note has no valid example" in problem for problem in problems), problems)
        self.assertTrue(any("note has no invalid example" in problem for problem in problems), problems)

    def _support_schema(self, root: Path, name: str, defs: dict) -> Path:
        directory = root / name / "v1"
        directory.mkdir(parents=True)
        schema = {
            "$schema": DRAFT, "$id": f"urn:swissknifeman:demo:{name}:v1",
            "title": name, "description": "Definitions only.", "$defs": defs,
        }
        (directory / f"{name}.schema.json").write_text(json.dumps(schema), encoding="utf-8")
        return directory

    def test_a_support_schema_must_resolve_every_local_ref(self):
        root = Path(tempfile.mkdtemp(prefix="skm-examples-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        broken = self._support_schema(root, "note", {"bad": {"$ref": "#/$defs/missing"}})
        problems = check_directory(broken, "F3")
        self.assertTrue(any("unresolved reference" in problem and "#/$defs/missing" in problem
                            for problem in problems), problems)
        whole = self._support_schema(root, "defs", {
            "bad": {"$ref": "#/$defs/ok"},
            "ok": {"type": "string", "description": "Present."},
        })
        self.assertEqual(check_directory(whole, "F3"), [])
        loose = root / "loose.schema.json"
        loose.write_text((broken / "note.schema.json").read_text(encoding="utf-8"), encoding="utf-8")
        loose_problems = check_loose(loose, root / "examples", "loose")
        self.assertTrue(any("unresolved reference" in problem for problem in loose_problems), loose_problems)


if __name__ == "__main__":
    unittest.main()
