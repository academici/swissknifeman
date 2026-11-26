"""Inspect, test, trust and replay hook subscriptions on their execution plane."""

from __future__ import annotations

import argparse
from typing import Any, cast

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli._run_io import ask, dispatch, identifier, operations, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.commands.workspace import resolve_workspace_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import to_jsonable
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.ports_uow import Surface
from skm.modules.integrations.public import TargetId

__all__ = ["GROUP", "register"]

_HELP = {
    "list": "list effective hook subscriptions",
    "show": "inspect a hook subscription before trusting it",
    "test": "test a subscription on its execution plane",
    "trust": "trust the current host command digest",
    "untrust": "revoke host command trust",
    "deliveries": "list hook delivery facts",
    "retry": "requeue dead hook deliveries",
    "drain": "replay due local observation commands",
}
_NAMES = {
    "list": "integrations.list_hook_subscriptions",
    "show": "integrations.list_hook_subscriptions",
    "test": "integrations.test_hook_subscription",
    "trust": "integrations.host.trust_hook_subscription",
    "untrust": "integrations.host.trust_hook_subscription",
    "deliveries": "integrations.list_hook_deliveries",
    "retry": "integrations.retry_hook_deliveries",
    "drain": "integrations.host.drain_hook_spool",
}


def _dto(name: str) -> Any:
    return next(
        cast("Any", spec).dto
        for manifest in MANIFESTS
        if manifest.id == "integrations"
        for spec in (*manifest.queries, *manifest.commands)
        if cast("Any", spec).name == name
    )


def _run_host_op(ctx: CliContext, name: str, payload: dict[str, Any]) -> object:
    spec = next(op for manifest in MANIFESTS for op in manifest.host_operations if op.name == name)
    if Surface.CLI not in spec.surfaces:
        raise ValidationFailed(ErrorCode.CAPABILITY_UNAVAILABLE, "host operation unavailable for CLI")
    return spec.run(build_host_context(ctx), payload)


def _run(args: argparse.Namespace, ctx: CliContext) -> int:  # noqa: PLR0912 - eight operator verbs
    verb = args.verb
    queries, commands = operations("integrations"), operations("integrations", writes=True)
    if verb == "drain":
        return show(ctx, _NAMES[verb], _run_host_op(ctx, _NAMES[verb], {}))
    workspace = resolve_workspace_id(ctx, args.workspace)
    project = resolve_project_id(ctx, args.project) if verb not in {"retry", "deliveries"} else None
    if verb == "retry":
        result = dispatch(
            ctx,
            commands.RetryHookDeliveries,
            workspace_id=str(workspace),
            delivery_ids=[str(identifier(item, "delivery")) for item in args.delivery_ids],
        )
    elif verb == "deliveries":
        result = ask(
            ctx,
            queries.ListHookDeliveries,
            workspace_id=str(workspace),
            subscription_id=args.subscription_id,
            state=args.state,
            after=args.after,
            limit=args.limit,
        )
    else:
        result = ask(ctx, queries.ListHookSubscriptions, workspace_id=str(workspace), project_id=str(project))
        if verb != "list":
            entries = cast("Any", to_jsonable(result))["items"]
            sub = next((sub for sub in entries if sub["id"] == args.subscription_id), None)
            if sub is None:
                raise NotFound(ErrorCode.NOT_FOUND, "hook subscription not found")
            host = sub["execution_location"] == "host"
            payload = {"project_id": str(project), "subscription_id": args.subscription_id}
            if verb == "show" or verb == "trust":
                if host:
                    policy = ask(
                        ctx,
                        _dto("integrations.get_hook_policy"),
                        project_id=str(project),
                        target=TargetId.CLAUDE_CODE.value,
                    )
                    result = next(
                        item
                        for item in cast("Any", to_jsonable(policy))["subscriptions"]
                        if item["id"] == args.subscription_id
                    )
                else:
                    result = sub
            if verb in {"trust", "untrust"}:
                if not host:
                    raise ValidationFailed(
                        ErrorCode.HOOK_SUBSCRIPTION_LOCATION, "only host commands require local trust"
                    )
                if verb == "trust":
                    payload["expected_digest"] = str(result["digest"])
                    show(ctx, "integrations.get_hook_policy", result)
                    if not (ctx.assume_yes or getattr(args, "yes", False)) and not ctx.confirm(
                        "Trust this exact host command digest?"
                    ):
                        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "trust confirmation required")
                result = _run_host_op(ctx, _NAMES[verb], {**payload, "revoke": verb == "untrust"})
            elif verb == "test":
                if host:
                    result = _run_host_op(
                        ctx,
                        "integrations.host.test_host_subscription",
                        {
                            **payload,
                            "event_kind": args.event_kind,
                            "command": args.input_command,
                            "paths": args.paths,
                        },
                    )
                else:
                    result = dispatch(
                        ctx, commands.TestHookSubscription, **payload, workspace_id=str(workspace)
                    )
    return show(ctx, _NAMES[verb], result)


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("hooks", help=GROUP.help, allow_abbrev=False)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("list", "show", "test", "trust", "untrust", "deliveries", "retry", "drain"):
        command = verbs.add_parser(verb, help=_HELP[verb], allow_abbrev=False)
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb != "drain":
            command.add_argument("--workspace")
            command.add_argument("--project")
        if verb in {"show", "test", "trust", "untrust"}:
            command.add_argument("subscription_id")
        if verb == "trust":
            command.add_argument("--yes", action="store_true")
        if verb == "test":
            command.add_argument("--event-kind", default="pre_shell")
            command.add_argument("--command", dest="input_command")
            command.add_argument("--path", dest="paths", action="append", default=[])
        if verb == "deliveries":
            command.add_argument("--subscription-id")
            command.add_argument("--state", choices=("pending", "delivered", "dead"))
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
        if verb == "retry":
            command.add_argument("delivery_ids", nargs="+")
        command.set_defaults(run=_run, command_name=_NAMES[verb])


GROUP = CommandGroup(
    "hooks", "manage hook subscriptions and local command trust", register, module="integrations", order=102
)
