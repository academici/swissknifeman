"""``skm ext`` (cli §6, extensions §10): manage extension packs, resources, quarantine and upstream tracking.

Thin CLI surface over ``extensions`` bus commands/queries and host operations
(``extensions.host.install_pack`` and ``extensions.host.check_upstream``). Never mutates state during
``resolve`` or ``upstream check``.
"""

from __future__ import annotations

import argparse
import contextlib
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import UUID

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.host import build_host_context
from skm.entrypoints.cli.output import kv_lines, render, render_table
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    InternalError,
    NotFound,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access

if TYPE_CHECKING:
    from skm.entrypoints.cli.context import CliContext
    from skm.kernel.json_types import JsonObject
    from skm.kernel.module_manifest import ModuleManifest

__all__ = ["GROUP", "register"]

_HELP: Final = {
    "list": "list installed extension packs or active resources",
    "show": "show details of an extension pack or resource version",
    "resolve": "resolve a resource by kind and key for the active scope",
    "install": "install an extension pack from a directory or .tar.gz archive",
    "sync": "synchronize built-in extension packs",
    "quarantine": "place a resource version into quarantine",
    "release": "release a quarantined resource version (instance owner only)",
    "uninstall": "retire an installed pack version",
    "retire": "retire an installed pack version (alias for uninstall)",
    "upstream": "check tracked upstream resources without mutating local state",
}

_COMMAND: Final = {
    "list": "extensions.list_packs",
    "show": "extensions.get_pack",
    "resolve": "extensions.resolve_resource",
    "install": "extensions.host.install_pack",
    "sync": "extensions.sync_builtin_packs",
    "quarantine": "extensions.quarantine_resource",
    "release": "extensions.release_quarantine",
    "uninstall": "extensions.uninstall_pack_version",
    "retire": "extensions.uninstall_pack_version",
    "upstream": "extensions.host.check_upstream",
}

_RESOURCE_KINDS: Final = (
    "skill",
    "steering",
    "agent_profile",
    "workflow",
    "plan_template",
    "prompt_block",
    "integration_bundle",
    "runtime_catalog",
    "model_guideline",
)


def _extensions_manifest() -> ModuleManifest:
    for item in MANIFESTS:
        if item.id == "extensions":
            return item
    raise KeyError("extensions")


def _query_dto(name: str, payload: JsonObject) -> object:
    manifest = _extensions_manifest()
    for spec in manifest.queries:
        spec_obj = cast("Any", spec)
        if spec_obj.name == name:
            return spec_obj.dto.from_json(payload)
    raise KeyError(name)


def _command_dto(name: str, payload: JsonObject) -> object:
    manifest = _extensions_manifest()
    for spec in manifest.commands:
        spec_obj = cast("Any", spec)
        if spec_obj.name == name:
            return spec_obj.dto.from_json(payload)
    raise KeyError(name)


def _scope_dto(args: argparse.Namespace | None, ctx: CliContext) -> JsonObject:
    raw_scope = getattr(args, "scope", None) if args is not None else None
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


def _run_host_op(ctx: CliContext, name: str, request: JsonObject) -> object:
    host_ctx = build_host_context(ctx)
    spec = next(
        (
            op
            for manifest in MANIFESTS
            if manifest.id == "extensions"
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


def _parse_uuid(text: str, prefix: str = "") -> UUID | None:
    cleaned = text.removeprefix(prefix) if prefix else text
    try:
        return UUID(cleaned)
    except ValueError:
        return None


def _resolve_resource_version_id(
    ctx: CliContext,
    target: str,
    *,
    kind_opt: str | None = None,
    args: argparse.Namespace | None = None,
) -> UUID:
    as_uuid = _parse_uuid(target, "resource_version:")
    if as_uuid is not None:
        return as_uuid

    if kind_opt is not None:
        kind_str = kind_opt
        rest = target
    elif ":" in target:
        kind_str, _, rest = target.partition(":")
    else:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f"expected resource_version UUID or <kind>:<key>, got {target!r}",
            details={"target": target},
        )

    if kind_str not in _RESOURCE_KINDS:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f"unknown resource kind {kind_str!r}",
            details={"kind": kind_str, "target": target},
        )

    key_str, _, ver_str = rest.partition("@")
    version_filter = ver_str or None

    scope_dto = _scope_dto(args, ctx)
    resolved = cast(
        "Any",
        ctx.client.ask(
            _query_dto(
                "extensions.resolve_resource",
                {"kind": kind_str, "key": key_str, "scope": scope_dto},
            )
        ),
    )
    chosen = getattr(resolved, "chosen", None)
    if chosen is not None:
        if version_filter is not None and str(chosen.version) != version_filter:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"resource version for {target!r} not found",
                details={"target": target, "version": version_filter},
            )
        return UUID(str(chosen.resource_version_id))

    candidates: tuple[Any, ...] = tuple(getattr(resolved, "candidates", ()))
    for candidate in candidates:
        if getattr(candidate, "reason", None) == "quarantined" and (
            version_filter is None or str(getattr(candidate, "version", "")) == version_filter
        ):
            raise PreconditionFailed(
                ErrorCode.RESOURCE_QUARANTINED,
                f"resource {kind_str}:{key_str} is quarantined",
                details={"target": target, "kind": kind_str, "key": key_str},
            )

    raise NotFound(
        ErrorCode.NOT_FOUND,
        f"resource version for {target!r} not found",
        details={"target": target},
    )


def _resolve_pack_version_id(ctx: CliContext, target: str, *, version_opt: str | None = None) -> UUID:
    as_uuid = _parse_uuid(target, "pack_version:")
    if as_uuid is not None:
        return as_uuid

    cleaned = target.removeprefix("pack:")
    if "@" in cleaned:
        slug, _, ver = cleaned.partition("@")
    else:
        slug, ver = cleaned, version_opt or ""

    pack_view = cast("Any", ctx.client.ask(_query_dto("extensions.get_pack", {"pack": slug})))
    versions: tuple[Any, ...] = tuple(getattr(pack_view, "versions", ()))
    if ver:
        for item in versions:
            if str(item.version) == ver:
                return UUID(str(item.version_id))
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"pack {slug!r} has no version {ver!r}",
            details={"pack": slug, "version": ver},
        )

    active = [item for item in versions if getattr(item, "state", "") == "active"]
    chosen = active[-1] if active else (versions[-1] if versions else None)
    if chosen is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"pack {slug!r} has no versions",
            details={"pack": slug},
        )
    return UUID(str(chosen.version_id))


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    pack_filter: str | None = getattr(args, "pack", None)
    scope_opt: str | None = getattr(args, "scope", None)
    want_resources = bool(
        getattr(args, "resources", False)
        or getattr(args, "kind", None) is not None
        or pack_filter is not None
        or getattr(args, "quarantined", False)
    )
    if want_resources:
        payload: JsonObject = {"include_quarantined": bool(getattr(args, "quarantined", False))}
        if getattr(args, "kind", None) is not None:
            payload["kind"] = args.kind
        if scope_opt is not None:
            payload["scope"] = _scope_dto(args, ctx)
        view = cast("Any", ctx.client.ask(_query_dto("extensions.list_resources", payload)))
        raw_items: list[Any] = list(view.items)
        if pack_filter is not None:
            cleaned_pack = pack_filter.removeprefix("pack:")
            raw_items = [item for item in raw_items if str(item.pack_slug) == cleaned_pack]
        out_doc: JsonObject = {
            "items": [item.to_json() if hasattr(item, "to_json") else item for item in raw_items]
        }

        def human_resources(_: Any) -> list[str]:
            rows = [
                [
                    item.kind.value if hasattr(item.kind, "value") else str(item.kind),
                    item.key,
                    item.version,
                    str(item.digest),
                    f"{item.pack_slug}@{item.pack_version}",
                    item.verdict.value if hasattr(item.verdict, "value") else str(item.verdict),
                    "yes" if item.quarantined else "no",
                ]
                for item in raw_items
            ]
            return render_table(
                ctx,
                ("kind", "key", "version", "digest", "pack", "verdict", "quarantined"),
                rows,
            )

        return render(
            ctx,
            out_doc,
            human=human_resources,
            command="extensions.list_resources",
            essential=lambda _: "\n".join(f"{item.kind.value}:{item.key}" for item in raw_items),
        )

    view = cast("Any", ctx.client.ask(_query_dto("extensions.list_packs", {})))

    def human_packs(value: Any) -> list[str]:
        rows = [
            [
                item.slug,
                next((v.version for v in reversed(item.versions) if v.state == "active"), "-"),
                item.trust.value if hasattr(item.trust, "value") else str(item.trust),
                str(item.priority),
                item.title,
            ]
            for item in value.items
        ]
        return render_table(ctx, ("slug", "active", "trust", "priority", "title"), rows)

    return render(
        ctx,
        view,
        human=human_packs,
        command=args.command_name,
        essential=lambda value: "\n".join(str(item.slug) for item in value.items),
    )


def _show(args: argparse.Namespace, ctx: CliContext) -> int:
    target: str = args.target
    kind_opt: str | None = getattr(args, "kind", None)
    include_bodies = bool(getattr(args, "bodies", False))

    as_uuid = _parse_uuid(target, "resource_version:")
    if as_uuid is not None:
        rv_view = cast(
            "Any",
            ctx.client.ask(
                _query_dto(
                    "extensions.get_resource_version",
                    {"resource_version_id": str(as_uuid), "include_bodies": include_bodies},
                )
            ),
        )
        return _render_resource_version(ctx, rv_view)

    is_explicit_pack = target.startswith("pack:") and kind_opt is None
    is_resource_ref = not is_explicit_pack and (
        kind_opt is not None or (":" in target and target.partition(":")[0] in _RESOURCE_KINDS)
    )
    if is_resource_ref:
        rv_id = _resolve_resource_version_id(ctx, target, kind_opt=kind_opt, args=args)
        rv_view = cast(
            "Any",
            ctx.client.ask(
                _query_dto(
                    "extensions.get_resource_version",
                    {"resource_version_id": str(rv_id), "include_bodies": include_bodies},
                )
            ),
        )
        return _render_resource_version(ctx, rv_view)

    cleaned_target = target.removeprefix("pack:")
    slug = cleaned_target.partition("@")[0] if "@" in cleaned_target else cleaned_target
    pack_view = cast("Any", ctx.client.ask(_query_dto("extensions.get_pack", {"pack": slug})))

    def human_pack(value: Any) -> list[str]:
        pairs: list[tuple[str, object]] = [
            ("slug", value.slug),
            ("title", value.title),
            ("publisher", value.manifest.publisher),
            ("trust", value.trust.value if hasattr(value.trust, "value") else str(value.trust)),
            ("license", value.manifest.license),
            ("versions", ", ".join(f"{v.version} ({v.state})" for v in value.versions) or "none"),
        ]
        return kv_lines(ctx, pairs)

    return render(
        ctx,
        pack_view,
        human=human_pack,
        command=args.command_name,
        essential=lambda value: str(value.slug),
    )


def _render_resource_version(ctx: CliContext, rv_view: Any) -> int:
    def human(value: Any) -> list[str]:
        pairs: list[tuple[str, object]] = [
            ("id", value.resource_version_id),
            ("kind", value.kind.value if hasattr(value.kind, "value") else str(value.kind)),
            ("key", value.key),
            ("version", value.version),
            ("pack_version_id", value.pack_version_id),
            ("digest", value.digest),
            ("files", len(value.files)),
        ]
        return kv_lines(ctx, pairs)

    return render(
        ctx,
        rv_view,
        human=human,
        command="extensions.get_resource_version",
        essential=lambda value: str(value.resource_version_id),
    )


def _resolve(args: argparse.Namespace, ctx: CliContext) -> int:
    target: str = args.target
    extra_key: str | None = getattr(args, "key", None)
    kind_opt: str | None = getattr(args, "kind", None)

    if extra_key is not None:
        kind_str, key_str = target, extra_key
    elif kind_opt is not None:
        kind_str, key_str = kind_opt, target
    elif ":" in target:
        kind_str, _, key_str = target.partition(":")
    else:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "expected <kind>:<key> or --kind <kind> <key>",
            details={"target": target},
        )

    if kind_str not in _RESOURCE_KINDS:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unknown resource kind {kind_str!r}",
            details={"kind": kind_str},
        )

    payload: JsonObject = {
        "kind": kind_str,
        "key": key_str,
        "scope": _scope_dto(args, ctx),
    }

    view = cast("Any", ctx.client.ask(_query_dto("extensions.resolve_resource", payload)))

    def human(value: Any) -> list[str]:
        if value.chosen is not None:
            c = value.chosen
            return [f"{c.kind.value}:{c.key} -> {c.resource_version_id} ({c.version}, {c.digest})"]
        return [f"{kind_str}:{key_str} -> unresolved ({len(value.candidates)} candidates)"]

    return render(
        ctx,
        view,
        human=human,
        command=args.command_name,
        essential=lambda value: str(value.chosen.resource_version_id) if value.chosen is not None else "",
    )


def _install(args: argparse.Namespace, ctx: CliContext) -> int:
    req: JsonObject = {
        "path": args.path,
        "trust": args.trust,
        "dry_run": bool(getattr(args, "dry_run", False)),
    }
    if bool(getattr(args, "no_quarantine", False)):
        req["allow_quarantine"] = False
    elif bool(getattr(args, "allow_quarantine", False)):
        req["allow_quarantine"] = True

    report = cast("Any", _run_host_op(ctx, "extensions.host.install_pack", req))

    def human(value: Any) -> list[str]:
        return [
            f"{value.status} pack {value.slug}@{value.version} "
            f"({len(value.resources)} resources, {len(value.quarantined)} quarantined)"
        ]

    return render(
        ctx,
        report,
        human=human,
        command=args.command_name,
        essential=lambda value: str(value.pack_version_id),
    )


def _sync(args: argparse.Namespace, ctx: CliContext) -> int:
    result = cast(
        "Any",
        ctx.client.dispatch(
            _command_dto("extensions.sync_builtin_packs", {}),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )

    def human(value: Any) -> list[str]:
        lines = [f"{item.slug}@{item.version}: installed" for item in value.installed]
        lines.extend(f"{item.slug}@{item.version}: already_installed" for item in value.already_installed)
        return lines or ["no built-in packs found"]

    return render(
        ctx,
        result,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(
            f"{item.slug}@{item.version}" for item in (*value.installed, *value.already_installed)
        ),
    )


def _quarantine(args: argparse.Namespace, ctx: CliContext) -> int:
    rv_id = _resolve_resource_version_id(
        ctx,
        args.target,
        kind_opt=getattr(args, "kind", None),
        args=args,
    )
    reason = getattr(args, "reason", None) or "quarantined via cli"
    result = cast(
        "Any",
        ctx.client.dispatch(
            _command_dto(
                "extensions.quarantine_resource",
                {"resource_version_id": str(rv_id), "reason": reason},
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: f"quarantined {value.resource_version_id}",
        command=args.command_name,
        essential=lambda value: str(value.resource_version_id),
    )


def _release(args: argparse.Namespace, ctx: CliContext) -> int:
    rv_id = _resolve_resource_version_id(
        ctx,
        args.target,
        kind_opt=getattr(args, "kind", None),
        args=args,
    )
    reason = getattr(args, "reason", None) or "released via cli"
    result = cast(
        "Any",
        ctx.client.dispatch(
            _command_dto(
                "extensions.release_quarantine",
                {"resource_version_id": str(rv_id), "reason": reason},
            ),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: f"released {value.resource_version_id}",
        command=args.command_name,
        essential=lambda value: str(value.resource_version_id),
    )


def _uninstall(args: argparse.Namespace, ctx: CliContext) -> int:
    pv_id = _resolve_pack_version_id(
        ctx,
        args.target,
        version_opt=getattr(args, "version", None),
    )
    result = cast(
        "Any",
        ctx.client.dispatch(
            _command_dto("extensions.uninstall_pack_version", {"pack_version_id": str(pv_id)}),
            idempotency_key=ctx.new_idempotency_key(),
        ),
    )
    return render(
        ctx,
        result,
        human=lambda value: f"retired pack version {value.pack_version_id} ({value.state})",
        command=args.command_name,
        essential=lambda value: str(value.pack_version_id),
    )


def _upstream_digest_summary(files: Any) -> str:
    digests = [
        str(getattr(f, "upstream_sha256", None))
        for f in (files or ())
        if getattr(f, "upstream_sha256", None) is not None
    ]
    if not digests:
        return "-"
    if len(digests) == 1:
        return digests[0]
    return f"{digests[0]} (+{len(digests) - 1})"


def _upstream(args: argparse.Namespace, ctx: CliContext) -> int:
    req: JsonObject = {}
    pack_arg = getattr(args, "pack", None) or getattr(args, "pack_pos", None)
    if isinstance(pack_arg, str) and pack_arg.strip():
        req["pack"] = pack_arg.strip().removeprefix("pack:")
    if getattr(args, "kind", None) is not None:
        req["kind"] = args.kind
    if getattr(args, "key", None) is not None:
        req["key"] = args.key
    with contextlib.suppress(CapabilityUnavailable, NotFound):
        req["scope"] = _scope_dto(args, ctx)

    report = cast("Any", _run_host_op(ctx, "extensions.host.check_upstream", req))

    def human(value: Any) -> list[str]:
        rows = [
            [
                item.kind.value if hasattr(item.kind, "value") else str(item.kind),
                item.key,
                item.strategy or "-",
                item.status,
                _upstream_digest_summary(item.files),
                str(len(item.files)),
            ]
            for item in value.items
        ]
        return render_table(
            ctx,
            ("kind", "key", "strategy", "status", "upstream_digest", "files"),
            rows,
        )

    return render(
        ctx,
        report,
        human=human,
        command=args.command_name,
        essential=lambda value: "\n".join(
            f"{item.kind.value}:{item.key}:{item.status}" for item in value.items
        ),
    )


def _add_subparser_defaults(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
    subparser.add_argument("--scope", default=argparse.SUPPRESS)


_RUN: Final = {
    "list": _list,
    "show": _show,
    "resolve": _resolve,
    "install": _install,
    "sync": _sync,
    "quarantine": _quarantine,
    "release": _release,
    "uninstall": _uninstall,
    "retire": _uninstall,
    "upstream": _upstream,
}


def register(sub: SubParsers) -> None:
    parser = sub.add_parser(
        "ext",
        help="manage extension packs, resources, quarantine and upstream tracking",
    )
    verbs = parser.add_subparsers(dest="ext_verb", required=True)
    for verb in (
        "list",
        "show",
        "resolve",
        "install",
        "sync",
        "quarantine",
        "release",
        "uninstall",
        "retire",
        "upstream",
    ):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
        command.add_argument("--json", default=argparse.SUPPRESS, action="store_true")
        command.add_argument("--scope", default=argparse.SUPPRESS)
        if verb == "list":
            command.add_argument("--resources", action="store_true")
            command.add_argument(
                "--kind",
                choices=(
                    "skill",
                    "steering",
                    "agent_profile",
                    "workflow",
                    "plan_template",
                    "prompt_block",
                    "integration_bundle",
                    "runtime_catalog",
                    "model_guideline",
                ),
            )
            command.add_argument("--pack")
            command.add_argument("--quarantined", action="store_true")
        elif verb == "show":
            command.add_argument("target")
            command.add_argument(
                "--kind",
                choices=(
                    "skill",
                    "steering",
                    "agent_profile",
                    "workflow",
                    "plan_template",
                    "prompt_block",
                    "integration_bundle",
                    "runtime_catalog",
                    "model_guideline",
                ),
            )
            command.add_argument("--bodies", action="store_true")
        elif verb == "resolve":
            command.add_argument("target")
            command.add_argument("key", nargs="?")
            command.add_argument(
                "--kind",
                choices=(
                    "skill",
                    "steering",
                    "agent_profile",
                    "workflow",
                    "plan_template",
                    "prompt_block",
                    "integration_bundle",
                    "runtime_catalog",
                    "model_guideline",
                ),
            )
        elif verb == "install":
            command.add_argument("path")
            command.add_argument("--trust", choices=("operator", "third_party"), default="third_party")
            command.add_argument("--allow-quarantine", action="store_true")
            command.add_argument("--no-quarantine", action="store_true")
            command.add_argument("--dry-run", action="store_true")
        elif verb in ("quarantine", "release"):
            command.add_argument("target")
            command.add_argument("--reason", default="operator action")
            command.add_argument(
                "--kind",
                choices=(
                    "skill",
                    "steering",
                    "agent_profile",
                    "workflow",
                    "plan_template",
                    "prompt_block",
                    "integration_bundle",
                    "runtime_catalog",
                    "model_guideline",
                ),
            )
            command.add_argument("--pack")
        elif verb in ("uninstall", "retire"):
            command.add_argument("target")
            command.add_argument("--version")
            command.add_argument("--yes", default=argparse.SUPPRESS, action="store_true")
        elif verb == "upstream":
            upstream_verbs = command.add_subparsers(dest="upstream_verb", required=False)
            command = upstream_verbs.add_parser(
                "check",
                help="check tracked upstream resources without mutating local state",
            )
            command.set_defaults(run=_RUN[verb], command_name=_COMMAND[verb])
            _add_subparser_defaults(command)
            command.add_argument("pack_pos", nargs="?", metavar="PACK")
            command.add_argument("--pack")
            command.add_argument(
                "--kind",
                choices=(
                    "skill",
                    "steering",
                    "agent_profile",
                    "workflow",
                    "plan_template",
                    "prompt_block",
                    "integration_bundle",
                    "runtime_catalog",
                    "model_guideline",
                ),
            )
            command.add_argument("--key")


GROUP: Final = CommandGroup(
    name="ext",
    help="manage extension packs, resources, quarantine and upstream tracking",
    register=register,
    requires_backend=True,
    module="extensions",
    order=80,
)
