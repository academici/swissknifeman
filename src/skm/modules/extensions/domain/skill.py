"""Skill manifest and ``SKILL.md`` frontmatter domain parser (extensions §4.2, §4.4)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.extensions.domain.keys import SemVer, parse_resource_key
from skm.modules.extensions.domain.provenance import (
    CompatAcceptance,
    Provenance,
    parse_compat_accepted,
    parse_provenance,
)

if TYPE_CHECKING:
    from skm.modules.extensions.domain.keys import ResourceKey

__all__ = [
    "SelectionKind",
    "SkillFrontmatter",
    "SkillManifest",
    "SkillTriggers",
    "parse_skill_frontmatter",
    "parse_skill_manifest",
]

_YAML_FENCE: Final = "---"
_ALLOWED_FRONTMATTER_KEYS: Final = frozenset({"name", "description"})
_MAX_DESCRIPTION_CHARS: Final = 1024


class SelectionKind(StrEnum):
    DOMAIN = "domain"
    ROUTER = "router"
    REFERENCE = "reference"
    PERSONA = "persona"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class SkillTriggers:
    paths: tuple[str, ...] = ()
    deps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillManifest:
    key: ResourceKey
    version: SemVer
    kind: SelectionKind
    roles: tuple[str, ...]
    requires: tuple[ResourceKey, ...]
    requires_tools: tuple[str, ...]
    required_capabilities: frozenset[str]
    adapters: tuple[str, ...]
    exclusive_group: str | None
    replaced_by: str | None
    max_tokens: int | None
    risk: str
    license: str | None
    triggers: SkillTriggers
    conflicts_with: tuple[ResourceKey, ...]
    provenance: Provenance
    compat_accepted: tuple[CompatAcceptance, ...]


type SkillFrontmatter = JsonObject


def _invalid(reason: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"pack is invalid: {reason}",
        details={"reason": reason, **details},
    )


def parse_skill_frontmatter(text: str, *, key: str = "") -> tuple[SkillFrontmatter, str]:
    """Validate and split optional ``SKILL.md`` YAML frontmatter (§4.2): only ``name`` and ``description``."""
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n")
    lines = normalized.split("\n")
    if lines[0].strip() != _YAML_FENCE:
        return {}, normalized
    closing: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _YAML_FENCE:
            closing = index
            break
    if closing is None:
        raise _invalid("front_matter_unterminated", path="SKILL.md")
    fm: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            raise _invalid("frontmatter_invalid", path="SKILL.md")
        k, raw_v = (part.strip() for part in line.split(":", 1))
        if k not in _ALLOWED_FRONTMATTER_KEYS:
            raise _invalid("frontmatter_key_not_allowed", path="SKILL.md", key=k)
        if k in fm or not raw_v or raw_v[0] in ("|", ">", "[", "{"):
            raise _invalid("frontmatter_invalid", path="SKILL.md", key=k)
        if len(raw_v) >= 2 and raw_v[0] == raw_v[-1] and raw_v[0] in ('"', "'"):
            raw_v = raw_v[1:-1]
        fm[k] = raw_v
    if "name" not in fm or "description" not in fm or not fm["name"]:
        raise _invalid("frontmatter_invalid", path="SKILL.md")
    if key and fm["name"] != key:
        raise _invalid("key_mismatch", kind="skill", key=key, declared=fm["name"])
    if not (1 <= len(fm["description"]) <= _MAX_DESCRIPTION_CHARS):
        raise _invalid("frontmatter_invalid", path="SKILL.md", key="description")
    return {"name": fm["name"], "description": fm["description"]}, "\n".join(lines[closing + 1 :])


def parse_skill_manifest(data: Mapping[str, object]) -> SkillManifest:
    """Parse a validated ``urn:skm:extensions:skill-manifest:v1`` document into a ``SkillManifest``."""
    raw_triggers = data.get("triggers")
    triggers = SkillTriggers()
    if isinstance(raw_triggers, Mapping):
        trig_map = cast("Mapping[str, object]", raw_triggers)
        paths = trig_map.get("paths", ())
        deps = trig_map.get("deps", ())
        triggers = SkillTriggers(
            paths=tuple(str(p) for p in cast("Sequence[object]", paths)) if isinstance(paths, list) else (),
            deps=tuple(str(d) for d in cast("Sequence[object]", deps)) if isinstance(deps, list) else (),
        )
    max_tokens_raw = data.get("max_tokens")
    max_tokens = (
        max_tokens_raw if isinstance(max_tokens_raw, int) and not isinstance(max_tokens_raw, bool) else None
    )
    return SkillManifest(
        key=parse_resource_key(str(data["key"]), prompt_block=False),
        version=SemVer.parse(str(data["version"])),
        kind=SelectionKind(str(data.get("kind", "domain"))),
        roles=tuple(str(r) for r in cast("list[object]", data.get("roles", []))),
        requires=tuple(
            parse_resource_key(str(r), prompt_block=False)
            for r in cast("list[object]", data.get("requires", []))
        ),
        requires_tools=tuple(str(t) for t in cast("list[object]", data.get("requires_tools", []))),
        required_capabilities=frozenset(
            str(c) for c in cast("list[object]", data.get("required_capabilities", []))
        ),
        adapters=tuple(str(a) for a in cast("list[object]", data.get("adapters", []))),
        exclusive_group=cast("str | None", data.get("exclusive_group")),
        replaced_by=cast("str | None", data.get("replaced_by")),
        max_tokens=max_tokens,
        risk=str(data.get("risk", "low")),
        license=cast("str | None", data.get("license")),
        triggers=triggers,
        conflicts_with=tuple(
            parse_resource_key(str(c), prompt_block=False)
            for c in cast("list[object]", data.get("conflicts_with", []))
        ),
        provenance=parse_provenance(cast("Mapping[str, object] | None", data.get("provenance"))),
        compat_accepted=parse_compat_accepted(
            cast("Sequence[Mapping[str, object]] | None", data.get("compat_accepted"))
        ),
    )
