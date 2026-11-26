"""Template rendering, provenance locking, and transactional rollback in ``planning.create_plan``."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from tests.unit.planning.application.test_open_draft import build_world

from fakes.ids import SequentialIds
from skm.adapters.memory.planning.state import planning_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.modules.planning.application.commands import create_plan
from skm.modules.planning.domain.templates import render_template
from skm.modules.planning.generated.commands import CreatePlan
from skm.platform.schema.registry import SchemaRegistry


@pytest.mark.parametrize("template_key", ["feature", "bugfix"])
def test_create_template_draft_assigns_ids_and_locks_provenance(
    monkeypatch: pytest.MonkeyPatch, template_key: str
) -> None:
    world = build_world()
    project = world.project(world.workspace())
    rv_id = uuid4()
    resource = SimpleNamespace(
        resource_version_id=rv_id, key=template_key, version="2.0.0", digest="sha256:test"
    )
    base = Path("resources/packs/core/plan-templates") / template_key
    monkeypatch.setattr(create_plan.extensions, "resolve_resource", lambda *a, **kw: resource)
    monkeypatch.setattr(
        create_plan.extensions,
        "get_resource_version",
        lambda *a, **kw: SimpleNamespace(
            bodies={
                "manifest.toml": (base / "manifest.toml").read_text(encoding="utf-8"),
                "template.json": (base / "template.json").read_text(encoding="utf-8"),
            }
        ),
    )
    result = world.run(
        CreatePlan(
            project_id=project,
            title="Actual Plan Title",
            template_key=template_key,
            template_inputs={"title": "Item Scoped Title", "goal": "Concrete {{inert}} goal"},
        )
    )
    assert result.draft_id is not None
    assert result.edit_version == 1
    draft = world.draft_row(result.draft_id)
    assert draft.base_revision_id is None
    doc = draft.document
    SchemaRegistry.load_default().require_valid("urn:skm:planning:specification:v1", doc)
    assert doc["title"] == "Actual Plan Title"
    assert doc["goal"] == "Concrete {{inert}} goal"
    assert doc["items"][0]["title"] == "Item Scoped Title"
    assert doc["extensions"]["core/template"] == {
        "schema_version": 1,
        "value": {
            "key": template_key,
            "version": "2.0.0",
            "digest": "sha256:test",
            "resource_version_id": str(rv_id),
        },
    }
    for section in ("phases", "items"):
        assert all(UUID(str(entity["id"])) for entity in doc[section])
    opened = world.events("draft-opened")[-1]
    assert opened.payload["source"] == "template"
    assert opened.payload["base_revision_id"] is None


def test_atomic_rollback_on_missing_quarantined_or_invalid_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = build_world()
    project = world.project(world.workspace())
    before_events = world.event_count()

    # 1. template_inputs without template_key -> SCHEMA_INVALID
    with pytest.raises(ValidationFailed) as orphan_err:
        world.run(CreatePlan(project_id=project, title="T", template_inputs={"goal": "x"}))
    assert orphan_err.value.code is ErrorCode.SCHEMA_INVALID

    # 2. Missing template -> NOT_FOUND
    def _raise_missing(*_a: Any, **_kw: Any) -> Any:
        raise NotFound(ErrorCode.NOT_FOUND, "template not found")

    monkeypatch.setattr(create_plan.extensions, "resolve_resource", _raise_missing)
    with pytest.raises(NotFound) as nf_err:
        world.run(CreatePlan(project_id=project, title="T", template_key="missing"))
    assert nf_err.value.code is ErrorCode.NOT_FOUND

    # 3. Quarantined template -> RESOURCE_QUARANTINED
    def _raise_quarantined(*_a: Any, **_kw: Any) -> Any:
        raise PreconditionFailed(ErrorCode.RESOURCE_QUARANTINED, "template quarantined")

    monkeypatch.setattr(create_plan.extensions, "resolve_resource", _raise_quarantined)
    with pytest.raises(PreconditionFailed) as q_err:
        world.run(CreatePlan(project_id=project, title="T", template_key="quarantined"))
    assert q_err.value.code is ErrorCode.RESOURCE_QUARANTINED

    # 4. Invalid inputs / rendered spec -> SCHEMA_INVALID
    resource = SimpleNamespace(resource_version_id=uuid4(), key="x", version="1.0.0", digest="sha256:x")
    monkeypatch.setattr(create_plan.extensions, "resolve_resource", lambda *a, **kw: resource)
    monkeypatch.setattr(
        create_plan.extensions,
        "get_resource_version",
        lambda *a, **kw: SimpleNamespace(
            bodies={
                "manifest.toml": '[inputs_schema]\ntype = "object"\nadditionalProperties = false',
                "template.json": '{"schema": "urn:skm:planning:specification:v1"}',
            }
        ),
    )
    with pytest.raises(ValidationFailed) as extra_err:
        world.run(CreatePlan(project_id=project, title="T", template_key="x", template_inputs={"extra": "x"}))
    assert extra_err.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as spec_err:
        world.run(CreatePlan(project_id=project, title="T", template_key="x"))
    assert spec_err.value.code is ErrorCode.SCHEMA_INVALID

    # Verify zero partial artifacts, zero events, and alias counter rollback
    state = planning_state(world.backend.committed)
    assert not state.plans
    assert not state.drafts
    assert world.event_count() == before_events
    assert world.run(CreatePlan(project_id=project, title="Next")).alias == "PLAN1"


def test_domain_render_escaped_braces_and_rejects_bad_expressions() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "flag": {"type": "boolean"}},
        "required": ["name", "flag"],
        "additionalProperties": False,
    }
    tpl = json.dumps(
        {
            "schema": "urn:skm:planning:specification:v1",
            "title": "placeholder",
            "goal": 'Keep {{ "{{" }}literal{{ "}}" }} for {{name}} ({{inputs.flag}})',
            "phases": [],
            "items": [],
        }
    )
    doc = render_template(
        tpl, {"name": "Alice", "flag": False}, schema, "Override", SequentialIds(), {"k": 1}
    )
    assert doc["title"] == "Override"
    assert doc["goal"] == "Keep {{literal}} for Alice (false)"
    assert isinstance(doc["extensions"], dict)
    assert doc["extensions"]["core/template"] == {"schema_version": 1, "value": {"k": 1}}

    with pytest.raises(ValidationFailed) as bad_expr:
        render_template(
            json.dumps({"goal": "{{__import__('os')}}"}),
            {"name": "x", "flag": True},
            schema,
            "T",
            SequentialIds(),
            {},
        )
    assert bad_expr.value.code is ErrorCode.SCHEMA_INVALID

    with pytest.raises(ValidationFailed) as bad_ref:
        render_template(
            "{}", {}, {"type": "object", "$ref": "https://example.com/schema"}, "T", SequentialIds(), {}
        )
    assert bad_ref.value.code is ErrorCode.SCHEMA_INVALID
