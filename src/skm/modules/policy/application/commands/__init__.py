"""Checks and mappings shared by the policy handlers, the queries and the facade (policy §7, §13).

They live in the package module because a file of ``commands/`` or ``queries/`` is a registered operation.

``SELF_PERMISSION`` is the bus right of the operations whose DTO names an intent, not a scope: the bus lets
every authenticated principal through, and the handler loads the intent and decides the real permission on
the scope of the intent (``require``), with the same decision (reason code included) the bus would give.

``require_active_scope`` is the admission point of a new proposal, approval or execution: it reads the
*current* state of the project and workspace on the chain, so an archived area refuses at once. Deny, outcome
recording and expiry never call it (closing an area must not strand an effect that already runs).

``approver_still_authorized`` is the live check of access §4.6 for the human who approved: the stored
principal is a human, is active, and holds ``intent.approve`` on the scope of the intent now. A credential
(bearer token) of the approver is deliberately not consulted: losing it does not erase a durable approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final, cast

from skm.application_bus.context import CommandContext
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, Unauthenticated, ValidationFailed
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry
from skm.modules.access.public import RbacAuthorizer
from skm.modules.policy.application.composition import compose_effective
from skm.modules.policy.domain.approval import Approval
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet
from skm.modules.policy.domain.profiles import parse_layer
from skm.modules.policy.domain.tool_intent import EffectKind, RiskClass, ToolIntent
from skm.modules.policy.generated import views
from skm.modules.workspace.public import require_active_project, require_active_workspace

if TYPE_CHECKING:
    from skm.kernel.clock import Clock
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config import EffectiveConfig

__all__ = [
    "SELF_PERMISSION",
    "Context",
    "admit",
    "allow_unconfined",
    "approval_single_use",
    "approver_still_authorized",
    "chain_of",
    "effective_for",
    "intent_view",
    "layer_of",
    "require",
    "require_active_scope",
    "require_human",
    "require_operator",
    "risk_of",
    "setting",
    "workspace_of",
]

Context = CommandContext  # the context of a handler, for the facade that runs in a handler's unit of work
SELF_PERMISSION: Final = "token.own"
_UNCONFINED_KEY: Final = "policy.host.allow_unconfined"
_CONFIG_NOT_VISIBLE: Final = frozenset({ErrorCode.CONFIG_SCOPE_NOT_ALLOWED, ErrorCode.CONFIG_UNKNOWN_KEY})
_APPROVE: Final = "intent.approve"


def admit(uow: UnitOfWork, ctx: CommandContext) -> None:
    """Access §4.6 for the acting principal now: ``UNAUTHENTICATED`` unless principal and credential live."""
    RbacAuthorizer(ctx.clock).admit(uow, ctx.actor)


def chain_of(uow: UnitOfWork, scope_id: ScopeId) -> tuple[ScopeRecord, ...]:
    return uow.repo(ScopeRegistry).ancestors(ScopeId(scope_id))


def workspace_of(chain: Sequence[ScopeRecord]) -> WorkspaceId:
    """The workspace of the scope; an intent lives inside one (``tool_intents.workspace_id`` is required)."""
    for record in reversed(chain):
        if record.workspace_id is not None:
            return record.workspace_id
    raise ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        "an intent belongs to a scope inside a workspace",
        details={"field": "scope_id", "reason": "scope_outside_workspace"},
    )


def require(uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope_id: ScopeId) -> None:
    """``FORBIDDEN`` unless ``actor`` holds ``permission`` on ``scope_id`` now (the reason code is kept)."""
    verdict = RbacAuthorizer(clock).authorize(uow, actor, permission, chain_of(uow, scope_id))
    if not verdict.allowed:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            f"{permission} is not granted here",
            details={
                "permission": permission,
                "scope_id": str(scope_id),
                "reason_code": verdict.reason_code or "",
            },
        )


def require_operator(uow: UnitOfWork, ctx: CommandContext, scope_id: ScopeId) -> None:
    """Who may drive an intent: a human (or the service owner) with ``run.control``, a worker with
    ``worker.claim``, both on the scope of the intent."""
    permission = "worker.claim" if ctx.actor.kind is PrincipalKind.WORKER else "run.control"
    require(uow, ctx.clock, ctx.actor, permission, scope_id)


def require_human(actor: Actor) -> None:
    """The human gate (policy §7): approval and denial by a user are a human act; ``Actor.kind`` is the
    stored kind of the principal (the bus compares it with the record), never a field of the request."""
    if actor.kind is not PrincipalKind.HUMAN:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "only a human approves or denies an intent",
            details={"permission": _APPROVE, "reason": "human_gate"},
        )


def require_active_scope(uow: UnitOfWork, scope_id: ScopeId) -> None:
    """``PROJECT_ARCHIVED`` when the project or the workspace of the scope is not active."""
    chain = chain_of(uow, scope_id)
    projects = [record for record in chain if record.kind is ScopeKind.PROJECT]
    if projects:
        require_active_project(uow, ProjectId(projects[-1].id))  # also checks its workspace
        return
    workspaces = [record for record in chain if record.kind is ScopeKind.WORKSPACE]
    if workspaces:
        require_active_workspace(uow, WorkspaceId(workspaces[-1].id))


def approver_still_authorized(
    uow: UnitOfWork, clock: Clock, approver_id: PrincipalId, scope_id: ScopeId
) -> bool:
    """The approver is a stored, active human who holds ``intent.approve`` on the scope of the intent now."""
    actor = Actor(principal_id=approver_id, kind=PrincipalKind.HUMAN, display_name="approver")
    try:
        verdict = RbacAuthorizer(clock).authorize(uow, actor, _APPROVE, chain_of(uow, scope_id))
    except Unauthenticated:  # unknown, disabled or not a human any more
        return False
    return verdict.allowed


# ------------------------------------------------------------------------------------------ configuration
def setting(config: EffectiveConfig, key: str, default: JsonValue) -> JsonValue:
    value = config.get(key)
    return default if value is None else value


def approval_single_use(config: EffectiveConfig) -> bool:
    return setting(config, "policy.approval.single_use", True) is True


def allow_unconfined(config: EffectiveConfig) -> bool:
    """``policy.host.allow_unconfined`` is a host-chain key: a workspace-chain context cannot see it.

    Not visible means not allowed (fail closed).
    """
    try:
        return config.get(_UNCONFINED_KEY) is True
    except ValidationFailed as error:
        if error.code in _CONFIG_NOT_VISIBLE:
            return False
        raise


def layer_of(document: object, source: str) -> PermissionLayer | None:
    if document is None:
        return None
    to_json = getattr(document, "to_json", None)
    body = to_json() if callable(to_json) else document
    return parse_layer(cast("Mapping[str, object]", body), source=source)


def effective_for(
    config: EffectiveConfig,
    *,
    profile_id: str | None,
    role_layer: PermissionLayer | None,
    task_layer: PermissionLayer | None,
    interactive: bool = False,
) -> PermissionSet:
    return compose_effective(
        config,
        profile_id=profile_id,
        role_layer=role_layer,
        task_layer=task_layer,
        allow_unconfined=allow_unconfined(config),
        interactive=interactive,
    )


def risk_of(config: EffectiveConfig, kind: EffectKind) -> RiskClass:
    table = config.get("policy.effects.risk")
    if isinstance(table, Mapping):
        found = cast("Mapping[str, JsonValue]", table).get(EffectKind(kind).value)
        if isinstance(found, str):
            return RiskClass(found)
    return RiskClass.MEDIUM


# ------------------------------------------------------------------------------------------ views
def _approval_item(approval: Approval) -> views.IntentViewApprovalsItem:
    return views.IntentViewApprovalsItem(
        id=approval.id,
        intent_id=approval.intent_id,
        approver_id=approval.approver_id,
        decision=approval.decision.value,
        args_digest=approval.args_digest,
        single_use=approval.single_use,
        expires_at=approval.expires_at,
        used_at=approval.used_at,
        reason=approval.reason,
        created_at=approval.created_at,
    )


def intent_view(intent: ToolIntent, approvals: Sequence[Approval]) -> views.IntentView:
    return views.IntentView(
        intent_id=intent.id,
        kind=views.EffectKind(EffectKind(intent.kind).value),
        risk=views.RiskClass(RiskClass(intent.risk).value),
        state=intent.state.value,
        subject_ref=intent.subject_ref,
        created_at=intent.created_at,
        expires_at=intent.expires_at,
        scope_id=intent.scope_id,
        workspace_id=intent.workspace_id,
        actor_id=intent.actor_id,
        normalized_args=dict(intent.normalized_args),
        args_digest=intent.args_digest,
        reason=intent.reason,
        denied_reason=intent.denied_reason,
        row_version=intent.row_version,
        approvals=tuple(_approval_item(item) for item in approvals),
    )
