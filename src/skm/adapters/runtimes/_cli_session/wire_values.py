"""Bounded extraction of identifiers, versions and HTTP status from untrusted CLI wire events."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, cast

__all__: list[str] = []

_MODEL_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}")
_VERSION_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+()-]{0,99}")
_HTTP_STATUS_RE: Final = re.compile(r"\b(400|401|403|404|408|409|413|422|429|500|502|503|504|529)\b")


def identity_redact(text: str) -> str:
    return text


def bounded_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not 1 <= len(cleaned) <= 200:
        return None
    return cleaned


def bounded_model(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.startswith("secret://") or _MODEL_RE.fullmatch(cleaned) is None:
        return None
    return cleaned


def bounded_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or _VERSION_RE.fullmatch(cleaned) is None:
        return None
    return cleaned


def nonneg_opt(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def extract_http_status(data: Mapping[str, object], text: str | None = None) -> int | None:
    for key in ("http_status", "error_status", "status_code", "status"):
        raw = data.get(key)
        if not isinstance(raw, bool) and isinstance(raw, int) and 100 <= raw <= 599:
            return raw
    err = data.get("error")
    if isinstance(err, Mapping):
        err_map = cast("Mapping[str, object]", err)
        for key in ("http_status", "status_code", "status"):
            raw = err_map.get(key)
            if not isinstance(raw, bool) and isinstance(raw, int) and 100 <= raw <= 599:
                return raw
    if text:
        match = _HTTP_STATUS_RE.search(text)
        if match is not None:
            return int(match.group(1))
    return None
