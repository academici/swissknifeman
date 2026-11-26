"""Facade of the extensions module (extensions §13).

Every function uses the caller's transaction. The effective configuration belongs to the caller's
scope. ``pins`` (K19) keep a run inside the pack versions of its bundle.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.platform.jsonc.digest import digest

from .application.candidate import build_candidate, parse_text_resource
from .application.install import install_candidate
from .application.resolving import (
    active_decision,
    chosen_pack_versions,
    decide,
    resolved_keys,
    resource_version_view,
    selected_packs,
)
from .domain.agent_profile import (
    AgentPermissions,
    AgentProfile,
    ContextPolicySpec,
    PromptPlan,
    RoleLimits,
    parse_agent_profile,
    require_role,
)
from .domain.agent_profile import default_profile_key as _default_profile_key
from .domain.keys import PackId, PackSlug, PackVersionId, ResourceId, ResourceKey, SemVer, VersionConstraint
from .domain.kinds import KindSpec, ResourceKind
from .domain.pack import ExclusiveGroup, PackManifest, PackPins, PackState, PackTrust
from .domain.payload import PackPayload, PayloadFile, check_payload_limits
from .domain.prompt_block import PromptBlockManifest
from .domain.resolution import require_chosen
from .domain.resource import ResourceRef, ResourceVersion, RuntimeCatalogEntry, RuntimeCatalogView
from .domain.skill import SkillManifest
from .domain.steering import SteeringManifest
from .generated.views import ResourceVersionView
from .ports import PackRepository, ResourceRepository

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.clock import Clock
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ids import PrincipalId, ResourceVersionId
    from skm.kernel.json_types import JsonObject
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.scopes import ScopeRef
    from skm.kernel.tokens import TokenEstimator
    from skm.platform.config import EffectiveConfig


_CATALOG_SNAPSHOT_ORIGIN = "runtime_catalog_snapshot"


def _resolved_id(
    uow: UnitOfWork, kind: ResourceKind, key: ResourceKey, *, config: EffectiveConfig, pins: PackPins | None
) -> ResourceVersionId:
    decision, _diagnostics, missing = decide(uow, kind, key, config=config, pins=pins)
    return require_chosen(decision, missing_packs=missing).id


def resolve_resource(
    uow: UnitOfWork,
    kind: ResourceKind,
    key: ResourceKey,
    *,
    config: EffectiveConfig,
    pins: PackPins | None = None,
) -> ResourceVersionView:
    return resource_version_view(uow, _resolved_id(uow, kind, key, config=config, pins=pins))


def get_resource_version(
    uow: UnitOfWork, version_id: ResourceVersionId, *, include_bodies: bool = False
) -> ResourceVersionView:
    return resource_version_view(uow, version_id, include_bodies=include_bodies)


def known_keys(
    uow: UnitOfWork, kind: ResourceKind, *, config: EffectiveConfig, pins: PackPins | None = None
) -> frozenset[ResourceKey]:
    return frozenset(resolved_keys(uow, kind, config=config, pins=pins))


def list_resolved(
    uow: UnitOfWork, kind: ResourceKind, *, config: EffectiveConfig, pins: PackPins | None = None
) -> tuple[ResourceVersionView, ...]:
    """Every resolved resource of a kind by key; a key whose candidates are all quarantined is not listed."""
    found: list[ResourceVersionView] = []
    for key in resolved_keys(uow, kind, config=config, pins=pins):
        version_id = active_decision(uow, kind, key, config=config, pins=pins)
        if version_id is not None:
            found.append(resource_version_view(uow, version_id))
    return tuple(found)


def pinned_pack_versions(uow: UnitOfWork, *, config: EffectiveConfig) -> PackPins:
    """The snapshot of ``choose_pack_versions`` for the bundle of a run; a missing pack is ``NOT_FOUND``."""
    choices, missing = chosen_pack_versions(uow, config)
    if missing:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "no fitting version of an enabled pack is installed",
            details={"kind": "pack_version", "pack": sorted(missing)[0]},
        )
    return {choice.slug: choice.version_id for choice in choices}


def load_agent_profile(uow: UnitOfWork, version_id: ResourceVersionId) -> AgentProfile:
    version = uow.repo(ResourceRepository).get_version(version_id).version
    if version.kind is not ResourceKind.AGENT_PROFILE:
        raise PreconditionFailed(
            ErrorCode.EXTENSION_INCOMPATIBLE,
            "the resource version is not an agent profile",
            details={"reason": "not_an_agent_profile", "kind": version.kind.value, "key": version.key},
        )
    return parse_agent_profile(version.manifest)


def select_agent_profile(
    uow: UnitOfWork,
    role: str,
    *,
    stage_profile: ResourceKey | None,
    config: EffectiveConfig,
    pins: PackPins | None = None,
) -> ResourceVersionView:
    """§4.6 rule 2: stage parameter, then ``extensions.role_profiles.<role>``, then the default key."""
    profiles = cast("Mapping[str, str]", config.get("extensions.role_profiles"))
    key = stage_profile or profiles.get(role) or _default_profile_key(role)
    view = resolve_resource(uow, ResourceKind.AGENT_PROFILE, key, config=config, pins=pins)
    require_role(view.manifest.get("role"), key=key, expected=role)
    return view


def default_profile_key(role: str) -> ResourceKey:
    return _default_profile_key(role)


def load_text_resource(uow: UnitOfWork, version_id: ResourceVersionId) -> tuple[JsonObject, str]:
    """``(meta, body)`` of a steering or prompt block version."""
    found = uow.repo(ResourceRepository).get_version(version_id, include_bodies=True)
    if found.version.kind not in (ResourceKind.STEERING, ResourceKind.PROMPT_BLOCK):
        raise PreconditionFailed(
            ErrorCode.EXTENSION_INCOMPATIBLE,
            "the resource version is not a text resource",
            details={
                "reason": "not_a_text_resource",
                "kind": found.version.kind.value,
                "key": found.version.key,
            },
        )
    bodies = found.bodies or {}
    path = found.version.files[0].path
    return parse_text_resource(bodies[path].decode("utf-8"), path)


def exclusive_groups(
    uow: UnitOfWork, *, config: EffectiveConfig, pins: PackPins | None = None
) -> Mapping[str, ExclusiveGroup]:
    """The groups of the selected (or pinned) pack versions; the strongest pack wins a repeated name."""
    choices, _diagnostics = selected_packs(uow, config, pins)
    packs = uow.repo(PackRepository)
    found: dict[str, ExclusiveGroup] = {}
    for choice in sorted(choices, key=lambda item: (item.priority, item.slug)):
        for group in packs.get_version(choice.version_id).manifest.exclusive_groups:
            found[group.name] = group
    return found


def runtime_catalog(
    uow: UnitOfWork, scope_chain: Sequence[ScopeRef], config: EffectiveConfig, *, pins: PackPins | None = None
) -> RuntimeCatalogView | None:
    """Every resolved ``runtime_catalog:*`` by key.

    No resource: ``None``, a quarantined one: ``RESOURCE_QUARANTINED``. Parsing and merging belong to
    ``runtimes``; ``config`` already carries the levels of ``scope_chain``.
    """
    del scope_chain
    entries: list[RuntimeCatalogEntry] = []
    packs = uow.repo(PackRepository)
    for key in resolved_keys(uow, ResourceKind.RUNTIME_CATALOG, config=config, pins=pins):
        version_id = _resolved_id(uow, ResourceKind.RUNTIME_CATALOG, key, config=config, pins=pins)
        found = uow.repo(ResourceRepository).get_version(version_id, include_bodies=True)
        bodies = found.bodies or {}
        pack = packs.get_version(found.version.pack_version_id)
        entries.append(
            RuntimeCatalogEntry(
                resource_version_id=found.version.id,
                key=found.version.key,
                digest=found.version.digest,
                manifest=dict(found.version.manifest),
                body=bodies[found.version.files[0].path].decode("utf-8"),
                is_operator_snapshot=pack.origin == _CATALOG_SNAPSHOT_ORIGIN,
            )
        )
    if not entries:
        return None
    return RuntimeCatalogView(tuple(entries), digest(sorted(entry.digest for entry in entries)))


def publish_runtime_catalog_snapshot(  # noqa: PLR0913 -- caller UoW plus the snapshot payload and publication dependencies
    uow: UnitOfWork,
    *,
    pack_manifest: str,
    catalog_toml: str,
    installed_by: PrincipalId,
    clock: Clock,
    ids: IdGenerator,
    config: EffectiveConfig,
    estimator: TokenEstimator,
    resource_key: str = "models",
) -> InstallPackResult:
    """Install an immutable operator catalog pack version in the caller's write UoW.

    The caller authorizes publication. The version uses the regular pack override, compatibility and replay
    rules. Config selects the active version for new reads. Existing PackPins keep selecting their version.
    """
    contents = catalog_toml.encode("utf-8")
    check_payload_limits(
        1, len(contents), max_bytes=cast("int", config.get("extensions.install.max_archive_bytes"))
    )
    candidate = build_candidate(
        PackPayload(pack_manifest, (PayloadFile(f"runtimes/{resource_key}.toml", contents),)),
        estimator=estimator,
        allowed_licenses=frozenset(cast("list[str]", config.get("extensions.compat.allowed_licenses"))),
    )
    if candidate.manifest.config or candidate.manifest.exclusive_groups:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "a catalog snapshot pack contains only catalog data")
    return install_candidate(
        candidate,
        origin=_CATALOG_SNAPSHOT_ORIGIN,
        trust=PackTrust.OPERATOR,
        installed_by=installed_by,
        clock=clock,
        ids=ids,
        config=config,
        uow=uow,
        allow_quarantine=False,
    )


if TYPE_CHECKING:
    from .generated.commands import (
        InstallPack as InstallPack,
    )
    from .generated.commands import (
        QuarantineResource as QuarantineResource,
    )
    from .generated.commands import (
        ReleaseQuarantine as ReleaseQuarantine,
    )
    from .generated.commands import (
        SyncBuiltinPacks as SyncBuiltinPacks,
    )
    from .generated.commands import (
        UninstallPackVersion as UninstallPackVersion,
    )
    from .generated.queries import (
        GetPack as GetPack,
    )
    from .generated.queries import (
        GetResourceVersion as GetResourceVersion,
    )
    from .generated.queries import (
        ListPacks as ListPacks,
    )
    from .generated.queries import (
        ListResources as ListResources,
    )
    from .generated.queries import (
        ResolveResource as ResolveResource,
    )
    from .generated.results import (
        InstallPackResult as InstallPackResult,
    )
    from .generated.results import (
        QuarantineResourceResult as QuarantineResourceResult,
    )
    from .generated.results import (
        ReleaseQuarantineResult as ReleaseQuarantineResult,
    )
    from .generated.results import (
        SyncBuiltinPacksResult as SyncBuiltinPacksResult,
    )
    from .generated.results import (
        UninstallPackVersionResult as UninstallPackVersionResult,
    )
    from .generated.views import (
        PacksView as PacksView,
    )
    from .generated.views import (
        PackView as PackView,
    )
    from .generated.views import (
        ResolutionView as ResolutionView,
    )
    from .generated.views import (
        ResourcesView as ResourcesView,
    )

_LAZY_EXPORTS: dict[str, str] = {
    **dict.fromkeys(
        (
            "InstallPack",
            "QuarantineResource",
            "ReleaseQuarantine",
            "SyncBuiltinPacks",
            "UninstallPackVersion",
        ),
        ".generated.commands",
    ),
    **dict.fromkeys(
        ("GetPack", "GetResourceVersion", "ListPacks", "ListResources", "ResolveResource"),
        ".generated.queries",
    ),
    **dict.fromkeys(
        (
            "InstallPackResult",
            "QuarantineResourceResult",
            "ReleaseQuarantineResult",
            "SyncBuiltinPacksResult",
            "UninstallPackVersionResult",
        ),
        ".generated.results",
    ),
    **dict.fromkeys(("PackView", "PacksView", "ResolutionView", "ResourcesView"), ".generated.views"),
}


def __getattr__(name: str) -> object:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __package__), name)
    globals()[name] = value
    return value


__all__ = [
    "AgentPermissions",
    "AgentProfile",
    "ContextPolicySpec",
    "ExclusiveGroup",
    "GetPack",
    "GetResourceVersion",
    "InstallPack",
    "InstallPackResult",
    "KindSpec",
    "ListPacks",
    "ListResources",
    "PackId",
    "PackManifest",
    "PackPins",
    "PackSlug",
    "PackState",
    "PackTrust",
    "PackVersionId",
    "PackView",
    "PacksView",
    "PromptBlockManifest",
    "PromptPlan",
    "QuarantineResource",
    "QuarantineResourceResult",
    "ReleaseQuarantine",
    "ReleaseQuarantineResult",
    "ResolutionView",
    "ResolveResource",
    "ResourceId",
    "ResourceKey",
    "ResourceKind",
    "ResourceRef",
    "ResourceVersion",
    "ResourceVersionView",
    "ResourcesView",
    "RoleLimits",
    "RuntimeCatalogEntry",
    "RuntimeCatalogView",
    "SemVer",
    "SkillManifest",
    "SteeringManifest",
    "SyncBuiltinPacks",
    "SyncBuiltinPacksResult",
    "UninstallPackVersion",
    "UninstallPackVersionResult",
    "VersionConstraint",
    "default_profile_key",
    "exclusive_groups",
    "get_resource_version",
    "known_keys",
    "list_resolved",
    "load_agent_profile",
    "load_text_resource",
    "pinned_pack_versions",
    "publish_runtime_catalog_snapshot",
    "resolve_resource",
    "runtime_catalog",
    "select_agent_profile",
]
