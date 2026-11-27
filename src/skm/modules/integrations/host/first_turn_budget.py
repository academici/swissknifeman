"""Budget the five native resident sources; partial observations remain incomplete (§5.7)."""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.ids import ProjectId, parse_uuid
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.budget import first_turn_sources, first_turn_verdict, source_total
from skm.modules.integrations.domain.checks.context import effective_settings, mapping
from skm.modules.integrations.domain.contracts import ClientLayer
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId
from skm.modules.integrations.domain.reports import FirstTurnReport
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.host import (
    FirstTurnBudgetResult,
    first_turn_budget_request_from_json,
    first_turn_budget_result_from_json,
)
from skm.modules.integrations.ports import CheckoutFs

from .doctor import budget_settings, native_inputs, read_layers, read_text

__all__ = ["SPEC", "FirstTurnBudgetOperation", "first_turn_budget", "run"]


def _session_commands(value: JsonValue) -> tuple[str, ...]:
    """Read native command registrations; other output-producing hook types are unknown."""
    if isinstance(value, list):
        return tuple(command for entry in value for command in _session_commands(entry))
    if isinstance(value, dict):
        if "hooks" in value:
            return _session_commands(value["hooks"])
        command = value.get("command")
        if isinstance(command, str) and value.get("type", "command") == "command":
            return (command,)
    raise ValueError("SessionStart hook output is not measurable")


def _context_command(command: str, inputs: ProjectionInputs) -> bool:
    """Recognize the native SKM context command without executing shell text."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) != 8 or argv[1].casefold().replace("_", "") != "sessionstart":
        return False
    return argv == [
        "skm-hook",
        argv[1],
        "--target",
        inputs.target.value,
        "--surface",
        HookSurfaceId.SESSION_CONTEXT.value,
        "--project",
        str(inputs.project_id),
    ]


def _hook_template(
    fs: CheckoutFs,
    layers: tuple[ClientLayer, ...],
    files: tuple[DesiredFile, ...],
    inputs: ProjectionInputs,
) -> str | None:
    """A template estimate is complete only when every observed SessionStart output is known."""
    if any(layer.get("valid") is not True for layer in layers):
        return None
    documents = {str(layer.get("path")): mapping(layer.get("data")) for layer in layers}
    for file in files:
        if file.surface is not Surface.HOOKS:
            continue
        text = read_text(fs, file.relative_path)
        if text is None:
            return None
        try:
            decoded: object = json.loads(text)
            if not isinstance(decoded, dict):
                raise ValueError("Native hooks must be an object")
        except ValueError:
            return None
        documents[file.relative_path] = cast("JsonObject", decoded)
    commands: list[str] = []
    for data in documents.values():
        hooks = data.get("hooks")
        if hooks is not None and not isinstance(hooks, dict):
            return None
        for event, entries in mapping(hooks).items():
            if event.casefold().replace("_", "") == "sessionstart":
                try:
                    commands.extend(_session_commands(entries))
                except ValueError:
                    return None
    if not commands:
        return ""
    if any(not _context_command(command, inputs) for command in commands):
        return None
    templates = [
        block["session_start_template"]
        for block in (inputs.instructions_core, inputs.instructions_project)
        if isinstance(block.get("session_start_template"), str)
    ]
    return "".join(cast("list[str]", templates)) * len(commands) if templates else None


def _mcp(  # noqa: PLR0911 - preserve every distinct unavailable native observation
    fs: CheckoutFs,
    paths: tuple[str, ...],
    desired: Mapping[str, JsonObject],
    layers: tuple[ClientLayer, ...],
) -> Mapping[str, JsonObject] | None:
    native: dict[str, JsonObject] = {}
    for layer in layers:
        if layer.get("exists") is True and layer.get("valid") is not True:
            return None
        data = mapping(layer.get("data"))
        configs = data.get("mcp_servers") or data.get("mcpServers")
        if configs is not None and not isinstance(configs, dict):
            return None
        for name, spec in mapping(configs).items():
            if not isinstance(spec, dict):
                return None
            native[name] = mapping(spec)
    for path in paths:
        text = read_text(fs, path)
        if text is None:
            return None
        if not path.endswith(".json"):
            continue  # TOML was decoded by the native layer reader.
        try:
            decoded: object = json.loads(text)
        except ValueError:
            return None
        if not isinstance(decoded, dict):
            return None
        configs = cast("JsonObject", decoded).get("mcpServers")
        if configs is not None and not isinstance(configs, dict):
            return None
        for name, spec in mapping(configs).items():
            if not isinstance(spec, dict):
                return None
            native[name] = mapping(spec)
    if set(desired) - native.keys():
        return None
    return {name: {**desired.get(name, {}), **spec} for name, spec in native.items()}


def first_turn_budget(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    target: TargetId,
    mount: str | None = None,
    include_plugins: bool = False,
) -> FirstTurnReport:
    settings = budget_settings(ctx)
    target_max, warn = settings.budget.first_turn.target, settings.budget.first_turn.warn
    first_turn_verdict(0, target=target_max, warn=warn)
    fs, adapter, inputs, files = native_inputs(ctx, project_id, mount, target)
    layers = read_layers(ctx, adapter, fs)
    skills = {
        file.relative_path: read_text(fs, file.relative_path)
        for file in files
        if file.surface is Surface.SKILLS and file.relative_path.rsplit("/", 1)[-1] == "SKILL.md"
    }
    codex_skill_metadata = (
        {path: read_text(fs, path.removesuffix("SKILL.md") + "agents/openai.yaml") for path in skills}
        if target is TargetId.CODEX
        else None
    )
    agents = {
        file.relative_path: read_text(fs, file.relative_path)
        for file in files
        if file.surface is Surface.AGENTS
    }
    instruction_paths = dict.fromkeys(
        (
            *adapter.instruction_paths(),
            *(file.relative_path for file in files if file.surface is Surface.INSTRUCTIONS),
        )
    )
    instructions = {path: read_text(fs, path) for path in instruction_paths}
    if include_plugins:
        # Plugin home paths are outside the UserHomeReader allowlist.
        skills["plugins:unobserved"] = None
        agents["plugins:unobserved"] = None
    native = effective_settings(layers)
    env = mapping(native.get("env"))
    tool_search = str(env.get("ENABLE_TOOL_SEARCH", "")).casefold()
    deferred = tool_search in ("1", "true", "auto") or tool_search.startswith("auto:")
    template = _hook_template(fs, layers, files, inputs)
    mcp_paths = tuple(file.relative_path for file in files if file.surface is Surface.MCP)
    if target is TargetId.CLAUDE_CODE and ".mcp.json" not in mcp_paths:
        try:
            if fs.stat(".mcp.json").exists:
                mcp_paths += (".mcp.json",)
        except (OSError, ValueError):
            mcp_paths += (".mcp.json",)
    servers = _mcp(fs, mcp_paths, inputs.mcp_servers, layers)
    sources = first_turn_sources(
        target=target,
        skills=skills,
        agents=agents,
        instructions=instructions,
        session_start_template=template,
        mcp_servers=servers,
        deferred_tool_search=deferred,
        listing_fraction=settings.budget.skill_listing.fraction,
        context_window=settings.budget.skill_listing.context_window,
        codex_skill_metadata=codex_skill_metadata,
    )
    total = source_total(sources)
    return FirstTurnReport(
        project_id,
        target,
        {"target": target_max, "warn": warn},
        sources,
        total,
        first_turn_verdict(total, target=target_max, warn=warn),
    )


def run(ctx: HostContext, request: object) -> FirstTurnBudgetResult:
    req = cast("Mapping[str, Any]", first_turn_budget_request_from_json(request))
    report = first_turn_budget(
        ctx,
        project_id=ProjectId(parse_uuid(str(req["project_id"]))),
        target=TargetId(req["target"]),
        mount=req.get("mount"),
        include_plugins=req["include_plugins"],
    )
    return first_turn_budget_result_from_json(
        {
            "schema": "urn:skm:integrations:host-result:first-turn-budget:v1",
            "project_id": str(report.project_id),
            "target": report.target.value,
            "include_plugins": req["include_plugins"],
            "thresholds": dict(report.thresholds),
            "sources": [
                {
                    "kind": source.kind.value,
                    "tokens": source.tokens,
                    "method": source.method,
                    "detail": dict(source.detail),
                }
                for source in report.sources
            ],
            "total": report.total,
            "verdict": report.verdict.value,
        }
    )


class FirstTurnBudgetOperation:
    name = "integrations.host.first_turn_budget"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name=FirstTurnBudgetOperation.name,
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", dict),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
