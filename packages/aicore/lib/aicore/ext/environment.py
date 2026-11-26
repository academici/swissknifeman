"""The environment a plugin or subscriber command runs in: an allowlist, never a copy of the host's.

Only a fixed set of harmless names (plus every ``LC_*``) passes from the source environment. A
*trusted* plugin may also receive the names it lists in ``permissions.env`` and the secrets it lists in
``permissions.secrets`` (``env://NAME`` references, resolved here and handed over under ``NAME``); an
untrusted one gets neither, and the ignored requests are reported by :func:`ignored_requests` for status
output. Secret values are returned to the caller only so that the process layer can redact them from
captured output; they are never logged, raised or kept. stdlib and ``aicore.config.secrets`` only.
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

from ..config import secrets as _secrets
from ..state import envtable
from .errors import ExtError

BASE_ALLOW = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TZ", "TMPDIR", "TERM", *envtable.NAMES,
              "AICORE_ROOT", "SKM_UNITS_PATH", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME",
              "XDG_CACHE_HOME")
LOCALE_PREFIX = "LC_"
RESERVED_PREFIX = "SKM_EXT_"
PROFILES = ("trusted-local", "read-only")


def _permission_list(permissions: Optional[Mapping[str, object]], key: str) -> List[str]:
    value = (permissions or {}).get(key) or []
    return [item for item in value if isinstance(item, str)] if isinstance(value, (list, tuple)) else []


def _allowed(name: str) -> bool:
    return name in BASE_ALLOW or name.startswith(LOCALE_PREFIX)


def clean_environment(source_env: Mapping[str, str], *, permissions: Optional[Mapping[str, object]] = None,
                      trusted: bool = False, extra: Optional[Mapping[str, str]] = None
                      ) -> Tuple[Dict[str, str], List[str]]:
    """Return ``(env, secret_values)`` for a child process.

    ``permissions`` is a ``permissions/v1`` object. ``extra`` holds per-call ``SKM_*`` variables
    (``ValueError`` for other names or for the reserved ``SKM_EXT_*``). ``SKM_EXT_PROTOCOL=1`` and
    ``SKM_EXT_TRUSTED=0|1`` are always set. A secret reference of a scheme other than ``env`` raises
    ``ExtError("PLUGIN_SECRET_UNSUPPORTED")``; a malformed or unresolvable one raises the
    :class:`~aicore.config.ConfigError` of the resolver. Neither carries a secret value.
    """
    env: Dict[str, str] = {name: value for name, value in source_env.items()
                           if isinstance(name, str) and isinstance(value, str) and _allowed(name)}
    secret_values: List[str] = []
    if trusted:
        for name in _permission_list(permissions, "env"):
            if name.startswith(RESERVED_PREFIX):
                continue
            value = source_env.get(name)
            if isinstance(value, str):
                env[name] = value
        for ref in _permission_list(permissions, "secrets"):
            scheme, name = _secrets.split_ref(ref)
            if scheme != "env":
                raise ExtError("PLUGIN_SECRET_UNSUPPORTED",
                               f"secret scheme {scheme!r} is not supported for plugins; only env:// is")
            if name.startswith(RESERVED_PREFIX):
                continue
            value = _secrets.resolve_ref(ref, source_env)
            env[name] = value
            if value not in secret_values:
                secret_values.append(value)
    for name, value in (extra or {}).items():
        if not isinstance(name, str) or not name.startswith("SKM_") or name.startswith(RESERVED_PREFIX):
            raise ValueError(f"extra variable {name!r} must start with SKM_ and not with {RESERVED_PREFIX}")
        if not isinstance(value, str):
            raise ValueError(f"extra variable {name!r} must be a string")
        env[name] = value
    env[RESERVED_PREFIX + "PROTOCOL"] = "1"
    env[RESERVED_PREFIX + "TRUSTED"] = "1" if trusted else "0"
    return env, secret_values


def ignored_requests(permissions: Optional[Mapping[str, object]], *, trusted: bool) -> List[str]:
    """Texts for the status output: what an untrusted plugin asked for and did not get."""
    if trusted:
        return []
    found = []
    for name in _permission_list(permissions, "env"):
        found.append(f"environment variable {name} ignored: the plugin is not trusted")
    for ref in _permission_list(permissions, "secrets"):
        found.append(f"secret {ref} ignored: the plugin is not trusted")
    return found


def effective_profile(permissions: Optional[Mapping[str, object]]) -> Dict[str, object]:
    """The profile a launch runs under; ``{"profile": name, "enforced": False}`` for ``trusted-local``.

    The host enforces no sandbox yet, so ``read-only`` raises ``ExtError("PLUGIN_PROFILE_UNAVAILABLE")``
    instead of pretending. Status output reads the declared ``permissions.profile`` directly.
    """
    name = (permissions or {}).get("profile", "trusted-local")
    if name not in PROFILES:
        raise ExtError("PLUGIN_PROFILE_UNAVAILABLE", f"unknown permission profile {name!r}")
    if name == "read-only":
        raise ExtError("PLUGIN_PROFILE_UNAVAILABLE",
                       "the read-only profile is not enforced by this host; the plugin was not started")
    return {"profile": name, "enforced": False}
