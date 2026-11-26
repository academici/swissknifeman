"""Read-only host layer reader for Claude Code ``doctor`` checks (integrations §5.6)."""

from __future__ import annotations

from typing import Final, Literal, cast

from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.contracts import ClientLayer
from skm.modules.integrations.domain.merged_json import parse_json_document
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader

__all__ = [
    "CLAUDE_LAYER_SPECS",
    "read_claude_layers",
]

type _HomeLogical = Literal["claude.user_settings", "claude.managed_settings", "vscode.user_settings"]

CLAUDE_LAYER_SPECS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("user", "home", "claude.user_settings", "~/.claude/settings.json"),
    ("project", "checkout", ".claude/settings.json", ".claude/settings.json"),
    ("local", "checkout", ".claude/settings.local.json", ".claude/settings.local.json"),
    ("managed", "home", "claude.managed_settings", "/etc/claude-code/managed-settings.json"),
    ("vscode", "home", "vscode.user_settings", "~/.config/Code/User/settings.json"),
)


def _parse_layer_bytes(
    layer_id: str,
    display_path: str,
    raw: bytes | None,
    *,
    gitignored: bool | None = None,
) -> ClientLayer:
    if raw is None:
        layer: ClientLayer = {
            "layer": layer_id,
            "path": display_path,
            "exists": False,
            "valid": True,
            "data": None,
            "error": None,
        }
        if gitignored is not None:
            layer["gitignored"] = gitignored
        return layer

    try:
        parsed = parse_json_document(raw)
    except ValueError:
        err_layer: ClientLayer = {
            "layer": layer_id,
            "path": display_path,
            "exists": True,
            "valid": False,
            "data": None,
            "error": "invalid_json",
        }
        if gitignored is not None:
            err_layer["gitignored"] = gitignored
        return err_layer

    ok_layer: ClientLayer = {
        "layer": layer_id,
        "path": display_path,
        "exists": True,
        "valid": True,
        "data": cast("JsonObject", parsed),
        "error": None,
    }
    if gitignored is not None:
        ok_layer["gitignored"] = gitignored
    return ok_layer


def read_claude_layers(fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
    """Read user, project, local, managed, and VS Code settings layers without mutation."""
    layers: list[ClientLayer] = []
    for layer_id, origin, selector, display_path in CLAUDE_LAYER_SPECS:
        if origin == "home":
            raw = home.read(cast("_HomeLogical", selector))
            layers.append(_parse_layer_bytes(layer_id, display_path, raw))
        else:
            raw = fs.read(selector)
            gitignored = fs.is_gitignored(selector) if layer_id == "local" else None
            layers.append(_parse_layer_bytes(layer_id, display_path, raw, gitignored=gitignored))
    return tuple(layers)
