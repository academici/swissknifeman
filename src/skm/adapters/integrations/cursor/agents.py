"""Cursor native subagent file renderer for ``.cursor/agents/<name>.md`` (integrations §4.8, §4.11)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import AgentPayload, SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CURSOR_AGENTS_PREFIX",
    "CURSOR_AGENTS_RENDERER",
    "render_agents",
]

CURSOR_AGENTS_PREFIX: Final[str] = ".cursor/agents"
CURSOR_AGENTS_RENDERER: Final[str] = "cursor.agents@1"

_AGENT_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_MODEL_CLASS_MAP: Final[Mapping[str, str]] = {
    "fast": "fast",
    "light": "fast",
    "balanced": "inherit",
    "implementation": "inherit",
    "frontier": "inherit",
    "reasoning": "inherit",
}

_READ_ONLY_ROLES: Final[frozenset[str]] = frozenset({"reviewer", "scout", "advisor", "planner", "verifier"})
_YAML_SPECIAL: Final[frozenset[str]] = frozenset(":#\"'{}[]&*!|>%@")


def _yaml_scalar(value: str) -> str:
    cleaned = " ".join(value.splitlines()).strip()
    if not cleaned:
        return '""'
    if any(ch in _YAML_SPECIAL for ch in cleaned):
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def _resolve_agent_name(agent: AgentPayload) -> object:
    raw_name = agent.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    prefix = agent.get("pack_prefix")
    role = agent.get("role") or agent.get("key")
    if isinstance(prefix, str) and prefix.strip() and isinstance(role, str) and role.strip():
        return f"{prefix.strip()}-{role.strip()}"
    return agent.get("key")


def _resolve_model(agent: AgentPayload) -> str:
    explicit = agent.get("model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    model_class = agent.get("model_class")
    if isinstance(model_class, str):
        return _MODEL_CLASS_MAP.get(model_class, "inherit")
    return "inherit"


def _resolve_readonly(agent: AgentPayload) -> bool:
    explicit = agent.get("readonly")
    if isinstance(explicit, bool):
        return explicit
    role = str(agent.get("role", "")).strip().lower()
    return role in _READ_ONLY_ROLES


def _resolve_body(agent: AgentPayload, name: str, description: str) -> str:
    for field in ("body", "prompt", "instructions"):
        raw = agent.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.replace("\r\n", "\n").strip() + "\n"
    title = agent.get("title")
    heading = str(title).strip() if isinstance(title, str) and title.strip() else name
    summary = description or f"Managed SKM agent profile `{name}`."
    return f"# {heading}\n\n{summary}\n"


def render_agents(inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
    """Render agent profiles as ``.cursor/agents/<name>.md`` ``MANAGED_FILE`` entries."""
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    rendered: list[DesiredFile] = []
    seen_names: set[str] = set()

    sorted_agents = sorted(inputs.agents, key=lambda a: str(_resolve_agent_name(a) or ""))
    for agent in sorted_agents:
        raw_name = _resolve_agent_name(agent)
        if not isinstance(raw_name, str) or not _AGENT_SLUG_RE.fullmatch(raw_name):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid Cursor agent name {raw_name!r}",
                details={"agent_name": None if raw_name is None else str(raw_name)},
            )
        if raw_name in seen_names:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate Cursor agent name {raw_name!r}",
                details={"agent_name": raw_name},
            )
        seen_names.add(raw_name)

        key = str(agent.get("key") or raw_name)
        raw_desc = agent.get("description")
        description = str(raw_desc).strip() if isinstance(raw_desc, str) else ""
        model = _resolve_model(agent)
        readonly = "true" if _resolve_readonly(agent) else "false"
        body = _resolve_body(agent, raw_name, description)

        content = (
            "---\n"
            f"name: {raw_name}\n"
            f"description: {_yaml_scalar(description)}\n"
            f"model: {model}\n"
            f"readonly: {readonly}\n"
            "---\n"
            f"<!-- skm:managed surface=agents key={key} -->\n\n"
            f"{body}"
        )
        file_bytes = content.encode("utf-8")
        ref: SourceRef = {"kind": "agent_profile", "key": key}
        version = agent.get("version")
        if isinstance(version, str) and version:
            ref["version"] = version
        digest = agent.get("digest")
        if isinstance(digest, str) and digest:
            ref["digest"] = digest
        refs: list[SourceRef] = [ref]
        bundle_key = agent.get("bundle_key")
        if isinstance(bundle_key, str) and bundle_key:
            bref: SourceRef = {"kind": "integration_bundle", "key": bundle_key}
            bver = agent.get("bundle_version")
            if isinstance(bver, str) and bver:
                bref["version"] = bver
            bdigest = agent.get("bundle_digest")
            if isinstance(bdigest, str) and bdigest:
                bref["digest"] = bdigest
            refs.append(bref)

        rendered.append(
            DesiredFile(
                target=TargetId.CURSOR,
                surface=Surface.AGENTS,
                relative_path=f"{CURSOR_AGENTS_PREFIX}/{raw_name}.md",
                boundary=boundary,
                managed_bytes=file_bytes,
                managed_digest=sha256_tagged(file_bytes),
                source_refs=tuple(refs),
                renderer=CURSOR_AGENTS_RENDERER,
            )
        )

    return tuple(rendered)
