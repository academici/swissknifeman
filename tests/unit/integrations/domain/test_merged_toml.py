"""Unit tests for merged TOML codec and pure-Python TOML writer (integrations §4.6)."""

from __future__ import annotations

import tomllib

import pytest

from skm.adapters.integrations._render import toml_doc
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.merged_toml import (
    extract_owned_toml,
    merge_owned_toml,
    parse_toml,
)
from skm.modules.integrations.domain.observed import observe_bytes
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId


def test_replace_owned_table_and_preserve_foreign_tables_comments_and_spacing() -> None:
    raw = (
        "# User top-level configuration comment\n"
        'model = "o3"\n'
        "\n"
        "# Foreign MCP server comment\n"
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        'args = ["--stdio"]  # inline comment preserved!\n'
        "\n"
        "[mcp_servers.skm]\n"
        'command = "old-skm"\n'
        'args = ["legacy"]\n'
        "\n"
        "# Trailing user profile section\n"
        "[profiles.custom]\n"
        "temperature = 0.2\n"
    )
    owned = (
        OwnedKeyPath(("mcp_servers", "skm"), "replace"),
        OwnedKeyPath(("permission",), "replace"),
    )

    extracted = extract_owned_toml(raw, owned)
    assert extracted == {
        "mcp_servers": {
            "skm": {
                "command": "old-skm",
                "args": ["legacy"],
            }
        }
    }

    managed = {
        "mcp_servers": {
            "skm": {
                "command": "skm",
                "args": ["mcp", "serve"],
                "env": {"SKM_MODE": "strict"},
            }
        },
        "permission": {
            "bash": "allow",
            "edit": "ask",
        },
    }
    merged = merge_owned_toml(raw, managed, owned)

    # Foreign comments, blank lines, and sections are preserved byte-for-byte
    assert (
        "# User top-level configuration comment\n"
        'model = "o3"\n'
        "\n"
        "# Foreign MCP server comment\n"
        "[mcp_servers.github]\n"
        'command = "gh-mcp"\n'
        'args = ["--stdio"]  # inline comment preserved!\n'
    ) in merged
    assert ("# Trailing user profile section\n[profiles.custom]\ntemperature = 0.2\n") in merged

    # Cross-verify against Python stdlib tomllib
    parsed_stdlib = tomllib.loads(merged)
    parsed_domain = parse_toml(merged)
    assert parsed_domain == parsed_stdlib
    assert parsed_stdlib["model"] == "o3"
    assert parsed_stdlib["mcp_servers"]["github"] == {"command": "gh-mcp", "args": ["--stdio"]}
    assert parsed_stdlib["mcp_servers"]["skm"] == {
        "command": "skm",
        "args": ["mcp", "serve"],
        "env": {"SKM_MODE": "strict"},
    }
    assert parsed_stdlib["permission"] == {"bash": "allow", "edit": "ask"}
    assert parsed_stdlib["profiles"]["custom"] == {"temperature": 0.2}


def test_insert_owned_top_level_key_before_first_table_header() -> None:
    # Case 1: File starts directly with a comment attached to the first table (no top-level keys yet)
    raw_table_first = '# Comment describing foreign table\n[mcp_servers.user]\ncommand = "user-mcp"\n'
    owned = (
        OwnedKeyPath(("approval_policy",), "replace"),
        OwnedKeyPath(("sandbox_mode",), "replace"),
    )
    managed = {
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
    }

    merged = merge_owned_toml(raw_table_first, managed, owned)
    first_table_idx = merged.index("[mcp_servers.user]")
    approval_idx = merged.index('approval_policy = "never"')
    sandbox_idx = merged.index('sandbox_mode = "workspace-write"')
    comment_idx = merged.index("# Comment describing foreign table")

    assert approval_idx < sandbox_idx < comment_idx < first_table_idx
    assert tomllib.loads(merged) == {
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "mcp_servers": {"user": {"command": "user-mcp"}},
    }

    # Case 2: Updating an existing top-level key in-place and inserting another before first [table]
    raw_with_top = (
        '# Global header\nmodel = "gpt-5"\napproval_policy = "on-request"\n\n[features]\nfast = true\n'
    )
    merged2 = merge_owned_toml(raw_with_top, managed, owned)
    assert merged2.index('approval_policy = "never"') < merged2.index("[features]")
    assert merged2.index('sandbox_mode = "workspace-write"') < merged2.index("[features]")
    assert "# Global header\n" in merged2
    assert 'model = "gpt-5"\n' in merged2
    assert tomllib.loads(merged2) == {
        "model": "gpt-5",
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "features": {"fast": True},
    }


def test_remove_owned_toml_keys_and_tables_leaves_foreign_content_intact() -> None:
    raw = (
        'model = "o3"\n'
        'approval_policy = "never"\n'
        "\n"
        "[mcp_servers.user]\n"
        'command = "u"\n'
        "\n"
        "[mcp_servers.skm]\n"
        'command = "skm"\n'
    )
    owned = (
        OwnedKeyPath(("approval_policy",), "replace"),
        OwnedKeyPath(("mcp_servers", "skm"), "replace"),
    )
    cleaned = merge_owned_toml(raw, {}, owned)
    assert extract_owned_toml(cleaned, owned) == {}
    assert tomllib.loads(cleaned) == {
        "model": "o3",
        "mcp_servers": {"user": {"command": "u"}},
    }
    assert '[mcp_servers.user]\ncommand = "u"\n' in cleaned


def test_toml_doc_pure_python_writer() -> None:
    assert toml_doc.format_key("simple_key-1") == "simple_key-1"
    assert toml_doc.format_key("git *") == '"git *"'
    assert toml_doc.format_value(True) == "true"
    assert toml_doc.format_value(42) == "42"
    assert toml_doc.format_value(["a", "b"]) == '["a", "b"]'
    assert toml_doc.format_inline_table({"a": "1", "b": True}) == '{ a = "1", b = true }'

    doc = {
        "approval_policy": "never",
        "mcp_servers": {
            "skm": {
                "command": "skm",
                "args": ["mcp"],
                "env": {"FOO": "bar"},
            }
        },
    }
    text = toml_doc.dumps(doc)
    assert tomllib.loads(text) == doc
    assert toml_doc.dumps_bytes(doc) == text.encode("utf-8")


@pytest.mark.parametrize(
    "bad_toml",
    [
        "[unclosed_header\na = 1\n",
        'key = "unterminated string\n',
        "a = 1\na = 2\n",
        "[tbl]\nx = 1\n[tbl]\ny = 2\n",
        "bare_without_equals\n",
    ],
)
def test_malformed_toml_raises_and_marks_boundary_invalid(bad_toml: str) -> None:
    owned = (OwnedKeyPath(("approval_policy",), "replace"),)
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        extract_owned_toml(bad_toml, owned)
    with pytest.raises(ValueError, match="INTEGRATION_BOUNDARY_INVALID"):
        merge_owned_toml(bad_toml, {"approval_policy": "never"}, owned)

    boundary = ManagedBoundary(ownership=Ownership.MERGED_TOML, owned_keys=owned)
    observed = observe_bytes(".codex/config.toml", bad_toml.encode("utf-8"), boundary)
    assert observed.boundary_valid is False
    assert observed.managed_digest is None

    managed_bytes = toml_doc.dumps_bytes({"approval_policy": "never"})
    desired = DesiredFile(
        target=TargetId.CODEX,
        surface=Surface.PERMISSIONS,
        relative_path=".codex/config.toml",
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=(),
        renderer="test-v1",
    )
    decision = decide_file(desired, None, observed, safe=True)
    assert decision.kind is FileDecisionKind.BOUNDARY_INVALID
    assert decision.diagnostic == "INTEGRATION_BOUNDARY_INVALID"
