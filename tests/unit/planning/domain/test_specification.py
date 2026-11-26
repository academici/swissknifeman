"""The typed specification: round trip, explicit defaults, findings, indexes and work-policy value object."""

import copy
import dataclasses
import json
import pickle
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import EntityId
from skm.modules.planning.domain import item as item_module
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.check_spec import CheckKind, CheckSpec, CommandDefinition, ShellDefinition
from skm.modules.planning.domain.item import (
    Intensity,
    Item,
    ModelClass,
    RoleName,
    Routine,
    WorkKind,
    WorkPolicyOverride,
    work_policy_from_doc,
    work_policy_to_doc,
)
from skm.modules.planning.domain.material import Material
from skm.modules.planning.domain.review_requirement import RequiredReview, WaivedReview
from skm.modules.planning.domain.specification import Specification, from_document, to_document
from skm.modules.planning.domain.unit import Unit, UnitKind, UnitMode
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/plans"
DOMAIN = ROOT / "src/skm/modules/planning/domain"
SPECIFICATION = "urn:skm:planning:specification:v1"


def _doc() -> dict[str, Any]:
    return json.loads((EXAMPLES / "auth-refresh.specification.json").read_text())


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _entity[T](spec: Specification, key: str, kind: type[T]) -> T:
    entity = spec.by_key(key)
    assert isinstance(entity, kind), key
    return entity


def _strip_defaults(doc: dict[str, Any]) -> dict[str, Any]:
    """The example without the members from_document writes explicitly (planning §5.1)."""
    out = copy.deepcopy(doc)
    for item in out["items"]:
        for name, default in (
            ("work_kind", "code"),
            ("unit_strategy", "dag"),
            ("authority", {"kind": "routine"}),
        ):
            if item.get(name) == default:
                del item[name]
    for unit in out["units"]:
        for name, default in (("unit_kind", "implementation"), ("mode", "either")):
            if unit.get(name) == default:
                del unit[name]
    for check in out["checks"]:
        check.pop("evidence", None)
    return out


def test_round_trip_of_the_owner_example_is_the_identity_and_never_mutates_the_input(registry):
    doc = _doc()
    before = copy.deepcopy(doc)
    spec, findings = from_document(doc)
    assert findings == ()
    assert doc == before
    out: dict[str, Any] = to_document(spec)
    registry.require_valid(SPECIFICATION, out)
    explicit = {
        "items": ("work_kind", "unit_strategy"),
        "units": ("mode", "unit_kind"),
        "phases": ("strategy",),
    }
    for array, names in explicit.items():  # the only differences are explicit defaults
        for original, rebuilt in zip(doc[array], out[array], strict=True):
            assert {k: v for k, v in rebuilt.items() if k not in names or k in original} == original
    for original, rebuilt in zip(doc["checks"], out["checks"], strict=True):
        written = {"evidence", "rerun_after_integration", "definition"}
        assert {
            k: v for k, v in rebuilt.items() if k not in written or (k in original and k != "definition")
        } == {k: v for k, v in original.items() if k != "definition"}
        assert {
            k: v
            for k, v in rebuilt["definition"].items()
            if k != "timeout_seconds" or k in original["definition"]
        } == original["definition"]
    assert to_document(from_document(out)[0]) == out


def test_meaningful_defaults_are_written_explicitly():
    out: dict[str, Any] = to_document(from_document(_strip_defaults(_doc()))[0])
    assert all(i["work_kind"] and i["unit_strategy"] == "dag" and i["authority"] for i in out["items"])
    assert all(u["unit_kind"] == "implementation" and u["mode"] == "either" for u in out["units"][:2])
    assert all(c["evidence"] == {"stdout": True, "stderr": True} for c in out["checks"])
    assert all(isinstance(c["required"], bool) for c in out["checks"])
    assert all(p["strategy"] == "dag" for p in out["phases"])
    assert out["execution_constraints"]["strategy"] == "dag"
    assert out["items"][0]["review"]["independence"] == "separate_session"


def test_check_required_defaults_to_acceptance_and_is_stored():
    doc = _doc()
    for check in doc["checks"]:
        check.pop("required", None)
    spec, _ = from_document(doc)
    assert [(c.category.value, c.required) for c in spec.checks if c.owner == "P1"] == [("impact", False)]
    assert all(c.required for c in spec.checks if c.category.value == "acceptance")
    out: dict[str, Any] = to_document(spec)
    assert all("required" in c for c in out["checks"])


def test_phase_depends_on_absent_is_not_filled_in():
    spec, _ = from_document(_doc())
    assert spec.phases[0].depends_on == ()
    assert spec.phases[1].depends_on is None
    out: dict[str, Any] = to_document(spec)
    assert "depends_on" not in out["phases"][1]
    assert out["phases"][0]["depends_on"] == []


def test_records_are_frozen_and_collections_are_tuples():
    spec, _ = from_document(_doc())
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.title = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.items[0].title = "x"  # type: ignore[misc]
    assert isinstance(spec.items, tuple)
    assert isinstance(spec.items[0].implements, tuple)
    definition = spec.checks[0].definition
    assert isinstance(definition, CommandDefinition)
    assert isinstance(definition.argv, tuple)
    with pytest.raises(TypeError):
        spec.extensions["x/y"] = {}  # type: ignore[index]
    assert not hasattr(spec.items[0], "__dict__")


def test_union_members_are_typed_not_loose_objects():
    spec, _ = from_document(_doc())
    assert isinstance(_entity(spec, "P2.1", Item).review, RequiredReview)
    assert isinstance(_entity(spec, "P2.3", Item).review, WaivedReview)
    assert isinstance(_entity(spec, "P1.1", Item).authority, Routine)
    assert isinstance(_entity(spec, "P1.1:V1", CheckSpec).definition, CommandDefinition)
    assert isinstance(_entity(spec, "P1.1:V2", CheckSpec).definition, ShellDefinition)
    assert _entity(spec, "P1.1:V2", CheckSpec).kind is CheckKind.SHELL
    assert _entity(spec, "P1.1/U2", Unit).unit_kind is UnitKind.IMPLEMENTATION
    assert _entity(spec, "P1.1/U2", Unit).mode is UnitMode.EITHER
    assert _entity(spec, "P1.1", Item).work_kind is WorkKind.CODE
    route = _entity(spec, "P1.1", Item).route
    assert route is not None
    assert route.model_class in ModelClass


def test_ids_come_from_the_document_and_are_the_lookup_key():
    spec, _ = from_document(_doc())
    item = spec.by_key("P1.2")
    assert item.id == EntityId(UUID("0192f5c4-0000-7000-8000-000000000015"))
    assert spec.entity(item.id) is item
    check = spec.by_key("P1.2:V1")
    assert spec.display_key(check) == "P1.2:V1"
    assert spec.by_key("P2.1:V1") is not check
    assert spec.display_key(spec.by_key("material/storage-design")) == "material/storage-design"


def test_lookups_report_not_found_with_the_reference():
    spec, _ = from_document(_doc())
    with pytest.raises(NotFound) as by_key:
        spec.by_key("P9.9")
    assert dict(by_key.value.details) == {"kind": "entity", "ref": "P9.9"}
    unknown = UUID("0192f5c4-0000-7000-8000-0000000000aa")
    with pytest.raises(NotFound) as by_id:
        spec.entity(EntityId(unknown))
    assert by_id.value.details["ref"] == str(unknown)


def test_owner_indexes_and_inheriting_accessors():
    spec, _ = from_document(_doc())
    assert [i.key for i in spec.items_of("P2")] == ["P2.1", "P2.2", "P2.3"]
    assert [u.key for u in spec.units_of("P1.1")] == ["P1.1/U1", "P1.1/U2"]
    assert [c.key for c in spec.checks_of("P1.1")] == ["V1", "V2"]
    assert [c.key for c in spec.criteria_of("P1.2")] == ["AC1"]
    unit = spec.by_key("P1.1/U1")
    assert [e.key for e in spec.ancestors(unit.id)] == ["P1.1", "P1"]
    owner = _entity(spec, "P1.1", Item)
    assert spec.review_requirement_for(unit.id) == owner.review
    assert spec.route_for(unit.id) == owner.route
    assert spec.work_kind_for(unit.id) == "code"
    write_scope = spec.declared_write_scope_for(unit.id)
    assert write_scope is not None
    assert [r.pattern for r in write_scope] == ["migrations/versions/*.py"]
    assert spec.declared_write_scope_for(spec.by_key("P1.1").id) is None
    assert [c.key for c in spec.checks_for(spec.by_key("P1.2").id)] == ["V1"]
    assert [c.key for c in spec.criteria_for(spec.by_key("P2.1/U2").id)] == ["AC2"]
    assert spec.change_hints_for(unit.id) == owner.change_hints


def test_duplicate_keys_are_findings_and_the_model_keeps_the_first_occurrence():
    doc = _doc()
    twin = copy.deepcopy(doc["items"][1])
    twin["id"] = "0192f5c4-0000-7000-8000-0000000000ee"
    twin["title"] = "second P1.2"
    doc["items"].append(twin)
    twin_check = copy.deepcopy(doc["checks"][0])
    twin_check["id"] = "0192f5c4-0000-7000-8000-0000000000ef"
    doc["checks"].append(twin_check)
    unrelated = copy.deepcopy(doc["checks"][0])
    unrelated["id"] = "0192f5c4-0000-7000-8000-0000000000f0"
    unrelated["owner"] = "P1.2"  # P1.2:V1 exists: the same local key under another owner is a duplicate here
    doc["checks"].append(unrelated)
    spec, findings = from_document(doc)
    assert sorted((f.code, f.entity_key, f.pointer) for f in findings) == [
        ("duplicate_key", "P1.1:V1", "/checks/8/key"),
        ("duplicate_key", "P1.2", "/items/5/key"),
        ("duplicate_key", "P1.2:V1", "/checks/9/key"),
    ]
    assert _entity(spec, "P1.2", Item).title != "second P1.2"
    assert len(spec.items) == 5
    assert len(spec.checks) == 8


def test_same_local_check_key_under_another_owner_is_not_a_duplicate():
    spec, findings = from_document(_doc())
    assert findings == ()
    assert len([c for c in spec.checks if c.key == "V1"]) == 6


def test_item_key_prefix_must_match_its_phase():
    doc = _doc()
    doc["items"][1]["phase"] = "P2"
    spec, findings = from_document(doc)
    (finding,) = findings
    assert (finding.code, finding.entity_key, finding.pointer) == (
        "key_prefix_mismatch",
        "P1.2",
        "/items/1/key",
    )
    assert _entity(spec, "P1.2", Item).phase == "P2"  # the model is still built so the other rules can run


def test_entity_ids_are_required_to_build_the_model():
    doc = _doc()
    del doc["requirements"][0]["id"]
    with pytest.raises(ValidationFailed) as raised:
        from_document(doc)
    assert raised.value.details["key"] == "R1"


def test_brief_dates_and_timestamps_round_trip():
    out: dict[str, Any] = to_document(from_document(_doc())[0])
    assert [m["at"] for m in out["brief"]["messages"]] == ["2026-10-20", "2026-10-21T09:30:00Z"]
    assert out["brief"]["environment"] == ["Python 3.12 API, TypeScript web client."]


FRACTIONS = ("", ".0", ".5", ".50", ".120", ".0001", ".00000", ".000000", ".123456", ".999999")


def _with_timestamps(fraction: str) -> dict[str, Any]:
    """The example with ``fraction`` written into a brief message ``at`` and a material ``retrieved_at``."""
    doc = _doc()
    doc["brief"]["messages"][1]["at"] = f"2026-10-21T09:30:00{fraction}Z"
    material = next(m for m in doc["materials"] if m["key"] == "oauth-threats")
    material["retrieved_at"] = f"2026-10-21T10:00:00{fraction}Z"
    return doc


@pytest.mark.parametrize("fraction", FRACTIONS)
def test_fractional_timestamps_round_trip_exactly_and_keep_the_digest(registry, fraction):
    doc = _with_timestamps(fraction)
    registry.require_valid(SPECIFICATION, doc)
    spec, _ = from_document(doc)
    out: dict[str, Any] = to_document(spec)
    assert out == normalize_document(doc)
    assert specification_digest(out) == specification_digest(doc)
    assert out["brief"]["messages"][1]["at"] == f"2026-10-21T09:30:00{fraction}Z"
    material = next(m for m in out["materials"] if m["key"] == "oauth-threats")
    assert material["retrieved_at"] == f"2026-10-21T10:00:00{fraction}Z"
    assert spec.brief is not None
    retrieved_at = _entity(spec, "material/oauth-threats", Material).retrieved_at
    for value, text in (
        (spec.brief.messages[1].at, f"2026-10-21T09:30:00{fraction}Z"),
        (retrieved_at, f"2026-10-21T10:00:00{fraction}Z"),
    ):
        assert isinstance(value, datetime)  # the typed contract: an aware UTC datetime of the written instant
        assert value.utcoffset() == timedelta(0)
        assert value == datetime.fromisoformat(text)


def test_fraction_precision_is_part_of_the_document_not_of_the_instant():
    short, padded = _with_timestamps(".5"), _with_timestamps(".500000")
    short_spec, padded_spec = from_document(short)[0], from_document(padded)[0]
    assert short_spec.brief is not None
    assert padded_spec.brief is not None
    assert short_spec.brief.messages[1].at == padded_spec.brief.messages[1].at
    assert to_document(short_spec) != to_document(padded_spec)
    assert specification_digest(to_document(short_spec)) == specification_digest(short)
    assert specification_digest(to_document(padded_spec)) == specification_digest(padded)
    assert specification_digest(short) != specification_digest(padded)


def _brief_at(spec: Specification) -> datetime:
    assert spec.brief is not None
    at = spec.brief.messages[1].at
    assert isinstance(at, datetime)
    return at


@pytest.mark.parametrize(("written", "fold"), [("2026-10-25T00:30:00.5Z", 0), ("2026-10-25T01:30:00.5Z", 1)])
def test_copies_keep_timestamps_across_the_paris_dst_end(written, fold):
    doc = _doc()
    doc["brief"]["messages"][1]["at"] = written
    spec = from_document(doc)[0]
    assert spec.brief is not None
    message = dataclasses.replace(
        spec.brief.messages[1], at=_brief_at(spec).astimezone(ZoneInfo("Europe/Paris"))
    )
    messages = (*spec.brief.messages[:1], message, *spec.brief.messages[2:])
    local = dataclasses.replace(spec, brief=dataclasses.replace(spec.brief, messages=messages))
    assert (_brief_at(spec).tzinfo, _brief_at(local).hour, _brief_at(local).fold) == (UTC, 2, fold)
    for original, text in ((spec, written), (local, written.replace(".5Z", ".500000Z"))):
        brief = original.brief  # a specification neither copies nor pickles (mapping proxies); its brief does
        assert brief is not None
        pickled = [pickle.loads(pickle.dumps(brief, p)) for p in range(pickle.HIGHEST_PROTOCOL + 1)]  # noqa: S301
        for twin_brief in (copy.deepcopy(brief), *pickled):
            twin = dataclasses.replace(original, brief=twin_brief)
            at, original_at = _brief_at(twin), _brief_at(original)
            assert at is not original_at
            assert (at.tzinfo, at.fold) == (original_at.tzinfo, original_at.fold)
            assert at.utcoffset() == original_at.utcoffset()
            later = timedelta(hours=1)
            assert (at + later).astimezone(UTC) == (original_at + later).astimezone(UTC)
            out: dict[str, Any] = to_document(twin)
            assert out == to_document(original)
            assert out["brief"]["messages"][1]["at"] == text


def test_extensions_are_kept_as_a_copy():
    doc = _doc()
    doc["extensions"] = {"acme/audit": {"schema_version": 1, "value": {"tags": ["a"]}}}
    spec, _ = from_document(doc)
    doc["extensions"]["acme/audit"]["value"]["tags"].append("b")
    assert spec.extensions["acme/audit"]["value"] == {"tags": ["a"]}
    assert to_document(spec)["extensions"] == {"acme/audit": {"schema_version": 1, "value": {"tags": ["a"]}}}


# ------------------------------------------------------------------------------------- work policy


def test_work_policy_absent_and_empty_round_trip_differently():
    doc = _doc()
    doc["items"][0]["work_policy"] = {}
    doc["items"][1]["work_policy"] = {"role_intensity": {}}
    spec, _ = from_document(doc)
    out: dict[str, Any] = to_document(spec)
    assert spec.items[0].work_policy == WorkPolicyOverride()
    assert spec.items[2].work_policy is None
    assert out["items"][0]["work_policy"] == {}
    assert "work_policy" not in out["items"][2]
    assert out["items"][1]["work_policy"] == {"role_intensity": {}}
    assert WorkPolicyOverride() != WorkPolicyOverride({})


def test_work_policy_is_closed_immutable_and_never_gains_effective_values():
    policy = work_policy_from_doc({"role_intensity": {"executor": "light"}})
    assert work_policy_to_doc(policy) == {"role_intensity": {"executor": "light"}}
    with pytest.raises(TypeError):
        policy.role_intensity[RoleName.SCOUT] = Intensity.HEAVY  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.verification_intensity = Intensity.HEAVY  # type: ignore[misc]
    with pytest.raises(ValueError, match="boss"):
        work_policy_from_doc({"role_intensity": {"boss": "light"}})
    with pytest.raises(ValueError, match="extreme"):
        work_policy_from_doc({"verification_intensity": "extreme"})
    assert [r.value for r in RoleName] == [
        "scout",
        "executor",
        "reviewer",
        "triager",
        "advisor",
        "researcher",
        "registrar",
    ]
    assert [i.value for i in Intensity] == ["light", "medium", "heavy"]


def test_partial_role_merge_inherits_what_is_absent():
    item = WorkPolicyOverride(
        {RoleName.EXECUTOR: Intensity.HEAVY, RoleName.REVIEWER: Intensity.MEDIUM}, Intensity.LIGHT
    )
    unit = WorkPolicyOverride({RoleName.EXECUTOR: Intensity.LIGHT})
    effective = unit.merged_over(item)
    assert effective.role_intensity is not None
    assert dict(effective.role_intensity) == {
        RoleName.EXECUTOR: Intensity.LIGHT,
        RoleName.REVIEWER: Intensity.MEDIUM,
    }
    assert effective.verification_intensity is Intensity.LIGHT
    assert WorkPolicyOverride().merged_over(item) == item  # {} overrides nothing
    assert item.role_intensity is not None
    assert dict(item.role_intensity) == {
        RoleName.EXECUTOR: Intensity.HEAVY,
        RoleName.REVIEWER: Intensity.MEDIUM,
    }


def test_work_policy_lives_in_item_module_and_unit_shares_the_value_object():
    assert item_module.WorkPolicyOverride is WorkPolicyOverride
    from skm.modules.planning.domain.unit import Unit

    assert "WorkPolicyOverride" in Unit.__annotations__["work_policy"]


def test_the_pure_domain_imports_neither_execution_nor_runtimes():
    forbidden = re.compile(
        r"^\s*(?:from|import)\s+skm\.(?:modules\.(?:execution|runtimes)|adapters|platform)\b", re.M
    )
    names = [
        "specification",
        "display_keys",
        "references",
        "identity",
        "changes",
        "text_edits",
        "phase",
        "item",
        "unit",
        "requirement",
        "criterion",
        "check_spec",
        "decision",
        "material",
        "reads",
        "review_requirement",
        "plan_relation",
        "execution_constraints",
    ]
    for name in names:
        source = (DOMAIN / f"{name}.py").read_text()
        assert forbidden.search(source) is None, name
        # authoring performs no filesystem IO
        assert "import os" not in source, name
        assert "open(" not in source, name
