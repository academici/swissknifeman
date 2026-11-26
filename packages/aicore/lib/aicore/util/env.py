"""Base immutable execution context shared by monorepo packages."""
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()


@dataclass(frozen=True)
class BaseEnv:
    """Execution context with repository root, command, and home directory.

    Values are explicit for testability; ``__post_init__`` normalizes paths.
    """

    root: Path
    cmd: str = ""
    # Resolve Path.home() per instance so tests can replace HOME.
    home: Path = field(default_factory=lambda: Path.home())

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root))
        object.__setattr__(self, "home", Path(self.home))
