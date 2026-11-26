"""Shared ENCH4 authoring documents and edit sequence."""

from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from contracts.execution._client_execution import manual_check
from contracts.planning.test_client_planning import preview, publication
from integration.artifacts.test_upload_flow import add_file_dto, dispatch_new
from skm.application_bus.client import SkmClient
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonObject
from skm.modules.artifacts import public as artifacts
from skm.modules.planning import public as planning
from support.backend import ClientBackend

A, B, REKEYED = "P1.1", "P1.2", "P1.3"
BASE_TEXT = "Use café notes. P1.2 is the historical name."
EDITED_TEXT = "Use the revised café notes. P1.2 is the historical name."
BASE_GUIDE = b"Original authoring guide\n"
NEW_GUIDE = b"Second authoring guide\n"


def _item(key: str, summary: str) -> JsonObject:
    return {
        "key": key,
        "phase": "P1",
        "title": f"Author {key}",
        "summary": summary,
        "why": "Exercise independent draft edits",
        "scope": {"include": ["repo:src/**"], "exclude": []},
        "deliverables": ["Verified fixture"],
        "guidance_md": "Keep the fixture self-contained.",
        "route": {"runtime": "fake", "class": "implementation", "effort": "high"},
        "review": {"mode": "self", "reason": "Application fake"},
    }


def add_guide(side: ClientBackend, owner: SkmClient) -> Any:
    ws = side.seed.workspace_id
    staged = owner.upload_blob(ws, [BASE_GUIDE], size=len(BASE_GUIDE), media_type="text/plain")
    return dispatch_new(owner, add_file_dto(ws, side.seed.project_id, staged))


def base_draft(
    side: ClientBackend,
    owner: SkmClient,
    file_version_id: UUID,
) -> tuple[UUID, Any]:
    plan = dispatch_new(owner, planning.CreatePlan(side.seed.project_id, "Concurrent authors"))
    draft = dispatch_new(owner, planning.OpenDraft(plan.plan_id, base="empty"))
    document: JsonObject = {
        "goal": "Keep authored revisions isolated from existing runs",
        "phases": [
            {"key": "P1", "title": "Author", "goal": "Exercise pinned inputs", "design_state": "detailed"}
        ],
        "items": [_item(A, BASE_TEXT), _item(B, "Independent item")],
        "checks": [manual_check(key, "Verify original fixture") for key in (A, B)],
        "requirements": [
            {
                "key": "R1",
                "statement": "Retain the structural owner",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": [B],
            }
        ],
        "materials": [
            {
                "key": "guide",
                "title": "Authoring guide",
                "kind": "file_version",
                "role": "input",
                "file_version_id": str(file_version_id),
                "freshness": {"policy": "latest_at_publish"},
                "required_for": ["execution"],
                "applies_to": [A, B],
            }
        ],
    }
    saved = owner.dispatch(
        planning.SaveDraft(plan.plan_id, draft.draft_id, draft.edit_version, merge_patch=document)
    )
    return plan.plan_id, saved


def _draft_fragment(client: SkmClient, plan_id: UUID, draft: Any) -> tuple[Any, Any]:
    source = {"draft_id": draft.draft_id, "expected_edit_version": draft.edit_version}
    page = planning.ListEntities(plan_id, kinds=("item",), limit=1, **source)
    first: Any = client.ask(page)
    assert first.next_cursor
    second: Any = client.ask(replace(page, after=first.next_cursor))
    assert [first.items[0].display_key, second.items[0].display_key] == [A, B]
    assert second.next_cursor is None
    entity: Any = client.ask(planning.GetEntity(plan_id, A, **source))
    read = planning.ReadText(plan_id, A, "/summary", max_bytes=9, **source)
    fragment: Any = client.ask(read)
    tail: Any = client.ask(replace(read, offset_bytes=fragment.end_offset_bytes, max_bytes=100))
    assert fragment.truncated
    assert tail.next_offset_bytes is None
    assert fragment.text + tail.text == BASE_TEXT
    assert fragment.text_digest == tail.text_digest
    source_json = first.source.to_json()
    assert all(view.source.to_json() == source_json for view in (second, entity, fragment, tail))
    assert source_json["edit_version"] == draft.edit_version
    assert (entity.entity_id, fragment.target_entity_id) == (first.items[0].entity_id,) * 2
    return fragment, second.items[0].entity_id


def _save_changes(client: SkmClient, plan_id: UUID, draft: Any, *changes: JsonObject) -> Any:
    return client.dispatch(
        planning.SaveDraft.from_json(
            {
                "plan_id": str(plan_id),
                "draft_id": str(draft.draft_id),
                "expected_edit_version": draft.edit_version,
                "changes": list(changes),
            }
        )
    )


def _patch(target: str, **fields: Any) -> JsonObject:
    return {"op": "patch", "target": target, "merge_patch": fields}


def _text(fragment: Any, replacement: str) -> JsonObject:
    return {
        "op": "replace_text",
        "target": A,
        "pointer": "/summary",
        "expected_text_digest": fragment.text_digest,
        "old_text": BASE_TEXT,
        "new_text": replacement,
    }


def merge_edits(side: ClientBackend, plan: UUID) -> tuple[Any, Any]:
    first, second = side.client("editor"), side.client("other-editor")
    draft1 = dispatch_new(first, planning.OpenDraft(plan, base="current"))
    draft2 = dispatch_new(second, planning.OpenDraft(plan, base="current"))
    assert draft1.draft_id != draft2.draft_id
    assert draft1.base_revision_id == draft2.base_revision_id
    fragment1, _ = _draft_fragment(first, plan, draft1)
    fragment2, entity_b = _draft_fragment(second, plan, draft2)
    assert fragment1.text_digest == fragment2.text_digest

    saved1 = _save_changes(
        first,
        plan,
        draft1,
        _text(fragment1, "First editor wording"),
        _patch(A, route={"class": "frontier"}, depends_on=[B]),
    )
    saved2 = _save_changes(
        second,
        plan,
        draft2,
        _text(fragment2, EDITED_TEXT),
        _patch(B, depends_on=[A]),
        {
            "op": "add",
            "kind": "check",
            "entity": manual_check(A, "Verify authored output", key="V2", required=True),
        },
        {"op": "rekey", "target": B, "new_key": REKEYED},
    )
    drift = planning.ReadText(
        plan, A, "/summary", draft_id=draft1.draft_id, expected_edit_version=draft1.edit_version
    )
    with pytest.raises(SkmError) as stale_read:
        first.ask(drift)
    assert stale_read.value.code is ErrorCode.VERSION_CONFLICT
    candidate1, candidate2 = preview(first, plan, saved1), preview(second, plan, saved2)
    assert candidate1.publishable, candidate1.validation.to_json()
    assert candidate2.publishable, candidate2.validation.to_json()
    intermediate = dispatch_new(first, publication(plan, saved1, candidate1))
    with pytest.raises(SkmError) as stale_base:
        dispatch_new(second, publication(plan, saved2, candidate2))
    assert stale_base.value.code is ErrorCode.BASE_REVISION_CHANGED

    rebase = planning.RebaseDraft(plan, saved2.draft_id, saved2.edit_version, intermediate.revision_id)
    before = second.ask(planning.GetDraft(plan, saved2.draft_id))
    with pytest.raises(SkmError) as conflict:
        dispatch_new(second, rebase)
    assert conflict.value.code is ErrorCode.REBASE_CONFLICTS
    assert second.ask(planning.GetDraft(plan, saved2.draft_id)) == before
    conflicts = conflict.value.details["conflicts"]
    assert isinstance(conflicts, list)
    assert len(conflicts) == 1
    (found,) = conflicts
    assert isinstance(found, dict)
    assert found["pointer"] == "/items/0/summary"
    resolved = dispatch_new(
        second,
        planning.RebaseDraft.from_json(
            {
                **rebase.to_json(),
                "resolutions": [{"conflict_id": found["conflict_id"], "keep": "yours"}],
            }
        ),
    )
    cyclic = preview(second, plan, resolved)
    assert not cyclic.publishable
    assert any("cycle" in finding.code.lower() for finding in cyclic.validation.findings)
    with pytest.raises(SkmError) as bad_graph:
        dispatch_new(second, publication(plan, resolved, cyclic))
    assert bad_graph.value.code is ErrorCode.PLAN_NOT_READY
    head: Any = second.ask(planning.GetPlan(plan))
    assert head.current_revision_id == intermediate.revision_id
    assert len(revisions(second, plan)) == 2

    repaired = _save_changes(second, plan, resolved, _patch(A, depends_on=[]))
    final: Any = second.ask(planning.GetDraft(plan, repaired.draft_id))
    document = final.document
    assert document["requirements"][0]["owners"] == [REKEYED]
    assert document["materials"][0]["applies_to"] == [A, REKEYED]
    assert document["items"][1]["id"] == str(entity_b)
    assert document["items"][1]["depends_on"] == [A]
    assert document["items"][0]["summary"] == EDITED_TEXT
    assert document["items"][0]["route"]["class"] == "frontier"
    assert any(check["key"] == "V2" and check["required"] for check in document["checks"])
    return second, repaired


def revisions(client: SkmClient, plan: UUID) -> tuple[Any, ...]:
    page: Any = client.ask(planning.ListRevisions(plan))
    return page.items


def add_version(side: ClientBackend, owner: SkmClient, added: Any) -> Any:
    payload = NEW_GUIDE
    staged = owner.upload_blob(side.seed.workspace_id, [payload], size=len(payload), media_type="text/plain")
    return dispatch_new(
        owner,
        artifacts.AddFileVersion.from_json(
            {
                "file_id": str(added.file_id),
                "expected_row_version": 2,
                "blob": {
                    "workspace_id": str(staged.workspace_id),
                    "staged_blob_id": str(staged.staged_blob_id),
                    "digest": staged.digest,
                    "size": staged.size,
                    "media_type": staged.media_type,
                },
                "original_filename": "guide-v2.txt",
                "declared_media_type": None,
                "source": {"kind": "upload"},
            }
        ),
    )
