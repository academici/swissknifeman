"""A checkout or material destination cannot be rebound to an outside file (S13)."""

from io import BytesIO
from pathlib import Path
from typing import override
from uuid import uuid4

import pytest

from security.test_blob_access import assert_private_output, files_under
from security.test_materialization_paths import _entry
from skm.adapters.blobs.local.materializer import LocalMaterialWriter
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.artifacts.domain.materialization import MaterialEntry
from skm.platform.fs.safe_paths import UnsafePathError

PRIVATE = "private-symlink-target-4157"


@pytest.mark.parametrize("follow_symlinks", [False, True])
def test_outside_symlink_has_no_checkout_read_or_vault_write(
    tmp_path: Path,
    follow_symlinks: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout, outside = tmp_path / "checkout", tmp_path / "outside"
    checkout.mkdir()
    outside.mkdir()
    (outside / "victim.md").write_text(PRIVATE)
    (checkout / "link").symlink_to(outside, target_is_directory=True)
    before = files_under(tmp_path)

    found = GitCheckoutReader({"repo": checkout}).read(
        "repo", "link/victim.md", max_bytes=1024, follow_symlinks=follow_symlinks
    )
    assert found.status in {"symlink_refused", "symlink_outside"}
    assert (found.data, found.size) == (None, None)
    with pytest.raises(SkmError) as rejected:
        LocalVaultFs(checkout).create_new("link/injected.md", b"unwanted")
    assert rejected.value.code is ErrorCode.INTEGRATION_UNSAFE_TARGET
    assert_private_output((found, rejected.value, rejected.value.details, capsys.readouterr()), PRIVATE)
    assert files_under(tmp_path) == before


class _UnreadablePayload(BytesIO):
    @override
    def read(self, size: int | None = -1, /) -> bytes:
        pytest.fail("an unsafe material target reached the content stream")


def test_materialization_refuses_directory_swap_before_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside, root = tmp_path / "outside", tmp_path / "materialized"
    outside.mkdir()
    (outside / "victim.md").write_text(PRIVATE)
    entry = _entry(uuid4(), "victim.md", b"unauthorized material")
    root.mkdir()
    version_dir = root / str(entry.file_version_id)
    version_dir.mkdir()
    untouched = files_under(outside)
    moved = tmp_path / "owned-original"
    swapped = False

    def swap(target: Path, item: MaterialEntry) -> None:
        nonlocal swapped
        intended = target / str(item.file_version_id)
        intended.rename(moved)
        intended.symlink_to(outside, target_is_directory=True)
        swapped = True

    with _UnreadablePayload() as source, pytest.raises(UnsafePathError) as rejected:
        LocalMaterialWriter(before_open=swap).write(root, entry, source)
    assert swapped
    assert files_under(outside) == untouched
    assert not list(moved.iterdir())
    assert files_under(root) == {Path(str(entry.file_version_id)): outside}
    assert_private_output((rejected.value, capsys.readouterr()), PRIVATE)
