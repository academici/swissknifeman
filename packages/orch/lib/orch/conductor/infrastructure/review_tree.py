"""Git content identities for review receipts, including modes and symlink target blobs."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import subprocess

from aicore.util.proc import run as run_with_timeout


def _git(root: Path, *args: str) -> str:
    done = run_with_timeout(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip() or done.returncode}")
    return done.stdout


def path_fingerprint(root: Path, path: str) -> str:
    """Git blob identity including executable mode and the symlink target, without filters."""
    target = root / path
    try:
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return "absent"
    if stat.S_ISLNK(mode):
        blob = subprocess.run(["git", "hash-object", "--stdin"], cwd=root,
                              input=os.fsencode(os.readlink(target)), capture_output=True, check=True, timeout=60)
        return "120000 " + blob.stdout.decode("ascii").strip()
    if stat.S_ISREG(mode):
        return ("100755 " if mode & 0o111 else "100644 ") + _git(root, "hash-object", "--no-filters", "--", path).strip()
    return "other"


def candidate(project: Path, paths) -> dict:
    """The reviewed contents, ordered by repository path; HEAD is metadata, not the freshness test."""
    found = {path: path_fingerprint(project, path) for path in sorted(set(paths))}
    payload = "\n".join(f"{path}\t{value}" for path, value in found.items())
    return {"head": _git(project, "rev-parse", "HEAD").strip(),
            "digest": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(), "paths": found}


def review_outside(project: Path, base: str, paths, exclude=()) -> dict:
    """Product changes already present at review time, beyond the item's candidate."""
    names = set(_git(project, "diff", "--name-only", "-z", base, "--").split("\0"))
    names |= set(_git(project, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    excluded = [".swissknifeman", *[name.rstrip("/") for name in exclude if name]]
    return {path: path_fingerprint(project, path) for path in sorted(names - set(paths))
            if path and not any(path == name or path.startswith(name + "/") for name in excluded)}
