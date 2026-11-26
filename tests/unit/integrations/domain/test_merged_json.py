"""Unit tests for merged JSON ownership codec and canonical JSON renderer (integrations §4.6)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from skm.adapters.integrations._render import json_doc
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.merged_json import (
    OwnedKeyPath,
    extract_owned,
    extract_owned_json,
    has_jsonc_comments,
    is_tagged_item,
    merge_owned,
    merge_owned_json,
    parse_json_document,
)
from skm.modules.integrations.domain.observed import observe_bytes
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId


def test_replace_mode_extract_merge_and_removal() -> None:
    owned = (
        OwnedKeyPath(("permissions", "allow"), "replace"),
        OwnedKeyPath(("mcpServers", "skm"), "replace"),
    )
    doc: dict[str, Any] = {
        "theme": "dark",
        "enabledPlugins": {"foo": False, "bar": True},
        "permissions": {
            "allow": ["Bash(old)"],
            "deny": ["Read(.env)"],
        },
        "mcpServers": {
            "user_srv": {"command": "node"},
            "skm": {"command": "skm", "args": ["old"]},
        },
    }

    extracted = extract_owned(doc, owned)
    assert extracted == {
        "permissions": {"allow": ["Bash(old)"]},
        "mcpServers": {"skm": {"command": "skm", "args": ["old"]}},
    }

    managed_update: dict[str, Any] = {
        "permissions": {"allow": ["Bash(git status)", "Read(*)"]},
        "mcpServers": {"skm": {"command": "skm", "args": ["mcp", "serve"]}},
    }
    merged = merge_owned(doc, managed_update, owned)

    # Top-level and nested key order preserved; explicit user `False` untouched
    assert list(merged.keys()) == ["theme", "enabledPlugins", "permissions", "mcpServers"]
    assert merged["enabledPlugins"] == {"foo": False, "bar": True}
    assert merged["enabledPlugins"]["foo"] is False
    assert list(merged["permissions"].keys()) == ["allow", "deny"]
    assert merged["permissions"]["allow"] == ["Bash(git status)", "Read(*)"]
    assert merged["permissions"]["deny"] == ["Read(.env)"]
    assert list(merged["mcpServers"].keys()) == ["user_srv", "skm"]
    assert merged["mcpServers"]["user_srv"] == {"command": "node"}
    assert merged["mcpServers"]["skm"] == {"command": "skm", "args": ["mcp", "serve"]}

    # Removal when managed is empty: prunes owned keys while keeping foreign siblings
    removed = merge_owned(merged, {}, owned)
    assert removed == {
        "theme": "dark",
        "enabledPlugins": {"foo": False, "bar": True},
        "permissions": {"deny": ["Read(.env)"]},
        "mcpServers": {"user_srv": {"command": "node"}},
    }


def test_list_union_tagged_preserves_foreign_order_and_updates_skm_hooks() -> None:
    owned = (
        OwnedKeyPath(("hooks", "PreToolUse"), "list_union_tagged"),
        OwnedKeyPath(("hooks", "beforeShellExecution"), "list_union_tagged"),
    )
    doc: dict[str, Any] = {
        "version": 1,
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-linter --fast"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "skm-hook old-entry"}]},
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "user-audit"}]},
            ],
            "beforeShellExecution": [
                {"command": "custom-guard"},
                {"command": "skm-hook cursor-old"},
            ],
        },
    }

    assert is_tagged_item({"command": "skm-hook run"}) is True
    assert is_tagged_item({"command": "skm-hook"}) is False
    assert is_tagged_item({"hooks": [{"command": "skm-hook claude"}]}) is True
    assert is_tagged_item({"hooks": [{"command": "other"}]}) is False

    extracted = extract_owned(doc, owned)
    assert extracted == {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "skm-hook old-entry"}]}
            ],
            "beforeShellExecution": [{"command": "skm-hook cursor-old"}],
        }
    }

    new_managed: dict[str, Any] = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "skm-hook new-1"}]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "skm-hook new-2"}]},
            ],
            "beforeShellExecution": [
                {"command": "skm-hook cursor-new"},
            ],
        }
    }
    merged = merge_owned(doc, new_managed, owned)
    assert merged["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-linter --fast"}]},
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "user-audit"}]},
        {"matcher": "*", "hooks": [{"type": "command", "command": "skm-hook new-1"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "skm-hook new-2"}]},
    ]
    assert merged["hooks"]["beforeShellExecution"] == [
        {"command": "custom-guard"},
        {"command": "skm-hook cursor-new"},
    ]


def test_urls_inside_strings_are_not_treated_as_jsonc_comments() -> None:
    raw = (
        "{\n"
        '  "endpoint": "https://example.test/a//b/*not-a-comment*/",\n'
        '  "escaped": "\\" // still string"\n'
        "}\n"
    )
    assert has_jsonc_comments(raw) is False
    parsed = parse_json_document(raw)
    assert parsed["endpoint"] == "https://example.test/a//b/*not-a-comment*/"


@pytest.mark.parametrize(
    "invalid_raw",
    [
        '{\n  // line comment\n  "a": 1\n}\n',
        '{\n  /* block comment */\n  "a": 1\n}\n',
        '{"a": 1} // trailing comment',
        '["top-level-array-not-object"]',
        '{"broken": }',
        '{"nan_not_json": NaN}',
    ],
)
def test_jsonc_comments_and_malformed_json_trigger_boundary_invalid(invalid_raw: str) -> None:
    owned = (OwnedKeyPath(("permissions", "allow"), "replace"),)
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        extract_owned_json(invalid_raw, owned)
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        merge_owned_json(invalid_raw, {"permissions": {"allow": []}}, owned)

    boundary = ManagedBoundary(ownership=Ownership.MERGED_JSON, owned_keys=owned)
    observed = observe_bytes(".claude/settings.json", invalid_raw.encode("utf-8"), boundary)
    assert observed.boundary_valid is False
    assert observed.managed_digest is None

    managed_bytes = json_doc.dumps_bytes({"permissions": {"allow": ["Read(*)"]}})
    desired = DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.PERMISSIONS,
        relative_path=".claude/settings.json",
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=(),
        renderer="test-v1",
    )
    decision = decide_file(desired, None, observed, safe=True)
    assert decision.kind is FileDecisionKind.BOUNDARY_INVALID
    assert decision.diagnostic == "INTEGRATION_BOUNDARY_INVALID"


def test_json_doc_canonical_formatting() -> None:
    payload = {"日本語": "世界", "nested": {"flag": False, "items": [1, 2]}}
    rendered = json_doc.dumps(payload)
    assert rendered.endswith("\n")
    assert "日本語" in rendered  # ensure_ascii=False
    assert rendered == json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    assert json_doc.dumps_bytes(payload) == rendered.encode()
