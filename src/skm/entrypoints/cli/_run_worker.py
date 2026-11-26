"""CLI worker host-loop composition, credential references and capacity slots."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from skm.bootstrap.worker import build_http_worker, worker_host_from_context
from skm.bootstrap.worker_entrypoint import main as worker_main
from skm.entrypoints.cli._run_io import show
from skm.entrypoints.cli.commands.mcp import serve_stage
from skm.entrypoints.cli.commands.worker import resolve_worker_view, worker_token_path
from skm.entrypoints.cli.context import CliContext, CliOptions, CliSession
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.output import render_waiting
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import WorkerId
from skm.kernel.json_types import JsonObject
from skm.kernel.outcomes import Waiting
from skm.modules.workspace.public import ListWorkersView, RecordWorkerHeartbeat, WorkerView
from skm.platform.config import EffectiveConfig
from skm.platform.config.bootstrap import BootstrapConfig

if TYPE_CHECKING:
    from skm.entrypoints.cli.main import Backend


def http_backend(
    bootstrap: BootstrapConfig,
    options: CliOptions,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
    credential_ref: str | None,
    credential_path: Path | None,
) -> Backend:
    from skm.entrypoints.cli.main import Backend

    if options.actor_hint is not None and credential_ref is None:
        bootstrap = replace(bootstrap, api_credential=options.actor_hint)
    host, client = build_http_worker(
        bootstrap,
        environ=environ,
        credential_ref=credential_ref,
        credential_path=credential_path,
        on_secret=on_secret,
    )
    return Backend(
        client, host_context_factory(host, client), bootstrap.state_dir, bootstrap.instance_id, host.close
    )


def positive_capacity(text: str) -> int:
    try:
        number = int(text)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("capacity must be a positive integer")


def start(args: argparse.Namespace, ctx: CliContext) -> int:  # noqa: PLR0912 - credential/host lifecycle
    from skm.entrypoints.cli.main import production_backend

    host = ctx.host_context()
    worker = resolve_worker_view(ctx, args.worker) if args.worker else None
    if worker is None:
        from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
        from skm.modules.workspace.public import ListWorkers

        after = None
        candidates: list[WorkerView] = []
        while True:
            page = cast(
                "ListWorkersView",
                ctx.client.ask(ListWorkers(workspace_id=resolve_workspace_id(ctx), after=after)),
            )
            candidates.extend(
                item for item in page.items if item.host_id == host.host_id and item.state != "retired"
            )
            after = page.next
            if after is None:
                break
        if len(candidates) != 1:
            raise ValidationFailed(
                ErrorCode.AMBIGUOUS_REFERENCE, "select one registered worker with --worker"
            )
        worker = candidates[0]
    if worker.host_id != host.host_id:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "worker belongs to another host")
    token_ref = args.token
    if token_ref is None and isinstance(ctx, CliSession):
        path = worker_token_path(ctx, WorkerId(worker.worker_id))
        if path.is_file():
            token_ref = "secret://file/" + str(path)
    attached = None
    client = host.client
    try:
        if token_ref:
            from skm.bootstrap.worker_credentials import resolve_worker_credential

            if not isinstance(ctx, CliSession):
                raise ValidationFailed(ErrorCode.CONFIG_INVALID, "worker token needs a CLI session")
            secret = resolve_worker_credential(
                token_ref, environ=ctx.environ, on_reveal=ctx.redactor.register_secret
            )
            attached = production_backend(
                replace(ctx.options, actor_hint=secret),
                ctx.environ,
                ctx.redactor.register_secret,
                worker=True,
                credential_ref=token_ref,
                credential_path=worker_token_path(ctx, WorkerId(worker.worker_id)),
            )
            client = attached.client
            if attached.host_factory is not None:
                host = attached.host_factory()
        client.dispatch(
            RecordWorkerHeartbeat(worker.worker_id, None), idempotency_key=ctx.new_idempotency_key()
        )
        capacity = args.capacity
        if capacity is None:
            capacity = cast("EffectiveConfig", host.config).get("worker.capacity")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "worker.capacity must be a positive integer")
        # --once means one assignment in total, even when configured capacity is larger than one.
        caps = worker.capabilities
        request: JsonObject = {
            "workspace_id": str(worker.workspace_id),
            "host_id": str(worker.host_id),
            "worker_id": str(worker.worker_id),
            "once": bool(args.once),
            "max_assignments": 1 if args.once else 0,
            "offer": {
                "capabilities": [*caps.runtimes, *(f"runtime:{runtime}" for runtime in caps.runtimes)],
                "labels": list(caps.labels),
                "environment_kinds": ["git_worktree"],
                "isolation_profiles": list(caps.isolation_profiles),
            },
        }
        host_services = worker_host_from_context(host)
        completed: list[JsonObject] = []
        worker_main(
            host=host_services,
            client=client,
            request=request,
            capacity=capacity,
            on_result=completed.append,
            stage_mcp=serve_stage,
        )
        result = completed[0]
        results = cast("list[JsonObject]", result["slots"])
        if any(item.get("reason") for item in results):
            show(ctx, "worker.start", result)
            return 6
        if args.once and not any(item.get("assignments") for item in results):
            return render_waiting(
                ctx,
                Waiting(ErrorCode.NOTHING_TO_CLAIM, "no work available"),
                command="execution.claim_assignment",
            )
        return show(ctx, "worker.start", result)
    finally:
        if attached is not None and attached.close is not None:
            attached.close()


__all__ = ["http_backend", "positive_capacity", "start"]
