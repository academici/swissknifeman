"""Read-only host observations for doctor and the resident budget (integrations §5.6-5.7)."""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, ValidationFailed
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.checks import DoctorContext
from skm.modules.integrations.domain.checks.claude import hook_commands
from skm.modules.integrations.domain.checks.context import (
    HygieneObservation,
    ScriptObservation,
    effective_settings,
    mapping,
    strings,
)
from skm.modules.integrations.domain.checks.hygiene import script_path
from skm.modules.integrations.domain.contracts import ClientLayer, UserHomeSelector
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.desired import DesiredFile, HostSubscriptionEvent, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind
from skm.modules.integrations.domain.hook_rules import ENFORCEMENT, HookMode
from skm.modules.integrations.domain.hook_subscriptions import parse_subscriptions
from skm.modules.integrations.domain.observed import FileKind
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.queries import GetDesiredProjection, ListHookSubscriptions
from skm.modules.integrations.generated.results import ListHookSubscriptionsResult
from skm.modules.integrations.generated.settings import IntegrationsSettings
from skm.modules.integrations.generated.views import DesiredProjectionView
from skm.modules.integrations.ports import (
    CheckoutFs,
    HostCommandRunner,
    IntegrationTarget,
    IntegrationTargetRegistry,
    UserHomeReader,
)
from skm.modules.integrations.public import GetHookPolicy
from skm.modules.workspace.public import marker_from_document

from .observe import (
    bind_checkout_fs,
    integrations_settings,
    resolve_checkout_for_mount,
    resolve_project_workspace_id,
)
from .plan_projection import checkout_inputs

__all__ = ["budget_settings", "doctor_context", "native_inputs", "read_layers", "read_text"]


def budget_settings(ctx: HostContext) -> IntegrationsSettings:
    """Propagate invalid settings instead of substituting defaults for an invalid section."""
    section = getattr(ctx.config, "section", None)
    return (
        cast("IntegrationsSettings", section(IntegrationsSettings))
        if callable(section)
        else (integrations_settings(ctx))
    )


def native_inputs(
    ctx: HostContext,
    project_id: ProjectId,
    mount: str | None,
    target: TargetId,
) -> tuple[CheckoutFs, IntegrationTarget, ProjectionInputs, tuple[DesiredFile, ...]]:
    checkout = resolve_checkout_for_mount(ctx, project_id, mount)
    fs = bind_checkout_fs(ctx, checkout.local_locator)
    adapter = ctx.gateways.get(IntegrationTargetRegistry).get(target)
    view = ctx.client.ask(
        GetDesiredProjection(
            project_id=project_id, checkout_binding_id=checkout.binding_id, target=cast("Any", target.value)
        )
    )
    assert isinstance(view, DesiredProjectionView)  # noqa: S101
    inputs = checkout_inputs(view, fs)
    return fs, adapter, inputs, adapter.render(inputs)


class _ObservedHome:
    def __init__(self, reader: UserHomeReader) -> None:
        self.reader = reader

    def read(self, logical: UserHomeSelector) -> bytes | None:
        try:
            return self.reader.read(logical)
        except (OSError, ValueError, SkmError):
            return b"\x00"


class _ObservedCheckout:
    def __init__(self, fs: CheckoutFs) -> None:
        self.fs = fs

    def read(self, path: str) -> bytes | None:
        try:
            return self.fs.read(path)
        except (OSError, ValueError, SkmError):
            return b"\x00"

    def __getattr__(self, name: str) -> Any:
        return getattr(self.fs, name)


def read_layers(ctx: HostContext, adapter: IntegrationTarget, fs: CheckoutFs) -> tuple[ClientLayer, ...]:
    home = _ObservedHome(ctx.gateways.get(UserHomeReader))
    return adapter.client_layers(cast("CheckoutFs", _ObservedCheckout(fs)), home)


def read_text(fs: CheckoutFs, path: str) -> str | None:
    try:
        raw = fs.read(path)
        return None if raw is None else raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError, SkmError):
        return None


def _checkout_marker(
    fs: CheckoutFs,
    project_id: ProjectId,
    workspace_id: WorkspaceId,
    repository_id: UUID,
    mount: str,
    instance_id: UUID | None,
) -> str:
    text = read_text(fs, ".skm/project.json")
    if text is None:
        return "missing"
    try:
        marker = marker_from_document(mapping(json.loads(text)))
    except (ValueError, SkmError):
        return "mismatch"
    if (
        marker.project_id != project_id
        or marker.workspace_id != workspace_id
        or marker.repository_id != repository_id
        or marker.mount_name.value != mount
        or (instance_id is not None and marker.instance_id != instance_id)
    ):
        return "mismatch"
    return "present"


def _config(ctx: HostContext, key: str, default: Any) -> Any:
    getter = getattr(ctx.config, "get", None)
    if not callable(getter):
        return default
    try:
        try:
            return getter(key, default)
        except TypeError:
            return getter(key)
    except ValidationFailed as error:
        # The host chain never resolves work keys such as ``hooks.subscriptions``; the control plane
        # listing already reports those, so a host read of one is simply absent.
        if (
            key == "hooks.subscriptions"
            and error.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
            and error.details.get("reason") == "other_chain"
        ):
            return default
        raise


def _expected(files: Sequence[DesiredFile]) -> JsonObject:
    layers: list[ClientLayer] = []
    for file in files:
        if file.relative_path not in (".claude/settings.json", ".claude/settings.local.json"):
            continue
        data = json.loads(file.managed_bytes)
        layers.append(
            {"layer": "local" if ".local." in file.relative_path else "project", "valid": True, "data": data}
        )
    return effective_settings(layers)


def _commands(ctx: HostContext, fs: CheckoutFs, layers: tuple[ClientLayer, ...]) -> frozenset[str]:
    if not ctx.gateways.has(HostCommandRunner):
        return frozenset()
    programs: set[str] = set()
    for layer in layers:
        for command in hook_commands(mapping(layer.get("data")).get("hooks")):
            try:
                argv = shlex.split(command)
            except ValueError:
                continue
            if argv:
                programs.add(argv[0])
    runner = ctx.gateways.get(HostCommandRunner)
    available: set[str] = set()
    for program in sorted(programs):
        # Only executable lookup runs, never the hook or its configured arguments.
        try:
            result = runner.run(("which", "--", program), cwd=fs.root, env={}, stdin=b"", timeout_ms=1000)
        except (OSError, SkmError):
            continue
        if result.exit_code == 0 and not result.timed_out:
            available.add(program)
    return frozenset(available)


def _supported(adapter: IntegrationTarget, inputs: ProjectionInputs) -> frozenset[HookEventKind]:
    """Ask the public renderer for native bindings without duplicating provider capability tables."""
    return frozenset(
        kind
        for kind in HookEventKind
        if any(
            b"custom.subscriptions" in file.managed_bytes
            for file in adapter.render(
                replace(
                    inputs,
                    skills=(),
                    agents=(),
                    hook_modes={},
                    host_subscription_events=(HostSubscriptionEvent(kind, (HookClass.OBSERVATION,)),),
                )
            )
            if file.surface is Surface.HOOKS or file.surface is Surface.PERMISSIONS
        )
    )


def _native_scripts(layers: tuple[ClientLayer, ...]) -> set[tuple[str, bool]]:
    found: set[tuple[str, bool]] = set()
    for layer in layers:
        for command in hook_commands(mapping(layer.get("data")).get("hooks")):
            try:
                words = shlex.split(command)
            except ValueError:
                continue
            if (path := script_path(words)) is not None:
                found.add((path, path != words[0] or "/" in path))
    return found


def _script_observations(
    fs: CheckoutFs,
    runner: HostCommandRunner | None,
    layers: tuple[ClientLayer, ...],
    trust: Mapping[str, object],
    subscriptions: tuple[JsonObject, ...],
) -> tuple[ScriptObservation, ...]:
    scripts: list[tuple[str, bool, str | None, bool]] = [
        (path, local, None, False) for path, local in sorted(_native_scripts(layers))
    ]
    for sub in subscriptions:
        target = mapping(sub.get("target"))
        argv = strings(target.get("argv"))
        if (path := script_path(argv)) is not None:
            local = target.get("cwd") == "checkout" and (path != argv[0] or "/" in path)
            subscription_id = str(sub["id"])
            scripts.append((path, local, subscription_id, trust.get(subscription_id) == sub["digest"]))

    observations: list[ScriptObservation] = []
    for path, local, subscription_id, trusted in scripts:
        relative = path.removeprefix("./") if local else ""
        if path.startswith("/"):
            relative = path.removeprefix(str(fs.root).rstrip("/") + "/")
        checkout_file = executable = False
        if is_safe_relative_path(relative):
            try:
                checkout_file = fs.read(relative) is not None
                if checkout_file and runner is not None:
                    result = runner.run(
                        ("test", "-x", str(fs.root / relative)),
                        cwd=fs.root,
                        env={"PATH": "/usr/bin:/bin"},
                        stdin=b"",
                        timeout_ms=1000,
                    )
                    executable = result.exit_code == 0 and not result.timed_out
            except (OSError, ValueError, SkmError):
                pass
        observations.append(ScriptObservation(path, executable, checkout_file, subscription_id, trusted))
    return tuple(observations)


def _hygiene(
    ctx: HostContext,
    fs: CheckoutFs,
    layers: tuple[ClientLayer, ...],
    trust: Mapping[str, object],
    subscriptions: tuple[JsonObject, ...],
) -> HygieneObservation:
    files = {
        path: text
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            "composer.json",
            "pubspec.yaml",
            "phpunit.xml",
            "tests/TestCase.php",
        )
        if (text := read_text(fs, path)) is not None
    }
    runner = ctx.gateways.get(HostCommandRunner) if ctx.gateways.has(HostCommandRunner) else None
    observations = _script_observations(fs, runner, layers, trust, subscriptions)

    skills: tuple[str, ...] = ()
    if "pubspec.yaml" in files and runner is not None:
        try:
            result = runner.run(
                (
                    "find",
                    "-P",
                    "skills",
                    "-mindepth",
                    "2",
                    "-maxdepth",
                    "2",
                    "-type",
                    "f",
                    "-name",
                    "SKILL.md",
                    "-print0",
                ),
                cwd=fs.root,
                env={"PATH": "/usr/bin:/bin"},
                stdin=b"",
                timeout_ms=1000,
            )
            if result.exit_code == 0 and not result.timed_out:
                skills = tuple(
                    sorted(
                        path
                        for path in result.stdout.decode("utf-8").split("\0")
                        if is_safe_relative_path(path)
                        and path.startswith("skills/")
                        and path.count("/") == 2
                        and path.endswith("/SKILL.md")
                    )
                )
        except (OSError, ValueError, SkmError):
            pass
    return HygieneObservation(files, skills, observations)


def doctor_context(
    ctx: HostContext,
    fs: CheckoutFs,
    adapter: IntegrationTarget,
    inputs: ProjectionInputs,
    files: tuple[DesiredFile, ...],
    *,
    repository_id: UUID,
    mount: str,
    drift_paths: tuple[str, ...] = (),
) -> DoctorContext:
    layers = read_layers(ctx, adapter, fs)
    directories: dict[str, bool | None] = {}
    for path in strings(mapping(effective_settings(layers).get("permissions")).get("additionalDirectories")):
        try:
            if path.startswith("/") and not (fs.root / path).is_relative_to(fs.root):
                if ctx.gateways.has(HostCommandRunner):
                    result = ctx.gateways.get(HostCommandRunner).run(
                        ("test", "-d", path), cwd=fs.root, env={}, stdin=b"", timeout_ms=1000
                    )
                    directories[path] = (
                        result.exit_code == 0 if result.exit_code in (0, 1) and not result.timed_out else None
                    )
                else:
                    directories[path] = None
                continue
            relative = str((fs.root / path).relative_to(fs.root)) if path.startswith("/") else path
            observer = getattr(fs, "observe_entry", None)
            if callable(observer):
                directories[path] = (
                    cast("tuple[FileKind, bytes | None, bool, bool]", observer(relative))[0]
                    is FileKind.DIRECTORY
                )
            else:
                observed = fs.stat(relative)
                directories[path] = False if not observed.exists else None
        except (OSError, ValueError, SkmError):
            directories[path] = None
    marker_files: dict[str, bytes] = {}
    for path in dict.fromkeys(
        (
            *adapter.instruction_paths(),
            *(file.relative_path for file in files if file.surface is Surface.INSTRUCTIONS),
        )
    ):
        text = read_text(fs, path)
        if text is not None:
            marker_files[path] = text.encode()
    subscriptions, violations = parse_subscriptions(mapping(_config(ctx, "hooks.subscriptions", {})), {})
    workspace_id = resolve_project_workspace_id(ctx, inputs.project_id)
    listed = ctx.client.ask(ListHookSubscriptions(workspace_id=workspace_id, project_id=inputs.project_id))
    assert isinstance(listed, ListHookSubscriptionsResult)  # noqa: S101
    # The control plane validates effective subscriptions with its event and sink registries.
    # Only entries absent from that result need the host-side fallback validation.
    server_ids = {item.id for item in listed.items}
    subscriptions = tuple(sub for sub in subscriptions if sub.id not in server_ids)
    validated_keys = {"hooks.subscriptions." + sub_id for sub_id in server_ids}
    violations = tuple(problem for problem in violations if problem.key not in validated_keys)
    host_commands: dict[str, JsonObject] = {}
    if any(item.enabled and item.valid and item.execution_location == "host" for item in listed.items):
        policy = cast(
            "Mapping[str, Any]",
            ctx.client.ask(
                GetHookPolicy.from_json({"project_id": str(inputs.project_id), "target": inputs.target.value})
            ),
        )
        host_commands = {
            item["id"]: {"argv": item["argv"], "cwd": item["cwd"], "digest": item["digest"]}
            for item in policy["subscriptions"]
        }
    subscription_facts: tuple[JsonObject, ...] = tuple(
        {**cast("JsonObject", item.to_json()), "target": host_commands[item.id]}
        if item.id in host_commands and item.digest == host_commands[item.id]["digest"]
        else cast("JsonObject", item.to_json())
        for item in listed.items
    )
    trust = mapping(_config(ctx, "hooks.host.trusted", {}))
    known = {
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "SubagentStop",
        "Stop",
        "PermissionRequest",
        "Notification",
        "PreCompact",
    }
    return DoctorContext(
        target=inputs.target,
        layers=layers,
        expected=_expected(files),
        directories=directories,
        commands=_commands(ctx, fs, layers),
        known_hook_events=frozenset(known),
        drift_paths=drift_paths,
        marker_files=marker_files,
        subscriptions=subscriptions,
        subscription_facts=subscription_facts,
        subscription_violations=violations,
        trusted={key: value for key, value in trust.items() if isinstance(value, str)},
        supported_kinds=_supported(adapter, inputs),
        checkout_marker=_checkout_marker(
            fs, inputs.project_id, workspace_id, repository_id, mount, ctx.instance_id
        ),
        enforcement_enabled=any(inputs.hook_modes.get(surface) is HookMode.STRICT for surface in ENFORCEMENT),
        hygiene=_hygiene(ctx, fs, layers, trust, subscription_facts),
    )
