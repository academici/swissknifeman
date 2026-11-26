"""Packs and their immutable versions (extensions §4.3).

``parse_pack_manifest`` takes a document already validated by ``urn:skm:extensions:pack:v1`` and adds the
semantics a schema cannot express. A version stays immutable except its ``state``; ``trust = builtin`` belongs
only to the ``builtin`` origin of ``skm/_resources/packs``, and no surface can claim that origin.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.modules.extensions.domain.keys import SemVer, VersionConstraint, parse_pack_slug, parse_resource_key
from skm.modules.extensions.domain.kinds import ResourceKind

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from skm.kernel.ids import PrincipalId
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.extensions.domain.keys import PackId, PackSlug, PackVersionId, ResourceKey

__all__ = [
    "BUILTIN_ORIGIN",
    "CORE_PACK",
    "DEFAULT_PRIORITY",
    "TRUST_RANK",
    "Digest",
    "ExclusiveGroup",
    "Pack",
    "PackManifest",
    "PackOverride",
    "PackPins",
    "PackState",
    "PackTrust",
    "PackVersion",
    "PackVersionSummary",
    "manifest_to_json",
    "parse_pack_manifest",
    "require_external_origin",
]

type Digest = str

BUILTIN_ORIGIN: Final = "builtin"
CORE_PACK: Final = "core"  # always active (config catalog: extensions.packs.enabled)
_EXTERNAL_ORIGIN: Final = re.compile(r"(path|archive):.{1,200}")


class PackTrust(StrEnum):
    BUILTIN = "builtin"
    OPERATOR = "operator"
    THIRD_PARTY = "third_party"


TRUST_RANK = {PackTrust.BUILTIN: 2, PackTrust.OPERATOR: 3, PackTrust.THIRD_PARTY: 1}
DEFAULT_PRIORITY: Final = {PackTrust.BUILTIN: 0, PackTrust.OPERATOR: 100, PackTrust.THIRD_PARTY: -100}


class PackState(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ExclusiveGroup:
    name: str
    max: int
    description: str


@dataclass(frozen=True, slots=True)
class PackOverride:
    kind: ResourceKind
    key: ResourceKey
    reason: str


@dataclass(frozen=True, slots=True)
class PackManifest:
    slug: PackSlug
    version: SemVer
    title: str
    description: str
    publisher: str
    trust: PackTrust
    priority: int
    license: str
    requires_skm: VersionConstraint
    config: Mapping[str, JsonValue]
    exclusive_groups: tuple[ExclusiveGroup, ...]
    overrides: tuple[PackOverride, ...]


@dataclass(frozen=True, slots=True)
class Pack:
    id: PackId
    slug: PackSlug
    title: str
    publisher: str
    trust: PackTrust
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PackVersion:
    id: PackVersionId
    pack_id: PackId
    version: SemVer
    digest: Digest
    manifest: PackManifest
    state: PackState
    origin: str
    installed_at: datetime
    installed_by: PrincipalId


@dataclass(frozen=True, slots=True)
class PackVersionSummary:
    """A row of ``pack_versions`` with its pack: what resolution and the pack lists need."""

    version_id: PackVersionId
    pack_id: PackId
    slug: PackSlug
    title: str
    trust: PackTrust
    version: SemVer
    digest: Digest
    priority: int
    state: PackState
    installed_at: datetime


type PackPins = Mapping[PackSlug, PackVersionId]


def _invalid(reason: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID, f"pack manifest: {reason}", details={"reason": reason, **details}
    )


def parse_pack_manifest(data: Mapping[str, object]) -> PackManifest:
    try:
        trust = PackTrust(cast("str", data["trust"]))
        groups = cast("list[Mapping[str, object]]", data.get("exclusive_groups", []))
        overrides = cast("list[Mapping[str, object]]", data.get("overrides", []))
        return PackManifest(
            slug=parse_pack_slug(cast("str", data["slug"])),
            version=SemVer.parse(cast("str", data["version"])),
            title=cast("str", data["title"]),
            description=cast("str", data["description"]),
            publisher=cast("str", data["publisher"]),
            trust=trust,
            priority=cast("int", data.get("priority", DEFAULT_PRIORITY[trust])),
            license=cast("str", data["license"]),
            requires_skm=VersionConstraint.parse(cast("str", data["requires_skm"])),
            config=copy.deepcopy(cast("dict[str, JsonValue]", data.get("config", {}))),
            exclusive_groups=tuple(
                ExclusiveGroup(
                    cast("str", item["name"]), cast("int", item["max"]), cast("str", item["description"])
                )
                for item in groups
            ),
            overrides=tuple(_override(item) for item in overrides),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise _invalid("manifest_malformed") from exc


def _override(item: Mapping[str, object]) -> PackOverride:
    kind = ResourceKind(cast("str", item["kind"]))
    key = parse_resource_key(cast("str", item["key"]), prompt_block=kind is ResourceKind.PROMPT_BLOCK)
    return PackOverride(kind, key, cast("str", item["reason"]))


def manifest_to_json(manifest: PackManifest) -> JsonObject:
    """The stored ``urn:skm:extensions:pack:v1`` document; ``parse_pack_manifest`` reads it back unchanged."""
    return {
        "schema": "urn:skm:extensions:pack:v1",
        "slug": manifest.slug,
        "version": str(manifest.version),
        "title": manifest.title,
        "description": manifest.description,
        "publisher": manifest.publisher,
        "trust": manifest.trust.value,
        "priority": manifest.priority,
        "license": manifest.license,
        "requires_skm": str(manifest.requires_skm),
        "config": copy.deepcopy(dict(manifest.config)),
        "exclusive_groups": [
            {"name": group.name, "max": group.max, "description": group.description}
            for group in manifest.exclusive_groups
        ],
        "overrides": [
            {"kind": item.kind.value, "key": item.key, "reason": item.reason} for item in manifest.overrides
        ],
    }


def require_external_origin(origin_label: str) -> str:
    """The origin a surface may declare: ``builtin`` is ``FORBIDDEN``, anything else needs its prefix."""
    if origin_label == BUILTIN_ORIGIN:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            "a surface cannot declare the builtin origin",
            details={"reason": "builtin_origin_not_allowed"},
        )
    if _EXTERNAL_ORIGIN.fullmatch(origin_label) is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid origin label", details={"reason": "origin_label_invalid"}
        )
    return origin_label
