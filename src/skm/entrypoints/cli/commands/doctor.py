"""Read-only integration diagnostics (cli §6.12, integrations §14)."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import render, render_table, safe_text
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.execution.public import ExplainAutopilot
from skm.modules.integrations.public import TargetId

__all__ = ["GROUP", "add_parser", "register", "run_host_operation"]


def run_host_operation(ctx: CliContext, name: str, request: JsonObject) -> object:
    spec = next(
        (
            op
            for manifest in MANIFESTS
            if manifest.id == "integrations"
            for op in manifest.host_operations
            if op.name == name
        ),
        None,
    )
    if spec is None or Surface.CLI not in spec.surfaces:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "Integration host operation is unavailable", details={"operation": name}
        )
    return spec.run(build_host_context(ctx), request)


COMMAND = "integrations.host.run_doctor"
HELP = "inspect integration layers, ownership and hook trust"


def _campaign(ctx: CliContext, project_id: str, *, strict: bool) -> int:
    view = cast("Mapping[str, Any]", ctx.client.ask(ExplainAutopilot(project_id=project_id)))
    status = view["status"]
    checks: list[tuple[str, str, str]] = []
    if status["emergency"]:
        checks.append(("autopilot.emergency", "error", "Emergency stop is active"))
    if status["effective_state"] != "disabled":
        checks.extend(
            ("autopilot.queue", "warning", f"{row['ref']} is {row['status']}")
            for row in status["queue"]
            if row["status"] not in {"ready", "ready_with_advisories", "complete"}
        )
        checks.extend(
            ("autopilot." + row["id"], "error", row["code"])
            for row in view["stop_conditions"]
            if row["met"] and row["id"] in {"AP10", "AP11", "AP14", "AP15", "AP19"}
        )
    if not checks:
        checks.append(("autopilot.state", "ok", status["effective_state"]))
    render(
        ctx,
        {
            "project_id": project_id,
            "checks": [
                {"check_id": name, "level": level, "detail": detail} for name, level, detail in checks
            ],
        },
        command="execution.explain_autopilot",
        human=lambda _: render_table(ctx, ("check", "level", "detail"), checks),
    )
    return int(any(level == "error" or (strict and level == "warning") for _, level, _ in checks))


def _offline(args: argparse.Namespace, ctx: CliSession) -> JsonObject:
    from skm.bootstrap.instance_profiles import verified_config
    from skm.bootstrap.projection_wiring import offline_projection_doctor

    if args.autopilot:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Offline diagnostics require integration targets")
    catalog = ctx.profile_catalog()
    cwd = Path.cwd()
    name = catalog.select(ctx.options.instance, cwd)
    config = verified_config(catalog.config(name), name, ctx.environ, ctx.redactor.register_secret)
    return offline_projection_doctor(config, cwd, args.project, args.targets)


def _run(args: argparse.Namespace, ctx: CliSession) -> int:
    report: Mapping[str, Any]
    if args.offline:
        report = _offline(args, ctx)
    else:
        payload: JsonObject = {"project_id": str(resolve_project_id(ctx, args.project))}
        if args.autopilot:
            return _campaign(ctx, str(payload["project_id"]), strict=args.strict)
        if args.targets:
            payload["targets"] = args.targets
        report = cast("Mapping[str, Any]", run_host_operation(ctx, COMMAND, payload))

    def human(value: Mapping[str, Any]) -> list[str]:
        rows = [
            [
                item["target"],
                item["check_id"],
                item["level"],
                item["title"],
                item.get("path") or "-",
                item["detail"],
                item.get("hint") or "-",
            ]
            for item in value["checks"]
        ]
        lines = [
            safe_text(
                ctx,
                f"project: {value['project_id']}; host: {value.get('host_id', '-')}; "
                f"targets: {', '.join(value['targets'])}",
            )
        ]
        lines.extend(render_table(ctx, ("target", "check", "level", "title", "path", "detail", "hint"), rows))
        lines.append(
            safe_text(
                ctx,
                "status: "
                + str(value["status"])
                + "; "
                + ", ".join(f"{key}={count}" for key, count in value["counts"].items()),
            )
        )
        return "\n".join(lines).splitlines()

    render(ctx, report, human=human, command="integrations.host.run_doctor")
    counts = cast("Mapping[str, int]", report["counts"])
    return int(counts.get("error", 0) > 0 or (args.strict and counts.get("warning", 0) > 0))


def add_parser(sub: SubParsers) -> None:
    parser = sub.add_parser("doctor", help=HELP)
    parser.set_defaults(run=_run, command_name=COMMAND)
    parser.add_argument("--project", default=None, help="project reference (defaults to active)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--autopilot", action="store_true", help="check campaign queue, authority, budget and recovery"
    )
    mode.add_argument(
        "--target",
        dest="targets",
        action="append",
        choices=[t.value for t in TargetId],
        help="integration target (repeatable; defaults to configured targets)",
    )
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true", help="exit 1 for warnings as well as errors")
    parser.add_argument("--offline", action="store_true", help="inspect native layers in the local checkout")


def register(sub: SubParsers) -> None:
    add_parser(sub)


GROUP = CommandGroup(
    name="doctor",
    help="inspect integration health without changing files",
    register=register,
    module="integrations",
    order=86,
)
