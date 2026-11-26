"""Isolation profile identifiers (00-conventions §4.0.3, D-REG-6, ADR 0022).

How a step process is launched: four built-in profiles form a closed enum; plugins add profiles only under the
key ``<plugin_id>:<name>``. This is unrelated to the database ``Isolation`` of ``ports_uow``.
"""

import re
from enum import StrEnum
from typing import Final, NewType

__all__ = [
    "ISOLATION_PLUGIN_PATTERN",
    "IsolationProfile",
    "PluginIsolationProfile",
    "is_builtin_isolation_profile",
    "is_plugin_isolation_profile",
    "parse_isolation_profile",
]


class IsolationProfile(StrEnum):
    """Closed enum of the four built-in profiles (D-REG-6)."""

    NONE = "none"
    WORKTREE = "worktree"
    LANDLOCK = "landlock"
    CONTAINER = "container"


_BUILTIN_VALUES: Final = frozenset(profile.value for profile in IsolationProfile)

# Same pattern as the ``isolation_profile`` definition of the policy schemas.
ISOLATION_PLUGIN_PATTERN: Final = r"^[a-z0-9_.-]+:[a-z0-9_-]+$"
_PLUGIN_PROFILE: Final = re.compile(r"[a-z0-9_.-]+:[a-z0-9_-]+")

PluginIsolationProfile = NewType("PluginIsolationProfile", str)  # "<plugin_id>:<name>"


def is_builtin_isolation_profile(text: str) -> bool:
    return text in _BUILTIN_VALUES


def is_plugin_isolation_profile(text: str) -> bool:
    # fullmatch: "$" would accept a trailing newline.
    return _PLUGIN_PROFILE.fullmatch(text) is not None


def parse_isolation_profile(text: str) -> IsolationProfile | PluginIsolationProfile:
    """Parse a built-in enum or plugin profile; reject unknown values."""
    if not isinstance(text, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"isolation profile must be str, got {type(text).__name__}")
    if is_builtin_isolation_profile(text):
        return IsolationProfile(text)
    if is_plugin_isolation_profile(text):
        return PluginIsolationProfile(text)
    raise ValueError(f"not an isolation profile: {text!r}")
