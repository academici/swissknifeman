"""Explicit child environment: no ambient reads, secrets or legacy markers."""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

__all__ = ["BASE_ALLOW", "LOCALE_PREFIX", "build_env"]

BASE_ALLOW: Final = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TZ", "TMPDIR", "TERM")
LOCALE_PREFIX: Final = "LC_"


def build_env(
    source: Mapping[str, str],
    *,
    allow: Iterable[str] = (),
    extra: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> dict[str, str]:
    allowed = frozenset(allow) | frozenset(BASE_ALLOW)
    env = {name: value for name, value in source.items() if name in allowed or name.startswith(LOCALE_PREFIX)}
    if extra is not None:
        env.update(extra)
    if home is not None:
        env["HOME"] = str(home)
    for name, value in env.items():
        if not isinstance(name, str) or not name or "=" in name or "\0" in name:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("invalid environment name")
        if not isinstance(value, str) or "\0" in value:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("environment values must be strings without NUL")
    return env
