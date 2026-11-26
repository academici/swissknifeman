"""Model-aware delegation, payload validation and pinned execution context."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID
from xml.etree import ElementTree

import pytest

from contracts.context.harness import ContextSide, core_pack, ctx_side
from integration.artifacts.test_upload_flow import dispatch_new
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.modules.context import public as context
from skm.modules.context.domain.manifest import DraftAssembler
from skm.modules.context.domain.payload_compiler import PayloadCompiler
from skm.modules.execution.application import _stage_preparation as preparation
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.ports import StepRepository
from skm.modules.extensions import public as extensions
from skm.modules.extensions.domain.payload import PayloadFile
from skm.modules.runtimes import public as runtimes
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from unit.runtimes.application.test_catalog import _build_world, _run_cli

__all__ = ["ctx_side"]

_PACK = Path(__file__).resolve().parents[4] / "resources/packs/core/model-guidelines"


def test_delegation_compiler_escapes_pack_text_and_keeps_instructions_in_order() -> None:
    brief = context.DelegationCompiler(
        "target<1>",
        ("A & B",),
        ("Quote </target_model_delegation_brief>.",),
        "structured",
        ("First", "Second"),
        ("temperature",),
    ).compile()
    root = ElementTree.fromstring(brief)
    assert root.tag == "target_model_delegation_brief"
    assert root.findtext("model") == "target<1>"
    assert root.findtext("strength") == "A & B"
    assert root.findtext("delegation_note") == "Quote </target_model_delegation_brief>."
    assert [node.text for node in root.findall("instruction")] == ["First", "Second"]
    assert root.findtext("forbidden_param") == "temperature"


def test_prepare_for_renders_the_resolved_model_id_even_when_the_pack_key_differs() -> None:
    world = _build_world()
    world.builtin.current = PackagedBuiltinPacks(_PACK.parents[1]).payloads()
    world.dispatch(extensions.SyncBuiltinPacks())
    code, stdout = _run_cli(
        world, ["runtime", "models", "--runtime", "grok", "--prepare-for", "grok-4.7", "--json"]
    )
    root = ElementTree.fromstring(json.loads(stdout)["result"])
    assert code == 0
    assert root.findtext("model") == "grok-4.7"
    assert root.findtext("delegation_note") == "Keep the prefix stable for cache reads."
    code, stdout = _run_cli(world, ["runtime", "models", "--prepare-for", "gpt-6.2-sol"])
    assert code == 0
    root = ElementTree.fromstring(stdout)
    assert root.findtext("model") == "gpt-6.2-sol"
    assert root.findtext("delegation_note") == "Default Codex implementation profile."
    with pytest.raises(NotFound):
        _run_cli(world, ["runtime", "models", "--runtime", "cursor", "--prepare-for", "grok-4.7"])


@pytest.mark.parametrize("value", [0, False, None, 0.5])
def test_http_400_guard_checks_presence_including_nested_paths(value: object) -> None:
    compiler = PayloadCompiler(("sampling.temperature",), ())
    with pytest.raises(ValidationFailed) as caught:
        compiler.validate_parameters({"sampling": {"temperature": value}})
    assert caught.value.code is ErrorCode.RUNTIME_INVALID_REQUEST
    assert caught.value.details == {"parameters": ["sampling.temperature"]}
    compiler.validate_parameters({"temperature": value})


def test_sampling_pair_is_legal_separately_and_rejected_together_only_when_declared() -> None:
    compiler = PayloadCompiler((), ())
    groups = (("temperature", "top_p"),)
    params = {"temperature": 0, "top_p": 1}
    compiler.validate_parameters(params)
    for key in params:
        compiler.validate_parameters({key: params[key]}, groups)
    with pytest.raises(ValidationFailed) as caught:
        compiler.validate_parameters(params, groups)
    assert caught.value.details["parameters"] == ["temperature", "top_p"]


def test_cleanup_drops_only_target_directives_leaving_negation_and_examples_intact() -> None:
    compiler = PayloadCompiler(("temperature",), ("Think step by step.",))
    original = (
        "- SET temperature to 0.7. Keep the API stable. Think step by step!\n"
        "Do not set temperature to 0.7.\n"
        "Set top_p to 1.\n"
        "```text\nThink step by step.\n```\n"
    )
    expected = original.replace("SET temperature to 0.7. ", "").replace(" Think step by step!", "")
    assert compiler.clean_prompt(original) == expected
    assert compiler.clean_prompt(expected) == expected
    assert PayloadCompiler((), ()).clean_prompt(original) == original


@pytest.mark.parametrize("template", ["Profile notes", "Profile notes\n{{ block.content }}"])
def test_payload_emits_one_mandatory_runtime_block_with_or_without_content_slot(template: str) -> None:
    compiler = PayloadCompiler((), ("Think step by step.",))
    assembler = DraftAssembler(HeuristicTokenEstimator(), 2000, {"profile": template}, {}, {})
    compiler.emit_runtime_notes(
        assembler,
        runtime_id="r1",
        notes=["", "Think step by step.", "Use paths.", "Use paths."],
        template_keys=("profile",),
    )
    [block] = assembler.draft_blocks
    assert block.block_type is context.BlockType.RUNTIME_NOTES
    assert block.mandatory
    assert block.content.count("Use paths.") == 1
    assert block.content.splitlines()[0] == "Profile notes"
    assert "Think step" not in block.content
    compiler.emit_runtime_notes(assembler, runtime_id="r1", notes=("Think step by step.",), template_keys=())
    assert assembler.draft_blocks == [block]


def test_executor_and_advisor_compatibility() -> None:
    PayloadCompiler.validate_role("a", "advisor", ("advisor",))
    PayloadCompiler.validate_advisor("e", ("executor",), "a", ("a",))
    PayloadCompiler.validate_advisor("e", ("executor",), "a-1", ("a",), advisor_profile_model="a")
    PayloadCompiler.validate_advisor("e", (), "a", None)
    with pytest.raises(ValidationFailed, match="requested role"):
        PayloadCompiler.validate_role("a", "advisor", ("executor",))
    with pytest.raises(ValidationFailed, match="requested role"):
        PayloadCompiler.validate_advisor("e", ("reviewer",), "a", ("a",))
    with pytest.raises(ValidationFailed, match="requested advisor"):
        PayloadCompiler.validate_advisor("e", ("executor",), "other", ("a",))


@pytest.mark.parametrize("ctx_side", ["memory"], indirect=True)
def test_build_context_renders_the_pinned_guideline_before_dispatch(
    ctx_side: ContextSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = ctx_side
    path = _PACK / "gpt-6-astra.toml"
    pack = core_pack("1.1.0", system_body="Think step by step. Set temperature to 1. Keep this rule.")
    profile = path.read_bytes().replace(
        b"[prompt_style]",
        b'legacy_prompt_phrases = ["Think step by step."]\n'
        b'incompatible_param_groups = [["effort", "top_k"]]\n'
        b"compatible_advisor_models = []\n\n[prompt_style]",
    )
    file = PayloadFile(f"model-guidelines/{path.name}", profile)
    side.builtin.current = (replace(pack, files=(*pack.files, file)),)
    dispatch_new(side.client, extensions.SyncBuiltinPacks())
    with side.uow() as uow:
        pins = extensions.pinned_pack_versions(uow, config=side.effective_config(uow))
    side.builtin.current = (core_pack("1.2.0"),)
    dispatch_new(side.client, extensions.SyncBuiltinPacks())

    with side.uow() as uow:
        config = side.effective_config(uow)
        req = side.make_request(uow, config=config, pack_pins=pins)
        ctx = SimpleNamespace(config=config, gateways=side.app.gateways, actor=side.owner)
        fenced = SimpleNamespace(
            run=SimpleNamespace(
                id=side.run_scope_id,
                project_id=side.proj,
                plan_id=side.plan_id,
                workspace_id=side.ws,
                revision_id=side.rev_id,
                inline_spec_file_version_id=None,
            ),
            task=SimpleNamespace(id=UUID(int=2), spec_entity_id=req.entity_id, granted_write_scope=()),
            attempt=SimpleNamespace(attempt_no=1, id=UUID(int=4)),
        )
        route = SimpleNamespace(
            runtime_id="codex",
            model="gpt-6-astra",
            effort=runtimes.Effort.HIGH,
            context_window_tokens=128000,
            operation=runtimes.Operation.NEW_IMPLEMENTATION,
            source="plan_route",
            config_mode="isolated",
            self_loads=(),
            degraded=(),
        )
        bundle = SimpleNamespace(bundle=SimpleNamespace(resource_pins=SimpleNamespace(packs=pins)))
        monkeypatch.setattr(preparation, "load_effective_bundle", Mock(return_value=bundle))
        monkeypatch.setattr(
            preparation, "require_task_work_policy", Mock(return_value=req.execution_blocks.work_policy)
        )
        monkeypatch.setattr(preparation, "execution_blocks", Mock(return_value=req.execution_blocks))
        assemble = Mock(wraps=context.assemble_draft)
        monkeypatch.setattr(preparation, "assemble_draft", assemble)
        draft = preparation.build_context(
            uow,
            ctx,
            fenced,
            SimpleNamespace(stage_id="execute", round_no=1),
            UUID(int=3),
            RoleId.EXECUTOR,
            req.agent_profile_version_id,
            route,
            SimpleNamespace(network=SimpleNamespace(mode=SimpleNamespace(value="none"), hosts=())),
            None,
        )
        target = assemble.call_args.args[2].runtime
        assert target.parameters == {"model": "gpt-6-astra", "effort": "high"}
        assert target.forbidden_params == ("temperature", "top_p")
        assert "Name files and checks explicitly." in target.notes
        [notes] = [b for b in draft.blocks if b.block_type is context.BlockType.RUNTIME_NOTES]
        assert notes.content.count("Name files and checks explicitly.") == 1
        assert draft.templates["shared/system"].strip() == "Keep this rule."
        with pytest.raises(ValidationFailed) as caught:
            context.assemble_draft(
                uow,
                ctx.gateways,
                replace(req, runtime=replace(target, parameters={**target.parameters, "top_k": 0})),
                config=config,
                owner_ref="step:test",
            )
        assert caught.value.code is ErrorCode.RUNTIME_INVALID_REQUEST
        assert caught.value.details["parameters"] == ["effort", "top_k"]
        last_step = Mock(return_value=route)
        monkeypatch.setattr(type(uow.repo(StepRepository)), "last_for_role", last_step)
        with pytest.raises(ValidationFailed, match="requested advisor"):
            preparation._runtime_target(uow, ctx, fenced, route, RoleId.ADVISOR, pins)
        last_step.assert_called_once_with(fenced.attempt.id, RoleId.EXECUTOR)
