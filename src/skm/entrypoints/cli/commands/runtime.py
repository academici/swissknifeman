"""``skm runtime`` CLI group (runtimes §14): list, detect, capabilities, models, sync and route."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Final, cast
from uuid import UUID

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, NotFound
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.modules.context.public import DelegationCompiler
from skm.modules.runtimes import public as runtimes

__all__ = ["GROUP", "register", "register_route_args", "route_pick"]

_HELP: Final = {
    "list": "list registered runtimes and observed host installations",
    "detect": "detect runtimes installed on the current host",
    "capabilities": "show effective capabilities of a runtime",
    "models": "list resolved catalog models with context windows and pricing",
    "sync": "stage model catalog candidates from external inventories without activating them",
    "route": "explain admission and routing for a role",
}
_COMMAND: Final = {
    "list": "runtimes.list_runtimes",
    "detect": "runtimes.host.detect_runtimes",
    "capabilities": "runtimes.get_capabilities",
    "models": "runtimes.list_models",
    "sync": "runtimes.catalog_sync",
    "route": "runtimes.explain_routing",
}


def _scope_dto(args: argparse.Namespace, ctx: CliContext) -> JsonObject:
    raw_scope = getattr(args, "scope", None)
    try:
        scope = ctx.resolve_scope(raw_scope)
        return {"kind": scope.kind.value, "id": str(scope.id)}
    except CapabilityUnavailable as err:
        if err.details.get("kind") != "instance":
            raise
    view = ctx.client.ask(access.WhoAmI())
    assert isinstance(view, access.WhoAmIView)  # noqa: S101 - validated by the bus
    for membership in view.memberships:
        if membership.scope_kind == "instance":
            return {"kind": "instance", "id": str(membership.scope_id)}
    raise NotFound(
        ErrorCode.NOT_FOUND,
        "the instance scope is known to its members only; pass --scope workspace:<uuid>",
        details={"kind": "scope"},
    )


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {}
    if args.host is not None:
        payload["host_id"] = str(ctx.resolve_host(args.host))
    raw = ctx.client.ask(runtimes.ListRuntimes.from_json(payload))
    items: tuple[runtimes.RuntimesViewItem, ...]
    if isinstance(raw, runtimes.ListRuntimesResult):
        items = raw.items
    elif isinstance(raw, list | tuple):
        items = tuple(cast("tuple[runtimes.RuntimesViewItem, ...]", raw))
    else:
        raise TypeError(f"unexpected list_runtimes result {type(raw).__name__}")

    def human(value: tuple[runtimes.RuntimesViewItem, ...]) -> list[str]:
        if not value:
            return ["no runtimes registered"]
        rows = [
            [
                item.runtime_id,
                "yes" if item.registered else "no",
                item.adapter_version,
                "yes" if item.allowed_in_scope else "no",
                len(item.installations),
            ]
            for item in value
        ]
        return render_table(ctx, ("runtime", "registered", "adapter", "allowed", "installs"), rows)

    return render(
        ctx,
        list(items),
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(item.runtime_id for item in value),
    )


def _detect(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.bootstrap.runtime_detection import run_runtime_detection

    report = run_runtime_detection(build_host_context(ctx), ctx.redactor.text)

    def human(value: runtimes.DetectRuntimesReport) -> list[str]:
        if not value.runtimes and not value.removed:
            return [f"host {value.host_id}: no runtimes detected"]
        rows = [
            [
                item.runtime_id,
                item.version or "-",
                item.auth_state,
                "changed" if item.changed else "unchanged",
            ]
            for item in value.runtimes
        ]
        lines = render_table(ctx, ("runtime", "version", "auth", "state"), rows) if rows else []
        if value.removed:
            lines.append(f"removed: {', '.join(value.removed)}")
        return lines

    return render(
        ctx,
        report,
        human=human,
        command=args.command_name,
        essential=lambda value: str(value.host_id),
    )


def _capabilities(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"runtime_id": args.runtime_id}
    if args.version is not None:
        payload["runtime_version"] = args.version
    view = ctx.client.ask(runtimes.GetCapabilities.from_json(payload))
    assert isinstance(view, runtimes.RuntimeCapabilitiesView)  # noqa: S101 - validated by the bus

    def human(value: runtimes.RuntimeCapabilitiesView) -> list[str]:
        rows = [
            [
                rec.capability.value,
                rec.status,
                rec.source,
                rec.tested_runtime_version or "-",
                rec.last_verified_at.isoformat() if rec.last_verified_at is not None else "-",
            ]
            for rec in value.records
        ]
        header = [f"{value.runtime_id} (adapter {value.adapter_version})"]
        if not rows:
            return [*header, "no capabilities declared"]
        return [*header, *render_table(ctx, ("capability", "status", "source", "version", "verified"), rows)]

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: value.runtime_id,
    )


def _https_transport() -> tuple[runtimes.CatalogTransport, Mapping[str, str]]:  # runtime provider map
    """The process HTTPS transport. Tests replace this function; the job itself stays offline."""
    from skm.bootstrap.catalog_transport import PROVIDER_RUNTIME, HttpsCatalogTransport

    return HttpsCatalogTransport(), PROVIDER_RUNTIME


def _sync(args: argparse.Namespace, ctx: CliContext) -> int:
    """Stage candidates. Fetch runs before any unit of work; nothing is activated."""
    from skm.platform.system_clock import SystemClock

    transport, providers = _https_transport()
    report = runtimes.ModelCatalogSyncJob(
        transport=transport, today=SystemClock().now().date(), provider_runtimes=providers
    ).run()

    def human(value: runtimes.CatalogSyncReport) -> list[str]:
        lines = [f"staged {len(value.staged)} candidates; {len(value.pending)} awaiting activation"]
        lines.extend(f"{source.value}: {message}" for source, message in value.source_errors)
        return lines

    return render(
        ctx,
        report,
        human=human,
        command=args.command_name,
        essential=lambda value: str(len(value.pending)),
    )


def _models(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {}
    if args.runtime is not None:
        payload["runtime_id"] = args.runtime
    if args.model_class is not None:
        payload["model_class"] = args.model_class
    if args.prepare_for is not None:
        payload["prepare_for"] = args.prepare_for
    view = ctx.client.ask(runtimes.ListModels.from_json(payload))
    assert isinstance(view, runtimes.ModelsView)  # noqa: S101 - validated by the bus
    if args.prepare_for is not None:
        profile = view.models[0].get("guideline") if view.models else None
        if profile is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, "no guideline for target model", details={"model": args.prepare_for}
            )
        brief = DelegationCompiler(
            args.prepare_for,
            tuple(profile["strengths"]),
            tuple(profile["delegation_notes"]),
            profile["prompt_style"]["shape"],
            tuple(profile["prompt_style"]["instructions"]),
            tuple(profile["forbidden_params"]),
        ).compile()
        return render(ctx, brief, human=str.splitlines, command=args.command_name, essential=str)

    def human(value: runtimes.ModelsView) -> list[str]:
        if not value.models:
            return [f"catalog {value.catalog_version}: no matching models"]
        rows: list[list[object]] = []
        for model in value.models:
            raw_classes = model.get("classes")
            cls_str = (
                ",".join(str(c) for c in cast("list[object]", raw_classes))
                if isinstance(raw_classes, list)
                else "-"
            )
            raw_pricing = model.get("pricing")
            if isinstance(raw_pricing, Mapping):
                p_map = cast("Mapping[str, object]", raw_pricing)
                price_str = f"{p_map.get('input_per_mtok_usd')}/{p_map.get('output_per_mtok_usd')}"
            else:
                price_str = "unverified"
            rows.append(
                [
                    model.get("runtime_id", "-"),
                    model.get("id", "-"),
                    cls_str,
                    model.get("context_window_tokens", "-"),
                    price_str,
                    model.get("status", "-"),
                ]
            )
        lines = render_table(
            ctx, ("runtime", "model", "classes", "context", "usd/mtok(in/out)", "status"), rows
        )
        if value.stale:
            lines.append(f"note: catalog {value.catalog_version} has stale entries")
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: value.catalog_digest,
    )


def route_pick(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {
        "role": args.role,
        "scope": _scope_dto(args, ctx),
    }
    if args.host is not None:
        payload["host_id"] = str(ctx.resolve_host(args.host))
    if args.model_class is not None:
        payload["model_class"] = args.model_class
    view = ctx.client.ask(runtimes.ExplainRouting.from_json(payload))
    assert isinstance(view, runtimes.RouteExplainView)  # noqa: S101 - validated by the bus

    def human(value: runtimes.RouteExplainView) -> list[str]:
        pairs: list[tuple[str, object]] = [("role", value.role.value)]
        if value.host_id is not None:
            pairs.append(("host", UUID(str(value.host_id))))
        if value.decision is not None:
            dec = value.decision
            pairs.extend(
                [
                    ("runtime", dec.get("runtime_id")),
                    ("model", dec.get("model")),
                    ("class", dec.get("model_class")),
                    ("effort", dec.get("effort")),
                    ("source", dec.get("source")),
                    ("config mode", dec.get("config_mode")),
                ]
            )
        elif value.error is not None:
            pairs.append(("error", f"{value.error.code}: {value.error.message}"))
        lines = kv_lines(ctx, pairs)
        if value.rejected:
            rej_rows = [
                [
                    r.get("runtime_id", "-"),
                    r.get("model") or "-",
                    r.get("source", "-"),
                    r.get("reason", "-"),
                ]
                for r in value.rejected
            ]
            table_lines = render_table(ctx, ("rejected runtime", "model", "source", "reason"), rej_rows)
            lines.extend(["", *table_lines])
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: (
            str(value.decision.get("runtime_id", "")) if value.decision is not None else ""
        ),
    )


def register_route_args(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "role",
        choices=(
            "scout",
            "executor",
            "reviewer",
            "triager",
            "advisor",
            "researcher",
            "registrar",
        ),
        metavar="ROLE",
        help="agent role",
    )
    command.add_argument("--scope", default=argparse.SUPPRESS, metavar="S", help="target scope")
    command.add_argument("--host", metavar="H", help="host id for installation/auth checks")
    command.add_argument(
        "--class",
        dest="model_class",
        choices=("economy", "implementation", "frontier"),
        metavar="C",
        help="requested model class",
    )


_RUN: Final = {
    "list": _list,
    "detect": _detect,
    "capabilities": _capabilities,
    "models": _models,
    "sync": _sync,
    "route": route_pick,
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("runtime", help="inspect runtimes, models, capabilities and routing")
    verbs = parser.add_subparsers(dest="runtime_verb", required=True)
    for verb in ("list", "detect", "capabilities", "models", "sync", "route"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "list":
            command.add_argument("--host", metavar="H", help="filter installations to one host")
        elif verb == "capabilities":
            command.add_argument("runtime_id", metavar="RUNTIME", help="registered runtime id")
            command.add_argument("--version", metavar="V", help="evaluate against a runtime version")
        elif verb == "models":
            command.add_argument("--runtime", metavar="R", help="filter to one runtime id")
            selection = command.add_mutually_exclusive_group()
            selection.add_argument(
                "--prepare-for", metavar="MODEL", help="render the target model delegation brief"
            )
            selection.add_argument(
                "--class",
                dest="model_class",
                choices=("economy", "implementation", "frontier"),
                metavar="C",
                help="model class",
            )
        elif verb == "route":
            register_route_args(command)


GROUP = CommandGroup(
    "runtime",
    "inspect runtimes, models, capabilities and routing",
    register,
    module="runtimes",
    order=65,
)
