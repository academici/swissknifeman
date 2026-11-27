"""Skill directory renderer for ``.agents/skills/<skill_key>/...`` (integrations §4.8, §5.2)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.budget import frontmatter_end, frontmatter_field
from skm.modules.integrations.domain.contracts import SkillPayload, SourceRef
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CODEX_SKILLS_PREFIX",
    "CODEX_SKILLS_RENDERER",
    "SKILL_LISTING_MAX_CHARS",
    "render_skills",
]

CODEX_SKILLS_PREFIX: Final[str] = ".agents/skills"
CODEX_SKILLS_RENDERER: Final[str] = "codex.skills@1"
SKILL_LISTING_MAX_CHARS: Final[int] = 8000
_ENTRY_DESCRIPTION_MAX_CHARS: Final[int] = 1536

_SKILL_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESOURCE_MANIFEST_FILENAMES: Final[frozenset[str]] = frozenset({"skill.toml"})
_YAML_SPECIAL: Final[frozenset[str]] = frozenset(":#\"'{}[]&*!|>%@")
_INVOCATION_FIELD_RE: Final = re.compile(r"(?:disable-model-invocation|argument-hint)\s*:")
_OPENAI_METADATA: Final[str] = "agents/openai.yaml"


def _yaml_scalar(value: str) -> str:
    cleaned = " ".join(value.splitlines()).strip()
    if not cleaned:
        return '""'
    if any(ch in _YAML_SPECIAL for ch in cleaned):
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def _ensure_skill_markdown(key: str, manifest: Mapping[str, object], raw_text: str) -> str:
    normalized = raw_text.removeprefix("\ufeff").replace("\r\n", "\n")
    if normalized.partition("\n")[0].strip() == "---":
        if not normalized.endswith("\n"):
            normalized += "\n"
        return normalized

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
        return f"{frontmatter}\n{body}"
    return frontmatter


def _encode_skill_file(
    key: str, manifest: Mapping[str, object], rel_path: str, content: bytes | str
) -> bytes:
    if isinstance(content, bytes):
        return content
    if rel_path == "SKILL.md":
        return _ensure_skill_markdown(key, manifest, content).encode()
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


def _extract_skill_files(key: str, skill: SkillPayload, manifest: Mapping[str, object]) -> dict[str, bytes]:
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

    return collected


def _add_invocation_files(
    key: str, manifest: Mapping[str, object], target: TargetId, files: dict[str, bytes]
) -> None:
    # Targets sharing .agents/skills must produce identical SKILL.md bytes.
    if target not in (
        TargetId.CLAUDE_CODE,
        TargetId.CODEX,
        TargetId.ANTIGRAVITY,
        TargetId.CURSOR,
        TargetId.GROK,
    ):
        return
    invocation = manifest.get("invocation")
    if not isinstance(invocation, Mapping) or "SKILL.md" not in files:
        return
    invocation = cast("Mapping[str, object]", invocation)
    if invocation.get("user_only") is not True:
        return

    normalized = _ensure_skill_markdown(key, manifest, files["SKILL.md"].decode("utf-8-sig"))
    lines = normalized.split("\n")
    end = frontmatter_end(lines)
    if end is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"unterminated SKILL.md frontmatter for skill {key!r}",
            details={"skill_key": key},
        )
    header = [line for line in lines[1:end] if not _INVOCATION_FIELD_RE.match(line)]
    header.append("disable-model-invocation: true")
    hint = invocation.get("argument_hint")
    if isinstance(hint, str):
        header.append(f"argument-hint: {json.dumps(hint, ensure_ascii=False)}")
    markdown = "\n".join(["---", *header, "---", *lines[end + 1 :]])
    files["SKILL.md"] = markdown.encode()

    if target is TargetId.CODEX:
        display_name = invocation.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = key.replace("-", " ").replace("_", " ").title()
        description = frontmatter_field(markdown, "description") or ""
        files[_OPENAI_METADATA] = (
            "interface:\n"
            f"  display_name: {json.dumps(display_name, ensure_ascii=False)}\n"
            f"  short_description: {json.dumps(description, ensure_ascii=False)}\n"
            "policy:\n"
            "  allow_implicit_invocation: false\n"
        ).encode()


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


def render_skills(
    inputs: ProjectionInputs,
    *,
    prefix: str = CODEX_SKILLS_PREFIX,
    renderer: str = CODEX_SKILLS_RENDERER,
) -> tuple[DesiredFile, ...]:
    """Render selected skills as individual managed files beneath the client skill root."""
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    rendered: list[DesiredFile] = []
    seen_keys: set[str] = set()

    sorted_skills = sorted(inputs.skills, key=lambda s: str(s.get("key", "")))
    for skill in sorted_skills:
        raw_key = skill.get("key")
        if not isinstance(raw_key, str) or not _SKILL_KEY_RE.fullmatch(raw_key):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid skill key for {inputs.target.value} projection: {raw_key!r}",
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

        skill_files = _extract_skill_files(raw_key, skill, manifest)
        _add_invocation_files(raw_key, manifest, inputs.target, skill_files)
        for rel_inside, file_bytes in skill_files.items():
            if not is_safe_relative_path(rel_inside):
                raise ValidationFailed(
                    ErrorCode.INTEGRATION_UNSAFE_TARGET,
                    f"unsafe skill file path {rel_inside!r} in skill {raw_key!r}",
                    details={"skill_key": raw_key, "path": rel_inside},
                )
            full_rel = f"{prefix}/{raw_key}/{rel_inside}"
            rendered.append(
                DesiredFile(
                    target=inputs.target,
                    surface=Surface.SKILLS,
                    relative_path=full_rel,
                    boundary=boundary,
                    managed_bytes=file_bytes,
                    managed_digest=sha256_tagged(file_bytes),
                    source_refs=source_refs,
                    renderer=renderer,
                )
            )

    return tuple(sorted(rendered, key=lambda f: f.relative_path))
