"""Allowlisted, bounded, read-only user-home observations (integrations §6.2)."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skm.modules.integrations.domain.contracts import UserHomeSelector

__all__ = ["LocalUserHomeReader"]


class LocalUserHomeReader:
    """Read only fixed native locations; never follow links or accept filesystem selectors."""

    def __init__(
        self,
        home: Path | None = None,
        *,
        managed_root: Path = Path("/etc/claude-code"),
        max_bytes: int = 1_048_576,
    ) -> None:
        self.home = (home if home is not None else Path.home()).absolute()
        self.managed_root = managed_root.absolute()
        self.max_bytes = max_bytes

    def read(self, logical: UserHomeSelector) -> bytes | None:
        locations = {
            "claude.user_settings": (self.home, (".claude", "settings.json")),
            "claude.managed_settings": (self.managed_root, ("managed-settings.json",)),
            "codex.user_config": (self.home, (".codex", "config.toml")),
            "gemini.user_settings": (self.home, (".gemini", "settings.json")),
            "vscode.user_settings": (self.home, (".config", "Code", "User", "settings.json")),
        }
        if logical not in locations:
            raise ValueError("Unsupported user-home observation selector")
        root, parts = locations[logical]
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptors: list[int] = []
        try:
            # Walk from / so ancestor links cannot redirect even the configured home root.
            directory = os.open(root.anchor, flags | os.O_DIRECTORY)
            descriptors.append(directory)
            for part in (*root.parts[1:], *parts[:-1]):
                if part in (".", ".."):
                    raise ValueError("Unsafe user-home observation root")
                directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                descriptors.append(directory)
            fd = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=directory)
            descriptors.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("User-home observation must be a regular file")
            chunks: list[bytes] = []
            remaining = self.max_bytes + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > self.max_bytes:
                raise OSError("User-home observation exceeds the byte limit")
        except FileNotFoundError:
            return None
        else:
            return raw
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
