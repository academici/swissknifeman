"""Unit tests for integration conflict sidecar naming helpers (integrations §4.4)."""

from __future__ import annotations

import pytest

from skm.modules.integrations.domain.conflict_names import (
    DEFAULT_CONFLICT_SUFFIX,
    conflict_path,
    is_conflict_path,
    original_path,
)


def test_conflict_path_default_suffix() -> None:
    assert DEFAULT_CONFLICT_SUFFIX == ".skm-new"
    assert conflict_path("foo/bar.txt") == "foo/bar.txt.skm-new"
    assert conflict_path("AGENTS.md") == "AGENTS.md.skm-new"
    assert conflict_path(".codex/config.toml") == ".codex/config.toml.skm-new"


def test_conflict_path_custom_suffix() -> None:
    assert conflict_path("foo/bar.txt", suffix=".custom") == "foo/bar.txt.custom"


def test_is_conflict_path_and_original_path_roundtrip() -> None:
    sidecar = conflict_path("nested/dir/settings.json")
    assert is_conflict_path(sidecar) is True
    assert is_conflict_path("nested/dir/settings.json") is False
    assert is_conflict_path(".skm-new") is False
    assert is_conflict_path("nested/dir/.skm-new") is False
    assert original_path(sidecar) == "nested/dir/settings.json"
    assert original_path("nested/dir/settings.json") == "nested/dir/settings.json"
    assert original_path("nested/dir/.skm-new") == "nested/dir/.skm-new"


def test_conflict_helpers_reject_empty_inputs() -> None:
    with pytest.raises(ValueError, match="relative_path"):
        conflict_path("")
    with pytest.raises(ValueError, match="suffix"):
        conflict_path("foo.txt", suffix="")
    with pytest.raises(ValueError, match="suffix"):
        is_conflict_path("foo.txt.skm-new", suffix="")
    with pytest.raises(ValueError, match="suffix"):
        original_path("foo.txt.skm-new", suffix="")
