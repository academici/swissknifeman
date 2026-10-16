"""Which local files a research query may read, and reading one without following a swap.

A file is read only when its name is not a secret one, git does not ignore it (inside a work tree) and, at the
moment it is opened, it is a regular file of bounded size that is not a symlink: the type is checked on the open
descriptor, so a file replaced by a fifo or a link after the walk saw it is refused instead of blocking or leaking.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Optional

MAX_FILE_BYTES = 1_000_000
GIT_TIMEOUT_S = 30
SKIPPED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".swissknifeman", ".ssh", ".gnupg", ".aws", ".kube",
                          ".docker", ".azure", ".gcloud", ".config"})
# Files that hold secrets are never read into a prompt, whatever the query
SECRET_FILE = re.compile(r"^(\.env($|[.-]|rc$)|id_(rsa|dsa|ecdsa|ed25519)|\.netrc|\.npmrc|\.pypirc|\.pgpass|\.htpasswd|"
                         r"\.dockercfg|kubeconfig)|(secret|token|password|credential)|"
                         r"\.(pem|key|p8|p12|pfx|keystore|jks|kdbx|gpg|asc)$", re.IGNORECASE)


def is_secret_name(name: str) -> bool:
    return bool(SECRET_FILE.search(name))


def git_visible(top: Path) -> Optional[frozenset]:
    """The files git shows under ``top`` (tracked, and untracked that no ignore rule hides), as resolved paths;
    ``None`` outside a work tree or without git: then only the name rules apply."""
    try:
        listed = subprocess.run(["git", "-C", str(top), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                capture_output=True, timeout=GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        return None
    base = top.resolve()
    return frozenset(str(base / name) for name in listed.stdout.decode("utf-8", "surrogateescape").split("\0") if name)


def read_text(path: Path, limit: int = MAX_FILE_BYTES) -> Optional[str]:
    """The UTF-8 text of a regular file of at most ``limit`` bytes; ``None`` for anything else."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)  # a fifo opens, then is refused
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            return None
        data = handle.read(limit + 1)
    if len(data) > limit:  # grew after the check
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None
