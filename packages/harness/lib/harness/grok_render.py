"""Grok provider renderer for project ``.grok/config.toml`` permission rules.

Grok reads only ``[mcp_servers]``, ``[plugins]``, ``[permission]`` and
``[mcp] max_output_bytes`` from the project file. ``[ui] permission_mode`` is
user-level (``~/.grok/config.toml``) and is not written here. Launch mode is
``--permission-mode`` or ``--always-approve``. MCP shares this path through the
TOML MCP adapter.
"""
from __future__ import annotations

import json
from pathlib import Path

from .profiles import ProfileResolution

_DENY_FLOOR = (
    "Read(.env*)",
    "Read(**/.env*)",
    "Read(**/*.pem)",
    "Read(**/id_rsa*)",
    "Write(**/.env*)",
    "Write(**/*.key)",
    "Write(**/*.pem)",
)

# Launch labels checked against the binding. They are not project-file keys:
# ``ask`` is the user-config alias of CLI ``default``; ``acceptEdits`` is
# ``--permission-mode acceptEdits``; ``always-approve`` is ``--always-approve``.
_LAUNCH_MODES = {
    "observe": "ask",
    "workspace-contained": "acceptEdits",
    "trusted-full-access": "always-approve",
}


def grok_profile_target() -> str:
    return ".grok/config.toml"


def _load_bindings(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "grok" not in value:
        raise ValueError("HARNESS_MAPPING_MISSING")
    return value["grok"]


def _require_self_host(resolution: ProfileResolution) -> None:
    if resolution.profile is None:
        raise ValueError("cannot render a refused profile")
    if resolution.profile.id != "trusted-full-access":
        return
    allowed = (resolution.target_identity or "").rstrip(":") in ("repo:swissknifeman", "repo:fixture")
    if resolution.operation_id != "self-host-apply" or not allowed:
        raise ValueError("HARNESS_GROK_TRUSTED_NON_SELF_HOST_REFUSED")


def render_grok_config_toml(resolution: ProfileResolution, bindings_path: Path) -> bytes:
    """Render the project deny floor. Permission mode stays a launch flag."""
    _require_self_host(resolution)
    bindings = _load_bindings(bindings_path)
    profile_id = resolution.profile.id
    if profile_id not in bindings or profile_id not in _LAUNCH_MODES:
        raise ValueError("HARNESS_MAPPING_MISSING")
    binding = bindings[profile_id]
    if binding.get("permission_mode") != _LAUNCH_MODES[profile_id]:
        raise ValueError("HARNESS_MAPPING_MISSING")
    deny = ",\n  ".join(json.dumps(item) for item in _DENY_FLOOR)
    text = f"[permission]\ndeny = [\n  {deny}\n]\n"
    return text.encode("utf-8")
