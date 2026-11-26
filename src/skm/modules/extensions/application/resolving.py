"""Reads of the resolved resources in the caller's transaction (extensions §4.12, §13).

``config`` is the effective configuration of the caller's scope. With ``pins`` (K19) the enabled packs and
their constraints are not consulted: resolution stays inside exactly the pinned pack versions; the quarantine
and the resource pins of steps 5-6 still apply, a quarantined pinned resource is never replaced by another
version.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, cast

from skm.kernel.outcomes import Diagnostic
from skm.modules.extensions.domain.keys import VersionConstraint
from skm.modules.extensions.domain.pack import CORE_PACK
from skm.modules.extensions.domain.resolution import (
    PackChoice,
    ResolutionDecision,
    ResolutionOutcome,
    choices_from_pins,
    choose_pack_versions,
    parse_resource_pin,
    require_chosen,
    resolve,
)
from skm.modules.extensions.generated.views import (
    ResourceKind as ViewKind,
)
from skm.modules.extensions.generated.views import (
    ResourceVersionView,
    ResourceVersionViewFilesItem,
)
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import ResourceVersionId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.extensions.domain.kinds import ResourceKind
    from skm.modules.extensions.domain.pack import PackPins
    from skm.modules.extensions.domain.resource import ResourceVersionWithBodies
    from skm.platform.config import EffectiveConfig

__all__ = [
    "active_decision",
    "chosen_pack_versions",
    "decide",
    "resolved_keys",
    "resource_version_view",
    "selected_packs",
    "version_view",
]


def _priorities(config: EffectiveConfig) -> Mapping[str, int]:
    return cast("Mapping[str, int]", config.get("extensions.packs.priority"))


def selected_packs(
    uow: UnitOfWork, config: EffectiveConfig, pins: PackPins | None
) -> tuple[tuple[PackChoice, ...], tuple[Diagnostic, ...]]:
    installed = uow.repo(PackRepository).list_versions()
    if pins is not None:
        return choices_from_pins(pins, installed, priorities=_priorities(config)), ()
    enabled = cast("list[str]", config.get("extensions.packs.enabled"))
    versions = cast("Mapping[str, str]", config.get("extensions.packs.versions"))
    return choose_pack_versions(
        [CORE_PACK, *enabled],
        {slug: VersionConstraint.parse(text) for slug, text in versions.items()},
        installed,
        priorities=_priorities(config),
    )


def chosen_pack_versions(
    uow: UnitOfWork, config: EffectiveConfig
) -> tuple[tuple[PackChoice, ...], tuple[str, ...]]:
    """The snapshot of a run and the packs without a fitting version (``PACK_NOT_INSTALLED``)."""
    choices, diagnostics = selected_packs(uow, config, None)
    return choices, tuple(item.target or "" for item in diagnostics)


def decide(
    uow: UnitOfWork, kind: ResourceKind, key: str, *, config: EffectiveConfig, pins: PackPins | None
) -> tuple[ResolutionDecision, tuple[Diagnostic, ...], tuple[str, ...]]:
    choices, diagnostics = selected_packs(uow, config, pins)
    versions = uow.repo(ResourceRepository).versions_of(kind, key, [choice.version_id for choice in choices])
    quarantine = uow.repo(QuarantineRepository).quarantined_ids([row.id for row in versions])
    pinned = cast("Mapping[str, str]", config.get("extensions.resources.pinned")).get(f"{kind.value}:{key}")
    pin = None if pinned is None else parse_resource_pin(pinned)
    decision = resolve(kind, key, choices, versions, quarantine, pin)
    return decision, diagnostics, tuple(item.target or "" for item in diagnostics)


def resolved_keys(
    uow: UnitOfWork, kind: ResourceKind, *, config: EffectiveConfig, pins: PackPins | None
) -> tuple[str, ...]:
    """Keys of the kind in the selected pack versions, sorted."""
    choices, _diagnostics = selected_packs(uow, config, pins)
    rows = uow.repo(ResourceRepository).list_in_pack_versions(
        [choice.version_id for choice in choices], kind=kind
    )
    return tuple(sorted({row.key for row in rows}))


def active_decision(
    uow: UnitOfWork, kind: ResourceKind, key: str, *, config: EffectiveConfig, pins: PackPins | None
) -> ResourceVersionId | None:
    """The version of a key for a list of resolved resources; only quarantined versions: skipped."""
    decision, _diagnostics, missing = decide(uow, kind, key, config=config, pins=pins)
    if decision.outcome is ResolutionOutcome.QUARANTINED:
        return None
    return require_chosen(decision, missing_packs=missing).id


def _body_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:  # §8: a binary file travels as base64
        return base64.b64encode(content).decode("ascii")


def version_view(found: ResourceVersionWithBodies) -> ResourceVersionView:
    version = found.version
    return ResourceVersionView(
        resource_version_id=version.id,
        kind=ViewKind(version.kind.value),
        key=version.key,
        version=str(version.version),
        digest=version.digest,
        pack_version_id=version.pack_version_id,
        manifest=dict(version.manifest),
        files=tuple(
            ResourceVersionViewFilesItem(path=item.path, size_bytes=item.size_bytes, digest=item.digest)
            for item in version.files
        ),
        bodies=None
        if found.bodies is None
        else {path: _body_text(body) for path, body in found.bodies.items()},
    )


def resource_version_view(
    uow: UnitOfWork, version_id: ResourceVersionId, *, include_bodies: bool = False
) -> ResourceVersionView:
    return version_view(uow.repo(ResourceRepository).get_version(version_id, include_bodies=include_bodies))
