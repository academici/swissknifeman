"""Unit tests for Phase-A/B/C context domain protocol and work-policy rules (P09.04.a)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import ContextManifestId, FileVersionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import BLOCK_SPECS, BlockType, BudgetClass, TrustLevel
from skm.modules.context.domain.budget import apply_budget
from skm.modules.context.domain.contracts import Digest
from skm.modules.context.domain.decide import decide, decide_with_diagnostics
from skm.modules.context.domain.draft import (
    BudgetPolicy,
    ConditionalBlock,
    ContextDraft,
    DraftBlock,
    compute_draft_digest,
    draft_meta_of,
    make_repo_instruction_requests,
    make_repo_path_request,
)
from skm.modules.context.domain.finalize import (
    finalize,
    host_facts_to_meta,
    sha256_text,
    verify_finalization,
)
from skm.modules.context.domain.host_inputs import (
    HostBlock,
    HostBlockMeta,
    HostFacts,
    HostInputKind,
    HostInputRequest,
    HostReadStatus,
    HostSelector,
)
from skm.modules.context.domain.manifest import ManifestState, draft_block_to_manifest_row
from skm.modules.context.domain.reasons import ExcludeReason, IncludeReason
from skm.modules.context.domain.render import (
    EntityPromptScope,
    fence,
    format_host_block,
    render,
    render_block_text,
    render_task_contract_markdown,
    substitute,
)
from skm.modules.context.domain.request import ResumeInfo, validate_work_policy
from skm.modules.context.module import MODULE
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

_NOW = datetime(2026, 11, 15, 7, 0, tzinfo=UTC)
_MANIFEST_ID = ContextManifestId(UUID("01900000-0000-7000-8000-000000000701"))
_PROMPT_FV_ID = FileVersionId(UUID("01900000-0000-7000-8000-000000000702"))
_EST = HeuristicTokenEstimator()
_TEMPLATES = {"shared/block_wrapper": "## {{ block.title }}\n\n{{ block.content }}"}


def _hblock(
    request_id: str,
    status: HostReadStatus,
    resolved_path: str | None = None,
    *,
    text: str | None = None,
    text_digest: Digest | None = None,
    size_bytes: int | None = None,
    tokens_estimate: int | None = None,
) -> HostBlock:
    return HostBlock(request_id, status, resolved_path, text, text_digest, size_bytes, tokens_estimate)


def _hmeta(
    request_id: str,
    status: HostReadStatus,
    resolved_path: str | None = None,
    text_digest: Digest | None = None,
    size_bytes: int | None = None,
    tokens_estimate: int | None = None,
    research_query_ids: tuple[str, ...] = (),
) -> HostBlockMeta:
    return HostBlockMeta(
        request_id, status, resolved_path, text_digest, size_bytes, tokens_estimate, research_query_ids
    )


def _hfacts(
    *,
    deps: frozenset[str] = frozenset(),
    work_paths: tuple[tuple[str, str], ...] = (),
    work_paths_truncated: bool = False,
    baseline: Mapping[str, str] | None = None,
) -> HostFacts:
    return HostFacts(deps, work_paths, work_paths_truncated, {} if baseline is None else baseline)


def _dblock(
    ordinal: int,
    btype: BlockType,
    content: str,
    *,
    title: str = "",
    mandatory: bool | None = None,
    bclass: BudgetClass | None = None,
    source_ref: str | None = None,
    reason: IncludeReason = IncludeReason.MANDATORY,
    atomic_group: str | None = None,
) -> DraftBlock:
    spec = BLOCK_SPECS[btype]
    eff_mand = (spec.mandatory == "always") if mandatory is None else mandatory
    eff_cls = spec.budget_class if bclass is None else bclass
    sref = source_ref or f"src:{btype.value}:{ordinal}"
    norm = content.strip()
    rendered = render_block_text(
        block_type=btype,
        title=title or btype.value,
        content=norm,
        source_ref=sref,
        templates=_TEMPLATES,
        prompt_plan={},
        variables={},
    )
    return DraftBlock(
        ordinal=ordinal,
        block_type=btype,
        budget_class=eff_cls,
        mandatory=eff_mand,
        source_kind="spec",
        source_ref=sref,
        source_version="v1",
        trust=TrustLevel.SYSTEM if eff_mand else TrustLevel.PROJECT,
        atomic_group=atomic_group,
        title=title or btype.value,
        content=norm,
        content_digest=sha256_text(norm),
        tokens_estimate=_EST.estimate(rendered),
        reason=reason if not eff_mand else IncludeReason.MANDATORY,
    )


def _mandatory_six(
    *, wp_raw: JsonObject | None = None, start_ord: int = 0
) -> tuple[tuple[DraftBlock, ...], str]:
    default_wp: JsonObject = {
        "intensity": "medium",
        "verification_intensity": "medium",
        "warn_seconds": 900,
        "emergency_wall_seconds": 3600,
    }
    policy = validate_work_policy(wp_raw or default_wp, role="executor")
    escope = EntityPromptScope(
        "U-01",
        "Implement protocol",
        "Ship deterministic draft/final context protocol.",
        "Reproducibility",
        "code",
        "Follow context spec.",
        "(none)",
        ("repo:src/skm/modules/context/**",),
        ("repo:../swissknifeman/**",),
        ("context protocol",),
        (),
        ("domain purity",),
        frozenset({"U-01"}),
    )
    tc_md = render_task_contract_markdown(escope, policy, _TEMPLATES, {}, {})
    specs = (
        (BlockType.SYSTEM_CONSTRAINTS, "Obey sandbox boundaries."),
        (BlockType.ROLE_CONTRACT, "Act as executor."),
        (BlockType.RUN_RULES, f"Verification intensity: {policy.verification_intensity}."),
        (BlockType.TASK_CONTRACT, tc_md),
        (BlockType.ACCEPTANCE, "Pass unit and contract checks."),
        (BlockType.RESULT_CONTRACT, "Emit executor JSON result."),
    )
    return tuple(_dblock(start_ord + i, bt, body) for i, (bt, body) in enumerate(specs)), tc_md


def _make_draft(
    blocks: tuple[DraftBlock, ...],
    *,
    conditional: tuple[ConditionalBlock, ...] = (),
    host_inputs: tuple[HostInputRequest, ...] = (),
    total_limit: int = 50000,
    supporting_limit: int | None = None,
    retrieval_limit: int | None = None,
    core_limit: int | None = None,
    skills_budget: int = 500,
    resume: ResumeInfo | None = None,
    repo_max_files: int = 2,
) -> ContextDraft:
    budget = BudgetPolicy(
        total_limit=total_limit,
        class_limits={
            BudgetClass.CORE: core_limit,
            BudgetClass.TASK: None,
            BudgetClass.SUPPORTING: supporting_limit,
            BudgetClass.RETRIEVAL: retrieval_limit,
        },
        skills_budget=skills_budget,
        estimator_id=_EST.estimator_id,
    )
    meta = draft_meta_of(
        manifest_id=_MANIFEST_ID,
        blocks=blocks,
        conditional=conditional,
        host_inputs=host_inputs,
        budget=budget,
        resume=resume,
        repo_max_files=repo_max_files,
    )
    cond_deps: JsonObject = {f"c:{cb.block.ordinal}": list[JsonValue](sorted(cb.deps)) for cb in conditional}
    res_j: JsonValue = (
        None
        if resume is None
        else {"session_ref": resume.session_ref, "previous_task_digest": resume.previous_task_digest}
    )
    skills_trace: JsonObject = {
        "mode": "auto",
        "skills_budget": skills_budget,
        "skills_remaining": budget.skills_budget,
        "repo_max_files": repo_max_files,
        "conditional_deps": cond_deps,
        "resume": res_j,
    }
    return ContextDraft(
        manifest_id=_MANIFEST_ID,
        blocks=blocks,
        conditional=conditional,
        excluded=(),
        host_inputs=host_inputs,
        templates=_TEMPLATES,
        prompt_plan={},
        variables={"role": {"name": "executor"}, "runtime": {"id": "codex_cli", "model": "gpt-5"}},
        budget=budget,
        resume=resume,
        skills_trace=skills_trace,
        diagnostics=(),
        draft_digest=compute_draft_digest(meta),
        repo_max_files=repo_max_files,
    )


def _ok_host_block(draft: ContextDraft, req: HostInputRequest, text: str, path: str) -> HostBlock:
    hb_raw = _hblock(req.request_id, HostReadStatus.OK, path, text=text)
    btype, title, body, sref = format_host_block(req, hb_raw)
    wrapped = render_block_text(
        block_type=btype,
        title=title,
        content=body,
        source_ref=sref,
        templates=draft.templates,
        prompt_plan=draft.prompt_plan,
        variables=draft.variables,
    )
    return _hblock(
        req.request_id,
        HostReadStatus.OK,
        path,
        text=text,
        text_digest=sha256_text(text),
        size_bytes=len(text.encode("utf-8")),
        tokens_estimate=_EST.estimate(wrapped),
    )


def test_substitute_closed_namespaces_non_recursive_and_errors() -> None:
    variables: dict[str, JsonValue] = {
        "task": {"key": "U-01", "goal": "Literal {{ role.name }} must not expand", "rules": ["r1", "r2"]},
        "role": {"name": "executor", "warn_seconds": 600},
    }
    rendered = substitute(
        "Task {{ task.key }} ({{ role.warn_seconds }}s):\n{{ task.goal }}\n{{ task.rules }}", variables
    )
    assert "Task U-01 (600s):" in rendered
    assert "Literal {{ role.name }} must not expand" in rendered
    assert "- r1\n- r2" in rendered

    for bad_tpl in ("{{ env.SECRET }}", "{{ invalid }}", "{{ task.missing }}", "unclosed {{ task.key"):
        with pytest.raises(ValidationFailed) as exc_info:
            substitute(bad_tpl, variables)
        assert exc_info.value.code is ErrorCode.CONTEXT_TEMPLATE_INVALID


def test_fence_escapes_inner_backtick_runs() -> None:
    assert fence("def f():\n    return 1\n", "python") == "```python\ndef f():\n    return 1\n```"
    nested = fence("Example:\n```python\nx = 1\n```\n````md\ny\n````", "markdown")
    assert (nested.startswith("`````markdown\n"), nested.endswith("\n`````")) == (True, True)


def _cskill(ordinal: int, body: str, dep: str) -> ConditionalBlock:
    return ConditionalBlock(
        block=_dblock(ordinal, BlockType.SKILLS, body, mandatory=False, reason=IncludeReason.TRIGGER_DEP),
        condition="deps_any",
        deps=frozenset({dep}),
    )


def test_conditional_skills_host_statuses_and_tamper_checks() -> None:
    mand, _ = _mandatory_six()
    c_match = _cskill(10, "pytest guidance", "pytest")
    c_miss = _cskill(11, "django guidance", "django")
    c_over = _cskill(12, "heavy skill " * 80, "pytest")
    hi_reqs = make_repo_instruction_requests(
        0,
        write_paths=("repo:src/pkg/mod.py",),
        max_files=3,
        files=("AGENTS.md",),
        max_bytes=200,
        constraints_only=False,
        sections=(),
        self_loaded_files=("AGENTS.md",),
    )
    dep_req = HostInputRequest(
        "hi:3",
        HostInputKind.DEPENDENCY_MANIFEST,
        "repo",
        "pyproject.toml",
        (),
        HostSelector("whole"),
        1000,
        False,
        None,
        TrustLevel.REPOSITORY,
        "repo:repo/pyproject.toml",
        False,
        (),
        None,
    )
    draft = _make_draft(
        mand,
        conditional=(c_match, c_miss, c_over),
        host_inputs=(*hi_reqs, dep_req),
        skills_budget=40,
        repo_max_files=2,
    )
    hb0 = _hblock("hi:0", HostReadStatus.SELF_LOADED, "AGENTS.md")
    hb1 = _ok_host_block(draft, hi_reqs[1], "Keep modules pure.", "src/AGENTS.md")
    hb2 = _hblock("hi:2", HostReadStatus.MISSING)
    hb3 = _hblock("hi:3", HostReadStatus.OK, "pyproject.toml", size_bytes=20)

    fin = finalize(draft, (hb0, hb1, hb2, hb3), _hfacts(deps=frozenset({"pytest"})), _EST)
    inc_refs = {ref for ref, _ in fin.selection.included}
    exc_by_ref = {ref: rsn for ref, rsn, _ in fin.selection.excluded}
    assert {"c:10", "h:hi:1"}.issubset(inc_refs)
    assert exc_by_ref["c:11"] is ExcludeReason.TRIGGER_NOT_MET
    assert exc_by_ref["c:12"] is ExcludeReason.OVER_SKILL_BUDGET
    assert exc_by_ref["h:hi:0"] is ExcludeReason.RUNTIME_SELF_LOADED
    assert exc_by_ref["h:hi:2"] is ExcludeReason.NOT_FOUND
    assert not any(b.block_ref == "h:hi:3" for b in fin.manifest.blocks)

    meta = draft_meta_of(
        manifest_id=draft.manifest_id,
        blocks=draft.blocks,
        conditional=draft.conditional,
        host_inputs=draft.host_inputs,
        budget=draft.budget,
        resume=None,
        repo_max_files=draft.repo_max_files,
    )
    base_hm = [
        _hmeta("hi:0", HostReadStatus.SELF_LOADED, "AGENTS.md"),
        _hmeta(
            "hi:1", HostReadStatus.OK, "src/AGENTS.md", hb1.text_digest, hb1.size_bytes, hb1.tokens_estimate
        ),
        _hmeta("hi:2", HostReadStatus.MISSING),
        _hmeta("hi:3", HostReadStatus.OK, "pyproject.toml", None, 20, None),
    ]
    bad_h1 = _hmeta("hi:1", HostReadStatus.OK, "src/AGENTS.md", hb1.text_digest, 999, 10)
    tampered_cases = [
        base_hm[:-1],
        [*base_hm, base_hm[0]],
        [*base_hm[:-1], _hmeta("hi:999", HostReadStatus.MISSING)],
        [_hmeta("hi:0", HostReadStatus.SELF_LOADED, "CLAUDE.md"), *base_hm[1:]],
        [base_hm[0], bad_h1, *base_hm[2:]],
        [base_hm[0], base_hm[1], _hmeta("hi:2", HostReadStatus.OVER_MAX_FILES), base_hm[3]],
    ]
    for bad_hm in tampered_cases:
        with pytest.raises(ValidationFailed) as exc_info:
            decide(meta, bad_hm, _hfacts())
        assert exc_info.value.code is ErrorCode.CONTEXT_MANIFEST_TAMPERED


def test_required_host_input_missing_raises_context_input_missing() -> None:
    mand, _ = _mandatory_six()
    req = make_repo_path_request("hi:0", mount="repo", path="docs/spec.md", max_bytes=4096, required=True)
    draft = _make_draft(mand, host_inputs=(req,))
    with pytest.raises(PreconditionFailed) as exc_info:
        finalize(draft, (_hblock("hi:0", HostReadStatus.MISSING, "docs/spec.md"),), _hfacts(), _EST)
    assert exc_info.value.code is ErrorCode.CONTEXT_INPUT_MISSING


def test_budget_cuts_atomic_groups_class_warning_and_total_over_budget() -> None:
    mand, _ = _mandatory_six()
    g1 = _dblock(
        6,
        BlockType.MEMORY,
        "Lesson A " * 15,
        mandatory=False,
        reason=IncludeReason.MEMORY_MATCH,
        atomic_group="l1",
    )
    g2 = _dblock(
        7,
        BlockType.MEMORY,
        "Lesson B " * 15,
        mandatory=False,
        reason=IncludeReason.MEMORY_MATCH,
        atomic_group="l1",
    )
    opt_mat = _dblock(
        8, BlockType.MATERIALS, "Optional ref " * 20, mandatory=False, reason=IncludeReason.OPTIONAL_MATERIAL
    )
    draft = _make_draft(
        (*mand, g1, g2, opt_mat),
        core_limit=1,
        retrieval_limit=g1.tokens_estimate,
        supporting_limit=opt_mat.tokens_estimate - 1,
    )
    meta = draft_meta_of(
        manifest_id=draft.manifest_id,
        blocks=draft.blocks,
        conditional=(),
        host_inputs=(),
        budget=draft.budget,
        resume=None,
    )
    sel, diags = decide_with_diagnostics(meta, (), _hfacts())
    exc_map = {ref: (rsn, det) for ref, rsn, det in sel.excluded}
    assert exc_map["d:6"] == (ExcludeReason.OVER_BUDGET_RETRIEVAL, "atomic_group:l1[d:6,d:7]")
    assert exc_map["d:7"][0] is ExcludeReason.OVER_BUDGET_RETRIEVAL
    assert exc_map["d:8"][0] is ExcludeReason.OVER_BUDGET_SUPPORTING
    assert any(d.get("code") == "CLASS_OVER_LIMIT" and d.get("budget_class") == "core" for d in diags)

    b_sel = apply_budget(draft.blocks, draft.budget)
    assert {ref for ref, _ in b_sel.included} == {f"d:{i}" for i in range(6)}
    assert {ref for ref, _, _ in b_sel.excluded} == {"d:6", "d:7", "d:8"}

    with pytest.raises(PreconditionFailed) as exc_info:
        finalize(_make_draft(mand, total_limit=5), (), _hfacts(), _EST)
    assert exc_info.value.code is ErrorCode.CONTEXT_OVER_BUDGET


def test_task_digest_stability_and_full_vs_delta_resume_modes() -> None:
    mand, _ = _mandatory_six(start_ord=1)
    rnote = _dblock(0, BlockType.RESUME_NOTE, "Resuming s1", mandatory=False, reason=IncludeReason.MANDATORY)
    ans = _dblock(
        7,
        BlockType.DECISION_ANSWERS,
        "Answer: proceed",
        mandatory=False,
        reason=IncludeReason.EXECUTION_INPUT,
    )
    hist = _dblock(8, BlockType.HISTORY, "Step 1 done", mandatory=False, reason=IncludeReason.RECENT_HISTORY)
    fin1 = finalize(_make_draft((*mand, hist)), (), _hfacts(), _EST)
    assert fin1.selection.mode == "full"

    hist2 = _dblock(
        8, BlockType.HISTORY, "Steps 1..2 done", mandatory=False, reason=IncludeReason.RECENT_HISTORY
    )
    round2 = _make_draft(
        (rnote, *mand, ans, hist2),
        resume=ResumeInfo(session_ref="sess_1", previous_task_digest=fin1.selection.task_digest),
    )
    fin2 = finalize(round2, (), _hfacts(), _EST)
    assert fin2.selection.task_digest == fin1.selection.task_digest
    assert fin2.selection.mode == "delta"
    assert {ref for ref, _ in fin2.selection.included} == {"d:0", "d:7"}
    exc2 = {ref: rsn for ref, rsn, _ in fin2.selection.excluded}
    assert exc2["d:8"] is ExcludeReason.IN_RESUMED_SESSION
    assert exc2["d:1"] is ExcludeReason.IN_RESUMED_SESSION

    round3 = _make_draft(
        (rnote, *mand, ans),
        resume=ResumeInfo(session_ref="sess_1", previous_task_digest=sha256_text("stale")),
    )
    fin3 = finalize(round3, (), _hfacts(), _EST)
    assert fin3.selection.mode == "full"
    assert ("d:0", ExcludeReason.FULL_PROMPT, None) in fin3.selection.excluded


def test_render_concatenation_and_server_verify_finalization() -> None:
    mand, _ = _mandatory_six()
    req = make_repo_path_request("hi:0", mount="repo", path="src/app.py", max_bytes=4096, required=False)
    draft = _make_draft(mand, host_inputs=(req,))
    stored_draft = replace(
        finalize(draft, (_hblock("hi:0", HostReadStatus.MISSING),), _hfacts(), _EST).manifest,
        state=ManifestState.DRAFT,
        mode=None,
        task_digest=None,
        prompt_digest=None,
        total_tokens_estimate=None,
        host_facts=None,
        finalized_at=None,
        blocks=tuple(draft_block_to_manifest_row(b) for b in draft.blocks),
    )
    draft_with_manifest = replace(draft, manifest=stored_draft)
    hb = _ok_host_block(draft_with_manifest, req, "x = 42\n", "src/app.py")
    facts = _hfacts(deps=frozenset({"pytest"}), work_paths=(("repo", "src/app.py"),))
    fin = finalize(draft_with_manifest, (hb,), facts, _EST)
    prompt, pieces = render(draft_with_manifest, (hb,), fin.selection)
    assert "".join(pieces) == prompt == fin.rendered_prompt
    assert prompt.endswith("\n")
    assert "```python\nx = 42\n```" in prompt

    hm = (_hmeta("hi:0", HostReadStatus.OK, "src/app.py", hb.text_digest, hb.size_bytes, hb.tokens_estimate),)
    verified, host_rows = verify_finalization(
        stored_draft,
        draft_digest=draft.draft_digest,
        estimator_id=_EST.estimator_id,
        host_meta=hm,
        facts_meta=host_facts_to_meta(facts),
        claimed_selection=fin.selection,
        rendered_prompt_digest=fin.prompt_digest,
        artifact_prompt_digest=fin.prompt_digest,
        prompt_file_version_id=_PROMPT_FV_ID,
        finalized_at=_NOW,
    )
    assert (verified.state, verified.prompt_file_version_id) == (ManifestState.FINAL, _PROMPT_FV_ID)
    assert [r.block_ref for r in host_rows] == ["h:hi:0"]

    forged_sel = replace(fin.selection, included=fin.selection.included[:-1])
    with pytest.raises(ValidationFailed) as exc_info:
        verify_finalization(
            stored_draft,
            draft_digest=draft.draft_digest,
            estimator_id=_EST.estimator_id,
            host_meta=hm,
            facts_meta=host_facts_to_meta(facts),
            claimed_selection=forged_sel,
            rendered_prompt_digest=fin.prompt_digest,
            artifact_prompt_digest=fin.prompt_digest,
            prompt_file_version_id=_PROMPT_FV_ID,
            finalized_at=_NOW,
        )
    assert exc_info.value.code is ErrorCode.CONTEXT_MANIFEST_TAMPERED


def test_work_policy_validation_digests_light_mandatory_preservation_and_guarded_bus() -> None:
    for invalid_wp in (
        None,
        {},
        {"intensity": "extreme", "verification_intensity": "medium", "warn_seconds": 600},
        {"intensity": "light", "verification_intensity": "medium", "warn_seconds": 0},
        {
            "intensity": "light",
            "verification_intensity": "light",
            "warn_seconds": 300,
            "digest": "sha256:bad",
        },
    ):
        with pytest.raises(ValidationFailed) as exc_info:
            validate_work_policy(invalid_wp, role="executor")
        assert exc_info.value.code is ErrorCode.SCHEMA_INVALID

    light_blocks, light_tc = _mandatory_six(
        wp_raw={
            "intensity": "light",
            "verification_intensity": "light",
            "warn_seconds": 300,
            "emergency_wall_seconds": 1800,
            "soft_warnings": [
                {"kind": "role", "role": "executor", "actual_seconds": 350, "expected_seconds": 300}
            ],
        }
    )
    heavy_blocks, _ = _mandatory_six(
        wp_raw={
            "intensity": "heavy",
            "verification_intensity": "heavy",
            "warn_seconds": 1800,
            "emergency_wall_seconds": 7200,
        }
    )
    fin_light = finalize(_make_draft(light_blocks), (), _hfacts(), _EST)
    fin_heavy = finalize(_make_draft(heavy_blocks), (), _hfacts(), _EST)

    assert fin_light.selection.task_digest != fin_heavy.selection.task_digest
    assert fin_light.prompt_digest != fin_heavy.prompt_digest
    assert "advisory soft warning, not a hard cutoff" in light_tc
    assert "continue authorized work" in light_tc
    assert {b.block_type for b in fin_light.manifest.blocks if b.included is True} == {
        BlockType.SYSTEM_CONSTRAINTS,
        BlockType.ROLE_CONTRACT,
        BlockType.RUN_RULES,
        BlockType.TASK_CONTRACT,
        BlockType.ACCEPTANCE,
        BlockType.RESULT_CONTRACT,
    }
    from skm.application_bus.registry import IdempotencyMode
    from skm.modules.context.application.commands.finalize_manifest import SPEC

    assert SPEC in MODULE.commands
    assert SPEC.idempotency is IdempotencyMode.FORBIDDEN
    assert SPEC.permission == "worker.claim"
    assert SPEC.permission_alternatives == ("run.control", "context.assemble")
