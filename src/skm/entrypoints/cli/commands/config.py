"""Thin settings CLI (settings §A.14); ``doctor`` asks the public ``platform.doctor`` query (CLI §5.3)."""

import argparse
import json
import math
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.output import escape_terminal, render, render_table, safe_text, to_jsonable
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, InternalError, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.settings import public as settings
from skm.platform.config.explain import render_explain_text
from skm.platform.config.keys import MISSING, KeySpec
from skm.platform.config.registry import MAX_KEY_SEGMENTS
from skm.platform.config.sources.text_values import parse_text_value
from skm.platform.generated import queries as platform_queries

__all__ = ["GROUP", "register"]

_OPERATIONS = {
    "schema": settings.GetSchema,
    "get": settings.GetValue,
    "explain": settings.ExplainConfig,
    "set": settings.SetValue,
    "unset": settings.UnsetValue,
    "remove": settings.RemoveValue,
    "lock": settings.LockValue,
    "unlock": settings.UnlockValue,
    "import": settings.ImportConfig,
    "export": settings.ExportConfig,
    "entries": settings.ListEntries,
    "history": settings.GetHistory,
    "doctor": platform_queries.Doctor,
}
_WRITES = frozenset({"set", "unset", "remove", "lock", "unlock", "import"})
_HELP = {
    "schema": "show declared sections and key metadata",
    "get": "read one effective value",
    "explain": "explain effective values and their contributions",
    "set": "set a typed value at a scope",
    "unset": "reset a key to its default at a scope",
    "remove": "remove a scope contribution, revealing inherited values",
    "lock": "lock a key at instance or workspace scope",
    "unlock": "unlock a key at instance or workspace scope",
    "import": "import a TOML or JSON configuration document",
    "export": "export scope entries as TOML or JSON",
    "entries": "list stored scope entries",
    "history": "show entry history",
    "doctor": "diagnose registry, stored entries of every scope, locks and restart-pending",
}
# Explain's text layout branches on these closed-enum members (settings §B.8.2).
_LAYOUT_MEMBERS = frozenset({"level", "op", "status", "reason", "merge", "reload", "interpretation"})
_IDENTIFIER = re.compile(r"[a-z][a-z_]*")


def _scope(args: argparse.Namespace, ctx: CliContext) -> JsonObject:
    # CliSession cannot resolve the instance id; the facade explicitly permits its omission.
    # A default without an explicit selector still follows the session's saved context.
    try:
        scope = ctx.resolve_scope(args.scope)
    except CapabilityUnavailable as exc:
        if exc.details.get("kind") != "instance":
            raise
        return {"level": "instance"}
    return {"level": scope.kind.value, "scope_id": str(scope.id)}


def _section_views(ctx: CliContext, key: str, scope: JsonObject) -> Iterator[settings.GetSchemaView]:
    """The schema of each section that may own ``key``: every dotted prefix that is a section.

    A key starts with its section id, so asking for those sections alone avoids fetching and
    validating the whole catalog on every write. An unknown prefix is simply not a section.
    """
    parts = key.split(".", MAX_KEY_SEGMENTS)
    prefix_count = len(parts) - 1 if 1 < len(parts) <= MAX_KEY_SEGMENTS else 1
    # Even a malformed key must go through the target scope's config.read check.
    for end in range(1, prefix_count + 1):
        section = ".".join(parts[:end])
        try:
            view = ctx.client.ask(settings.GetSchema.from_json({"scope": scope, "section": section}))
        except ValidationFailed as exc:
            if exc.code is ErrorCode.CONFIG_UNKNOWN_KEY and exc.details.get("section") == section:
                continue
            raise
        yield cast("settings.GetSchemaView", view)


def _key_spec(ctx: CliContext, key: str, scope: JsonObject) -> KeySpec:
    # config.read is checked at the write's target before metadata is disclosed (settings §A.8).
    owners = [
        (section, declared)
        for view in _section_views(ctx, key, scope)
        for section in view.sections
        for declared in section.keys
        if declared.key == key
    ]
    if not owners:
        raise ValidationFailed(
            ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown config key {key}", details={"key": key}
        )
    if len(owners) > 1:
        # The registry refuses a key declared twice; reaching this means its catalog is inconsistent.
        sections = [section.id for section, _ in owners]
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            f"config key {key} is declared by several sections: {', '.join(sections)}",
            details={"key": key, "sections": list[JsonValue](sections)},
        )
    [(section, declared)] = owners
    descriptor = cast("JsonObject", to_jsonable(declared))
    metadata = {
        name: value
        for name, value in descriptor.items()
        if name not in {"key", "section", "value_schema", "default"} and value is not None
    }
    return KeySpec.from_metadata(
        key=key,
        section=section.id,
        owner=section.owner,
        value_schema=cast("Mapping[str, JsonValue]", declared.value_schema),
        default=descriptor.get("default", MISSING),
        description="",
        x_skm=metadata,
    )


def _finite(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"number {text} is not finite")
    return number


def _not_json(text: str) -> float:
    raise ValueError(f"{text} is not a JSON number")


def _document(path_text: str) -> tuple[str, str | JsonObject]:
    path = Path(path_text)
    fmt = path.suffix.lower().removeprefix(".")
    if fmt not in {"toml", "json"}:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "config import requires a .toml or .json file")
    try:
        # The facade owns the same 1 MiB limit; bound local IO before constructing its DTO.
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("document exceeds 1 MiB")
        text = data.decode("utf-8")
        if fmt == "toml":
            return fmt, text
        # Python's decoder accepts NaN, Infinity and overflowing numbers; JSON (§A.7.6) does not.
        document = json.loads(text, parse_float=_finite, parse_constant=_not_json)
        if not isinstance(document, dict):
            raise ValueError("JSON document must be an object")
    except RecursionError:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "cannot read config document: nested too deeply",
            details={"path": path_text},
        ) from None
    except (OSError, ValueError) as exc:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, f"cannot read config document: {exc}", details={"path": path_text}
        ) from None
    else:
        return fmt, cast("JsonObject", document)


def _present(**members: JsonValue) -> JsonObject:
    """Members of an optional, non-nullable field are omitted when unset: ``null`` is not "absent" (codec)."""
    return {name: value for name, value in members.items() if value is not None}


def _payload(args: argparse.Namespace, ctx: CliContext) -> JsonObject:
    verb = args.config_verb
    if verb == "schema":
        return _present(section=args.section)
    if verb == "doctor":
        # platform.doctor is authorized at the instance and covers every scope; a selector would be ignored.
        if getattr(args, "scope", None) is not None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "config doctor covers every scope and takes no --scope"
            )
        return _present(only=args.only)
    payload: JsonObject = {"scope": _scope(args, ctx)}
    if verb == "explain":
        return {
            **payload,
            **_present(keys=args.keys or None, section=args.section),
            "detail": args.detail,
            "include_defaults_only": args.all,
        }
    if verb in {"get", "set", "unset", "remove", "lock", "unlock", "history"}:
        payload.update(_present(key=args.key))  # history's key is optional
    if verb in _WRITES:
        payload.update(reason=args.reason, confirmed=ctx.assume_yes)
        if verb != "import":
            payload["expected_row_version"] = args.expected_version
    if verb == "set":
        spec = _key_spec(ctx, args.key, cast("JsonObject", payload["scope"]))
        payload.update(
            value=parse_text_value(spec, args.value),
            mode="append" if args.append else "set",
            locked=True if args.lock else None,
            confirmed=ctx.assume_yes or (spec.confirm and ctx.confirm(f"Set {args.key}?")),
        )
    elif verb == "import":
        fmt, document = _document(args.file)
        payload.update(
            format=fmt,
            document=document,
            mode="replace" if args.replace else "merge",
            dry_run=args.dry_run,
            expected_entries_digest=args.expect_digest,
        )
    elif verb == "export":
        payload.update(format=args.format, portable_only=args.portable_only)
    elif verb in {"entries", "history"}:
        payload.update(_present(after=args.after), limit=args.limit)
        if verb == "entries":
            payload.update(_present(key_prefix=args.prefix))
    return payload


def _json(value: object) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, sort_keys=True, allow_nan=False)


def _human(verb: str, result: JsonObject) -> list[str]:
    if verb == "explain":
        # Split trusted layout before render() escapes each line, including all dynamic values.
        # Escape controls in data first so a value cannot introduce an extra line in that layout.
        return render_explain_text(result).splitlines()
    if verb == "get":
        return [f"{result['key']} = {_json(result['value'])}  ({_json(result.get('winner'))})"]
    if verb == "schema":
        return [
            f"{key['key']}  {_json(key['value_schema'])}  default={_json(key.get('default'))}  "
            f"levels={_json(key['levels'])}  {key['merge']}  {key['reload']}"
            for section in cast("list[JsonObject]", result["sections"])
            for key in cast("list[JsonObject]", section["keys"])
        ]
    if verb == "doctor":
        return _doctor_lines(result)
    if verb == "import":
        changes = cast("list[JsonObject]", result["changes"])
        return [
            *(
                f"{c['change']} {c['key']}: {_json(c.get('before'))} → {_json(c.get('after'))}"
                for c in changes
            ),
            *(_json(p) for p in cast("list[JsonValue]", result["problems"])),
            f"{'dry run' if result['dry_run'] else 'imported'}: {len(changes)} changes, "
            f"{len(cast('list[JsonValue]', result['problems']))} errors",
        ]
    if verb == "remove":
        return [f"removed {result['removed_entry_id']} (generation {result['generation']})"]
    entry = cast("JsonObject", result["entry"])
    return [
        f"{verb} {entry['key']}={_json(entry.get('value'))} at {_json(entry['scope'])} "
        f"(v{entry['row_version']}{', locked' if entry['locked'] else ''})"
    ]


def _doctor_lines(result: JsonObject) -> list[str]:
    """One line per check; a ``warn`` is shown as such (unknown coverage is never reported as ``ok``)."""
    checks = cast("list[JsonObject]", result["checks"])
    counts = {status: sum(1 for c in checks if c["status"] == status) for status in ("fail", "warn", "ok")}
    lines: list[str] = []
    for check in checks:
        details = cast("JsonObject", check["details"])
        lines.append(f"{check['status']}  {check['id']}  {check['message']}  [{details['target']}]")
        if details.get("detail"):
            lines.append(f"      {details['detail']}")
        if details.get("path"):
            lines.append(f"      path: {details['path']}")
        if check.get("hint"):
            lines.append(f"      hint: {check['hint']}")
    lines.append(
        f"{len(checks)} checks: {counts['fail']} fail, {counts['warn']} warn, {counts['ok']} ok"
        + ("" if checks else " (none selected)")
    )
    return lines


def _side(item: JsonObject, side: str) -> str:
    op = item[f"{side}_op"]
    shown = "—" if op is None else "<unset>" if op == "unset" else _json(item.get(f"{side}_value"))
    return shown + (" [locked]" if item.get(f"{side}_locked") else "")


def _page_lines(ctx: CliContext, verb: str, result: JsonObject) -> list[str]:
    """CLI §6.2 tables; render_table redacts and escapes every cell."""
    items = cast("list[JsonObject]", result["items"])
    if verb == "history":
        headers = ["at", "actor", "op", "key", "old → new", "reason"]
        rows = [
            [
                h["changed_at"],
                h["actor_id"],
                h["change_kind"],
                h["key"],
                f"{_side(h, 'old')} → {_side(h, 'new')}",
                h["reason"],
            ]
            for h in items
        ]
    else:
        headers = ["key", "op", "value", "locked", "version", "updated", "reason"]
        rows = [
            [
                e["key"],
                e["op"],
                "<unset>" if e["op"] == "unset" else _json(e.get("value")),
                "locked" if e["locked"] else "",
                e["row_version"],
                e["updated_at"],
                e.get("reason"),
            ]
            for e in items
        ]
    lines = render_table(ctx, headers, rows)
    if result["next"] is not None:
        lines.append(safe_text(ctx, f"next: {result['next']} (use --after)"))
    return lines


def _format_text(text: str) -> str:
    """JSON and TOML basic strings accept ``\\uXXXX`` but not the terminal sink's ``\\xNN``.

    A serialized document holds such characters only inside strings, so escaping them in place keeps the
    document valid; its line separators remain.
    """
    return "".join(
        f"\\u{ord(char):04x}" if char != "\n" and escape_terminal(char) != char else char for char in text
    )


def _safe_report(ctx: CliContext, value: JsonValue, member: str | None = None) -> JsonValue:
    # Only explain's existing text renderer supplies multiline layout. Escape its data beforehand.
    if isinstance(value, str):
        # Closed-enum layout values select wording; render() still redacts the final lines.
        if member in _LAYOUT_MEMBERS and _IDENTIFIER.fullmatch(value):
            return value
        return safe_text(ctx, value)
    if isinstance(value, list):
        return [_safe_report(ctx, item) for item in value]
    if isinstance(value, dict):
        # Report member names are structural input to the text renderer. Its final output is
        # redacted by render(); masking a member named like a credential here would break lookup.
        return {key: _safe_report(ctx, item, key) for key, item in value.items()}
    return value


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    verb = args.config_verb
    payload = _payload(args, ctx)
    try:
        operation = _OPERATIONS[verb].from_json(payload)
    except RecursionError:
        # No owner limit exists: only input the DTO copy cannot recurse through is refused, before dispatch.
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "config input is nested too deeply to process",
            details={"reason": "too_deep"},
        ) from None
    if verb in _WRITES:
        result = ctx.client.dispatch(operation, idempotency_key=ctx.new_idempotency_key())
    else:
        result = ctx.client.ask(operation)
    document = cast("JsonObject", to_jsonable(result))
    if verb == "schema" and args.key is not None:
        sections = cast("list[JsonObject]", document["sections"])
        for section in sections:
            section["keys"] = [
                key for key in cast("list[JsonObject]", section["keys"]) if key["key"] == args.key
            ]
        if not any(section["keys"] for section in sections):
            raise ValidationFailed(ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown config key {args.key}")
    if not ctx.json and (verb == "export" or (verb == "get" and args.raw)):
        value = document["document"] if verb == "export" else document["value"]
        text = _format_text(value if verb == "export" and isinstance(value, str) else _json(value))
        # Keep document line separators, while every data line uses the shared safe sink.
        for line in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
            ctx.stdout.write(safe_text(ctx, line) + "\n")
        return 0
    if not ctx.json and verb in {"entries", "history"}:
        if not ctx.quiet:
            for line in _page_lines(ctx, verb, document):
                ctx.stdout.write(line + "\n")
        return 0
    render(
        ctx,
        result if verb != "schema" else document,
        human=lambda _: (
            _human(verb, cast("JsonObject", _safe_report(ctx, document)))
            if verb == "explain"
            else _human(verb, document)
        ),
        command=args.command_name,
    )
    if verb == "doctor":
        # CLI §5.3: exit 6 on errors; warnings, including unknown coverage, are reported but do not fail.
        return 6 if any(c["status"] == "fail" for c in cast("list[JsonObject]", document["checks"])) else 0
    return 1 if verb == "import" and document["problems"] else 0


def _run_machine(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.bootstrap.machine import open_machine_store
    from skm.bootstrap.runtimes import MACHINE_SETTING_KEYS, WorkerRuntimeSettings

    session = cast("CliSession", ctx)
    if session.options.actor_hint is not None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine settings use local operator credentials")
    if args.config_verb == "machine-keys":
        keys = sorted(MACHINE_SETTING_KEYS)
        return render(ctx, keys, human=lambda _: keys, command=args.command_name)
    key = cast("str", args.key)
    if key not in MACHINE_SETTING_KEYS:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Unknown machine setting; see skm config machine-keys"
        )
    catalog = session.profile_catalog()
    config = catalog.config(catalog.select(session.options.instance, Path.cwd()))
    store = open_machine_store(config, session.environ, on_secret=ctx.redactor.register_secret)
    installation = config.installation_id
    assert installation is not None  # noqa: S101 -- the machine-store opener checked the installation
    if args.config_verb == "machine-set":
        try:
            value = cast("JsonValue", json.loads(args.value, parse_constant=_not_json))
        except (ValueError, RecursionError):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Machine setting requires a JSON value"
            ) from None
        WorkerRuntimeSettings.validate_setting(key, value)
        store.set_operator_setting(installation, key, value)
        return render(
            ctx, {"key": key, "status": "saved"}, human=lambda _: f"saved {key}", command=args.command_name
        )
    value = store.get_operator_setting(installation, key)
    return render(
        ctx,
        {"key": key, "value": value},
        human=lambda _: safe_text(ctx, _json(value)),
        command=args.command_name,
    )


def register(sub: SubParsers) -> None:  # noqa: PLR0912, PLR0915 -- declare project and machine commands
    parser = sub.add_parser("config", help="inspect and change configuration")
    verbs = parser.add_subparsers(dest="config_verb", required=True)
    machine_keys = verbs.add_parser("machine-keys", help="list settings managed by the local operator")
    machine_keys.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    machine_keys.set_defaults(run=_run_machine, host_local=True, command_name="cli.config_machine_keys")

    machine_get = verbs.add_parser("machine-get", help="read a machine setting as the local operator")
    machine_get.add_argument("key", help="machine setting from skm config machine-keys")
    machine_get.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    machine_get.set_defaults(run=_run_machine, host_local=True, command_name="cli.config_machine_get")

    machine_set = verbs.add_parser("machine-set", help="set a machine setting as the local operator")
    machine_set.add_argument("key", help="machine setting from skm config machine-keys")
    machine_set.add_argument("value", metavar="JSON", help="JSON value for this machine setting")
    machine_set.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    machine_set.set_defaults(run=_run_machine, host_local=True, command_name="cli.config_machine_set")
    for verb, operation in _OPERATIONS.items():
        command = verbs.add_parser(verb, help=_HELP[verb])
        owner, name = operation.SCHEMA_URN.split(":")[2], operation.SCHEMA_URN.split(":")[-2]
        command.set_defaults(run=_run, command_name=f"{owner}.{name.replace('-', '_')}")
        # Suppressed defaults retain global options supplied before the group.
        for flag in ("--scope", "--json", "--yes"):
            if flag == "--scope":
                if verb != "doctor":
                    command.add_argument(
                        flag,
                        default=argparse.SUPPRESS,
                        metavar="SCOPE",
                        help="target scope (default: the saved context)",
                    )
            elif flag == "--json":
                command.add_argument(
                    flag,
                    default=argparse.SUPPRESS,
                    action="store_true",
                    help="machine-readable output (as global --json)",
                )
            else:
                command.add_argument(
                    flag, default=argparse.SUPPRESS, action="store_true", help="do not ask for confirmation"
                )
        if verb in {"get", "set", "unset", "remove", "lock", "unlock", "history"}:
            if verb == "history":
                command.add_argument("key", nargs="?", help="only the history of this key")
            else:
                command.add_argument("key", help="dotted config key, e.g. execution.review.max_rounds")
        if verb in _WRITES:
            command.add_argument("--reason", default="", help="reason recorded in the entry history")
            if verb != "import":
                command.add_argument(
                    "--expect-version",
                    "--expected-version",
                    dest="expected_version",
                    type=int,
                    metavar="N",
                    help="fail unless the stored entry has this version (0: create only)",
                )
        if verb == "set":
            command.add_argument("value", help="text parsed by the declared key type")
            command.add_argument("--lock", action="store_true", help="also lock the key at this scope")
            command.add_argument(
                "--append", action="store_true", help="append items to the inherited array value"
            )
        elif verb == "get":
            command.add_argument("--raw", action="store_true", help="print only the value")
        elif verb == "schema":
            command.add_argument("section", nargs="?", help="only this section")
            command.add_argument("--key", metavar="KEY", help="only this key")
        elif verb == "explain":
            command.add_argument("keys", nargs="*", help="keys to explain (default: all)")
            command.add_argument("--section", metavar="SECTION", help="only keys of this section")
            command.add_argument(
                "--detail", choices=("value", "full"), default="full", help="value only or all contributions"
            )
            # One destination: the last of --all/--no-all wins.
            command.add_argument(
                "--all",
                action="store_true",
                default=True,
                help="include keys with only a default value (default)",
            )
            command.add_argument(
                "--no-all", dest="all", action="store_false", help="show only keys some scope or source sets"
            )
            command.add_argument(
                "--show-secrets-refs", action="store_true", help="references only; never secrets"
            )
        elif verb == "doctor":
            command.add_argument(
                "--only", action="append", metavar="CHECK", help="run only this check id (repeatable)"
            )
        elif verb == "import":
            command.add_argument("file", help=".toml or .json document, at most 1 MiB")
            command.add_argument(
                "--replace", action="store_true", help="also remove stored keys missing from the document"
            )
            command.add_argument(
                "--dry-run", action="store_true", help="show changes and problems, apply nothing"
            )
            command.add_argument(
                "--expect-digest",
                metavar="DIGEST",
                help="fail unless the stored entries digest is this sha256:…",
            )
        elif verb == "export":
            command.add_argument(
                "--portable-only",
                action="store_true",
                help="omit keys declared portable=false",
            )
            command.add_argument(
                "--format", choices=("toml", "json"), default="toml", help="document format (default toml)"
            )
        elif verb in {"entries", "history"}:
            command.add_argument(
                "--after", metavar="NEXT", help="continue from the next value of the previous page"
            )
            command.add_argument(
                "--limit",
                type=int,
                default=20 if verb == "history" else 50,
                metavar="N",
                help="page size (at most 500)",
            )
            if verb == "entries":
                command.add_argument("--prefix", metavar="PREFIX", help="only keys starting with this prefix")


GROUP = CommandGroup("config", "inspect and change configuration", register, module="settings", order=30)
