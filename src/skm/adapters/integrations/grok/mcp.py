"""MCP server builder for Grok ``[mcp_servers.<name>]`` tables (integrations §4.8, §15)."""

from __future__ import annotations

import re
from typing import Any, Final

from skm.adapters.integrations._mcp import build_server_entry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.merged_json import OwnedKeyPath

__all__ = [
    "GROK_MCP_RENDERER",
    "build_mcp_servers",
]

GROK_MCP_RENDERER: Final[str] = "grok.mcp@1"

_MCP_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def build_mcp_servers(
    inputs: ProjectionInputs,
) -> tuple[dict[str, dict[str, Any]], tuple[OwnedKeyPath, ...], tuple[SourceRef, ...]]:
    """Build ``mcp_servers`` subtable mapping, ``OwnedKeyPath`` specs, and ``SourceRef`` items."""
    enabled_names = [
        name
        for name in sorted(inputs.mcp_servers)
        if inputs.mcp_servers[name].get("enabled", True) is not False
    ]
    servers_doc: dict[str, dict[str, Any]] = {}
    owned_keys: list[OwnedKeyPath] = []
    refs: list[SourceRef] = []

    for name in enabled_names:
        if name in (".", "..") or not _MCP_NAME_RE.fullmatch(name):
            raise ValidationFailed(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"invalid MCP server name {name!r}",
                details={"server": name},
            )
        servers_doc[name] = build_server_entry(name, inputs.mcp_servers[name])
        owned_keys.append(OwnedKeyPath(("mcp_servers", name), "replace"))
        refs.append({"kind": "mcp_server", "key": name})

    return servers_doc, tuple(owned_keys), tuple(refs)
