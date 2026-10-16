#!/usr/bin/env python3
"""Run a command with the whole filesystem readable and writable only in a few directories (Linux Landlock).

Landlock needs neither root nor user namespaces, so it works where bubblewrap sandboxes are refused (Ubuntu
`apparmor_restrict_unprivileged_userns`). The ruleset applies to this process before `exec` and every child
inherits it; a process can never lift it.

Usage: ro-run.py [--rw DIR]... [--no-default-rw] -- COMMAND [ARGS...]

Writable by default: /tmp, /var/tmp, /dev and ~/.grok (the reviewer CLI keeps its session there). A missing
directory is skipped. Exit 3 with LANDLOCK_UNAVAILABLE when the kernel offers no Landlock.
"""
from __future__ import annotations

import ctypes
import os
import platform
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

DEFAULT_WRITABLE = ("/tmp", "/var/tmp", "/dev", "~/.grok")


def _die(code: str, message: str, status: int = 1) -> None:
    print(f"{code}: {message}", file=sys.stderr)
    sys.exit(status)


def _parse(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        _die("USAGE", "ro-run.py [--rw DIR]... [--no-default-rw] -- COMMAND [ARGS...]", 2)
    split = argv.index("--")
    options, command = argv[:split], argv[split + 1:]
    if not command:
        _die("USAGE", "a command is required after --", 2)
    writable = [] if "--no-default-rw" in options else [os.path.expanduser(path) for path in DEFAULT_WRITABLE]
    index = 0
    while index < len(options):
        option = options[index]
        if option == "--rw" and index + 1 < len(options):
            writable.append(options[index + 1])
            index += 2
        elif option == "--no-default-rw":
            index += 1
        else:
            _die("USAGE", f"unknown option {option!r}", 2)
    return writable, command


def restrict(writable: list[str]) -> None:
    """Make every path outside ``writable`` read-only for this process and its children."""
    if platform.system() != "Linux":
        _die("LANDLOCK_UNAVAILABLE", "Landlock is a Linux kernel feature", 3)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = libc.syscall(SYS_CREATE_RULESET, None, 0, CREATE_RULESET_VERSION)
    if abi < 1:
        _die("LANDLOCK_UNAVAILABLE", f"the kernel offers no Landlock ({os.strerror(ctypes.get_errno())})", 3)
    handled = WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_ANY
    handled |= REFER if abi >= 2 else 0
    handled |= TRUNCATE if abi >= 3 else 0
    attr = struct.pack("=Q", handled)
    ruleset = libc.syscall(SYS_CREATE_RULESET, attr, len(attr), 0)
    if ruleset < 0:
        _die("LANDLOCK_FAILED", f"create ruleset: {os.strerror(ctypes.get_errno())}")
    for path in writable:
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
    writable, command = _parse(argv)
    restrict(writable)
    try:
        os.execvp(command[0], command)
    except OSError as error:
        _die("EXEC_FAILED", f"{command[0]}: {error.strerror}", 127)


if __name__ == "__main__":
    main(sys.argv[1:])
