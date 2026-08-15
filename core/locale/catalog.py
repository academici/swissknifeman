"""Key-addressed English catalogs and sparse overlays."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping


@dataclass(frozen=True)
class Catalog:
    locale: str
    units: Mapping[str, str]


@dataclass(frozen=True)
class Overlay:
    locale: str
    source_catalog_sha256: str
    units: Mapping[str, Mapping[str, object]]


def resolve_catalog(english: Catalog, overlay: Overlay | None, key: str, *, immutable_tokens: tuple[str, ...] = ()):
    if key not in english.units: raise ValueError("OVERLAY_FALLBACK_MISSING")
    text, fallback, digest = english.units[key], True, None
    expected = "sha256:" + sha256(json.dumps(dict(sorted(english.units.items())), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if overlay is not None:
        if overlay.locale != "ru" or overlay.source_catalog_sha256 != expected: raise ValueError("OVERLAY_SOURCE_DIGEST_MISMATCH")
        unit = overlay.units.get(key)
        if unit is not None:
            candidate = unit.get("text") if isinstance(unit, Mapping) else None
            if not isinstance(candidate, str) or not candidate: raise ValueError("OVERLAY_SCHEMA_INVALID")
            if any(candidate.count(token) != text.count(token) for token in immutable_tokens): raise ValueError("OVERLAY_IMMUTABLE_TOKEN_MISMATCH")
            text, fallback = candidate, False
            digest = "sha256:" + sha256(candidate.encode()).hexdigest()
    return {"key": key, "source_sha256": "sha256:" + sha256(english.units[key].encode()).hexdigest(),
            "resolved_locale": "en" if fallback else "ru", "text": text, "fallback": fallback,
            "overlay_sha256": digest}
