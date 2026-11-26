"""Safe logical home selectors, read-only observations and special-file refusal."""

import os
from typing import Any

import pytest

from skm.adapters.checkout_fs.user_home import LocalUserHomeReader


@pytest.mark.parametrize(
    ("logical", "relative"),
    [
        ("claude.user_settings", ".claude/settings.json"),
        ("codex.user_config", ".codex/config.toml"),
        ("vscode.user_settings", ".config/Code/User/settings.json"),
        ("claude.managed_settings", "managed/settings.json"),
    ],
)
def test_exact_logical_mapping_is_read_only(tmp_path, logical, relative):
    if logical == "claude.managed_settings":
        relative = "managed/managed-settings.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"native bytes")
    reader = LocalUserHomeReader(tmp_path, managed_root=tmp_path / "managed")
    before = path.stat().st_mtime_ns
    assert reader.read(logical) == b"native bytes"
    assert path.read_bytes() == b"native bytes"
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    "selector", ["../settings.json", "/etc/passwd", "claude.user_settings/../x", "grok.user_config"]
)
def test_traversal_and_unlisted_selectors_rejected(tmp_path, selector: Any):
    with pytest.raises(ValueError, match="Unsupported user-home"):
        LocalUserHomeReader(tmp_path).read(selector)


@pytest.mark.parametrize("kind", ["ancestor_link", "leaf_link", "fifo", "directory", "oversize"])
def test_unsafe_home_reads_are_rejected_without_blocking(tmp_path, kind):
    home = tmp_path / "home"
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "settings.json").write_bytes(b"outside secret")
    if kind == "ancestor_link":
        settings.parent.rmdir()
        settings.parent.symlink_to(outside, target_is_directory=True)
    elif kind == "leaf_link":
        settings.symlink_to(outside / "settings.json")
    elif kind == "fifo":
        os.mkfifo(settings)
    elif kind == "directory":
        settings.mkdir()
    else:
        settings.write_bytes(b"x" * 9)
    with pytest.raises(OSError, match=r"."):
        LocalUserHomeReader(home, max_bytes=8).read("claude.user_settings")


def test_missing_home_file_is_absent_and_utf8_is_not_assumed(tmp_path):
    reader = LocalUserHomeReader(tmp_path)
    assert reader.read("claude.user_settings") is None
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_bytes(b"\xff")
    assert reader.read("claude.user_settings") == b"\xff"
