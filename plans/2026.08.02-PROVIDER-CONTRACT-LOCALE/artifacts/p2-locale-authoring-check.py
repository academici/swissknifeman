#!/usr/bin/env python3
"""Deterministic P2 locale-resolution contract and fixture checker."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


EXPECTED_URL = "https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry"
EXPECTED_RETRIEVAL_URL = (
    "https://raw.githubusercontent.com/jcari-dev/pyworldatlas/"
    "9c61d166a353390977a21155796b4092bb796e50/"
    "build_data/raw/iana/2026-07-22/language-subtag-registry.txt"
)
EXPECTED_FILE_DATE = "2026-06-14"
EXPECTED_SHA256 = "be1fad86a99e3a932d07b80c9b3c271ec2381a5909ce22420144e5077ab0a43a"
EXPECTED_BYTES = 731605
SURFACES = ("response", "plan", "diagnostics")
KINDS = {
    1: "command-session",
    2: "environment",
    3: "project",
    4: "user",
    5: "built-in",
}
PROVENANCE_FIELDS = (
    "surface",
    "rank",
    "kind",
    "requested",
    "canonical",
    "resolved",
    "fallback",
    "diagnostic",
)
VARIANT_RE = re.compile(r"^(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3})$")
OVERLAY_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9][a-z0-9_-]*)+$")
OVERLAY_CLASSES = {
    "semantic-source",
    "render-resource",
    "english-only",
    "machine-identity",
    "generated-target",
    "legacy-input",
}
OVERLAY_LOCALIZATION = {
    "sparse-overlay",
    "forbidden",
    "immutable-token",
    "renderer-only",
    "input-only",
}
OVERLAY_CARRIERS = (
    "code.comments",
    "code.docstrings",
    "development.docs",
    "diagnostic.message",
    "generated.provider-target",
    "legacy.skill-ru",
    "machine.identity",
    "plan.human-text",
    "plugin.human-metadata",
    "provider.human-message",
    "semantic.command",
    "semantic.skill",
)


class Refusal(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedTag:
    language: str | None
    extlangs: tuple[str, ...]
    script: str | None
    region: str | None
    variants: tuple[str, ...]
    extensions: tuple[tuple[str, tuple[str, ...]], ...]
    private: tuple[str, ...]
    registered_tag: str | None = None


@dataclass
class Registry:
    records: dict[str, dict[str, dict[str, object]]]
    tags: dict[str, dict[str, object]]
    ranges: dict[str, list[tuple[str, str]]]


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal("LOCALE_SCHEMA_INVALID") from exc


def parse_registry(data: bytes) -> Registry:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH") from exc
    if not text.startswith(f"File-Date: {EXPECTED_FILE_DATE}\n"):
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH")

    records: dict[str, dict[str, dict[str, object]]] = {}
    tags: dict[str, dict[str, object]] = {}
    ranges: dict[str, list[tuple[str, str]]] = {}
    for block in text.split("%%\n")[1:]:
        fields: dict[str, object] = {}
        last_key = None
        for line in block.splitlines():
            if line.startswith("  ") and last_key:
                previous = fields[last_key]
                if isinstance(previous, list):
                    previous[-1] += " " + line.strip()
                else:
                    fields[last_key] = str(previous) + " " + line.strip()
                continue
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            last_key = key
            if key in fields:
                if not isinstance(fields[key], list):
                    fields[key] = [fields[key]]
                fields[key].append(value)
            else:
                fields[key] = value
        record_type = str(fields.get("Type", "")).lower()
        if "Tag" in fields:
            tags[str(fields["Tag"]).lower()] = fields
        if "Subtag" not in fields or not record_type:
            continue
        subtag = str(fields["Subtag"]).lower()
        if ".." in subtag:
            start, end = subtag.split("..", 1)
            ranges.setdefault(record_type, []).append((start, end))
        else:
            records.setdefault(record_type, {})[subtag] = fields
    return Registry(records=records, tags=tags, ranges=ranges)


def registered(registry: Registry, record_type: str, subtag: str) -> bool:
    lowered = subtag.lower()
    if lowered in registry.records.get(record_type, {}):
        return True
    return any(start <= lowered <= end for start, end in registry.ranges.get(record_type, []))


def parse_tag(tag: str, registry: Registry) -> ParsedTag:
    if not isinstance(tag, str) or not tag or len(tag) > 255 or "_" in tag:
        raise Refusal("LOCALE_MALFORMED")
    if tag.lower() in registry.tags:
        return ParsedTag(None, (), None, None, (), (), (), tag.lower())
    parts = tag.split("-")
    if any(not part or len(part) > 8 or not part.isascii() or not part.isalnum() for part in parts):
        raise Refusal("LOCALE_MALFORMED")
    lowered = [part.lower() for part in parts]
    if lowered[0] == "x":
        if len(parts) < 2:
            raise Refusal("LOCALE_MALFORMED")
        return ParsedTag(None, (), None, None, (), (), tuple(lowered[1:]))

    language = lowered[0]
    if not language.isalpha() or not 2 <= len(language) <= 8:
        raise Refusal("LOCALE_MALFORMED")
    index = 1
    extlangs: list[str] = []
    if len(language) in (2, 3):
        while index < len(parts) and len(extlangs) < 3 and len(parts[index]) == 3 and parts[index].isalpha():
            extlangs.append(lowered[index])
            index += 1
    script = None
    if index < len(parts) and len(parts[index]) == 4 and parts[index].isalpha():
        script = lowered[index]
        index += 1
    region = None
    if index < len(parts) and (
        (len(parts[index]) == 2 and parts[index].isalpha())
        or (len(parts[index]) == 3 and parts[index].isdigit())
    ):
        region = lowered[index]
        index += 1
    variants: list[str] = []
    while index < len(parts) and VARIANT_RE.fullmatch(parts[index]):
        value = lowered[index]
        if value in variants:
            raise Refusal("LOCALE_MALFORMED")
        variants.append(value)
        index += 1
    extensions: list[tuple[str, tuple[str, ...]]] = []
    singletons: set[str] = set()
    while index < len(parts) and len(parts[index]) == 1 and lowered[index] != "x":
        singleton = lowered[index]
        if singleton in singletons:
            raise Refusal("LOCALE_MALFORMED")
        singletons.add(singleton)
        index += 1
        values: list[str] = []
        while index < len(parts) and 2 <= len(parts[index]) <= 8:
            values.append(lowered[index])
            index += 1
        if not values:
            raise Refusal("LOCALE_MALFORMED")
        extensions.append((singleton, tuple(values)))
    private: tuple[str, ...] = ()
    if index < len(parts) and lowered[index] == "x":
        if index + 1 == len(parts):
            raise Refusal("LOCALE_MALFORMED")
        private = tuple(lowered[index + 1 :])
        index = len(parts)
    if index != len(parts):
        raise Refusal("LOCALE_MALFORMED")
    return ParsedTag(
        language,
        tuple(extlangs),
        script,
        region,
        tuple(variants),
        tuple(extensions),
        private,
    )


def preferred(registry: Registry, record_type: str, subtag: str) -> str:
    record = registry.records.get(record_type, {}).get(subtag.lower())
    if not record:
        return subtag
    return str(record.get("Preferred-Value", subtag))


def canonicalize(tag: str, registry: Registry) -> str:
    parsed = parse_tag(tag, registry)
    if parsed.registered_tag:
        record = registry.tags[parsed.registered_tag]
        target = str(record.get("Preferred-Value", parsed.registered_tag))
        if target.lower() != parsed.registered_tag:
            return canonicalize(target, registry)
        return target.lower()
    if parsed.language is None:
        return "x-" + "-".join(parsed.private)
    if not registered(registry, "language", parsed.language):
        raise Refusal("LOCALE_UNREGISTERED")
    language = preferred(registry, "language", parsed.language).lower()
    extlangs = []
    for value in parsed.extlangs:
        if not registered(registry, "extlang", value):
            raise Refusal("LOCALE_UNREGISTERED")
        extlangs.append(preferred(registry, "extlang", value).lower())
    script = None
    if parsed.script:
        if not registered(registry, "script", parsed.script):
            raise Refusal("LOCALE_UNREGISTERED")
        script = preferred(registry, "script", parsed.script).title()
    region = None
    if parsed.region:
        if not registered(registry, "region", parsed.region):
            raise Refusal("LOCALE_UNREGISTERED")
        region = preferred(registry, "region", parsed.region).upper()
    variants = []
    for value in parsed.variants:
        if not registered(registry, "variant", value):
            raise Refusal("LOCALE_UNREGISTERED")
        variants.append(preferred(registry, "variant", value).lower())
    out = [language, *extlangs]
    if script:
        out.append(script)
    if region:
        out.append(region)
    out.extend(variants)
    for singleton, values in parsed.extensions:
        out.extend((singleton, *values))
    if parsed.private:
        out.extend(("x", *parsed.private))
    return "-".join(out)


def catalog_resolve(canonical: str) -> tuple[str | None, bool, str | None]:
    lowered = canonical.lower()
    parts = lowered.split("-")
    if parts[0] == "x" or "x" in parts[1:]:
        return None, False, "LOCALE_UNSUPPORTED_PRIVATE_USE"
    if lowered in ("en", "ru"):
        return lowered, False, None
    while len(parts) > 1:
        parts.pop()
        parent = "-".join(parts)
        if parent in ("en", "ru"):
            return parent, True, None
    return "en", True, "LOCALE_UNSUPPORTED_CATALOG"


def validate_layer_shape(layer: object) -> None:
    if not isinstance(layer, dict):
        raise Refusal("LOCALE_SCHEMA_INVALID")
    if layer.get("kind") == "provider-adapter-status":
        raise Refusal("LOCALE_ADAPTER_INPUT_FORBIDDEN")
    if layer.get("persist") is True:
        raise Refusal("LOCALE_PERSISTENCE_FORBIDDEN")
    if "copy_to" in layer:
        raise Refusal("LOCALE_CROSS_SURFACE_LEAKAGE")
    allowed = {"contract_version", "rank", "kind", "locale"}
    if set(layer) - allowed:
        raise Refusal("LOCALE_UNKNOWN_FIELD")
    if layer.get("contract_version") != "1.0.0":
        raise Refusal("LOCALE_VERSION_UNSUPPORTED")
    rank = layer.get("rank")
    kind = layer.get("kind")
    if not isinstance(rank, int) or rank not in KINDS or kind != KINDS[rank]:
        raise Refusal("LOCALE_CARRIER_MISMATCH")
    locale = layer.get("locale")
    if not isinstance(locale, dict) or not locale:
        raise Refusal("LOCALE_SCHEMA_INVALID")
    if set(locale) - set(SURFACES):
        raise Refusal("LOCALE_UNSUPPORTED_SURFACE")
    if any(not isinstance(value, str) or not value for value in locale.values()):
        raise Refusal("LOCALE_SCHEMA_INVALID")


def resolve_layers(layers: object, registry: Registry) -> dict[str, dict[str, object]]:
    if not isinstance(layers, list) or not layers:
        raise Refusal("LOCALE_SCHEMA_INVALID")
    for layer in layers:
        validate_layer_shape(layer)
    ranks = [layer["rank"] for layer in layers]
    if len(ranks) != len(set(ranks)):
        raise Refusal("LOCALE_DUPLICATE_RANK")
    built_in = [layer for layer in layers if layer["rank"] == 5]
    if len(built_in) != 1 or built_in[0]["locale"] != {surface: "en" for surface in SURFACES}:
        raise Refusal("LOCALE_CARRIER_MISMATCH")
    ordered = sorted(layers, key=lambda item: item["rank"])
    result: dict[str, dict[str, object]] = {}
    for surface in SURFACES:
        winner = next(layer for layer in ordered if surface in layer["locale"])
        requested = winner["locale"][surface]
        canonical = canonicalize(requested, registry)
        resolved, fallback, diagnostic = catalog_resolve(canonical)
        if diagnostic == "LOCALE_UNSUPPORTED_PRIVATE_USE":
            raise Refusal(diagnostic)
        row = {
            "surface": surface,
            "rank": winner["rank"],
            "kind": winner["kind"],
            "requested": requested,
            "canonical": canonical,
            "resolved": resolved,
            "fallback": fallback,
            "diagnostic": diagnostic,
        }
        if tuple(row) != PROVENANCE_FIELDS:
            raise Refusal("LOCALE_CROSS_SURFACE_LEAKAGE")
        result[surface] = row
    return result


def verify_registry(registry_path: Path, upstream_path: Path) -> Registry:
    data = registry_path.read_bytes()
    if len(data) != EXPECTED_BYTES or hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH")
    upstream = load_json(upstream_path)
    expected = {
        "url": EXPECTED_URL,
        "retrieval_url": EXPECTED_RETRIEVAL_URL,
        "file_date": EXPECTED_FILE_DATE,
        "sha256": EXPECTED_SHA256,
        "bytes": EXPECTED_BYTES,
    }
    if not isinstance(upstream, dict) or any(upstream.get(key) != value for key, value in expected.items()):
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH")
    if not isinstance(upstream.get("retrieved_at"), str) or not upstream.get("vendoring_policy"):
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH")
    return parse_registry(data)


def verify_contract(contract_path: Path) -> None:
    text = contract_path.read_text(encoding="utf-8")
    required = (
        "`response`, `plan`, and `diagnostics`",
        "`command-session`",
        "`environment`",
        "`.swissknife.json#/locale`",
        "`~/.swissknifeman/locale.json#/locale`",
        "### Stage 1 — RFC 5646 syntax",
        "### Stage 2 — registry-backed canonicalization",
        "### Stage 3 — Swissknifeman catalog",
        EXPECTED_URL,
        EXPECTED_FILE_DATE,
        EXPECTED_SHA256,
        str(EXPECTED_BYTES),
        "`LOCALE_UNSUPPORTED_PRIVATE_USE`",
        "`LOCALE_UNSUPPORTED_CATALOG`",
        "## P1 provider-configuration crosswalk",
        "APPROVE P2.1 LOCALE-RESOLUTION L1-L6 AS WRITTEN",
    )
    missing = [fragment for fragment in required if fragment not in text]
    if missing:
        raise Refusal("LOCALE_SCHEMA_INVALID")
    candidate = (
        "**Version:** v1.0.0-candidate" in text
        and "**Status:** candidate" in text
        and "**Approval:** pending exact P2.1 decision" in text
    )
    frozen = (
        "**Version:** v1.0.0\n" in text
        and "**Status:** frozen" in text
        and re.search(r"^\*\*Approval:\*\* D[0-9]+ · 2026-[0-9]{2}-[0-9]{2}$", text, re.MULTILINE)
    )
    if not candidate and not frozen:
        raise Refusal("LOCALE_SCHEMA_INVALID")


def compare_resolution(actual: dict[str, dict[str, object]], expected: object) -> bool:
    if not isinstance(expected, dict) or tuple(expected) != SURFACES:
        return False
    stripped = {
        surface: {key: value for key, value in row.items() if key != "surface"}
        for surface, row in actual.items()
    }
    return stripped == expected


def run_validation(contract: Path, registry_path: Path, upstream: Path, fixtures: Path) -> Registry:
    verify_contract(contract)
    registry = verify_registry(registry_path, upstream)
    positive = load_json(fixtures / "positive.json")
    negative = load_json(fixtures / "negative.json")
    if not isinstance(positive, dict) or not isinstance(negative, dict):
        raise Refusal("LOCALE_SCHEMA_INVALID")
    if positive.get("provenance_fields") != list(PROVENANCE_FIELDS):
        raise Refusal("LOCALE_SCHEMA_INVALID")
    registry_identity = positive.get("registry")
    if registry_identity != {
        "file_date": EXPECTED_FILE_DATE,
        "sha256": EXPECTED_SHA256,
        "bytes": EXPECTED_BYTES,
    }:
        raise Refusal("LOCALE_REGISTRY_IDENTITY_MISMATCH")

    for vector in positive.get("syntax_vectors", []):
        accepted = True
        try:
            parse_tag(vector["requested"], registry)
        except Refusal:
            accepted = False
        if accepted is not vector.get("accepted"):
            raise Refusal("LOCALE_MALFORMED")
    for vector in positive.get("canonicalization_vectors", []):
        if canonicalize(vector["requested"], registry) != vector.get("canonical"):
            raise Refusal("LOCALE_UNREGISTERED")
    for vector in positive.get("catalog_vectors", []):
        actual = catalog_resolve(vector["canonical"])
        expected = (vector.get("resolved"), vector.get("fallback"), vector.get("diagnostic"))
        if actual != expected:
            raise Refusal("LOCALE_UNSUPPORTED_CATALOG")
    for case in positive.get("resolution_cases", []):
        actual = resolve_layers(case.get("layers"), registry)
        if not compare_resolution(actual, case.get("expected")):
            raise Refusal("LOCALE_CROSS_SURFACE_LEAKAGE")

    cases = negative.get("cases")
    if not isinstance(cases, list) or not cases:
        raise Refusal("LOCALE_SCHEMA_INVALID")
    for case in cases:
        observed = None
        try:
            resolve_layers(case.get("layers"), registry)
        except Refusal as exc:
            observed = exc.code
        if observed != case.get("code"):
            raise Refusal("LOCALE_SCHEMA_INVALID")
    return registry


def run_self_test(registry: Registry) -> None:
    observed: dict[str, str] = {}
    try:
        parse_tag("en--US", registry)
    except Refusal as exc:
        observed["syntax"] = exc.code

    changed = copy.deepcopy(registry)
    changed.records["language"].pop("ru", None)
    try:
        canonicalize("ru-RU", changed)
    except Refusal as exc:
        observed["canonicalization"] = exc.code

    resolved, fallback, diagnostic = catalog_resolve("fr-FR")
    if (resolved, fallback, diagnostic) == ("en", True, "LOCALE_UNSUPPORTED_CATALOG"):
        observed["catalog"] = diagnostic

    leaking = [
        {"contract_version": "1.0.0", "rank": 1, "kind": "command-session", "locale": {"response": "ru"}, "copy_to": "plan"},
        {"contract_version": "1.0.0", "rank": 5, "kind": "built-in", "locale": {"response": "en", "plan": "en", "diagnostics": "en"}},
    ]
    try:
        resolve_layers(leaking, registry)
    except Refusal as exc:
        observed["provenance"] = exc.code

    expected = {
        "syntax": "LOCALE_MALFORMED",
        "canonicalization": "LOCALE_UNREGISTERED",
        "catalog": "LOCALE_UNSUPPORTED_CATALOG",
        "provenance": "LOCALE_CROSS_SURFACE_LEAKAGE",
    }
    if observed != expected:
        raise Refusal("LOCALE_SCHEMA_INVALID")


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def source_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def matrix_markdown(matrix: dict[str, object]) -> str:
    def cell(value: object, *, code: bool = False) -> str:
        if value is None:
            return "—"
        rendered = str(value).replace("|", "\\|")
        return f"`{rendered}`" if code else rendered

    lines = [
        "# P2 authoring carrier matrix",
        "",
        "Generated from `P2-authoring-carrier-matrix.json`. Do not edit manually.",
        "",
        f"Contract: `{matrix['contract_version']}` · source: `{matrix['source_language']}` "
        f"· overlays: `{', '.join(matrix['overlay_locales'])}`",
        "",
        "| Carrier | Pattern | Class | Canonical owner | Localization | Overlay namespace | Generated owner | Migration admission | Rollback |",
        "|:--|:--|:--|:--|:--|:--|:--|:--|:--|",
    ]
    for row in matrix["rows"]:
        lines.append(
            "| "
            + " | ".join(
                (
                    cell(row["carrier_id"], code=True),
                    cell(row["pattern"], code=True),
                    cell(row["class"], code=True),
                    cell(row["canonical_owner"]),
                    cell(row["localization"], code=True),
                    cell(row["overlay_namespace"], code=row["overlay_namespace"] is not None),
                    cell(row["generated_owner"]),
                    cell(row["migration_admission"]),
                    cell(row["rollback"]),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def verify_overlay_contract(contract_path: Path, locale_contract_path: Path) -> None:
    contract = contract_path.read_text(encoding="utf-8")
    locale_contract = locale_contract_path.read_text(encoding="utf-8")
    required = (
        "**Version:** v1.0.0-candidate",
        "**Status:** candidate",
        "`en`; the only rendered overlay locale is `ru`",
        "`source_catalog_sha256`",
        "`immutable_tokens`",
        "`OVERLAY_IMMUTABLE_TOKEN_MISMATCH`",
        "`OVERLAY_CROSS_PROVIDER_TARGET`",
        "`OVERLAY_OVERRIDE_ADOPTION_FORBIDDEN`",
        "APPROVE P2.2 ENGLISH-OVERLAY E1-E7 AS WRITTEN",
    )
    frozen_required = (
        "**Version:** v1.0.0\n",
        "**Status:** frozen",
        "APPROVE P2.2 ENGLISH-OVERLAY E1-E7 AS WRITTEN",
    )
    candidate = all(fragment in contract for fragment in required)
    frozen = all(fragment in contract for fragment in frozen_required) and bool(
        re.search(r"^\*\*Approval:\*\* D[0-9]+ · 2026-[0-9]{2}-[0-9]{2}$", contract, re.MULTILINE)
    )
    if not candidate and not frozen:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    if (
        "**Version:** v1.0.0" not in locale_contract
        or "**Status:** frozen" not in locale_contract
        or "The rendered catalog set is exactly `en` and `ru`." not in locale_contract
    ):
        raise Refusal("OVERLAY_FALLBACK_MISSING")


def verify_matrix(matrix_path: Path) -> dict[str, object]:
    matrix = load_json(matrix_path)
    if not isinstance(matrix, dict) or set(matrix) != {
        "$schema", "contract_version", "source_language", "overlay_locales", "rows"
    }:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    if (
        matrix.get("$schema") != "urn:swissknifeman:authoring-carrier-matrix:v1"
        or matrix.get("contract_version") != "1.0.0"
        or matrix.get("source_language") != "en"
        or matrix.get("overlay_locales") != ["ru"]
    ):
        raise Refusal("OVERLAY_VERSION_UNSUPPORTED")
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    expected_fields = {
        "carrier_id", "pattern", "class", "canonical_owner", "localization",
        "overlay_namespace", "generated_owner", "migration_admission", "rollback",
    }
    ids = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise Refusal("OVERLAY_UNKNOWN_FIELD")
        if any(
            not isinstance(row[field], str) or not row[field]
            for field in ("carrier_id", "pattern", "canonical_owner", "migration_admission", "rollback")
        ):
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        if row["class"] not in OVERLAY_CLASSES or row["localization"] not in OVERLAY_LOCALIZATION:
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        if row["overlay_namespace"] is not None and not isinstance(row["overlay_namespace"], str):
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        if row["generated_owner"] is not None and not isinstance(row["generated_owner"], str):
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        ids.append(row["carrier_id"])
    if tuple(ids) != OVERLAY_CARRIERS or len(ids) != len(set(ids)):
        raise Refusal("OVERLAY_SOURCE_DUPLICATE")
    return matrix


def token_parity(source: str, rendered: str, tokens: list[str]) -> bool:
    if not all(isinstance(token, str) and token for token in tokens):
        return False
    for token in set(tokens):
        declared = tokens.count(token)
        if source.count(token) != declared or rendered.count(token) != declared:
            return False
    source_positions = [source.find(token) for token in tokens]
    rendered_positions = [rendered.find(token) for token in tokens]
    return source_positions == sorted(source_positions) and rendered_positions == sorted(rendered_positions)


def validate_overlay_fixture(data: object) -> dict[str, object]:
    if not isinstance(data, dict) or set(data) != {
        "$schema", "contract_version", "source_locale", "english_units", "overlay", "migration", "expected"
    }:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    if data.get("source_locale") != "en":
        raise Refusal("OVERLAY_LOCALIZED_SEMANTIC_SOURCE")
    english = data.get("english_units")
    if not isinstance(english, dict) or not english:
        raise Refusal("OVERLAY_FALLBACK_MISSING")
    source_identities = []
    for key, unit in english.items():
        if not OVERLAY_KEY_RE.fullmatch(key):
            raise Refusal("OVERLAY_KEY_INVALID")
        if not isinstance(unit, dict) or set(unit) != {"source_identity", "text", "immutable_tokens"}:
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        if unit.get("source_identity") != key:
            source_identities.append(unit.get("source_identity"))
        else:
            source_identities.append(key)
        if not isinstance(unit.get("text"), str) or not isinstance(unit.get("immutable_tokens"), list):
            raise Refusal("OVERLAY_SCHEMA_INVALID")
    if len(source_identities) != len(set(source_identities)):
        raise Refusal("OVERLAY_SOURCE_DUPLICATE")

    migration = data.get("migration")
    if migration == {"source_class": "local-override", "action": "adopt"}:
        raise Refusal("OVERLAY_OVERRIDE_ADOPTION_FORBIDDEN")
    if migration != {"source_class": "owned", "action": "preserve"}:
        raise Refusal("OVERLAY_SCHEMA_INVALID")

    overlay = data.get("overlay")
    if not isinstance(overlay, dict) or set(overlay) != {
        "$schema", "contract_version", "locale", "source_catalog_sha256", "units"
    }:
        raise Refusal("OVERLAY_UNKNOWN_FIELD")
    if overlay.get("$schema") != "urn:swissknifeman:localized-overlay:v1" or overlay.get("contract_version") != "1.0.0":
        raise Refusal("OVERLAY_VERSION_UNSUPPORTED")
    if overlay.get("locale") != "ru":
        raise Refusal("OVERLAY_LOCALIZED_SEMANTIC_SOURCE")
    if overlay.get("source_catalog_sha256") != canonical_digest(english):
        raise Refusal("OVERLAY_SOURCE_DIGEST_MISMATCH")
    units = overlay.get("units")
    if not isinstance(units, dict):
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    for key, unit in units.items():
        if not OVERLAY_KEY_RE.fullmatch(key) or key not in english:
            raise Refusal("OVERLAY_KEY_INVALID")
        if not isinstance(unit, dict) or set(unit) != {"source_sha256", "immutable_tokens", "text"}:
            raise Refusal("OVERLAY_UNKNOWN_FIELD")
        source = english[key]
        if unit.get("source_sha256") != source_digest(source["text"]):
            raise Refusal("OVERLAY_SOURCE_DIGEST_MISMATCH")
        if unit.get("immutable_tokens") != source["immutable_tokens"] or not token_parity(
            source["text"], unit.get("text", ""), source["immutable_tokens"]
        ):
            raise Refusal("OVERLAY_IMMUTABLE_TOKEN_MISMATCH")

    expected = data.get("expected")
    if not isinstance(expected, dict) or set(expected) != {"resolved_locales", "fallback_keys", "provider_requests"}:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    resolved = expected.get("resolved_locales")
    if not isinstance(resolved, dict):
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    for key, locale in resolved.items():
        if key not in english:
            raise Refusal("OVERLAY_FALLBACK_MISSING")
        actual = "ru" if key in units else "en"
        if locale != actual:
            raise Refusal("OVERLAY_FALLBACK_MISSING")
    fallback = sorted(key for key in english if key not in units)
    if expected.get("fallback_keys") != fallback:
        raise Refusal("OVERLAY_FALLBACK_MISSING")
    requests = expected.get("provider_requests")
    if not isinstance(requests, list) or not requests:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    for request in requests:
        if not isinstance(request, dict) or set(request) != {"provider_id", "target_owner", "source"}:
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        if request["provider_id"] != request["target_owner"]:
            raise Refusal("OVERLAY_CROSS_PROVIDER_TARGET")
        if request["source"] == "generated-target":
            raise Refusal("OVERLAY_GENERATED_EDIT_FORBIDDEN")
        if request["source"] != "resolved-semantic-request":
            raise Refusal("OVERLAY_SCHEMA_INVALID")
    return data


def mutate_overlay_fixture(base: dict[str, object], mutation: str) -> dict[str, object]:
    candidate = copy.deepcopy(base)
    keys = list(candidate["english_units"])
    if mutation == "duplicate-source":
        candidate["english_units"][keys[1]]["source_identity"] = keys[0]
    elif mutation == "invalid-key":
        unit = candidate["overlay"]["units"].pop(keys[0])
        candidate["overlay"]["units"]["Invalid Key"] = unit
    elif mutation == "localized-semantic-source":
        candidate["source_locale"] = "ru"
    elif mutation == "generated-edit":
        candidate["expected"]["provider_requests"][0]["source"] = "generated-target"
    elif mutation == "missing-fallback":
        candidate["english_units"].pop(keys[-1])
    elif mutation == "immutable-token":
        candidate["overlay"]["units"][keys[1]]["text"] = "Проверяй внешние утверждения через context7 до ВебПоиска."
    elif mutation == "cross-provider-target":
        candidate["expected"]["provider_requests"][0]["target_owner"] = "codex"
    elif mutation == "override-adoption":
        candidate["migration"] = {"source_class": "local-override", "action": "adopt"}
    else:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    candidate["overlay"]["source_catalog_sha256"] = canonical_digest(candidate["english_units"])
    return candidate


def run_overlay_validation(
    locale_contract: Path,
    contract: Path,
    matrix_path: Path,
    fixtures: Path,
) -> None:
    verify_overlay_contract(contract, locale_contract)
    matrix = verify_matrix(matrix_path)
    projection = matrix_path.with_suffix(".md")
    if projection.read_text(encoding="utf-8") != matrix_markdown(matrix):
        raise Refusal("OVERLAY_GENERATED_EDIT_FORBIDDEN")
    positive = load_json(fixtures / "overlay-positive.json")
    negative = load_json(fixtures / "overlay-negative.json")
    validate_overlay_fixture(positive)
    if not isinstance(negative, dict) or set(negative) != {"$schema", "contract_version", "cases"}:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    cases = negative.get("cases")
    if not isinstance(cases, list) or not cases:
        raise Refusal("OVERLAY_SCHEMA_INVALID")
    observed = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "mutation", "code"}:
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        code = None
        try:
            validate_overlay_fixture(mutate_overlay_fixture(positive, case["mutation"]))
        except Refusal as exc:
            code = exc.code
        if code != case["code"]:
            raise Refusal("OVERLAY_SCHEMA_INVALID")
        observed.append(case["id"])
    if tuple(observed) != (
        "duplicate-source", "invalid-key", "localized-semantic-source", "generated-edit",
        "missing-fallback", "immutable-token", "cross-provider-target", "override-adoption",
    ):
        raise Refusal("OVERLAY_SCHEMA_INVALID")


def defaults() -> tuple[Path, Path, Path, Path]:
    script = Path(__file__).resolve()
    plan_dir = script.parents[1]
    repo = script.parents[3]
    return (
        plan_dir / "root/contracts/locale-resolution-v1.md",
        repo / "core/locale/data/language-subtag-registry.txt",
        repo / "core/locale/data/upstream.json",
        plan_dir / "artifacts/P2-locale-resolution-fixtures",
    )


def main(argv: list[str] | None = None) -> int:
    default_contract, default_registry, default_upstream, default_fixtures = defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("resolution", "overlay"))
    parser.add_argument("--self-test", choices=("resolution", "overlay"))
    parser.add_argument("--contract", type=Path, default=default_contract)
    parser.add_argument("--locale-contract", type=Path, default=default_contract)
    parser.add_argument("--matrix", type=Path, default=default_contract.parents[1] / "P2-authoring-carrier-matrix.json")
    parser.add_argument("--registry", type=Path, default=default_registry)
    parser.add_argument("--registry-upstream", type=Path, default=default_upstream)
    parser.add_argument("--fixtures", type=Path, default=default_fixtures)
    args = parser.parse_args(argv)
    if not args.stage and not args.self_test:
        parser.error("one of --stage/--self-test resolution|overlay is required")
    try:
        if args.stage == "overlay" or args.self_test == "overlay":
            run_overlay_validation(
                args.locale_contract,
                args.contract,
                args.matrix,
                args.fixtures,
            )
            if args.self_test:
                print("overlay self-test: pass (duplicate source, immutable token, localized source, generated edit, fallback, provider target, override)")
            else:
                print("overlay: pass")
                print("matrix: pass")
            return 0
        registry = run_validation(
            args.contract,
            args.registry,
            args.registry_upstream,
            args.fixtures,
        )
        if args.self_test:
            run_self_test(registry)
            print("resolution self-test: pass (syntax, canonicalization, catalog, provenance)")
        else:
            print("resolution: pass")
    except (OSError, UnicodeError, Refusal) as exc:
        code = exc.code if isinstance(exc, Refusal) else "LOCALE_SCHEMA_INVALID"
        stage = args.stage or args.self_test or "resolution"
        print(f"{stage}: fail: {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
