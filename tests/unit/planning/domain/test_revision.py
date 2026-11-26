"""Revision metadata, append-only revision port, publication and read-source DTO guards (planning §4.4-§8)."""

import inspect
import json
from dataclasses import FrozenInstanceError, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PlanId, PrincipalId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.planning import ports, public
from skm.modules.planning.domain.canonical import CANONICALIZATION_VERSION
from skm.modules.planning.domain.compile_graph import COMPILER_VERSION
from skm.modules.planning.domain.plan import Plan, archive, new_plan, record_publication
from skm.modules.planning.domain.revision import RevisionMeta, RevisionOrigin, new_revision_meta
from skm.modules.planning.module import MODULE

SCHEMAS = Path(__file__).resolve().parents[4] / "src/skm/schemas"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "b" * 64
OTHER_DIGEST = "sha256:" + "c" * 64


def uid(n: int) -> UUID:
    return UUID(f"01900000-0000-7000-8000-{n:012d}")


@dataclass(frozen=True)
class Project:
    workspace_id: WorkspaceId
    project_id: ProjectId


ACTOR = PrincipalId(uid(3))


def fresh_plan() -> Plan:
    return new_plan(
        PlanId(uid(10)), Project(WorkspaceId(uid(1)), ProjectId(uid(2))), "PLAN1", "T", ACTOR, NOW
    )


def published_plan(revisions: int = 1) -> Plan:
    plan = fresh_plan()
    for n in range(revisions):
        plan = record_publication(plan, RevisionId(uid(20 + n)), "T", NOW)
    return plan


def meta(plan: Plan, **changes: object) -> RevisionMeta:
    arguments: dict[str, object] = {
        "content_digest": DIGEST,
        "origin": RevisionOrigin.DRAFT,
        "restored_from": None,
        "change_reason": "first cut",
        "actor": ACTOR,
        "now": NOW,
    }
    arguments.update(changes)
    return new_revision_meta(RevisionId(uid(50)), plan, **arguments)  # type: ignore[arg-type]


# --- RevisionMeta ------------------------------------------------------------------------------------------


def test_first_revision_has_number_one_and_no_parent() -> None:
    first = meta(fresh_plan())
    assert (first.revision_no, first.parent_revision_id) == (1, None)
    assert (first.plan_id, first.workspace_id) == (PlanId(uid(10)), WorkspaceId(uid(1)))
    assert first.origin is RevisionOrigin.DRAFT
    assert first.restored_from_revision_id is None
    assert (first.published_by, first.published_at, first.change_reason) == (ACTOR, NOW, "first cut")
    assert first.content_digest == DIGEST


def test_next_revision_takes_the_plan_counter_and_the_current_revision_as_parent() -> None:
    plan = published_plan(2)
    second = meta(plan)
    assert second.revision_no == 3
    assert second.parent_revision_id == plan.current_revision_id


def test_meta_records_the_versions_it_was_built_with() -> None:
    built = meta(fresh_plan())
    assert built.schema_version == 1
    assert built.canonicalization_version == CANONICALIZATION_VERSION
    assert built.compiler_version == COMPILER_VERSION


def test_restore_names_its_source_and_requires_an_existing_revision() -> None:
    plan = published_plan(2)
    restored = meta(plan, origin=RevisionOrigin.RESTORE, restored_from=RevisionId(uid(20)))
    assert restored.origin is RevisionOrigin.RESTORE
    assert restored.restored_from_revision_id == uid(20)
    assert restored.parent_revision_id == plan.current_revision_id  # a restore never rewrites history


@pytest.mark.parametrize(
    ("origin", "restored_from"),
    [
        (RevisionOrigin.RESTORE, None),
        (RevisionOrigin.DRAFT, RevisionId(uid(20))),
        (RevisionOrigin.SYSTEM, RevisionId(uid(20))),
        (RevisionOrigin.IMPORT, RevisionId(uid(20))),
    ],
)
def test_restored_from_is_set_exactly_for_the_restore_origin(
    origin: RevisionOrigin, restored_from: RevisionId | None
) -> None:
    with pytest.raises(InternalError):
        meta(published_plan(2), origin=origin, restored_from=restored_from)


def test_restore_into_a_plan_without_a_revision_or_from_itself_is_refused() -> None:
    with pytest.raises(InternalError):
        meta(fresh_plan(), origin=RevisionOrigin.RESTORE, restored_from=RevisionId(uid(20)))
    with pytest.raises(InternalError):
        meta(published_plan(), origin=RevisionOrigin.RESTORE, restored_from=RevisionId(uid(50)))


@pytest.mark.parametrize("digest", ["", "sha256:abc", "sha256:" + "B" * 64, "md5:" + "b" * 64, DIGEST + "0"])
def test_digest_must_be_sha256_lowercase_hex(digest: str) -> None:
    with pytest.raises(InternalError):
        meta(fresh_plan(), content_digest=digest)


@pytest.mark.parametrize("reason", ["", "   ", "x" * 2001])
def test_reason_is_1_to_2000_characters(reason: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        meta(fresh_plan(), change_reason=reason)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["field"] == "reason"


def test_a_revision_is_not_written_for_an_archived_plan() -> None:
    with pytest.raises(PreconditionFailed) as caught:
        meta(archive(fresh_plan(), NOW))
    assert caught.value.code is ErrorCode.PLAN_ARCHIVED


def test_revision_meta_is_frozen_and_slotted() -> None:
    first = meta(fresh_plan())
    with pytest.raises(FrozenInstanceError):
        setattr(first, "content_digest", OTHER_DIGEST)  # noqa: B010 -- exercise the frozen setter at runtime.
    assert not hasattr(first, "__dict__")
    assert [f.name for f in fields(RevisionMeta)][:4] == ["id", "plan_id", "workspace_id", "revision_no"]


# --- ports -------------------------------------------------------------------------------------------------

_MUTATORS = ("update", "delete", "remove", "replace", "set_", "save", "rewrite", "patch", "upsert")


def _methods(port: type) -> list[str]:
    return [
        name for name, member in inspect.getmembers(port) if callable(member) and not name.startswith("_")
    ]


def test_revision_repository_is_append_only() -> None:
    names = _methods(ports.RevisionRepository)
    assert "add" in names
    assert [name for name in names if name.startswith(_MUTATORS)] == []
    assert set(names) == {
        "get_meta",
        "find_by_number",
        "get_document",
        "load_typed_document",
        "identities",
        "add",
        "list_for_plan",
    }


def test_the_record_a_revision_is_written_from_is_immutable() -> None:
    assert ports.RevisionRecord.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert ports.MaterialPin.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_cas_is_explicit_on_every_mutable_aggregate() -> None:
    plan_save = inspect.signature(ports.PlanRepository.save).parameters["expected_version"]
    draft_save = inspect.signature(ports.DraftRepository.save).parameters["expected_edit_version"]
    for parameter in (plan_save, draft_save):
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty
    assert "allocate_plan_no" in _methods(ports.PlanCounters)


def test_lock_methods_exist_for_the_plan_then_drafts_order() -> None:
    assert {"lock", "lock_shared"} <= set(_methods(ports.PlanRepository))
    assert {"lock", "lock_open_for_plan", "count_open"} <= set(_methods(ports.DraftRepository))
    assert "lock" not in _methods(ports.RevisionRepository)


def test_plan_list_state_is_the_closed_set_of_the_query() -> None:
    assert set(ports.PlanListState.__value__.__args__) == {"active", "archived", "all"}
    assert "state" in inspect.signature(ports.PlanningQueries.list_plans).parameters


def test_manifest_declares_every_repository_port_and_no_subscriber() -> None:
    assert set(MODULE.repository_ports) == {
        ports.PlanRepository,
        ports.PlanCounters,
        ports.DraftRepository,
        ports.RevisionRepository,
        ports.PlanningQueries,
    }
    assert MODULE.subscribers == ()
    assert MODULE.permissions == {
        "plan.read",
        "plan.create",
        "plan.edit",
        "plan.publish",
        "plan.approve",
        "plan.archive",
    }


def test_public_facade_exposes_the_contract_types() -> None:
    for name in ("PlanRef", "PlanView", "RevisionMetaView", "EntityRef", "SpecificationDoc", "DraftId"):
        assert name in public.__all__
        assert hasattr(public, name)
    assert [f.name for f in fields(public.RevisionMetaView)] == [
        "revision_id",
        "plan_id",
        "project_id",
        "workspace_id",
        "revision_no",
        "digest",
        "published_at",
        "compiler_version",
        "plan_purpose",
        "plan_lifecycle",
    ]
    assert [f.name for f in fields(public.PlanRef)] == [
        "plan_id",
        "workspace_id",
        "project_id",
        "alias",
        "title",
        "purpose",
        "lifecycle",
        "current_revision_id",
    ]


# --- authoring DTO guards ----------------------------------------------------------------------------------


def _validator(relative: str) -> Draft202012Validator:
    resources: list[tuple[str, Resource[Schema]]] = []
    for path in [*(SCHEMAS / "kernel").glob("*.json"), *SCHEMAS.glob("planning/*.json")]:
        document: JsonObject = json.loads(path.read_text())
        resources.append((str(document["$id"]), Resource[Schema].from_contents(document)))
    schema: JsonObject = json.loads((SCHEMAS / relative).read_text())
    return Draft202012Validator(schema, registry=Registry[Schema]().with_resources(resources))


PLAN = str(uid(10))
DRAFT = str(uid(30))
REVISION = str(uid(21))
TEXT_TARGET = {"target": "plan", "pointer": "/goal"}


def test_publish_requires_the_expected_digest_of_the_previewed_candidate() -> None:
    validator = _validator("planning/commands/publish-revision.v1.json")
    command = {
        "plan_id": PLAN,
        "draft_id": DRAFT,
        "expected_edit_version": 2,
        "expected_content_digest": DIGEST,
        "reason": "ship it",
    }
    validator.validate(command)
    for missing in ("expected_content_digest", "expected_edit_version", "reason"):
        with pytest.raises(ValidationError):
            validator.validate({k: v for k, v in command.items() if k != missing})
    for bad in ("sha256:" + "A" * 64, "sha256:short", DIGEST + "0", ""):
        with pytest.raises(ValidationError):
            validator.validate({**command, "expected_content_digest": bad})


@pytest.mark.parametrize(
    ("schema", "extra"),
    [
        ("planning/queries/list-entities.v1.json", {}),
        ("planning/queries/read-text.v1.json", TEXT_TARGET),
    ],
)
def test_a_read_source_is_one_revision_or_one_draft_with_its_edit_version(
    schema: str, extra: dict[str, str]
) -> None:
    validator = _validator(schema)
    validator.validate({"plan_id": PLAN, "revision_id": REVISION, **extra})
    validator.validate({"plan_id": PLAN, "draft_id": DRAFT, "expected_edit_version": 3, **extra})
    rejected: list[dict[str, object]] = [
        {"plan_id": PLAN, **extra},  # no source
        {"plan_id": PLAN, "draft_id": DRAFT, **extra},  # draft without the version it was read at
        {"plan_id": PLAN, "expected_edit_version": 3, **extra},  # a version without a draft
        {"plan_id": PLAN, "revision_id": REVISION, "draft_id": DRAFT, "expected_edit_version": 3, **extra},
        {"plan_id": PLAN, "revision_id": REVISION, "expected_edit_version": 3, **extra},
        {"plan_id": PLAN, "draft_id": DRAFT, "expected_edit_version": 0, **extra},
    ]
    for dto in rejected:
        with pytest.raises(ValidationError):
            validator.validate(dto)


def test_preview_publication_names_the_draft_and_the_version_it_previews() -> None:
    validator = _validator("planning/queries/preview-publication.v1.json")
    validator.validate({"plan_id": PLAN, "draft_id": DRAFT, "expected_edit_version": 1})
    for missing in ("plan_id", "draft_id", "expected_edit_version"):
        dto = {"plan_id": PLAN, "draft_id": DRAFT, "expected_edit_version": 1}
        del dto[missing]
        with pytest.raises(ValidationError):
            validator.validate(dto)
    with pytest.raises(ValidationError):
        validator.validate(
            {"plan_id": PLAN, "draft_id": DRAFT, "expected_edit_version": 1, "revision_id": REVISION}
        )


def test_list_entities_and_read_text_bounds() -> None:
    entities = _validator("planning/queries/list-entities.v1.json")
    source = {"plan_id": PLAN, "revision_id": REVISION}
    entities.validate({**source, "kinds": ["phase", "check"], "limit": 200})
    for bad in (
        {"kinds": []},
        {"kinds": ["phase", "phase"]},
        {"kinds": ["file"]},
        {"limit": 0},
        {"limit": 201},
    ):
        with pytest.raises(ValidationError):
            entities.validate({**source, **bad})
    text = _validator("planning/queries/read-text.v1.json")
    base = {**source, **TEXT_TARGET}
    text.validate({**base, "offset_bytes": 0, "max_bytes": 65536})
    for bad in ({"max_bytes": 0}, {"max_bytes": 65537}, {"offset_bytes": -1}, {"pointer": "goal"}):
        with pytest.raises(ValidationError):
            text.validate({**base, **bad})


def test_read_source_and_source_view_have_one_owner() -> None:
    defs: JsonObject = json.loads((SCHEMAS / "planning/defs.v1.json").read_text())
    owned = defs["$defs"]
    assert isinstance(owned, dict)
    assert {"read-source", "source-view", "draft-change"} <= set(owned)
    # views reference the owner definition; none of them repeats or varies it
    for view in (
        "entity",
        "entity-page",
        "text-fragment",
        "publication-preview",
        "ready-preview",
        "plan-stats",
    ):
        document: JsonObject = json.loads((SCHEMAS / f"planning/views/{view}.v1.json").read_text())
        properties = document["properties"]
        assert isinstance(properties, dict)
        assert properties["source"] == {"$ref": "urn:skm:planning:defs:v1#/$defs/source-view"}, view
    # read_text / list_entities carry the same fields as the owner ReadSource, flattened
    read_source = owned["read-source"]
    assert isinstance(read_source, dict)
    for query in ("list-entities", "read-text"):
        document = json.loads((SCHEMAS / f"planning/queries/{query}.v1.json").read_text())
        assert document["oneOf"] == read_source["oneOf"], query
        properties = document["properties"]
        assert isinstance(properties, dict)
        assert properties["expected_edit_version"] == read_source["properties"]["expected_edit_version"]  # type: ignore[index]
        assert {"plan_id", "revision_id", "draft_id"} <= set(properties)
    standalone = {path.name for path in SCHEMAS.glob("planning/*.json")}
    assert not {
        name for name in standalone if name.startswith(("query-", "command-"))
    }  # examples are not a registry
