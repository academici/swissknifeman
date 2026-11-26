"""Normalize, gather host facts and evaluate built-in hooks through the client."""

from __future__ import annotations

import json
import posixpath
import shlex
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.gateways import host_gateway
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.hook_events import HookEventKind, HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import (
    HookMode,
    HookPolicyContext,
    HookVerdict,
    commit_message,
    evaluate_hook,
    failure_decision,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.ports import IntegrationTargetRegistry, LocalCheckoutProjections

from .hook_state import HookState

if TYPE_CHECKING:
    from skm.kernel.module_manifest import HostOperationSpec
    from skm.modules.integrations.generated.host import EvaluateHookResult

    SPEC: HostOperationSpec

__all__ = ["SPEC", "EvaluateHookOperation", "SessionEndObserver", "run"]

MAX_PAYLOAD_BYTES = 1_048_576


@host_gateway
class SessionEndObserver(Protocol):
    """Admit a session only when the current backend enables learning."""

    def enqueue(self, project: str, checkout: str, session_id: str, transcript: str) -> None: ...


def _observe_session_end(
    ctx: HostContext, event: NormalizedHookEvent, project: str, root: str, payload: dict[str, Any]
) -> None:
    if (
        event.kind is not HookEventKind.SESSION_END
        or event.target is not TargetId.CLAUDE_CODE
        or not event.cwd
        or not ctx.gateways.has(SessionEndObserver)
    ):
        return
    transcript = payload.get("transcript_path")
    if event.session_id is not None and isinstance(transcript, str) and transcript:
        with suppress(Exception):
            ctx.gateways.get(SessionEndObserver).enqueue(project, root, event.session_id, transcript)


def _policy(
    ctx: HostContext, state: HookState, project: str, target: str, timeout: int, *, live: bool
) -> dict[str, Any]:
    getter = getattr(ctx.config, "get", None)
    configured_ttl = getter("integrations.hook.cache_ttl_seconds") if callable(getter) else None
    ttl = int(cast("Any", configured_ttl)) if configured_ttl is not None else None
    cached = None if live else state.load(project, target, ttl)
    if cached is not None:
        return dict(cached)
    from skm.modules.integrations.generated.views import hook_policy_view_from_json

    query = state.query("integrations.get_hook_policy", {"project_id": project, "target": target})
    result = state.call(lambda: ctx.client.ask(query), timeout)
    policy = dict(hook_policy_view_from_json(result))
    if ttl is not None:
        policy["ttl_seconds"] = ttl
    state.save(project, target, policy)
    return policy


_CHECKOUT_DETAILS = frozenset(
    {"checkout_marker_missing", "checkout_marker_mismatch", "checkout_foreign", "checkout_unbound"}
)


def _detail(error: Exception) -> str | None:
    """The stable cause code of a checkout failure; never the message, which may carry local values."""
    detail = getattr(error, "detail", None)
    return detail if isinstance(detail, str) and detail in _CHECKOUT_DETAILS else None


class _CheckoutUnbound(ValueError):
    detail = "checkout_unbound"


def _resolve_bound_checkout(
    ctx: HostContext,
    state: HookState,
    event: NormalizedHookEvent,
    project: str,
    timeout: int,
) -> tuple[str, str, str, str]:
    offline_snapshot = getattr(ctx.client, "cached_snapshot", None)
    if isinstance(offline_snapshot, dict):
        snapshot = cast("dict[str, Any]", offline_snapshot)
        proj = cast("dict[str, Any]", snapshot["project"])
        loc = cast("dict[str, Any]", snapshot["checkout"])
        mount = str(snapshot["mount"])
        if str(proj.get("project_id")) != project or loc.get("state") != "active":
            raise _CheckoutUnbound("hook cwd is not bound to this project and host")
        root = str(loc["local_locator"])
        state.checkout(
            root,
            event.cwd or root,
            project,
            str(loc["binding_id"]),
            str(loc["repository_id"]),
            mount,
        )
        return root, mount, str(loc["repository_id"]), str(proj["slug"])

    from skm.modules.workspace.public import GetProject

    from .observe import resolve_checkout_for_mount

    project_id = ProjectId(UUID(project))
    if ctx.gateways.has(LocalCheckoutProjections) and not event.cwd:
        raise ValueError("native hook cwd is required")
    view: Any = state.call(lambda: ctx.client.ask(GetProject(project_id=project_id)), timeout)
    # Select the mount whose verified checkout contains cwd; no payload mount is authoritative.
    selected: Any = None
    mount = "main"
    refusal: Exception | None = None
    for item in view.mounts:
        try:
            location: Any = state.call(
                lambda name=item.mount_name: resolve_checkout_for_mount(ctx, project_id, name),
                timeout,
            )
            state.checkout(
                location.local_locator,
                event.cwd or location.local_locator,
                project,
                str(location.binding_id),
                str(location.repository_id),
                item.mount_name,
            )
            selected, mount = location, item.mount_name
            break
        except (ValueError, NotFound) as exc:
            refusal = refusal or (exc if _detail(exc) else None)
            continue
        except PreconditionFailed as exc:
            if exc.code not in {ErrorCode.CHECKOUT_UNBOUND, ErrorCode.CHECKOUT_MISMATCH}:
                raise
    if selected is None:
        raise refusal or _CheckoutUnbound("hook cwd is not bound to this project and host")
    state.remember(
        project,
        event.target.value,
        {
            "host_id": str(ctx.host_id),
            "project": view.to_json(),
            "checkout": selected.to_json(),
            "mount": mount,
        },
    )
    return selected.local_locator, mount, str(selected.repository_id), str(view.slug)


def _context(
    ctx: HostContext,
    state: HookState,
    event: NormalizedHookEvent,
    project: str,
    surface: HookSurfaceId,
    mode: HookMode,
    policy: dict[str, Any],
    timeout: int,
) -> HookPolicyContext:
    root, mount, repository_id, slug = _resolve_bound_checkout(ctx, state, event, project, timeout)
    changelog = policy["changelog"]
    context = HookPolicyContext(
        root=root,
        reserved_paths=tuple(policy["reserved_paths"]),
        managed_file_paths=frozenset(state.resolve(path, root) for path in policy["managed_file_paths"]),
        code_globs=tuple(changelog["code_globs"]),
        changelog_paths=tuple(changelog.get("changelog_paths", [changelog["changelog_path"]])),
        skip_marker=changelog["skip_marker"],
        session_context=f"SKM project: {slug}. Use skm inbox for open questions.",
    )
    command = event.command or ""
    if surface in {HookSurfaceId.SESSION_CONTEXT, HookSurfaceId.REVIEW_GATE} and event.kind in {
        HookEventKind.SESSION_START,
        HookEventKind.SUBAGENT_STOP,
    }:
        session, review = _workflow_context(ctx, state, project, event.target.value, timeout)
        context = replace(
            context, session_context=context.session_context + "\n" + session, review_context=review
        )
    if surface is HookSurfaceId.GIT_GUARDRAILS:
        from skm.modules.policy.public import git_guard_check

        violation = git_guard_check(command)
        context = replace(context, git_violation=violation is not None)
        if violation is not None and violation.id == "push-force":
            context = replace(
                context,
                git_reason="GIT_FORCE_PUSH",
                git_message=(
                    "skm git_guardrails: force push without --force-with-lease is blocked; "
                    "use git push --force-with-lease"
                ),
            )
    if surface is HookSurfaceId.SAFE_DIRS and event.kind is HookEventKind.PRE_SHELL:
        from skm.modules.policy.public import (
            Ask,
            Deny,
            EnforcementMode,
            RunCommand,
            ScopeRoots,
            TaskAuthority,
            check_tool_call,
            permission_set_from_view,
        )

        permissions = permission_set_from_view(policy["permissions"])
        result = check_tool_call(
            permissions,
            RunCommand(command, event.cwd),
            roots=ScopeRoots({mount: root}, None, None, state.home, (), (), frozenset()),
            facts=state.facts(root),
            authority=TaskAuthority(None, (), frozenset(), frozenset()),
            mode=EnforcementMode.INTERACTIVE,
        )
        context = replace(
            context,
            safe_verdict="deny" if isinstance(result, Deny) else "ask" if isinstance(result, Ask) else "none",
            safe_reason=result.code if isinstance(result, Deny) else None,
        )
    if surface in {HookSurfaceId.PLAN_GUARD, HookSurfaceId.PACK_GUARD}:
        from skm.modules.policy.public import managed_hit

        protected = (
            tuple(
                posixpath.join(root, path.removesuffix("/**").rstrip("/")) for path in context.reserved_paths
            )
            if surface is HookSurfaceId.PLAN_GUARD
            else ()
        )
        paths = [state.resolve(path, event.cwd) for path in (*event.paths, *shlex.split(command))]
        managed = context.managed_file_paths if surface is HookSurfaceId.PACK_GUARD else frozenset[str]()
        hit = managed_hit([command, *event.paths, *paths], event.cwd, managed, protected_dirs=protected)
        context = replace(context, managed_path=hit)
    if (
        mode is HookMode.OFF
        or event.kind is not HookEventKind.PRE_SHELL
        or commit_message(event.command or "") is None
    ):
        return context
    if surface not in {HookSurfaceId.REVIEW_GATE, HookSurfaceId.CHANGELOG_GATE}:
        return context
    state.verify_commit(command, event.cwd, root)
    if surface is HookSurfaceId.CHANGELOG_GATE:
        from skm.modules.policy.public import GuardMode, changelog_gate_verdict

        message = state.commit_text(command, event.cwd, root)
        gate = changelog_gate_verdict(message, mode=GuardMode.STRICT)
        context = replace(context, commit_text=message, changelog_required=gate.match is not None)
    tree, paths = state.call(lambda: state.staged(root, mount, repository_id), timeout)
    context = replace(context, staged_paths=paths)
    if surface is HookSurfaceId.REVIEW_GATE:
        return _receipt_context(ctx, state, project, mount, repository_id, tree, context, timeout)

    return context


def _subscriptions(
    ctx: HostContext,
    state: HookState,
    event: NormalizedHookEvent,
    project: str,
    policy: dict[str, Any],
    request: dict[str, Any],
    timeout: int,
    started: float | None,
) -> Any:
    from skm.modules.integrations.domain.hook_events import HookClass

    from .host_subscriptions import SubscriptionState, run_host_subscriptions

    cls = HookClass(request.get("class") or "enforcement")
    root, _, _, _ = _resolve_bound_checkout(ctx, state, event, project, timeout)
    local = ctx.gateways.get(SubscriptionState)
    elapsed = 0 if started is None else int((local.monotonic() - started) * 1000)
    return run_host_subscriptions(
        event, cls, {**policy, "project_id": project, "checkout_root": root}, ctx, timeout - elapsed
    )


def _failure(
    request: dict[str, Any],
    surface: HookSurfaceId,
    mode: HookMode,
    reason: str,
    *,
    commit: bool = False,
    detail: str | None = None,
) -> Any:
    decision = failure_decision(surface, mode, reason, commit=commit, detail=detail)
    if surface is HookSurfaceId.SUBSCRIPTIONS and request.get("class") not in {"workflow", "observation"}:
        decision = replace(decision, verdict=HookVerdict.DENY)
    return decision


def run(
    ctx: HostContext, request: dict[str, Any], *, payload_size: int | None = None, live: bool = False
) -> EvaluateHookResult:
    target = TargetId(request["target"])
    surface = HookSurfaceId(request["surface"])
    event_name = str(request["event_name"])
    project = str(request["project_id"])
    adapter = ctx.gateways.get(IntegrationTargetRegistry).get(target)
    event = NormalizedHookEvent(
        target, HookEventKind.PRE_SHELL, None, "", None, "", (), None, None, event_name
    )
    mode = HookMode.STRICT
    started: float | None = None
    if surface is HookSurfaceId.SUBSCRIPTIONS:
        from .host_subscriptions import SubscriptionState

        if ctx.gateways.has(SubscriptionState):
            started = ctx.gateways.get(SubscriptionState).monotonic()
    state: HookState | None = None
    backend_ok = False
    bound_root = ""
    try:
        payload = request["payload"]
        if (
            not isinstance(payload, dict)
            or (
                payload_size
                if payload_size is not None
                else len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            )
            > MAX_PAYLOAD_BYTES
        ):
            raise ValueError("payload must be a bounded object")
        event = adapter.normalize_hook_payload(event_name, cast("Any", payload))
    except Exception:  # noqa: BLE001 - native parsers never leak payload values
        decision = _failure(
            request, surface, mode, "HOOK_PAYLOAD_INVALID", commit=surface is HookSurfaceId.REVIEW_GATE
        )
    else:
        try:
            UUID(project)
            state = ctx.gateways.get(HookState)
            timeout = 2000
            getter = getattr(ctx.config, "get", None)
            if callable(getter):
                timeout = int(cast("Any", getter("integrations.hook.timeout_ms")) or timeout)
            policy = _policy(ctx, state, project, target.value, timeout, live=live)
            modes = policy["hook_modes"]
            key = surface.value.rpartition(".")[2]
            mode = HookMode(modes.get(surface.value, modes.get(key, "strict")))
            if surface is HookSurfaceId.SUBSCRIPTIONS:
                decision = _subscriptions(ctx, state, event, project, policy, request, timeout, started)
            else:
                context = _context(ctx, state, event, project, surface, mode, policy, timeout)
                decision = evaluate_hook(event, surface, mode, context)
                bound_root = context.root
            if mode is not HookMode.OFF and (
                (
                    surface is HookSurfaceId.COMMAND_LOG
                    and event.kind
                    in {HookEventKind.PRE_SHELL, HookEventKind.POST_SHELL, HookEventKind.POST_TOOL}
                )
                or (surface is HookSurfaceId.RUN_REPORT and event.kind is HookEventKind.SESSION_END)
            ):
                state.observe(project, surface.value, event.kind.value, event.session_id)
                _observe_session_end(ctx, event, project, bound_root, cast("dict[str, Any]", payload))
            backend_ok = True
        except Exception as exc:  # noqa: BLE001 - fail closed on backend, config, checkout or IO errors
            commit = event.kind is HookEventKind.PRE_SHELL and commit_message(event.command or "") is not None
            decision = _failure(
                request, surface, mode, "HOOK_BACKEND_UNAVAILABLE", commit=commit, detail=_detail(exc)
            )
    if decision.reason_code and decision.verdict is HookVerdict.NONE:
        warning = getattr(ctx.log, "warning", None)
        if callable(warning):
            warning("integrations.hook_skipped", code=decision.reason_code)
    if decision.verdict is HookVerdict.DENY:
        with suppress(Exception):
            (state or ctx.gateways.get(HookState)).audit(
                project, surface.value, decision.reason_code or "denied"
            )
    if (
        backend_ok
        and state is not None
        and surface is not HookSurfaceId.SUBSCRIPTIONS
        and decision.verdict is not HookVerdict.DENY
        and not getattr(ctx.client, "offline", False)
    ):
        with suppress(Exception):
            state.call(lambda: state.flush(ctx.client), 50)
    client_out = cast("dict[str, Any]", adapter.render_hook_decision(event, decision))
    return cast(
        "EvaluateHookResult",
        {
            "schema": "urn:skm:integrations:host:hook-decision:v1",
            "surface": surface.value,
            "mode": mode.value,
            "verdict": "warn" if decision.verdict is HookVerdict.CONTEXT else decision.verdict.value,
            "reason_code": decision.reason_code,
            "user_message": decision.user_message,
            "agent_message": decision.agent_message,
            "additional_context": decision.additional_context,
            "client_output": {
                "exit_code": int(client_out["exit_code"]),
                "stdout": client_out["stdout"],
                "stderr": str(client_out["stderr"]),
            },
        },
    )


class EvaluateHookOperation:
    name = "integrations.host.evaluate_hook"
    run = staticmethod(run)


def __getattr__(name: str) -> object:
    if name == "SPEC":
        from skm.kernel.module_manifest import HostOperationSpec

        spec = HostOperationSpec(
            name=EvaluateHookOperation.name,
            run=run,
            request=dict,
            result=dict,
            surfaces=cast("Any", frozenset({"cli", "hook"})),
        )
        globals()["SPEC"] = spec
        return spec
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _workflow_context(
    ctx: HostContext, state: HookState, project: str, target: str, timeout: int
) -> tuple[str, str]:
    snapshot = state.snapshot(project, target) or {}
    if getattr(ctx.client, "offline", False):
        workflow = snapshot.get("workflow", {})
        return workflow.get("session", "Run/task context unavailable."), workflow.get(
            "review", "Review findings unavailable."
        )

    def ask(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        result: Any = state.call(lambda: ctx.client.ask(state.query(name, payload)), timeout)
        return result.to_json() if hasattr(result, "to_json") else result

    session, review = "Run/task context unavailable.", "Review findings unavailable."
    with suppress(Exception):
        runs = ask(
            "execution.list_runs",
            {
                "project_id": project,
                "statuses": ["running", "waiting", "paused"],
                "kinds": ["plan", "review_request"],
                "limit": 1,
            },
        )
        session, review = "No active run/task.", "No bound active review task."
        if runs["items"]:
            run_id = runs["items"][0]["run_id"]
            session = f"Current run: {run_id}."
            tasks = ask("execution.list_tasks", {"run_id": run_id})
            if tasks["tasks"]:
                task = next(
                    (task for task in tasks["tasks"] if task.get("status") in {"running", "blocked"}),
                    tasks["tasks"][0],
                )
                session += f" Task: {task['task_id']}."
                detail = ask("execution.get_task", {"task_id": task["task_id"]})
                findings = [
                    finding for finding in detail.get("findings", []) if finding.get("state") == "open"
                ]
                review = (
                    "Open review findings: " + ", ".join(str(finding["finding_id"]) for finding in findings)
                    if findings
                    else "No open review findings."
                )
    with suppress(Exception):
        questions = ask(
            "execution.list_decision_requests",
            {"scope": {"kind": "project", "id": project}, "states": ["open"], "limit": 20},
        )
        session += f" Open inbox questions: {len(questions['items'])}."
    state.remember(project, target, {**snapshot, "workflow": {"session": session, "review": review}})
    return session, review


def _receipt_context(
    ctx: HostContext,
    state: HookState,
    project: str,
    mount: str,
    repository: str,
    tree: str,
    context: HookPolicyContext,
    timeout: int,
) -> HookPolicyContext:
    root = context.root
    query = state.query(
        "execution.get_review_receipt",
        {
            "project_id": project,
            "mount": mount,
            "tree_digest": tree,
        },
    )
    try:
        receipt: Any = state.call(lambda: ctx.client.ask(query), timeout)
    except NotFound:
        return context
    data = receipt.to_json() if hasattr(receipt, "to_json") else receipt
    base, head = data.get("base_commit"), data.get("head_commit")
    if base and head:
        tree = state.call(lambda: state.review_digest(root, mount, repository, base, head), timeout)
    fresh = data["tree_digest"] == tree and data["status"] == "succeeded"
    blockers = any(
        finding.get("severity") == "blocker" and finding.get("state", finding.get("status", "open")) == "open"
        for finding in data["findings"]
    )
    current_tree = (
        state.call(lambda: state.review_digest(root, mount, repository, base, head), timeout)
        if base and head
        else state.call(lambda: state.staged(root, mount, repository), timeout)[0]
    )
    fresh = fresh and current_tree == tree
    context = replace(context, review_fresh=fresh, open_blockers=blockers)
    return context
