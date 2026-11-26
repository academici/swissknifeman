"""Replay observation failures under a host lock, checking fresh policy and authority on every attempt."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.ids import ProjectId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.hook_subscriptions import Backoff, RetrySpec, next_attempt_at
from skm.modules.integrations.generated.host import DrainHookSpoolResult
from skm.modules.workspace.public import GetProject, ProjectView

from .host_subscriptions import SubscriptionState, load_policy, run_one, setting
from .observe import resolve_checkout_for_mount

__all__ = ["SPEC", "run"]


def _attempt(ctx: HostContext, key: str, document: dict[str, Any]) -> tuple[str, float]:
    state = ctx.gateways.get(SubscriptionState)
    data = document["input"]
    policy = load_policy(ctx, data["project_id"], data["target"])
    sub = next((sub for sub in policy.get("subscriptions", ()) if sub["id"] == data["subscription_id"]), None)
    if (
        sub is None
        or sub["digest"] != document["digest"]
        or sub["class"] != "observation"
        or sub["failure_policy"] != "retry"
        or data["host_id"] != str(ctx.host_id)
        or setting(ctx, "hooks.host.trusted", {}).get(sub["id"]) != sub["digest"]
    ):
        state.replace(key, None)
        return "dropped", 0
    attempts, retry = int(document["attempts"]), sub["retry"]
    if attempts >= retry["max_attempts"]:
        state.replace(key, None)
        state.audit(
            {
                "subscription_id": sub["id"],
                "digest": sub["digest"],
                "status": "dead",
                "occurred_at": state.now().isoformat(),
            }
        )
        return "dead", 0
    delay = (datetime.fromisoformat(document["available_at"]) - state.now()).total_seconds()
    if delay > 0:
        return "waiting", delay
    root = document.get("checkout_root")
    if root is not None:
        project_id = ProjectId(UUID(data["project_id"]))
        project = ctx.client.ask(GetProject(project_id))
        assert isinstance(project, ProjectView)  # noqa: S101
        for mount in project.mounts:
            try:
                location = resolve_checkout_for_mount(ctx, project_id, mount.mount_name)
            except NotFound:
                continue
            except PreconditionFailed as exc:
                if exc.code not in {ErrorCode.CHECKOUT_UNBOUND, ErrorCode.CHECKOUT_MISMATCH}:
                    raise
                continue
            if root == location.local_locator:
                break
        else:
            state.replace(key, None)
            return "dropped", 0
    outcome = run_one(ctx, sub, data, sub["timeout_ms"], checkout_root=root)
    if outcome.status.value == "ok":
        state.replace(key, None)
        return "replayed", 0
    if outcome.status.value == "untrusted":
        state.replace(key, None)
        return "dropped", 0
    attempts += 1
    if attempts >= retry["max_attempts"]:
        state.audit(
            {
                "subscription_id": sub["id"],
                "digest": sub["digest"],
                "status": "dead",
                "occurred_at": state.now().isoformat(),
            }
        )
        state.replace(key, None)
        return "replayed_dead", 0
    backoff = retry["backoff"]
    next_at = next_attempt_at(
        RetrySpec(retry["max_attempts"], Backoff(**backoff)), attempt=attempts, now=state.now(), jitter=1.0
    )
    state.replace(key, {**document, "attempts": attempts, "available_at": next_at.isoformat()})
    return "replayed", 0


def run(ctx: HostContext, request: object) -> DrainHookSpoolResult:
    del request
    state = ctx.gateways.get(SubscriptionState)
    counts = {"replayed": 0, "dead": 0, "dropped": 0}
    with state.locked() as acquired:
        if not acquired:
            return cast("Any", counts)
        while pending := state.pending():
            waits: list[float] = []
            for key, document in pending:
                ctx.cancel.raise_if_cancelled()
                try:
                    status, delay = _attempt(ctx, key, document)
                except Exception:  # noqa: BLE001 - preserve work across backend outages, without secret text
                    return cast("Any", counts)
                if status == "waiting":
                    waits.append(delay)
                elif status == "replayed_dead":
                    counts["replayed"] += 1
                    counts["dead"] += 1
                else:
                    counts[status] += 1
            if waits:
                ctx.cancel.wait(min(waits))
    return cast("Any", counts)


SPEC = HostOperationSpec(
    "integrations.host.drain_hook_spool", run, dict, dict, cast("Any", frozenset({"cli", "hook"}))
)
