"""Facade of the policy module (policy §13).

Pure functions need no unit of work: the worker, the host hook operation and render adapters call them with
data they obtained by query. ``propose_intent``/``require_approved``/``record_outcome`` run in the unit of
work of the caller: execution drives the life cycle of push and PR in its own transactions, a worker never
calls them. Each starts with a fresh admission of the acting principal; the caller has already decided its
own right (execution ownership). The managed-file and changelog guards serve interactive hooks.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from skm.kernel.json_types import JsonObject, JsonValue

if TYPE_CHECKING:
    from skm.kernel.ids import ScopeId, ToolIntentId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.scopes import ScopeRef
    from skm.platform.config import EffectiveConfig

    from .application.commands import Context
    from .domain.approval import Approval, ApprovalDecision, ApprovalId, ApprovalRequired
    from .domain.calls import (
        FileDelete,
        FileEdit,
        FileRead,
        FileWrite,
        McpCall,
        RunCommand,
        ToolCall,
        WebAccess,
    )
    from .domain.command_classes import GIT_NETWORK_SUBCOMMANDS, PROJECTION_CARRIER_HEADS
    from .domain.commands import CommandMode, CommandPolicy, CommandRule
    from .domain.git_guard import GitViolation
    from .domain.network import FORGE_API_HOSTS, NetworkMode, NetworkPolicy
    from .domain.operations import (
        AccessCapability,
        OperationDecision,
        OperationName,
        OperationRule,
        PathOrigin,
        Requirement,
        StaticPathFacts,
        TaskAuthority,
    )
    from .domain.paths import PathPolicy, PathRule, PathScope, ScopedPath, ScopeRoots
    from .domain.permission_set import PermissionLayer, PermissionSet, tool_allowed
    from .domain.profiles import (
        parse_layer as parse_layer,
    )
    from .domain.profiles import (
        permission_set_from_document as permission_set_from_document,
    )
    from .domain.render import IsolationGrants, Violation
    from .domain.rm_guard import rm_is_safe, rm_targets
    from .domain.rule_ladder import GuardMode, LadderVerdict
    from .domain.tool_call import Allow, Ask, Deny, EnforcementMode, ToolDecision
    from .domain.tool_intent import EffectKind, IntentState, RiskClass, ToolIntent
    from .generated.commands import (
        ApproveIntent as ApproveIntent,
    )
    from .generated.commands import (
        DenyIntent as DenyIntent,
    )
    from .generated.commands import (
        ProposeIntent as ProposeIntent,
    )
    from .generated.commands import (
        RecordIntentOutcome as RecordIntentOutcome,
    )
    from .generated.commands import (
        RecordToolDecisions as RecordToolDecisions,
    )
    from .generated.commands import (
        StartIntentExecution as StartIntentExecution,
    )
    from .generated.intent_approval import IntentApprovalView as IntentApprovalView
    from .generated.queries import (
        CheckToolCall as CheckToolCall,
    )
    from .generated.queries import (
        EffectivePermissions as EffectivePermissions,
    )
    from .generated.queries import (
        ExplainPermissions as ExplainPermissions,
    )
    from .generated.queries import (
        GetIntent as GetIntent,
    )
    from .generated.queries import (
        ListIntents as ListIntents,
    )
    from .generated.queries import (
        ListProfiles as ListProfiles,
    )
    from .generated.results import (
        ApproveIntentResult as ApproveIntentResult,
    )
    from .generated.results import (
        DenyIntentResult as DenyIntentResult,
    )
    from .generated.results import (
        ExplainPermissionsResult as ExplainPermissionsResult,
    )
    from .generated.results import (
        ListProfilesResult as ListProfilesResult,
    )
    from .generated.results import (
        ProposeIntentResult as ProposeIntentResult,
    )
    from .generated.results import (
        RecordIntentOutcomeResult as RecordIntentOutcomeResult,
    )
    from .generated.results import (
        RecordToolDecisionsResult as RecordToolDecisionsResult,
    )
    from .generated.results import (
        StartIntentExecutionResult as StartIntentExecutionResult,
    )
    from .generated.views import (
        EffectivePermissionsView as EffectivePermissionsView,
    )
    from .generated.views import (
        IntentsView as IntentsView,
    )
    from .generated.views import IntentView
    from .generated.views import (
        ToolDecisionView as ToolDecisionView,
    )
    from .ports import PathFacts

_LAZY_EXPORTS: dict[str, str] = {
    **dict.fromkeys(("Approval", "ApprovalDecision", "ApprovalId", "ApprovalRequired"), ".domain.approval"),
    **dict.fromkeys(("GIT_NETWORK_SUBCOMMANDS", "PROJECTION_CARRIER_HEADS"), ".domain.command_classes"),
    **dict.fromkeys(("CommandMode", "CommandPolicy", "CommandRule"), ".domain.commands"),
    "GitViolation": ".domain.git_guard",
    **dict.fromkeys(("FORGE_API_HOSTS", "NetworkMode", "NetworkPolicy"), ".domain.network"),
    **dict.fromkeys(
        (
            "AccessCapability",
            "OperationDecision",
            "OperationName",
            "OperationRule",
            "PathOrigin",
            "Requirement",
            "StaticPathFacts",
            "TaskAuthority",
        ),
        ".domain.operations",
    ),
    **dict.fromkeys(("PathPolicy", "PathRule", "PathScope", "ScopedPath", "ScopeRoots"), ".domain.paths"),
    **dict.fromkeys(("PermissionLayer", "PermissionSet", "tool_allowed"), ".domain.permission_set"),
    **dict.fromkeys(("parse_layer", "permission_set_from_document"), ".domain.profiles"),
    **dict.fromkeys(("IsolationGrants", "Violation"), ".domain.render"),
    **dict.fromkeys(("rm_is_safe", "rm_targets"), ".domain.rm_guard"),
    **dict.fromkeys(("GuardMode", "LadderVerdict"), ".domain.rule_ladder"),
    **dict.fromkeys(
        ("FileDelete", "FileEdit", "FileRead", "FileWrite", "McpCall", "RunCommand", "ToolCall", "WebAccess"),
        ".domain.calls",
    ),
    **dict.fromkeys(("Allow", "Ask", "Deny", "EnforcementMode", "ToolDecision"), ".domain.tool_call"),
    **dict.fromkeys(("EffectKind", "IntentState", "RiskClass", "ToolIntent"), ".domain.tool_intent"),
    "IntentApprovalView": ".generated.intent_approval",
    "IntentView": ".generated.views",
    "PathFacts": ".ports",
    **dict.fromkeys(
        (
            "ApproveIntent",
            "DenyIntent",
            "ProposeIntent",
            "RecordIntentOutcome",
            "RecordToolDecisions",
            "StartIntentExecution",
        ),
        ".generated.commands",
    ),
    **dict.fromkeys(
        (
            "CheckToolCall",
            "EffectivePermissions",
            "ExplainPermissions",
            "GetIntent",
            "ListIntents",
            "ListProfiles",
        ),
        ".generated.queries",
    ),
    **dict.fromkeys(
        (
            "ApproveIntentResult",
            "DenyIntentResult",
            "ExplainPermissionsResult",
            "ListProfilesResult",
            "ProposeIntentResult",
            "RecordIntentOutcomeResult",
            "RecordToolDecisionsResult",
            "StartIntentExecutionResult",
        ),
        ".generated.results",
    ),
    **dict.fromkeys(("EffectivePermissionsView", "IntentsView", "ToolDecisionView"), ".generated.views"),
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


class _JsonView(Protocol):
    def to_json(self) -> dict[str, object]: ...


def _document(view: object) -> Mapping[str, object]:
    if isinstance(view, Mapping):
        return cast("Mapping[str, object]", view)
    return cast("_JsonView", view).to_json()


def check_tool_call(
    perms: PermissionSet,
    call: ToolCall,
    *,
    roots: ScopeRoots,
    facts: PathFacts,
    authority: TaskAuthority,
    mode: EnforcementMode,
) -> ToolDecision:
    from .application.composition import builtin_profiles
    from .domain.tool_call import check_tool_call as _check_tool_call

    reference = builtin_profiles()["read-only"].permissions.commands
    return _check_tool_call(
        perms, call, roots=roots, facts=facts, authority=authority, mode=mode, reference=reference
    )


def narrow(perms: PermissionSet, layer: PermissionLayer) -> PermissionSet:
    from .domain.permission_set import narrow as _narrow

    return _narrow(perms, layer)


def permission_set_from_view(view: object) -> PermissionSet:
    """``PermissionSetView`` (generated record or its JSON) → permission set; a defect: ``SCHEMA_INVALID``."""
    from .domain.profiles import permission_set_from_document

    return permission_set_from_document(_document(view))


def permission_set_to_view(perms: PermissionSet) -> JsonObject:
    """Serialize the transport view; the digest-only canonical form is not a view."""
    from .domain.render import view_document

    return view_document(perms)


def _path_rules(items: object) -> tuple[PathRule, ...]:
    from .domain.profiles import parse_layer

    layer = parse_layer({"fs": {"write": {"allow": cast("JsonValue", items)}}}, source="view")
    return () if layer.fs_write is None else layer.fs_write.allow


def task_authority_from_view(view: object) -> TaskAuthority:
    """``TaskAuthorityView`` (``urn:skm:policy:task-authority:v1``) → task authority."""
    from .domain.operations import AccessCapability, OperationName, TaskAuthority

    doc = _document(view)
    write_scope = doc.get("write_scope")
    return TaskAuthority(
        write_scope=None if write_scope is None else _path_rules(write_scope),
        delete_scope=_path_rules(doc.get("delete_scope", [])),
        operations=frozenset(
            OperationName(str(item)) for item in cast("list[object]", doc.get("operations", []))
        ),
        capabilities=frozenset(
            AccessCapability(str(item)) for item in cast("list[object]", doc.get("capabilities", []))
        ),
    )


_GUARDED_GIT_SUBCOMMANDS = frozenset(
    {
        "push",
        "reset",
        "clean",
        "branch",
        "checkout",
        "restore",
        "switch",
        "stash",
        "reflog",
        "update-ref",
        "rebase",
        "filter-branch",
    }
)


def git_guard_check(command: str) -> GitViolation | None:
    if command and command.isascii() and all(ch.isalnum() or ch in " _./:-" for ch in command):
        tokens = command.split()
        if (
            len(tokens) >= 2
            and tokens[0] == "git"
            and not tokens[1].startswith("-")
            and tokens[1] not in _GUARDED_GIT_SUBCOMMANDS
        ):
            return None
    from .domain.git_guard import check

    return check(command)


def managed_hit(
    tool_input: JsonValue, cwd: str, managed: frozenset[str], *, protected_dirs: tuple[str, ...]
) -> str | None:
    from .domain.managed_guard import managed_hit as _managed_hit

    return _managed_hit(tool_input, cwd, managed, protected_dirs=protected_dirs)


def managed_guard_verdict(hit: str | None, *, mode: GuardMode) -> LadderVerdict:
    from .domain.rule_ladder import LadderRule, verdict

    rules = (LadderRule("MANAGED_FILE", ".+", "Edit the source, then run skm integrations apply."),)
    return verdict(hit or "", rules=rules, mode=mode)


def changelog_gate_verdict(message: str, *, mode: GuardMode) -> LadderVerdict:
    from .domain.changelog_gate import changelog_gate_verdict as _changelog_gate_verdict

    return _changelog_gate_verdict(message, mode=mode)


def representable_paths(policies: tuple[PathPolicy, ...]) -> PathPolicy | None:
    from .domain.render import representable_paths as _representable_paths

    return _representable_paths(policies)


def isolation_grants(perms: PermissionSet, roots: ScopeRoots, profile: str) -> IsolationGrants:
    from .domain.render import isolation_grants as _isolation_grants

    return _isolation_grants(perms, roots, profile)


def permissions_digest(perms: PermissionSet) -> str:
    """``platform.jsonc`` digest of the canonical form without ``sources`` (bundle ``policy_digest``)."""
    from skm.platform.jsonc.digest import digest

    from .domain.permission_set import canonical_document

    return digest(canonical_document(perms))


def effective_permissions(
    uow: UnitOfWork,
    *,
    scope_chain: tuple[ScopeRef, ...],
    config: EffectiveConfig,
    profile_id: str | None,
    role_layer: PermissionLayer | None,
    task_layer: PermissionLayer | None,
    allow_unconfined: bool,
) -> PermissionSet:
    """Composition of §5.1 on the caller's live configuration; reads no repository."""
    from .application.composition import compose_effective

    del uow, scope_chain  # the configuration of the chain already carries every level
    return compose_effective(
        config,
        profile_id=profile_id,
        role_layer=role_layer,
        task_layer=task_layer,
        allow_unconfined=allow_unconfined,
    )


def _hint(hint: object) -> tuple[str, str, str]:
    if isinstance(hint, Mapping):
        doc = cast("Mapping[str, object]", hint)
        return str(doc.get("mount", "")), str(doc.get("pattern", "")), str(doc.get("change", ""))
    return (
        str(getattr(hint, "mount", "")),
        str(getattr(hint, "pattern", "")),
        str(getattr(hint, "change", "")),
    )


def task_authority(
    config: EffectiveConfig, *, write_scope: tuple[PathRule, ...] | None, change_hints: tuple[object, ...]
) -> TaskAuthority:
    """Delete scope = hints with ``change ∈ {delete, any}`` that the write scope provably contains."""
    from .application.composition import task_authority_from
    from .domain.paths import PathRule, PathScope, subsumes

    delete_scope: list[PathRule] = []
    for hint in change_hints:
        mount, pattern, change = _hint(hint)
        if change not in {"delete", "any"} or not pattern:
            continue
        rule = PathRule(PathScope.WORKTREE, pattern, mount or None)
        if write_scope is None or any(subsumes(outer, rule) for outer in write_scope):
            delete_scope.append(rule)
    return task_authority_from(config, write_scope=write_scope, delete_scope=delete_scope)


def forbidden_paths_layer(forbidden: tuple[tuple[str, str], ...], *, source: str) -> PermissionLayer:
    from .application.composition import forbidden_paths_layer as _forbidden_paths_layer

    return _forbidden_paths_layer(forbidden, source=source)


def _view(uow: UnitOfWork, intent: ToolIntent) -> IntentView:
    from .application.commands import intent_view
    from .ports import ApprovalRepository

    return intent_view(intent, uow.repo(ApprovalRepository).for_intent(intent.id))


def propose_intent(
    uow: UnitOfWork,
    ctx: Context,
    *,
    scope_id: ScopeId,
    subject_ref: str,
    kind: EffectKind,
    args: Mapping[str, object],
    reason: str,
    perms: PermissionSet,
) -> IntentView:
    """The intent of an external effect in the caller's transaction (an open one is returned as is).

    ``perms`` are the permissions the caller composed for the step; a kind outside them, or arguments nobody
    may approve, give a ``denied`` intent, a kind that needs no human is approved by the system at once.
    """
    from .application.commands import admit
    from .application.commands.propose_intent import propose_in

    admit(uow, ctx)
    intent = propose_in(
        uow, ctx, scope_id=scope_id, subject_ref=subject_ref, kind=kind, args=args, reason=reason, perms=perms
    )
    return _view(uow, intent)


def require_approved(
    uow: UnitOfWork, ctx: Context, *, intent_id: ToolIntentId, args_digest: str
) -> IntentView:
    """``policy.start_intent_execution`` in the caller's transaction: the only admission of an effect.

    Refused with ``APPROVAL_REQUIRED`` (waits for a human), ``APPROVAL_MISMATCH`` (changed arguments, a spent
    or expired approval) or ``FORBIDDEN`` (``revoked``: the ceiling no longer permits the kind;
    ``approval_authority_revoked``: the approver lost the right). The caller does the IO after this returns,
    outside the transaction. The live check reads the configuration of ``ctx``: the caller passes the context
    of the scope that runs the effect.
    """
    from .application.commands import admit
    from .application.commands.start_intent_execution import start_in

    admit(uow, ctx)
    executing, _approval = start_in(uow, ctx, intent_id=intent_id, args_digest=args_digest)
    return _view(uow, executing)


def record_outcome(
    uow: UnitOfWork,
    ctx: Context,
    *,
    intent_id: ToolIntentId,
    outcome: str,
    receipt: Mapping[str, object],
) -> IntentView:
    """``executing -> succeeded|failed|outcome_unknown``; reconciliation settles ``outcome_unknown``."""
    from .application.commands import admit
    from .application.commands.record_intent_outcome import record_in

    admit(uow, ctx)
    resolved = record_in(uow, ctx, intent_id=intent_id, outcome=outcome, receipt=receipt)
    return _view(uow, resolved)


def intent_scope_id(uow: UnitOfWork, intent_id: ToolIntentId) -> ScopeId | None:
    """Resolve the stored ``scope_id`` of ``intent_id`` without ``token.own`` for SSE read filtering."""
    from skm.kernel.errors import NotFound

    from .ports import ToolIntentRepository

    try:
        return uow.repo(ToolIntentRepository).get(intent_id).scope_id
    except NotFound:
        return None


def is_subset(requested: Mapping[str, JsonValue], ceiling: object) -> tuple[Violation, ...]:
    """Every field of a ``urn:skm:policy:permission-request:v1`` document that ``ceiling`` (a
    ``PermissionSetView``, its JSON, or a ``PermissionSet``) does not provably contain; ``()``: none."""
    from .domain.permission_set import PermissionSet
    from .domain.render import request_violations

    limit = ceiling if isinstance(ceiling, PermissionSet) else permission_set_from_view(ceiling)
    return request_violations(requested, limit)


# fmt: off
__all__ = [
    "FORGE_API_HOSTS", "GIT_NETWORK_SUBCOMMANDS", "PROJECTION_CARRIER_HEADS",
    "AccessCapability", "Allow", "Approval", "ApprovalDecision", "ApprovalId", "ApprovalRequired",
    "ApproveIntent", "ApproveIntentResult", "Ask", "CheckToolCall", "CommandMode", "CommandPolicy",
    "CommandRule", "Deny", "DenyIntent", "DenyIntentResult", "EffectKind", "EffectivePermissions",
    "EffectivePermissionsView", "EnforcementMode", "ExplainPermissions", "ExplainPermissionsResult",
    "FileDelete", "FileEdit", "FileRead", "FileWrite", "GetIntent", "GitViolation", "GuardMode",
    "IntentApprovalView", "IntentState", "IntentView", "IntentsView", "IsolationGrants", "LadderVerdict",
    "ListIntents", "ListProfiles", "ListProfilesResult", "McpCall", "NetworkMode", "NetworkPolicy",
    "OperationDecision", "OperationName", "OperationRule", "PathFacts", "PathOrigin", "PathPolicy",
    "PathRule", "PathScope",
    "PermissionLayer", "PermissionSet", "ProposeIntent", "ProposeIntentResult", "RecordIntentOutcome",
    "RecordIntentOutcomeResult", "RecordToolDecisions", "RecordToolDecisionsResult", "Requirement",
    "RiskClass", "RunCommand", "ScopeRoots", "ScopedPath", "StartIntentExecution",
    "StartIntentExecutionResult", "StaticPathFacts", "TaskAuthority", "ToolCall", "ToolDecision",
    "ToolDecisionView", "ToolIntent", "Violation", "WebAccess", "changelog_gate_verdict",
    "check_tool_call", "effective_permissions", "forbidden_paths_layer", "git_guard_check",
    "intent_scope_id", "is_subset",
    "isolation_grants", "managed_guard_verdict", "managed_hit", "narrow", "permission_set_from_view",
    "permission_set_to_view", "permissions_digest", "propose_intent", "record_outcome",
    "representable_paths", "require_approved", "rm_is_safe", "rm_targets", "task_authority",
    "task_authority_from_view", "tool_allowed",
]
# fmt: on
