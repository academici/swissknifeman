#!/usr/bin/env python3
"""Consumer-driven check of event data contracts: the fixtures of every module against the schemas of the producer.

A module that declares ``provides.events`` and publishes ``schemas/event-data/v1/<type>.schema.json`` owns the data
contract of those types. Every ``packages/*/tests/fixtures/events/<type>/valid-*.json`` of any module must be a valid
``event/v1`` envelope and its ``data`` must satisfy the schema of the producer; ``valid-additive*`` fixtures are
checked as envelopes only (a consumer ignores unknown fields). A mismatch is fixed where the schema of the producer
is right, usually in the consumer's fixture.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
sys.path.insert(0, str(PACKAGES / "aicore" / "lib"))

from aicore.ext import events  # noqa: E402
from aicore.util import schema  # noqa: E402

SCHEMA_DIR = Path("schemas") / "event-data" / "v1"
FOUNDATION_CONTRACTS = ("artifact-ref", "digest", "common")  # contracts the data schemas may reference


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def producers() -> dict:
    """``{event type: (module id, schema file)}`` of every module that publishes event data schemas."""
    found = {}
    for unit_file in sorted(PACKAGES.glob("*/unit.json")):
        module = unit_file.parent
        if not (module / SCHEMA_DIR).is_dir():
            continue
        for event_type in load_json(unit_file).get("provides", {}).get("events", []):
            found[event_type] = (module.name, module / SCHEMA_DIR / f"{event_type}.schema.json")
    return found


def registry(module: str, event_type_names: list):
    directory = PACKAGES / module / SCHEMA_DIR
    unit = load_json(PACKAGES / module / "unit.json")
    contract = next(c for c in unit["provides"]["contracts"] if c["path"] == SCHEMA_DIR.as_posix())
    extras = tuple(PACKAGES / "aicore" / "schemas" / name / "v1" for name in FOUNDATION_CONTRACTS)
    return schema.load_registry(directory, urn_prefix=contract["id"] + ":", kinds=tuple(event_type_names),
                                extra_dirs=extras)


def kind_of(event_type: str) -> str:
    """The kind of the schema ``$id`` of a type: its dots become hyphens."""
    return event_type.replace(".", "-")


def fixtures() -> list:
    """``(event type, file)`` of every ``valid-*.json`` fixture of every module."""
    return [(path.parent.name, path) for path in sorted(PACKAGES.glob("*/tests/fixtures/events/*/valid-*.json"))]


class ProducerSchemaTests(unittest.TestCase):
    def test_every_declared_type_of_a_publishing_module_has_a_schema_and_no_schema_is_stray(self):
        for unit_file in sorted(PACKAGES.glob("*/unit.json")):
            module = unit_file.parent
            if not (module / SCHEMA_DIR).is_dir():
                continue
            declared = set(load_json(unit_file).get("provides", {}).get("events", []))
            published = {p.name[:-len(".schema.json")] for p in (module / SCHEMA_DIR).glob("*.schema.json")}
            self.assertEqual(declared, published, f"{module.name}: provides.events and {SCHEMA_DIR} disagree")

    def test_schemas_load_and_carry_the_id_of_their_type(self):
        by_module = {}
        for event_type, (module, path) in producers().items():
            by_module.setdefault(module, []).append(event_type)
            self.assertEqual(load_json(path)["$id"].rsplit(":", 2)[1], kind_of(event_type), path.name)
        for module, types in by_module.items():
            reg = registry(module, [kind_of(t) for t in types])
            for event_type in types:
                reg.for_kind(kind_of(event_type))


class FixtureTests(unittest.TestCase):
    def test_there_are_fixtures_to_check(self):
        self.assertTrue(fixtures())

    def test_every_valid_fixture_matches_the_schema_of_its_producer(self):
        owners = producers()
        registries = {}
        for event_type, path in fixtures():
            name = f"{path.relative_to(ROOT)}"
            with self.subTest(fixture=name):
                self.assertIn(event_type, owners, f"{name}: no module declares {event_type} with a data schema")
                doc = load_json(path)
                self.assertEqual(events.validate_document(doc), [], f"{name}: not a valid event/v1 envelope")
                self.assertEqual(doc.get("type"), event_type, f"{name}: type differs from its folder")
                if path.name.startswith("valid-additive"):
                    continue
                module = owners[event_type][0]
                if module not in registries:
                    types = [kind_of(t) for t, (m, _) in owners.items() if m == module]
                    registries[module] = registry(module, types)
                issues = schema.validate(doc.get("data"), kind_of(event_type), registries[module])
                self.assertEqual([], [f"{i.path or '/'} {i.code}: {i.message}" for i in issues],
                                 f"{name}: data breaks the schema of {owners[event_type][0]}")


if __name__ == "__main__":
    unittest.main()
