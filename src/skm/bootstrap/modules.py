"""Catalog of the 14 modules and their dependency graph (conventions §3.1, ADR 0003) and module selection.

``MODULE_CATALOG`` is the normative module graph in topological order (policy precedes extensions).
``MANIFESTS`` are the ``modules/<id>/module.py: MODULE`` declarations, loaded in catalog order and checked
against it. ``topological_order()`` and ``enabled_manifests()`` (kernel-platform §5.1) validate and select
them; ``section_index()`` and ``resolve_section_urns()`` turn the ``settings_sections`` ids into schema
URNs by ``x-skm-section.id`` of the packaged schemas (kernel-platform §2.12) before the registry build.
"""

import importlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.outcomes import Diagnostic, Severity
from skm.platform.schema.registry import SchemaRegistry

__all__ = [
    "MANIFESTS",
    "MODULE_CATALOG",
    "PLATFORM_SECTIONS",
    "ModuleCatalogEntry",
    "ModuleGraphError",
    "ModuleSelection",
    "enabled_manifests",
    "resolve_section_urns",
    "section_index",
    "select_modules",
    "topological_order",
]

# Settings sections owned by the platform (schemas ``owner: platform``); no module manifest lists them.
PLATFORM_SECTIONS: Final = (
    "modules",
    "plugins",
    "logging",
    "storage",
    "events",
    "background",
    "api",
    "ui",
    "ecosystems",
)


class ModuleGraphError(ValueError):
    """The graph is not a DAG over known modules (``kind``: unknown_dependency, cycle, duplicate_id, ...)."""

    def __init__(self, kind: str, message: str, *, module: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.module = module


@dataclass(frozen=True, slots=True)
class ModuleCatalogEntry:
    id: str
    depends_on: tuple[str, ...]  # every module whose public facade the module calls
    optional: bool
    db_schema: str
    settings_sections: tuple[str, ...]  # settings section ids owned by the module


MODULE_CATALOG: Final[tuple[ModuleCatalogEntry, ...]] = (
    ModuleCatalogEntry("access", (), False, "skm_access", ("access",)),
    ModuleCatalogEntry("settings", (), False, "skm_config", ()),
    ModuleCatalogEntry("workspace", ("access",), False, "skm_workspace", ("workspace",)),
    ModuleCatalogEntry("artifacts", ("access", "workspace"), False, "skm_artifacts", ("artifacts",)),
    ModuleCatalogEntry("policy", ("access", "workspace"), False, "skm_policy", ("policy",)),
    ModuleCatalogEntry(
        "extensions", ("access", "workspace", "policy"), False, "skm_extensions", ("extensions",)
    ),
    ModuleCatalogEntry(
        "runtimes", ("access", "workspace", "extensions"), False, "skm_runtimes", ("runtimes",)
    ),
    ModuleCatalogEntry(
        "planning",
        ("access", "workspace", "artifacts", "extensions", "runtimes"),
        False,
        "skm_planning",
        ("planning",),
    ),
    ModuleCatalogEntry(
        "context",
        ("access", "workspace", "planning", "extensions", "artifacts"),
        False,
        "skm_context",
        ("context",),
    ),
    ModuleCatalogEntry(
        "execution",
        ("access", "workspace", "artifacts", "extensions", "policy", "runtimes", "planning", "context"),
        False,
        "skm_execution",
        ("execution", "budgets", "worker", "checks"),
    ),
    ModuleCatalogEntry(
        "integrations",
        ("workspace", "artifacts", "extensions", "policy", "runtimes"),
        False,
        "skm_integrations",
        ("integrations", "hooks"),
    ),
    ModuleCatalogEntry("knowledge", ("access", "workspace"), True, "skm_knowledge", ("knowledge",)),
    ModuleCatalogEntry(
        "learning",
        ("access", "workspace", "runtimes", "execution", "knowledge"),
        True,
        "skm_learning",
        ("learning",),
    ),
    ModuleCatalogEntry(
        "exports", ("access", "workspace", "planning", "execution"), True, "skm_exports", ("exports",)
    ),
)


def _load_manifests() -> tuple[ModuleManifest, ...]:
    loaded: list[ModuleManifest] = []
    for entry in MODULE_CATALOG:
        manifest = cast("ModuleManifest", importlib.import_module(f"skm.modules.{entry.id}.module").MODULE)
        declared = (
            manifest.id,
            manifest.depends_on,
            manifest.optional,
            manifest.db_schema,
            manifest.settings_sections,
        )
        if declared != (entry.id, entry.depends_on, entry.optional, entry.db_schema, entry.settings_sections):
            raise ModuleGraphError(
                "catalog_mismatch", f"manifest of {entry.id!r} differs from MODULE_CATALOG", module=entry.id
            )
        loaded.append(manifest)
    return tuple(loaded)


MANIFESTS: Final[tuple[ModuleManifest, ...]] = _load_manifests()


def topological_order(manifests: Sequence[ModuleManifest]) -> tuple[str, ...]:
    """Module ids, every dependency before its dependants; ties keep the input order.

    ``ModuleGraphError`` for a duplicate id, an unknown dependency or a cycle.
    """
    graph: dict[str, tuple[str, ...]] = {}
    for manifest in manifests:
        if manifest.id in graph:
            raise ModuleGraphError("duplicate_id", f"duplicate module id {manifest.id!r}", module=manifest.id)
        graph[manifest.id] = manifest.depends_on
    order: list[str] = []
    done: set[str] = set()
    active: list[str] = []

    def visit(name: str) -> None:
        if name in done:
            return
        if name in active:
            cycle = " -> ".join([*active[active.index(name) :], name])
            raise ModuleGraphError("cycle", f"module dependency cycle: {cycle}", module=name)
        active.append(name)
        for dependency in graph[name]:
            if dependency not in graph:
                raise ModuleGraphError(
                    "unknown_dependency",
                    f"module {name!r} depends on unknown module {dependency!r}",
                    module=name,
                )
            visit(dependency)
        active.pop()
        done.add(name)
        order.append(name)

    for name in graph:
        visit(name)
    return tuple(order)


@dataclass(frozen=True, slots=True)
class ModuleSelection:
    """``manifests``: the enabled ones in topological order; ``disabled``: requested plus cascaded ids."""

    manifests: tuple[ModuleManifest, ...]
    disabled: frozenset[str]
    diagnostics: tuple[Diagnostic, ...]


def select_modules(manifests: Sequence[ModuleManifest], disabled: Iterable[str]) -> ModuleSelection:
    """Apply ``modules.<id>.enabled = false``: only optional modules may be disabled (``CONFIG_INVALID``).

    A module that depends on a disabled one is disabled too, with a ``MODULE_DISABLED`` warning; a required
    module that would have to be cascaded off is the same ``CONFIG_INVALID`` (it cannot be disabled).
    """
    order = topological_order(manifests)
    by_id = {manifest.id: manifest for manifest in manifests}
    requested = frozenset(disabled)
    for name in sorted(requested):
        if name not in by_id:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"modules.{name}.enabled refers to an unknown module",
                details={"key": f"modules.{name}.enabled", "reason": "unknown_module"},
            )
        if not by_id[name].optional:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"module {name!r} is required and cannot be disabled",
                details={"key": f"modules.{name}.enabled", "reason": "required_module"},
            )
    off = set(requested)
    diagnostics: list[Diagnostic] = []
    for name in order:
        if name in off:
            continue
        blockers = [dependency for dependency in by_id[name].depends_on if dependency in off]
        if not blockers:
            continue
        if not by_id[name].optional:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"required module {name!r} depends on disabled module {blockers[0]!r}",
                details={
                    "key": f"modules.{blockers[0]}.enabled",
                    "reason": "required_dependant",
                    "module": name,
                },
            )
        off.add(name)
        diagnostics.append(
            Diagnostic(
                ErrorCode.MODULE_DISABLED,
                f"module {name!r} is disabled because it depends on disabled {blockers[0]!r}",
                Severity.WARNING,
                target=f"modules.{name}.enabled",
            )
        )
    from skm.modules.integrations.module import bind_hook_subscribers

    selected = tuple(by_id[name] for name in order if name not in off)
    return ModuleSelection(bind_hook_subscribers(selected), frozenset(off), tuple(diagnostics))


def enabled_manifests(
    manifests: Sequence[ModuleManifest], disabled: frozenset[str]
) -> tuple[ModuleManifest, ...]:
    return select_modules(manifests, disabled).manifests


def section_index(schemas: SchemaRegistry) -> Mapping[str, str]:
    """``x-skm-section.id`` -> schema ``$id``; a duplicate id is ``CONFIG_REGISTRY_INVALID``."""
    index: dict[str, str] = {}
    for urn in sorted(schemas.urns()):
        section = schemas.get(urn).get("x-skm-section")
        if not isinstance(section, dict):
            continue
        section_id = cast("dict[str, object]", section).get("id")
        if not isinstance(section_id, str):
            raise InternalError(
                ErrorCode.CONFIG_REGISTRY_INVALID,
                f"{urn} has an x-skm-section without a string id",
                details={"schema": urn},
            )
        if section_id in index:
            raise InternalError(
                ErrorCode.CONFIG_REGISTRY_INVALID,
                f"settings section id {section_id!r} is declared by {index[section_id]} and {urn}",
                details={"section": section_id, "schemas": [index[section_id], urn]},
            )
        index[section_id] = urn
    return index


def resolve_section_urns(
    manifests: Sequence[ModuleManifest],
    schemas: SchemaRegistry,
    *,
    platform_sections: Sequence[str] = PLATFORM_SECTIONS,
) -> tuple[str, ...]:
    """Schema URNs of the manifests' ``settings_sections`` followed by the platform's, in declaration order.

    A missing id or an id claimed twice (by two manifests or a manifest and the platform) is
    ``CONFIG_REGISTRY_INVALID``; the check runs before ``SettingsRegistry.build``.
    """
    index = section_index(schemas)
    claimed: dict[str, str] = {}
    urns: list[str] = []
    wanted = [(manifest.id, section) for manifest in manifests for section in manifest.settings_sections]
    wanted.extend(("platform", section) for section in platform_sections)
    for owner, section in wanted:
        if section in claimed:
            raise InternalError(
                ErrorCode.CONFIG_REGISTRY_INVALID,
                f"settings section {section!r} is listed by {claimed[section]!r} and {owner!r}",
                details={"section": section, "owners": [claimed[section], owner]},
            )
        if section not in index:
            raise InternalError(
                ErrorCode.CONFIG_REGISTRY_INVALID,
                f"settings section {section!r} of {owner!r} has no schema with that x-skm-section.id",
                details={"section": section, "owner": owner},
            )
        claimed[section] = owner
        urns.append(index[section])
    return tuple(urns)
