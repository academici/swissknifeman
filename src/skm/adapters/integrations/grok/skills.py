"""Grok skill directory renderer for ``.agents/skills/<skill_key>/...`` (integrations §4.8, §5.2)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import SkillPayload, SourceRef
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "GROK_SKILLS_PREFIX",
    "GROK_SKILLS_RENDERER",
    "SKILL_LISTING_MAX_CHARS",
    "render_skills",
]

GROK_SKILLS_PREFIX: Final[str] = ".agents/skills"
GROK_SKILLS_RENDERER: Final[str] = "grok.skills@1"
SKILL_LISTING_MAX_CHARS: Final[int] = 8000
_ENTRY_DESCRIPTION_MAX_CHARS: Final[int] = 1536

_SKILL_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESOURCE_MANIFEST_FILENAMES: Final[frozenset[str]] = frozenset({"skill.toml"})
_YAML_SPECIAL: Final[frozenset[str]] = frozenset(":#\"'{}[]&*!|>%@")


def _yaml_scalar(value: str) -> str:
    cleaned = " ".join(value.splitlines()).strip()
    if not cleaned:
        return '""'
    if any(ch in _YAML_SPECIAL for ch in cleaned):
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def _ensure_skill_markdown(key: str, manifest: Mapping[str, object], raw_text: str) -> bytes:
    normalized = raw_text.replace("\r\n", "\n")
    if normalized.startswith("---\n"):
        if not normalized.endswith("\n"):
            normalized += "\n"
        return normalized.encode()

    raw_desc = manifest.get("description")
    desc = str(raw_desc).strip() if isinstance(raw_desc, str) else ""
    budget = max(0, _ENTRY_DESCRIPTION_MAX_CHARS - len(key) - 4)
    if len(desc) > budget and budget > 1:
        desc = desc[: budget - 1].rstrip() + "…"
    body = normalized.lstrip("\n")
    if body and not body.endswith("\n"):
        body += "\n"
    frontmatter = f"---\nname: {key}\ndescription: {_yaml_scalar(desc)}\n---\n"
    if body:
        return f"{frontmatter}\n{body}".encode()
    return frontmatter.encode()


def _encode_skill_file(
    key: str, manifest: Mapping[str, object], rel_path: str, content: bytes | str
) -> bytes:
    if isinstance(content, bytes):
        return content
    if rel_path == "SKILL.md":
        return _ensure_skill_markdown(key, manifest, content)
    return content.replace("\r\n", "\n").encode()


def _parse_file_entry(key: str, manifest: Mapping[str, object], entry: object) -> tuple[str, bytes] | None:
    if isinstance(entry, Mapping):
        entry_map = cast("Mapping[str, object]", entry)
        p_val = entry_map.get("path") or entry_map.get("relative_path")
        c_val = entry_map.get("content") if "content" in entry_map else entry_map.get("bytes")
        if isinstance(p_val, str) and isinstance(c_val, (bytes, str)):
            return p_val, _encode_skill_file(key, manifest, p_val, c_val)
        return None
    if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
        seq_entry = cast("Sequence[object]", entry)
        if len(seq_entry) == 2:
            p_item, c_item = seq_entry[0], seq_entry[1]
            if isinstance(p_item, str) and isinstance(c_item, (bytes, str)):
                return p_item, _encode_skill_file(key, manifest, p_item, c_item)
    return None


def _extract_skill_files(
    key: str, skill: SkillPayload, manifest: Mapping[str, object]
) -> list[tuple[str, bytes]]:
    collected: dict[str, bytes] = {}

    bodies = skill.get("bodies")
    if isinstance(bodies, Mapping):
        body_items = sorted(cast("Mapping[object, object]", bodies).items(), key=lambda kv: str(kv[0]))
        for rel_raw, content_raw in body_items:
            rel = str(rel_raw)
            if rel not in _RESOURCE_MANIFEST_FILENAMES and isinstance(content_raw, str):
                collected[rel] = _encode_skill_file(key, manifest, rel, content_raw)

    files_field = skill.get("files")
    if isinstance(files_field, Sequence) and not isinstance(files_field, (str, bytes)):
        for entry in cast("Sequence[object]", files_field):
            parsed = _parse_file_entry(key, manifest, entry)
            if parsed is not None and parsed[0] not in _RESOURCE_MANIFEST_FILENAMES:
                collected[parsed[0]] = parsed[1]

    ordered_keys = sorted(collected, key=lambda p: (0 if p == "SKILL.md" else 1, p))
    return [(rel, collected[rel]) for rel in ordered_keys]


def _skill_source_ref(key: str, skill: SkillPayload) -> SourceRef:
    ref: SourceRef = {"kind": "skill", "key": key}
    version = skill.get("version")
    if isinstance(version, str) and version:
        ref["version"] = version
    digest = skill.get("digest")
    if isinstance(digest, str) and digest:
        ref["digest"] = digest
    rvid = skill.get("resource_version_id")
    if isinstance(rvid, str) and rvid:
        ref["resource_version_id"] = rvid
    return ref


def render_skills(inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
    """Render selected skills as individual ``MANAGED_FILE`` entries under ``.agents/skills/<key>/``."""
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    rendered: list[DesiredFile] = []
    seen_keys: set[str] = set()

    sorted_skills = sorted(inputs.skills, key=lambda s: str(s.get("key", "")))
    for skill in sorted_skills:
        raw_key = skill.get("key")
        if not isinstance(raw_key, str) or not _SKILL_KEY_RE.fullmatch(raw_key):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid skill key for Grok projection: {raw_key!r}",
                details={"skill_key": raw_key},
            )
        if raw_key in seen_keys:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate skill key in projection inputs: {raw_key!r}",
                details={"skill_key": raw_key},
            )
        seen_keys.add(raw_key)

        raw_manifest = skill.get("manifest")
        manifest: Mapping[str, object] = (
            cast("Mapping[str, object]", raw_manifest) if isinstance(raw_manifest, Mapping) else {}
        )
        source_refs = (_skill_source_ref(raw_key, skill),)

        for rel_inside, file_bytes in _extract_skill_files(raw_key, skill, manifest):
            if not is_safe_relative_path(rel_inside):
                raise ValidationFailed(
                    ErrorCode.INTEGRATION_UNSAFE_TARGET,
                    f"unsafe skill file path {rel_inside!r} in skill {raw_key!r}",
                    details={"skill_key": raw_key, "path": rel_inside},
                )
            full_rel = f"{GROK_SKILLS_PREFIX}/{raw_key}/{rel_inside}"
            rendered.append(
                DesiredFile(
                    target=TargetId.GROK,
                    surface=Surface.SKILLS,
                    relative_path=full_rel,
                    boundary=boundary,
                    managed_bytes=file_bytes,
                    managed_digest=sha256_tagged(file_bytes),
                    source_refs=source_refs,
                    renderer=GROK_SKILLS_RENDERER,
                )
            )

    return tuple(sorted(rendered, key=lambda f: f.relative_path))
