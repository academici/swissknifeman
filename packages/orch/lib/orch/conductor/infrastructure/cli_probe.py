"""Which flags a provider CLI lists: one help command per CLI, version, help command and flags, cached for the process.

The help command comes from the isolation profile (``codex exec --help``: the flags of ``exec`` are not in
``codex --help``); its first word is replaced by the CLI of the route. A timeout is tried once more; a help that still
cannot be read lists nothing (the flag counts as missing, :func:`failed` says why). What a missing flag means for a run
(``ISOLATION_PARTIAL``, once per run) is the caller's: ``application/route_service.knows``."""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

PROVIDERS = {"claude": "claude-code", "codex": "codex", "grok": "grok"}  # CLI name -> provider id
TIMEOUT_S = 20
# A CLI is its file (realpath, inode, size, mtime): a CLI replaced at the same path (an update) is asked again.
_KNOWN: dict = {}  # (identity, version, help argv, flags) -> whether the help lists the flags
_HELP: dict = {}  # (identity, version, help argv) -> help text, None when it could not be read
_VERSION: dict = {}  # identity -> first line of ``<cli> --version``, "unknown" when it could not be read


def command(argv: list) -> Optional[str]:
    """The provider CLI of ``argv`` (past a launcher such as ``ro-run.py ... --``), ``None`` for a stand-in."""
    return next((arg for arg in argv if os.path.basename(arg) in PROVIDERS), None)


def provider(argv: list) -> Optional[str]:
    found = command(argv)
    return PROVIDERS[os.path.basename(found)] if found else None


def _run(args: list) -> Optional[str]:
    """stdout of ``args``; one more try after a timeout; ``None`` when it cannot be read."""
    for _attempt in range(2):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S).stdout
        except subprocess.TimeoutExpired:
            continue
        except (OSError, subprocess.SubprocessError):
            return None
    return None


def _identity(cli: str) -> tuple:
    """The file of ``cli``: its real path and, when it can be read, its inode, size and change time."""
    real = os.path.realpath(shutil.which(cli) or cli)
    try:
        found = os.stat(real)
    except OSError:
        return (real,)
    return real, found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns


def version(argv: list) -> Optional[str]:
    """The first line of ``<cli> --version`` of the CLI of ``argv`` (``unknown`` when it cannot be read), ``None`` for a
    stand-in; asked again when the file of the CLI changed."""
    cli = command(argv)
    if cli is None:
        return None
    identity = _identity(cli)
    if identity not in _VERSION:
        text = _run([cli, "--version"])
        lines = (text or "").strip().splitlines()
        _VERSION[identity] = lines[0].strip() if lines and lines[0].strip() else "unknown"
    return _VERSION[identity]


def _help(cli: str, help_argv: Optional[list]) -> tuple:
    """``(key, text)`` of the help command of ``cli``."""
    args = [cli, *(help_argv[1:] if help_argv else ["--help"])]
    key = (_identity(cli), version([cli]), tuple(args[1:]))
    if key not in _HELP:
        _HELP[key] = _run(args)
    return key, _HELP[key]


def knows(argv: list, flags: list, *, help_argv: Optional[list] = None) -> bool:
    """Whether the provider CLI of ``argv`` lists every one of ``flags`` in its help (``help_argv``, else
    ``<cli> --help``); a stand-in or a wrapper the conductor does not know passes the flags as asked, which confirms
    nothing (:func:`command` is ``None``: the isolation plan of such a route stays partial)."""
    cli = command(argv)
    if cli is None:
        return True
    key, text = _help(cli, help_argv)
    found = (*key, tuple(flags))
    if found not in _KNOWN:
        _KNOWN[found] = text is not None and all(flag in text for flag in flags)
    return _KNOWN[found]


def failed(argv: list, *, help_argv: Optional[list] = None) -> bool:
    """Whether the help of the CLI of ``argv`` could not be read (a missing flag is then unknown, not absent)."""
    cli = command(argv)
    return cli is not None and _help(cli, help_argv)[1] is None
