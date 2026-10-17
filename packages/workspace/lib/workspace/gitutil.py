"""Git for the workspace: every call is an argument list (no shell) with a C locale, and every call that changes the
workspace repository runs under ``git.lock`` (invariant W7). Remote URLs are shown without user information."""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from aicore.config import ConfigError, resolve
from aicore.state import ensure_dir, workspace_state_dir
from aicore.workspace import WorkspaceError, redact_remote

UNIT_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = "git.lock"
DEFAULT_LOCK_TIMEOUT_S = 60.0
MIN_GIT_INIT = (2, 28)  # git init -b
MIN_GIT_WORKSPACE = (2, 38)
_POLL_S = 0.05

PathLike = Union[str, "os.PathLike[str]"]
Env = Optional[Mapping[str, str]]


def run(argv: Sequence[str], cwd: PathLike, input: Optional[str] = None, timeout: float = 300.0,
        env: Env = None, binary: bool = False) -> "subprocess.CompletedProcess[Any]":
    """Run ``argv`` in ``cwd`` without a shell, with ``LC_ALL=C`` and no terminal prompts; never raises for a failing
    command (read ``returncode``). A missing git is ``WORKSPACE_GIT_TOO_OLD``.

    Text is decoded with ``surrogateescape``: a byte that is not UTF-8 (a pathname from ``-z`` output) comes back as a lone
    surrogate and ``os.fsencode`` restores it, so the path still names the same file. ``binary`` returns bytes."""
    environment = dict(os.environ if env is None else env)
    environment.update(LC_ALL="C", GIT_TERMINAL_PROMPT="0")
    mode: Dict[str, Any] = {} if binary else {"text": True, "errors": "surrogateescape"}
    try:
        return subprocess.run(list(argv), cwd=str(cwd), input=input, capture_output=True, env=environment,
                              timeout=timeout, check=False, **mode)
    except FileNotFoundError:
        raise WorkspaceError("WORKSPACE_GIT_TOO_OLD", "git is not installed or not on PATH") from None
    except subprocess.TimeoutExpired:
        raise WorkspaceError("REMOTE_UNREACHABLE", f"git {argv[1] if len(argv) > 1 else ''} timed out") from None


def git(args: Sequence[str], cwd: PathLike, input: Optional[str] = None, env: Env = None) -> "subprocess.CompletedProcess[str]":
    return run(["git", *args], cwd, input=input, env=env)


def git_bytes(args: Sequence[str], cwd: PathLike, env: Env = None) -> "subprocess.CompletedProcess[bytes]":
    """``git`` with the output kept as bytes (file content)."""
    return run(["git", *args], cwd, env=env, binary=True)


def require(done: "subprocess.CompletedProcess[str]", what: str) -> str:
    """The stdout of a successful git call; a failure is ``WORKSPACE_LAYOUT_INVALID`` with the redacted message."""
    if done.returncode != 0:
        detail = redact_remote_text(done.stderr.strip() or done.stdout.strip() or f"exit {done.returncode}")
        raise WorkspaceError("WORKSPACE_LAYOUT_INVALID", f"git {what} failed: {detail}")
    return done.stdout


_URL_USERINFO = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")


def redact_remote_text(text: str) -> str:
    """``text`` with the user information of every URL in it removed."""
    return _URL_USERINFO.sub(r"\1", text)


def git_version(cwd: PathLike = ".") -> Optional[Tuple[int, ...]]:
    """The installed git version as a tuple, or ``None`` when git is missing or its output is not understood."""
    try:
        done = run(["git", "--version"], cwd, timeout=30)
    except WorkspaceError:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", done.stdout)
    return tuple(int(part) for part in match.groups(default="0")) if match else None


def lock_timeout(env: Env = None, home: Optional[PathLike] = None) -> float:
    """``workspace.git.lock_timeout_s`` of the configuration (machine and defaults layers); 60 s when unreadable."""
    try:
        config = resolve("workspace", unit_root=UNIT_ROOT, env=env, home=home, warn=lambda message: None)
        return float(config.get("git.lock_timeout_s"))
    except (ConfigError, TypeError, ValueError):
        return DEFAULT_LOCK_TIMEOUT_S


@contextmanager
def git_lock(env: Env = None, home: Optional[PathLike] = None, timeout_s: Optional[float] = None) -> Iterator[None]:
    """Hold ``flock(LOCK_EX)`` on ``workspace_state_dir()/git.lock`` while the workspace repository is changed;
    after ``timeout_s`` (default: the configured limit) ``WORKSPACE_GIT_LOCKED``."""
    wait = lock_timeout(env, home) if timeout_s is None else timeout_s
    folder = workspace_state_dir(env, home)
    ensure_dir(folder)
    fd = os.open(str(folder / LOCK_FILE), os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        deadline = time.monotonic() + max(wait, 0.0)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise WorkspaceError("WORKSPACE_GIT_LOCKED", f"another process holds the workspace git lock "
                                         f"(waited {wait:g} s); try again") from None
                time.sleep(_POLL_S)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def identity_args(cwd: PathLike) -> Sequence[str]:
    """``-c user.name=... -c user.email=...`` for the settings git does not have, so a commit never fails on a machine
    without a git identity."""
    args = []
    for key, fallback in (("user.name", "skm-workspace"), ("user.email", "workspace@localhost")):
        if not git(["config", "--get", key], cwd).stdout.strip():
            args += ["-c", f"{key}={fallback}"]
    return args


def remote_of(cwd: PathLike, name: str = "origin") -> Optional[str]:
    """The URL of remote ``name`` without user information, or ``None``."""
    done = git(["remote", "get-url", name], cwd)
    return redact_remote(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None
