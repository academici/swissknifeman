"""Validated root-owned provider capability manifest.

The parser is pure over caller-supplied bytes or a mapping.  Filesystem access is
deliberately limited to :func:`load_provider_manifest`, which reads only the exact
path supplied by its caller and performs no repository, home, or fleet discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .values import (CapabilityId, NativeExtensionId, ProviderId,
                     SupportLevel)
from .config import (CapabilitySupport, NativeExtension,
                     ProviderConfigCatalog)


_CONTRACT_MAJOR = 1
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DISPLAY_NAMES = {ProviderId.CLAUDE_CODE: "Claude Code", ProviderId.CODEX: "Codex",
                  ProviderId.CURSOR: "Cursor", ProviderId.GROK: "Grok"}
_ENVELOPE_KEYS = frozenset({"contract_version", "catalog_version", "providers",
                            "capabilities", "native_extensions"})
_PROVIDER_KEYS = frozenset({"id", "display_name"})
_CAPABILITY_KEYS = frozenset({"id", "intent", "support"})
_SUPPORT_KEYS = frozenset({"level", "binding", "adapter_id", "limitations",
                           "evidence", "diagnostic"})
_EVIDENCE_KEYS = frozenset({"source", "verified_at", "scope", "claim"})
_EXTENSION_KEYS = frozenset({"id", "provider_id", "intent", "binding", "evidence",
                             "diagnostic"})
_COLLAPSED_SECURITY_KEYS = frozenset({"permission_mode", "permission-mode", "autonomy"})


@dataclass(frozen=True, order=True)
class ProviderManifestDiagnostic:
    code: str
    path: str
    message: str


class ProviderManifestError(ValueError):
    """One deterministic aggregate of all manifest validation diagnostics."""

    def __init__(self, diagnostics: tuple[ProviderManifestDiagnostic, ...]):
        self.diagnostics = tuple(sorted(diagnostics, key=lambda row: (row.path, row.code,
                                                                       row.message)))
        super().__init__("; ".join(f"{row.code}:{row.path}:{row.message}"
                                   for row in self.diagnostics))


@dataclass(frozen=True, order=True)
class ManifestEvidence:
    source: str
    verified_at: str
    scope: str
    claim: str


@dataclass(frozen=True)
class ManifestSupport:
    provider_id: ProviderId
    level: SupportLevel
    binding: tuple[tuple[str, object], ...] | None
    adapter_id: str | None
    limitations: tuple[str, ...]
    evidence: tuple[ManifestEvidence, ...]
    diagnostic: str


@dataclass(frozen=True)
class ManifestCapability:
    capability_id: CapabilityId
    intent: str
    support: tuple[ManifestSupport, ...]


@dataclass(frozen=True)
class ManifestNativeExtension:
    extension_id: NativeExtensionId
    provider_id: ProviderId
    intent: str
    binding: tuple[tuple[str, object], ...]
    evidence: tuple[ManifestEvidence, ...]
    diagnostic: str


@dataclass(frozen=True)
class ProviderCapabilityManifest:
    contract_version: str
    catalog_version: str
    providers: tuple[ProviderId, ...]
    capabilities: tuple[ManifestCapability, ...]
    native_extensions: tuple[ManifestNativeExtension, ...]


class _DuplicateKey(ValueError):
    pass


class _JsonArray(tuple):
    """Internal immutable tag that preserves JSON array identity."""


def _object_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(str(key))
        value[key] = item
    return value


def parse_provider_manifest(value: bytes | Mapping[str, object], *,
                            source_id: str = "memory") -> ProviderCapabilityManifest:
    """Parse and validate exactly one v1 manifest without performing I/O."""
    diagnostics: list[ProviderManifestDiagnostic] = []
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a non-empty string")
    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8")
            raw = json.loads(decoded, object_pairs_hook=_object_pairs)
        except UnicodeDecodeError as error:
            raise ProviderManifestError((_diag("MANIFEST_SCHEMA_INVALID", "/",
                                                  f"{source_id}: invalid UTF-8: {error}"),)) from error
        except _DuplicateKey as error:
            raise ProviderManifestError((_diag("MANIFEST_SCHEMA_INVALID", "/",
                                                  f"{source_id}: duplicate object key {error}"),)) from error
        except json.JSONDecodeError as error:
            raise ProviderManifestError((_diag("MANIFEST_SCHEMA_INVALID", "/",
                                                  f"{source_id}: invalid JSON: {error.msg}"),)) from error
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise TypeError("value must be bytes or Mapping")

    if not isinstance(raw, dict):
        raise ProviderManifestError((_diag("MANIFEST_SCHEMA_INVALID", "/",
                                              "manifest envelope must be an object"),))
    _exact_keys(raw, _ENVELOPE_KEYS, "/", diagnostics)
    contract_version = raw.get("contract_version")
    contract_match = (_SEMVER_RE.fullmatch(contract_version)
                      if isinstance(contract_version, str) else None)
    if contract_match is None or int(contract_match.group(1)) != _CONTRACT_MAJOR:
        diagnostics.append(_diag("MANIFEST_VERSION_UNSUPPORTED", "/contract_version",
                                 "contract version must be SemVer with supported major 1"))
    catalog_version = raw.get("catalog_version")
    if not isinstance(catalog_version, str) or not _SEMVER_RE.fullmatch(catalog_version):
        diagnostics.append(_diag("MANIFEST_VERSION_UNSUPPORTED", "/catalog_version",
                                 "catalog version must be SemVer"))

    providers, provider_values = _providers(raw.get("providers"), diagnostics)
    capabilities = _capabilities(raw.get("capabilities"), providers, diagnostics)
    extensions = _extensions(raw.get("native_extensions"), providers, diagnostics)
    _security_axes(raw, diagnostics)
    if diagnostics:
        raise ProviderManifestError(tuple(diagnostics))
    # Provider display metadata is validated before it is deliberately omitted from the
    # semantic model.  Canonical serialization restores the stable v1 display names.
    del provider_values
    return ProviderCapabilityManifest(
        contract_version, catalog_version, tuple(sorted(providers, key=lambda item: item.value)),
        tuple(sorted(capabilities, key=lambda item: item.capability_id.value)),
        tuple(sorted(extensions, key=lambda item: item.extension_id.value)))


def load_provider_manifest(path: Path) -> ProviderCapabilityManifest:
    """Read only ``path`` and validate its bytes; there is no lookup or fallback."""
    path = Path(path)
    try:
        value = path.read_bytes()
    except OSError as error:
        raise ProviderManifestError((_diag("MANIFEST_SCHEMA_INVALID", "/",
                                              f"{path}: {error.strerror or error}"),)) from error
    return parse_provider_manifest(value, source_id=str(path))


def provider_config_catalog(manifest: ProviderCapabilityManifest) -> ProviderConfigCatalog:
    """Project the rich manifest into the unchanged frozen P1 catalog."""
    _require_manifest(manifest)
    support = tuple(CapabilitySupport(capability.capability_id, row.provider_id, row.level)
                    for capability in manifest.capabilities for row in capability.support)
    extensions = tuple(NativeExtension(row.extension_id, row.provider_id)
                       for row in manifest.native_extensions)
    return ProviderConfigCatalog(manifest.catalog_version, manifest.providers, support, extensions)


def provider_support_projection(manifest: ProviderCapabilityManifest,
                                provider_id: ProviderId) -> Mapping[str, SupportLevel]:
    """Return a detached read-only capability-to-level projection for one provider."""
    _require_manifest(manifest)
    if not isinstance(provider_id, ProviderId):
        raise TypeError("provider_id must be ProviderId")
    if provider_id not in manifest.providers:
        raise ValueError("provider is not present in manifest")
    projection = {capability.capability_id.value:
                  next(row.level for row in capability.support
                       if row.provider_id is provider_id)
                  for capability in manifest.capabilities}
    return MappingProxyType(projection)


def provider_manifest_canonical_bytes(manifest: ProviderCapabilityManifest) -> bytes:
    """Serialize semantic v1 data canonically, without a carrier newline."""
    _require_manifest(manifest)
    return json.dumps(_manifest_mapping(manifest), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def provider_manifest_sha256(manifest: ProviderCapabilityManifest) -> str:
    """Return the lowercase hex digest of canonical bytes (carrier LF excluded)."""
    return hashlib.sha256(provider_manifest_canonical_bytes(manifest)).hexdigest()


def support_for(manifest: ProviderCapabilityManifest, capability_id: str,
                provider_id: ProviderId) -> ManifestSupport:
    """Resolve one exact support record or fail closed."""
    _require_manifest(manifest)
    for capability in manifest.capabilities:
        if capability.capability_id.value == capability_id:
            for support in capability.support:
                if support.provider_id is provider_id:
                    return support
    raise ValueError(f"MANIFEST_CAPABILITY_INVALID:{provider_id.value}:{capability_id}")


def _providers(value, diagnostics):
    providers, records = [], []
    if not isinstance(value, list) or not value:
        diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", "/providers",
                                 "providers must be a non-empty list"))
        return providers, records
    seen = set()
    for index, record in enumerate(value):
        path = f"/providers/{index}"
        if not isinstance(record, dict):
            diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", path,
                                     "provider must be an object")); continue
        _exact_keys(record, _PROVIDER_KEYS, path, diagnostics,
                    required=frozenset({"id"}))
        provider_text = record.get("id")
        try:
            provider = ProviderId(provider_text)
        except (TypeError, ValueError):
            diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", f"{path}/id",
                                     "unknown provider ID")); continue
        if provider in seen:
            diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", f"{path}/id",
                                     "duplicate provider ID")); continue
        seen.add(provider)
        display_name = record.get("display_name")
        if "display_name" in record and (not isinstance(display_name, str) or not display_name):
            diagnostics.append(_diag("MANIFEST_SCHEMA_INVALID", f"{path}/display_name",
                                     "display_name must be non-empty"))
        elif "display_name" in record and display_name != _DISPLAY_NAMES[provider]:
            diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", f"{path}/display_name",
                                     "display_name does not match the canonical provider name"))
        providers.append(provider); records.append(record)
    required = set(ProviderId)
    if set(providers) != required:
        diagnostics.append(_diag("MANIFEST_PROVIDER_INVALID", "/providers",
                                 "v1 requires exactly one row per ProviderId"))
    return providers, records


def _capabilities(value, providers, diagnostics):
    capabilities = []
    if not isinstance(value, list) or not value:
        diagnostics.append(_diag("MANIFEST_CAPABILITY_INVALID", "/capabilities",
                                 "capabilities must be a non-empty list"))
        return capabilities
    seen = set()
    for index, record in enumerate(value):
        path = f"/capabilities/{index}"
        if not isinstance(record, dict):
            diagnostics.append(_diag("MANIFEST_CAPABILITY_INVALID", path,
                                     "capability must be an object")); continue
        _exact_keys(record, _CAPABILITY_KEYS, path, diagnostics)
        capability_text = record.get("id")
        if not isinstance(capability_text, str) or not _IDENTIFIER_RE.fullmatch(capability_text):
            diagnostics.append(_diag("MANIFEST_CAPABILITY_INVALID", f"{path}/id",
                                     "invalid capability ID")); continue
        if capability_text in seen:
            diagnostics.append(_diag("MANIFEST_CAPABILITY_INVALID", f"{path}/id",
                                     "duplicate capability ID")); continue
        seen.add(capability_text)
        intent = record.get("intent")
        if not isinstance(intent, str) or not intent:
            diagnostics.append(_diag("MANIFEST_CAPABILITY_INVALID", f"{path}/intent",
                                     "intent must be non-empty"))
        support = _support_matrix(record.get("support"), providers, path, diagnostics)
        try:
            capability_id = CapabilityId(capability_text)
        except ValueError:
            continue
        capabilities.append(ManifestCapability(capability_id, intent if isinstance(intent, str) else "",
                                               support))
    return capabilities


def _support_matrix(value, providers, capability_path, diagnostics):
    path = f"{capability_path}/support"
    if not isinstance(value, dict):
        diagnostics.append(_diag("MANIFEST_SUPPORT_MATRIX_INVALID", path,
                                 "support must be an object")); return ()
    expected = {provider.value for provider in providers}
    actual = set(value)
    for provider_text in sorted(expected - actual):
        diagnostics.append(_diag("MANIFEST_SUPPORT_MATRIX_INVALID", f"{path}/{provider_text}",
                                 "missing provider support record"))
    for provider_text in sorted(actual - expected):
        diagnostics.append(_diag("MANIFEST_SUPPORT_MATRIX_INVALID", f"{path}/{provider_text}",
                                 "unknown provider support record"))
    rows = []
    for provider in sorted(providers, key=lambda item: item.value):
        if provider.value not in value:
            continue
        row = _support(value[provider.value], provider, f"{path}/{provider.value}", diagnostics)
        if row is not None:
            rows.append(row)
    return tuple(rows)


def _support(value, provider, path, diagnostics):
    if not isinstance(value, dict):
        diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", path,
                                 "support record must be an object")); return None
    required = {"level", "limitations", "evidence", "diagnostic"}
    allowed = set(required) | {"binding", "adapter_id"}
    _exact_keys(value, frozenset(allowed), path, diagnostics, required=frozenset(required))
    level_text = value.get("level")
    try:
        level = SupportLevel(level_text)
    except (TypeError, ValueError):
        diagnostics.append(_diag("MANIFEST_SUPPORT_LEVEL_INVALID", f"{path}/level",
                                 "unknown support level")); return None
    limitations_value = value.get("limitations")
    if (not isinstance(limitations_value, list)
            or not all(isinstance(item, str) and item for item in limitations_value)):
        diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", f"{path}/limitations",
                                 "limitations must be a list of non-empty strings"))
        limitations = ()
    else:
        limitations = tuple(limitations_value)
    if len(set(limitations)) != len(limitations):
        diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", f"{path}/limitations",
                                 "limitations must not repeat"))
    evidence = _evidence(value.get("evidence"), f"{path}/evidence", diagnostics)
    diagnostic = value.get("diagnostic")
    if not isinstance(diagnostic, str) or not diagnostic:
        diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", f"{path}/diagnostic",
                                 "diagnostic must be non-empty")); diagnostic = ""
    binding_value = value.get("binding")
    binding = _binding(binding_value, f"{path}/binding", diagnostics) if "binding" in value else None
    adapter_id = value.get("adapter_id")
    if "adapter_id" in value and (not isinstance(adapter_id, str)
                                   or not _IDENTIFIER_RE.fullmatch(adapter_id)):
        diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", f"{path}/adapter_id",
                                 "adapter_id must be a stable identifier"))
        adapter_id = None
    if level is SupportLevel.NATIVE:
        if binding is None or "adapter_id" in value or not evidence:
            diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", path,
                                     "native requires binding/evidence and forbids adapter_id"))
    elif level is SupportLevel.ADAPTED:
        if adapter_id is None or not limitations or not evidence:
            diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", path,
                                     "adapted requires adapter_id, limitations and evidence"))
    else:
        fail_closed = isinstance(diagnostic, str) and any(
            token in diagnostic.lower() for token in ("unsupported", "fail closed", "fail-closed",
                                                       "refus", "exclude", "disabled"))
        if "binding" in value or "adapter_id" in value or not evidence or not fail_closed:
            diagnostics.append(_diag("MANIFEST_SUPPORT_INVARIANT", path,
                                     "unsupported forbids binding/adapter and requires fail-closed diagnostic/evidence"))
    return ManifestSupport(provider, level, binding, adapter_id, limitations, evidence, diagnostic)


def _evidence(value, path, diagnostics):
    if not isinstance(value, list) or not value:
        diagnostics.append(_diag("MANIFEST_EVIDENCE_INVALID", path,
                                 "evidence must be a non-empty list")); return ()
    evidence = []
    for index, record in enumerate(value):
        item_path = f"{path}/{index}"
        if not isinstance(record, dict):
            diagnostics.append(_diag("MANIFEST_EVIDENCE_INVALID", item_path,
                                     "evidence record must be an object")); continue
        _exact_keys(record, _EVIDENCE_KEYS, item_path, diagnostics,
                    code="MANIFEST_EVIDENCE_INVALID")
        fields = []
        for key in ("source", "verified_at", "scope", "claim"):
            item = record.get(key)
            if not isinstance(item, str) or not item:
                diagnostics.append(_diag("MANIFEST_EVIDENCE_INVALID", f"{item_path}/{key}",
                                         f"{key} must be non-empty")); item = ""
            fields.append(item)
        if fields[1] and not _DATE_RE.fullmatch(fields[1]):
            diagnostics.append(_diag("MANIFEST_EVIDENCE_INVALID", f"{item_path}/verified_at",
                                     "verified_at must be YYYY-MM-DD"))
        evidence.append(ManifestEvidence(*fields))
    return tuple(evidence)


def _extensions(value, providers, diagnostics):
    if not isinstance(value, list):
        diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", "/native_extensions",
                                 "native_extensions must be a list")); return ()
    extensions, seen = [], set()
    for index, record in enumerate(value):
        path = f"/native_extensions/{index}"
        if not isinstance(record, dict):
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", path,
                                     "native extension must be an object")); continue
        _exact_keys(record, _EXTENSION_KEYS, path, diagnostics,
                    code="MANIFEST_EXTENSION_INVALID")
        extension_text, provider_text = record.get("id"), record.get("provider_id")
        try:
            provider = ProviderId(provider_text)
        except (TypeError, ValueError):
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/provider_id",
                                     "unknown extension provider")); continue
        if provider not in providers:
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/provider_id",
                                     "extension provider is absent from provider set"))
        if (not isinstance(extension_text, str) or extension_text in seen
                or not extension_text.startswith(provider.value + ".")):
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/id",
                                     "extension ID must be unique and provider-namespaced")); continue
        seen.add(extension_text)
        try:
            extension_id = NativeExtensionId(extension_text)
        except ValueError:
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/id",
                                     "invalid extension ID")); continue
        intent, diagnostic = record.get("intent"), record.get("diagnostic")
        if not isinstance(intent, str) or not intent:
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/intent",
                                     "intent must be non-empty")); intent = ""
        if not isinstance(diagnostic, str) or not diagnostic:
            diagnostics.append(_diag("MANIFEST_EXTENSION_INVALID", f"{path}/diagnostic",
                                     "diagnostic must be non-empty")); diagnostic = ""
        binding = _binding(record.get("binding"), f"{path}/binding", diagnostics,
                           code="MANIFEST_EXTENSION_INVALID")
        evidence = _evidence(record.get("evidence"), f"{path}/evidence", diagnostics)
        extensions.append(ManifestNativeExtension(extension_id, provider, intent,
                                                  binding or (), evidence, diagnostic))
    return tuple(extensions)


def _binding(value, path, diagnostics, code="MANIFEST_SUPPORT_INVARIANT"):
    if not isinstance(value, dict) or not value or not all(isinstance(key, str) and key for key in value):
        diagnostics.append(_diag(code, path, "binding must be a non-empty JSON object")); return None
    try:
        return tuple((key, _freeze_json(item)) for key, item in sorted(value.items()))
    except (TypeError, ValueError) as error:
        diagnostics.append(_diag(code, path, f"binding is not JSON-compatible: {error}")); return None


def _freeze_json(value):
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("object keys must be strings")
        return tuple((key, _freeze_json(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return _JsonArray(_freeze_json(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("float values must be finite")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(type(value).__name__)


def _thaw_json(value):
    if isinstance(value, _JsonArray):
        return [_thaw_json(item) for item in value]
    if isinstance(value, tuple):
        return {key: _thaw_json(item) for key, item in value}
    return value


def _manifest_mapping(manifest):
    capabilities = []
    for capability in manifest.capabilities:
        support = {}
        for row in capability.support:
            value = {"level": row.level.value, "limitations": list(row.limitations),
                     "evidence": [{"source": item.source, "verified_at": item.verified_at,
                                   "scope": item.scope, "claim": item.claim}
                                  for item in row.evidence],
                     "diagnostic": row.diagnostic}
            if row.binding is not None:
                value["binding"] = _thaw_json(row.binding)
            if row.adapter_id is not None:
                value["adapter_id"] = row.adapter_id
            support[row.provider_id.value] = value
        capabilities.append({"id": capability.capability_id.value, "intent": capability.intent,
                             "support": support})
    extensions = [{"id": item.extension_id.value, "provider_id": item.provider_id.value,
                   "intent": item.intent, "binding": _thaw_json(item.binding),
                   "evidence": [{"source": row.source, "verified_at": row.verified_at,
                                 "scope": row.scope, "claim": row.claim}
                                for row in item.evidence],
                   "diagnostic": item.diagnostic}
                  for item in manifest.native_extensions]
    return {"contract_version": manifest.contract_version,
            "catalog_version": manifest.catalog_version,
            "providers": [{"id": provider.value, "display_name": _DISPLAY_NAMES[provider]}
                          for provider in manifest.providers],
            "capabilities": capabilities, "native_extensions": extensions}


def _security_axes(value, diagnostics):
    def walk(item, path):
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{path}/{key}" if path != "/" else f"/{key}"
                if isinstance(key, str) and key.lower() in _COLLAPSED_SECURITY_KEYS:
                    diagnostics.append(_diag("MANIFEST_SECURITY_AXES_COLLAPSED", child_path,
                                             "trust, approval and sandbox must remain independent"))
                walk(child, child_path)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{path}/{index}")
    walk(value, "/")


def _exact_keys(value, expected, path, diagnostics, *, required=None,
                code="MANIFEST_SCHEMA_INVALID"):
    required = expected if required is None else required
    for key in sorted(set(value) - set(expected)):
        diagnostics.append(_diag(code, f"{path.rstrip('/')}/{key}", "unknown field"))
    for key in sorted(set(required) - set(value)):
        diagnostics.append(_diag(code, f"{path.rstrip('/')}/{key}", "missing required field"))


def _diag(code, path, message):
    return ProviderManifestDiagnostic(code, path or "/", message)


def _require_manifest(value):
    if not isinstance(value, ProviderCapabilityManifest):
        raise TypeError("manifest must be ProviderCapabilityManifest")
