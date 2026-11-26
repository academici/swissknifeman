"""``workspace.host.bind_checkout`` (workspace §5.2, §6.2, §9, §12): observe local checkout and bind it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Never, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, RepositoryId, WorkspaceId
from skm.kernel.module_manifest import HostOperationSpec
from skm.kernel.outcomes import Diagnostic, Severity
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.workspace.domain.checkout_binding import CheckoutBindingId, ObservedCheckout
from skm.modules.workspace.domain.checkout_marker import CheckoutMarker, marker_to_document
from skm.modules.workspace.domain.mount import DEFAULT_MOUNT_NAME, MountName
from skm.modules.workspace.domain.remote_url import normalize_remote
from skm.modules.workspace.generated.commands import AttachRepository, BindCheckout, RegisterRepository
from skm.modules.workspace.generated.queries import GetProject, ListProjectRepositories, MatchCheckout
from skm.modules.workspace.generated.results import BindCheckoutResult, RegisterRepositoryResult
from skm.modules.workspace.generated.views import (
    AttachDecisionView,
    ListProjectRepositoriesView,
    MountView,
    ProjectView,
)
from skm.modules.workspace.ports import RepositoryInspector

from .checkout_config import checkout_marker_relpath, git_timeout_seconds
from .checkout_transaction import BeginCheckout, CheckoutTransaction

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.workspace.generated.documents import CheckoutMarkerDoc

__all__ = [
    "SPEC",
    "BindCheckoutOperation",
    "BindCheckoutReport",
    "BindCheckoutRequest",
    "bind_checkout",
    "run",
]

type MountRoleLiteral = Literal["primary", "secondary", "docs", "infra"]
type BindingStateLiteral = Literal["active", "missing", "mismatched", "removed"]


def _step_key(step_keys: dict[str, str], ctx: HostContext, step: str) -> str:
    if step not in step_keys:
        step_keys[step] = ctx.client.new_idempotency_key()
    return step_keys[step]


def _log_warn(ctx: HostContext, event: str, **fields: Any) -> None:
    warn_fn = getattr(ctx.log, "warning", None) or getattr(ctx.log, "warn", None)
    if callable(warn_fn):
        warn_fn(event, **fields)


@dataclass(frozen=True, slots=True)
class BindCheckoutRequest:
    """Parameters for ``workspace.host.bind_checkout``."""

    workspace_id: WorkspaceId
    path: str = "."
    project_id: ProjectId | None = None
    repository_id: RepositoryId | None = None
    mount_name: str = DEFAULT_MOUNT_NAME
    role: MountRoleLiteral = "primary"
    title: str | None = None
    assume_yes: bool = False
    register_missing: bool = False
    write_marker: bool = False
    instance_id: UUID | None = None
    confirm: Callable[[AttachDecisionView], bool] | None = None
    idempotency_keys: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class BindCheckoutReport:
    """Outcome of ``workspace.host.bind_checkout``."""

    binding_id: CheckoutBindingId
    workspace_id: WorkspaceId
    project_id: ProjectId | None
    repository_id: RepositoryId
    mount_name: str | None
    local_locator: str
    state: BindingStateLiteral
    reason: str | None
    row_version: int
    marker_written: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_json(self) -> JsonObject:
        return {
            "binding_id": str(self.binding_id),
            "workspace_id": str(self.workspace_id),
            "project_id": None if self.project_id is None else str(self.project_id),
            "repository_id": str(self.repository_id),
            "mount_name": self.mount_name,
            "local_locator": self.local_locator,
            "state": self.state,
            "reason": self.reason,
            "row_version": self.row_version,
            "marker_written": self.marker_written,
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity.value,
                    "details": dict(item.details),
                }
                for item in self.diagnostics
            ],
        }


class BindCheckoutOperation(Protocol):
    def __call__(
        self, ctx: HostContext, request: BindCheckoutRequest | Mapping[str, Any]
    ) -> BindCheckoutReport: ...


def _observe(
    inspector: RepositoryInspector,
    path: str,
    *,
    marker_relpath: str,
    timeout_seconds: float,
) -> tuple[ObservedCheckout, tuple[Diagnostic, ...]]:
    with_diag = getattr(inspector, "observe_with_diagnostics", None)
    if callable(with_diag):
        result = cast(
            "tuple[ObservedCheckout, tuple[object, ...]]",
            with_diag(path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds),
        )
        converted: list[Diagnostic] = []
        for item in result[1]:
            if isinstance(item, Diagnostic):
                converted.append(item)
            elif isinstance(item, str):
                converted.append(
                    Diagnostic(
                        code=item,
                        message=f"checkout observation diagnostic: {item}",
                        severity=Severity.WARNING,
                    )
                )
        return result[0], tuple(converted)
    observed = inspector.observe(path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds)
    return observed, ()


def _diagnostics_from_view(items: tuple[JsonObject, ...]) -> tuple[Diagnostic, ...]:
    out: list[Diagnostic] = []
    for raw in items:
        code = str(raw.get("code", "DIAGNOSTIC"))
        message = str(raw.get("message", ""))
        sev_raw = str(raw.get("severity", "warning"))
        severity = Severity(sev_raw) if sev_raw in {s.value for s in Severity} else Severity.WARNING
        details_raw = raw.get("details")
        details: JsonObject = dict(details_raw) if isinstance(details_raw, Mapping) else {}
        out.append(Diagnostic(code=code, message=message, severity=severity, details=details))
    return tuple(out)


def _raise_refusal(decision: AttachDecisionView, path: str) -> Never:
    code_str = decision.refuse_code or ErrorCode.CHECKOUT_MISMATCH.value
    details: dict[str, Any] = {
        **(decision.refuse_details or {}),
        "path": (decision.refuse_details or {}).get("path", path),
    }
    reason = str(details.get("reason", "checkout_refused"))
    if code_str == ErrorCode.AMBIGUOUS_REFERENCE.value:
        raise ValidationFailed(
            ErrorCode.AMBIGUOUS_REFERENCE,
            f"Checkout remotes match multiple repositories ({reason})",
            details=details,
        )
    if code_str == ErrorCode.SCHEMA_INVALID.value:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"Checkout cannot be bound without required parameters ({reason})",
            details=details,
        )
    if code_str == ErrorCode.NOT_FOUND.value:
        raise NotFound(
            ErrorCode.NOT_FOUND, f"Target for checkout binding was not found ({reason})", details=details
        )
    error_code = (
        ErrorCode(code_str) if code_str in {m.value for m in ErrorCode} else ErrorCode.CHECKOUT_MISMATCH
    )
    raise PreconditionFailed(error_code, f"Checkout cannot be bound ({reason})", details=details)


def _default_title(toplevel: str, canonical_remote: str | None) -> str:
    if canonical_remote and (tail := canonical_remote.rstrip("/").rsplit("/", 1)[-1]):
        return tail
    stripped = toplevel.rstrip("/")
    return (stripped.rsplit("/", 1)[-1] if "/" in stripped else stripped) or "repository"


def _resolve_registration_remote_url(
    inspector: RepositoryInspector, toplevel: str, canonical: str | None, timeout_s: float
) -> str | None:
    if canonical is None:
        return None
    if callable(remote_urls_fn := getattr(inspector, "remote_urls", None)):
        with suppress(Exception):
            for _name, url in cast(
                "tuple[tuple[str, str], ...]", remote_urls_fn(toplevel, timeout_s=timeout_s)
            ):
                if (norm := normalize_remote(url)) is not None and norm.value == canonical:
                    return url
    return canonical if normalize_remote(canonical) is not None else f"https://{canonical}"


def _ensure_mounted(
    ctx: HostContext,
    project_id: ProjectId,
    repository_id: RepositoryId,
    mount_name: str,
    role: MountRoleLiteral,
    step_keys: dict[str, str],
    transaction: CheckoutTransaction | None,
) -> str:
    mounts_view = ctx.client.ask(ListProjectRepositories(project_id=project_id, host_id=ctx.host_id))
    items = (
        mounts_view.items
        if isinstance(mounts_view, ListProjectRepositoriesView)
        else (cast("tuple[MountView, ...]", mounts_view) if isinstance(mounts_view, tuple) else ())
    )
    pending = transaction is not None and transaction.has_step("attach_repository")
    for item in items:
        if not pending and RepositoryId(item.repository.repository_id) == repository_id:
            return item.mount_name
    if not pending and not isinstance(mounts_view, (ListProjectRepositoriesView, tuple)):
        proj_view = ctx.client.ask(GetProject(project_id=project_id))
        if isinstance(proj_view, ProjectView):
            for mount in proj_view.mounts:
                if RepositoryId(mount.repository_id) == repository_id:
                    return mount.mount_name
    _dispatch(
        ctx,
        transaction,
        step_keys,
        "attach_repository",
        AttachRepository(
            project_id=project_id, repository_id=repository_id, mount_name=mount_name, role=role
        ),
    )
    return mount_name


def _resolve_instance_id(
    ctx: HostContext,
    req: BindCheckoutRequest,
    observed: ObservedCheckout,
) -> UUID:
    if req.instance_id is not None:
        return req.instance_id
    if observed.marker is not None:
        return observed.marker.instance_id
    whoami = ctx.client.ask(WhoAmI())
    if isinstance(whoami, WhoAmIView):
        for membership in whoami.memberships:
            if membership.scope_kind == "instance":
                return UUID(str(membership.scope_id))
    raise PreconditionFailed(
        ErrorCode.INVALID_TRANSITION,
        "Cannot determine instance_id required to write checkout marker",
        details={"reason": "instance_id_unavailable"},
    )


def _normalize_role(raw: str) -> MountRoleLiteral:
    role_map: dict[str, MountRoleLiteral] = {
        "primary": "primary",
        "secondary": "secondary",
        "dependency": "secondary",
        "docs": "docs",
        "reference": "docs",
        "infra": "infra",
    }
    if raw not in role_map:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid mount role {raw!r}",
            details={"field": "role", "value": raw},
        )
    return role_map[raw]


def _coerce_request(request: BindCheckoutRequest | Mapping[str, Any]) -> BindCheckoutRequest:
    if isinstance(request, BindCheckoutRequest):
        return request
    ws_raw = request["workspace_id"]
    proj_raw = request.get("project_id")
    repo_raw = request.get("repository_id")
    inst_raw = request.get("instance_id")
    role_raw = str(request.get("role", "primary"))
    idem_raw = request.get("idempotency_keys")
    return BindCheckoutRequest(
        workspace_id=WorkspaceId(ws_raw if isinstance(ws_raw, UUID) else UUID(str(ws_raw))),
        path=str(request.get("path", ".")),
        project_id=None
        if proj_raw is None
        else ProjectId(proj_raw if isinstance(proj_raw, UUID) else UUID(str(proj_raw))),
        repository_id=None
        if repo_raw is None
        else RepositoryId(repo_raw if isinstance(repo_raw, UUID) else UUID(str(repo_raw))),
        mount_name=str(request.get("mount_name", DEFAULT_MOUNT_NAME)),
        role=_normalize_role(role_raw),
        title=None if request.get("title") is None else str(request["title"]),
        assume_yes=bool(request.get("assume_yes", False)),
        register_missing=bool(request.get("register_missing", False)),
        write_marker=bool(request.get("write_marker", False)),
        instance_id=None
        if inst_raw is None
        else (inst_raw if isinstance(inst_raw, UUID) else UUID(str(inst_raw))),
        confirm=cast("Callable[[AttachDecisionView], bool] | None", request.get("confirm")),
        idempotency_keys=cast("Mapping[str, str] | None", idem_raw)
        if isinstance(idem_raw, Mapping)
        else None,
    )


def _dispatch(
    ctx: HostContext,
    transaction: CheckoutTransaction | None,
    keys: dict[str, str],
    step: str,
    command: object,
) -> object:
    if transaction is not None:
        return transaction.dispatch(step, command)
    return ctx.client.dispatch(command, idempotency_key=_step_key(keys, ctx, step))


def bind_checkout(  # noqa: PLR0912, PLR0915
    ctx: HostContext,
    request: BindCheckoutRequest | Mapping[str, Any],
    *,
    begin: BeginCheckout | None = None,
) -> BindCheckoutReport:
    """Execute the host-side checkout observation, attach decision, binding and optional marker write."""
    req = _coerce_request(request)
    inspector = ctx.gateways.get(RepositoryInspector)
    marker_relpath = checkout_marker_relpath(ctx)
    timeout_seconds = git_timeout_seconds(ctx)

    observed, obs_diagnostics = _observe(
        inspector, req.path, marker_relpath=marker_relpath, timeout_seconds=timeout_seconds
    )
    for diag in obs_diagnostics:
        _log_warn(ctx, "workspace.checkout.observation_diagnostic", code=diag.code, details=diag.details)

    if not observed.is_git_checkout or observed.toplevel is None:
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_MISMATCH,
            "Path is not a git checkout",
            details={"reason": "not_a_git_checkout", "path": req.path},
        )

    transaction = begin(observed) if begin is not None else None
    locator = observed.toplevel if transaction is None else transaction.locator
    step_keys = dict(req.idempotency_keys or {})

    diagnostics: list[Diagnostic] = list(obs_diagnostics)
    target_project_id: ProjectId | None = req.project_id
    target_mount_name: str | None = req.mount_name if req.project_id is not None else None

    marker_doc = (
        None if observed.marker is None else cast("CheckoutMarkerDoc", marker_to_document(observed.marker))
    )
    match = MatchCheckout(
        workspace_id=req.workspace_id,
        host_id=ctx.host_id,
        project_id=req.project_id,
        mount_name=req.mount_name,
        assume_yes=req.assume_yes,
        observed_exists=observed.exists,
        observed_toplevel=locator,
        observed_remotes=tuple(item.value for item in observed.remotes),
        observed_head=observed.head,
        observed_marker=marker_doc,
    )
    decision = (
        cast("AttachDecisionView", ctx.client.ask(match)) if transaction is None else transaction.match(match)
    )
    decision_diags = _diagnostics_from_view(decision.diagnostics)
    for diag in decision_diags:
        _log_warn(ctx, "workspace.checkout.match_diagnostic", code=diag.code, details=diag.details)
    diagnostics.extend(decision_diags)

    target_repo_id: RepositoryId | None = None
    desired_mount_name: str = decision.mount_name or req.mount_name

    if req.repository_id is not None:
        if decision.kind == "refuse":
            code = decision.refuse_code
            reason = (decision.refuse_details or {}).get("reason")
            if code in {ErrorCode.AMBIGUOUS_REFERENCE.value, ErrorCode.NOT_FOUND.value} or (
                code == ErrorCode.CHECKOUT_MISMATCH.value
                and reason
                in {
                    "marker_other_workspace",
                    "marker_other_project",
                    "not_a_git_checkout",
                }
            ):
                _raise_refusal(decision, req.path)
        if (
            decision.kind == "use_marker"
            and decision.repository_id is not None
            and RepositoryId(decision.repository_id) != req.repository_id
        ):
            raise PreconditionFailed(
                ErrorCode.CHECKOUT_MISMATCH,
                "Checkout marker points to a different repository",
                details={
                    "reason": "marker_other_repository",
                    "marker_repository_id": str(decision.repository_id),
                    "requested_repository_id": str(req.repository_id),
                },
            )
        if (
            decision.kind == "use_existing_repository"
            and decision.repository_id is not None
            and RepositoryId(decision.repository_id) != req.repository_id
        ):
            raise PreconditionFailed(
                ErrorCode.CHECKOUT_MISMATCH,
                "Checkout remotes match a different repository",
                details={
                    "reason": "remotes",
                    "matched_repository_id": str(decision.repository_id),
                    "requested_repository_id": str(req.repository_id),
                },
            )
        target_repo_id = req.repository_id
        if target_project_id is None and decision.project_id is not None:
            target_project_id = ProjectId(decision.project_id)
    elif decision.kind == "refuse":
        _raise_refusal(decision, req.path)
    elif decision.kind == "use_marker":
        assert decision.repository_id is not None  # noqa: S101
        assert decision.project_id is not None  # noqa: S101
        target_repo_id = RepositoryId(decision.repository_id)
        target_project_id = ProjectId(decision.project_id)
    elif decision.kind == "use_existing_repository":
        assert decision.repository_id is not None  # noqa: S101
        target_repo_id = RepositoryId(decision.repository_id)
        if decision.project_id is not None:
            target_project_id = ProjectId(decision.project_id)
        if decision.needs_confirmation and not (req.confirm(decision) if req.confirm is not None else False):
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "Confirmation required to bind existing repository matched by remote; pass --yes",
                details={
                    "reason": "confirmation_required",
                    "repository_id": str(target_repo_id),
                    "project_id": None if target_project_id is None else str(target_project_id),
                },
            )
    elif decision.kind == "create_repository":
        if decision.project_id is not None:
            target_project_id = ProjectId(decision.project_id)
        if not req.register_missing:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "No matching repository in workspace; pass --register to register and attach it",
                details={
                    "reason": "repository_not_registered",
                    "canonical_remote": decision.canonical_remote,
                },
            )
    else:
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_MISMATCH,
            f"Unexpected attach decision kind: {decision.kind}",
            details={"kind": decision.kind},
        )

    marker_instance_id: UUID | None = None
    if req.write_marker:
        if target_project_id is None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "Writing a checkout marker requires a project (--project)",
                details={"reason": "project_required_for_marker"},
            )
        marker_instance_id = _resolve_instance_id(ctx, req, observed)

    if target_repo_id is None:
        repo_title = req.title or _default_title(observed.toplevel, decision.canonical_remote)
        reg_remote_url = _resolve_registration_remote_url(
            inspector, observed.toplevel, decision.canonical_remote, timeout_seconds
        )
        reg_result = cast(
            "RegisterRepositoryResult",
            _dispatch(
                ctx,
                transaction,
                step_keys,
                "register_repository",
                RegisterRepository(
                    workspace_id=req.workspace_id,
                    title=repo_title,
                    remote_url=reg_remote_url,
                    external_id=None,
                ),
            ),
        )
        target_repo_id = RepositoryId(reg_result.repository_id)

    if req.repository_id is None and target_project_id is not None:
        target_mount_name = _ensure_mounted(
            ctx, target_project_id, target_repo_id, desired_mount_name, req.role, step_keys, transaction
        )
    bind_result = cast(
        "BindCheckoutResult",
        _dispatch(
            ctx,
            transaction,
            step_keys,
            "bind_checkout",
            BindCheckout(
                repository_id=target_repo_id,
                host_id=ctx.host_id,
                local_locator=locator,
                observed_toplevel=locator,
                observed_remotes=tuple(item.value for item in observed.remotes),
                observed_head=observed.head,
                observed_dirty=observed.dirty,
                observed_at=observed.observed_at,
            ),
        ),
    )
    if req.repository_id is not None and target_project_id is not None:
        target_mount_name = _ensure_mounted(
            ctx, target_project_id, target_repo_id, desired_mount_name, req.role, step_keys, transaction
        )

    if transaction is not None:
        if bind_result.state != "active":
            raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "Project refused the observed checkout")
        if target_project_id is not None and target_mount_name is not None:
            transaction.bound(
                req.workspace_id, target_project_id, target_repo_id, bind_result.binding_id, target_mount_name
            )

    marker_written = False
    if req.write_marker:
        assert target_project_id is not None  # noqa: S101
        assert marker_instance_id is not None  # noqa: S101
        mount_for_marker = target_mount_name or req.mount_name
        marker = CheckoutMarker(
            instance_id=marker_instance_id,
            workspace_id=req.workspace_id,
            project_id=target_project_id,
            repository_id=target_repo_id,
            mount_name=MountName(mount_for_marker),
        )
        inspector.write_marker(observed.toplevel, marker_relpath=marker_relpath, marker=marker)
        marker_written = True

    return BindCheckoutReport(
        binding_id=CheckoutBindingId(bind_result.binding_id),
        workspace_id=req.workspace_id,
        project_id=target_project_id,
        repository_id=target_repo_id,
        mount_name=target_mount_name,
        local_locator=observed.toplevel,
        state=bind_result.state,
        reason=bind_result.reason,
        row_version=bind_result.row_version,
        marker_written=marker_written,
        diagnostics=tuple(diagnostics),
    )


def run(ctx: HostContext, request: BindCheckoutRequest | Mapping[str, Any]) -> BindCheckoutReport:
    return bind_checkout(ctx, request)


SPEC = HostOperationSpec(
    name="workspace.host.bind_checkout",
    run=run,
    request=cast("type[object]", BindCheckoutRequest),
    result=BindCheckoutReport,
    surfaces=cast("frozenset[Any]", frozenset({"cli"})),
)
