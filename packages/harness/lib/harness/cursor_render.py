"""Cursor provider renderers for permissions, rules and profile shapes.

Project-level ``.cursor/cli.json`` accepts only a ``permissions`` object (E14.1).
Approval mode and sandbox are launch-only axes and must never be written here.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import ProviderId

from .profiles import ProfileResolution

_DENY_FLOOR = [
    "Read(.env*)",
    "Read(**/.env*)",
    "Read(**/*.pem)",
    "Read(**/id_rsa*)",
    "Write(**/.env*)",
    "Write(**/*.key)",
    "Write(**/*.pem)",
]

_CLI_ALLOW = {
    "observe": [
        "Read(**)",
        "Shell(git status)",
        "Shell(git diff)",
        "Shell(git log)",
        "Shell(ls)",
        "Mcp(*:*_recall)",
    ],
    "workspace-contained": [
        "Read(**)",
        "Write(packages/**)",
        "Write(core/**)",
        "Write(docs/**)",
        "Write(configs/**)",
        "Write(CHANGELOG.md)",
        "Shell(git)",
        "Shell(python3)",
        "Shell(bash)",
        "WebFetch(cursor.com)",
        "WebFetch(*.cursor.com)",
        "Mcp(plugin-core-maind:*)",
        "Mcp(plugin-core-serena:*)",
    ],
    "trusted-full-access": [
        "Read(**)",
        "Write(**)",
        "Shell(**)",
        "Mcp(*:*)",
        "WebFetch(*)",
    ],
}

_IDE_PERMISSIONS = {
    "observe": {
        "mcpAllowlist": [],
        "terminalAllowlist": [],
        "autoRun": {
            "block_instructions": [
                "This repository is in observe mode: block any write, install, migration or release operation.",
            ],
        },
    },
    "workspace-contained": {
        "mcpAllowlist": ["plugin-core-maind:*", "plugin-core-serena:*"],
        "terminalAllowlist": [
            "git status",
            "git diff",
            "git log",
            "python3",
            "bash scripts/validate.sh",
            "bash scripts/test.sh",
            "packages/harness/bin/harness",
            "packages/skiller/bin/skiller",
        ],
        "autoRun": {
            "block_instructions": [
                "Block release, tag, publish and fleet-sync operations in this repository.",
                "Block writes outside the workspace root.",
            ],
        },
    },
    "trusted-full-access": {
        "mcpAllowlist": ["*:*"],
        "terminalAllowlist": ["git", "python3", "bash", "packages", "maind", "skiller", "harness"],
    },
}

_RULE_CORE = """---
alwaysApply: true
---
<!-- swissknifeman:instructions:root:cursor:extension:begin -->
<!-- semantic:root.cursor.instruction-precedence -->

## root.cursor.instruction-precedence
The common repository contract reaches this session through the `AGENTS.md` Cursor already reads; it is not
repeated here. Sections marked `root.codex.*` in that file are Codex-owned and are **not** authoritative in a
Cursor session — never follow Codex launch flags (`-a never`, `-s danger-full-access`) from them.
<!-- swissknifeman:instructions:root:cursor:extension:end -->
"""

_RULE_LAUNCH = """---
description: Cursor launch and autonomy in this repository — Run Mode, model routing, the permissions deny floor, and why approval mode is not file-configurable. Read before starting or re-configuring an autonomous session.
alwaysApply: false
---
<!-- semantic:root.cursor.launch-and-autonomy -->

## root.cursor.launch-and-autonomy
Name the intended workspace, the routed model and the Run Mode before acting. Autonomy in a trusted session
comes from launch flags (`--force --sandbox disabled --trust --approve-mcps`), never from a committed file:
the approval mode is not project-configurable. The `deny` floor in `.cursor/cli.json` still applies under
`--force`, so a denied secret path is a real refusal, not a transient error to retry.
"""

_RULE_PACKAGES = """---
globs: packages/**,core/**
alwaysApply: false
---
<!-- semantic:root.cursor.package-scope-routing -->

## root.cursor.package-scope-routing
Start package-scoped work with the intended workspace root so native discovery reads root→cwd. During an
authorized cross-package task, explicitly read each applicable package guide in the current session.
"""


def _load_bindings(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "cursor" not in value:
        raise ValueError("HARNESS_MAPPING_MISSING")
    return value["cursor"]


def _require_self_host(resolution: ProfileResolution) -> None:
    if resolution.profile is None:
        raise ValueError("cannot render a refused profile")
    if resolution.profile.id != "trusted-full-access":
        return
    allowed = (resolution.target_identity or "").rstrip(":") in ("repo:swissknifeman", "repo:fixture")
    if resolution.operation_id != "self-host-apply" or not allowed:
        raise ValueError("HARNESS_CURSOR_TRUSTED_NON_SELF_HOST_REFUSED")


def render_cursor_cli_json(resolution: ProfileResolution, bindings_path: Path) -> bytes:
    """Render project-scoped CLI permissions only — never approvalMode or sandbox."""
    _require_self_host(resolution)
    bindings = _load_bindings(bindings_path)
    profile_id = resolution.profile.id
    if profile_id not in bindings:
        raise ValueError("HARNESS_MAPPING_MISSING")
    binding = bindings[profile_id]
    for forbidden in ("approvalMode", "sandbox", "approval_mode", "sandbox_mode"):
        if forbidden in binding:
            raise ValueError("HARNESS_CURSOR_CLI_PROJECT_MODE_REFUSED")
    allow = list(_CLI_ALLOW[profile_id])
    payload = {"permissions": {"allow": allow, "deny": list(_DENY_FLOOR)}}
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def render_cursor_permissions_json(resolution: ProfileResolution, bindings_path: Path) -> bytes:
    _require_self_host(resolution)
    bindings = _load_bindings(bindings_path)
    profile_id = resolution.profile.id
    if profile_id not in bindings:
        raise ValueError("HARNESS_MAPPING_MISSING")
    payload = _IDE_PERMISSIONS[profile_id]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def render_cursor_rules(resolution: ProfileResolution) -> dict[str, bytes]:
    """Instruction rules ship only for the self-host umbrella repository."""
    _require_self_host(resolution)
    if (resolution.target_identity or "").rstrip(":") not in ("repo:swissknifeman", "repo:fixture"):
        return {}
    return {
        ".cursor/rules/swissknifeman-core.mdc": _RULE_CORE.encode("utf-8"),
        ".cursor/rules/swissknifeman-launch.mdc": _RULE_LAUNCH.encode("utf-8"),
        ".cursor/rules/swissknifeman-packages.mdc": _RULE_PACKAGES.encode("utf-8"),
    }


def assert_rule_frontmatter(path: str, content: bytes) -> None:
    """Conformance guard: mis-set alwaysApply silently promotes a rule to always-on."""
    text = content.decode("utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"HARNESS_CURSOR_RULE_FRONTMATTER:{path}")
    if path.endswith("swissknifeman-core.mdc"):
        if "alwaysApply: true" not in text.split("---", 2)[1]:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:core-missing-alwaysApply")
    elif path.endswith("swissknifeman-launch.mdc"):
        if "alwaysApply: false" not in text or "description:" not in text:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:launch-trigger")
        if "globs:" in text.split("---", 2)[1]:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:launch-has-globs")
    elif path.endswith("swissknifeman-packages.mdc"):
        if "globs: packages/**,core/**" not in text or "alwaysApply: false" not in text:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:packages-glob")
    else:
        raise ValueError(f"HARNESS_CURSOR_RULE_FRONTMATTER:unknown:{path}")


def profile_bindings_path(package_root: Path) -> Path:
    return package_root / "configs/cursor/config/profile-bindings.json"


def cursor_profile_target() -> str:
    return ".cursor/cli.json+.cursor/permissions.json"
