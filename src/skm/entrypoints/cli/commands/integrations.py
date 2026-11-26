"""``skm integrations`` (cli §6, integrations §14): plan, apply, drift, adopt, remove and list projections."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import CLI_EXIT, render, render_table, safe_text
from skm.kernel.error_codes import ErrorCategory, ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ports_uow import Surface
from skm.modules.integrations import public as integrations

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.ids import WorkspaceId
    from skm.kernel.json_types import JsonObject
    from skm.modules.workspace import public as workspace

__all__ = ["GROUP", "register", "sync_checkout_projections"]

_HELP: Final = {
    "plan": "compute projection plan without modifying checkout files",
    "apply": "apply planned integration files to the local checkout",
    "drift": "detect and record drift between checkout files and applied ownership",
    "adopt": "adopt an unmanaged checkout file and capture its pre-image",
    "remove": "remove or cut owned integration spans from the local checkout",
    "list": "list recorded integration projections for a project",
    "untrack-service-files": "remove SKM service files from the Git index while keeping local copies",
}

_COMMAND: Final = {
    "plan": "integrations.host.plan_projection",
    "apply": "integrations.host.apply_projection",
    "drift": "integrations.host.detect_drift",
    "adopt": "integrations.host.adopt_file",
    "remove": "integrations.host.remove_projection",
    "list": "integrations.list_projections",
    "untrack-service-files": "integrations.host.untrack_service_files",
}


def _run_host_op(ctx: CliContext, name: str, request: JsonObject) -> object:
    host_ctx = build_host_context(ctx)
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
            ErrorCode.INTERNAL_ERROR,
            f"host operation {name} is not registered for CLI",
            details={"operation": name},
        )
    return spec.run(host_ctx, request)


def _format_plan_lines(ctx: CliContext, plans: Sequence[Mapping[str, Any]]) -> list[str]:
    rows: list[list[object]] = []
    for plan in plans:
        target = str(plan.get("target", "-"))
        for dec in cast("Sequence[Mapping[str, Any]]", plan.get("decisions", ())):
            bnd = cast("Mapping[str, Any]", dec.get("boundary", {}))
            rows.append(
                [
                    target,
                    dec.get("relative_path", "-"),
                    bnd.get("ownership", "-"),
                    dec.get("decision", "-"),
                ]
            )
    if not rows:
        return ["nothing to project (plan only)"]
    lines = render_table(ctx, ("target", "path", "ownership", "decision"), rows)
    lines.append(safe_text(ctx, f"{len(rows)} file(s), nothing written (plan only)"))
    return lines


def _plan(args: argparse.Namespace, ctx: CliContext) -> int:
    project_id = resolve_project_id(ctx, args.project)
    payload: JsonObject = {
        "project_id": str(project_id),
        "force_conflicts": bool(args.force_conflicts),
    }
    if args.mount is not None:
        payload["mount"] = args.mount
    if args.targets:
        payload["targets"] = list(args.targets)

    plans = cast("list[dict[str, Any]]", _run_host_op(ctx, _COMMAND["plan"], payload))
    return render(
        ctx,
        plans,
        human=lambda value: _format_plan_lines(ctx, value),
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.get("plan_digest", "")) for item in value),
    )


def _needs_apply_confirmation(plans: Sequence[Mapping[str, Any]], *, force_conflicts: bool) -> bool:
    if force_conflicts:
        return True
    for plan in plans:
        for dec in cast("Sequence[Mapping[str, Any]]", plan.get("decisions", ())):
            if str(dec.get("decision")) in ("conflict_write_new", "remove_owned"):
                return True
    return False


def _apply(args: argparse.Namespace, ctx: CliContext) -> int:
    project_id = resolve_project_id(ctx, args.project)
    plan_payload: JsonObject = {
        "project_id": str(project_id),
        "force_conflicts": bool(args.force_conflicts),
    }
    if args.mount is not None:
        plan_payload["mount"] = args.mount
    if args.targets:
        plan_payload["targets"] = list(args.targets)

    plans = cast("list[dict[str, Any]]", _run_host_op(ctx, _COMMAND["plan"], plan_payload))
    if (
        _needs_apply_confirmation(plans, force_conflicts=bool(args.force_conflicts))
        and not getattr(args, "yes", False)
        and not ctx.assume_yes
    ):
        if not ctx.json and not ctx.quiet:
            for line in _format_plan_lines(ctx, plans):
                ctx.stderr.write(line + "\n")
        if not ctx.confirm("Apply integration changes with conflicts or removals?"):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "Confirmation required; pass --yes to confirm",
                details={"reason": "confirmation_required", "project_id": str(project_id)},
            )

    apply_payload: JsonObject = {
        "plans": cast("list[Any]", plans),
        "restore_pre_image": bool(args.restore_pre_image),
    }
    outcomes = cast("list[dict[str, Any]]", _run_host_op(ctx, _COMMAND["apply"], apply_payload))

    def human(value: list[dict[str, Any]]) -> list[str]:
        if not value:
            return ["no targets selected"]
        lines: list[str] = []
        for item in value:
            written = cast("list[str]", item.get("written", []))
            conflicts = cast("list[str]", item.get("conflicts", []))
            failed = cast("list[list[str]]", item.get("failed", []))
            lines.append(
                f"applied {item['target']}: {len(written)} written, "
                f"{len(conflicts)} conflict(s), {len(failed)} failed "
                f"(state {item['state']}, projection {item['projection_id']})"
            )
            lines.extend(
                f"conflict  {cpath} -> merge manually, then `skm integrations adopt {cpath}`"
                for cpath in conflicts
            )
            lines.extend(f"failed    {fpair[0]} ({fpair[1]})" for fpair in failed if len(fpair) == 2)
        return lines

    render(
        ctx,
        outcomes,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item["projection_id"]) for item in value),
    )
    has_issues = any(
        item.get("state") in ("drifted", "failed") or bool(item.get("conflicts")) or bool(item.get("failed"))
        for item in outcomes
    )
    return CLI_EXIT[ErrorCategory.PRECONDITION] if has_issues else 0


def _drift(args: argparse.Namespace, ctx: CliContext) -> int:
    project_id = resolve_project_id(ctx, args.project)
    payload: JsonObject = {"project_id": str(project_id)}
    if args.mount is not None:
        payload["mount"] = args.mount
    if args.targets:
        payload["targets"] = list(args.targets)

    reports = cast("list[dict[str, Any]]", _run_host_op(ctx, _COMMAND["drift"], payload))

    def human(value: list[dict[str, Any]]) -> list[str]:
        rows: list[list[object]] = []
        for rep in value:
            target = rep.get("target", "-")
            rows.extend(
                [
                    target,
                    fitem.get("relative_path", "-"),
                    fitem.get("decision", "-"),
                    fitem.get("diagnostic") or "-",
                ]
                for fitem in cast("Sequence[Mapping[str, Any]]", rep.get("files", ()))
            )
        if not rows:
            return ["no drift detected"]
        lines = render_table(ctx, ("target", "path", "decision", "diagnostic"), rows)
        lines.append(safe_text(ctx, f"drift detected ({len(rows)} file(s))"))
        return lines

    render(
        ctx,
        reports,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(f"{rep['target']}:{rep.get('drifted', 0)}" for rep in value),
    )
    has_drift = any(int(cast("int", rep.get("drifted", 0))) > 0 for rep in reports)
    return CLI_EXIT[ErrorCategory.PRECONDITION] if has_drift else 0


def _adopt(args: argparse.Namespace, ctx: CliContext) -> int:
    project_id = resolve_project_id(ctx, args.project)
    if (
        not getattr(args, "yes", False)
        and not ctx.assume_yes
        and not ctx.confirm(f"Adopt unmanaged file {args.path} for {args.target} in project {project_id}?")
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Confirmation required; pass --yes to confirm",
            details={"reason": "confirmation_required", "project_id": str(project_id)},
        )
    payload: JsonObject = {
        "project_id": str(project_id),
        "target": args.target,
        "relative_path": args.path,
        "reason": args.reason,
    }
    if args.mount is not None:
        payload["mount"] = args.mount

    outcome = cast("dict[str, Any]", _run_host_op(ctx, _COMMAND["adopt"], payload))
    return render(
        ctx,
        outcome,
        human=lambda value: [
            f"adopted {value['relative_path']} for {value['target']} "
            f"(pre-image {value['pre_image_file_version_id']}, projection {value['projection_id']})"
        ],
        command=args.command_name,
        essential=lambda value: str(value["projection_id"]),
    )


def _remove(args: argparse.Namespace, ctx: CliContext) -> int:
    project_id = resolve_project_id(ctx, args.project)
    if (
        not getattr(args, "yes", False)
        and not ctx.assume_yes
        and not ctx.confirm(f"Remove integration projection {args.target} for project {project_id}?")
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "Confirmation required; pass --yes to confirm",
            details={"reason": "confirmation_required", "project_id": str(project_id)},
        )

    payload: JsonObject = {
        "project_id": str(project_id),
        "target": args.target,
        "restore_pre_image": bool(args.restore_pre_image),
    }
    if args.mount is not None:
        payload["mount"] = args.mount

    outcome = cast("dict[str, Any]", _run_host_op(ctx, _COMMAND["remove"], payload))
    render(
        ctx,
        outcome,
        human=lambda value: [
            f"removed {value['target']}: {len(cast('list[str]', value.get('written', [])))} cleaned, "
            f"{len(cast('list[str]', value.get('left_modified', [])))} left modified, "
            f"{len(cast('list[list[str]]', value.get('failed', [])))} failed "
            f"(state {value['state']}, projection {value['projection_id']})"
        ],
        command=args.command_name,
        essential=lambda value: str(value["projection_id"]),
    )
    has_issues = (
        outcome.get("state") == "failed" or bool(outcome.get("failed")) or bool(outcome.get("left_modified"))
    )
    return CLI_EXIT[ErrorCategory.PRECONDITION] if has_issues else 0


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.bootstrap.projection_wiring import list_host_projections

    project_id = resolve_project_id(ctx, args.project)
    query = integrations.ListProjections(project_id=project_id, after=args.after, limit=args.limit)
    view = (
        list_host_projections(build_host_context(ctx), query)
        if getattr(ctx, "machine_store", None) is not None
        else cast("integrations.ProjectionsView", ctx.client.ask(query))
    )

    def human(value: integrations.ProjectionsView) -> list[str]:
        if not value.items:
            return ["no projections"]
        rows = [
            [
                item.projection_id,
                item.target,
                item.state,
                item.checkout_binding_id,
                item.row_version,
            ]
            for item in value.items
        ]
        lines = render_table(ctx, ("projection_id", "target", "state", "binding_id", "version"), rows)
        if value.has_more and value.next_cursor is not None:
            lines.append(safe_text(ctx, f"next: {value.next_cursor} (use --after)"))
        return lines

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.projection_id) for item in value.items),
    )


def _untrack(args: argparse.Namespace, ctx: CliContext) -> int:
    payload: JsonObject = {"project_id": str(resolve_project_id(ctx, args.project))}
    if args.mount is not None:
        payload["mount"] = args.mount
    result = cast(
        "dict[str, list[str]]",
        _run_host_op(ctx, _COMMAND["untrack-service-files"], payload),
    )
    return render(
        ctx,
        result,
        human=lambda value: (
            [f"untracked {path}" for path in value["untracked"]] or ["no SKM service files are tracked"]
        ),
        command=args.command_name,
        essential=lambda value: "\n".join(value["untracked"]),
    )


def sync_checkout_projections(
    ctx: CliContext,
    command: str,
    workspace_id: WorkspaceId,
    *,
    project: workspace.ProjectView | None = None,
    workspace_slug: str | None = None,
) -> int:
    scope_id = workspace_id if project is None else project.project_id
    result = cast(
        "dict[str, Any]",
        _run_host_op(
            ctx, command, {"scope": "workspace" if project is None else "project", "scope_id": str(scope_id)}
        ),
    )
    has_issues = any(
        item["state"] in ("drifted", "failed") or item["conflicts"] or item["failed"]
        for checkout in result["checkouts"]
        for item in checkout["outcomes"]
    )
    if project is not None and not has_issues:
        ctx.save_context(
            workspace_id=str(workspace_id),
            workspace_slug=workspace_slug,
            project_id=str(project.project_id),
            project_slug=project.slug,
        )

    def human(value: dict[str, Any]) -> list[str]:
        lines = [f"activated project {project.slug}"] if project is not None and not has_issues else []
        for checkout in value["checkouts"]:
            lines.append(f"synced {checkout['project_id']}/{checkout['mount']}")
            for item in checkout["outcomes"]:
                lines.append(f"  {item['target']} {item['state']}")
                lines.extend(f"  conflict {path}" for path in item["conflicts"])
                lines.extend(f"  failed {path} ({code})" for path, code in item["failed"])
        return lines or ["no local checkouts to sync"]

    render(ctx, result, human=human, command=command, essential=lambda _value: str(scope_id))
    return CLI_EXIT[ErrorCategory.PRECONDITION] if has_issues else 0


_HANDLERS: Final = {
    "plan": _plan,
    "apply": _apply,
    "drift": _drift,
    "adopt": _adopt,
    "remove": _remove,
    "list": _list,
    "untrack-service-files": _untrack,
}


def register(sub: SubParsers) -> None:
    """Register ``skm integrations`` subcommands."""
    parser = sub.add_parser("integrations", help="project, reconcile and inspect client integration files")
    verbs = parser.add_subparsers(dest="integrations_verb", required=True)
    from .budget import add_parser as add_budget
    from .doctor import add_parser as add_doctor

    add_doctor(verbs)
    add_budget(verbs)
    for verb in ("plan", "apply", "drift", "adopt", "remove", "list", "untrack-service-files"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_HANDLERS[verb], command_name=_COMMAND[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        if verb == "adopt":
            command.add_argument("path", help="checkout-relative file path to adopt")
        command.add_argument("--project", default=None, help="project reference (defaults to active)")
        if verb in ("plan", "apply", "drift", "adopt", "remove", "untrack-service-files"):
            command.add_argument("--mount", default=None, help="checkout mount name (defaults to main)")
        if verb in ("plan", "apply", "drift"):
            command.add_argument(
                "--target",
                dest="targets",
                action="append",
                default=None,
                metavar="TARGET",
                help="integration target (repeatable; defaults to configured targets)",
            )
        elif verb in ("adopt", "remove"):
            command.add_argument(
                "--target",
                required=True,
                metavar="TARGET",
                help="integration target",
            )
        if verb in ("plan", "apply"):
            command.add_argument(
                "--force-conflicts",
                action="store_true",
                default=False,
                help="overwrite conflicted files after capturing pre-images",
            )
        if verb in ("apply", "remove"):
            command.add_argument(
                "--restore-pre-image",
                action="store_true",
                default=False,
                help="restore captured pre-image when removing unmodified owned files",
            )
        if verb == "adopt":
            command.add_argument("--reason", required=True, help="audit reason for adopting the file")
        if verb in ("apply", "adopt", "remove"):
            command.add_argument(
                "--yes",
                default=argparse.SUPPRESS,
                action="store_true",
                help="confirm destructive or adoption operations",
            )
        if verb == "list":
            command.add_argument("--after", default=None, help="pagination cursor")
            command.add_argument("--limit", type=int, default=50, help="page size (1..200)")


GROUP = CommandGroup(
    name="integrations",
    help="project, reconcile and inspect client integration files",
    register=register,
    requires_backend=True,
    module="integrations",
    order=85,
)
