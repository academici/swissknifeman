"""Pack compilation preserves logical paths and verifies the stored representation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skm.adapters.resources.pack_compiler import compile_packs
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.kernel.errors import BackendUnavailable, ValidationFailed

SHARED = b"an identical asset\x00\xff\n"
DISTINCT = b"a different asset\n"
SHARED_DIGEST = hashlib.sha256(SHARED).hexdigest()
FIRST = "alpha/prompts/body.md"
SECOND = "beta/steering/body.md"


def _write(root: Path, name: str, data: bytes) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _sources(root: Path, *, reverse: bool = False) -> dict[str, bytes]:
    files = {
        "beta/pack.toml": b'slug = "beta"\n',
        SECOND: SHARED,
        "alpha/pack.toml": b'slug = "alpha"\n',
        FIRST: SHARED,
        "alpha/prompts/unique.md": DISTINCT,
    }
    names = tuple(files)
    for name in reversed(names) if reverse else names:
        _write(root, name, files[name])
    return files


def _snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_deduplicates_across_packs_and_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "first"
    files = _sources(root)
    original = _snapshot(root)
    with pytest.raises(ValidationFailed, match="out of date"):
        compile_packs(root, check=True)
    assert _snapshot(root) == original

    other_root = tmp_path / "second"
    _sources(other_root, reverse=True)
    result = compile_packs(root)
    assert compile_packs(other_root) == result
    assert result["packs"] == 2
    assert result["files"] == len(files)
    assert result["duplicate_copies"] == 1

    path_digests = {
        path: "sha256:" + hashlib.sha256(content).hexdigest() for path, content in sorted(files.items())
    }
    expected_tree = hashlib.sha256(json.dumps(path_digests, separators=(",", ":")).encode()).hexdigest()
    lock = root / "pack.lock.json"
    assert lock.read_bytes() == (other_root / "pack.lock.json").read_bytes()
    assert json.loads(lock.read_bytes()) == {
        "version": 1,
        "aliases": dict.fromkeys((FIRST, SECOND), f"sha256:{SHARED_DIGEST}"),
        "tree_digest": f"sha256:{expected_tree}",
    }
    assert not (root / FIRST).exists()
    assert not (root / SECOND).exists()
    assert (root / "alpha/prompts/unique.md").read_bytes() == DISTINCT
    assert {path.name: path.read_bytes() for path in (root / ".pack-blobs").iterdir()} == {
        SHARED_DIGEST: SHARED,
    }
    compiled = _snapshot(root)
    assert compile_packs(root, check=True) == result
    assert compile_packs(root) == result
    assert _snapshot(root) == compiled


@pytest.mark.parametrize(
    "change",
    ["stale-lock", "source-edited", "duplicate", "missing-blob", "wrong-blob", "extra-blob", "missing-lock"],
)
def test_check_rejects_drift_without_writing(tmp_path: Path, change: str) -> None:
    _sources(tmp_path)
    compile_packs(tmp_path)
    blob = tmp_path / ".pack-blobs" / SHARED_DIGEST
    lock = tmp_path / "pack.lock.json"
    if change == "stale-lock":
        data = json.loads(lock.read_bytes())
        data["tree_digest"] = "sha256:" + "0" * 64
        lock.write_text(json.dumps(data), encoding="utf-8")
    elif change == "source-edited":
        _write(tmp_path, "beta/pack.toml", b'slug = "edited"\n')
    elif change == "duplicate":
        _write(tmp_path, FIRST, SHARED)
    elif change == "missing-blob":
        blob.unlink()
    elif change == "wrong-blob":
        blob.write_bytes(b"wrong")
    elif change == "extra-blob":
        blob.with_name(hashlib.sha256(DISTINCT).hexdigest()).write_bytes(DISTINCT)
    else:
        lock.unlink()
    changed = _snapshot(tmp_path)
    with pytest.raises(ValidationFailed):
        compile_packs(tmp_path, check=True)
    assert _snapshot(tmp_path) == changed
    if change == "missing-lock":
        with pytest.raises(ValidationFailed, match="restore it"):
            compile_packs(tmp_path)
        with pytest.raises(ValidationFailed, match="lock is missing"):
            FilesystemPackReader().read_dir(str(tmp_path / "alpha"))
        assert _snapshot(tmp_path) == changed


def test_editing_one_alias_materializes_remaining_singleton(tmp_path: Path) -> None:
    _sources(tmp_path)
    compile_packs(tmp_path)
    _write(tmp_path, FIRST, b"edited")
    assert compile_packs(tmp_path)["duplicate_copies"] == 0
    assert (tmp_path / FIRST).read_bytes() == b"edited"
    assert (tmp_path / SECOND).read_bytes() == SHARED
    assert not tuple((tmp_path / ".pack-blobs").iterdir())
    compile_packs(tmp_path, check=True)


def test_retry_finishes_partial_duplicate_removal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _sources(tmp_path)
    reader = FilesystemPackReader()
    expected = reader.read_dir(str(tmp_path / "alpha"))
    unlink = Path.unlink

    def interrupt(path: Path, missing_ok: bool = False) -> None:
        if path == tmp_path / SECOND:
            raise PermissionError("interrupted before removing the second copy")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patches:
        patches.setattr(Path, "unlink", interrupt)
        with pytest.raises(BackendUnavailable):
            compile_packs(tmp_path)

    assert (tmp_path / "pack.lock.json").is_file()
    assert not (tmp_path / FIRST).exists()
    assert (tmp_path / SECOND).is_file()
    assert reader.read_dir(str(tmp_path / "alpha")) == expected
    with pytest.raises(ValidationFailed, match="out of date"):
        compile_packs(tmp_path, check=True)
    compile_packs(tmp_path)
    compile_packs(tmp_path, check=True)


def test_rejects_unsafe_alias_and_symlinked_asset(tmp_path: Path) -> None:
    _sources(tmp_path)
    symlink = tmp_path / "alpha/prompts/link"
    symlink.symlink_to(tmp_path / SECOND)
    with pytest.raises(ValidationFailed, match="regular files"):
        compile_packs(tmp_path)
    symlink.unlink()
    compile_packs(tmp_path)
    lock = tmp_path / "pack.lock.json"
    document = json.loads(lock.read_bytes())
    document["aliases"]["alpha/../../unrelated"] = f"sha256:{SHARED_DIGEST}"
    lock.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValidationFailed, match="invalid path"):
        compile_packs(tmp_path, check=True)
    with pytest.raises(ValidationFailed, match="invalid path"):
        FilesystemPackReader().read_dir(str(tmp_path / "alpha"))
