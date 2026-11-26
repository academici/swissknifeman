#!/usr/bin/env python3
"""Consumer-driven check of event data contracts: the fixtures of every module against the schemas of the producer.

A module that declares ``provides.events`` and publishes ``schemas/event-data/v1/<type>.schema.json`` owns the data
contract of those types. Every ``packages/*/tests/fixtures/events/<type>/valid-*.json`` of any module must be a valid
``event/v1`` envelope and its ``data`` must satisfy the schema of the producer; ``valid-additive*`` fixtures are
checked as envelopes only (a consumer ignores unknown fields). A mismatch is fixed where the schema of the producer
is right, usually in the consumer's fixture.

The other side is checked too: every event type a module emits (found in its source by ``emitted_types``) must be
declared in its ``provides.events`` and have a data schema, so an emitter cannot start sending a type nobody described.
``aicore events emit`` (``packages/aicore/lib/aicore/ext/cli.py``) sends arbitrary types by design and is left out.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
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
    first = load_json(next(iter(sorted(directory.glob("*.schema.json")))))["$id"]
    extras = tuple(PACKAGES / "aicore" / "schemas" / name / "v1" for name in FOUNDATION_CONTRACTS)
    return schema.load_registry(directory, urn_prefix=first.rsplit(":", 2)[0] + ":", kinds=tuple(event_type_names),
                                extra_dirs=extras)


ARBITRARY_EMITTERS = ("packages/aicore/lib/aicore/ext/cli.py",)  # relative to the repository root
EMIT_CALLEE = re.compile(r"emit|event", re.IGNORECASE)


def _constants(tree: ast.Module) -> dict:
    """``{name: text}`` of the module-level string constants and ``{name: [text, ...]}`` of dicts of strings."""
    found: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, str):
                found[node.targets[0].id] = value
            elif isinstance(value, dict) and all(isinstance(item, str) for item in value.values()):
                found[node.targets[0].id] = sorted(set(value.values()))
    return found


def _aliases(tree: ast.Module) -> set:
    """Local names that stand for an emitter imported under another name: ``from aicore.ext import emit as publish``
    (any module, wrappers included) gives ``publish``. Names that already say emit or event need no alias."""
    return {item.asname for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for item in node.names
            if item.asname and EMIT_CALLEE.search(item.name)}


def _callee(call: ast.Call) -> str:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def _resolve(node: ast.expr, constants: dict) -> list:
    """The event type texts a call argument stands for: a literal, a module constant, or an f-string ``prefix{x}``
    whose placeholder is one of the dicts of strings of the module (``gui.run.{verb}`` over ``_VERBS``)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name) and isinstance(constants.get(node.id), str):
        return [constants[node.id]]
    if isinstance(node, ast.JoinedStr) and len(node.values) == 2:
        head, hole = node.values
        if isinstance(head, ast.Constant) and isinstance(hole, ast.FormattedValue):
            options = [value for value in constants.values() if isinstance(value, list)]
            return [head.value + option for values in options for option in values] if len(options) == 1 else []
    return []


def emitted_types(lib_dir: Path, module: str, root: Path = ROOT) -> dict:
    """``{event type: [file:line]}`` of the types of ``module`` that the sources under ``lib_dir`` emit.

    A type is a string (literal, module constant or ``prefix{verb}`` f-string) that starts with ``<module>.`` and is
    an argument of a call whose name has ``emit`` or ``event`` in it (``emit``, ``_emit``, ``emit_all``,
    ``_beacon_event``, ``self.emit``, or any name an emitter is imported as: ``from aicore.ext import emit as publish``),
    or the first item of a ``(type, data)`` pair (how the planner engine collects
    its events). Anything else is not an emission.
    """
    shape = re.compile(rf"^{re.escape(module)}(\.[a-z][a-z0-9_-]*){{2,}}$")
    found: dict = {}
    for path in sorted(Path(lib_dir).rglob("*.py")):
        inside = path.is_relative_to(root)
        if inside and path.relative_to(root).as_posix() in ARBITRARY_EMITTERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _constants(tree)
        aliases = _aliases(tree)
        for node in ast.walk(tree):
            candidates = []
            if isinstance(node, ast.Call) and (EMIT_CALLEE.search(_callee(node)) or _callee(node) in aliases):
                candidates = list(node.args) + [keyword.value for keyword in node.keywords]
            elif isinstance(node, ast.Tuple) and len(node.elts) == 2 and isinstance(node.elts[1], (ast.Dict, ast.Call)):
                candidates = node.elts[:1]
            for argument in candidates:
                for text in _resolve(argument, constants):
                    if shape.match(text):
                        place = path.relative_to(root).as_posix() if inside else path.name
                        found.setdefault(text, []).append(f"{place}:{node.lineno}")
    return found


def undeclared(lib_dir: Path, module_dir: Path, declared: set) -> list:
    """Problems of the types ``module_dir`` emits: not in ``declared`` (``provides.events``) or without a data schema."""
    rows = []
    for event_type, places in sorted(emitted_types(lib_dir, module_dir.name).items()):
        if event_type not in declared:
            rows.append(f"{event_type} ({places[0]}): emitted but not in provides.events of {module_dir.name}")
        elif not (module_dir / SCHEMA_DIR / f"{event_type}.schema.json").is_file():
            rows.append(f"{event_type} ({places[0]}): declared but {SCHEMA_DIR}/{event_type}.schema.json is missing")
    return rows


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


class EmittedTypesTests(unittest.TestCase):
    def test_every_emitted_type_is_declared_and_has_a_schema(self):
        seen = 0
        for unit_file in sorted(PACKAGES.glob("*/unit.json")):
            module = unit_file.parent
            declared = set(load_json(unit_file).get("provides", {}).get("events", []))
            with self.subTest(module=module.name):
                seen += len(emitted_types(module / "lib", module.name))
                self.assertEqual([], undeclared(module / "lib", module, declared))
        self.assertGreater(seen, 30, "the scan found almost no emissions: the AST rules no longer match the sources")

    def test_the_scan_sees_each_way_a_module_emits(self):
        found = {module: emitted_types(PACKAGES / module / "lib", module)
                 for module in ("orch", "planner", "workspace", "brain", "gui")}
        self.assertIn("orch.run.refused", found["orch"])  # _emit("...") of the cli
        self.assertIn("orch.agent.failed", found["orch"])  # events.emit("...")
        self.assertIn("orch.review.added", found["orch"])  # _beacon_event("...")
        self.assertIn("planner.item.started", found["planner"])  # (type, data) pairs of the engine
        self.assertIn("workspace.migration.applied", found["workspace"])
        self.assertIn("brain.note.created", found["brain"])  # _emit(CREATED_EVENT, ...): a module constant
        self.assertIn("gui.run.lost", found["gui"])  # self.emit("...")
        self.assertIn("gui.run.started", found["gui"])  # self.emit(f"gui.run.{verb}", ...) over _VERBS

    def test_an_undeclared_type_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "demo"
            (module / "lib" / "demo").mkdir(parents=True)
            (module / "lib" / "demo" / "emitter.py").write_text(
                'KNOWN = "demo.thing.made"\n\ndef run(emit):\n    emit("demo.thing.lost", {})\n    emit(KNOWN, {})\n'
                '    emit("other.thing.made", {})\n', encoding="utf-8")
            (module / SCHEMA_DIR).mkdir(parents=True)
            rows = undeclared(module / "lib", module, {"demo.thing.made"})
        self.assertEqual(2, len(rows), rows)
        self.assertIn("demo.thing.lost", rows[0])
        self.assertIn("not in provides.events", rows[0])
        self.assertIn("demo.thing.made", rows[1])
        self.assertIn("schema.json is missing", rows[1])

    def test_an_emitter_imported_under_another_name_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "demo"
            (module / "lib" / "demo").mkdir(parents=True)
            (module / "lib" / "demo" / "emitter.py").write_text(
                "from aicore.ext import emit as publish\nfrom aicore.ext.events import emit as send\n\n"
                "def run():\n    publish('demo.thing.lost', {}, source='demo')\n    send('demo.thing.made', {})\n",
                encoding="utf-8")
            (module / SCHEMA_DIR).mkdir(parents=True)
            found = emitted_types(module / "lib", "demo")
            self.assertEqual(sorted(found), ["demo.thing.lost", "demo.thing.made"])
            rows = undeclared(module / "lib", module, set())
            self.assertEqual(2, len(rows), rows)
            self.assertTrue(all("not in provides.events" in row for row in rows), rows)
            rows = undeclared(module / "lib", module, {"demo.thing.lost", "demo.thing.made"})
            self.assertTrue(all("schema.json is missing" in row for row in rows) and len(rows) == 2, rows)

    def test_a_type_with_a_declaration_and_a_schema_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "demo"
            (module / "lib" / "demo").mkdir(parents=True)
            (module / "lib" / "demo" / "emitter.py").write_text('def run(emit):\n    emit("demo.thing.made", {})\n',
                                                                 encoding="utf-8")
            (module / SCHEMA_DIR).mkdir(parents=True)
            (module / SCHEMA_DIR / "demo.thing.made.schema.json").write_text("{}", encoding="utf-8")
            self.assertEqual([], undeclared(module / "lib", module, {"demo.thing.made"}))

    def test_the_aicore_cli_may_emit_any_type(self):
        self.assertEqual({}, emitted_types(PACKAGES / "aicore" / "lib" / "aicore" / "ext", "aicore"))


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
