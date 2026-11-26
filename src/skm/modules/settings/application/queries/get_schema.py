"""``settings.get_schema`` (settings §A.8): the sections and key metadata of the registry, for forms and
completion. ``schema`` is the section schema document as packaged; a section outside the packaged schemas
(a plugin section) gets a flat object schema of its keys instead.

The registry is one per instance: ``scope`` (default instance) only selects where the bus checks
``config.read`` before any metadata is read, as for ``get_generation``. A named scope must also be the
scope the bus resolved (``INVALID_REFERENCE``), so the right confirmed is the right of that scope.
"""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.project_keys import MACHINE_ONLY_KEYS
from skm.modules.settings.application.rights import packaged_schemas
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.generated.queries import GetSchema
from skm.modules.settings.generated.views import GetSchemaView
from skm.platform.config.keys import CHAIN_LEVELS, MISSING, KeySpec, copy_json
from skm.platform.config.registry import SectionInfo, SettingsRegistry

__all__ = ["SPEC", "handle"]


def key_view(spec: KeySpec) -> JsonObject:
    """``KeySpecView`` of settings §A.8."""
    order = CHAIN_LEVELS[spec.chain]
    view: JsonObject = {
        "key": spec.key,
        "section": spec.section,
        "chain": spec.chain.value,
        "levels": [level.value for level in sorted(spec.levels, key=order.index)],
        "merge": spec.merge.value,
        "reload": spec.reload.value,
        "override": spec.override,
        "sensitivity": spec.sensitivity.value,
        "portable": spec.portable,
        "lockable": spec.lockable,
        "nullable": spec.nullable,
        "pack": spec.pack,
        "confirm": spec.confirm,
        "value_schema": copy_json(dict(spec.value_schema), spec.key),
        "validators": list(spec.validators),
        "ui": {
            name: value
            for name, value in (
                ("group", spec.ui.group),
                ("order", spec.ui.order),
                ("widget", spec.ui.widget),
                ("advanced", spec.ui.advanced),
                ("title", spec.ui.title),
                ("help_url", spec.ui.help_url),
            )
            if value is not None
        },
    }
    if spec.default is not MISSING:
        view["default"] = copy_json(spec.default, spec.key)
    if spec.narrow is not None:
        narrow: JsonObject = {}
        if spec.narrow.direction is not None:
            narrow["direction"] = spec.narrow.direction.value
        if spec.narrow.order is not None:
            narrow["order"] = list(spec.narrow.order)
        if spec.narrow.unlimited is not MISSING:
            narrow["unlimited"] = copy_json(spec.narrow.unlimited, spec.key)
        view["narrow"] = narrow
    if spec.deprecated is not None:
        deprecated: JsonObject = {"since": spec.deprecated.since}
        if spec.deprecated.replacement is not None:
            deprecated["replacement"] = spec.deprecated.replacement
        if spec.deprecated.until is not None:
            deprecated["until"] = spec.deprecated.until
        view["deprecated"] = deprecated
    return view


def _project_schema(schema: JsonObject, prefix: str) -> JsonObject:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        removed: set[str] = set()
        for name, child in tuple(properties.items()):
            key = f"{prefix}.{name}"
            if key in MACHINE_ONLY_KEYS:
                del properties[name]
                removed.add(name)
            elif isinstance(child, dict) and "x-skm" not in child:
                _project_schema(child, key)
        required = schema.get("required")
        if removed and isinstance(required, list):
            schema["required"] = [
                name for name in required if not isinstance(name, str) or name not in removed
            ]
    return schema


def _schema(section: SectionInfo, registry: SettingsRegistry) -> JsonObject:
    schemas = packaged_schemas()
    if section.schema_urn in schemas.urns():
        return _project_schema(copy_json(schemas.get(section.schema_urn), section.id), section.id)
    properties: dict[str, JsonValue] = {
        key: copy_json(dict(registry.spec(key).value_schema), key)
        for key in section.keys
        if key not in MACHINE_ONLY_KEYS
    }
    return {"$id": section.schema_urn, "title": section.title, "type": "object", "properties": properties}


def handle(query: GetSchema, ctx: QueryContext, uow: UnitOfWork) -> GetSchemaView:
    if query.scope is not None:
        resolve_target_scope(uow, query.scope, ctx.scope_chain)  # INVALID_REFERENCE
    registry = ctx.config.registry
    sections = registry.sections() if query.section is None else (registry.section(query.section),)
    document: JsonObject = {
        "registry_digest": registry.digest,
        "sections": [
            {
                "id": section.id,
                "owner": section.owner,
                "title": section.title,
                "schema_urn": section.schema_urn,
                "schema": _schema(section, registry),
                "validators": [validator.id for validator in section.validators],
                "keys": [
                    key_view(registry.spec(key)) for key in section.keys if key not in MACHINE_ONLY_KEYS
                ],
            }
            for section in sections
        ],
    }
    return GetSchemaView.from_json(document)


SPEC = QuerySpec(
    name="settings.get_schema",
    dto=GetSchema,
    result=GetSchemaView,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
