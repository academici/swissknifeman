"""A few seconds of memory for "this checkout is still the repository it was bound to".

Proving a checkout's identity runs several ``git`` processes. A long-lived process (``skm-hookd``, the worker)
proves the same plain checkout many times a second, so it may reuse a proof while nothing a proof depends on
has changed. The stamp covers the root directory and ``.git``, ``.git/HEAD`` and ``.git/config`` (where the
remotes live). Any change, a worktree or submodule ``.git`` file, or an unreadable path means "prove again".
"""

from __future__ import annotations

import os
import stat
import threading
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from skm.adapters.git.runner import validate_repository_trust

__all__ = ["IdentityProofCache"]

_Stamp = tuple[tuple[int, int, int, int, int], ...]


def _stamp(root: Path) -> _Stamp | None:
    try:
        # Extended worktree layouts can take remotes from a different configuration file.
        for name in ("commondir", "gitdir", "config.worktree"):
            try:
                (root / ".git" / name).lstat()
            except FileNotFoundError:
                continue
            return None
        entries = [
            os.lstat(root),
            os.lstat(root / ".git"),
            os.lstat(root / ".git/HEAD"),
            os.lstat(root / ".git/config"),
        ]
    except OSError:
        return None
    if not stat.S_ISDIR(entries[1].st_mode) or not all(stat.S_ISREG(item.st_mode) for item in entries[2:]):
        return None
    return tuple(
        (item.st_dev, item.st_ino, item.st_mtime_ns, item.st_ctime_ns, item.st_size) for item in entries
    )


class IdentityProofCache:
    """Remember successful identity proofs for ``ttl_seconds``; failures are never remembered."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._proofs: dict[tuple[str, str | None, type], tuple[float, _Stamp]] = {}
        self._lock = threading.Lock()

    def proven(self, root: Path, remote: str | None, prove: Callable[[], None], *, via: type) -> None:
        """Run ``prove`` (raises if the identity fails) unless a fresh proof by ``via`` still applies."""
        key = (str(root), remote, via)
        stamp = _stamp(root)  # taken before the proof, so a change during it is never mistaken for proven
        now = self._clock()
        if stamp is not None:
            with self._lock:
                remembered = self._proofs.get(key)
            if remembered is not None and remembered[1] == stamp and now - remembered[0] < self._ttl:
                validate_repository_trust(root)
                return
        prove()
        with self._lock:
            if stamp is None:
                self._proofs.pop(key, None)
            else:
                if len(self._proofs) >= 256:
                    self._proofs.clear()
                self._proofs[key] = (now, stamp)
