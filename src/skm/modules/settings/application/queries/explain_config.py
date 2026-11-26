"""``settings.explain_config`` (settings §A.8, §B.8.1): the explain report of a scope chain.

The chain follows the scope level (host → host chain, else work chain) and never contains the invocation
layer of the serving process. Without ``keys``/``section`` every key of the chain is reported;
``include_defaults_only=false`` keeps only keys with a contribution other than the default; ``detail=value``
drops the contribution trace and the narrowing base. A key of the other chain is
``CONFIG_SCOPE_NOT_ALLOWED`` with a hint which scope level explains it.

The report is the generated ``ExplainReport`` (a JSON-mode TypedDict of ``urn:skm:config:explain:v1``);
``ExplainConfigResult`` is its bus result wrapper with ``SCHEMA_URN`` and ``to_json``.
"""

from dataclasses import dataclass
from typing import ClassVar, cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.preview import Preview, chain_kind
from skm.modules.settings.application.project_keys import MACHINE_ONLY_KEYS, require_project_key
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.generated.queries import ExplainConfig
from skm.modules.settings.generated.views import (
    ExplainReport,
    explain_report_from_json,
    explain_report_to_json,
)
from skm.platform.config.explain import build_explain
from skm.platform.config.keys import Chain
from skm.platform.config.store import PackConfigSource

__all__ = ["SPEC", "ExplainConfigResult", "handle"]


@dataclass(frozen=True, slots=True)
class ExplainConfigResult:
    report: ExplainReport

    SCHEMA_URN: ClassVar[str] = "urn:skm:config:explain:v1"

    def to_json(self) -> JsonObject:
        return cast("JsonObject", explain_report_to_json(self.report))


def _selected(query: ExplainConfig, ctx: QueryContext, kind: Chain) -> list[str]:
    registry = ctx.config.registry
    section = None if query.section is None else registry.section(query.section).id
    if query.keys is None:
        return [
            spec.key
            for spec in registry.keys(chain=kind, section=section)
            if spec.key not in MACHINE_ONLY_KEYS
        ]
    keys = list(dict.fromkeys(query.keys))
    for key in keys:
        require_project_key(key)
    return keys if section is None else [key for key in keys if registry.spec(key).section == section]


def handle(query: ExplainConfig, ctx: QueryContext, uow: UnitOfWork) -> ExplainConfigResult:
    target = resolve_target_scope(uow, query.scope, ctx.scope_chain)
    kind = chain_kind(target.ref.level)
    selected = _selected(query, ctx, kind)
    preview = Preview(uow, ctx.config.registry, uow.repo(PackConfigSource), target.ref)
    try:
        effective = preview.current(kind, selected)
    except ValidationFailed as err:
        if err.code is not ErrorCode.CONFIG_SCOPE_NOT_ALLOWED:
            raise
        hint = "host" if kind is Chain.WORK else "instance, workspace, project, plan or run"
        raise ValidationFailed(
            err.code, f"{err.message}; explain it at a {hint} scope", details={**err.details, "hint": hint}
        ) from err
    report = build_explain(effective, keys=selected, include_defaults_only=query.include_defaults_only)
    if query.detail == "value":
        keys = report["keys"]
        for item in keys if isinstance(keys, list) else ():
            if isinstance(item, dict):
                item["contributions"] = []
                item.pop("base", None)
    return ExplainConfigResult(report=explain_report_from_json(report))


SPEC = QuerySpec(
    name="settings.explain_config",
    dto=ExplainConfig,
    result=ExplainConfigResult,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
