"""Safe path-containment helpers for traversal and symlink-escape protection.

Both checks fail closed when path resolution fails. stdlib-only.
"""
from pathlib import Path


def is_within(path, root):
    """Return whether ``path`` resolves inside or equals ``root``; fail closed."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def state_dir(home, app=None):
    """Return the umbrella state root or its application subdirectory.

    maind deliberately owns its separate ``~/.maind`` state directory.
    """
    base = Path(home) / ".swissknifeman"
    return base / app if app else base


def is_within_lexical(path, root):
    """Check lexical containment without resolving the final ``path`` symlink.

    This is intended for install gates and fails closed on resolution errors.
    """
    try:
        base = Path(root).resolve()
        full = Path(path).parent.resolve() / Path(path).name
        return full == base or base in full.parents
    except (OSError, ValueError):
        return False
