"""Cursor provider renderers for permissions, rules and profile shapes.

Project-level ``.cursor/cli.json`` accepts only a ``permissions`` object (E14.1).
Approval mode and sandbox are launch-only axes and must never be written here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aicore.provider.models import load_model_catalog, select_model
from aicore.provider.values import ProviderId

from .instructions import fragment_section, semantic_block
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
            "harness",
            "skiller",
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

_LAUNCH_DESCRIPTION = (
    "Cursor launch and autonomy in this repository — Run Mode, model routing, the permissions "
    "deny floor, and why approval mode is not file-configurable. Read before starting or "
    "re-configuring an autonomous session."
)


@dataclass(frozen=True)
class _CursorRule:
    """One `.mdc` rule: canonical body plus Cursor-specific trigger metadata."""

    path: str
    semantic_id: str
    frontmatter: tuple[str, ...]
    managed_block: bool
    source_kind: str = "catalog"


# Rule bodies are projected from existing canons:
# - catalog-backed instruction sections (`root.cursor.*`);
# - observe profile policy (`_IDE_PERMISSIONS["observe"]`);
# - the aicore model catalog (Cursor class selectors).
# Only frontmatter lives directly in this table.
_RULES = (
    _CursorRule(".cursor/rules/swissknifeman-core.mdc",
                "root.cursor.instruction-precedence",
                ("alwaysApply: true",), True),
    _CursorRule(".cursor/rules/swissknifeman-launch.mdc",
                "root.cursor.launch-and-autonomy",
                (f"description: {_LAUNCH_DESCRIPTION}", "alwaysApply: false"), False),
    _CursorRule(".cursor/rules/swissknifeman-packages.mdc",
                "root.cursor.package-scope-routing",
                ("globs: packages/**,core/**", "alwaysApply: false"), False),
    _CursorRule(
        ".cursor/rules/swissknifeman-observer.mdc",
        "cursor.context.observer.static-policy",
        ("description: Static Cursor observer policy carrier (no sessionStart.additional_context).",
         "alwaysApply: true"),
        False,
        "observer",
    ),
    _CursorRule(
        ".cursor/rules/swissknifeman-router.mdc",
        "cursor.lifecycle.router.session-scoped-static",
        ("alwaysApply: false",),
        False,
        "router",
    ),
)


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


def _render_rule(rule: _CursorRule, root: Path | None) -> bytes:
    if rule.source_kind == "catalog":
        body = fragment_section("root", ProviderId.CURSOR.value, rule.semantic_id, root=root)
        ids = (rule.semantic_id,)
        if rule.managed_block:
            section = semantic_block("root", ProviderId.CURSOR.value, "extension", body, ids)
        else:
            section = (f"<!-- semantic:{rule.semantic_id} -->\n"
                       + body.rstrip() + "\n").encode("utf-8")
    elif rule.source_kind == "observer":
        section = _observer_rule_section(rule.semantic_id)
    elif rule.source_kind == "router":
        section = _router_rule_section(rule.semantic_id, root)
    else:
        raise ValueError("HARNESS_MAPPING_MISSING")
    frontmatter = "---\n" + "".join(f"{line}\n" for line in rule.frontmatter) + "---\n"
    return frontmatter.encode("utf-8") + section


def _observer_rule_section(semantic_id: str) -> bytes:
    block = _IDE_PERMISSIONS["observe"]["autoRun"]["block_instructions"][0]
    text = (
        f"<!-- semantic:{semantic_id} -->\n"
        "## Cursor observer policy (static)\n\n"
        "This managed rule is the observer carrier for Cursor sessions.\n"
        "It is static and always-on; do not depend on `sessionStart.additional_context`.\n\n"
        f"- {block}\n"
        "- Treat write/install/migration/release requests as out of scope for observe mode.\n"
        "- If mutation is required, request an explicit profile switch before continuing.\n"
    )
    return text.encode("utf-8")


def _router_rule_section(semantic_id: str, root: Path | None) -> bytes:
    catalog = load_model_catalog()
    selectors = {name: select_model(catalog, ProviderId.CURSOR.value, name)
                 for name in ("economy", "implementation", "frontier")}
    if not all(selectors.values()):
        raise ValueError("HARNESS_MAPPING_MISSING")
    classes = ", ".join(f"{name}={selector}" for name, selector in selectors.items())
    text = (
        f"<!-- semantic:{semantic_id} -->\n"
        "## Cursor planner routing (explicit invocation only)\n\n"
        "This managed rule is generated from the aicore model catalog.\n"
        "Apply only when the owner explicitly invokes planner or attaches this manual rule.\n"
        "Ordinary requests and existing plan files do not activate planner.\n\n"
        f"- Model selectors: {classes}.\n"
        "- Never replace fixed frontier or fixed implementation routes with `auto`.\n"
    )
    return text.encode("utf-8")


def plan_cursor_rules(root: Path | None = None) -> dict[str, bytes]:
    """Expected bytes of the committed `.cursor/rules/*.mdc`, keyed by repository path."""
    return {rule.path: _render_rule(rule, root) for rule in _RULES}


def check_cursor_rules(root: Path) -> tuple[str, ...]:
    """Committed rule paths that drifted from the instruction catalog."""
    drift = []
    for path, expected in plan_cursor_rules(root).items():
        assert_rule_frontmatter(path, expected)
        target = Path(root) / path
        if not target.is_file() or target.read_bytes() != expected:
            drift.append(path)
    return tuple(drift)


def write_cursor_rules(root: Path) -> tuple[str, ...]:
    """Write the committed rules from canon; returns the paths that changed."""
    written = []
    for path in check_cursor_rules(root):
        target = Path(root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plan_cursor_rules(root)[path])
        written.append(path)
    return tuple(written)


def render_cursor_rules(resolution: ProfileResolution, *,
                        root: Path | None = None) -> dict[str, bytes]:
    """Instruction rules ship only for the self-host umbrella repository."""
    _require_self_host(resolution)
    if (resolution.target_identity or "").rstrip(":") not in ("repo:swissknifeman", "repo:fixture"):
        return {}
    return plan_cursor_rules(root)


# Deliberately restated rather than derived from `_RULES`: a guard that reads its
# expectations from the table it guards cannot catch a wrong edit to that table.
_RULE_SEMANTICS = {
    "swissknifeman-core.mdc": "root.cursor.instruction-precedence",
    "swissknifeman-launch.mdc": "root.cursor.launch-and-autonomy",
    "swissknifeman-packages.mdc": "root.cursor.package-scope-routing",
    "swissknifeman-observer.mdc": "cursor.context.observer.static-policy",
    "swissknifeman-router.mdc": "cursor.lifecycle.router.session-scoped-static",
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
    elif path.endswith("swissknifeman-observer.mdc"):
        if "alwaysApply: true" not in text or "description:" not in text:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:observer-trigger")
        if "globs:" in text.split("---", 2)[1]:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:observer-has-globs")
    elif path.endswith("swissknifeman-router.mdc"):
        frontmatter = text.split("---", 2)[1]
        if "alwaysApply: false" not in frontmatter or "description:" in frontmatter:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:router-trigger")
        if "globs:" in frontmatter:
            raise ValueError("HARNESS_CURSOR_RULE_FRONTMATTER:router-has-globs")
    else:
        raise ValueError(f"HARNESS_CURSOR_RULE_FRONTMATTER:unknown:{path}")
    expected = _RULE_SEMANTICS[Path(path).name]
    if f"<!-- semantic:{expected} -->" not in text:
        raise ValueError(f"HARNESS_CURSOR_RULE_SEMANTIC:{path}")


def profile_bindings_path(package_root: Path) -> Path:
    return package_root / "configs/cursor/config/profile-bindings.json"


def cursor_profile_target() -> str:
    return ".cursor/cli.json+.cursor/permissions.json"
