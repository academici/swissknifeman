"""Dual-backend lesson curation, effective recall and immutable context provenance."""

from dataclasses import replace
from datetime import timedelta
from functools import partial
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from contracts.context.harness import ContextSide, MutableBuiltinPacks, core_pack, ctx_side
from contracts.context.test_repositories import _resolve_host_inputs
from contracts.execution.harness import ExecSide, exec_side
from contracts.execution.seed_helpers import seed_attempt, seed_run, seed_stage, seed_step, seed_task
from integration.artifacts.test_upload_flow import dispatch_new
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, InternalError, NotFound, ValidationFailed
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import Role
from skm.modules.context import public as context
from skm.modules.context.domain.finalize import host_facts_to_meta, verify_finalization
from skm.modules.context.ports import ContextRepository, MemoryRetriever, TextStore
from skm.modules.execution import public as execution
from skm.modules.execution.domain.ids import StepId
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.knowledge import public as knowledge
from skm.modules.knowledge.ports import LessonRepository
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace.public import CreateWorkspace
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401

from .harness import KnowledgeSide, knowledge_side

__all__ = ["ctx_side", "exec_side", "knowledge_side"]


def _candidate(
    workspace: WorkspaceId,
    project: ProjectId,
    action: str,
) -> knowledge.CandidateForPromotion:
    return knowledge.CandidateForPromotion(
        uuid4(),
        workspace,
        ScopeId(project),
        knowledge.LessonKind.GOTCHA,
        "Pool timeout",
        action,
        (knowledge.EvidenceRef("review", str(uuid4())),),
        0.95,
        knowledge.ConfidenceTier.STRONG,
    )


def _promote(
    side: KnowledgeSide,
    action: str,
    *,
    supersedes: knowledge.LessonId | None = None,
) -> knowledge.LessonId:
    with side.uow() as uow:
        ref = knowledge.promote_lesson(
            uow,
            _candidate(side.workspace, side.project, action),
            actor=side.owner,
            now=side.clock.now(),
            supersedes=supersedes,
        )
        uow.commit()
    return ref.lesson_id


def test_promotion_rolls_back_and_supersedes_only_in_exact_scope(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    original = _promote(side, "Wait for the pool")
    replacement = _candidate(side.workspace, side.project, "Raise the pool limit")
    scopes = (ScopeRef(ScopeKind.PROJECT, ScopeId(side.project)),)
    applicability = knowledge.LessonApplicability(
        "For staging",
        (("repo:version", "v3"),),
        side.clock.now() + timedelta(hours=1),
    )
    with side.uow() as uow:
        pending = knowledge.promote_lesson(
            uow,
            replacement,
            actor=side.owner,
            supersedes=original,
            now=side.clock.now(),
            applicability=applicability,
        )
        assert [row["id"] for row in knowledge.list_lessons_for_context(uow, scopes, limit=5)] == [
            str(pending.lesson_id)
        ]
    with side.uow(readonly=True) as uow:
        assert uow.repo(LessonRepository).by_candidate(replacement.candidate_id) is None
        assert [row["id"] for row in knowledge.list_lessons_for_context(uow, scopes, limit=5)] == [
            str(original)
        ]

    other = side.new_project("foreign")
    with side.uow() as uow, pytest.raises(ValidationFailed) as error:
        knowledge.promote_lesson(
            uow,
            _candidate(side.workspace, other, "Restart the pool"),
            actor=side.owner,
            supersedes=original,
        )
    assert error.value.code == ErrorCode.SCHEMA_INVALID

    with side.uow() as uow:
        ref = knowledge.promote_lesson(
            uow,
            replacement,
            actor=side.owner,
            supersedes=original,
            now=side.clock.now(),
            applicability=applicability,
        )
        uow.commit()
    with side.uow(readonly=True) as uow:
        assert uow.repo(LessonRepository).get(ref.lesson_id).applicability == applicability
        views = knowledge.list_lessons_for_context(
            uow,
            scopes,
            limit=5,
            now=side.clock.now(),
            current_versions={"repo:version": "v3"},
        )
        assert [(row["id"], row["freshness"]) for row in views] == [(str(ref.lesson_id), "current")]
        assert knowledge.lesson_confidence_inputs(uow, (ref.lesson_id,)) == {
            ref.lesson_id: replacement.candidate_id
        }
    with side.uow() as uow, pytest.raises(Conflict) as duplicate:
        knowledge.promote_lesson(uow, replacement, actor=side.owner, supersedes=None)
    assert duplicate.value.code == ErrorCode.ALREADY_EXISTS

    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = dispatch_new(client, CreateWorkspace(slug="foreign", title="Foreign")).workspace_id
    with pytest.raises(NotFound):
        side.query("get_lesson", {"workspace_id": str(foreign), "lesson_id": str(original)})
    with pytest.raises(NotFound):
        side.action(
            "deprecate_lesson",
            {
                "workspace_id": str(foreign),
                "lesson_id": str(original),
                "reason": "Unsafe",
                "expected_row_version": 1,
            },
        )
    page = side.query("list_lessons", {"workspace_id": str(side.workspace), "kind": "gotcha", "limit": 1})
    assert len(page["items"]) == 1
    assert page["has_more"]
    assert (
        len(
            side.query(
                "list_lessons",
                {
                    "workspace_id": str(side.workspace),
                    "kind": "gotcha",
                    "after": page["next_cursor"],
                },
            )["items"]
        )
        == 1
    )


def test_conflicting_lessons_recall_as_an_atomic_group(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    ids = {_promote(side, "Wait for the pool"), _promote(side, "Replace the pool")}
    retriever = side.app.gateways.get(MemoryRetriever)
    recall = partial(
        retriever.search, workspace_id=side.workspace, project_id=side.project, query="pool", actor=side.owner
    )
    with side.uow(readonly=True) as uow:
        assert recall(uow, top_k=1) == ()
        hits = recall(uow, top_k=2)
    assert {str(hit["lesson_id"]) for hit in hits} == {str(lesson_id) for lesson_id in ids}
    first, second = hits
    assert first["atomic_group"] == second["atomic_group"]
    assert first["atomic_group"]
    assert all(hit["source_kind"] == "lesson" and hit["freshness"] == "unvalidated" for hit in hits)
    assert all(str(hit["text"]).startswith("Potentially conflicting lesson") for hit in hits)
    assert all(hit["source_version"] == "1" and hit["evidence"] for hit in hits)


def test_promotion_is_facade_only_and_requires_a_human(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    with pytest.raises(InternalError, match="unregistered command"):
        side.app.bus._registry.command_by_name("knowledge.promote_lesson")
    candidate = _candidate(side.workspace, side.project, "Use the staging pool")
    service = Actor(PrincipalId(uuid4()), PrincipalKind.SERVICE, "curation-service")
    with side.uow() as uow, pytest.raises(Forbidden) as failure:
        knowledge.promote_lesson(uow, candidate, actor=service, supersedes=None)
    assert failure.value.details["reason"] == "human_gate"


def _enable_recall(side: ContextSide) -> None:
    pack = core_pack("1.1.0")
    side.builtin.current = (
        replace(
            pack,
            files=tuple(
                replace(file, content=file.content.replace(b"memory_top_k = 0", b"memory_top_k = 2"))
                if file.path == "agent-profiles/executor.toml"
                else file
                for file in pack.files
            ),
        ),
    )
    dispatch_new(side.client, SyncBuiltinPacks())
    dispatch_new(
        side.client, SetValue(SetValueDefsScopeRef("project", side.proj), "context.memory.enabled", True)
    )


def _assemble(side: ContextSide, actor: Actor, step_ref: str) -> context.ContextDraft:
    with side.uow() as uow:
        cfg = side.effective_config(uow)
        draft = context.assemble_draft(
            uow,
            side.app.gateways,
            side.make_request(uow, config=cfg, step_ref=step_ref),
            config=cfg,
            owner_ref=f"step:{step_ref}",
            actor=actor,
        )
        uow.commit()
    return draft


def _finalize_snapshot(side: ContextSide, draft: context.ContextDraft) -> context.ContextManifest:
    host_blocks, host_meta, facts = _resolve_host_inputs(draft, side)
    final = context.finalize(draft, host_blocks, facts, side.estimator)
    prompt_version = side.upload_text(final.rendered_prompt)
    with side.uow() as uow:
        repo = uow.repo(ContextRepository)
        manifest, host_rows = verify_finalization(
            repo.get(draft.manifest_id, for_update=True),
            draft_digest=draft.draft_digest,
            estimator_id=side.estimator.estimator_id,
            host_meta=host_meta,
            facts_meta=host_facts_to_meta(facts),
            claimed_selection=final.selection,
            rendered_prompt_digest=final.prompt_digest,
            artifact_prompt_digest=final.prompt_digest,
            prompt_file_version_id=prompt_version,
            finalized_at=side.clock.now(),
        )
        repo.finalize(manifest, host_rows=host_rows)
        uow.commit()
    return manifest


def test_final_manifest_keeps_lesson_version_bytes_and_digest_after_deprecation(
    exec_side: ExecSide,
) -> None:
    builtin = exec_side.app.gateways.get(BuiltinPacks)
    assert isinstance(builtin, MutableBuiltinPacks)
    with exec_side.uow() as uow:
        run = seed_run(exec_side, uow)
        task = seed_task(exec_side, uow, run.id)
        attempt = seed_attempt(exec_side, uow, run.id, task.id)
        stage = seed_stage(exec_side, uow, attempt)
        uow.commit()
    side = ContextSide(
        kind=exec_side.kind,
        app=exec_side.app,
        clock=exec_side.clock,
        owner=exec_side.owner,
        client=exec_side.client,
        ws=exec_side.ws,
        proj=exec_side.proj,
        plan_id=exec_side.plan1,
        rev_id=exec_side.rev1,
        run_scope_id=ScopeId(run.id),
        mat_fv_id=exec_side.fv1,
        prompt_fv_id=exec_side.fv2,
        builtin=builtin,
        estimator=exec_side.estimator,
        dsn=exec_side.dsn,
    )
    _enable_recall(side)
    with side.uow() as uow:
        ref = knowledge.promote_lesson(
            uow,
            _candidate(side.ws, side.proj, "Use the staging pool"),
            actor=side.owner,
            now=side.clock.now(),
            supersedes=None,
        )
        uow.commit()
    source_ref = f"knowledge:{ref.lesson_id}"
    lesson_text = "Trigger: Pool timeout\nAction: Use the staging pool\nFreshness: unvalidated"
    digest = "sha256:" + sha256(lesson_text.encode()).hexdigest()
    step_id = StepId(exec_side.new_id())
    manifest = _finalize_snapshot(side, _assemble(side, side.owner, f"step:{step_id}"))
    with exec_side.uow() as uow:
        seed_step(exec_side, uow, attempt, stage, manifest_id=manifest.id, step_id=step_id)
        uow.commit()
    with side.uow(readonly=True) as uow:
        previous = context.require_final(uow, manifest.id)
        row = next(block for block in previous.blocks if block.source_ref == source_ref)
        assert row.included is True
        assert row.source_version == "1"
        assert row.content_digest == digest
        original_texts = uow.repo(TextStore).get_many((digest,))
        assert original_texts == {digest: lesson_text}
    lesson_refs = [{"id": source_ref, "version": "1", "content_digest": digest}]

    spec = side.app.bus._registry.command_by_name("knowledge.deprecate_lesson")
    dispatch_new(
        side.client,
        spec.dto.from_json(
            {
                "workspace_id": str(side.ws),
                "lesson_id": str(ref.lesson_id),
                "reason": "Unsafe with new pool semantics",
                "expected_row_version": 1,
            }
        ),
    )
    refreshed = _assemble(side, side.owner, "step:after-deprecation")
    assert not any(block.source_ref == source_ref for block in refreshed.blocks)
    with side.uow(readonly=True) as uow:
        assert context.require_final(uow, previous.id) == previous
        assert uow.repo(TextStore).get_many((digest,)) == original_texts
        assert execution.get_attempt_activity(uow, attempt.id)["exposed_lesson_refs"] == lesson_refs
        persisted = uow.repo(LessonRepository).get(knowledge.LessonId(UUID(str(ref.lesson_id))))
        assert persisted.row_version == 2
        assert persisted.state is knowledge.LessonState.DEPRECATED


def test_new_assembly_rechecks_lesson_access_after_membership_revocation(ctx_side: ContextSide) -> None:
    side = ctx_side
    _enable_recall(side)
    reader = Actor(PrincipalId(uuid4()), PrincipalKind.HUMAN, "reader")
    now = side.clock.now()
    with side.uow() as uow:
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=reader.principal_id,
                kind=reader.kind,
                display_name=reader.display_name,
                created_by=side.owner.principal_id,
                now=now,
            )
        )
        uow.repo(MembershipRepository).upsert(
            Membership(ScopeId(side.proj), reader.principal_id, Role.VIEWER, None, now)
        )
        ref = knowledge.promote_lesson(
            uow,
            _candidate(side.ws, side.proj, "Use the staging pool"),
            actor=side.owner,
            now=now,
            supersedes=None,
        )
        uow.commit()

    source = f"knowledge:{ref.lesson_id}"
    assert any(block.source_ref == source for block in _assemble(side, reader, "step:before-revoke").blocks)
    with side.uow() as uow:
        uow.repo(MembershipRepository).delete(ScopeId(side.proj), reader.principal_id)
        uow.commit()
    assert all(block.source_ref != source for block in _assemble(side, reader, "step:after-revoke").blocks)
