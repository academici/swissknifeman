"""Claude Code native subagent file renderer for ``.claude/agents/<name>.md`` (integrations §4.8, §4.11)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import AgentPayload, SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CLAUDE_AGENTS_PREFIX",
    "CLAUDE_AGENTS_RENDERER",
    "render_agents",
]

CLAUDE_AGENTS_PREFIX: Final[str] = ".claude/agents"
CLAUDE_AGENTS_RENDERER: Final[str] = "claude_code.agents@1"

_AGENT_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_MODEL_CLASS_MAP: Final[Mapping[str, str]] = {
    "fast": "haiku",
    "light": "haiku",
    "balanced": "sonnet",
    "implementation": "sonnet",
    "frontier": "opus",
    "reasoning": "opus",
}

_READ_ONLY_ROLES: Final[frozenset[str]] = frozenset({"reviewer", "scout", "advisor", "planner", "verifier"})
_DEFAULT_READONLY_TOOLS: Final[tuple[str, ...]] = ("Read", "Grep", "Glob", "Bash")
_DEFAULT_WRITABLE_TOOLS: Final[tuple[str, ...]] = ("Read", "Edit", "Write", "Grep", "Glob", "Bash")


_YAML_SPECIAL: Final[frozenset[str]] = frozenset(":#\"'{}[]&*!|>%@")


def _yaml_scalar(value: str) -> str:
    cleaned = " ".join(value.splitlines()).strip()
    if not cleaned:
        return '""'
    if any(ch in _YAML_SPECIAL for ch in cleaned):
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return cleaned


def _resolve_model(agent: AgentPayload) -> str:
    explicit = agent.get("model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    model_class = agent.get("model_class")
    if isinstance(model_class, str):
        return _MODEL_CLASS_MAP.get(model_class, "sonnet")
    return "sonnet"


def _resolve_tools(agent: AgentPayload) -> tuple[str, ...]:
    raw_tools = agent.get("tools")
    if isinstance(raw_tools, Sequence) and not isinstance(raw_tools, (str, bytes)) and raw_tools:
        return tuple(str(t) for t in cast("Sequence[object]", raw_tools) if str(t).strip())
    role = str(agent.get("role", "")).strip().lower()
    if role in _READ_ONLY_ROLES:
        return _DEFAULT_READONLY_TOOLS
    return _DEFAULT_WRITABLE_TOOLS


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
    """Render agent profiles as ``.claude/agents/<name>.md`` ``MANAGED_FILE`` entries."""
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    rendered: list[DesiredFile] = []
    seen_names: set[str] = set()

    sorted_agents = sorted(inputs.agents, key=lambda a: str(a.get("name") or a.get("key") or ""))
    for agent in sorted_agents:
        raw_name = agent.get("name") or agent.get("key")
        if not isinstance(raw_name, str) or not _AGENT_SLUG_RE.fullmatch(raw_name):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid Claude Code agent name {raw_name!r}",
                details={"agent_name": raw_name},
            )
        if raw_name in seen_names:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate Claude Code agent name {raw_name!r}",
                details={"agent_name": raw_name},
            )
        seen_names.add(raw_name)

        key = str(agent.get("key") or raw_name)
        raw_desc = agent.get("description")
        description = str(raw_desc).strip() if isinstance(raw_desc, str) else ""
        model = _resolve_model(agent)
        tools = _resolve_tools(agent)
        tools_csv = ", ".join(tools)
        body = _resolve_body(agent, raw_name, description)

        content = (
            "---\n"
            f"name: {raw_name}\n"
            f"description: {_yaml_scalar(description)}\n"
            f"model: {model}\n"
            f"tools: {tools_csv}\n"
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
                target=TargetId.CLAUDE_CODE,
                surface=Surface.AGENTS,
                relative_path=f"{CLAUDE_AGENTS_PREFIX}/{raw_name}.md",
                boundary=boundary,
                managed_bytes=file_bytes,
                managed_digest=sha256_tagged(file_bytes),
                source_refs=tuple(refs),
                renderer=CLAUDE_AGENTS_RENDERER,
            )
        )

    return tuple(rendered)
