"""Cross-provider MCP parity and Claude settings duplicate helpers.

Read-only collectors feed fleet audit; repair helpers run during sync before deploy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .mcpconfig import MCP_FILES

_CODEX_MCP_RE = re.compile(r"^\[mcp_servers\.([^\]]+)\]", re.M)
_SETTINGS_FILES = ("settings.json", "settings.local.json")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def json_server_ids(path):
    """Server IDs from a JSON MCP carrier; missing/broken → None."""
    path = Path(path)
    if not path.is_file():
        return None
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    return set(servers)


def codex_server_ids(path):
    """Server IDs from Codex `[mcp_servers.*]` blocks; missing → None."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return set(_CODEX_MCP_RE.findall(text))


def settings_mcp_ids(project_root):
    """Union of `mcpServers` keys across Claude settings layers."""
    root = Path(project_root)
    names = set()
    for name in _SETTINGS_FILES:
        data = _read_json(root / ".claude" / name)
        if isinstance(data, dict):
            names |= set((data.get("mcpServers") or {}).keys())
    return names


def collect_surfaces(project_root):
    """On-disk MCP server sets per provider surface."""
    root = Path(project_root)
    return {
        "claude": json_server_ids(root / MCP_FILES["claude"]),
        "cursor": json_server_ids(root / MCP_FILES["cursor"]),
        "codex": codex_server_ids(root / ".codex/config.toml"),
        "settings": settings_mcp_ids(root),
    }


def parity_drifts(surfaces, *, excluded_ids_by_surface=None):
    """Pairwise drift between provider carriers, honoring per-project exclusions."""
    excluded_ids_by_surface = excluded_ids_by_surface or {}
    carriers = {name: ids - set(excluded_ids_by_surface.get(name, ()))
                for name, ids in surfaces.items()
                if name != "settings" and ids is not None}
    drifts = []
    names = sorted(carriers)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            if carriers[left] != carriers[right]:
                drifts.append({"left": left, "right": right,
                               "only_left": sorted(carriers[left] - carriers[right]),
                               "only_right": sorted(carriers[right] - carriers[left])})
    return drifts


def settings_duplicates(surfaces):
    """MCP IDs declared both in `.mcp.json` and Claude settings layers."""
    claude = surfaces.get("claude")
    settings = surfaces.get("settings") or set()
    if not claude or not settings:
        return []
    return sorted(claude & settings)


def undeclared_servers(surfaces, expected_ids):
    """Servers present on disk but outside hub semantic inventory."""
    observed = set()
    for name, ids in surfaces.items():
        if name != "settings" and ids is not None:
            observed |= ids
    return sorted(observed - set(expected_ids))


def analyze(project_root, expected_ids=(), *, excluded_ids_by_surface=None):
    """Full parity snapshot for audit/sync."""
    surfaces = collect_surfaces(project_root)
    return {
        "surfaces": {key: sorted(value) if value is not None else None
                     for key, value in surfaces.items()},
        "drifts": parity_drifts(surfaces, excluded_ids_by_surface=excluded_ids_by_surface),
        "settings_dup": settings_duplicates(surfaces),
        "undeclared": undeclared_servers(surfaces, expected_ids),
    }


def repair_settings_duplicates(project_root, *, dry=False):
    """Drop overlapping `mcpServers` from Claude settings; provider deploy owns `.mcp.json`."""
    root = Path(project_root)
    claude_ids = json_server_ids(root / MCP_FILES["claude"]) or set()
    if not claude_ids:
        return []
    removed = []
    for name in _SETTINGS_FILES:
        path = root / ".claude" / name
        if not path.is_file():
            continue
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            continue
        overlap = sorted(set(servers) & claude_ids)
        if not overlap:
            continue
        for server_id in overlap:
            del servers[server_id]
        if servers:
            data["mcpServers"] = servers
        else:
            data.pop("mcpServers", None)
        removed.extend(f"{name}:{server_id}" for server_id in overlap)
        if dry:
            continue
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return removed
