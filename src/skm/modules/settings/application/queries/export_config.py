"""``settings.export_config`` (settings §A.8): the entries of one scope as a document (§B.11.4).

Only the entries stored at the scope are exported, never effective values: a scope without an entry exports
the absence of the key, so importing the document elsewhere creates no override and the inherited value keeps
following its farther level. ``portable_only`` drops keys with ``portable=false``; entries of keys missing
from the registry are not exported (no import accepts them). The rendering is deterministic (sorted keys).
``digest`` is the ``entries_digest`` of every entry of the scope: the CAS value for
``import_config.expected_entries_digest`` against the same scope.
"""

from dataclasses import dataclass
from typing import Any, cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.project_keys import project_keys
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.application.write_flow import entry_view, safe_value
from skm.modules.settings.domain.digest import entries_digest
from skm.modules.settings.domain.entry import EntryOp
from skm.modules.settings.generated.queries import ExportConfig
from skm.modules.settings.generated.views import ExportConfigView
from skm.modules.settings.ports import ConfigEntryRepository
from skm.platform.config.sources.document import render_document

__all__ = ["SPEC", "handle"]


@dataclass(frozen=True, slots=True)
class _Row:
    key: str
    op: str
    value: JsonValue
    locked: bool


def _nested(document: JsonObject) -> JsonObject:
    """The JSON document with every section table nested by the key path (``{"run": {"max_usd": …}}``
    instead of ``{"run.max_usd": …}``), the shape of ``urn:skm:settings:document:v1``; values stay whole."""
    nested: JsonObject = {}
    for name, table in document.items():
        if name in ("schema", "unset", "lock", "append") or not isinstance(table, dict):
            nested[name] = table
            continue
        section: JsonObject = {}
        for path, value in table.items():
            *groups, leaf = path.split(".")
            node = section
            for group in groups:
                node = cast("JsonObject", node.setdefault(group, {}))
            node[leaf] = value
        nested[name] = section
    return nested


def handle(query: ExportConfig, ctx: QueryContext, uow: UnitOfWork) -> ExportConfigView:
    target = resolve_target_scope(uow, query.scope, ctx.scope_chain)
    registry = ctx.config.registry
    stored = project_keys(uow.repo(ConfigEntryRepository).entries_of_scope(target.scope.id))
    exported = [
        (entry, spec)
        for entry in stored.values()
        if (spec := registry.find(entry.key)) is not None and (spec.portable or not query.portable_only)
    ]
    rows = [
        _Row(
            entry.key,
            entry.op.value,
            None if entry.op is EntryOp.UNSET else safe_value(spec, entry.value),
            entry.locked,
        )
        for entry, spec in exported
    ]
    document = render_document(rows, registry, fmt=query.format)
    return ExportConfigView(
        format=query.format,
        document=document if isinstance(document, str) else cast("Any", _nested(document)),
        entries=tuple(entry_view(entry, target.label, spec) for entry, spec in exported),
        digest=entries_digest(stored),
    )


SPEC = QuerySpec(
    name="settings.export_config",
    dto=ExportConfig,
    result=ExportConfigView,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
