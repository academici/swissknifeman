"""Dual-backend repository and Phase-A/B/C protocol contract tests (P09.04.a)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import UUID

import psycopg
import pytest

from fakes.ids import SequentialIds
from skm.adapters.postgres.uow import PostgresUnitOfWork
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ContextManifestId, PrincipalId, ScopeId
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.context import public as context
from skm.modules.context.application.commands.finalize_manifest import FinalizeManifest
from skm.modules.context.domain.blocks import BlockType
from skm.modules.context.domain.finalize import host_facts_to_meta, sha256_text, verify_finalization
from skm.modules.context.domain.host_inputs import (
    HostBlock,
    HostBlockMeta,
    HostFacts,
    HostInputKind,
    HostInputRequest,
    HostReadStatus,
)
from skm.modules.context.domain.manifest import ManifestState
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.ports import ContextRepository, TextStore
from skm.modules.extensions import public as extensions
from skm.modules.extensions.generated.commands import SyncBuiltinPacks

from .harness import ContextSide, core_pack, default_work_policy


def test_standalone_manifest_owns_assembly_reads_and_finalization(ctx_side: ContextSide) -> None:
    side = ctx_side
    another = cast(
        "access.CreatePrincipalResult",
        side.client.dispatch(
            access.CreatePrincipal.from_json({"kind": "human", "display_name": "Another project member"}),
            idempotency_key="create-context-test-member",
        ),
    )
    outsider = Actor(PrincipalId(another.principal_id), PrincipalKind.HUMAN, "Another project member")
    with side.uow() as uow:
        access.grant_initial_membership(
            uow,
            scope_id=ScopeId(side.proj),
            principal_id=outsider.principal_id,
            role=access.Role.MEMBER,
            now=side.clock.now(),
        )
        owner = f"standalone:{side.owner.principal_id}"
        cfg = side.effective_config(uow)
        base = side.make_request(uow, config=cfg)
        req = replace(
            base,
            plan_id=None,
            revision_id=None,
            entity_id=None,
            purpose=replace(base.purpose, step_ref=None),
        )
        ids = SequentialIds()
        manifest_id = ContextManifestId(ids.new_id())
        with pytest.raises(Forbidden):
            context.assemble_draft(
                uow,
                side.app.gateways,
                req,
                config=cfg,
                owner_ref=owner,
                actor=outsider,
                manifest_id=manifest_id,
            )
        if isinstance(uow, PostgresUnitOfWork):
            uow.connection.execute("SET LOCAL ROLE skm_app")
        draft = context.assemble_draft(
            uow,
            side.app.gateways,
            req,
            config=cfg,
            owner_ref=owner,
            actor=side.owner,
            manifest_id=manifest_id,
        )
        # The same principal may own several standalone manifests.
        context.assemble_draft(
            uow,
            side.app.gateways,
            req,
            config=cfg,
            owner_ref=owner,
            actor=side.owner,
            manifest_id=ContextManifestId(ids.new_id()),
        )
        uow.commit()
    blocks, _, facts = _resolve_host_inputs(draft, side)
    finalized = context.finalize(draft, blocks, facts, side.estimator)
    assert finalized.manifest.owner_ref == owner
    prompt_version = side.upload_text(finalized.rendered_prompt)
    command = FinalizeManifest.from_json(
        context.finalize_command(
            draft, finalized, blocks, facts, prompt_version, store_content=False, runtime_self_loaded=()
        )
    )
    other_client = side.app.client(actor=outsider, surface=Surface.CLI)
    query = context.ExplainContextRequest.from_json(
        {"project_id": str(side.proj), "manifest_id": str(manifest_id)}
    )
    assert cast("context.ContextExplainResponse", side.client.ask(query))["state"] == "draft"
    with pytest.raises(NotFound):
        other_client.ask(query)
    with pytest.raises(Forbidden):
        other_client.dispatch(command)
    side.client.dispatch(command)
    with side.uow(readonly=True) as uow:
        stored = context.require_final(uow, draft.manifest_id)
        assert stored.owner_ref == owner
        assert stored.purpose.step_ref is None
        assert (stored.plan_id, stored.revision_id, stored.entity_id) == (None, None, None)
    with pytest.raises(Forbidden):
        other_client.dispatch(command)


def _resolve_host_inputs(
    draft: context.ContextDraft,
    side: ContextSide,
    *,
    repo_file_text: str = "def target() -> int:\n    return 1\n",
) -> tuple[tuple[HostBlock, ...], tuple[HostBlockMeta, ...], HostFacts]:
    blocks: list[HostBlock] = []
    metas: list[HostBlockMeta] = []
    for req in draft.host_inputs:
        if req.kind is HostInputKind.REPO_INSTRUCTIONS:
            if req.path == "AGENTS.md":
                hb = HostBlock(
                    req.request_id, HostReadStatus.SELF_LOADED, "AGENTS.md", None, None, None, None
                )
            else:
                hb = HostBlock(req.request_id, HostReadStatus.MISSING, None, None, None, None, None)
        elif req.kind is HostInputKind.REPOSITORY_PATH:
            hb = _make_ok_host_block(draft, req, repo_file_text, req.path, side)
        else:
            hb = HostBlock(req.request_id, HostReadStatus.MISSING, None, None, None, None, None)
        blocks.append(hb)
        metas.append(
            HostBlockMeta(
                req.request_id,
                hb.status,
                hb.resolved_path,
                hb.text_digest,
                hb.size_bytes,
                hb.tokens_estimate,
                (),
            )
        )
    facts = HostFacts(
        deps=frozenset({"pytest"}),
        work_paths=(("repo", "src/target.py"),),
        work_paths_truncated=False,
        baseline={"repo": "deadbeef"},
    )
    return tuple(blocks), tuple(metas), facts


def _make_ok_host_block(
    draft: context.ContextDraft, req: HostInputRequest, text: str, path: str, side: ContextSide
) -> HostBlock:
    probe = HostBlock(req.request_id, HostReadStatus.OK, path, text, None, None, None)
    btype, title, body, sref = format_host_block(req, probe)
    wrapped = render_block_text(
        block_type=btype,
        title=title,
        content=body,
        source_ref=sref,
        templates=draft.templates,
        prompt_plan=draft.prompt_plan,
        variables=draft.variables,
    )
    return HostBlock(
        request_id=req.request_id,
        status=HostReadStatus.OK,
        resolved_path=path,
        text=text,
        text_digest=sha256_text(text),
        size_bytes=len(text.encode("utf-8")),
        tokens_estimate=side.estimator.estimate(wrapped),
    )


def test_text_store_append_only_roundtrip_idempotency_and_digest_verification(ctx_side: ContextSide) -> None:
    t1, t2 = "Alpha text body", "Кириллица и Latin body"
    d1, d2 = sha256_text(t1), sha256_text(t2)

    with ctx_side.uow() as uow:
        store = uow.repo(TextStore)
        store.put_many({d1: t1, d2: t2})
        store.put_many({d1: t1})
        uow.commit()

    with ctx_side.uow(readonly=True) as uow:
        got = uow.repo(TextStore).get_many((d1, d2, sha256_text("missing")))
        assert got == {d1: t1, d2: t2}
        uow.rollback()

    with ctx_side.uow() as uow:
        with pytest.raises(ValidationFailed) as exc_info:
            uow.repo(TextStore).put_many({d1: "tampered content"})
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
        uow.rollback()


def test_manifest_lifecycle_require_final_plan_audit_sentinel_and_immutability(ctx_side: ContextSide) -> None:
    ids = SequentialIds()
    with ctx_side.uow() as uow:
        cfg = ctx_side.effective_config(uow)
        draft = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(uow, config=cfg, step_ref="run:1/step:unit"),
            config=cfg,
            owner_ref="step:run:1/step:unit",
        )
        audit_draft = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(
                uow,
                config=cfg,
                step_ref="run:1/step:plan-audit",
                entity_id=None,
                role="advisor",
                stage_id="plan_audit",
            ),
            config=cfg,
            owner_ref="step:run:1/step:plan-audit",
        )
        uow.commit()

    with ctx_side.uow(readonly=True) as uow:
        with pytest.raises(NotFound):
            uow.repo(ContextRepository).get(ContextManifestId(UUID("01900000-0000-7000-8000-00000000ffff")))
        loaded_audit = uow.repo(ContextRepository).get(audit_draft.manifest_id)
        assert loaded_audit.entity_id is None
        assert loaded_audit.purpose.step_ref == "run:1/step:plan-audit"

        with pytest.raises(PreconditionFailed) as exc_info:
            context.require_final(uow, draft.manifest_id)
        assert exc_info.value.code is ErrorCode.CONTEXT_NOT_FINALIZED
        uow.rollback()

    # Duplicate step_ref within the same workspace raises Conflict(ALREADY_EXISTS)
    with ctx_side.uow() as uow:
        stored_for_dup = uow.repo(ContextRepository).get(draft.manifest_id)
        dup = replace(stored_for_dup, id=ContextManifestId(ids.new_id()))
        with pytest.raises(Conflict) as exc_info:
            uow.repo(ContextRepository).add_draft(dup)
        assert exc_info.value.code is ErrorCode.ALREADY_EXISTS
        uow.rollback()

    # Phase B (host-local pure finalize) + Phase C (server verify_finalization + repo.finalize)
    h_blocks, h_metas, facts = _resolve_host_inputs(draft, ctx_side)
    fin = context.finalize(draft, h_blocks, facts, ctx_side.estimator)
    real_prompt_fv_id = ctx_side.upload_text(fin.rendered_prompt, filename="rendered-prompt.md")
    without_claim = context.finalize_command(
        draft, fin, h_blocks, facts, real_prompt_fv_id, store_content=False, runtime_self_loaded=()
    )
    with pytest.raises(ValidationFailed, match="current execution claim"):
        ctx_side.client.dispatch(FinalizeManifest.from_json(without_claim))
    finalized_at = ctx_side.clock.now() + timedelta(seconds=5)

    with ctx_side.uow() as uow:
        repo = uow.repo(ContextRepository)
        stored_draft = repo.get(draft.manifest_id, for_update=True)
        verified_final, host_rows = verify_finalization(
            stored_draft,
            draft_digest=draft.draft_digest,
            estimator_id=ctx_side.estimator.estimator_id,
            host_meta=h_metas,
            facts_meta=host_facts_to_meta(facts),
            claimed_selection=fin.selection,
            rendered_prompt_digest=fin.prompt_digest,
            artifact_prompt_digest=fin.prompt_digest,
            prompt_file_version_id=real_prompt_fv_id,
            finalized_at=finalized_at,
        )
        tampered_header = replace(
            verified_final,
            purpose=replace(verified_final.purpose, step_ref="run:1/step:forged"),
        )
        with pytest.raises(ValidationFailed) as exc_info:
            repo.finalize(tampered_header, host_rows=host_rows)
        assert exc_info.value.code is ErrorCode.CONTEXT_MANIFEST_TAMPERED

        repo.finalize(verified_final, host_rows=host_rows)
        uow.commit()

    with ctx_side.uow(readonly=True) as uow:
        persisted = context.require_final(uow, draft.manifest_id)
        assert persisted.state is ManifestState.FINAL
        assert persisted.prompt_digest == fin.prompt_digest
        assert persisted.task_digest == fin.selection.task_digest
        assert persisted.prompt_file_version_id == real_prompt_fv_id
        assert persisted.finalized_at == finalized_at
        assert any(b.block_ref.startswith("h:hi:") and b.included is True for b in persisted.blocks)
        uow.rollback()

    with ctx_side.uow() as uow:
        with pytest.raises(PreconditionFailed) as exc_info:
            uow.repo(ContextRepository).finalize(verified_final, host_rows=host_rows)
        assert exc_info.value.code is ErrorCode.INVALID_TRANSITION
        uow.rollback()


def test_postgres_append_only_and_finalize_only_triggers(ctx_side: ContextSide) -> None:
    if ctx_side.kind != "postgres":
        return
    assert ctx_side.dsn is not None

    text_digest = sha256_text("trigger check body")
    with ctx_side.uow() as uow:
        uow.repo(TextStore).put_many({text_digest: "trigger check body"})
        cfg = ctx_side.effective_config(uow)
        draft = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(uow, config=cfg, step_ref="run:pg/step:triggers"),
            config=cfg,
            owner_ref="step:run:pg/step:triggers",
        )
        uow.commit()

    with psycopg.connect(ctx_side.dsn, autocommit=False) as conn:
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("UPDATE skm_context.texts SET text = 'mutated' WHERE digest = %s", (text_digest,))
        conn.rollback()
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("DELETE FROM skm_context.texts WHERE digest = %s", (text_digest,))
        conn.rollback()

    with psycopg.connect(ctx_side.dsn, autocommit=False) as conn:
        with pytest.raises(psycopg.errors.RestrictViolation, match="never deleted"):
            conn.execute("DELETE FROM skm_context.context_manifests WHERE id = %s", (draft.manifest_id,))
        conn.rollback()
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute(
                "UPDATE skm_context.context_manifests SET role = 'advisor' WHERE id = %s",
                (draft.manifest_id,),
            )
        conn.rollback()

    h_blocks, h_metas, facts = _resolve_host_inputs(draft, ctx_side)
    fin = context.finalize(draft, h_blocks, facts, ctx_side.estimator)
    pfv = ctx_side.upload_text(fin.rendered_prompt, filename="pg-trigger-prompt.md")
    with ctx_side.uow() as uow:
        repo = uow.repo(ContextRepository)
        stored = repo.get(draft.manifest_id, for_update=True)
        vf, hrows = verify_finalization(
            stored,
            draft_digest=draft.draft_digest,
            estimator_id=ctx_side.estimator.estimator_id,
            host_meta=h_metas,
            facts_meta=host_facts_to_meta(facts),
            claimed_selection=fin.selection,
            rendered_prompt_digest=fin.prompt_digest,
            artifact_prompt_digest=fin.prompt_digest,
            prompt_file_version_id=pfv,
            finalized_at=ctx_side.clock.now() + timedelta(seconds=1),
        )
        repo.finalize(vf, host_rows=hrows)
        uow.commit()

    with psycopg.connect(ctx_side.dsn, autocommit=False) as conn:
        with pytest.raises(psycopg.errors.RestrictViolation, match="not allowed"):
            conn.execute(
                "UPDATE skm_context.context_manifests SET total_tokens_estimate = 999 WHERE id = %s",
                (draft.manifest_id,),
            )
        conn.rollback()


def test_pack_pins_reproducibility_across_pack_upgrade_and_work_policy_parity(
    ctx_side: ContextSide,
) -> None:
    with ctx_side.uow() as uow:
        cfg = ctx_side.effective_config(uow)
        pins_v1 = extensions.pinned_pack_versions(uow, config=cfg)
        draft_v1 = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(uow, config=cfg, step_ref="run:pins/step:v1", pack_pins=pins_v1),
            config=cfg,
            owner_ref="step:run:pins/step:v1",
        )
        uow.commit()
    hb_v1, _, facts = _resolve_host_inputs(draft_v1, ctx_side)
    fin_v1 = context.finalize(draft_v1, hb_v1, facts, ctx_side.estimator)
    assert "Obey core v1 invariants." in fin_v1.rendered_prompt

    # 2. Install core@2.0.0; unpinned assembly picks 2.0.0, pinned reproduces 1.0.0!
    ctx_side.builtin.current = (
        core_pack("1.0.0", system_body="Obey core v1 invariants."),
        core_pack("2.0.0", system_body="Obey UPGRADED core v2 invariants."),
    )
    ctx_side.client.dispatch(SyncBuiltinPacks(), idempotency_key=ctx_side.client.new_idempotency_key())

    with ctx_side.uow() as uow:
        cfg = ctx_side.effective_config(uow)
        draft_unpinned = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(uow, config=cfg, step_ref="run:pins/step:unpinned-v2"),
            config=cfg,
            owner_ref="step:run:pins/step:unpinned-v2",
        )
        draft_pinned_replay = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(
                uow, config=cfg, step_ref="run:pins/step:pinned-v1-replay", pack_pins=pins_v1
            ),
            config=cfg,
            owner_ref="step:run:pins/step:pinned-v1-replay",
        )
        uow.commit()

    hb_v2, _, _ = _resolve_host_inputs(draft_unpinned, ctx_side)
    fin_v2 = context.finalize(draft_unpinned, hb_v2, facts, ctx_side.estimator)
    assert "Obey UPGRADED core v2 invariants." in fin_v2.rendered_prompt
    assert fin_v2.prompt_digest != fin_v1.prompt_digest

    hb_replay, _, _ = _resolve_host_inputs(draft_pinned_replay, ctx_side)
    fin_replay = context.finalize(draft_pinned_replay, hb_replay, facts, ctx_side.estimator)
    assert fin_replay.rendered_prompt == fin_v1.rendered_prompt
    assert fin_replay.prompt_digest == fin_v1.prompt_digest
    assert fin_replay.selection.task_digest == fin_v1.selection.task_digest

    # 3. End-to-end work_policy: light vs heavy digests + continuation rule + all 6 mandatory blocks kept
    with ctx_side.uow() as uow:
        cfg = ctx_side.effective_config(uow)
        draft_light = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(
                uow,
                config=cfg,
                step_ref="run:wp/step:light",
                work_policy=default_work_policy(
                    intensity="light",
                    verification_intensity="light",
                    warn_seconds=300,
                    emergency_wall_seconds=1800,
                ),
            ),
            config=cfg,
            owner_ref="step:run:wp/step:light",
        )
        draft_heavy = context.assemble_draft(
            uow,
            ctx_side.app.gateways,
            ctx_side.make_request(
                uow,
                config=cfg,
                step_ref="run:wp/step:heavy",
                work_policy=default_work_policy(
                    intensity="heavy",
                    verification_intensity="heavy",
                    warn_seconds=1800,
                    emergency_wall_seconds=7200,
                ),
            ),
            config=cfg,
            owner_ref="step:run:wp/step:heavy",
        )
        uow.commit()

    hb_l, _, _ = _resolve_host_inputs(draft_light, ctx_side)
    hb_h, _, _ = _resolve_host_inputs(draft_heavy, ctx_side)
    fin_light = context.finalize(draft_light, hb_l, facts, ctx_side.estimator)
    fin_heavy = context.finalize(draft_heavy, hb_h, facts, ctx_side.estimator)

    assert fin_light.selection.task_digest != fin_heavy.selection.task_digest
    assert fin_light.prompt_digest != fin_heavy.prompt_digest
    assert "advisory soft warning, not a hard cutoff" in fin_light.rendered_prompt
    assert "continue authorized work" in fin_light.rendered_prompt

    included_types = {b.block_type for b in fin_light.manifest.blocks if b.included is True}
    assert {
        BlockType.SYSTEM_CONSTRAINTS,
        BlockType.ROLE_CONTRACT,
        BlockType.RUN_RULES,
        BlockType.TASK_CONTRACT,
        BlockType.ACCEPTANCE,
        BlockType.RESULT_CONTRACT,
    }.issubset(included_types)
