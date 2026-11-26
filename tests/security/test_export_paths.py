"""Vault paths must stay under a descriptor-verified root."""

import os
from pathlib import Path

import pytest

from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError


@pytest.mark.parametrize("path", ["../outside.md", "folder/../inside.md", "/abs.md", "C:\\abs.md", "\x00.md"])
def test_vault_rejects_traversal_and_absolute_paths(tmp_path: Path, path: str) -> None:
    fs = LocalVaultFs(tmp_path)
    with pytest.raises(SkmError) as err:
        fs.create_new(path, b"unsafe")
    assert err.value.code == ErrorCode.INTEGRATION_UNSAFE_TARGET
    assert list(tmp_path.iterdir()) == []


def test_rejects_root_and_intermediate_symlinks_even_when_inside_vault(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "target.md").write_bytes(b"private")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    (root / "alias.md").symlink_to(root / "target.md")
    (tmp_path / "outer").symlink_to(tmp_path, target_is_directory=True)
    for fs, path in (
        (LocalVaultFs(alias), "target.md"),
        (LocalVaultFs(root), "alias.md"),
        (LocalVaultFs(tmp_path / "outer" / "root"), "target.md"),
    ):
        with pytest.raises(SkmError) as err:
            fs.read_head(path)
        assert err.value.code == ErrorCode.INTEGRATION_UNSAFE_TARGET


def test_descriptor_traversal_refuses_symlink_swapped_after_path_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "sub").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    fs = LocalVaultFs(root)
    original = os.open

    def swap_on_open(path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        if path == "sub" and not (root / "sub").is_symlink():
            (root / "sub").rename(root / "old")
            (root / "sub").symlink_to(outside, target_is_directory=True)
        return original(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_on_open)
    with pytest.raises(SkmError) as err:
        fs.create_new("sub/note.md", b"private")
    assert err.value.code == ErrorCode.INTEGRATION_UNSAFE_TARGET
    assert list(outside.iterdir()) == []
    assert list((root / "old").iterdir()) == []
