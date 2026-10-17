"""Digest of the frozen sidecar tree (``gui-backend.digest``), stdlib only.

``sidecar/build.sh`` writes the file next to the ``gui-backend`` executable after the build; ``gui serve --sidecar``
checks the tree against it before it opens a socket. The file lists every file of the onedir tree (sorted, without the
digest file itself) with its sha256, and ``tree`` is the sha256 of that list as canonical JSON.

ELF files (the executable, shared libraries, extension modules) are listed by name only (``sha256`` is ``"elf"``): the
bundlers (linuxdeploy, patchelf, strip) rewrite them after the build, so their bytes are not known at build time and are
the business of the platform signature. Everything else (the Python sources and data of gui and aicore, the schemas) is
hashed.

Limit: the digest is not signed. It detects a changed, added or removed file of the tree, not an attacker who also
rewrites the digest file; when the file is absent (a run from sources) the check is skipped silently. Both facts are in
docs/security.md.

``python3 -m gui.sidecar_digest write DIR`` writes the file; ``verify DIR`` checks it (exit 3 on a mismatch).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

DIGEST_NAME = "gui-backend.digest"
TAMPERED = "SIDECAR_TAMPERED"
EXIT_TAMPERED = 3
BLOCK = 1024 * 1024
ELF_MAGIC = b"\x7fELF"
ELF_MARK = "elf"  # listed by name only: bundlers rewrite ELF files after the build


class SidecarTampered(Exception):
    """The tree differs from its digest; ``path`` is the first file (sorted) that does."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{TAMPERED}: {path} ({reason})")
        self.path = path
        self.reason = reason


def _file_digest(path: str) -> str:
    """sha256 of a file read in blocks; a symlink counts by its target text, never by what it points at."""
    sha = hashlib.sha256()
    if os.path.islink(path):
        sha.update(b"symlink:" + os.readlink(path).encode("utf-8", "surrogateescape"))
        return sha.hexdigest()
    with open(path, "rb") as handle:
        if handle.read(4) == ELF_MAGIC:
            return ELF_MARK
        handle.seek(0)
        while True:
            block = handle.read(BLOCK)
            if not block:
                break
            sha.update(block)
    return sha.hexdigest()


def _tree_digest(files: List[Dict[str, str]]) -> str:
    text = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan(root: Path) -> List[Dict[str, str]]:
    """Every file under ``root`` (symlinks not followed) as ``{path, sha256}``, sorted, without the digest file."""
    base = str(root)
    found: List[Dict[str, str]] = []
    for folder, dirs, names in os.walk(base, followlinks=False):
        dirs.sort()
        for name in names:
            full = os.path.join(folder, name)
            relative = os.path.relpath(full, base).replace(os.sep, "/")
            if relative == DIGEST_NAME:
                continue
            found.append({"path": relative, "sha256": _file_digest(full)})
        for name in list(dirs):  # a symlink to a folder is an entry of its own
            full = os.path.join(folder, name)
            if os.path.islink(full):
                dirs.remove(name)
                found.append({"path": os.path.relpath(full, base).replace(os.sep, "/"), "sha256": _file_digest(full)})
    found.sort(key=lambda entry: entry["path"])
    return found


def build(root: Path, version: str) -> Dict[str, Any]:
    files = scan(root)
    return {"v": 1, "version": version, "files": files, "tree": _tree_digest(files)}


def write(root: Path, version: str) -> Path:
    document = build(root, version)
    target = Path(root) / DIGEST_NAME
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def verify(root: Path) -> bool:
    """Check the tree against ``DIGEST_NAME``: ``False`` when there is no digest file, ``True`` when it matches.

    ``SidecarTampered`` names the first differing file (sorted); an unreadable or malformed digest file counts as
    tampering with the digest file itself.
    """
    digest_file = Path(root) / DIGEST_NAME
    if not os.path.lexists(digest_file):
        return False
    try:
        document = json.loads(digest_file.read_text(encoding="utf-8"))
        listed = {entry["path"]: entry["sha256"] for entry in document["files"]}
        files = [{"path": entry["path"], "sha256": entry["sha256"]} for entry in document["files"]]
        tree = document["tree"]
    except (OSError, ValueError, KeyError, TypeError):
        raise SidecarTampered(DIGEST_NAME, "unreadable or malformed") from None
    if tree != _tree_digest(sorted(files, key=lambda entry: entry["path"])) or len(listed) != len(files):
        raise SidecarTampered(DIGEST_NAME, "its tree digest does not match its list")
    actual: Dict[str, str] = {}
    for entry in scan(root):
        actual[entry["path"]] = entry["sha256"]
    for path in sorted(set(listed) | set(actual)):
        if path not in actual:
            raise SidecarTampered(path, "missing")
        if path not in listed:
            raise SidecarTampered(path, "not in the digest")
        if actual[path] != listed[path]:
            raise SidecarTampered(path, "changed")
    return True


def frozen_root() -> Optional[Path]:
    """The folder of the frozen executable, or ``None`` when running from sources (nothing to check)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in ("write", "verify"):
        print("usage: python3 -m gui.sidecar_digest write|verify DIR", file=sys.stderr)
        return 2
    root = Path(args[1])
    if args[0] == "write":
        from . import __version__

        print(write(root, __version__))
        return 0
    try:
        present = verify(root)
    except SidecarTampered as error:
        print(str(error), file=sys.stderr)
        return EXIT_TAMPERED
    print("verified" if present else f"no {DIGEST_NAME}: skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
