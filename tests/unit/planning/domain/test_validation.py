"""Validation pipeline: every catalog code both ways, the semantic corpus, purity, rule failures, globs."""

import copy
import importlib
import itertools
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.ids import EntityId, FileVersionId
from skm.modules.planning.domain.identity import assign_missing_ids
from skm.modules.planning.domain.specification import EntityKind, from_document, to_document
from skm.modules.planning.domain.validation import pipeline
from skm.modules.planning.domain.validation.context import (
    FileVersionObservation,
    FileVersionStatus,
    ValidationContext,
    ValidationSettings,
)
from skm.modules.planning.domain.validation.findings import (
    DEFAULT_SEVERITY,
    Finding,
    FindingCode,
    RuleFailure,
    Severity,
    ValidationReport,
    finding,
)
from skm.modules.planning.domain.validation.globs import bare, covers, globs_overlap
from skm.modules.planning.domain.validation.pipeline import DEFAULT_RULES, PluginRule, Rule, validate
from skm.modules.planning.generated.settings import PlanningSettings
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "tests/fixtures/planning"
CATALOG_FILE = ROOT / "src/skm/schemas/planning/data/finding-codes.json"
PORTING = ROOT / "docs/porting/planning-findings.md"
SPECIFICATION = "urn:skm:planning:specification:v1"
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
FILE_VERSION = FileVersionId(UUID("0192f5c3-9999-7000-8000-000000000001"))
PLAN3 = UUID("0192f5c3-8888-7000-8000-000000000003")


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return json.loads(CATALOG_FILE.read_text())


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _base() -> dict[str, Any]:
    return _load("valid/auth-refresh.specification.json")


def _defaults(cls: Any) -> dict[str, Any]:
    """Settings values of ``cls`` as the settings registry would hand them over: every default."""
    values: dict[str, Any] = {}
    for _wire, _name, spec, _required, default, _has, key in cls._FIELDS:
        if key:
            values[key] = default
        else:
            module, name = spec[3]
            values.update(_defaults(getattr(importlib.import_module(module), name)))
    return values


SETTINGS = PlanningSettings.from_settings(_defaults(PlanningSettings)).to_json()


def _settings(**validation: Any) -> dict[str, Any]:
    """The resolved ``planning`` section with some ``validation`` keys replaced (tuples become arrays)."""
    changes = {key: list(value) if isinstance(value, tuple) else value for key, value in validation.items()}
    return {**SETTINGS, "validation": {**SETTINGS["validation"], **changes}}


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> UUID:
        self.n += 1
        return UUID(f"0192f5c9-0000-7000-8000-{self.n:012d}")


def _mounts(doc: Any) -> frozenset[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("mount"), str):
                found.add(node["mount"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)
    return frozenset(found)


BASE_MOUNTS = _mounts(_base())
READY = {FILE_VERSION: FileVersionObservation(FileVersionStatus.READY, NOW - timedelta(days=1))}


def _context(doc: dict[str, Any], **over: Any) -> ValidationContext:
    spec, _ = from_document(doc)
    values: dict[str, Any] = {
        "spec": spec,
        "document": doc,
        "project_mounts": BASE_MOUNTS,
        "known_identities": {},
        "file_versions": READY,
        "known_skills": None,
        "runtime_catalog": None,
        "project_plans": {"PLAN3": EntityId(PLAN3)},
        "now": NOW,
        "settings": SETTINGS,
    }
    values.update(over)
    return ValidationContext(**values)


def _run(doc: dict[str, Any], **over: Any) -> ValidationReport:
    return validate(_context(doc, **over))


def _codes(report: ValidationReport) -> set[str]:
    return {found.code for found in report.findings}


def _at(report: ValidationReport, code: str) -> list[Finding]:
    return [found for found in report.findings if found.code == code]


# The valid example is not silent: P2.1/U1 writes docs/api/refresh.md, which no change hint covers, and P1.1
# has no criterion. Everything a case adds is measured against this baseline.
BASELINE = {"write_scope_uncovered", "criterion_missing"}


def test_the_valid_example_has_no_error_and_no_rule_failure(registry):
    doc = _base()
    registry.require_valid(SPECIFICATION, doc)
    report = _run(doc)
    assert report.rule_failures == ()
    assert _codes(report) == BASELINE
    assert not report.has_errors(plugin_failures_block=True)
    assert report.graph is not None
    assert dict(report.counts()) == {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 1}


# --- the catalog -------------------------------------------------------------------------------------


def test_finding_codes_and_severities_restate_the_catalog(catalog):
    assert {code.value for code in FindingCode} == {entry["code"] for entry in catalog["codes"]}
    assert {code.value: sev.value for code, sev in DEFAULT_SEVERITY.items()} == {
        entry["code"]: entry["severity"] for entry in catalog["codes"]
    }


MODULE_ORDER = (
    "rules_structure",
    "rules_references",
    "rules_dependencies",
    "rules_scope",
    "rules_readiness",
    "rules_acceptance",
    "rules_review",
    "rules_checks",
    "rules_decisions",
    "rules_context",
    "rules_routing",
)


def test_every_catalog_code_is_one_rule_of_its_module_in_the_normative_order(catalog):
    """DEFAULT_RULES: modules in the order of planning 5.7, inside one the alphabetical order of the codes."""
    expected = []
    for entry in sorted(
        catalog["codes"], key=lambda e: (MODULE_ORDER.index(e["rule_module"].rsplit(".", 1)[1]), e["code"])
    ):
        module = importlib.import_module(entry["rule_module"])
        rule = getattr(module, entry["code"])
        assert rule in module.RULES
        expected.append(rule)
    assert tuple(expected) == DEFAULT_RULES
    assert len(set(DEFAULT_RULES)) == len(DEFAULT_RULES)


# --- one positive and one negative case for every code -----------------------------------------------


@dataclass(frozen=True)
class Case:
    code: str
    mutate: Callable[[dict[str, Any]], None]
    key: str | None
    pointer: str | None
    over: dict[str, Any] = field(default_factory=dict)
    fix: Callable[[dict[str, Any]], None] | None = None  # a near miss: the same document without the defect
    fix_over: dict[str, Any] | None = None
    note: str = ""


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    """Mutation: ``doc`` at ``path`` (``items/2/phase``) is set to ``value``, or removed for ``<del>``."""

    def mutate(doc: dict[str, Any]) -> None:
        *head, last = path.split("/")
        node: Any = doc
        for part in head:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if value == "<del>":
            node.pop(last, None)
        elif isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value

    return mutate


def _append(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    """Mutation: append ``value`` to the array at ``path``; an entity of a top-level array gets a fresh id."""

    def mutate(doc: dict[str, Any]) -> None:
        node: Any = doc
        for part in path.split("/"):
            node = node[int(part)] if isinstance(node, list) else node[part]
        member = copy.deepcopy(value)
        if "/" not in path and isinstance(member, dict) and "key" in member and "id" not in member:
            member = _new_id(doc, member)
        node.append(member)

    return mutate


def _all(*steps: Callable[[dict[str, Any]], None]) -> Callable[[dict[str, Any]], None]:
    def mutate(doc: dict[str, Any]) -> None:
        for step in steps:
            step(doc)

    return mutate


def _new_id(doc: dict[str, Any], entity: dict[str, Any]) -> dict[str, Any]:
    entity["id"] = f"0192f5c4-ffff-7000-8000-{sum(len(v) for v in doc.values() if isinstance(v, list)):012d}"
    return entity


def _clone(array: str, index: int, **changes: Any) -> Callable[[dict[str, Any]], None]:
    """Mutation: append a copy of ``doc[array][index]`` with a fresh id and ``changes`` applied."""

    def mutate(doc: dict[str, Any]) -> None:
        entity = copy.deepcopy(doc[array][index])
        entity.update(changes)
        doc[array].append(_new_id(doc, entity))

    return mutate


def _check(owner: str, key: str, **changes: Any) -> dict[str, Any]:
    base = {
        "key": key,
        "owner": owner,
        "title": "A check",
        "category": "acceptance",
        "kind": "command",
        "required": True,
        "definition": {"argv": ["true"], "cwd": {"mount": "api", "path": "."}},
    }
    base.update(changes)
    return base


def _new_decision(key: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    entity = {
        "key": key,
        "title": "T",
        "date": "2026-10-22",
        "state": "accepted",
        "options": [{"key": "A", "text": "a"}],
        "decision": "A",
        "rationale": "because",
    }
    entity.update(changes)
    return lambda doc: doc["decisions"].append(_new_id(doc, copy.deepcopy(entity)))


BROKEN_ORDER = _all(_set("items/2/depends_on", ["P2.3"]), _set("items/4/depends_on", []))  # B1 waits for B2
OVERLAPPING_P22 = _all(
    _set("units/5/write_scope", [{"mount": "web", "pattern": "src/auth/refresh.ts"}]),
    _set("units/5/depends_on", []),
)
HEAVY = "x" * 2000

CASES: list[Case] = [
    # structure
    Case(
        "duplicate_id",
        lambda doc: doc["units"][1].update(id=doc["units"][0]["id"]),
        "P1.1/U2",
        "/units/1/id",
        fix=lambda doc: doc["units"][1].update(id=doc["units"][1]["id"]),
    ),
    Case(
        "duplicate_key",
        _clone("requirements", 0),
        "R1",
        "/requirements/3/key",
        fix=_clone("requirements", 0, key="R9"),
    ),
    Case(
        "key_prefix_mismatch",
        _set("items/2/phase", "P1"),
        "P2.1",
        "/items/2/phase",
        fix=_set("items/2/phase", "P2"),
    ),
    Case(
        "entity_kind_changed",
        lambda doc: None,
        "P1.1",
        "/items/0/id",
        over={"known_identities": {EntityId(UUID(_base()["items"][0]["id"])): EntityKind.UNIT}},
        fix_over={"known_identities": {EntityId(UUID(_base()["items"][0]["id"])): EntityKind.ITEM}},
    ),
    # references
    Case(
        "self_reference",
        _set("items/1/depends_on", ["P1.2"]),
        "P1.2",
        "/items/1/depends_on/0",
        fix=_set("items/1/depends_on", ["P1.1"]),
    ),
    Case(
        "ref_unknown",
        _set("items/1/depends_on", ["P1.9"]),
        "P1.2",
        "/items/1/depends_on/0",
        fix=_set("items/1/depends_on", ["P1.1"]),
    ),
    Case(
        "artifact_duplicate",
        _append(
            "items/3/artifacts", {"key": "refresh-api-spec", "mount": "web", "path": "x.md", "role": "output"}
        ),
        "P2.2",
        "/items/3/artifacts/1/key",
        fix=_append("items/3/artifacts", {"key": "other", "mount": "web", "path": "x.md", "role": "output"}),
    ),
    Case(
        "artifact_path_mismatch",
        _set("items/3/artifacts/0/path", "docs/other.md"),
        "P2.2",
        "/items/3/artifacts/0/path",
        fix=_set("items/3/artifacts/0/path", "docs/api/refresh.md"),
    ),
    Case(
        "plan_relation_unresolved",
        _set("plan_relations/0/target", "PLAN9"),
        None,
        "/plan_relations/0/target",
        fix=_set("plan_relations/0/target", "PLAN3"),
    ),
    # dependencies
    Case(
        "dependency_cycle",
        _set("items/0/depends_on", ["P1.2"]),
        "P1.1",
        "/items/0/depends_on",
        fix=_set("items/0/depends_on", []),
    ),
    Case(
        "batch_foreign",
        _append("phases/0/batches/0/items", "P2.1"),
        "P2.1",
        "/phases/0/batches/0/items/2",
        fix=_append("phases/0/batches/0/items", "P1.2"),
    ),
    Case(
        "batch_multiple",
        _append("phases/1/batches/1/items", "P2.1"),
        "P2.1",
        "/phases/1/batches/1/items/1",
    ),
    Case(
        "batch_unassigned",
        _set("phases/0/batches/0/items", ["P1.1"]),
        "P1.2",
        "/phases/0/batches",
        fix=_set("phases/0/batches/0/items", ["P1.1", "P1.2"]),
    ),
    Case(
        "batch_order_conflict",
        BROKEN_ORDER,
        "P2.1",
        "/items/2/depends_on",
        fix=_set("items/2/depends_on", []),
    ),
    # scope
    Case(
        "mount_unknown",
        _set("items/0/change_hints/0/mount", "nowhere"),
        "P1.1",
        "/items/0/change_hints/0/mount",
        fix=_set("items/0/change_hints/0/mount", "api"),
    ),
    Case(
        "write_scope_overlap",
        OVERLAPPING_P22,
        "P2.2/U2",
        "/units/5/write_scope/0/pattern",
        fix=_all(OVERLAPPING_P22, _set("units/5/depends_on", ["U1"])),  # ordered by a dependency
    ),
    Case(
        "write_scope_overlap_cross_item",
        _set("units/4/write_scope", [{"mount": "api", "pattern": "src/http/*.py"}]),
        "P2.2/U1",
        "/units/4/write_scope/0/pattern",
        fix=_all(
            _set("units/4/write_scope", [{"mount": "api", "pattern": "src/http/*.py"}]),
            _set("items/3/depends_on", ["P2.1"]),
        ),
    ),
    Case(
        "write_scope_uncovered",
        lambda doc: None,
        "P2.1/U1",
        "/units/2/write_scope/1/pattern",
        fix=_append("items/2/change_hints", {"mount": "api", "pattern": "docs/api/", "change": "create"}),
    ),
    Case(
        "write_scope_empty",
        _all(
            _set("items/3/change_hints", []), _set("units/4/write_scope", []), _set("units/5/write_scope", [])
        ),
        "P2.2",
        "/items/3/change_hints",
        fix=_all(
            _set("items/3/change_hints", []),
            _set("units/4/write_scope", []),
            _set("units/4/work_kind", "research"),
            _set("units/5/write_scope", [{"mount": "web", "pattern": "src/auth/x.md"}]),
        ),
    ),
    Case(
        "write_scope_no_tests",
        _all(
            _set(
                "items/2/change_hints",
                [{"mount": "api", "pattern": "src/http/auth_routes.py", "change": "modify"}],
            ),
            _set("units/3/write_scope", []),
        ),
        "P2.1",
        "/items/2/change_hints",
        fix=_set(
            "items/2/change_hints",
            [
                {"mount": "api", "pattern": "src/http/auth_routes.py", "change": "modify"},
                {"mount": "api", "pattern": "tests/api/test_routes.py", "change": "create"},
            ],
        ),
    ),
    Case(
        "forbidden_path_conflict",
        _append(
            "items/0/change_hints", {"mount": "api", "pattern": "config/secrets/keys.py", "change": "create"}
        ),
        "P1.1",
        "/items/0/change_hints/3/pattern",
        fix=_append(
            "items/0/change_hints", {"mount": "web", "pattern": "config/secrets/keys.py", "change": "create"}
        ),
    ),
    # readiness
    Case(
        "incomplete",
        _set("items/3/deliverables", []),
        "P2.2",
        "/items/3/deliverables",
        fix=_set("items/3/deliverables", ["Silent refresh"]),
    ),
    Case(
        "phase_skeleton",
        _set("phases/1/design_state", "skeleton"),
        "P2",
        "/phases/1/design_state",
        fix=_set("phases/1/design_state", "detailed"),
    ),
    Case(
        "context_default",
        lambda doc: doc.update(goal=doc["title"]),
        None,
        "/goal",
        fix=lambda doc: doc.update(goal="Another sentence."),
    ),
    Case(
        "research_question_missing",
        _set("items/3/research", {"need": "required"}),
        "P2.2",
        "/items/3/research",
        fix=_set("items/3/research", {"need": "required", "question": "Which?"}),
    ),
    # acceptance
    Case(
        "criterion_unlinked",
        _set("criteria/0/checks", []),
        "AC1",
        "/criteria/0/checks",
        fix=_set("criteria/0/checks", ["P1.2:V1"]),
    ),
    Case(
        "criterion_check_mismatch",
        _set("criteria/0/checks", ["P2.1:V1"]),
        "AC1",
        "/criteria/0/checks/0",
        fix=_set("criteria/0/checks", ["P1.2:V1"]),
    ),
    Case(
        "requirement_unimplemented",
        _append(
            "requirements",
            {
                "id": "0192f5c4-ffff-7000-8000-0000000000aa",
                "key": "R4",
                "statement": "Nobody does this.",
                "priority": "must",
                "source": {"kind": "owner"},
            },
        ),
        "R4",
        "/requirements/3",
        fix=_append(
            "requirements",
            {
                "id": "0192f5c4-ffff-7000-8000-0000000000aa",
                "key": "R4",
                "statement": "Somebody does this.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.2"],
            },
        ),
    ),
    Case(
        "criterion_missing",
        lambda doc: None,
        "P1.1",
        "/items/0",
        fix=_append(
            "criteria",
            {
                "id": "0192f5c4-ffff-7000-8000-0000000000ab",
                "key": "AC9",
                "owner": "P1.1",
                "statement": "Works.",
                "verification_mode": "check",
                "checks": ["V1"],
            },
        ),
    ),
    # review
    Case(
        "review_reviewer_unset",
        _set("items/0/review", {"mode": "required", "profile": "code-review"}),
        "P1.1",
        "/items/0/review",
        fix=_set("items/0/review", {"mode": "required", "profile": "code-review", "max_rounds": 2}),
    ),
    # checks
    Case(
        "unit_command_missing",
        _all(_set("units/0/unit_kind", "command"), _set("units/0/command", "<del>")),
        "P1.1/U1",
        "/units/0/command",
        fix=_set("units/0/unit_kind", "implementation"),
    ),
    Case(
        "check_cadence",
        lambda doc: None,
        "P1.1:V1",
        "/checks/0/definition",
        over={"settings": _settings(heavy_check_markers=("pytest",))},
        fix_over={"settings": _settings(heavy_check_markers=("--tier all",))},
    ),
    Case(
        "check_duplicate_command",
        _append("checks", _check("P1", "V2", definition=_base()["checks"][0]["definition"])),
        "P1.1:V1",
        "/checks/0/definition",
        fix=_append("checks", _check("P1", "V2")),
    ),
    Case(
        "check_manual_rerun_after_integration",
        _set("checks/6/rerun_after_integration", True),
        "P2.3:V1",
        "/checks/6/rerun_after_integration",
        fix=_set("checks/6/rerun_after_integration", False),
    ),
    # decisions
    Case(
        "decision_fields",
        _set("decisions/0/rationale", "<del>"),
        "D1",
        "/decisions/0/rationale",
        fix=_set("decisions/0/rationale", "Only A detects replay."),
    ),
    Case(
        "decision_superseded_orphan",
        _set("decisions/1/state", "superseded"),
        "D2",
        "/decisions/1/state",
        fix=_all(
            _set("decisions/1/state", "superseded"),
            _new_decision("D3", supersedes=["D2"], applies_to=["P2.2"]),
        ),
    ),
    # context
    Case(
        "scope_ambiguous",
        _set("materials/1/applies_to", ["P1"]),
        "material/auth-module",
        "/materials/1/global",
        fix=_set("materials/1/global", False),
    ),
    Case(
        "context_unbound",
        _new_decision("D3"),
        "D3",
        "/decisions/2/applies_to",
        fix=_new_decision("D3", applies_to=["P1.2"]),
    ),
    Case(
        "brief_duplicate",
        lambda doc: doc["brief"]["messages"][1].update(text=doc["brief"]["messages"][0]["text"] + " "),
        "M2",
        "/brief/messages/1/text",
        fix=lambda doc: doc["brief"]["messages"][1].update(text="Another."),
    ),
    Case(
        "context_heavy",
        lambda doc: doc.update(context_md=HEAVY),
        None,
        "/context_md",
        over={"settings": _settings(heavy_text_bytes=1024)},
        fix_over={"settings": _settings(heavy_text_bytes=4096)},
    ),
    Case(
        "execution_prompt_heavy",
        _set("items/0/guidance_md", HEAVY),
        "P1.1",
        "/items/0",
        over={"settings": _settings(heavy_text_bytes=1024)},
        fix_over={"settings": _settings(heavy_text_bytes=4096)},
    ),
    Case(
        "material_unavailable",
        lambda doc: None,
        "material/storage-design",
        "/materials/0/file_version_id",
        over={"file_versions": {}},
        fix_over={"file_versions": READY},
    ),
    Case(
        "material_stale",
        _set("materials/2/retrieved_at", "2026-01-01T00:00:00Z"),
        "material/oauth-threats",
        "/materials/2/freshness",
        fix=_set("materials/2/retrieved_at", "2026-10-28T00:00:00Z"),
    ),
    # routing
    Case(
        "route_unknown_runtime",
        lambda doc: None,
        "P2.2",
        "/items/3/route/runtime",
        over={"runtime_catalog": {"claude": frozenset({"opus"})}},
        fix_over={"runtime_catalog": {"codex": frozenset({"gpt-5-codex"})}},
    ),
    Case(
        "route_unknown_model",
        lambda doc: None,
        "P2.2",
        "/items/3/route/model",
        over={"runtime_catalog": {"codex": frozenset({"other"})}},
        fix_over={"runtime_catalog": {"codex": frozenset({"gpt-5-codex"})}},
    ),
    Case(
        "skill_unknown",
        lambda doc: None,
        "P1.1",
        "/items/0/skills/0/key",
        over={"known_skills": frozenset()},
        fix_over={"known_skills": frozenset({"postgres-migrations"})},
    ),
]


def test_every_catalog_code_has_exactly_one_case(catalog):
    assert sorted(case.code for case in CASES) == sorted(entry["code"] for entry in catalog["codes"])


def _case_id(case: Case) -> str:
    return case.code


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_positive_the_defect_is_reported_at_its_entity_and_pointer(case, registry):
    doc = _base()
    case.mutate(doc)
    report = _run(doc, **case.over)
    assert report.rule_failures == ()
    hits = [found for found in _at(report, case.code) if found.pointer == case.pointer]
    assert hits, [(f.code, f.entity_key, f.pointer) for f in _at(report, case.code)]
    assert case.key in {found.entity_key for found in hits}
    assert {found.severity for found in hits} == {DEFAULT_SEVERITY[FindingCode(case.code)]}


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.fix is not None or c.fix_over is not None], ids=_case_id
)
def test_negative_the_near_miss_does_not_report_the_code(case):
    """The near miss is the valid example with the defect repaired (not the defect plus a repair)."""
    doc = _base()
    if case.fix is not None:
        case.fix(doc)
    report = _run(doc, **(case.fix_over or {}))
    assert report.rule_failures == ()
    assert case.code not in _codes(report), case.code


def test_a_baseline_code_always_has_a_near_miss():
    assert {c.code for c in CASES if c.code in BASELINE and c.fix is None and c.fix_over is None} == set()


@pytest.mark.parametrize("case", [c for c in CASES if c.fix is None and c.fix_over is None], ids=_case_id)
def test_a_case_without_near_miss_is_silent_on_the_valid_example(case):
    assert case.code not in _codes(_run(_base()))


# --- variants of the codes with several triggers ----------------------------------------------------


DUPLICATE_KEY_VARIANTS = [
    ("check key in one owner", _clone("checks", 0), "P1.1:V1", "/checks/8/key"),
    (
        "batch key in a phase",
        _append("phases/1/batches", {"key": "B1", "items": ["P2.3"], "mode": "recommended"}),
        "P2/B1",
        "/phases/1/batches/2/key",
    ),
    (
        "section id in an entity",
        _all(
            _set(
                "items/0/sections",
                [{"id": "s", "title": "t", "text": "x"}, {"id": "s", "title": "u", "text": "y"}],
            )
        ),
        "P1.1",
        "/items/0/sections/1/id",
    ),
    (
        "option key in a decision",
        _append("decisions/0/options", {"key": "A", "text": "again"}),
        "D1",
        "/decisions/0/options/2/key",
    ),
    ("material key", _clone("materials", 0), "material/storage-design", "/materials/3/key"),
    (
        "brief message key",
        _append("brief/messages", {"key": "M1", "kind": "record", "text": "later"}),
        "M1",
        "/brief/messages/2/key",
    ),
    (
        "plan section id",
        _set("sections", [{"id": "s", "title": "t", "text": "x"}, {"id": "s", "title": "t", "text": "y"}]),
        "s",
        "/sections/1/id",
    ),
]


@pytest.mark.parametrize(
    ("name", "mutate", "key", "pointer"),
    DUPLICATE_KEY_VARIANTS,
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_duplicate_key_in_each_scope(name, mutate, key, pointer):
    doc = _base()
    mutate(doc)
    found = [f for f in _at(_run(doc), "duplicate_key") if f.pointer == pointer]
    assert [f.entity_key for f in found] == [key], name
    assert found[0].details["first_pointer"] != pointer


def test_the_same_check_key_under_two_owners_is_not_a_duplicate():
    assert "duplicate_key" not in _codes(_run(_base()))  # P1.1:V1 and P1.2:V1


SELF_VARIANTS = [
    ("phase depends_on", _set("phases/1/depends_on", ["P2"]), "P2", "/phases/1/depends_on/0"),
    (
        "item relation target",
        _set("items/0/relations", [{"target": "P1.1", "relation": "related"}]),
        "P1.1",
        "/items/0/relations/0/target",
    ),
    ("unit depends_on", _set("units/1/depends_on", ["U2"]), "P1.1/U2", "/units/1/depends_on/0"),
    ("unit parent", _set("units/1/parent", "P1.1/U2"), "P1.1/U2", "/units/1/parent"),
    ("decision supersedes", _set("decisions/1/supersedes", ["D2"]), "D2", "/decisions/1/supersedes/0"),
]


@pytest.mark.parametrize(
    ("name", "mutate", "key", "pointer"), SELF_VARIANTS, ids=lambda v: v if isinstance(v, str) else ""
)
def test_self_reference_in_each_field(name, mutate, key, pointer):
    doc = _base()
    mutate(doc)
    assert (key, pointer) in {(f.entity_key, f.pointer) for f in _at(_run(doc), "self_reference")}, name


REF_VARIANTS = [
    ("phase depends_on", _set("phases/1/depends_on", ["P9"]), "/phases/1/depends_on/0"),
    ("batch item", _append("phases/0/batches/0/items", "P1.9"), "/phases/0/batches/0/items/2"),
    ("item phase", _set("items/0/phase", "P9"), "/items/0/phase"),
    ("item implements", _set("items/0/implements", ["R9"]), "/items/0/implements/0"),
    ("item decisions", _set("items/1/decisions", ["D9"]), "/items/1/decisions/0"),
    (
        "item relation",
        _set("items/0/relations", [{"target": "P9.9", "relation": "related"}]),
        "/items/0/relations/0/target",
    ),
    ("unit depends_on", _set("units/1/depends_on", ["U9"]), "/units/1/depends_on/0"),
    ("unit check", _set("units/0/checks", ["V9"]), "/units/0/checks/0"),
    ("criterion check", _set("criteria/0/checks", ["P1.2:V9"]), "/criteria/0/checks/0"),
    ("check owner", _set("checks/0/owner", "P9.9"), "/checks/0/owner"),
    (
        "material read",
        _append("items/0/reads", {"kind": "material", "ref": "material/none", "why": "w", "required": True}),
        "/items/0/reads/2/ref",
    ),
    (
        "plan entity read",
        _append("items/0/reads", {"kind": "plan_entity", "ref": "D9", "why": "w", "required": True}),
        "/items/0/reads/2/ref",
    ),
    ("decision supersedes", _set("decisions/0/supersedes", ["D9"]), "/decisions/0/supersedes/0"),
    (
        "decision evidence",
        _set("decisions/0/evidence", [{"kind": "material", "ref": "material/none"}]),
        "/decisions/0/evidence/0/ref",
    ),
    ("material applies_to", _set("materials/0/applies_to", ["P9"]), "/materials/0/applies_to/0"),
]


@pytest.mark.parametrize(
    ("name", "mutate", "pointer"), REF_VARIANTS, ids=lambda v: v if isinstance(v, str) else ""
)
def test_ref_unknown_in_each_reference_field(name, mutate, pointer):
    doc = _base()
    mutate(doc)
    assert pointer in {f.pointer for f in _at(_run(doc), "ref_unknown")}, name


def test_a_reference_by_entity_id_resolves_and_by_a_foreign_id_does_not():
    doc = _base()
    doc["items"][0]["relations"] = [{"target": f"entity:{doc['items'][1]['id']}", "relation": "related"}]
    assert "ref_unknown" not in _codes(_run(doc))
    doc["items"][0]["relations"] = [
        {"target": "entity:0192f5c4-ffff-7000-8000-ffffffffffff", "relation": "related"}
    ]
    assert "ref_unknown" in _codes(_run(doc))


def test_a_local_unit_reference_is_completed_by_the_item_it_is_written_in():
    doc = _base()  # P1.1/U2 depends on "U1": the unit of its own item
    assert "ref_unknown" not in _codes(_run(doc))
    doc["units"][3]["depends_on"] = ["U1"]  # P2.1/U2 -> P2.1/U1 exists too
    assert "ref_unknown" not in _codes(_run(doc))
    doc["units"][3]["depends_on"] = ["U7"]
    assert "ref_unknown" in _codes(_run(doc))


def _artifact_read(ref: str) -> dict[str, Any]:
    return {"kind": "artifact", "ref": ref, "why": "Needs the produced file.", "required": True}


def test_a_read_of_an_artifact_no_output_declares_is_ref_unknown(registry):
    doc = _base()
    assert "ref_unknown" not in _codes(_run(doc))  # P2.2 reads artifact/refresh-api-spec, declared by P2.1
    doc["items"][3]["reads"][0]["ref"] = "artifact/absent"
    registry.require_valid(SPECIFICATION, doc)
    report = _run(doc)
    (missing,) = _at(report, "ref_unknown")
    assert (missing.pointer, missing.entity_key, missing.severity) == (
        "/items/3/reads/0/ref",
        "P2.2",
        Severity.ERROR,
    )
    assert missing.details == {"ref": "artifact/absent", "kind": "artifact"}
    assert report.has_errors(plugin_failures_block=False)


@pytest.mark.parametrize(
    ("array", "index", "member"),
    [("phases", 0, "supporting"), ("items", 3, "examples"), ("units", 4, "reads"), ("items", 0, "reads")],
)
def test_artifact_reads_are_resolved_in_every_read_container(registry, array, index, member):
    doc = _base()
    doc[array][index][member] = [
        *doc[array][index].get(member, []),
        _artifact_read("artifact/refresh-api-spec"),
    ]
    registry.require_valid(SPECIFICATION, doc)
    assert "ref_unknown" not in _codes(_run(doc))
    last = len(doc[array][index][member]) - 1
    doc[array][index][member][last]["ref"] = "artifact/absent"
    registry.require_valid(SPECIFICATION, doc)
    assert {f.pointer for f in _at(_run(doc), "ref_unknown")} == {f"/{array}/{index}/{member}/{last}/ref"}


def test_an_input_artifact_does_not_declare_what_an_artifact_read_may_name():
    doc = _base()
    doc["items"][3]["reads"][0]["ref"] = "artifact/only-input"
    doc["items"][4]["artifacts"] = [
        {"key": "only-input", "mount": "api", "path": "docs/x.md", "role": "input"}
    ]
    assert "/items/3/reads/0/ref" in {f.pointer for f in _at(_run(doc), "ref_unknown")}
    doc["items"][4]["artifacts"][0]["role"] = "output"
    assert "ref_unknown" not in _codes(_run(doc))


def test_an_unlinked_plan_relation_target_may_be_a_plan_uuid():
    doc = _base()
    doc["plan_relations"][0]["target"] = f"plan:{PLAN3}"
    ctx = _context(doc, project_plans={f"plan:{PLAN3}": EntityId(PLAN3)})
    assert "plan_relation_unresolved" not in {f.code for f in validate(ctx).findings}


# --- dependency findings and the batch barrier ------------------------------------------------------


def test_a_cycle_closed_only_by_a_batch_barrier_is_a_batch_conflict_not_a_cycle():
    doc = _base()
    BROKEN_ORDER(doc)
    report = _run(doc)
    assert _codes(report) >= {"batch_order_conflict"}
    assert "dependency_cycle" not in _codes(report)


def test_a_real_cycle_reports_its_tasks_and_no_batch_conflict():
    doc = _base()
    doc["items"][0]["depends_on"] = ["P1.2"]
    (cycle,) = _at(_run(doc), "dependency_cycle")
    tasks = cast("list[str]", cycle.details["cycle"])
    assert tasks[0] == tasks[-1]
    assert "batch_order_conflict" not in _codes(_run(doc))


def test_a_cycle_through_a_phase_gate_is_found():
    doc = _load("invalid/dependency_cycle--through-phase.json")
    (cycle,) = _at(_run(doc), "dependency_cycle")
    assert "P1#gate" in cast("list[str]", cycle.details["cycle"])


def _two_phase_barrier_cycle() -> dict[str, Any]:
    """A cycle that the batch barriers of two phases close together: no single batch waits for a later one."""
    doc = _base()
    doc["phases"][0]["batches"] = [
        {"key": "B1", "items": ["P1.1"], "mode": "required"},
        {"key": "B2", "items": ["P1.2"], "mode": "required"},
    ]
    doc["phases"][1]["depends_on"] = []
    doc["phases"][1]["batches"][0]["items"] = ["P2.1"]
    doc["phases"][1]["batches"][1]["items"] = ["P2.2", "P2.3"]
    doc["items"][0]["depends_on"] = ["P2.2"]  # P1.1 -> P2.2 -(barrier)-> P2.1 -> P1.2 -(barrier)-> P1.1
    doc["items"][1]["depends_on"] = []
    doc["items"][2]["depends_on"] = ["P1.2"]
    return doc


@pytest.mark.parametrize("plugin_failures_block", [False, True])
def test_a_cycle_closed_by_the_barriers_of_two_phases_is_a_cycle_and_blocks(plugin_failures_block):
    doc = _two_phase_barrier_cycle()
    report = _run(doc)
    (cycle,) = _at(report, "dependency_cycle")
    tasks = cast("list[str]", cycle.details["cycle"])
    assert tasks[0] == tasks[-1]
    assert {"P1.1", "P2.2"} <= {task.split("/")[0] for task in tasks}
    assert cycle.severity is Severity.ERROR
    assert "batch_order_conflict" not in _codes(report)
    assert report.graph is None
    assert report.rule_failures == ()
    assert report.has_errors(plugin_failures_block=plugin_failures_block)
    doc["items"][0]["depends_on"] = []  # the cycle-forming dependency goes: the graph is whole again
    fixed = _run(doc)
    assert "dependency_cycle" not in _codes(fixed)
    assert fixed.graph is not None


def test_a_barrier_cycle_made_by_a_repeated_batch_item_is_left_to_batch_multiple():
    doc = _base()
    doc["phases"][1]["batches"][1]["items"].append("P2.1")  # P2.1 waits for itself through the barrier
    report = _run(doc)
    assert "batch_multiple" in _codes(report)
    assert "dependency_cycle" not in _codes(report)
    assert report.rule_failures == ()
    assert report.has_errors(plugin_failures_block=False)


def test_a_cycle_no_rule_reports_is_a_failure_of_the_validator_and_blocks():
    report = validate(_context(_two_phase_barrier_cycle()), rules=())
    assert report.graph is None
    assert [(f.rule, f.plugin) for f in report.rule_failures] == [("compile_execution_graph", None)]
    assert report.has_errors(plugin_failures_block=False)


def test_graph_rules_stay_silent_while_an_item_key_contradicts_its_phase():
    doc = _load(
        "invalid/key_prefix_mismatch--item-in-other-phase.json"
    )  # a cycle exists only by the misplacement
    report = _run(doc)
    assert {"key_prefix_mismatch", "batch_foreign"} <= _codes(report)
    assert _codes(report).isdisjoint({"dependency_cycle", "batch_order_conflict", "write_scope_overlap"})
    assert report.graph is None


def test_an_item_in_two_batches_of_one_phase_is_reported_once_at_the_second_use():
    doc = _base()
    doc["phases"][0]["batches"].append({"key": "B2", "items": ["P1.1"], "mode": "recommended"})
    (found,) = _at(_run(doc), "batch_multiple")
    assert (found.entity_key, found.pointer) == ("P1.1", "/phases/0/batches/1/items/0")


def test_items_outside_any_batch_are_info_only_for_a_phase_with_batches():
    doc = _base()
    doc["phases"][0]["batches"] = []
    assert "batch_unassigned" not in _codes(_run(doc))


# --- scope ------------------------------------------------------------------------------------------


MOUNT_VARIANTS = [
    ("change hint", "items/0/change_hints/0/mount", "/items/0/change_hints/0/mount"),
    ("unit write scope", "units/1/write_scope/0/mount", "/units/1/write_scope/0/mount"),
    ("unit output", "units/2/outputs/0/mount", "/units/2/outputs/0/mount"),
    ("item read", "items/0/reads/1/mount", "/items/0/reads/1/mount"),
    ("item artifact", "items/2/artifacts/0/mount", "/items/2/artifacts/0/mount"),
    ("check cwd", "checks/0/definition/cwd/mount", "/checks/0/definition/cwd/mount"),
    ("material repository path", "materials/1/mount", "/materials/1/mount"),
    (
        "forbidden path",
        "execution_constraints/forbidden_paths/0/mount",
        "/execution_constraints/forbidden_paths/0/mount",
    ),
]


@pytest.mark.parametrize(("name", "path", "pointer"), MOUNT_VARIANTS, ids=[v[0] for v in MOUNT_VARIANTS])
def test_mount_unknown_for_each_place_a_mount_is_named(name, path, pointer):
    doc = _base()
    _set(path, "nowhere")(doc)
    assert pointer in {f.pointer for f in _at(_run(doc), "mount_unknown")}, name


def test_mount_unknown_names_the_cwd_of_a_unit_command_phase_support_and_examples():
    doc = _base()
    doc["units"][0]["unit_kind"] = "command"
    doc["units"][0]["command"] = {
        "kind": "command",
        "definition": {"argv": ["true"], "cwd": {"mount": "gone"}},
    }
    doc["phases"][0]["supporting"] = [
        {"kind": "repository_path", "mount": "gone", "path": "x", "why": "w", "required": False}
    ]
    doc["items"][0]["examples"] = [
        {"kind": "repository_path", "mount": "gone", "path": "x", "why": "w", "required": False}
    ]
    pointers = {f.pointer for f in _at(_run(doc), "mount_unknown")}
    assert {
        "/units/0/command/definition/cwd/mount",
        "/phases/0/supporting/0/mount",
        "/items/0/examples/0/mount",
    } <= pointers


def test_independent_units_with_distinct_paths_do_not_overlap():
    doc = _base()
    doc["units"][5]["depends_on"] = []
    assert "write_scope_overlap" not in _codes(_run(doc))


def test_an_unknown_scope_is_not_reported_as_an_overlap():
    doc = _base()
    doc["units"][5][
        "write_scope"
    ] = []  # footprint unknown: the scheduler serialises it, the plan is not wrong
    assert _codes(_run(doc)).isdisjoint({"write_scope_overlap", "write_scope_overlap_cross_item"})


def test_a_dependency_between_items_orders_their_units():
    doc = _base()
    _set("units/4/write_scope", [{"mount": "api", "pattern": "src/http/*.py"}])(doc)
    assert "write_scope_overlap_cross_item" in _codes(_run(doc))
    doc["items"][3]["depends_on"] = ["P2.1"]
    assert "write_scope_overlap_cross_item" not in _codes(_run(doc))


def test_write_scope_no_tests_follows_the_suffix_setting_and_test_path_shapes():
    for test_path in (
        "tests/x.py",
        "pkg/test/x.py",
        "pkg/test_x.py",
        "pkg/x_test.py",
        "web/x.test.ts",
        "web/x.spec.ts",
        "pkg/XTest.java",
    ):
        doc = _base()
        doc["items"][2]["change_hints"] = [
            {"mount": "api", "pattern": "src/a.py", "change": "create"},
            {"mount": "api", "pattern": test_path, "change": "create"},
        ]
        doc["units"][2]["write_scope"] = doc["units"][3]["write_scope"] = []
        assert "write_scope_no_tests" not in _codes(_run(doc)), test_path
    doc["items"][2]["change_hints"] = [{"mount": "api", "pattern": "src/a.py", "change": "create"}]
    assert "write_scope_no_tests" in _codes(_run(doc))
    assert "write_scope_no_tests" not in _codes(_run(doc, settings=_settings(code_suffixes=(".go",))))
    doc["items"][2]["change_hints"] = [{"mount": "api", "pattern": "src/a.py", "change": "delete"}]
    assert "write_scope_no_tests" not in _codes(_run(doc))  # only create and modify count as writing code


def test_write_scope_no_tests_counts_code_of_hints_and_of_unit_scopes_together(registry):
    doc = _base()
    assert "write_scope_no_tests" not in _codes(_run(doc))
    # P2.2 hints only documentation, while its unit writes src/auth/refresh.ts and no test path
    doc["items"][3]["change_hints"] = [{"mount": "web", "pattern": "docs/readme.md", "change": "create"}]
    doc["units"][5]["write_scope"] = []
    registry.require_valid(SPECIFICATION, doc)
    (missing,) = _at(_run(doc), "write_scope_no_tests")
    assert missing.entity_key == "P2.2"
    assert missing.details == {"code_paths": ["src/auth/refresh.ts"]}
    doc["units"][5]["write_scope"] = [{"mount": "web", "pattern": "src/auth/refresh.test.ts"}]
    assert "write_scope_no_tests" not in _codes(_run(doc))  # a declared test path suppresses it
    doc["units"][5]["write_scope"] = []
    doc["items"][3]["change_hints"].append(
        {"mount": "web", "pattern": "src/auth/refresh.test.ts", "change": "any"}
    )
    assert "write_scope_no_tests" not in _codes(_run(doc))
    doc["items"][3]["change_hints"].pop()
    assert "write_scope_no_tests" in _codes(_run(doc))


def test_write_scope_empty_applies_to_writing_work_kinds_only():
    doc = _base()
    doc["items"][4]["change_hints"] = []  # P2.3 is review work, without units
    assert "write_scope_empty" not in _codes(_run(doc))


def test_write_scope_empty_reports_each_writing_unit_without_a_scope():
    doc = _base()
    doc["units"][0]["write_scope"] = []  # P1.1 keeps its change hints, which do not reach the unit task
    doc["units"][5]["write_scope"] = []  # P2.2/U1 keeps its scope, so the item itself has a footprint
    found = [f for f in _run(doc).findings if f.code == "write_scope_empty"]
    assert [(f.entity_key, f.pointer, f.details["work_kind"]) for f in found] == [
        ("P1.1/U1", "/units/0/write_scope", "code"),
        ("P2.2/U2", "/units/5/write_scope", "test"),
    ]


@pytest.mark.parametrize("work_kind", ["research", "review", "ops"])
def test_write_scope_empty_spares_units_that_do_not_write(work_kind: str):
    doc = _base()
    doc["units"][0]["write_scope"] = []
    doc["units"][0]["work_kind"] = work_kind
    assert "write_scope_empty" not in _codes(_run(doc))


def test_forbidden_paths_use_the_may_overlap_rule():
    doc = _base()
    doc["items"][0]["change_hints"][1] = {"mount": "api", "pattern": "config/**", "change": "create"}
    assert "forbidden_path_conflict" in _codes(_run(doc))


# --- the coverage dialect of write_scope_uncovered --------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "hint", "covered"),
    [
        ("src/a.py", "src/a.py", True),
        ("src/a.py", "src", True),  # a plain path names everything below it
        ("src/a.py", "src/", True),
        ("src/a.py", "./src//", True),
        ("src/a.py", "src/*.py", False),  # a plain path names what lies below it, which a glob does not
        ("src/pkg", "src/*", False),
        ("src/pkg", "src/**", True),
        ("src/a/b.py", "src/*", False),  # a glob matches whole paths at the fence: "*" stays in one segment
        ("src/a/b.py", "src/**", True),
        ("src/a/b.py", "**/b.py", False),  # a hint glob without "/" does not reach below b.py
        ("src/a/b.py", "**", True),
        ("src/*.py", "src/*.py", True),
        ("src/a*.py", "src/*.py", True),
        ("src/*.py", "src/a*.py", False),  # the entry names more than the hint
        ("src/*.py", "src/**", True),
        ("src/**", "src/*", False),
        ("src/**/x.py", "src/**", True),
        ("src/ab.py", "src/a?.py", False),
        ("src/a?.py", "src/ab.py", False),
        ("src/[ab].py", "src/?.py", True),
        ("src/?.py", "src/[ab].py", False),  # a bracket set of the hint is narrow
        ("src/a.py", "lib/a.py", False),
        ("docs/api/refresh.md", "src/http/auth_routes.py", False),
        ("src/a.py", "src/a.py/", True),
        ("src/", "src/*.py", False),  # an explicit directory names what lies below it
        ("src/", "src", True),
        ("src", "src/a.py", False),
        ("src/*/", "src/*/", True),  # the same pattern covers itself
        (
            "src/*/x",
            "src/*/",
            False,
        ),  # the fence reads a trailing "/" after a glob literally: a directory named "*"
        ("src/[ab].py", "src/[ab].py", True),
        ("src/a.py", "src/[ab].py", False),
        ("src/a", "src/a*", False),
        ("../x", "**", False),  # a pattern the fence rejects is never proven covered
        ("src/a.py", "../x", False),
        ("src/a.py", ".", False),
        ("", "src", False),
    ],
)
def test_covers_in_the_fence_dialect(entry, hint, covered):
    assert covers(entry, hint) is covered


def test_a_plain_scope_path_is_not_covered_by_a_glob_hint_that_misses_what_lies_below_it():
    assert not covers("src/pkg", "src/*")  # the fence matches src/pkg/a.py for the scope and not for the hint
    assert all(covers("src/pkg", hint) for hint in ("src/pkg", "src/", "src/**"))
    doc = _base()
    doc["items"][3]["change_hints"] = [{"mount": "web", "pattern": "src/*", "change": "modify"}]
    doc["units"][5]["write_scope"] = [{"mount": "web", "pattern": "src/auth"}]
    uncovered = {f.pointer for f in _at(_run(doc), "write_scope_uncovered")}
    assert "/units/5/write_scope/0/pattern" in uncovered
    doc["items"][3]["change_hints"][0]["pattern"] = "src/**"
    assert "/units/5/write_scope/0/pattern" not in {
        f.pointer for f in _at(_run(doc), "write_scope_uncovered")
    }


_SEGMENTS = ("a", "b", "ab", "ab.py", "x.py", "a.md", "[x", "*", "src")
_PATTERNS = (
    "a", "a/", "a/b", "ab.py", "*", "*/", "**", "a/**", "**/x.py", "a/**/b", "*.py", "a*.py", "*b.py",
    "a?", "?b*", "[ab]", "[!a]*", "[x", "[x/*", "*/*.md", "src/*", "src/**/x.py", "a/*/b", "*/a.md/", "a**",
    "**/*/a",
)  # fmt: skip


def _fence_matches(path: tuple[str, ...], pattern: str) -> bool:
    """The write-scope fence of adapters 3.5, restated for paths that need no normalisation."""
    parts = tuple(part for part in pattern.split("/") if part not in ("", "."))
    if pattern.endswith("/") or not any(char in pattern for char in "*?["):
        return path[: len(parts)] == parts

    def segments(at: int, rest: tuple[str, ...]) -> bool:
        if not rest:
            return at == len(path)
        if rest[0] == "**":
            return any(segments(n, rest[1:]) for n in range(at, len(path) + 1))
        return at < len(path) and fnmatchcase(path[at], rest[0]) and segments(at + 1, rest[1:])

    return segments(0, parts)


def _paths() -> list[tuple[str, ...]]:
    return [path for depth in (1, 2, 3) for path in itertools.product(_SEGMENTS, repeat=depth)]


def _under(pattern: str, paths: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    return {path for path in paths if any(_fence_matches(path[:n], pattern) for n in range(1, 4))}


def _glob_prefix_matches(path: tuple[str, ...], pattern: str) -> bool:
    """``pattern`` read as a glob that also names what lies below the paths it matches."""
    parts = tuple(part for part in pattern.split("/") if part not in ("", "."))

    def segments(at: int, rest: tuple[str, ...], whole: tuple[str, ...]) -> bool:
        if not rest:
            return at == len(whole)
        if rest[0] == "**":
            return any(segments(n, rest[1:], whole) for n in range(at, len(whole) + 1))
        return at < len(whole) and fnmatchcase(whole[at], rest[0]) and segments(at + 1, rest[1:], whole)

    return any(segments(0, parts, path[:n]) for n in range(1, len(path) + 1))


def _fence_set(pattern: str, paths: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    return {path for path in paths if _fence_matches(path, pattern)}


def _named_by(pattern: str, paths: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    """The paths ``pattern`` names for ``covers``; a glob with a trailing ``/`` is read both ways."""
    glob = any(char in pattern for char in "*?[")
    named = _fence_set(pattern, paths)  # a plain path names what lies below it, as the fence reads it
    if glob and pattern.endswith("/"):
        named |= {path for path in paths if _glob_prefix_matches(path, pattern)}
    return named


def test_covers_never_claims_a_path_the_fence_would_not_match():
    paths = _paths()
    named = {pattern: _named_by(pattern, paths) for pattern in _PATTERNS}
    fenced = {pattern: _fence_set(pattern, paths) for pattern in _PATTERNS}
    unsound = [
        (entry, hint)
        for entry, hint in itertools.product(_PATTERNS, repeat=2)
        if entry != hint and covers(entry, hint) and not named[entry] <= fenced[hint]
    ]
    assert unsound == []


def test_covers_is_reflexive_for_every_pattern_the_fence_accepts():
    assert [p for p in _PATTERNS if not covers(p, p)] == []


def test_covers_proves_something_among_the_brute_force_patterns():
    pairs = [(a, b) for a, b in itertools.product(_PATTERNS, repeat=2) if a != b and covers(a, b)]
    assert ("a/b", "a/**") in pairs
    assert ("a/**", "**") in pairs
    assert len(pairs) > 20


def test_a_covered_pattern_also_overlaps_what_covers_it():
    assert [
        (a, b) for a, b in itertools.product(_PATTERNS, repeat=2) if covers(a, b) and not globs_overlap(a, b)
    ] == []


# --- the moved overlap rule: the same battery the ready preview was proven with ----------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/a*.py", "src/*b.py"),
        ("src/*.py", "src/a?.py"),
        ("src/a**b", "src/ab"),
        ("a/**/c", "a/b/x/c"),
        ("src/**", "src"),
        ("**/*.py", "lib/x/y.py"),
        ("src/y.py", "**/x.py"),
        ("src/*", "src/a/b.py"),
        ("tests/", "tests/x/y.py"),
        ("./src//a/", "src/a/b.py"),
        ("src/[ab].py", "src/a.py"),
        ("src/[x", "src/[x/y"),
        ("src/*/", "src/a/b.py"),
        ("src/*/", "src/*/b.py"),
    ],
)
def test_globs_overlap_when_some_path_lies_under_both(left, right):
    assert globs_overlap(left, right)
    assert globs_overlap(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/*.py", "src/*.md"),
        ("src/a*.py", "src/b*.py"),
        ("src/a?.py", "src/abc.py"),
        ("src/*.py", "src/a/b.py"),
        ("a*/c", "ab/x/c"),
        ("tests/*.py", "tests/unit/x.py"),
        ("src/**/*.py", "lib/x.py"),
        ("src/[ab].py", "src/c.md"),
        ("docs/", "src/a/*.py"),
        ("src", "srcx/y"),
        ("src/*/", "lib/x"),
    ],
)
def test_globs_are_disjoint_only_when_no_path_lies_under_both(left, right):
    assert not globs_overlap(left, right)
    assert not globs_overlap(right, left)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("src/[!a].py", "src/a.py"),
        ("/abs/x", "src/y"),
        ("../x", "src/y"),
        ("src/../x", "lib/y"),
        ("src\\x", "lib/y"),
        ("C:/x", "lib/y"),
        ("~/x", "lib/y"),
        ("", "src"),
        (".", "src/x"),
        ("./", "src/x"),
    ],
)
def test_unsupported_or_root_patterns_may_overlap_anything(left, right):
    assert globs_overlap(left, right)
    assert globs_overlap(right, left)


def test_globs_overlap_never_misses_a_shared_path():
    paths = _paths()
    under = {pattern: _under(pattern, paths) for pattern in _PATTERNS}
    missed = [
        (left, right)
        for left, right in itertools.combinations_with_replacement(_PATTERNS, 2)
        if under[left] & under[right] and not globs_overlap(left, right)
    ]
    assert missed == []


def test_the_ready_preview_decides_overlap_by_the_shared_rule():
    from skm.modules.planning.domain import ready_preview

    assert ready_preview.globs_overlap is globs_overlap
    assert not hasattr(ready_preview, "_globs_overlap")


def test_bare_names_the_directory_without_dots_and_slashes():
    assert [bare(p) for p in ("lib/x/", "./lib/x", "lib//x", "lib/x", ".", "./")] == ["lib/x"] * 4 + [
        ".",
        "./",
    ]


# --- readiness, acceptance, decisions, context, routing variants -------------------------------------


INCOMPLETE_PARTS = [
    ("scope.include", _set("items/3/scope", {"include": [], "exclude": []})),
    ("deliverables", _set("items/3/deliverables", [])),
    (
        "reads",
        _all(
            _set("items/3/reads", []),
            _set("items/3/change_hints", []),
            _set("items/3/guidance_md", "<del>"),
            _set("items/3/sections", []),
        ),
    ),
    ("acceptance", _all(_set("checks/5/category", "impact"), _set("criteria/2/owner", "P1.2"))),
]


@pytest.mark.parametrize(("part", "mutate"), INCOMPLETE_PARTS, ids=[p[0] for p in INCOMPLETE_PARTS])
def test_incomplete_names_what_a_detailed_item_lacks(part, mutate):
    doc = _base()
    mutate(doc)
    parts = {str(f.details["missing"]) for f in _at(_run(doc), "incomplete") if f.entity_key == "P2.2"}
    assert part in parts


def test_incomplete_is_silent_for_a_skeleton_phase_and_flags_an_empty_detailed_phase():
    doc = _base()
    doc["items"][3]["deliverables"] = []
    doc["phases"][1]["design_state"] = "skeleton"
    assert "incomplete" not in _codes(_run(doc))
    doc = _base()
    doc["phases"].append(
        {
            "id": "0192f5c4-ffff-7000-8000-0000000000f1",
            "key": "P3",
            "title": "t",
            "goal": "g",
            "design_state": "detailed",
        }
    )
    (found,) = _at(_run(doc), "incomplete")
    assert (found.entity_key, found.details["missing"]) == ("P3", "items")


CRITERION_VARIANTS = [
    ("manual mode without a manual check", {"verification_mode": "manual", "checks": ["P1.2:V1"]}, "AC1"),
    (
        "review mode under a waived review",
        {"owner": "P2.3", "verification_mode": "review", "checks": []},
        "AC1",
    ),
]


@pytest.mark.parametrize(
    ("name", "changes", "key"), CRITERION_VARIANTS, ids=[v[0] for v in CRITERION_VARIANTS]
)
def test_criterion_unlinked_for_manual_and_review_modes(name, changes, key):
    doc = _base()
    doc["criteria"][0].update(changes)
    assert key in {f.entity_key for f in _at(_run(doc), "criterion_unlinked")}, name


def test_a_manual_criterion_with_a_manual_check_is_linked():
    doc = _base()
    doc["criteria"][0].update(owner="P2.3", verification_mode="manual", checks=["P2.3:V1"])
    assert "criterion_unlinked" not in _codes(_run(doc))
    assert "criterion_check_mismatch" not in _codes(_run(doc))


def test_the_acceptance_link_setting_lowers_criterion_unlinked_to_a_warning():
    doc = _base()
    doc["criteria"][0]["checks"] = []
    (found,) = _at(_run(doc), "criterion_unlinked")
    assert found.severity is Severity.ERROR
    (lowered,) = _at(_run(doc, settings=_settings(require_acceptance_links=False)), "criterion_unlinked")
    assert lowered.severity is Severity.WARNING
    assert not _run(doc, settings=_settings(require_acceptance_links=False)).has_errors(
        plugin_failures_block=True
    )


def test_criterion_check_mismatch_for_automatic_checks_in_manual_mode_and_manual_in_check_mode():
    doc = _base()
    doc["criteria"][0].update(owner="P2.3", verification_mode="manual", checks=["P2.3:V1", "P2.3:V2"])
    reasons = {str(f.details["reason"]) for f in _at(_run(doc), "criterion_check_mismatch")}
    assert reasons <= {"automatic_check_in_manual_mode"}
    doc = _base()
    doc["criteria"][3].update(verification_mode="check", checks=["P2.3:V1"])
    assert "manual_check_in_check_mode" in {
        str(f.details["reason"]) for f in _at(_run(doc), "criterion_check_mismatch")
    }


def test_a_criterion_may_use_the_check_of_the_item_of_its_unit_or_the_phase_of_its_owner():
    doc = _base()
    doc["criteria"][1]["checks"] = [
        "P2.1:V1",
        "P2:V1",
    ]  # owner P2.1/U2: the item's check; phase check is P1:V1 below
    assert "criterion_check_mismatch" not in {
        f.code for f in validate(_context(doc)).findings if f.pointer == "/criteria/1/checks/0"
    }
    doc["criteria"][1]["checks"] = ["P1:V1"]  # a check of another phase
    assert "criterion_check_mismatch" in _codes(_run(doc))


def test_a_should_requirement_without_owner_is_not_reported():
    doc = _base()
    doc["requirements"][1].pop("owners", None)
    doc["items"][3]["implements"] = []
    assert "requirement_unimplemented" not in _codes(_run(doc))


def test_a_must_requirement_is_implemented_by_an_item_or_a_criterion():
    for edit in (_append("items/0/implements", "R4"), _append("criteria/0/requirements", "R4")):
        doc = _base()
        doc["requirements"].append(
            {
                "id": "0192f5c4-ffff-7000-8000-0000000000aa",
                "key": "R4",
                "statement": "S",
                "priority": "must",
                "source": {"kind": "owner"},
            }
        )
        assert "requirement_unimplemented" in _codes(_run(doc))
        edit(doc)
        assert "requirement_unimplemented" not in _codes(_run(doc))


def test_check_cadence_ignores_phase_checks_and_unmarked_commands():
    doc = _base()
    assert "check_cadence" not in _codes(_run(doc))  # no markers by default
    report = _run(doc, settings=_settings(heavy_check_markers=("pytest",)))
    assert {f.entity_key for f in _at(report, "check_cadence")} >= {"P1.1:V1"}
    assert "P1:V1" not in {f.entity_key for f in _at(report, "check_cadence")}


def test_check_duplicate_command_compares_shell_scripts_after_strip():
    doc = _base()
    script = doc["checks"][1]["definition"]
    doc["checks"].append(
        _new_id(
            doc,
            _check("P1", "V2", kind="shell", definition={**script, "script": "  " + script["script"] + "\n"}),
        )
    )
    assert "P1.1:V2" in {f.entity_key for f in _at(_run(doc), "check_duplicate_command")}


DECISION_VARIANTS = [
    ("open without question", _set("decisions/1/question", "<del>"), "/decisions/1/question"),
    ("proposed and complete", _set("decisions/0/state", "proposed"), None),
    ("accepted without decision", _set("decisions/0/decision", "<del>"), "/decisions/0/decision"),
    ("a letter that is no option", _set("decisions/0/decision", "C"), "/decisions/0/decision"),
]


@pytest.mark.parametrize(
    ("name", "mutate", "pointer"), DECISION_VARIANTS, ids=[v[0] for v in DECISION_VARIANTS]
)
def test_decision_fields_triggers(name, mutate, pointer):
    doc = _base()
    mutate(doc)
    found = _at(_run(doc), "decision_fields")
    if pointer is None:
        assert [f.pointer for f in found] == [], name  # proposed with decision and rationale is complete
    else:
        assert pointer in {f.pointer for f in found}, name


def test_a_rejected_decision_and_a_prose_decision_need_nothing_more():
    doc = _base()
    doc["decisions"][0].update(state="rejected", decision="Use option A, as agreed.", rationale="r")
    assert "decision_fields" not in _codes(_run(doc))


SUPERSEDE_VARIANTS = [
    ("no superseder", _set("decisions/1/state", "superseded"), "no_superseder", "D2"),
    (
        "target not superseded",
        _new_decision("D3", supersedes=["D2"], applies_to=["P2.2"]),
        "target_not_superseded",
        "D3",
    ),
    (
        "two superseders",
        _all(
            _set("decisions/1/state", "superseded"),
            _new_decision("D3", supersedes=["D2"], applies_to=["P2.2"]),
            _new_decision("D4", supersedes=["D2"], applies_to=["P2.2"]),
        ),
        "multiple_superseders",
        "D2",
    ),
    (
        "superseder not accepted",
        _all(
            _set("decisions/1/state", "superseded"),
            _new_decision("D3", supersedes=["D2"], applies_to=["P2.2"], state="proposed"),
        ),
        "superseder_not_accepted",
        "D3",
    ),
]


@pytest.mark.parametrize(
    ("name", "mutate", "reason", "key"), SUPERSEDE_VARIANTS, ids=[v[0] for v in SUPERSEDE_VARIANTS]
)
def test_decision_superseded_orphan_triggers(name, mutate, reason, key):
    doc = _base()
    mutate(doc)
    assert (key, reason) in {
        (f.entity_key, f.details["reason"]) for f in _at(_run(doc), "decision_superseded_orphan")
    }, name


def test_a_proper_supersession_is_clean():
    doc = _base()
    _all(
        _set("decisions/1/state", "superseded"), _new_decision("D3", supersedes=["D2"], applies_to=["P2.2"])
    )(doc)
    assert "decision_superseded_orphan" not in _codes(_run(doc))


def test_context_unbound_is_satisfied_by_a_read_or_item_decisions_and_skips_open_decisions():
    doc = _base()
    _new_decision("D3")(doc)
    doc["items"][0]["decisions"] = ["D3"]
    assert "context_unbound" not in _codes(_run(doc))
    doc = _base()
    _new_decision("D3", state="open", question="q", decision=None, rationale=None)(doc)
    assert "context_unbound" not in _codes(_run(doc))
    doc = _base()
    doc["materials"][2]["applies_to"] = []  # oauth-threats: neither global, nor bound, nor read
    assert "material/oauth-threats" in {f.entity_key for f in _at(_run(doc), "context_unbound")}
    doc["items"][0]["reads"].append(
        {"kind": "material", "ref": "material/oauth-threats#s", "why": "w", "required": False}
    )
    assert "material/oauth-threats" not in {f.entity_key for f in _at(_run(doc), "context_unbound")}


def test_context_heavy_checks_every_kind_of_long_text_by_utf8_bytes():
    doc = _base()
    doc["brief"]["messages"][0]["text"] = "я" * 600  # 1200 UTF-8 bytes, 600 characters
    doc["items"][0]["sections"] = [{"id": "s", "title": "t", "text": HEAVY}]
    doc["sections"] = [{"id": "p", "title": "t", "text": HEAVY}]
    report = _run(doc, settings=_settings(heavy_text_bytes=1024))
    assert {f.pointer for f in _at(report, "context_heavy")} >= {
        "/brief/messages/0/text",
        "/items/0/sections/0/text",
        "/sections/0/text",
    }
    doc["brief"]["messages"][0]["text"] = "я" * 400  # 800 bytes
    assert "/brief/messages/0/text" not in {
        f.pointer for f in _at(_run(doc, settings=_settings(heavy_text_bytes=1024)), "context_heavy")
    }


def test_execution_prompt_heavy_sums_plan_rules_phase_pitfalls_item_rules_and_guidance():
    doc = _base()
    doc["rules"] = ["r" * 400]
    doc["phases"][0]["pitfalls"] = ["p" * 300]
    doc["items"][0]["rules"] = ["i" * 100]
    doc["items"][0]["guidance_md"] = "g" * 100  # 900 bytes in all
    settings = _settings(heavy_text_bytes=1024)
    assert "P1.1" not in {f.entity_key for f in _at(_run(doc, settings=settings), "execution_prompt_heavy")}
    doc["items"][0]["guidance_md"] = "g" * 300  # 1100 bytes
    assert "P1.1" in {f.entity_key for f in _at(_run(doc, settings=settings), "execution_prompt_heavy")}


def test_material_stale_age_boundaries_and_unknown_age():
    doc = _base()
    material = doc["materials"][2]
    material["freshness"]["max_age_seconds"] = 3600
    material["retrieved_at"] = (NOW - timedelta(seconds=3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert "material_stale" not in _codes(_run(doc))  # exactly at the limit is not older than it
    material["retrieved_at"] = (NOW - timedelta(seconds=3601)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert "material_stale" in _codes(_run(doc))
    material.pop("retrieved_at")
    assert "material_stale" in _codes(_run(doc))  # an unknown age is stale


def test_a_must_refresh_file_version_is_judged_by_its_creation_time_and_unavailable_is_not_stale():
    doc = _base()
    doc["materials"][0]["freshness"] = {"policy": "must_refresh", "max_age_seconds": 3600}
    old = {FILE_VERSION: FileVersionObservation(FileVersionStatus.READY, NOW - timedelta(hours=2))}
    assert "material_stale" in _codes(_run(doc, file_versions=old))
    gone = {FILE_VERSION: FileVersionObservation(FileVersionStatus.NOT_READY, NOW - timedelta(hours=2))}
    report = _run(doc, file_versions=gone)
    assert "material_stale" not in _codes(report)
    assert "material_unavailable" in _codes(report)


@pytest.mark.parametrize(
    "status", [FileVersionStatus.NOT_READY, FileVersionStatus.MISSING, FileVersionStatus.OTHER_WORKSPACE]
)
def test_every_file_version_status_but_ready_is_unavailable(status):
    report = _run(_base(), file_versions={FILE_VERSION: FileVersionObservation(status, None)})
    (found,) = _at(report, "material_unavailable")
    assert found.details["status"] == status.value


def test_a_missing_observation_is_unavailable_and_a_repository_path_never_is():
    report = _run(_base(), file_versions={})
    assert [f.entity_key for f in _at(report, "material_unavailable")] == ["material/storage-design"]


def test_a_missing_catalog_reports_nothing_and_an_empty_one_reports_everything():
    assert _codes(_run(_base(), runtime_catalog=None, known_skills=None)).isdisjoint(
        {"route_unknown_runtime", "route_unknown_model", "skill_unknown"}
    )
    doc = _base()
    doc["items"][0]["route"] = {"class": "implementation", "effort": "medium", "runtime": "codex"}
    report = _run(doc, runtime_catalog={}, known_skills=frozenset())
    assert {"route_unknown_runtime", "skill_unknown"} <= _codes(report)


def test_an_unknown_runtime_is_not_also_an_unknown_model():
    report = _run(_base(), runtime_catalog={"claude": frozenset({"opus"})})
    assert [f.entity_key for f in _at(report, "route_unknown_runtime")] == ["P2.2"]
    assert "route_unknown_model" not in _codes(report)


# --- the semantic validation corpus --------------------------------------------------------------------


MANIFEST = _load("expected-semantic-findings.json")


@pytest.mark.parametrize(
    "entry", MANIFEST["fixtures"], ids=[Path(e["file"]).stem for e in MANIFEST["fixtures"]]
)
def test_the_semantic_corpus_is_rejected_by_the_validator_with_the_listed_findings(entry, registry):
    doc = _load(entry["file"])
    registry.require_valid(SPECIFICATION, doc)  # schema-valid: the validator is the one that rejects it
    before = json.dumps(doc, sort_keys=True)
    report = _run(doc)
    assert report.rule_failures == ()
    hits = [f for f in _at(report, entry["code"]) if f.entity_key == entry["entity_key"]]
    assert hits, [(f.code, f.entity_key, f.pointer) for f in report.findings]
    assert entry["locus"] in {f.pointer for f in hits}
    assert {f.severity.value for f in hits} == {entry["severity"]}
    assert report.has_errors(plugin_failures_block=False)
    baseline = {f.code for f in _run(_base()).findings}
    companions = {entry["code"], *entry["allowed_companion_codes"]}
    unexpected = _codes(report) - companions - baseline
    assert unexpected == set()
    assert json.dumps(doc, sort_keys=True) == before  # the input is byte-identical


def test_every_semantic_fixture_is_listed_and_every_listed_file_exists():
    names = sorted(
        p.name for p in (FIXTURES / "invalid").glob("*.json") if not p.name.startswith("SCHEMA_INVALID")
    )
    assert names == sorted(Path(e["file"]).name for e in MANIFEST["fixtures"])


# --- purity ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(p.name for p in (FIXTURES / "valid").glob("*.json")))
def test_validation_never_mutates_the_document_or_the_specification(name):
    doc, _ = assign_missing_ids(_load(f"valid/{name}"), _Ids())
    spec, _ = from_document(doc)
    before_doc, before_spec = json.dumps(doc, sort_keys=True), json.dumps(to_document(spec), sort_keys=True)
    ctx = _context(doc, project_mounts=_mounts(doc) | {"api"})
    first, second = validate(ctx), validate(ctx)
    assert first == second  # deterministic
    assert json.dumps(doc, sort_keys=True) == before_doc
    assert json.dumps(to_document(spec), sort_keys=True) == before_spec


def test_a_mutating_rule_is_not_the_validators_business_but_a_clean_rule_leaves_the_context_alone():
    doc = _base()
    ctx = _context(doc)
    snapshot = copy.deepcopy(doc)
    for rule in DEFAULT_RULES:
        list(rule(ctx))
    assert doc == snapshot


# --- rule failures -----------------------------------------------------------------------------------


def test_a_rule_that_raises_is_a_rule_failure_and_never_a_finding():
    def broken(ctx: ValidationContext):
        yield finding(FindingCode.INCOMPLETE, "half done")  # produced before the exception: discarded with it
        raise TypeError("a defect of the rule")

    report = validate(_context(_base()), rules=(broken,))
    assert report.findings == ()
    assert report.rule_failures == (RuleFailure("broken", "TypeError", "a defect of the rule", None),)
    assert report.has_errors(plugin_failures_block=False)  # a built-in rule blocks whatever the setting says


def test_a_defect_of_a_builtin_rule_is_not_shown_as_an_invalid_plan():
    report = _run(_base(), runtime_catalog=5)  # not a catalog at all: the routing rules cannot work
    failed = {failure.rule for failure in report.rule_failures}
    assert {"route_unknown_model", "route_unknown_runtime"} <= failed
    assert all(failure.plugin is None for failure in report.rule_failures)
    assert _codes(report) == BASELINE  # the user's plan is as valid as before
    assert report.has_errors(plugin_failures_block=False)


def test_a_failing_rule_does_not_stop_the_others():
    def broken(ctx: ValidationContext):
        raise KeyError("x")

    report = validate(_context(_base()), rules=(broken, *DEFAULT_RULES))
    assert len(report.rule_failures) == 1
    assert _codes(report) == BASELINE


def test_a_rule_that_returns_something_else_than_findings_fails_as_a_rule():
    report = validate(_context(_base()), rules=(cast("Rule", lambda ctx: ["not a finding"]),))
    assert [f.error_type for f in report.rule_failures] == ["TypeError"]


def test_exceptions_that_are_not_errors_are_not_swallowed():
    def interrupted(ctx: ValidationContext):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        validate(_context(_base()), rules=(interrupted,))


def _plugin_finding(code: str = "x_acme_naming", severity: Severity = Severity.WARNING) -> Finding:
    return Finding(code, severity, "plugin says", "P1.1", None, "/items/0", {})


def test_a_plugin_finding_is_reported_and_a_plugin_failure_blocks_only_by_setting():
    good = PluginRule("acme.naming", lambda ctx: [_plugin_finding()])
    bad = PluginRule("acme.broken", cast("Rule", lambda ctx: 1 / 0))
    report = validate(_context(_base()), plugin_rules=(good, bad))
    assert "x_acme_naming" in _codes(report)
    (failure,) = report.rule_failures
    assert (failure.plugin, failure.error_type) == ("acme.broken", "ZeroDivisionError")
    assert not report.has_errors(plugin_failures_block=False)  # external_failure = warn
    assert report.has_errors(plugin_failures_block=True)  # external_failure = error


@pytest.mark.parametrize(
    "bad",
    [
        _plugin_finding(code="incomplete"),  # a core code is not the plugin's to use
        _plugin_finding(code="x_acme"),  # not x_<publisher>_<name>
        _plugin_finding(severity=Severity.ERROR),  # a plugin is a warning at most
        "text",
    ],
    ids=["core_code", "malformed_code", "error_severity", "not_a_finding"],
)
def test_a_plugin_result_outside_the_contract_is_a_plugin_failure(bad):
    report = validate(_context(_base()), plugin_rules=(PluginRule("acme.rule", lambda ctx: [bad]),))
    assert [(f.plugin, f.error_type in ("ValueError", "TypeError")) for f in report.rule_failures] == [
        ("acme.rule", True)
    ]
    assert _codes(report) == BASELINE


@pytest.mark.parametrize(
    "bad",
    [
        Finding("x_acme_bad", Severity.WARNING, "bad", None, None, cast("Any", 7), {}),
        Finding("x_acme_bad", Severity.WARNING, "bad", cast("Any", 7), None, None, {}),
        Finding("x_acme_bad", Severity.WARNING, "bad", None, cast("Any", "not-an-id"), None, {}),
        Finding("x_acme_bad", Severity.WARNING, "bad", None, None, None, cast("Any", {"a": object()})),
        Finding("x_acme_bad", Severity.WARNING, "bad", None, None, None, cast("Any", {1: "a"})),
        Finding("x_acme_bad", Severity.WARNING, "bad", None, None, None, cast("Any", {"a": [{"b": {1, 2}}]})),
        Finding("x_acme_bad", Severity.WARNING, "bad", None, None, None, {"a": float("nan")}),
    ],
    ids=[
        "pointer",
        "entity_key",
        "entity_id",
        "details_object",
        "details_key",
        "details_nested",
        "details_nan",
    ],
)
def test_a_plugin_finding_with_a_malformed_field_is_a_plugin_failure_and_never_raises(bad):
    good = PluginRule("acme.good", lambda ctx: [_plugin_finding()])
    plugin = PluginRule("acme.bad", lambda ctx: [_plugin_finding("x_acme_other"), bad])
    report = validate(_context(_base()), plugin_rules=(plugin, good))
    assert [f.plugin for f in report.rule_failures] == ["acme.bad"]
    assert {"x_acme_naming"} == _codes(report) - BASELINE  # nothing of the failed rule is kept
    assert not report.has_errors(plugin_failures_block=False)
    assert report.has_errors(plugin_failures_block=True)


def test_a_builtin_finding_with_a_malformed_field_is_a_blocking_rule_failure():
    broken = Finding("incomplete", Severity.ERROR, "x", None, None, cast("Any", 7), {})
    report = validate(_context(_base()), rules=(lambda ctx: [broken],))
    assert report.findings == ()
    assert [(f.error_type, f.plugin) for f in report.rule_failures] == [("TypeError", None)]
    assert report.has_errors(plugin_failures_block=False)


def test_a_plugin_finding_with_every_field_set_and_nested_details_is_accepted():
    entity = _base()["items"][0]["id"]
    ok = Finding(
        "x_acme_full",
        Severity.WARNING,
        "ok",
        "P1.1",
        EntityId(UUID(entity)),
        "/items/0",
        {"a": [1, 2.5, {"b": None}]},
    )
    report = validate(_context(_base()), plugin_rules=(PluginRule("acme.full", lambda ctx: [ok]),))
    assert report.rule_failures == ()
    assert ok in report.findings


def test_plugin_rules_do_not_run_when_external_checks_are_off():
    calls: list[int] = []

    def rule(ctx: ValidationContext):
        calls.append(1)
        return []

    validate(
        _context(_base(), settings=_settings(external_checks=False)), plugin_rules=(PluginRule("p", rule),)
    )
    assert calls == []
    validate(_context(_base()), plugin_rules=(PluginRule("p", rule),))
    assert calls == [1]


def test_a_builtin_rule_cannot_hide_behind_the_plugin_setting():
    def broken(ctx: ValidationContext):
        raise RuntimeError("infrastructure")

    report = validate(_context(_base()), rules=(broken,), plugin_rules=(PluginRule("p", lambda ctx: []),))
    assert report.has_errors(plugin_failures_block=False)
    assert report.rule_failures[0].plugin is None


def test_the_compiler_failing_is_a_validator_defect(monkeypatch):
    def explode(spec, revision_id=None):
        raise RuntimeError("compiler bug")

    monkeypatch.setattr(pipeline, "compile_execution_graph", explode)
    report = validate(_context(_base()), rules=())
    assert report.graph is None
    assert [(f.rule, f.error_type) for f in report.rule_failures] == [
        ("compile_execution_graph", "RuntimeError")
    ]


# --- the report ---------------------------------------------------------------------------------------


def test_findings_are_sorted_by_severity_then_pointer_then_code():
    def noisy(ctx: ValidationContext):
        yield finding(FindingCode.PHASE_SKELETON, "i", pointer="/a")
        yield finding(FindingCode.INCOMPLETE, "e2", pointer="/b")
        yield finding(FindingCode.SELF_REFERENCE, "e1", pointer="/a")
        yield finding(FindingCode.DUPLICATE_ID, "e0", pointer="/a")
        yield finding(FindingCode.CONTEXT_DEFAULT, "w", pointer="/a")
        yield finding(FindingCode.PHASE_SKELETON, "none", pointer=None)

    report = validate(_context(_base()), rules=(noisy,))
    assert [(f.severity.value, f.pointer, f.code) for f in report.findings] == [
        ("error", "/a", "duplicate_id"),
        ("error", "/a", "self_reference"),
        ("error", "/b", "incomplete"),
        ("warning", "/a", "context_default"),
        ("info", None, "phase_skeleton"),
        ("info", "/a", "phase_skeleton"),
    ]


def test_counts_and_has_errors():
    warn = finding(FindingCode.CONTEXT_DEFAULT, "w")
    info = finding(FindingCode.PHASE_SKELETON, "i")
    error = finding(FindingCode.INCOMPLETE, "e")
    assert dict(ValidationReport((), (), None).counts()) == {
        Severity.ERROR: 0,
        Severity.WARNING: 0,
        Severity.INFO: 0,
    }
    mixed = ValidationReport((error, warn, info, info), (), None)
    assert dict(mixed.counts()) == {Severity.ERROR: 1, Severity.WARNING: 1, Severity.INFO: 2}
    assert mixed.has_errors(plugin_failures_block=False)
    assert not ValidationReport((warn, info), (), None).has_errors(plugin_failures_block=True)
    plugin_failure = RuleFailure("r", "E", "m", "acme.rule")
    builtin_failure = RuleFailure("r", "E", "m", None)
    assert not ValidationReport((), (plugin_failure,), None).has_errors(plugin_failures_block=False)
    assert ValidationReport((), (plugin_failure,), None).has_errors(plugin_failures_block=True)
    assert ValidationReport((), (builtin_failure,), None).has_errors(plugin_failures_block=False)


def test_a_finding_carries_the_catalog_severity_and_frozen_details():
    found = finding(FindingCode.WRITE_SCOPE_EMPTY, "m", details={"a": 1})
    assert found.severity is Severity.WARNING
    with pytest.raises(TypeError):
        found.details["b"] = 2  # type: ignore[index]


def test_validation_settings_are_read_from_the_resolved_section_and_a_broken_one_is_a_failure():
    read = ValidationSettings.of(SETTINGS)
    assert (read.require_acceptance_links, read.external_checks, read.heavy_text_bytes) == (True, True, 16384)
    assert ".py" in read.code_suffixes
    assert read.heavy_check_markers == ()
    report = validate(_context(_base(), settings={"validation": {"external_checks": True}}))
    assert {failure.rule for failure in report.rule_failures} >= {
        "settings",
        "criterion_unlinked",
        "check_cadence",
    }
    assert report.has_errors(plugin_failures_block=False)
    assert _codes(report).isdisjoint({"criterion_unlinked", "check_cadence", "context_heavy"})


# --- the porting table --------------------------------------------------------------------------------


def _porting_rows() -> Iterator[tuple[str, str, str]]:
    in_table = False
    for line in PORTING.read_text().splitlines():
        if line.startswith("## Legacy to canonical"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            return
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if in_table and line.startswith("| `") and len(cells) >= 3:
            yield cells[0].strip("`"), cells[1], cells[2]


def test_every_legacy_code_has_one_explicit_verdict_consistent_with_the_catalog(catalog):
    rows = list(_porting_rows())
    legacy = [code for code, _, _ in rows]
    assert len(legacy) == len(set(legacy))
    ancestry: dict[str, set[str]] = {}
    for entry in catalog["codes"]:
        for old in entry["legacy_codes"]:
            ancestry.setdefault(old, set()).add(entry["code"])
    dropped = set(catalog["dropped_legacy_codes"])
    assert set(legacy) == set(ancestry) | dropped
    canonical = {entry["code"] for entry in catalog["codes"]}
    for old, verdict, targets in rows:
        assert verdict in {"retain", "map", "drop", "overlay"}, old
        named = set(re.findall(r"`([a-z_]+)`", targets))
        if verdict in ("retain", "map"):
            assert named == ancestry[old], old
            assert named <= canonical, old
            assert (verdict == "retain") == (named == {old}), old
        else:
            assert old in dropped, old
            assert not named, old
    assert {old for old, verdict, _ in rows if verdict == "overlay"} == {
        "execution_commit_instruction",
        "execution_rules_conflict",
    }


def test_every_canonical_code_is_either_ancestry_of_a_legacy_code_or_listed_as_new(catalog):
    text = PORTING.read_text()
    new_section = text.split("## Canonical codes with no legacy ancestor", 1)[1].split("\n## ", 1)[0]
    listed = set(re.findall(r"^\| `([a-z_]+)` \|", new_section, re.M))
    assert listed == {entry["code"] for entry in catalog["codes"] if not entry["legacy_codes"]}
