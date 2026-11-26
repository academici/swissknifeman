"""Execution surface value parsing, identifiers and safe result layouts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import kv_lines, render, render_table, to_jsonable
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.settings.public import GetSchema, GetSchemaView
from skm.platform.config.keys import MISSING, KeySpec
from skm.platform.config.sources.text_values import parse_text_value


def operations(module: str, *, writes: bool = False) -> Any:
    """Use registered DTO identities, including JSON-mode wrappers, as the existing plan CLI does."""
    manifest = next(item for item in MANIFESTS if item.id == module)
    declarations = manifest.commands if writes else manifest.queries
    return SimpleNamespace(**{cast("Any", spec).dto.__name__: cast("Any", spec).dto for spec in declarations})


queries = operations("execution")


def identifier(raw: str, kind: str) -> UUID:
    value = as_uuid(raw.removeprefix(kind + ":"))
    if value is None:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, f"{kind} requires a UUID")
    return value


def run_id(ctx: CliContext, raw: str) -> UUID:
    if (value := as_uuid(raw.removeprefix("run:"))) is not None:
        return value
    from skm.entrypoints.cli.commands.project import resolve_project_id

    after = None
    found: list[Any] = []
    while True:
        page = ask(ctx, queries.ListRuns, project_id=str(resolve_project_id(ctx, None)), after=after)
        found.extend(item for item in page.items if raw == "last" or str(item["run_id"]).startswith(raw))
        if raw == "last" or page.next_after is None:
            break
        after = page.next_after
    if not found:
        raise NotFound(ErrorCode.NOT_FOUND, f"run not found: {raw}")
    if raw != "last" and len(found) != 1:
        raise ValidationFailed(ErrorCode.AMBIGUOUS_REFERENCE, "multiple runs match this prefix")
    return UUID(str(found[0]["run_id"]))


def task_id(ctx: CliContext, raw: str, run: str | None = None) -> UUID:
    if "@" in raw:
        raw, run = raw.rsplit("@", 1)
    if (value := as_uuid(raw.removeprefix("task:"))) is not None:
        return value
    if run is None:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "a task display key requires --run")
    view = ask(ctx, queries.ListTasks, run_id=str(run_id(ctx, run)))
    for item in view.tasks:
        if item["display_key"] == raw:
            return UUID(str(item["task_id"]))
    raise NotFound(ErrorCode.NOT_FOUND, f"task not found: {raw}")


def ask(ctx: CliContext, operation: Any, **payload: Any) -> Any:
    return ctx.client.ask(_dto(operation, payload))


def dispatch(ctx: CliContext, operation: Any, **payload: Any) -> Any:
    return ctx.client.dispatch(_dto(operation, payload), idempotency_key=ctx.new_idempotency_key())


def changes(ctx: CliContext, pairs: Sequence[str], *, level: str, scope_id: UUID) -> JsonObject:
    result: JsonObject = {}
    for pair in pairs:
        key, sep, text = pair.partition("=")
        if not key or not sep:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "expected KEY=VALUE")
        spec = _schema_spec(ctx, key, {"level": level, "scope_id": str(scope_id)})
        result[key] = parse_text_value(spec, text)
    return result


def show(ctx: CliContext, command: str, value: Any) -> int:
    document = to_jsonable(value)

    def human(_: Any) -> list[str]:
        if isinstance(document, dict) and isinstance(document.get("items"), list):
            items = cast("list[Any]", document["items"])
            if not items:
                return ["no entries"]
            rows = [cast("dict[str, Any]", item) for item in items]
            fields = list(dict.fromkeys(key for row in rows for key in row))
            return render_table(ctx, fields, [[_text(row.get(key)) for key in fields] for row in rows])
        if isinstance(document, dict):
            return kv_lines(ctx, [(key, _text(item)) for key, item in document.items()])
        return [_text(document)]

    return render(ctx, value, command=command, human=human)


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else str(value)


def named_query(ctx: CliContext, name: str, **payload: Any) -> Any:
    operation: Any = next(
        cast("Any", spec).dto
        for manifest in MANIFESTS
        for spec in manifest.queries
        if cast("Any", spec).name == name
    )
    return ask(ctx, operation, **payload)


def _dto(operation: Any, payload: dict[str, Any]) -> Any:
    fields = getattr(operation, "_FIELDS", ())
    required = {field[0] for field in fields if field[3]}
    # Optional generated fields use omission, not JSON null. Preserve required nullable fields such
    # as StartRun.readiness_report_id; those carry actual contract meaning.
    payload = {key: value for key, value in payload.items() if value is not None or key in required}
    try:
        return operation.from_json(payload)
    except (ValueError, TypeError, KeyError) as error:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid command arguments") from error


def _schema_spec(ctx: CliContext, key: str, scope: JsonObject) -> KeySpec:
    view = cast("GetSchemaView", ctx.client.ask(GetSchema.from_json({"scope": scope})))
    for section in view.sections:
        for declared in section.keys:
            if declared.key != key:
                continue
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
    raise ValidationFailed(ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown config key {key}")


__all__ = [
    "ask",
    "changes",
    "dispatch",
    "identifier",
    "named_query",
    "operations",
    "queries",
    "run_id",
    "show",
    "task_id",
]
