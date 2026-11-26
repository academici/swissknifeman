"""Codex native agent role renderer for ``.codex/agents/<name>.toml`` (integrations §4.8, §4.11)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from skm.adapters.integrations._render import toml_doc
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import AgentPayload, SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CODEX_AGENTS_PREFIX",
    "CODEX_AGENTS_RENDERER",
    "render_agents",
]

CODEX_AGENTS_PREFIX: Final[str] = ".codex/agents"
CODEX_AGENTS_RENDERER: Final[str] = "codex.agents@1"

_AGENT_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_MODEL_CLASS_MAP: Final[Mapping[str, str]] = {
    "fast": "gpt-5-codex-mini",
    "light": "gpt-5-codex-mini",
    "balanced": "gpt-5-codex",
    "implementation": "gpt-5-codex",
    "frontier": "gpt-5-codex",
    "reasoning": "gpt-5-codex",
}


def _resolve_model(agent: AgentPayload) -> str:
    explicit = agent.get("model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    model_class = agent.get("model_class")
    if isinstance(model_class, str):
        return _MODEL_CLASS_MAP.get(model_class, "gpt-5-codex")
    return "gpt-5-codex"


def _resolve_developer_instructions(agent: AgentPayload, name: str, description: str) -> str:
    for field in ("developer_instructions", "instructions", "prompt", "body"):
        raw = agent.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.replace("\r\n", "\n").strip()
    title = agent.get("title")
    heading = str(title).strip() if isinstance(title, str) and title.strip() else name
    summary = description or f"Managed SKM agent profile `{name}`."
    return f"# {heading}\n\n{summary}"


def render_agents(inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
    """Render agent profiles as ``.codex/agents/<name>.toml`` ``MANAGED_FILE`` entries."""
    boundary = ManagedBoundary(Ownership.MANAGED_FILE)
    rendered: list[DesiredFile] = []
    seen_names: set[str] = set()

    sorted_agents = sorted(inputs.agents, key=lambda a: str(a.get("name") or a.get("key") or ""))
    for agent in sorted_agents:
        raw_name = agent.get("name") or agent.get("key")
        if not isinstance(raw_name, str) or not _AGENT_SLUG_RE.fullmatch(raw_name):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid Codex agent name {raw_name!r}",
                details={"agent_name": raw_name},
            )
        if raw_name in seen_names:
            raise ValidationFailed(
                ErrorCode.INTEGRATION_PATH_COLLISION,
                f"duplicate Codex agent name {raw_name!r}",
                details={"agent_name": raw_name},
            )
        seen_names.add(raw_name)

        key = str(agent.get("key") or raw_name)
        raw_desc = agent.get("description")
        description = str(raw_desc).strip() if isinstance(raw_desc, str) else ""
        model = _resolve_model(agent)
        dev_instructions = _resolve_developer_instructions(agent, raw_name, description)

        doc = {
            "name": raw_name,
            "model": model,
            "description": description,
            "developer_instructions": dev_instructions,
        }
        file_bytes = toml_doc.dumps_bytes(doc)

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
                target=TargetId.CODEX,
                surface=Surface.AGENTS,
                relative_path=f"{CODEX_AGENTS_PREFIX}/{raw_name}.toml",
                boundary=boundary,
                managed_bytes=file_bytes,
                managed_digest=sha256_tagged(file_bytes),
                source_refs=tuple(refs),
                renderer=CODEX_AGENTS_RENDERER,
            )
        )

    return tuple(rendered)
