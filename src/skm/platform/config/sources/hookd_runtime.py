"""Host paths shared by the hook transport and filesystem sandbox launchers."""

from __future__ import annotations

import os
import pwd
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["runtime_dir", "runtime_overlaps"]


def _fallback() -> Path:
    return Path(pwd.getpwuid(os.geteuid()).pw_dir) / ".skm-hookd"


def runtime_dir(environ: Mapping[str, str]) -> Path:
    configured = environ.get("XDG_RUNTIME_DIR")
    return Path(configured) / "skm" if configured else _fallback()


def runtime_overlaps(path: Path, environ: Mapping[str, str] = os.environ) -> bool:
    """Check both endpoints even when the daemon has yet to create its directory."""
    real = path.resolve()
    for endpoint in {runtime_dir(environ), _fallback()}:
        if endpoint.is_absolute():
            private = endpoint.resolve()
            if real.is_relative_to(private) or private.is_relative_to(real):
                return True
    return False
