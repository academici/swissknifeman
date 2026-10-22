"""Safe path-containment helpers for traversal and symlink-escape protection.

Both checks fail closed when path resolution fails. stdlib-only; the same answers on Python 3.11–3.14
(``Path.resolve()`` raises on a symlink loop up to 3.12 and silently keeps the loop from 3.13).
"""
import errno
import os
from pathlib import Path


def resolve_path(path):
    """Canonical absolute path without symlinks; a missing tail is allowed.

    ``OSError`` on a symlink loop or an unresolvable component, ``ValueError`` on ``..`` in a missing tail.
    ``..`` is not normalized textually: it applies to the already resolved parent, as the OS does.
    """
    text = os.fspath(path)
    if not os.path.isabs(text):
        text = os.path.join(os.getcwd(), text)
    if hasattr(os.path, "ALLOW_MISSING"):  # 3.13.4+, 3.14 and the backports to older minor versions
        return Path(os.path.realpath(text, strict=os.path.ALLOW_MISSING))
    head, tail = text, []
    while not os.path.lexists(head):  # the longest existing prefix
        parent, name = os.path.split(head)
        if parent == head:
            break
        head = parent
        tail.append(name)
    if ".." in tail:
        raise ValueError("'..' in a missing path tail")
    try:
        resolved = Path(head).resolve(strict=True)  # a loop raises (RuntimeError up to 3.12, OSError later)
    except RuntimeError:
        raise OSError(errno.ELOOP, "symlink loop", head) from None
    return resolved.joinpath(*reversed(tail))


def is_within(path, root):
    """Return whether ``path`` resolves inside or equals ``root``; fail closed."""
    try:
        resolve_path(path).relative_to(resolve_path(root))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def is_within_lexical(path, root, *, allow_root=True):
    """Check lexical containment without resolving the final ``path`` symlink.

    Normalize a final ``..`` without following a final symlink. Destructive install gates
    can set ``allow_root=False`` to require a child of the destination root. Fail closed
    on resolution errors, including symlink loops.
    """
    try:
        base = resolve_path(root)
        full = Path(os.path.abspath(resolve_path(Path(path).parent) / Path(path).name))
        return (allow_root and full == base) or base in full.parents
    except (OSError, ValueError, RuntimeError):
        return False
