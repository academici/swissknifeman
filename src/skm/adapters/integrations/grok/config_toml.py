"""Merged TOML renderer for ``.grok/config.toml`` (integrations §4.6, §4.8, §5.3, §5.4, §15)."""

from __future__ import annotations

from typing import Any, Final

from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned
from skm.modules.integrations.domain.merged_toml import merge_owned_toml
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

from .mcp import build_mcp_servers
from .permissions import render_grok_deny, validate_no_project_mode_keys

__all__ = [
    "GROK_CONFIG_PATH",
    "GROK_CONFIG_RENDERER",
    "render_config_toml",
]

GROK_CONFIG_PATH: Final[str] = ".grok/config.toml"
GROK_CONFIG_RENDERER: Final[str] = "grok.config_toml@1"


def render_config_toml(inputs: ProjectionInputs) -> DesiredFile:
    """Render ``.grok/config.toml`` owning ``[permission]`` deny floor and ``[mcp_servers.<name>]``."""
    deny_rules = render_grok_deny(inputs.permissions)
    servers_doc, mcp_owned_keys, mcp_refs = build_mcp_servers(inputs)

    owned_keys = (
        OwnedKeyPath(("permission",), "replace"),
        *mcp_owned_keys,
    )
    boundary = ManagedBoundary(Ownership.MERGED_TOML, owned_keys=owned_keys)

    raw_doc: dict[str, Any] = {
        "permission": {
            "deny": list(deny_rules),
        },
    }
    if servers_doc:
        raw_doc["mcp_servers"] = servers_doc

    validate_no_project_mode_keys(raw_doc)

    canonical_doc = extract_owned(raw_doc, boundary.owned_keys)
    managed_bytes = merge_owned_toml("", canonical_doc, boundary.owned_keys).encode("utf-8")

    refs: list[SourceRef] = [{"kind": "profile", "key": inputs.profile.value}]
    perm_digest = inputs.permissions.get("digest")
    if isinstance(perm_digest, str) and perm_digest:
        refs.append({"kind": "permissions", "digest": perm_digest})
    refs.extend(mcp_refs)

    return DesiredFile(
        target=TargetId.GROK,
        surface=Surface.PERMISSIONS,
        relative_path=GROK_CONFIG_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=GROK_CONFIG_RENDERER,
    )
