"""Closed security boundary for admitted Artifex provider work.

This module keeps untrusted provider data out of durable evidence.  It is deliberately
small: admission verification remains owned by :mod:`dispatch`; this layer makes that
verified identity mandatory at each package boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import dispatch


_SECRET_KEY = re.compile(r"(?:secret|password|credential|api[_-]?key|authorization|thinking|transcript)", re.I)
_SECRET_VALUE = re.compile(r"(?:\bsk-[A-Za-z0-9]|bearer\s+|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)", re.I)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ENV_NAMES = frozenset(("PATH", "LC_ALL", "LANG", "TZ"))


class SecurityRefusal(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or _SECRET_KEY.search(key):
                raise SecurityRefusal("UNTRUSTED_CONTENT")
            _reject_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive(item)
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise SecurityRefusal("UNTRUSTED_CONTENT")


def indexed_admission(plan_dir: Path, admission_path: Path) -> dict[str, Any]:
    """Load exactly one indexed admission, refusing links, grants and foreign paths."""
    try:
        value = dispatch.load_indexed_admission(plan_dir, admission_path)
    except dispatch.DispatchRefusal as exc:
        raise SecurityRefusal(exc.reason) from exc
    return value


def request(admission: dict[str, Any], value: Any) -> dict[str, Any]:
    """Require an exact, bounded provider request derived from that admission."""
    if not isinstance(value, dict) or set(value) != {"provider", "route", "permissions", "budgets", "bundle", "child_policy"}:
        raise SecurityRefusal("REQUEST_SCHEMA")
    task, grant = admission["task"], admission["grant"]
    provider, route, permissions, budgets, bundle, children = (value[key] for key in ("provider", "route", "permissions", "budgets", "bundle", "child_policy"))
    if (not isinstance(provider, dict) or provider.get("id") != task["provider"]
            or not isinstance(route, dict) or route.get("model_class") != grant["route"]["model_class"]
            or route.get("effort") != grant["route"]["effort"]):
        raise SecurityRefusal("ADMISSION_WIDENING")
    if permissions != {"approval_mode": "never", "sandbox_mode": "read_only", "network_mode": "disabled", "source": "indexed-admission"}:
        raise SecurityRefusal("PERMISSION_WIDENING")
    if budgets != task["budgets"] or not isinstance(bundle, dict) or set(bundle) != {"content_refs"}:
        raise SecurityRefusal("ADMISSION_WIDENING")
    refs = bundle["content_refs"]
    expected = [task["prompt"]["content_hash"], task["response_schema"]["content_hash"]]
    if refs != expected or any(not isinstance(row, str) or not _HEX.fullmatch(row) for row in refs):
        raise SecurityRefusal("CONTENT_REFERENCE_INVALID")
    if children != {"mode": "forbidden", "max_children": 0, "allowed_capabilities": []}:
        raise SecurityRefusal("CAPABILITY_WIDENING")
    _reject_sensitive(value)
    return value


def environment(value: dict[str, str]) -> dict[str, str]:
    """Permit only named, scalar execution environment values; never record them."""
    if not isinstance(value, dict) or set(value) - _ENV_NAMES:
        raise SecurityRefusal("ENVIRONMENT_WIDENING")
    if any(not isinstance(key, str) or not isinstance(item, str) or "\x00" in item for key, item in value.items()):
        raise SecurityRefusal("ENVIRONMENT_INVALID")
    return dict(value)


def observation(value: Any) -> dict[str, Any]:
    """Accept only the normalized, non-content worker outcome."""
    if not isinstance(value, dict):
        raise SecurityRefusal("OBSERVATION_SCHEMA")
    allowed = {"kind", "reason_code", "process_count", "duration_ms", "event_count", "output_hash", "exit_code"}
    if set(value) - allowed or not isinstance(value.get("kind"), str):
        raise SecurityRefusal("OBSERVATION_SCHEMA")
    if not isinstance(value.get("process_count", 0), int) or value["process_count"] < 0:
        raise SecurityRefusal("OBSERVATION_SCHEMA")
    if "output_hash" in value and (not isinstance(value["output_hash"], str) or not _HEX.fullmatch(value["output_hash"])):
        raise SecurityRefusal("OBSERVATION_SCHEMA")
    _reject_sensitive(value)
    return value


def bundle_lint(path: str | Path) -> dict[str, Any]:
    """Independent byte scan for forbidden persistence classes, returning a hash only."""
    candidate = Path(path)
    raw = candidate.read_bytes()
    lowered = raw.lower()
    forbidden = (b"sk-", b"bearer ", b"private key", b"authorization:")
    if any(token in lowered for token in forbidden):
        raise SecurityRefusal("FORBIDDEN_CONTENT")
    return {"path": candidate.name, "sha256": digest(raw), "bytes": len(raw)}
