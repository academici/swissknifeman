"""Budget decisions, host/server parity and atomic conditions and procedures."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.modules.context.domain.blocks import BlockType, BudgetClass
from skm.modules.context.domain.candidates import discover, objects
from skm.modules.context.domain.decide import decide, decide_with_diagnostics
from skm.modules.context.domain.digests import prompt_digest, task_digest
from skm.modules.context.domain.draft import draft_meta_of
from skm.modules.context.domain.finalize import finalize, host_facts_to_meta
from skm.modules.context.domain.manifest import draft_meta_from_manifest
from skm.modules.context.domain.policy import effective_policy, role_policy_spec
from skm.modules.context.domain.reasons import IncludeReason
from skm.modules.context.domain.request import ResumeInfo
from skm.modules.context.domain.selection import select
from skm.modules.context.domain.snapshot import estimate_text, snapshot
from skm.modules.context.domain.validation import validate
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

from .test_finalize import _EST, _cskill, _dblock, _hfacts, _make_draft, _mandatory_six
from .test_policy_matrix import core_sources, make_candidate, make_request, pipeline


def meta(draft):
    return draft_meta_of(
        manifest_id=draft.manifest_id,
        blocks=draft.blocks,
        conditional=draft.conditional,
        host_inputs=draft.host_inputs,
        budget=draft.budget,
        resume=draft.resume,
    )


@given(st.lists(st.text(alphabet="abc абв\n", min_size=1, max_size=100), max_size=8))
@settings(max_examples=30)
def test_host_server_decisions_and_prompt_digests_are_identical(bodies):
    mandatory, _ = _mandatory_six()
    blocks = tuple(_dblock(10 + i, BlockType.MEMORY, text, mandatory=False) for i, text in enumerate(bodies))
    draft = _make_draft((*mandatory, *blocks), retrieval_limit=60)
    facts = _hfacts(deps=frozenset({"pip:pytest"}))
    host = finalize(draft, (), facts, _EST)
    server = decide(meta(draft), (), host_facts_to_meta(facts))
    assert host.selection == server
    repeated = finalize(draft, (), facts, _EST)
    assert (host.prompt_digest, host.selection.task_digest) == (
        repeated.prompt_digest,
        repeated.selection.task_digest,
    )
    assert prompt_digest(host.rendered_prompt) == host.prompt_digest
    assert task_digest(host.manifest.blocks) == host.selection.task_digest


def test_conditional_skills_use_host_deps_and_remaining_budget():
    mandatory, _ = _mandatory_six()
    conditional = (
        _cskill(10, "small", "pip:pytest"),
        _cskill(11, "large " * 100, "pip:pytest"),
        _cskill(12, "missing", "pip:other"),
    )
    draft = _make_draft(mandatory, conditional=conditional, skills_budget=30)
    selected = decide(meta(draft), (), {"deps": ["pip:pytest"]})
    assert "c:10" in {ref for ref, _ in selected.included}
    assert {ref: str(reason) for ref, reason, _ in selected.excluded} == {
        "c:11": "over_skill_budget",
        "c:12": "trigger_not_met",
    }


def test_conditional_skills_respect_remaining_max_count_and_host_server_parity():
    mandatory, _ = _mandatory_six()
    explicit_skill = _dblock(
        6, BlockType.SKILLS, "explicit", mandatory=True, reason=IncludeReason.EXPLICIT_PROFILE
    )
    auto_skills = tuple(
        _dblock(7 + i, BlockType.SKILLS, f"auto {i}", mandatory=False, reason=IncludeReason.TRIGGER_PATH)
        for i in range(7)
    )
    conditional = (
        _cskill(20, "unmatched", "pip:other"),
        _cskill(21, "over budget " * 80, "pip:pytest"),
        _cskill(22, "eighth auto skill", "pip:pytest"),
        _cskill(23, "ninth auto skill", "pip:pytest"),
    )
    draft = _make_draft((*mandatory, explicit_skill, *auto_skills), conditional=conditional, skills_budget=95)
    facts = _hfacts(deps=frozenset({"pip:pytest"}))
    host = finalize(draft, (), facts, _EST)
    draft_meta = meta(draft)
    assert isinstance(draft_meta["budget"], dict)
    stored_draft = replace(
        host.manifest,
        skills_trace={**draft.skills_trace, "skills_remaining": draft_meta["budget"]["skills_remaining"]},
    )
    assert host.selection == decide(draft_meta, (), host_facts_to_meta(facts))
    assert host.selection == decide(draft_meta_from_manifest(stored_draft), (), host_facts_to_meta(facts))
    assert "c:22" in {ref for ref, _ in host.selection.included}
    assert {ref: str(reason) for ref, reason, _ in host.selection.excluded} == {
        "c:20": "trigger_not_met",
        "c:21": "over_skill_budget",
        "c:23": "over_skill_count",
    }
    custom_meta = meta(
        _make_draft(mandatory, conditional=(_cskill(30, "a", "pip:x"), _cskill(31, "b", "pip:x")))
    )
    assert isinstance(custom_meta["budget"], dict)
    custom_meta["budget"] = {**custom_meta["budget"], "count_remaining": 1}
    capped = decide(custom_meta, (), {"deps": ["pip:x"]})
    assert "c:30" in {ref for ref, _ in capped.included}
    assert ("c:31", "over_skill_count", None) in capped.excluded


@pytest.mark.parametrize(
    ("kind", "budget_class", "reason"),
    [
        (BlockType.RUNTIME_NOTES, BudgetClass.CORE, "over_budget_core"),
        (BlockType.MATERIALS, BudgetClass.SUPPORTING, "over_budget_supporting"),
        (BlockType.MEMORY, BudgetClass.RETRIEVAL, "over_budget_retrieval"),
    ],
)
def test_class_budget_reverse_ladder_and_mandatory_warning(kind, budget_class, reason):
    mandatory, _ = _mandatory_six()
    optional = _dblock(10, kind, "optional " * 50, mandatory=False)
    draft = _make_draft(
        (*mandatory, optional),
        core_limit=1 if budget_class is BudgetClass.CORE else None,
        supporting_limit=1 if budget_class is BudgetClass.SUPPORTING else None,
        retrieval_limit=1 if budget_class is BudgetClass.RETRIEVAL else None,
    )
    selected, diagnostics = decide_with_diagnostics(meta(draft), (), {})
    assert ("d:10", reason, None) in selected.excluded
    assert {f"d:{i}" for i in range(6)} <= {ref for ref, _ in selected.included}
    if budget_class is BudgetClass.CORE:
        assert any(d["code"] == "CLASS_OVER_LIMIT" for d in diagnostics)


def test_total_budget_drops_last_ladder_whole_atomic_group():
    mandatory, _ = _mandatory_six()
    a = _dblock(6, BlockType.MEMORY, "memory a " * 30, mandatory=False, atomic_group="group")
    b = _dblock(7, BlockType.MEMORY, "memory b " * 30, mandatory=False, atomic_group="group")
    supporting = _dblock(8, BlockType.MATERIALS, "keep", mandatory=False)
    limit = sum(b.tokens_estimate for b in (*mandatory, supporting)) + a.tokens_estimate
    selected = decide(meta(_make_draft((*mandatory, a, b, supporting), total_limit=limit)), (), {})
    assert {ref for ref, _, _ in selected.excluded} == {"d:6", "d:7"}
    assert all(reason == "over_total_budget" for _, reason, _ in selected.excluded)


@pytest.mark.parametrize(
    "text",
    [
        "X only when Y. Y requires owner approval.",
        "1. Inspect scope.\n2. Obtain approval.\n3. Apply X only when approved.",
    ],
)
def test_conditions_and_ordered_procedures_are_whole_or_abort(text):
    mandatory, _ = _mandatory_six()
    condition = _dblock(6, BlockType.REQUIREMENTS, text, mandatory=True)
    draft = _make_draft((*mandatory, condition))
    final = finalize(draft, (), _hfacts(), _EST)
    assert text in final.rendered_prompt
    with pytest.raises(PreconditionFailed) as exc:
        finalize(_make_draft((*mandatory, condition), total_limit=1), (), _hfacts(), _EST)
    assert exc.value.code is ErrorCode.CONTEXT_OVER_BUDGET
    selected, candidates, policy = pipeline(
        [
            {
                "block_type": "requirements",
                "source_ref": "spec:condition",
                "content": text,
                "tokens_estimate": 100,
            }
        ]
    )
    assert next(c for c in snapshot(selected, {}) if c["source_ref"] == "spec:condition")["content"] == text
    with pytest.raises(PreconditionFailed) as over_block_exc:
        validate(candidates, replace(policy, block_max_tokens=1))
    assert over_block_exc.value.code is ErrorCode.CONTEXT_OVER_BUDGET
    fallback_rt = replace(make_request().runtime, context_window_tokens=10)
    fallback_policy = effective_policy(role_policy_spec("executor"), {}, fallback_rt)
    with pytest.raises(PreconditionFailed) as fallback_exc:
        finalize(
            _make_draft((*mandatory, condition), total_limit=fallback_policy.total_limit), (), _hfacts(), _EST
        )
    assert fallback_exc.value.code is ErrorCode.CONTEXT_OVER_BUDGET


def test_explicit_required_skill_over_total_budget_fails():
    request = make_request()
    spec = replace(role_policy_spec("executor"), skills_include=("aa",))
    policy = effective_policy(spec, {}, request.runtime)
    source = make_candidate(
        "skills", "resource:skill:aa@1.0.0", key="aa", version="1.0.0", roles=["executor"]
    )
    source["content"] = "required skill " * 100
    selected = select(
        validate(discover([*core_sources(), source], request, policy), policy), request, policy, {}
    )
    skill = next(c for c in objects(selected["included"]) if c["block_type"] == "skills")
    assert skill["mandatory"] is True
    mandatory, _ = _mandatory_six()
    block = _dblock(6, BlockType.SKILLS, str(skill["content"]), mandatory=True)
    with pytest.raises(PreconditionFailed) as exc:
        finalize(_make_draft((*mandatory, block), total_limit=1), (), _hfacts(), _EST)
    assert exc.value.code is ErrorCode.CONTEXT_OVER_BUDGET


def test_delta_matches_task_digest_and_authority_change_forces_full():
    mandatory, _ = _mandatory_six(start_ord=1)
    base = finalize(_make_draft(mandatory), (), _hfacts(), _EST)
    note = _dblock(0, BlockType.RESUME_NOTE, "resume", mandatory=True)
    answer = _dblock(7, BlockType.DECISION_ANSWERS, "new answer", mandatory=True)
    resumed = _make_draft(
        (note, *mandatory, answer), resume=ResumeInfo("session", base.selection.task_digest)
    )
    final = finalize(resumed, (), _hfacts(), _EST)
    assert final.selection.mode == "delta"
    assert {ref for ref, _ in final.selection.included} == {"d:0", "d:7"}
    assert task_digest(final.manifest.blocks) == base.selection.task_digest
    changed = _dblock(1, BlockType.SYSTEM_CONSTRAINTS, "new owner constraints", mandatory=True)
    final = finalize(
        _make_draft((note, changed, *mandatory[1:], answer), resume=resumed.resume), (), _hfacts(), _EST
    )
    assert final.selection.mode == "full"


@pytest.mark.parametrize("text", ["", "English" * 30, "Кириллица" * 30, "aБ" * 30])
def test_estimator_uses_29_and_34_ratios(text):
    assert estimate_text(text) == HeuristicTokenEstimator().estimate(text)
