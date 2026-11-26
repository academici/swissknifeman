"""Run a command with every path readable and writable only below a few directories (Linux Landlock).

Port of the read-only runner ``ro-run.py`` (examples/adapters/sandbox/landlock.md, normative; adapters §7.1).
The ruleset applies to this process before ``execvp``; every child inherits it and nothing can lift it. It
needs neither root nor user namespaces. Only *writes* are restricted: read confidentiality, network, process
containment and disk quota are not provided here, so a request needing them uses another backend (§7.3).
Not even every write: ``chmod``/``chown``/``utime``/``setxattr`` outside the grants stay possible, and
``truncate(2)`` too below ABI 3; ``--protect`` only keeps a directory out of the grants.

Usage: ``python3 -m skm.adapters.sandbox.landlock_exec [--rw DIR]... [--protect DIR]... [--no-default-rw]
[--min-abi N] -- COMMAND [ARGS...]``. Exit codes: 2 usage; 3 ``LANDLOCK_UNAVAILABLE``/
``LANDLOCK_ABI_TOO_OLD``/``LANDLOCK_GRANT_INVALID``/``RO_RUN_PROTECT_OVERLAP``/``RO_RUN_RW_ESCAPE``; 1
``LANDLOCK_FAILED``; 127 ``EXEC_FAILED``. Messages go to stderr as ``CODE: message``. SKM always passes
``--no-default-rw`` with explicit grants and ``--min-abi``; the legacy defaults (``/tmp``, ``/var/tmp``,
``/dev``) remain only for the standalone use of the donor.

Fail closed before ``exec``: a kernel below ``--min-abi`` or without Landlock, an explicit ``--rw`` that is
not an existing directory (the ruleset would silently grant less than asked) and any failing syscall end the
process with the command never started. The restriction binds this process and what it execs or forks,
nothing else: unconfined processes of the same user stay unconstrained and a confined command can still ask
them to act (a local socket, a signal), so this is write confinement of one process tree, not protection of
the user's files. File descriptors above 2 are closed before ``exec``: Landlock checks a path when it is
opened, so a descriptor inherited from an unconfined parent would keep its write access. The whole range is
closed (``/proc/self/fd``, else ``close_range(2)``); when neither is usable the command is not started (exit 1
``LANDLOCK_FAILED``): a loop bounded by ``RLIMIT_NOFILE`` could miss a descriptor above a lowered hard limit.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass

# Classes (``WrapperError``, ``Plan``) stay out of ``__all__``: adapters export declarations/factories only.
__all__ = ["check_grants", "handled_access", "landlock_abi", "main", "parse", "probe_enforcement", "restrict"]

# Landlock syscalls have one number on every Linux architecture that has them (asm-generic table).
SYS_CREATE_RULESET, SYS_ADD_RULE, SYS_RESTRICT_SELF = 444, 445, 446
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

WRITE_FILE, REMOVE_DIR, REMOVE_FILE = 1 << 1, 1 << 4, 1 << 5
MAKE_ANY = sum(1 << bit for bit in range(6, 13))  # char, dir, regular, socket, fifo, block, symlink
REFER, TRUNCATE = 1 << 13, 1 << 14  # Landlock ABI 2 and 3

DEFAULT_WRITABLE = ("/tmp", "/var/tmp", "/dev")  # noqa: S108 - legacy standalone defaults, never used by SKM
USAGE = "landlock_exec [--rw DIR]... [--protect DIR]... [--no-default-rw] [--min-abi N] -- COMMAND [ARGS...]"


class WrapperError(Exception):
    """A refusal of the wrapper: ``CODE: message`` on stderr and ``status`` as the exit code."""

    def __init__(self, code: str, message: str, status: int = 1) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True, slots=True)
class Plan:
    writable: tuple[str, ...]
    protected: tuple[str, ...]
    explicit: tuple[str, ...]
    command: tuple[str, ...]
    min_abi: int = 0


def _inside(path: str, root: str) -> bool:
    return os.path.commonpath((path, root)) == root


def check_grants(
    writable: Sequence[str], protected: Sequence[str], explicit: Sequence[str], defaults: Sequence[str]
) -> tuple[str, ...]:
    """Validate the grants before resolving them, so a symlink cannot widen a protected checkout (exit 3)."""
    roots = [os.path.realpath(path) for path in defaults]
    for directory in protected:
        resolved = os.path.realpath(directory)
        for root in roots:
            if _inside(resolved, root):
                raise WrapperError("RO_RUN_PROTECT_OVERLAP", f"{resolved} is inside writable {root}", 3)
            if _inside(root, resolved):  # a default root under the protected tree would stay writable
                raise WrapperError("RO_RUN_PROTECT_OVERLAP", f"writable {root} is inside {resolved}", 3)
        for path in explicit:
            absolute, real = os.path.abspath(path), os.path.realpath(path)
            if _inside(resolved, real):  # the grant is the protected directory or one of its ancestors
                raise WrapperError("RO_RUN_RW_ESCAPE", path, 3)
            if (
                _inside(absolute, os.path.abspath(directory))
                or _inside(absolute, resolved)
                or _inside(real, resolved)
            ):
                try:
                    symlink = stat.S_ISLNK(os.lstat(absolute).st_mode)
                except FileNotFoundError:
                    symlink = False  # a missing grant is skipped, as without --protect
                if symlink or not _inside(real, resolved):
                    raise WrapperError("RO_RUN_RW_ESCAPE", path, 3)
    return tuple(os.path.realpath(path) for path in writable)


def parse(argv: Sequence[str]) -> Plan:
    """Options and command from ``argv`` (exit 2 on usage errors, exit 3 on protect conflicts)."""
    if "--" not in argv:
        raise WrapperError("USAGE", USAGE, 2)
    split = argv.index("--")
    options, command = list(argv[:split]), tuple(argv[split + 1 :])
    if not command:
        raise WrapperError("USAGE", "a command is required after --", 2)
    defaults = [] if "--no-default-rw" in options else [os.path.expanduser(path) for path in DEFAULT_WRITABLE]
    writable = list(defaults)
    protected: list[str] = []
    explicit: list[str] = []
    min_abi = 0
    index = 0
    while index < len(options):
        option = options[index]
        if option == "--rw" and index + 1 < len(options):
            writable.append(os.path.expanduser(options[index + 1]))
            explicit.append(os.path.expanduser(options[index + 1]))
            index += 2
        elif option == "--protect" and index + 1 < len(options):
            protected.append(os.path.expanduser(options[index + 1]))
            index += 2
        elif option == "--min-abi" and index + 1 < len(options) and options[index + 1].isdecimal():
            min_abi = int(options[index + 1])
            index += 2
        elif option == "--no-default-rw":
            index += 1
        else:
            raise WrapperError("USAGE", f"unknown option {option!r}", 2)
    if protected:
        writable = list(check_grants(writable, protected, explicit, defaults))
    return Plan(
        tuple(writable),
        tuple(os.path.realpath(path) for path in protected),
        tuple(explicit),
        command,
        min_abi,
    )


def _libc() -> ctypes.CDLL:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    return libc


def landlock_abi() -> int:
    """Kernel Landlock ABI version; ``0`` when the kernel offers none or this is not Linux."""
    if platform.system() != "Linux":
        return 0
    try:
        abi = int(_libc().syscall(SYS_CREATE_RULESET, None, 0, CREATE_RULESET_VERSION))
    except (OSError, AttributeError):
        return 0
    return max(abi, 0)


def handled_access(abi: int) -> int:
    """Filesystem accesses the ruleset restricts on ``abi``. Below ABI 3 ``TRUNCATE`` is not handled, so
    ``truncate(2)`` empties any same-UID file outside the grants; chmod, chown, utime and xattr changes are
    never handled (landlock.h): callers needing either guarantee must not rely on this wrapper."""
    handled = WRITE_FILE | REMOVE_DIR | REMOVE_FILE | MAKE_ANY
    handled |= REFER if abi >= 2 else 0
    handled |= TRUNCATE if abi >= 3 else 0
    return handled


def restrict(
    writable: Sequence[str],
    protected: Sequence[str] = (),
    *,
    min_abi: int = 0,
    required: Sequence[str] = (),
) -> None:
    """Make every path outside ``writable`` unwritable for this process and its children.

    ``min_abi`` refuses a kernel below it; a ``writable`` path also listed in ``required`` must be an existing
    directory (exit 3 ``LANDLOCK_GRANT_INVALID``), the others are skipped when missing (legacy defaults)."""
    if platform.system() != "Linux":
        raise WrapperError("LANDLOCK_UNAVAILABLE", "Landlock is a Linux kernel feature", 3)
    libc = _libc()
    abi = int(libc.syscall(SYS_CREATE_RULESET, None, 0, CREATE_RULESET_VERSION))
    if abi < 1:
        raise WrapperError(
            "LANDLOCK_UNAVAILABLE", f"the kernel offers no Landlock ({os.strerror(ctypes.get_errno())})", 3
        )
    needed = max(min_abi, 3 if protected else 0)
    if abi < needed:
        raise WrapperError("LANDLOCK_ABI_TOO_OLD", f"kernel ABI {abi}, required {needed}", 3)
    must_exist = {os.path.realpath(path) for path in required}
    handled = handled_access(abi)
    attr = struct.pack("=Q", handled)
    ruleset = int(libc.syscall(SYS_CREATE_RULESET, attr, len(attr), 0))
    if ruleset < 0:
        raise WrapperError("LANDLOCK_FAILED", f"create ruleset: {os.strerror(ctypes.get_errno())}")
    for path in writable:
        try:
            fd = os.open(path, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError as error:
            if os.path.realpath(path) in must_exist:
                raise WrapperError("LANDLOCK_GRANT_INVALID", f"{path}: {error.strerror}", 3) from error
            continue
        try:
            rule = struct.pack("=Qi", handled, fd)
            if libc.syscall(SYS_ADD_RULE, ruleset, RULE_PATH_BENEATH, rule, 0) != 0:
                raise WrapperError(
                    "LANDLOCK_FAILED", f"allow writes under {path}: {os.strerror(ctypes.get_errno())}"
                )
        finally:
            os.close(fd)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise WrapperError("LANDLOCK_FAILED", f"no_new_privs: {os.strerror(ctypes.get_errno())}")
    if libc.syscall(SYS_RESTRICT_SELF, ruleset, 0) != 0:
        raise WrapperError("LANDLOCK_FAILED", f"restrict self: {os.strerror(ctypes.get_errno())}")
    os.close(ruleset)


_CANARY = """
import os, sys
allowed, denied = sys.argv[1:3]
open(os.path.join(allowed, "ok"), "w").write("x")
victim = os.path.join(denied, "victim")
for attempt in (lambda: open(os.path.join(denied, "new"), "w"), lambda: os.truncate(victim, 0)):
    try:
        attempt()
    except PermissionError:
        continue
    sys.exit(11)
print("enforced")
"""


def probe_enforcement(python: str = sys.executable, min_abi: int = 3, timeout: float = 30.0) -> str | None:
    """Run the launcher on a canary command: ``None`` if it confined that command, else why it did not.

    A kernel can report an ABI and still refuse the ruleset (security policy, seccomp, a container runtime),
    so the version query is no evidence of enforcement. The probe shows only what it ran: one child process
    tree of this launcher, one granted directory and one denied directory."""
    root: str | None = None
    try:
        root = tempfile.mkdtemp(prefix="skm-landlock-probe-")
        allowed, denied = os.path.join(root, "allowed"), os.path.join(root, "denied")
        os.mkdir(allowed)
        os.mkdir(denied)
        victim = os.path.join(denied, "victim")
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("kept")
        command = [python, "-P", "-m", "skm.adapters.sandbox.landlock_exec", "--no-default-rw"]
        command += ["--min-abi", str(min_abi), "--rw", allowed, "--", python, "-c", _CANARY, allowed, denied]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            return f"the launcher did not run ({type(error).__name__})"
        with open(victim, encoding="utf-8") as handle:
            kept = handle.read() == "kept"
    except OSError as error:  # no space, no temp dir, unreadable victim: unproven, never a crash
        return f"the probe could not be set up or read back ({type(error).__name__}: {error.strerror})"
    finally:
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)
    if done.returncode == 0 and done.stdout.strip() == "enforced" and kept:
        return None
    detail = done.stderr.strip().splitlines()[-1:] or [f"exit {done.returncode}"]
    return f"the canary was not confined ({detail[0]})" if done.returncode in (0, 11) else detail[0]


_SYS_CLOSE_RANGE = 436  # one number on every architecture that has it (Linux 5.9+)


def _close_all_above_stderr_without_proc() -> None:
    """Close descriptors 3.. when ``/proc/self/fd`` cannot be listed: the whole range or a refusal.

    Only ``close_range(2)`` takes the entire range at once. A loop up to ``RLIMIT_NOFILE`` is no substitute:
    a descriptor opened under a higher limit stays open above a hard limit lowered afterwards, so such a
    bound can miss it. Without ``close_range`` the launcher refuses rather than claim a complete cleanup."""
    try:
        done = _libc().syscall(_SYS_CLOSE_RANGE, 3, 0xFFFFFFFF, 0) == 0
    except (OSError, AttributeError):
        done = False
    if not done:
        raise WrapperError(
            "LANDLOCK_FAILED",
            "cannot close inherited descriptors: neither /proc/self/fd nor close_range is usable",
        )


def _close_inherited_descriptors() -> None:
    """Close every descriptor above stderr: one opened for writing before the restriction stays writable.
    Raises ``WrapperError`` when that cannot be done completely."""
    try:
        numbers = [int(name) for name in os.listdir("/proc/self/fd")]
    except (OSError, ValueError):
        _close_all_above_stderr_without_proc()
        return
    for number in numbers:
        if number > 2:
            try:
                os.close(number)
            except OSError:
                continue  # the directory listing's own descriptor


def main(argv: Sequence[str]) -> int:
    """Restrict this process, then ``execvp`` the command; returns only an exit status of a refusal."""
    try:
        plan = parse(argv)
        restrict(plan.writable, plan.protected, min_abi=plan.min_abi, required=plan.explicit)
    except WrapperError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return error.status
    try:
        _close_inherited_descriptors()
    except WrapperError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return error.status
    try:
        os.execvp(plan.command[0], list(plan.command))
    except OSError as error:
        sys.stderr.write(f"EXEC_FAILED: {plan.command[0]}: {error.strerror}\n")
        return 127
    return 127  # pragma: no cover - execvp does not return on success


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
