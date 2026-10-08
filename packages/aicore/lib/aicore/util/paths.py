"""Safe path-containment helpers for traversal and symlink-escape protection.

Both checks fail closed when path resolution fails. stdlib-only.
"""
import os
from pathlib import Path


def is_within(path, root):
    """Return whether ``path`` resolves inside or equals ``root``; fail closed."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def state_dir(home, app=None):
    """Return the umbrella state root or its application subdirectory.

    Legacy location: new code uses :mod:`aicore.state` (XDG places, ``SKM_HOME``). Kept for the
    modules that are not moved yet. maind deliberately owns its separate ``~/.maind`` directory.
    """
    base = Path(home) / ".swissknifeman"
    return base / app if app else base


def is_within_lexical(path, root, *, allow_root=True):
    """Check lexical containment without resolving the final ``path`` symlink.

    Normalize a final ``..`` without following a final symlink. Destructive install gates
    can set ``allow_root=False`` to require a child of the destination root. Fail closed
    on resolution errors, including symlink loops on older Python versions.
    """
    try:
        base = Path(root).resolve()
        full = Path(os.path.abspath(Path(path).parent.resolve() / Path(path).name))
        return (allow_root and full == base) or base in full.parents
    except (OSError, ValueError, RuntimeError):
        return False
