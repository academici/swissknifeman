"""Pure domain contracts, manifest parser, path rules, and asset rendering for bundles (§4.11)."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.managed_block import is_valid_block_id, render_block
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "BUNDLE_SCHEMA_URN",
    "BundleAgent",
    "BundleAsset",
    "BundleAssetSurface",
    "BundleSkill",
    "IntegrationBundleManifest",
    "merge_and_render_bundle_assets",
    "normalize_desired_json",
    "normalize_desired_map",
    "parse_bundle_manifest",
    "resolve_bundle_asset_path",
    "validate_bundle_source_path",
    "validate_pack_prefix",
]

BUNDLE_SCHEMA_URN: Final[str] = "urn:skm:integrations:bundle:v1"
_MAX_BUNDLE_ASSETS: Final[int] = 500
_RESOURCE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
_SEMVER_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
_PACK_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]{0,15}$")

_CANONICAL_INSTRUCTION_PATHS: Final[Mapping[TargetId, str]] = {
    TargetId.ANTIGRAVITY: ".agents/AGENTS.md",
    TargetId.CLAUDE_CODE: "CLAUDE.md",
    TargetId.CODEX: "AGENTS.md",
    TargetId.CURSOR: ".cursor/rules/skm-instructions.mdc",
    TargetId.GEMINI_CLI: "AGENTS.md",
    TargetId.GROK: ".grok/rules/skm-instructions.md",
}


class BundleAssetSurface(StrEnum):
    INSTRUCTIONS = "instructions"
    AGENTS = "agents"
    RULES = "rules"
    WORKFLOWS = "workflows"


@dataclass(frozen=True, slots=True)
class BundleAgent:
    key: str
    profile: str


@dataclass(frozen=True, slots=True)
class BundleSkill:
    key: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class BundleAsset:
    target: TargetId
    surface: BundleAssetSurface
    source: str
    path: str
    ownership: Ownership
    block_id: str | None = None


@dataclass(frozen=True, slots=True)
class IntegrationBundleManifest:
    schema: str
    key: str
    version: str
    title: str
    description: str
    targets: tuple[TargetId, ...]
    agents: tuple[BundleAgent, ...] = ()
    skills: tuple[BundleSkill, ...] = ()
    assets: tuple[BundleAsset, ...] = ()


def normalize_desired_json(value: object) -> JsonValue:
    """Recursively normalize Python values into deterministic sorted JSON-compatible structures."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Mapping):
        mapping_val = cast("Mapping[object, object]", value)
        sorted_items = sorted(mapping_val.items(), key=lambda kv: str(kv[0]))
        return {str(k): normalize_desired_json(v) for k, v in sorted_items}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return cast(
            "JsonValue", tuple(normalize_desired_json(item) for item in cast("Sequence[object]", value))
        )
    return str(value)


def normalize_desired_map(value: Mapping[str, object]) -> JsonObject:
    return {str(k): normalize_desired_json(v) for k, v in sorted(value.items())}


def validate_pack_prefix(prefix: str) -> str:
    if not _PACK_PREFIX_RE.fullmatch(prefix):
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"invalid integrations.agents.pack_prefix {prefix!r}",
            details={"pack_prefix": prefix},
        )
    return prefix


def _validate_posix_relative(path: str, *, code: ErrorCode, field: str) -> str:
    if (
        not path
        or path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or "\x00" in path
        or ":" in path
    ):
        raise ValidationFailed(
            code,
            f"unsafe bundle {field} path {path!r}",
            details={field: path, "reason": "invalid_posix_relative_path"},
        )
    segments = path.split("/")
    for seg in segments:
        if not seg or seg in {".", ".."} or seg.lower() == ".git":
            raise ValidationFailed(
                code,
                f"unsafe segment in bundle {field} path {path!r}",
                details={field: path, "segment": seg, "reason": "forbidden_path_segment"},
            )
    return path


def validate_bundle_source_path(source: str) -> str:
    """Validate immutable bundle-internal ``source`` path (relative POSIX, never ``bundle.toml``)."""
    checked = _validate_posix_relative(source, code=ErrorCode.INTEGRATION_UNSAFE_TARGET, field="source")
    if checked == "bundle.toml":
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "bundle asset source cannot reference bundle.toml itself",
            details={"source": source},
        )
    return checked


def _allowed_directory_prefix(target: TargetId, surface: BundleAssetSurface) -> str:
    aliases = {TargetId.CLAUDE_CODE: ".claude", TargetId.ANTIGRAVITY: ".agents"}
    target_dir = aliases.get(target, f".{target.value}")
    return f"{target_dir}/{surface.value}/"


def resolve_bundle_asset_path(
    *,
    raw_path: str,
    target: TargetId,
    surface: BundleAssetSurface,
    pack_prefix: str,
    ownership: Ownership | None = None,
    preset: str | None = None,
    package_name: str | None = None,
    package_slug: str | None = None,
) -> str:
    """Expand ``{prefix}`` and validate canonical target/surface root rules (§4.11)."""
    if not raw_path:
        raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "empty bundle asset path")
    package_var = "{package_name}"
    if package_var in raw_path and (
        not raw_path.startswith("skills/{package_name}-")
        or preset != "dart-package"
        or not package_name
        or not re.fullmatch(r"[a-z][a-z0-9_]*", package_name)
    ):
        raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "invalid Dart package skill path")
    slug_var = "{package_slug}"
    if slug_var in raw_path and (
        not raw_path.startswith("resources/boost/skills/{package_slug}/")
        or preset != "php-package"
        or not package_slug
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", package_slug)
    ):
        raise ValidationFailed(ErrorCode.INTEGRATION_UNSAFE_TARGET, "invalid PHP package skill path")
    expanded = raw_path.replace(package_var, package_name or "").replace(slug_var, package_slug or "")
    if expanded.startswith(("resources/boost/", "skills/")):
        _validate_posix_relative(expanded, code=ErrorCode.INTEGRATION_UNSAFE_TARGET, field="path")
        php = preset == "php-package" and expanded.startswith("resources/boost/")
        dart = (
            preset == "dart-package"
            and package_name is not None
            and re.fullmatch(r"[a-z][a-z0-9_]*", package_name) is not None
            and re.fullmatch(rf"skills/{re.escape(package_name)}-[^/]+/.+", expanded) is not None
        )
        if (
            ownership is Ownership.MANAGED_FILE
            and (php or dart)
            and "{" not in expanded
            and "}" not in expanded
        ):
            return expanded
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"preset does not own consumer path {expanded!r}",
            details={"path": expanded},
        )
    if (
        (target is TargetId.GROK and surface is BundleAssetSurface.AGENTS)
        or (
            target is TargetId.ANTIGRAVITY
            and surface in (BundleAssetSurface.AGENTS, BundleAssetSurface.WORKFLOWS)
        )
        or (target is TargetId.GEMINI_CLI and surface is not BundleAssetSurface.INSTRUCTIONS)
    ):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            f"{target.value} target does not support bundle {surface.value} surface",
            details={"target": target.value, "surface": surface.value, "path": raw_path},
        )
    stripped_vars = raw_path.replace("{prefix}", "")
    if "{" in stripped_vars or "}" in stripped_vars:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"unsupported variable substitution in bundle asset path {raw_path!r}",
            details={"path": raw_path, "target": target.value, "reason": "unsupported_path_variable"},
        )
    validated_prefix = validate_pack_prefix(pack_prefix) if "{prefix}" in raw_path else pack_prefix
    expanded = raw_path.replace("{prefix}", validated_prefix)
    _validate_posix_relative(expanded, code=ErrorCode.INTEGRATION_UNSAFE_TARGET, field="path")

    if surface is BundleAssetSurface.INSTRUCTIONS:
        canonical = _CANONICAL_INSTRUCTION_PATHS[target]
        if expanded != canonical:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"instructions bundle asset must target {canonical!r}, got {expanded!r}",
                details={"path": expanded, "expected": canonical, "target": target.value},
            )
        if (
            target in {TargetId.ANTIGRAVITY, TargetId.CLAUDE_CODE, TargetId.CODEX, TargetId.GEMINI_CLI}
            and ownership is Ownership.MANAGED_FILE
        ):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"shared instruction file {canonical!r} requires managed_block ownership",
                details={"path": expanded, "target": target.value, "ownership": ownership.value},
            )
        return expanded

    expected_prefix = _allowed_directory_prefix(target, surface)
    if not expanded.startswith(expected_prefix) or len(expanded) <= len(expected_prefix):
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"bundle asset path {expanded!r} escapes allowed root {expected_prefix!r}",
            details={
                "path": expanded,
                "expected_prefix": expected_prefix,
                "target": target.value,
                "surface": surface.value,
            },
        )
    if target is TargetId.ANTIGRAVITY:
        name = expanded.removeprefix(expected_prefix)
        if "/" in name or not name.endswith(".md") or ownership is Ownership.MANAGED_BLOCK:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                "Antigravity bundle rules require a flat Markdown path and managed_file ownership",
                details={"path": expanded, "target": target.value},
            )
    return expanded


def _require_slug(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not _RESOURCE_KEY_RE.fullmatch(raw):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid bundle {field}: {raw!r}",
            details={"field": field, "value": None if raw is None else str(raw)},
        )
    return raw


def _require_nonempty_str(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"missing bundle {field}", details={"field": field})
    return raw


def _parse_asset(raw: object, *, allowed_targets: frozenset[TargetId]) -> BundleAsset:
    if not isinstance(raw, Mapping):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle asset must be an object")
    doc = cast("Mapping[str, object]", raw)
    try:
        target = TargetId(str(doc.get("target", "")))
        surface = BundleAssetSurface(str(doc.get("surface", "")))
        ownership = Ownership(str(doc.get("ownership", "")))
    except ValueError as exc:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"unsupported target, surface, or ownership in bundle asset: {doc!r}",
        ) from exc
    if target not in allowed_targets:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"bundle asset target {target.value!r} is not declared in bundle targets",
            details={"target": target.value},
        )
    if ownership not in {Ownership.MANAGED_FILE, Ownership.MANAGED_BLOCK}:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"bundle asset ownership {ownership.value!r} is not permitted",
            details={"ownership": ownership.value},
        )
    source = validate_bundle_source_path(_require_nonempty_str(doc.get("source"), "asset.source"))
    raw_path = _require_nonempty_str(doc.get("path"), "asset.path")
    raw_block_id = doc.get("block_id")
    block_id: str | None = None
    if ownership is Ownership.MANAGED_BLOCK:
        if not isinstance(raw_block_id, str) or not is_valid_block_id(raw_block_id):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                f"managed_block bundle asset requires valid block_id, got {raw_block_id!r}",
                details={"path": raw_path, "block_id": None if raw_block_id is None else str(raw_block_id)},
            )
        block_id = raw_block_id
    return BundleAsset(
        target=target,
        surface=surface,
        source=source,
        path=raw_path,
        ownership=ownership,
        block_id=block_id,
    )


def _parse_targets(raw_targets: object) -> tuple[TargetId, ...]:
    if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes)) or not raw_targets:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle targets must be a non-empty list")
    targets: list[TargetId] = []
    seen: set[TargetId] = set()
    for item in cast("Sequence[object]", raw_targets):
        try:
            tid = TargetId(str(item))
        except ValueError as exc:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET, f"unknown bundle target {item!r}"
            ) from exc
        if tid in seen:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"duplicate bundle target {tid.value!r}")
        seen.add(tid)
        targets.append(tid)
    return tuple(targets)


def _parse_agents(raw_agents: object, *, bundle_key: str) -> tuple[BundleAgent, ...]:
    if not isinstance(raw_agents, Sequence) or isinstance(raw_agents, (str, bytes)):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle agents must be a list")
    agents: list[BundleAgent] = []
    seen: set[str] = set()
    for entry in cast("Sequence[object]", raw_agents):
        if not isinstance(entry, Mapping):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle agent entry must be an object")
        edoc = cast("Mapping[str, object]", entry)
        akey = _require_slug(edoc.get("key"), "agents.key")
        aprof = _require_slug(edoc.get("profile"), "agents.profile")
        if akey in seen:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate agent key {akey!r} in bundle {bundle_key!r}",
                details={"bundle": bundle_key, "agent_key": akey},
            )
        seen.add(akey)
        agents.append(BundleAgent(key=akey, profile=aprof))
    return tuple(agents)


def _parse_skills(raw_skills: object) -> tuple[BundleSkill, ...]:
    if not isinstance(raw_skills, Sequence) or isinstance(raw_skills, (str, bytes)):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle skills must be a list")
    skills: list[BundleSkill] = []
    seen: set[str] = set()
    for entry in cast("Sequence[object]", raw_skills):
        if not isinstance(entry, Mapping):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle skill entry must be an object")
        sdoc = cast("Mapping[str, object]", entry)
        skey = _require_slug(sdoc.get("key"), "skills.key")
        if skey in seen:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"duplicate skill key {skey!r} in bundle")
        seen.add(skey)
        raw_ver = sdoc.get("version")
        sver: str | None = None
        if raw_ver is not None:
            if not isinstance(raw_ver, str) or not _SEMVER_RE.fullmatch(raw_ver):
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"invalid skill version {raw_ver!r}")
            sver = raw_ver
        skills.append(BundleSkill(key=skey, version=sver))
    return tuple(skills)


def parse_bundle_manifest(raw: Mapping[str, object]) -> IntegrationBundleManifest:
    """Parse and validate a ``urn:skm:integrations:bundle:v1`` manifest mapping."""
    schema = raw.get("schema")
    if schema != BUNDLE_SCHEMA_URN:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unexpected bundle schema {schema!r}",
            details={"schema": None if schema is None else str(schema)},
        )
    key = _require_slug(raw.get("key"), "key")
    version = _require_nonempty_str(raw.get("version"), "version")
    if not _SEMVER_RE.fullmatch(version):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, f"invalid bundle semver {version!r}", details={"version": version}
        )
    title = _require_nonempty_str(raw.get("title"), "title")
    description = _require_nonempty_str(raw.get("description"), "description")
    targets = _parse_targets(raw.get("targets"))
    agents = _parse_agents(raw.get("agents", ()), bundle_key=key)
    skills = _parse_skills(raw.get("skills", ()))

    raw_assets = raw.get("assets", ())
    if not isinstance(raw_assets, Sequence) or isinstance(raw_assets, (str, bytes)):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle assets must be a list")
    asset_seq = cast("Sequence[object]", raw_assets)
    if len(asset_seq) > _MAX_BUNDLE_ASSETS:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "bundle exceeds maximum 500 assets")
    allowed_target_set = frozenset(targets)
    assets = tuple(_parse_asset(item, allowed_targets=allowed_target_set) for item in asset_seq)

    return IntegrationBundleManifest(
        schema=BUNDLE_SCHEMA_URN,
        key=key,
        version=version,
        title=title,
        description=description,
        targets=targets,
        agents=agents,
        skills=skills,
        assets=assets,
    )


def _desired_surface(surface: BundleAssetSurface) -> Surface:
    if surface is BundleAssetSurface.AGENTS:
        return Surface.AGENTS
    return Surface.INSTRUCTIONS


def _apply_bundle_asset_entry(
    by_path: dict[str, DesiredFile],
    entry: Mapping[str, object],
    *,
    target: TargetId,
    renderer: str,
    preset: str | None,
    package_name: str | None,
    package_slug: str | None,
) -> None:
    if str(entry.get("target", "")) != target.value:
        return
    surface = BundleAssetSurface(str(entry["surface"]))
    ownership = Ownership(str(entry["ownership"]))
    pack_prefix = str(entry.get("pack_prefix") or "skm")
    raw_path = str(entry.get("raw_path") or entry.get("path") or "")
    expanded = resolve_bundle_asset_path(
        raw_path=raw_path,
        target=target,
        surface=surface,
        pack_prefix=pack_prefix,
        ownership=ownership,
        preset=preset,
        package_name=package_name,
        package_slug=package_slug,
    )
    try:
        raw_bytes = base64.b64decode(str(entry["content_b64"]), validate=True)
    except (KeyError, binascii.Error) as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid base64 payload for bundle asset {expanded!r}",
            details={"path": expanded},
        ) from exc

    for token, value in (("{package_name}", package_name), ("{package_slug}", package_slug)):
        if token in raw_path and value is not None:
            raw_bytes = raw_bytes.replace(token.encode(), value.encode())

    ref: SourceRef = {"kind": "integration_bundle", "key": str(entry["bundle_key"])}
    for k_in, k_out in (("bundle_version", "version"), ("bundle_digest", "digest")):
        val = entry.get(k_in)
        if isinstance(val, str) and val:
            ref[k_out] = val
    mapped_surface = _desired_surface(surface)

    if ownership is Ownership.MANAGED_FILE:
        if expanded in by_path:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"bundle asset path {expanded!r} collides with an existing target file",
                details={"path": expanded, "target": target.value},
            )
        by_path[expanded] = DesiredFile(
            target=target,
            surface=mapped_surface,
            relative_path=expanded,
            boundary=ManagedBoundary(Ownership.MANAGED_FILE),
            managed_bytes=raw_bytes,
            managed_digest=sha256_tagged(raw_bytes),
            source_refs=(ref,),
            renderer=renderer,
        )
        return

    block_id = str(entry.get("block_id") or "")
    if not is_valid_block_id(block_id):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"invalid block_id {block_id!r} for bundle asset {expanded!r}",
            details={"path": expanded, "block_id": block_id},
        )
    try:
        text_body = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"managed_block bundle asset {expanded!r} must be valid UTF-8",
            details={"path": expanded},
        ) from exc
    rendered_block = render_block(block_id, text_body)
    existing = by_path.get(expanded)
    if existing is None:
        by_path[expanded] = DesiredFile(
            target=target,
            surface=mapped_surface,
            relative_path=expanded,
            boundary=ManagedBoundary(Ownership.MANAGED_BLOCK, block_ids=(block_id,)),
            managed_bytes=rendered_block,
            managed_digest=sha256_tagged(rendered_block),
            source_refs=(ref,),
            renderer=renderer,
        )
        return

    if existing.boundary.ownership is not Ownership.MANAGED_BLOCK or block_id in existing.boundary.block_ids:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_PATH_COLLISION,
            f"bundle managed_block {block_id!r} collides at {expanded!r}",
            details={"path": expanded, "block_id": block_id, "target": target.value},
        )
    merged_bytes = existing.managed_bytes + rendered_block
    by_path[expanded] = DesiredFile(
        target=existing.target,
        surface=existing.surface,
        relative_path=existing.relative_path,
        boundary=ManagedBoundary(Ownership.MANAGED_BLOCK, block_ids=(*existing.boundary.block_ids, block_id)),
        managed_bytes=merged_bytes,
        managed_digest=sha256_tagged(merged_bytes),
        source_refs=(*existing.source_refs, ref),
        renderer=existing.renderer,
    )


def merge_and_render_bundle_assets(
    inputs: ProjectionInputs,
    *,
    target: TargetId,
    renderer: str,
    files: Sequence[DesiredFile],
) -> tuple[DesiredFile, ...]:
    """Render target-matching bundle assets and merge ``managed_block`` assets into shared files."""
    by_path: dict[str, DesiredFile] = {}
    for item in files:
        if item.relative_path in by_path:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate rendered path {item.relative_path!r}",
                details={"path": item.relative_path, "target": target.value},
            )
        by_path[item.relative_path] = item

    preset = inputs.instructions_project.get("preset")
    package_name = inputs.instructions_project.get("package_name")
    package_slug = inputs.instructions_project.get("package_slug")
    raw_assets = inputs.instructions_project.get("bundle_assets")
    if isinstance(raw_assets, Sequence) and not isinstance(raw_assets, (str, bytes)):
        for raw_item in cast("Sequence[object]", raw_assets):
            if isinstance(raw_item, Mapping):
                _apply_bundle_asset_entry(
                    by_path,
                    cast("Mapping[str, object]", raw_item),
                    target=target,
                    renderer=renderer,
                    preset=preset if isinstance(preset, str) else None,
                    package_name=package_name if isinstance(package_name, str) else None,
                    package_slug=package_slug if isinstance(package_slug, str) else None,
                )

    return tuple(sorted(by_path.values(), key=lambda f: f.relative_path))
