"""Golden prompt payloads for the core model guideline profiles (I-06.3)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from contracts.context.harness import ContextSide, ctx_side
from skm.modules.context import public as context
from skm.modules.context.domain.manifest import DraftAssembler
from skm.modules.context.domain.reasons import ExcludeReason
from skm.modules.context.domain.render import render, render_block_text
from skm.modules.runtimes import public as runtimes
from skm.platform.tokens.heuristic import HeuristicTokenEstimator

__all__ = ["ctx_side"]

_PACK = Path(__file__).resolve().parents[4] / "resources/packs/core/model-guidelines"
_NOW = datetime(2026, 11, 15, tzinfo=UTC)
_ESTIMATOR = HeuristicTokenEstimator()
_FACTS = context.HostFacts(frozenset(), (), False, {})
_PROFILES = {
    "claude-opus-5-5": "cache_control",
    "claude-sonnet-5-5": "cache_control",
    "gemini-3-8-flash": None,
    "gemini-4-argon": None,
    "gemini-4-carbon": None,
    "gemini-4-hydrogen": None,
    "gemini-4-neon": None,
    "gpt-6-astra": "prompt_cache_key",
    "gpt-6-luna": "prompt_cache_key",
    "gpt-6-sol": "prompt_cache_key",
    "gpt-oss-120b": None,
    "grok-4-7": None,
}


@pytest.fixture
def request_base(ctx_side: ContextSide) -> context.ContextRequest:
    with ctx_side.uow() as uow:
        return ctx_side.make_request(uow, config=ctx_side.effective_config(uow))


def _draft(request: context.ContextRequest, at: datetime) -> context.ContextDraft:
    block_type = context.BlockType
    assembler = DraftAssembler(_ESTIMATOR, 10000, {}, {}, {})
    if request.resume is not None:
        assembler.add(block_type.RESUME_NOTE, "", f"Resumed at {at.isoformat()}", "core", "resume")
    for kind, content in (
        (block_type.DECISION_ANSWERS, f"Answer recorded at {at.isoformat()}"),
        (block_type.ACCEPTANCE, "Pass the checks."),
        (block_type.TASK_CONTRACT, "Implement the contract."),
        (block_type.RUN_RULES, "Stay within scope."),
        (block_type.ROLE_CONTRACT, "Follow the role contract."),
        (block_type.SYSTEM_CONSTRAINTS, "Follow system constraints."),
        (block_type.RESULT_CONTRACT, "Return JSON."),
    ):
        assembler.add(kind, "", content, "spec", kind.value)
    context.PayloadCompiler((), ()).emit_runtime_notes(
        assembler, runtime_id=request.runtime.runtime_id, notes=request.runtime.notes, template_keys=()
    )
    assembler.exclude(block_type.HISTORY, "spec", "excluded-history", ExcludeReason.OVER_TOTAL_BUDGET)
    draft, _, _ = assembler.build(
        request,
        total_limit=12000,
        class_limits={},
        skills_budget=0,
        repo_max_files=0,
        owner_ref="step:1",
        created_at=at,
    )
    return draft


def _draft_texts(draft: context.ContextDraft) -> dict[str, str]:
    return {
        f"d:{block.ordinal}": render_block_text(
            block_type=block.block_type,
            title=block.title,
            content=block.content,
            source_ref=block.source_ref,
            templates=draft.templates,
            prompt_plan=draft.prompt_plan,
            variables=draft.variables,
        )
        for block in draft.blocks
    }


def test_goldens_cover_the_core_guideline_pack() -> None:
    assert {profile.stem for profile in _PACK.glob("*.toml")} == _PROFILES.keys()


@pytest.mark.parametrize("ctx_side", ["memory"], indirect=True)
@pytest.mark.parametrize(("key", "cache_field"), _PROFILES.items(), ids=_PROFILES.keys())
def test_core_model_payload_golden(
    request_base: context.ContextRequest, key: str, cache_field: str | None
) -> None:
    profile = tomllib.loads((_PACK / f"{key}.toml").read_text())
    runtime_id = profile["runtime_ids"][0]
    cache = profile["cache_capabilities"]
    capabilities = {"compaction"} if profile["compaction_threshold"]["input_tokens"] else set()
    # Exercise targets admitted by a transport that supports these wire parameters.
    wire_parameter = {"claude_code": "cache_control", "codex": "prompt_cache_key"}.get(runtime_id)
    if cache["prompt_cache"] == "native" and wire_parameter is not None:
        capabilities.add(wire_parameter)
    notes = (profile["notes"], *profile["prompt_style"]["instructions"])
    target = replace(
        request_base.runtime,
        model=profile["model_id"],
        runtime_id=runtime_id,
        capabilities=frozenset(capabilities),
        notes=notes,
    )
    request = replace(request_base, runtime=target)
    compiler = context.PrefixStablePromptCompiler(target)
    expected_prefix = (
        "Follow system constraints.\n\n"
        "Follow the role contract.\n\n"
        "Stay within scope.\n\n"
        "## Runtime Notes\n\n" + "\n".join(f"- {note}" for note in notes) + "\n\n"
        "Implement the contract.\n\n"
        "Pass the checks.\n"
    )
    prefix_hex = sha256(expected_prefix.encode()).hexdigest()
    parameters: dict[str, object] = {}
    if cache_field == "cache_control":
        parameters[cache_field] = {"type": "ephemeral"}
    if cache_field == "prompt_cache_key":
        parameters[cache_field] = prefix_hex

    for at in (_NOW, _NOW + timedelta(days=1)):
        draft = _draft(request, at)
        assert draft.manifest is not None
        assert draft.manifest.state is context.ManifestState.DRAFT
        final = context.finalize(draft, (), _FACTS, _ESTIMATOR)
        assert final.manifest.state is context.ManifestState.FINAL
        assert final.manifest.finalized_at == at
        _, pieces = render(draft, (), final.selection)
        final_texts = dict(zip((ref for ref, _ in final.selection.included), pieces, strict=True))
        golden = {
            "prefix": expected_prefix,
            "tail": f"Answer recorded at {at.isoformat()}\n\nReturn JSON.\n",
            "prefix_digest": f"sha256:{prefix_hex}",
            "cache_parameters": parameters,
            "should_compact": False,
        }
        assert asdict(compiler.compile(draft.manifest, _draft_texts(draft))) == golden
        compiled = compiler.compile(final.manifest, final_texts)
        assert asdict(compiled) == golden
        assert compiled.prompt == final.rendered_prompt

    usage = replace(
        runtimes.unknown_usage(),
        status=runtimes.UsageStatus.REPORTED,
        cache_read_tokens=240 if cache["cache_read"] else None,
        cache_write_tokens=80 if cache["cache_write"] else None,
    )
    expected_rate = 0.75 if cache["cache_read"] and cache["cache_write"] else None
    assert runtimes.cache_hit_rate(usage) == expected_rate


@pytest.mark.parametrize("ctx_side", ["memory"], indirect=True)
def test_compaction_at_65_percent_requires_capability(request_base: context.ContextRequest) -> None:
    target = replace(
        request_base.runtime, context_window_tokens=10000, capabilities=frozenset({"compaction"})
    )
    draft = _draft(request_base, _NOW)
    assert draft.manifest is not None
    final = context.finalize(draft, (), _FACTS, _ESTIMATOR)
    texts = _draft_texts(draft)
    compiler = context.PrefixStablePromptCompiler(target)
    for manifest in (draft.manifest, final.manifest):
        assert not compiler.compile(manifest, texts, context_tokens=6499).should_compact
        assert compiler.compile(manifest, texts, context_tokens=6500).should_compact
        assert compiler.compile(manifest, texts, context_tokens=6501).should_compact
    assert compiler.compile(replace(final.manifest, total_tokens_estimate=6500), texts).should_compact
    degraded = context.PrefixStablePromptCompiler(replace(target, degraded=target.capabilities))
    assert not degraded.compile(final.manifest, texts, context_tokens=6500).should_compact


@pytest.mark.parametrize("ctx_side", ["memory"], indirect=True)
def test_cache_parameters_require_eligible_prefix(request_base: context.ContextRequest) -> None:
    draft = _draft(request_base, _NOW)
    assert draft.manifest is not None
    texts = _draft_texts(draft)
    baseline = context.PrefixStablePromptCompiler(request_base.runtime).compile(draft.manifest, texts)
    assert baseline.cache_parameters == {}

    target = replace(
        request_base.runtime,
        capabilities=frozenset({"cache_control", "prompt_cache_key"}),
        degraded=frozenset({"cache_control"}),
    )
    compiler = context.PrefixStablePromptCompiler(target)
    assert compiler.compile(draft.manifest, texts).cache_parameters == {
        "prompt_cache_key": baseline.prefix_digest.removeprefix("sha256:")
    }
    compiler = replace(compiler, min_cacheable_tokens=draft.manifest.total_limit)
    assert compiler.compile(draft.manifest, texts).cache_parameters == {}


@pytest.mark.parametrize("ctx_side", ["memory"], indirect=True)
def test_resumed_delta_has_no_cache_boundary(request_base: context.ContextRequest) -> None:
    target = replace(request_base.runtime, capabilities=frozenset({"cache_control", "prompt_cache_key"}))
    first = context.finalize(_draft(request_base, _NOW), (), _FACTS, _ESTIMATOR)
    resume = context.ResumeInfo("session-1", first.selection.task_digest)
    resumed = _draft(replace(request_base, resume=resume), _NOW + timedelta(days=1))
    final = context.finalize(resumed, (), _FACTS, _ESTIMATOR)
    assert final.manifest.mode == "delta"
    compiled = context.PrefixStablePromptCompiler(target).compile(final.manifest, _draft_texts(resumed))
    assert compiled.prefix == ""
    assert compiled.cache_parameters == {}
    assert compiled.prompt == final.rendered_prompt
