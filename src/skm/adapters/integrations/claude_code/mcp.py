"""MCP server configuration renderer for ``.mcp.json`` (integrations §4.8, §15)."""

from __future__ import annotations

import re
from typing import Any, Final

from skm.adapters.integrations._mcp import build_server_entry
from skm.adapters.integrations._render import json_doc
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CLAUDE_MCP_PATH",
    "CLAUDE_MCP_RENDERER",
    "render_mcp",
]

CLAUDE_MCP_PATH: Final[str] = ".mcp.json"
CLAUDE_MCP_RENDERER: Final[str] = "claude_code.mcp@1"

_MCP_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def render_mcp(inputs: ProjectionInputs) -> DesiredFile | None:
    """Render ``.mcp.json`` owning ``mcpServers.<name>`` for each enabled server."""
    enabled_names = [
        name
        for name in sorted(inputs.mcp_servers)
        if inputs.mcp_servers[name].get("enabled", True) is not False
    ]
    if not enabled_names:
        return None

    servers_doc: dict[str, Any] = {}
    owned_keys: list[OwnedKeyPath] = []
    refs: list[SourceRef] = []

    for name in enabled_names:
        if not _MCP_NAME_RE.fullmatch(name):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid MCP server name {name!r}",
                details={"server": name},
            )
        servers_doc[name] = build_server_entry(name, inputs.mcp_servers[name])
        owned_keys.append(OwnedKeyPath(("mcpServers", name), "replace"))
        refs.append({"kind": "mcp_server", "key": name})

    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=tuple(owned_keys))
    canonical_doc = extract_owned({"mcpServers": servers_doc}, boundary.owned_keys)
    managed_bytes = json_doc.dumps_bytes(canonical_doc)
    return DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.MCP,
        relative_path=CLAUDE_MCP_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=CLAUDE_MCP_RENDERER,
    )
