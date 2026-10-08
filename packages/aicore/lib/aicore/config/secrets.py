"""Secret references and the :class:`Secret` handle.

A configuration file never holds a secret, only a reference such as ``env://NAME``. The value is
looked up when :meth:`Secret.reveal` is called and is neither kept nor shown anywhere: not in
``repr``/``str``, not in an error message, not in a traceback. A failed lookup raises
:class:`~aicore.config.ConfigError` with no chained cause, because the cause may carry the value.
The ``env`` scheme is built in; other schemes are added with :func:`register_secret_resolver`.
stdlib only.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Dict, Mapping, Optional, Tuple

from . import ConfigError

REF_PATTERN = re.compile(r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?P<path>\S+)$")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
BUILTIN_SCHEMES = ("env",)

_resolvers: Dict[str, Callable[[str], str]] = {}


def register_secret_resolver(scheme: str, fn: Callable[[str], str]) -> None:
    """Register ``fn(path) -> str`` for ``<scheme>://<path>`` references.

    A scheme can be registered once; the built-in ``env`` cannot be replaced (``ValueError``).
    """
    if not isinstance(scheme, str) or not _SCHEME.match(scheme):
        raise ValueError(f"invalid secret scheme: {scheme!r}")
    if not callable(fn):
        raise ValueError("a secret resolver must be callable")
    if scheme in BUILTIN_SCHEMES or scheme in _resolvers:
        raise ValueError(f"a secret resolver for {scheme!r} is already registered")
    _resolvers[scheme] = fn


def unregister_secret_resolver(scheme: str) -> None:
    """Remove a resolver added by :func:`register_secret_resolver` (for tests and plugin unload)."""
    if scheme in BUILTIN_SCHEMES:
        raise ValueError(f"the built-in {scheme!r} resolver cannot be removed")
    _resolvers.pop(scheme, None)


def is_secret_ref(value: object) -> bool:
    """True for a string of the form ``<scheme>://<path>``."""
    return isinstance(value, str) and REF_PATTERN.match(value) is not None


def split_ref(ref: str) -> Tuple[str, str]:
    """``(scheme, path)`` of a reference; ``SECRET_REF_INVALID`` (never echoing the text) otherwise."""
    match = REF_PATTERN.match(ref) if isinstance(ref, str) else None
    if match is None:
        raise ConfigError("SECRET_REF_INVALID", "not a secret reference of the form <scheme>://<name> "
                                                "(value redacted)")
    return match.group("scheme"), match.group("path")


def _env_value(path: str, env: Optional[Mapping[str, str]]) -> Optional[str]:
    if not _ENV_NAME.match(path):
        return None
    return (os.environ if env is None else env).get(path)


def resolve_ref(ref: str, env: Optional[Mapping[str, str]] = None) -> str:
    """Look the reference up now. Raises ``SECRET_SCHEME_UNKNOWN`` or ``SECRET_UNRESOLVED``."""
    scheme, path = split_ref(ref)
    if scheme == "env":
        value = _env_value(path, env)
        failed = value is None or value == ""
    else:
        resolver = _resolvers.get(scheme)
        if resolver is None:
            raise ConfigError("SECRET_SCHEME_UNKNOWN", f"no resolver for the secret scheme {scheme!r}; "
                              "register a resolver, resolver plugins arrive with aicore extensions")
        value, failed = None, False
        try:
            value = resolver(path)
        except Exception:  # noqa: BLE001 - the resolver's failure may carry the value: drop it entirely
            failed = True
        failed = failed or not isinstance(value, str) or value == ""
    if failed:
        # Raised outside the except block: no __context__ keeps the original error alive.
        raise ConfigError("SECRET_UNRESOLVED", f"secret {ref} could not be resolved") from None
    return value


class Secret:
    """A reference to a secret. The value exists only as the result of :meth:`reveal`."""

    __slots__ = ("ref", "_resolve")

    def __init__(self, ref: str, resolve: Optional[Callable[[], str]] = None) -> None:
        split_ref(ref)
        self.ref = ref
        self._resolve = resolve if resolve is not None else (lambda: resolve_ref(ref))

    def reveal(self) -> str:
        """Resolve now; nothing is cached, so a rotated secret is seen on the next call."""
        return self._resolve()

    def __repr__(self) -> str:
        return f"Secret({self.ref!r})"

    def __str__(self) -> str:
        return "***"

    def __reduce__(self):
        raise TypeError("Secret cannot be serialized; keep the reference instead")
