"""No-I/O locale resolver; its registry path is an explicit immutable input."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Mapping

from .values import LocaleDiagnostic, LocaleResult, SURFACES, SurfaceLocale

CONTRACT_VERSION = "1.0.0"
REGISTRY_SHA256 = "be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a"
REGISTRY_FILE_DATE = "2026-06-14"
_KINDS = {1: "command-session", 2: "environment", 3: "project", 4: "user", 5: "built-in"}
_TAG = re.compile(r"^[A-Za-z0-9-]+$")


def resolve_locale(layers: tuple[Mapping[str, object], ...] | list[Mapping[str, object]], *, registry_path: Path) -> LocaleResult:
    """Resolve already-read layers independently for all three public surfaces."""
    error = _validate_registry(Path(registry_path))
    if error:
        return _failure(error)
    parsed, diagnostics = _layers(layers)
    if diagnostics:
        return _failure(diagnostics[0])
    registry = _registry(Path(registry_path))
    rows = []
    for surface in SURFACES:
        winner = next((layer for layer in sorted(parsed, key=lambda value: value["rank"])
                       if surface in layer["locale"]), None)
        assert winner is not None
        requested = winner["locale"][surface]
        canonical, code = _canonicalize(requested, registry)
        if code:
            return _failure(code, surface)
        resolved, fallback, code = _catalog(canonical)
        rows.append(SurfaceLocale(surface, winner["rank"], winner["kind"], requested,
                                  canonical, resolved, fallback, code))
    diagnostics = tuple(LocaleDiagnostic("info", row.diagnostic, row.surface, row.diagnostic)
                        for row in rows if row.diagnostic)
    return LocaleResult(CONTRACT_VERSION, tuple(rows), diagnostics)


def _failure(code: str, surface: str = "response") -> LocaleResult:
    return LocaleResult(CONTRACT_VERSION, None, (LocaleDiagnostic("error", code, surface, code),))


def _validate_registry(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return "LOCALE_REGISTRY_IDENTITY_MISMATCH"
    if sha256(data).hexdigest() != REGISTRY_SHA256 or len(data) != 731605:
        return "LOCALE_REGISTRY_IDENTITY_MISMATCH"
    if not data.startswith(f"File-Date: {REGISTRY_FILE_DATE}\n".encode()):
        return "LOCALE_REGISTRY_IDENTITY_MISMATCH"
    return None


def _layers(raw):
    if not isinstance(raw, (tuple, list)):
        return (), ("LOCALE_SCHEMA_INVALID",)
    seen, values = set(), []
    for layer in raw:
        if not isinstance(layer, Mapping): return (), ("LOCALE_SCHEMA_INVALID",)
        if set(layer) - {"contract_version", "rank", "kind", "locale"}:
            return (), ("LOCALE_PERSISTENCE_FORBIDDEN" if "persist" in layer else "LOCALE_CROSS_SURFACE_LEAKAGE")
        if layer.get("contract_version") != CONTRACT_VERSION: return (), ("LOCALE_VERSION_UNSUPPORTED",)
        rank, kind, locale = layer.get("rank"), layer.get("kind"), layer.get("locale")
        if rank in seen: return (), ("LOCALE_DUPLICATE_RANK",)
        seen.add(rank)
        if kind == "provider-adapter-status": return (), ("LOCALE_ADAPTER_INPUT_FORBIDDEN",)
        if rank not in _KINDS or kind != _KINDS[rank]: return (), ("LOCALE_CARRIER_MISMATCH",)
        if not isinstance(locale, Mapping) or not locale: return (), ("LOCALE_SCHEMA_INVALID",)
        if set(locale) - set(SURFACES): return (), ("LOCALE_UNSUPPORTED_SURFACE",)
        if any(not isinstance(value, str) or not value for value in locale.values()): return (), ("LOCALE_SCHEMA_INVALID",)
        values.append({"rank": rank, "kind": kind, "locale": dict(locale)})
    if 5 not in seen: return (), ("LOCALE_SCHEMA_INVALID",)
    return tuple(values), ()


def _registry(path: Path):
    records, current = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines() + ["%%"]:
        if line == "%%":
            if current:
                kind, subtag = current.get("Type"), current.get("Subtag", current.get("Tag"))
                if kind and subtag: records[(kind, subtag.lower())] = current.get("Preferred-Value")
            current = {}
        elif ": " in line:
            key, value = line.split(": ", 1)
            current.setdefault(key, value)
    return records


def _canonicalize(tag: str, registry):
    if not _TAG.fullmatch(tag) or "--" in tag or tag.startswith("-") or tag.endswith("-"):
        return None, "LOCALE_MALFORMED"
    parts = tag.split("-")
    if parts[0].lower() == "x":
        if len(parts) < 2 or any(not 1 <= len(x) <= 8 for x in parts[1:]): return None, "LOCALE_MALFORMED"
        return "x-" + "-".join(x.lower() for x in parts[1:]), None
    if not 2 <= len(parts[0]) <= 8 or not parts[0].isalpha(): return None, "LOCALE_MALFORMED"
    if ("language", parts[0].lower()) not in registry: return None, "LOCALE_UNREGISTERED"
    result = [registry.get(("language", parts[0].lower())) or parts[0].lower()]
    private = False
    for index, part in enumerate(parts[1:], 1):
        lower = part.lower()
        if private:
            if not 1 <= len(part) <= 8: return None, "LOCALE_MALFORMED"
            result.append(lower); continue
        if lower == "x":
            if index == len(parts) - 1: return None, "LOCALE_MALFORMED"
            private = True; result.append("x"); continue
        if len(part) == 4 and part.isalpha():
            if ("script", lower) not in registry: return None, "LOCALE_UNREGISTERED"
            result.append((registry.get(("script", lower)) or lower).title())
        elif (len(part) == 2 and part.isalpha()) or (len(part) == 3 and part.isdigit()):
            if ("region", lower) not in registry: return None, "LOCALE_UNREGISTERED"
            result.append((registry.get(("region", lower)) or lower).upper())
        elif 4 <= len(part) <= 8 and part.isalnum():
            if ("variant", lower) not in registry: return None, "LOCALE_UNREGISTERED"
            result.append(registry.get(("variant", lower)) or lower)
        elif len(part) == 1 and part.isalnum():
            result.append(lower)
        elif 2 <= len(part) <= 8 and part.isalnum():
            result.append(lower)
        else:
            return None, "LOCALE_MALFORMED"
    return "-".join(result), None


def _catalog(canonical: str):
    if "-x-" in canonical or canonical.startswith("x-"):
        return None, False, "LOCALE_UNSUPPORTED_PRIVATE_USE"
    if canonical in {"en", "ru"}: return canonical, False, None
    if canonical.split("-", 1)[0] in {"en", "ru"}: return canonical.split("-", 1)[0], True, None
    return "en", True, "LOCALE_UNSUPPORTED_CATALOG"
