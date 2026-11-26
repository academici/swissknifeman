"""Authenticated and bounded local Unix socket transport for hook evaluation."""

from __future__ import annotations

import os
import socket
import stat
import struct
import sys
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from time import monotonic, time

from skm.platform.config.sources.hookd_runtime import runtime_dir

__all__ = ["capability_proven", "exchange", "listen", "remember_capability", "serve"]

_SOCKET = "hookd.sock"
_MAX_MESSAGE = 1_048_576 + 4096
_READ_SECONDS = 2.0
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _open_runtime(environ: Mapping[str, str], *, create: bool = False) -> Generator[tuple[Path, int]]:
    path = runtime_dir(environ)
    if path.anchor != "/" or ".." in path.parts:
        raise PermissionError("hookd runtime path must be absolute and canonical")
    uid = os.geteuid()
    fd = os.open("/", _DIRECTORY)
    try:
        trusted_owners = {uid, 0, os.fstat(fd).st_uid}
        for part in path.parts[1:-1]:
            child = os.open(part, _DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = child
            entry = os.fstat(fd)
            if entry.st_uid not in trusted_owners or (
                entry.st_mode & 0o022 and not entry.st_mode & stat.S_ISVTX
            ):
                raise PermissionError("hookd runtime ancestor is writable by another user")
        if create:
            with suppress(FileExistsError):
                os.mkdir(path.name, mode=0o700, dir_fd=fd)
        child = os.open(path.name, _DIRECTORY, dir_fd=fd)
        os.close(fd)
        fd = child
        if not _private(os.fstat(fd), 0o700):
            raise PermissionError("hookd runtime directory must be user-owned and mode 0700")
        yield path, fd
    finally:
        os.close(fd)


_CAPABILITY = "claude-capability"
_CAPABILITY_MAX = 512


def capability_proven(environ: Mapping[str, str], key: str, ttl_seconds: float) -> bool:
    """True when ``remember_capability`` stored exactly ``key`` less than ``ttl_seconds`` ago.

    Only a private, user-owned regular file inside the private runtime directory counts; anything else,
    including a missing directory, is "not proven" and the caller probes again.
    """
    try:
        with _open_runtime(environ) as (_, fd):
            file = os.open(_CAPABILITY, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
            try:
                entry = os.fstat(file)
                if (
                    not stat.S_ISREG(entry.st_mode)
                    or not _private(entry, 0o600)
                    or entry.st_size > _CAPABILITY_MAX
                ):
                    return False
                age = time() - entry.st_mtime
                content = os.read(file, _CAPABILITY_MAX).decode("utf-8")
            finally:
                os.close(file)
    except (OSError, UnicodeDecodeError):
        return False
    return 0 <= age < ttl_seconds and content == key


def remember_capability(environ: Mapping[str, str], key: str) -> None:
    """Store a successful probe for ``key``; best effort, never raises."""
    name = f"{_CAPABILITY}.{os.getpid()}.tmp"
    with suppress(OSError), _open_runtime(environ) as (_, fd):
        file = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            os.write(file, key.encode("utf-8")[:_CAPABILITY_MAX])
        finally:
            os.close(file)
        try:
            os.rename(name, _CAPABILITY, src_dir_fd=fd, dst_dir_fd=fd)
        except OSError:
            with suppress(OSError):
                os.unlink(name, dir_fd=fd)


def _private(entry: os.stat_result, mode: int) -> bool:
    return entry.st_uid == os.geteuid() and stat.S_IMODE(entry.st_mode) == mode


def _socket_entry(fd: int) -> os.stat_result:
    entry = os.stat(_SOCKET, dir_fd=fd, follow_symlinks=False)
    if not stat.S_ISSOCK(entry.st_mode) or not _private(entry, 0o600) or entry.st_nlink != 1:
        raise PermissionError("hookd endpoint must be a user-owned socket with mode 0600")
    return entry


def _address(path: Path, fd: int) -> str:
    # Linux resolves the socket relative to the pinned directory even if it is renamed.
    if sys.platform == "linux":
        return f"/proc/self/fd/{fd}/{_SOCKET}"
    # Ancestors of this pathname were opened without following links and checked for ownership.
    # BSD bind never replaces an existing entry, including a symlink.
    return str(path / _SOCKET)


def _check_runtime_path(path: Path, fd: int) -> None:
    if not os.path.samestat(path.lstat(), os.fstat(fd)):
        raise PermissionError("hookd runtime directory changed")


def _peer_uid(peer: socket.socket) -> int:
    if sys.platform == "linux":
        credentials = struct.Struct("=iII")  # struct ucred: pid, uid, gid
        _, uid, _ = credentials.unpack(
            peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, credentials.size)
        )
        return uid
    if sys.platform == "darwin" or sys.platform.startswith(("freebsd", "openbsd", "netbsd", "dragonfly")):
        # Python does not expose getpeereid on all supported builds.
        import ctypes

        getpeereid = ctypes.CDLL(None, use_errno=True).getpeereid
        getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        getpeereid.restype = ctypes.c_int
        euid, egid = ctypes.c_uint(), ctypes.c_uint()
        if getpeereid(peer.fileno(), ctypes.byref(euid), ctypes.byref(egid)) != 0:
            raise PermissionError(ctypes.get_errno(), "hookd could not verify peer credentials")
        return euid.value
    raise PermissionError("hookd requires Unix peer credentials")


def _authenticate(peer: socket.socket) -> None:
    try:
        uid = _peer_uid(peer)
    except (AttributeError, OSError, struct.error) as error:
        raise PermissionError("hookd could not verify peer credentials") from error
    if uid != os.geteuid():
        raise PermissionError("hookd peer UID differs from the current EUID")


def _receive(peer: socket.socket, deadline: float) -> bytes:
    message = bytearray()
    while len(message) <= _MAX_MESSAGE:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("hookd message deadline exceeded")
        peer.settimeout(remaining)
        chunk = peer.recv(min(65536, _MAX_MESSAGE + 1 - len(message)))
        if not chunk:
            return bytes(message)
        message += chunk
    raise ValueError("hookd message exceeds its size limit")


@contextmanager
def listen(environ: Mapping[str, str]) -> Generator[socket.socket]:
    with _open_runtime(environ, create=True) as (path, fd), socket.socket(socket.AF_UNIX) as listener:
        # This is the only listener in the foreground daemon. The bind is atomic and never replaces
        # an existing entry. Set permissions at creation time instead of chmod'ing a pathname.
        mask = os.umask(0o177)
        try:
            _check_runtime_path(path, fd)
            listener.bind(_address(path, fd))
            entry = _socket_entry(fd)
        finally:
            os.umask(mask)
        try:
            _check_runtime_path(path, fd)
            listener.listen()
            listener.settimeout(0.25)
            yield listener
        finally:
            with suppress(FileNotFoundError):
                if os.path.samestat(os.stat(_SOCKET, dir_fd=fd, follow_symlinks=False), entry):
                    os.unlink(_SOCKET, dir_fd=fd)


def serve(listener: socket.socket, evaluate: Callable[[bytes], bytes], stopped: Callable[[], bool]) -> None:
    while not stopped():
        try:
            peer, _ = listener.accept()
        except TimeoutError:
            continue
        with peer, suppress(OSError, ValueError):
            _authenticate(peer)
            raw = _receive(peer, monotonic() + _READ_SECONDS)
            reply = evaluate(raw)
            if len(reply) > _MAX_MESSAGE:
                raise ValueError("hookd reply exceeds its size limit")
            peer.settimeout(_READ_SECONDS)
            peer.sendall(reply)


def exchange(environ: Mapping[str, str], request: bytes, *, timeout: float) -> bytes:
    if len(request) > _MAX_MESSAGE:
        raise ValueError("hookd request exceeds its size limit")
    with _open_runtime(environ) as (path, fd), socket.socket(socket.AF_UNIX) as peer:
        entry = _socket_entry(fd)
        deadline = monotonic() + timeout
        peer.settimeout(timeout)
        peer.connect(_address(path, fd))
        _authenticate(peer)
        _check_runtime_path(path, fd)
        if not os.path.samestat(_socket_entry(fd), entry):
            raise PermissionError("hookd endpoint changed during connection")
        peer.settimeout(max(0, deadline - monotonic()))
        peer.sendall(request)
        peer.shutdown(socket.SHUT_WR)
        return _receive(peer, deadline)
