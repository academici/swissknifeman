"""Antigravity provider renderer for project ``.antigravity/config.toml`` permission rules."""
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

_LAUNCH_MODES = {
    "observe": "ask",
    "workspace-contained": "acceptEdits",
    "trusted-full-access": "always-approve",
}


def antigravity_profile_target() -> str:
    return ".antigravity/config.toml"


def _load_bindings(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "antigravity" not in value:
        raise ValueError("HARNESS_MAPPING_MISSING")
    return value["antigravity"]


def _require_self_host(resolution: ProfileResolution) -> None:
    if resolution.profile is None:
        raise ValueError("cannot render a refused profile")
    if resolution.profile.id != "trusted-full-access":
        return
    allowed = (resolution.target_identity or "").rstrip(":") in ("repo:swissknifeman", "repo:fixture")
    if resolution.operation_id != "self-host-apply" or not allowed:
        raise ValueError("HARNESS_ANTIGRAVITY_TRUSTED_NON_SELF_HOST_REFUSED")


def render_antigravity_config_toml(resolution: ProfileResolution, bindings_path: Path) -> bytes:
    """Render the project deny floor. Permission mode stays a launch flag."""
    _require_self_host(resolution)
    assert resolution.profile is not None
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
