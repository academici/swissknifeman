"""Git remotes as identity hints: normalization for matching, redaction for output, the remotes of a checkout.

A remote is never the identity of a project (the marker is); ``workspace project attach`` only uses the normalized
form to find an existing project of a checkout that has no marker yet.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Union

_URL = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://(.*)$", re.S)
_SCP = re.compile(r"^(?:[^@/\s]+@)?([^:/\s]+):(.*)$", re.S)
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_NET_SCHEMES = ("https", "http", "ssh", "git", "git+ssh", "ssh+git")
_PORT_DROPPED = ("ssh", "git", "git+ssh", "ssh+git")


def _split_authority(rest: str):
    authority, slash, path = rest.partition("/")
    host = authority.rpartition("@")[2]
    return host, path if slash else ""


def normalize_remote(url: str) -> Optional[str]:
    """``host/owner/repo`` for a network remote (scheme, user information, ssh port, trailing ``/`` and ``.git`` removed,
    host lower-cased, path as is); ``None`` for a local path, ``file://`` or anything that is not a network remote."""
    text = (url or "").strip()
    if not text or text.startswith(("/", ".", "~")) or _DRIVE.match(text):
        return None
    scheme = None
    match = _URL.match(text)
    if match:
        scheme = match.group(1).lower()
        if scheme not in _NET_SCHEMES:
            return None
        host, path = _split_authority(match.group(2))
        port = None
        if ":" in host and not host.endswith("]"):
            host, _, port = host.rpartition(":")
        if port and scheme not in _PORT_DROPPED and port.isdigit():
            host = f"{host}:{port}"
    else:
        scp = _SCP.match(text)
        if not scp:
            return None
        host, path = scp.group(1), scp.group(2)
    host = host.lower()
    path = path.strip()
    while path.endswith("/") or path.endswith(".git"):
        path = path[:-1] if path.endswith("/") else path[:-4]
    path = path.lstrip("/")
    if not host or not path or any(char.isspace() for char in host + path):
        return None
    return f"{host}/{path}"


def redact_remote(url: str) -> str:
    """The remote without user information (``user:token@``), for output and logs."""
    text = (url or "").strip()
    match = _URL.match(text)
    if match:
        authority, slash, path = match.group(2).partition("/")
        return f"{match.group(1)}://{authority.rpartition('@')[2]}{slash}{path}"
    scp = re.match(r"^[^@/\s]+@([^:/\s]+:.*)$", text, re.S)
    return scp.group(1) if scp else text


def checkout_remotes(root: Union[str, "os.PathLike[str]"]) -> List[str]:
    """Normalized fetch remotes of the checkout at ``root``, unique, in the order git lists them; ``[]`` when ``root`` is
    not a git checkout or git is missing."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(["git", "-C", str(Path(root)), "remote", "-v"], capture_output=True, check=False,
                              env=env, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    found: List[str] = []
    for line in done.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[-1] != "(fetch)":
            continue
        normalized = normalize_remote(" ".join(parts[1:-1]))
        if normalized is not None and normalized not in found:
            found.append(normalized)
    return found
