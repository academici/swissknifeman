"""``PackagedBuiltinPacks``: the packs built into the product (extensions §3, §6; control-plane gateway).

Reads pack directories below ``skm/_resources/packs`` through ``importlib.resources``, direct packs first.
directory without ``pack.toml`` is no pack (a slot of the source tree); a tree without packaged resources has
none. Files are bytes: nothing is imported or run. A symlink at any level below the root, a pack directory
itself included, is refused before anything is followed, so a payload holds only bytes of the packaged tree.
Installer bytecode caches for adjacent Python source files are excluded from pack payloads.
"""

from collections.abc import Iterator
from importlib import resources
from importlib.resources.abc import Traversable
from importlib.util import source_from_cache
from pathlib import Path

from skm.adapters.resources.compiled_pack import BLOB_DIR, LOCK_NAME, MANIFEST, enclosing_lock_root, read_lock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile

__all__ = ["PackagedBuiltinPacks"]


def _packaged_root() -> Traversable:
    return resources.files("skm").joinpath("_resources", "packs")


def _refuse_symlink(item: Traversable, path: str) -> None:
    if isinstance(item, Path) and item.is_symlink():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "a built-in pack holds a symlink",
            details={"reason": "unexpected_symlink", "path": path},
        )


def _is_source_cache(item: Traversable, source_folder: Traversable) -> bool:
    if not item.name.endswith(".pyc"):
        return False
    try:
        source_name = Path(source_from_cache(str(Path("__pycache__", item.name)))).name
    except ValueError:
        return False
    source = source_folder.joinpath(source_name)
    if isinstance(source, Path) and source.is_symlink():
        return False
    return source.is_file()


def _walk(folder: Traversable, prefix: str, *, source_folder: Traversable | None = None) -> list[PayloadFile]:
    found: list[PayloadFile] = []
    for item in sorted(folder.iterdir(), key=lambda entry: entry.name):
        if not prefix and item.name in {LOCK_NAME, BLOB_DIR}:
            continue
        path = f"{prefix}{item.name}"
        _refuse_symlink(item, path)
        if item.is_dir():
            parent = folder if item.name == "__pycache__" else None
            found.extend(_walk(item, f"{path}/", source_folder=parent))
        elif source_folder is None or not _is_source_cache(item, source_folder):
            found.append(PayloadFile(path, item.read_bytes()))
    return found


def _pack_folders(root: Traversable, prefix: str = "") -> Iterator[tuple[Traversable, str]]:
    groups: list[tuple[Traversable, str]] = []
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        if item.name in {LOCK_NAME, BLOB_DIR}:
            continue
        relative = prefix + item.name
        _refuse_symlink(item, relative)
        if item.is_dir():
            manifest = item.joinpath(MANIFEST)
            _refuse_symlink(manifest, f"{relative}/{MANIFEST}")
            if manifest.is_file():
                yield item, relative
            else:
                groups.append((item, relative))
    for group, relative in groups:
        yield from _pack_folders(group, relative + "/")


class PackagedBuiltinPacks:
    """``root`` replaces the packaged directory (a test or a build check)."""

    def __init__(self, root: Traversable | None = None) -> None:
        self._root = root

    def payloads(self) -> tuple[PackPayload, ...]:
        root = self._root if self._root is not None else _packaged_root()
        if not root.is_dir():
            return ()
        compiled_root = enclosing_lock_root(root) if isinstance(root, Path) else root
        lock = read_lock(compiled_root) if compiled_root is not None else None
        payloads: list[PackPayload] = []
        for folder, relative in _pack_folders(root):
            manifest = folder.joinpath(MANIFEST)
            files = [item for item in _walk(folder, "") if item.path != MANIFEST]
            if lock is not None and compiled_root is not None:
                prefix = (
                    folder.resolve().relative_to(compiled_root).as_posix()
                    if isinstance(folder, Path) and isinstance(compiled_root, Path)
                    else relative
                )
                files.extend(lock[0].assets(compiled_root, prefix + "/", {item.path for item in files}))
            elif (own_lock := read_lock(folder)) is not None:
                files.extend(own_lock[0].assets(folder, "", {item.path for item in files}))
            payloads.append(
                PackPayload(
                    manifest.read_text(encoding="utf-8"),
                    tuple(sorted(files, key=lambda item: item.path.split("/"))),
                )
            )
        return tuple(payloads)
