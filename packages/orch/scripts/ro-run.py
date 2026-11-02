#!/usr/bin/env python3
"""Run a command with the whole filesystem readable and writable only in a few directories (Linux Landlock).

Landlock needs neither root nor user namespaces, so it works where bubblewrap sandboxes are refused (Ubuntu
`apparmor_restrict_unprivileged_userns`). The ruleset applies to this process before `exec` and every child
inherits it; a process can never lift it.

Usage: ro-run.py [--rw DIR]... [--protect DIR]... [--no-default-rw] -- COMMAND [ARGS...]

Writable by default: /tmp, /var/tmp and /dev. A missing
directory is skipped. Exit 3 with LANDLOCK_UNAVAILABLE when the kernel offers no Landlock.
--protect requires ABI 3 (TRUNCATE) and refuses default writable overlap or escaping --rw paths.
"""
from __future__ import annotations

import ctypes
import errno
import os
import platform
import stat
import struct
import sys

# Landlock syscalls have one number on every Linux architecture that has them (asm-generic table).
SYS_CREATE_RULESET, SYS_ADD_RULE, SYS_RESTRICT_SELF = 444, 445, 446
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

WRITE_FILE, REMOVE_DIR, REMOVE_FILE = 1 << 1, 1 << 4, 1 << 5
MAKE_ANY = sum(1 << bit for bit in range(6, 13))  # char, dir, regular, socket, fifo, block, symlink
REFER, TRUNCATE = 1 << 13, 1 << 14  # Landlock ABI 2 and 3

DEFAULT_WRITABLE = ("/tmp", "/var/tmp", "/dev")


def _die(code: str, message: str, status: int = 1) -> None:
    print(f"{code}: {message}", file=sys.stderr)
    sys.exit(status)


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath((path, root)) == root


def _protect(writable: list[str], protected: list[str], explicit: list[str], defaults: list[str]) -> list[str]:
    """Validate grants before resolving them, so symlinks cannot widen a protected checkout."""
    roots = [os.path.realpath(path) for path in defaults]
    for directory in protected:
        resolved = os.path.realpath(directory)
        for root in roots:
            if _inside(resolved, root):
                _die("RO_RUN_PROTECT_OVERLAP", f"{resolved} is inside writable {root}", 3)
            if _inside(root, resolved):  # a default root under the protected tree would stay writable
                _die("RO_RUN_PROTECT_OVERLAP", f"writable {root} is inside {resolved}", 3)
        for path in explicit:
            absolute, real = os.path.abspath(path), os.path.realpath(path)
            if _inside(resolved, real):  # the grant is the protected directory or one of its ancestors
                _die("RO_RUN_RW_ESCAPE", path, 3)
            if _inside(absolute, os.path.abspath(directory)) or _inside(absolute, resolved) or _inside(real, resolved):
                try:
                    symlink = stat.S_ISLNK(os.lstat(absolute).st_mode)
                except FileNotFoundError:
                    symlink = False  # a missing grant is skipped, as without --protect
                if symlink or not _inside(real, resolved):
                    _die("RO_RUN_RW_ESCAPE", path, 3)
    return [os.path.realpath(path) for path in writable]


def _parse(argv: list[str]) -> tuple[list[str], list[str], list[str]]:
    if "--" not in argv:
        _die("USAGE", "ro-run.py [--rw DIR]... [--protect DIR]... [--no-default-rw] -- COMMAND [ARGS...]", 2)
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]
    if not command:
        _die("USAGE", "a command is required after --", 2)
    defaults = [] if "--no-default-rw" in options else [os.path.expanduser(path) for path in DEFAULT_WRITABLE]
    writable = list(defaults)
    protected, explicit = [], []
    index = 0
    while index < len(options):
        option = options[index]
        if option in ("--rw", "--rw-strict") and index + 1 < len(options):
            if option == "--rw-strict":
                writable.append(("strict", options[index + 1]))
                index += 2
                continue
            writable.append(os.path.expanduser(options[index + 1]))
            explicit.append(os.path.expanduser(options[index + 1]))
            index += 2
        elif option == "--protect" and index + 1 < len(options):
            protected.append(os.path.expanduser(options[index + 1]))
            index += 2
        elif option == "--no-default-rw":
            index += 1
        else:
            _die("USAGE", f"unknown option {option!r}", 2)
    if protected:
        if any(isinstance(path, tuple) for path in writable):
            _die("RO_RUN_RW_ESCAPE", "--rw-strict cannot be combined with --protect", 3)
        writable = _protect(writable, protected, explicit, defaults)
    return writable, command, [os.path.realpath(path) for path in protected]


def _landlock_abi(libc) -> int:
    return libc.syscall(SYS_CREATE_RULESET, None, 0, CREATE_RULESET_VERSION)


def protect_metadata() -> None:
    """Deny metadata mutation and asynchronous syscall bypasses for protected checks.

    Landlock does not mediate chmod, timestamps or extended attributes. Seccomp
    cannot resolve paths, so these operations are denied even in scratch space.
    Only the audited native x86-64 syscall table is supported; fail closed on
    other architectures and on the x32 ABI.
    """
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        _die("METADATA_GUARD_UNAVAILABLE", "unsupported platform or architecture", 3)
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    # chmod/chown, timestamps, xattrs, io_uring, ptrace and mount APIs.
    denied = (90, 91, 92, 93, 94, 101, 132, 133, 155, 161, 165, 166, 188, 189, 190,
              197, 198, 199, 235, 260, 261, 268, 272, 280, 304, 308, 310, 311, 321,
              323, 425, 426, 427, 428, 429, 430, 431, 432, 433, 442, 452, 463, 466, 467, 469)
    ins = [Filter(0x20, 0, 0, 4), Filter(0x15, 1, 0, 0xC000003E),
           Filter(0x06, 0, 0, 0x80000000), Filter(0x20, 0, 0, 0),
           Filter(0x35, 0, 1, 0x40000000), Filter(0x06, 0, 0, 0x80000000)]
    # Deny 335..423 (including the uprobe calls and reserved gap) and future
    # syscall numbers until their effects have been audited.
    ins.extend((Filter(0x35, 0, 1, 470), Filter(0x06, 0, 0, 0x00050000 | errno.EPERM),
                Filter(0x35, 0, 2, 335), Filter(0x35, 1, 0, 424),
                Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)))
    # FIOCLEX only sets FD_CLOEXEC on the descriptor. CPython uses it when
    # opening a script; all other ioctls can mutate filesystem metadata.
    # ioctl's request is an unsigned int: seccomp_data.args[1] low word is at 24.
    ins.extend((Filter(0x15, 0, 4, 16), Filter(0x20, 0, 0, 24),
                Filter(0x15, 0, 1, 0x5451), Filter(0x06, 0, 0, 0x7FFF0000),
                Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)))
    for number in denied:
        ins.extend((Filter(0x15, 0, 1, number), Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)))
    ins.append(Filter(0x06, 0, 0, 0x7FFF0000))
    array = (Filter * len(ins))(*ins)
    program = Program(len(ins), array)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:  # PR_SET_SECCOMP, FILTER
        _die("METADATA_GUARD_UNAVAILABLE", os.strerror(ctypes.get_errno()), 3)


def restrict(writable: list[str], protected: list[str] | tuple[str, ...] = ()) -> None:
    """Make every path outside ``writable`` read-only for this process and its children."""
    if platform.system() != "Linux":
        _die("LANDLOCK_UNAVAILABLE", "Landlock is a Linux kernel feature", 3)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = _landlock_abi(libc)
    if abi < 1:
        _die("LANDLOCK_UNAVAILABLE", f"the kernel offers no Landlock ({os.strerror(ctypes.get_errno())})", 3)
    if protected and abi < 3:
        _die("LANDLOCK_ABI_TOO_OLD", str(abi), 3)
    handled = WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_ANY
    handled |= REFER if abi >= 2 else 0
    handled |= TRUNCATE if abi >= 3 else 0
    attr = struct.pack("=Q", handled)
    ruleset = libc.syscall(SYS_CREATE_RULESET, attr, len(attr), 0)
    if ruleset < 0:
        _die("LANDLOCK_FAILED", f"create ruleset: {os.strerror(ctypes.get_errno())}")
    for path in writable:
        if isinstance(path, tuple):
            path = path[1]
            if not os.path.isabs(path) or os.path.normpath(path) != path:
                _die("RO_RUN_RW_ESCAPE", path, 3)
            fd = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                for part in path.split("/")[1:]:
                    child = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                    os.close(fd)
                    fd = child
            except OSError:
                os.close(fd)
                _die("RO_RUN_RW_ESCAPE", path, 3)
            try:
                rule = struct.pack("=Qi", handled, fd)
                if libc.syscall(SYS_ADD_RULE, ruleset, RULE_PATH_BENEATH, rule, 0) != 0:
                    _die("LANDLOCK_FAILED", f"allow writes under {path}: {os.strerror(ctypes.get_errno())}")
            finally:
                os.close(fd)
            continue
        if not os.path.isdir(path):
            continue
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = struct.pack("=Qi", handled, fd)
            if libc.syscall(SYS_ADD_RULE, ruleset, RULE_PATH_BENEATH, rule, 0) != 0:
                _die("LANDLOCK_FAILED", f"allow writes under {path}: {os.strerror(ctypes.get_errno())}")
        finally:
            os.close(fd)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        _die("LANDLOCK_FAILED", f"no_new_privs: {os.strerror(ctypes.get_errno())}")
    if libc.syscall(SYS_RESTRICT_SELF, ruleset, 0) != 0:
        _die("LANDLOCK_FAILED", f"restrict self: {os.strerror(ctypes.get_errno())}")
    os.close(ruleset)


def main(argv: list[str]) -> None:
    metadata = "--metadata-guard" in argv[:argv.index("--")] if "--" in argv else False
    if metadata:
        argv = argv.copy()
        argv.remove("--metadata-guard")
    writable, command, protected = _parse(argv)
    restrict(writable, protected)
    if metadata:
        protect_metadata()
    try:
        os.execvp(command[0], command)
    except OSError as error:
        _die("EXEC_FAILED", f"{command[0]}: {error.strerror}", 127)


if __name__ == "__main__":
    main(sys.argv[1:])
