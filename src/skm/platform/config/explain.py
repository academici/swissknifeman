"""Authorized config diagnostics (§B.8). SecretRef metadata is data; secrets are never resolved here.

Pass a FrozenConfig directly for historical inspection, even with an unavailable descriptor. This path
never constructs executable configuration, merges saved data, or fills absence from current defaults.
"""

import json
from collections.abc import Iterable, Mapping
from typing import cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.outcomes import Diagnostic

from .effective import FROZEN_SCHEMA, EffectiveConfig, FrozenConfig, registry_descriptor_digest
from .effective import safe_value as _safe
from .keys import CHAIN_LEVELS, MISSING, STORED_LEVELS, Chain, Level, copy_json
from .layers import LayerRef
from .registry import SettingsRegistry

__all__ = ["build_explain", "render_explain_text"]


def _diagnostic(diagnostic: Diagnostic) -> JsonObject:
    result: JsonObject = {
        "code": diagnostic.code,
        "severity": diagnostic.severity.value,
        "message": diagnostic.message,
    }
    if diagnostic.target is not None:
        result["key"] = diagnostic.target
    layer = diagnostic.details.get("layer")
    if isinstance(layer, dict):
        result["layer"] = copy_json(layer, "layer")
    return result


def _chain(effective: EffectiveConfig) -> list[JsonValue]:
    """All scopes, plus pack/invocation sources found in the traces, without entry-specific metadata."""
    refs = [LayerRef(Level.DEFAULT)]
    for key in effective.resolved_keys():
        for item in effective.resolution(key).trace:
            layer = item.contribution.layer
            if layer.level in (Level.PACK, Level.INVOCATION) and layer not in refs:
                refs.append(layer)
    refs.extend(LayerRef(s.level, s.scope_id, s.label) for s in effective.chain.scopes)
    order = CHAIN_LEVELS[effective.chain.kind]
    refs.sort(
        key=lambda r: (
            order.index(r.level),
            r.pack_priority or 0,
            r.pack_id or "",
            0 if r.source == "env" else 2 if r.source == "cli" else 1,
        )
    )
    return [ref.to_json() for ref in refs]


def build_explain(
    effective: EffectiveConfig | FrozenConfig,
    *,
    keys: Iterable[str] | None = None,
    include_defaults_only: bool = True,
    registry: SettingsRegistry | None = None,
) -> JsonObject:
    """JSON ``urn:skm:config:explain:v1``. Frozen input is diagnostic data, never an execution grant.

    ``registry`` optionally supplies the original interpretation for historical data. A different or
    unavailable descriptor leaves metadata explicitly unknown and does not apply its defaults.
    """
    if isinstance(effective, FrozenConfig):
        return _historical(effective, keys, registry)
    selected = effective.resolved_keys() if keys is None else tuple(dict.fromkeys(keys))
    reports: list[JsonValue] = []
    for key in selected:
        resolution = effective.resolution(key)  # enforce unknown/foreign-chain errors
        spec = effective.registry.spec(key)
        if not include_defaults_only and all(
            t.contribution.layer.level is Level.DEFAULT for t in resolution.trace
        ):
            continue
        schema = spec.value_schema
        entry: JsonObject = {
            "key": key,
            "present": resolution.present,
            "merge": spec.merge.value,
            "reload": spec.reload.value,
            "sensitivity": spec.sensitivity.value,
        }
        if resolution.value is not MISSING:
            entry["value"] = _safe(cast("JsonValue", resolution.value), schema)
        redacted = resolution.present and entry.get("value") != resolution.value
        provenance = effective.provenance(key).to_json()
        for name in ("winner", "base", "locked_by"):
            if provenance[name] is not None:
                entry[name] = provenance[name]
        contributions = cast("list[JsonObject]", provenance["contributions"])
        ceilings = [
            violation
            for diagnostic in resolution.diagnostics
            for violation in cast("list[JsonObject]", diagnostic.details.get("violations", []))
        ]
        for contribution, trace in zip(contributions, resolution.trace, strict=True):
            if trace.contribution.layer.level in STORED_LEVELS:
                contribution["locked"] = trace.contribution.locked
            if "value" in contribution:
                original = contribution["value"]
                contribution["value"] = _safe(original, schema)
                redacted = redacted or contribution["value"] != original
            if trace.reason == "narrowing_violation":
                _add_ceiling(contribution, ceilings, schema)
        entry["contributions"] = cast("list[JsonValue]", contributions)
        entry["diagnostics"] = [_diagnostic(d) for d in effective.diagnostics if d.target == key]
        if redacted:
            for diagnostic in cast("list[JsonObject]", entry["diagnostics"]):
                diagnostic["message"] = "configuration contribution is invalid (secret value redacted)"
        if key in effective.invalid_keys():
            entry["valid"] = False
        reports.append(entry)
    target = effective.chain.target
    scope: JsonObject = {"level": target.level.value, "scope_id": str(target.scope_id)}
    if target.label:
        scope["label"] = target.label
    return {
        "schema": "urn:skm:config:explain:v1",
        "scope": scope,
        "chain_kind": effective.chain.kind.value,
        "chain": _chain(effective),
        "generation": effective.generation,
        "pack_generation": effective.pack_generation,
        "digest": effective.digest,
        "keys": reports,
        "diagnostics": [
            _diagnostic(d) for d in effective.diagnostics if d.target not in effective.resolved_keys()
        ],
    }


def _add_ceiling(
    contribution: JsonObject, ceilings: list[JsonObject], schema: Mapping[str, JsonValue]
) -> None:
    # Violations and ignored traces have the same order. Layer/value identity alone is insufficient:
    # repeated --set operations can carry identical refs and values with a changed ceiling between them.
    if ceilings:
        violation = ceilings.pop(0)
        contribution["ceiling"] = _safe(violation.get("ceiling"), schema)
        if violation.get("ceiling_from") is not None:
            contribution["ceiling_from"] = violation["ceiling_from"]


def _historical(
    frozen: FrozenConfig, keys: Iterable[str] | None, registry: SettingsRegistry | None
) -> JsonObject:
    known = registry is not None and frozen.registry_digest == registry_descriptor_digest(registry)
    selected = set(frozen.values) | set(frozen.provenance)
    if keys is not None:
        selected = set(keys)
    if known and keys is None:
        selected.update(
            spec.key
            for spec in cast("SettingsRegistry", registry).keys(chain=Chain.WORK)
            if spec.reload.value == "run_frozen"
        )
    entries: list[JsonValue] = []
    # A frozen document is not authenticated: even a key name can contain a secret.
    # Only names present in the matching trusted descriptor may be emitted.
    for key in sorted(selected) if known else ():
        spec = registry.find(key) if registry is not None else None
        if spec is None:
            continue
        entry: JsonObject = {
            "key": key,
            "present": key in frozen.values,
            "merge": spec.merge.value if spec else None,
            "reload": spec.reload.value if spec else None,
            "sensitivity": spec.sensitivity.value if spec else None,
            "interpretation": "known" if spec else "unknown",
            "contributions": [],
            "diagnostics": [],
        }
        # Unauthenticated snapshots cannot prove that even a public field is safe to disclose.
        entries.append(entry)
    return {
        "schema": "urn:skm:config:explain:v1",
        "scope": {"level": "run", "scope_id": str(frozen.run_scope_id)},
        "chain_kind": "work",
        "chain": [{"level": "run_bundle"}],
        "generation": frozen.generation,
        "pack_generation": frozen.pack_generation,
        "digest": frozen.digest,
        "keys": entries,
        "diagnostics": [],
        "snapshot_schema": FROZEN_SCHEMA,
        "registry_digest": frozen.registry_digest,
        "interpretation": "known" if known else "unknown",
    }


def _label(layer: Mapping[str, JsonValue]) -> str:
    label = layer.get("label")
    if isinstance(label, str) and label:
        return label
    if layer.get("level") == "pack" and "pack_id" in layer:
        return f"pack {layer['pack_id']} (prio {layer.get('pack_priority', 0)})"
    return str(layer.get("source", layer["level"]))


def _short(value: str) -> str:
    return value[: 15 if value.startswith("sha256:") else 8] + "…" + value[-4:]


def _json(value: JsonValue, limit: int | None = None) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if limit is None or len(text) <= limit else text[: limit - 1] + "…"


def render_explain_text(report: Mapping[str, JsonValue]) -> str:
    """Deterministic text using the layout and reason wording of settings §B.8.2."""
    scope = cast("JsonObject", report["scope"])
    chain = cast("list[JsonObject]", report["chain"])
    chain_labels = [str(r.get("label", r["level"])) for r in chain]
    lines = [
        f"scope   {_label(scope)}  (chain: {' > '.join(chain_labels)})",
        f"config  generation {report['generation']}, packs {report['pack_generation']}, "
        f"digest {_short(str(report['digest']))}",
    ]
    if "snapshot_schema" in report:
        lines.append(
            f"snapshot {report['snapshot_schema']}, registry {report['registry_digest']}, "
            f"interpretation {report['interpretation']}"
        )
    for entry in cast("list[JsonObject]", report["keys"]):
        locked = cast("JsonObject", entry.get("locked_by", {}))
        value = (
            "<redacted>"
            if "value" not in entry and entry["present"]
            else _json(entry.get("value"))
            if entry["present"]
            else "<absent>"
        )
        metadata = f"{entry['merge']} · {entry['reload']}"
        if entry.get("interpretation") == "unknown":
            metadata = "unknown interpretation"
        if locked:
            metadata += f" · locked at {_label(locked)}"
        lines.extend(["", f"{entry['key']} = {value}".ljust(54) + "  " + metadata])
        lines.extend(
            _contribution_text(entry, item, locked)
            for item in cast("list[JsonObject]", entry["contributions"])
        )
        if "provenance" in entry:
            lines.append(f"  provenance {entry['provenance']}")
        for diagnostic in cast("list[JsonObject]", entry.get("diagnostics", [])):
            message = str(diagnostic["message"]).removesuffix(": the key is locked there")
            lines.append(f"  ! {diagnostic['code']}  {message}")
    lines.extend(
        f"! {d['code']}  {d['message']}" for d in cast("list[JsonObject]", report.get("diagnostics", []))
    )
    return "\n".join(lines) + "\n"


def _contribution_text(entry: JsonObject, item: JsonObject, locked: JsonObject) -> str:
    layer = cast("JsonObject", item["layer"])
    label = _label(layer)
    if item.get("locked"):
        label += "   [locked]"
    value = "<unset>" if item["op"] == "unset" else _json(item.get("value"), 40)
    status = "← winner" if item["status"] == "winner" else str(item["status"])
    reason = item.get("reason")
    if isinstance(reason, str):
        reasons = {
            "locked_above": f"locked above ({_label(locked)})" if locked else "locked above",
            "scope_not_allowed": "level not allowed",
            "narrowing_violation": "would widen the ceiling",
            "override_not_allowed": "override not allowed",
            "op_not_allowed": "operation not allowed",
            "pack_not_allowed": "packs may not set this key",
        }
        if reason == "narrowing_violation" and "ceiling" in item:
            source = cast("JsonObject", item.get("ceiling_from", {"level": "default"}))
            reasons[reason] = f"would widen {_json(item['ceiling'], 40)} from {_label(source)}"
        status += f": {reasons[reason]}"
    text = f"  {label:<32} {value:<21} {status}"
    base = entry.get("base")
    if base is None and entry.get("merge") == "narrow":
        base = next(
            (
                c["layer"]
                for c in cast("list[JsonObject]", entry["contributions"])
                if c["status"] in ("used", "winner")
                and cast("JsonObject", c["layer"])["level"] not in ("default", "pack")
            ),
            None,
        )
    if (
        entry.get("merge") == "narrow"
        and item["status"] == "used"
        and base == layer
        and layer["level"] not in ("default", "pack")
    ):
        text = text.ljust(68) + " (starts the narrowing chain; default and pack are base values)"
    if item["status"] == "winner" and "entry_id" in layer:
        text = text.ljust(68) + f" entry {_short(str(layer['entry_id']))} v{layer['row_version']}"
    return text
