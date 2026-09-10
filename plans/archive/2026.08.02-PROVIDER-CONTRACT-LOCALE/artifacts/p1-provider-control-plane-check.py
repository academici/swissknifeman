#!/usr/bin/env python3
"""Stdlib-only conformance checker for provider-control-plane v1 fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import posixpath
from pathlib import Path
import re
import sys


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
_SEMANTIC_ID = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_SKILL_ID = re.compile(r"^[a-z][a-z0-9-]*/[a-z][a-z0-9-]*$")
_MACHINE_CODE = re.compile(r"^[A-Z][A-Z0-9_]+$")
_RFC3339_Z = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_PROVIDER_STATUSES = {
    "not-selected", "ready", "unapplied", "observation-missing",
    "observation-stale", "drifted", "unsupported", "untrusted", "unknown", "error",
}
_AGGREGATE_STATUSES = {
    "ready", "unknown", "drifted", "blocked", "error", "no-providers-selected",
}
_SEVERITY = {"error": 0, "warning": 1, "info": 2}
_MIGRATION_SOURCE_CLASSES = {"legacy-absent-config", "provider-config-v1"}
_MIGRATION_CLASSIFICATIONS = {
    "canonical-equivalent", "stale-managed-copy", "broken-link",
    "local-override", "ambiguous",
}
_MIGRATION_NO_WRITE_MODES = {"plan", "check", "dry-run"}
_MIGRATION_WRITE_ORDER = ["provider-targets", "provider-lock", "provider-status"]
_MIGRATION_NEGATIVE_CODES = {
    "MIG_SOURCE_CLASS_UNKNOWN",
    "MIG_SOURCE_NEWER_MAJOR",
    "MIG_SOURCE_VERSION_UNSUPPORTED",
    "MIG_SOURCE_CORRUPT",
    "MIG_CLASSIFICATION_INCOMPLETE",
    "MIG_CLASSIFICATION_AMBIGUOUS",
    "MIG_LOCAL_OVERRIDE",
    "MIG_OWNERSHIP_UNPROVEN",
    "MIG_PREIMAGE_CHANGED",
    "MIG_TARGET_SNAPSHOT_INCOMPLETE",
    "MIG_TARGET_SNAPSHOT_INVALID",
    "MIG_PROVIDER_SET_MISMATCH",
    "MIG_WRITE_FORBIDDEN",
    "MIG_AUTHORITY_REQUIRED",
    "MIG_BACKUP_SET_MISMATCH",
    "MIG_PROVIDER_PARTIAL",
    "MIG_ROLLBACK_FAILED",
    "MIG_READBACK_FAILED",
    "MIG_SECOND_RECONCILE_NONEMPTY",
}
_PREDECESSOR_GATES = tuple(f"G{number:02d}" for number in range(1, 12))
_PREDECESSOR_GATE_HEADERS = (
    "Gate", "Transition", "Exact producer item / verifier", "Evidence path", "Owner",
    "Pass rule", "failure action",
)
_CROSSWALK_HEADERS = (
    "Gate", "Source row SHA-256", "Preserved obligation", "P1.3 enforcement",
)


class ContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _raise(code: str) -> None:
    raise ContractError(code)


def _mapping(value: object, code: str = "PCP_SCHEMA_INVALID") -> dict[str, object]:
    if not isinstance(value, dict):
        _raise(code)
    return value


def _exact(value: object, fields: set[str], *, invalid: str = "PCP_SCHEMA_INVALID") -> dict[str, object]:
    record = _mapping(value, invalid)
    if set(record) - fields:
        _raise("PCP_SCHEMA_UNKNOWN")
    if fields - set(record):
        _raise(invalid)
    return record


def _v1_patch(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"1\.0\.[0-9]+", value) is not None


def _stable_id(value: object) -> bool:
    return isinstance(value, str) and _SEMANTIC_ID.fullmatch(value) is not None


def _source_id(value: object) -> bool:
    return isinstance(value, str) and _SOURCE_ID.fullmatch(value) is not None and "/" not in value


def _provider_id(value: object) -> bool:
    return isinstance(value, str) and _PROVIDER_ID.fullmatch(value) is not None


def _skill_id(value: object) -> bool:
    return isinstance(value, str) and _SKILL_ID.fullmatch(value) is not None


def _timestamp(value: object) -> bool:
    return isinstance(value, str) and _RFC3339_Z.fullmatch(value) is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_diagnostics(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _raise("PCP_DIAGNOSTIC_INVALID")
    rows: list[dict[str, object]] = []
    for item in value:
        row = _exact(item, {"severity", "code", "message", "source_ref"},
                     invalid="PCP_DIAGNOSTIC_INVALID")
        if (row["severity"] not in _SEVERITY
                or not isinstance(row["code"], str)
                or _MACHINE_CODE.fullmatch(row["code"]) is None
                or not isinstance(row["message"], str) or not row["message"].strip()
                or not _source_id(row["source_ref"])):
            _raise("PCP_DIAGNOSTIC_INVALID")
        rows.append(row)
    ordered = sorted(rows, key=lambda row: (
        _SEVERITY[row["severity"]], row["source_ref"], row["code"]))
    if rows != ordered:
        _raise("PCP_DIAGNOSTIC_INVALID")
    return rows


def _validate_desired(value: object) -> tuple[dict[str, object], str, str]:
    desired = _exact(value, {
        "provider_config_contract_version", "capability_catalog_version",
        "selection", "provenance", "semantic_digest",
    })
    if (not _v1_patch(desired["provider_config_contract_version"])
            or not _v1_patch(desired["capability_catalog_version"])):
        _raise("PCP_VERSION_UNSUPPORTED")
    selection = _mapping(desired["selection"])
    if not selection or not all(_provider_id(provider_id) for provider_id in selection):
        _raise("PCP_IDENTITY_INVALID")
    expected_paths: list[str] = []
    for provider_id in sorted(selection):
        provider = _exact(selection[provider_id], {
            "enabled", "capabilities", "native_extensions",
        })
        if not isinstance(provider["enabled"], bool):
            _raise("PCP_SCHEMA_INVALID")
        expected_paths.append(f"/selection/{provider_id}/enabled")
        for field in ("capabilities", "native_extensions"):
            decisions = _mapping(provider[field])
            for identity in sorted(decisions):
                if not _stable_id(identity) or not isinstance(decisions[identity], bool):
                    _raise("PCP_IDENTITY_INVALID")
                expected_paths.append(f"/selection/{provider_id}/{field}/{identity}")

    provenance = desired["provenance"]
    if not isinstance(provenance, list):
        _raise("PCP_PROVENANCE_INVALID")
    actual_paths: list[str] = []
    for item in provenance:
        row = _exact(item, {"effective_path", "source", "source_path", "explicit"},
                     invalid="PCP_PROVENANCE_INVALID")
        source = _exact(row["source"], {"kind", "id", "carrier", "path"},
                        invalid="PCP_PROVENANCE_INVALID")
        if (not isinstance(row["effective_path"], str)
                or not row["effective_path"].startswith("/selection/")
                or not isinstance(row["source_path"], str) or not row["source_path"].startswith("/")
                or not isinstance(row["explicit"], bool)
                or source["kind"] not in {"operation", "project", "fleet-project", "fleet-defaults", "legacy"}
                or source["carrier"] not in {"operation", ".swissknife.json", "config.json", "legacy"}
                or not _source_id(source["id"])
                or not isinstance(source["path"], str) or not source["path"].startswith("/")):
            _raise("PCP_PROVENANCE_INVALID")
        actual_paths.append(row["effective_path"])
    if actual_paths != sorted(actual_paths) or actual_paths != sorted(expected_paths):
        _raise("PCP_PROVENANCE_INVALID")

    semantic_value = {key: desired[key] for key in (
        "provider_config_contract_version", "capability_catalog_version", "selection", "provenance")}
    expected_digest = _canonical_digest(semantic_value)
    if not _digest(desired["semantic_digest"]) or desired["semantic_digest"] != expected_digest:
        _raise("PCP_DIGEST_INVALID")
    return selection, expected_digest, desired["capability_catalog_version"]


def _validate_artifacts(value: object) -> None:
    if not isinstance(value, list):
        _raise("PCP_APPLY_INVALID")
    artifact_ids: list[str] = []
    for item in value:
        row = _exact(item, {
            "artifact_id", "adapter_id", "adapter_version", "target_path",
            "source_hash", "rendered_hash",
        }, invalid="PCP_APPLY_INVALID")
        if (not _stable_id(row["artifact_id"]) or not _stable_id(row["adapter_id"])
                or not isinstance(row["adapter_version"], str)
                or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", row["adapter_version"]) is None
                or not isinstance(row["target_path"], str) or row["target_path"].startswith("/")
                or ".." in Path(row["target_path"]).parts
                or not _digest(row["source_hash"]) or not _digest(row["rendered_hash"])):
            _raise("PCP_APPLY_INVALID")
        artifact_ids.append(row["artifact_id"])
    if artifact_ids != sorted(artifact_ids) or len(artifact_ids) != len(set(artifact_ids)):
        _raise("PCP_APPLY_INVALID")


def _validate_apply(value: object, desired_digest: str, catalog_version: str) -> None:
    row = _exact(value, {
        "apply_id", "desired_digest", "capability_catalog_version",
        "artifact_set_digest", "artifacts", "recorded_at",
    }, invalid="PCP_APPLY_INVALID")
    if (not _stable_id(row["apply_id"]) or row["desired_digest"] != desired_digest
            or row["capability_catalog_version"] != catalog_version
            or not _digest(row["artifact_set_digest"]) or not _timestamp(row["recorded_at"])):
        _raise("PCP_APPLY_INVALID")
    _validate_artifacts(row["artifacts"])


def _validate_observed(value: object) -> dict[str, object]:
    row = _exact(value, {
        "observation_id", "provider_version", "observed_at", "fresh_until",
        "freshness", "trust", "capability", "artifacts", "evidence_digest",
    }, invalid="PCP_OBSERVATION_INVALID")
    if (not _stable_id(row["observation_id"])
            or not isinstance(row["provider_version"], str) or not row["provider_version"]
            or not _timestamp(row["observed_at"]) or not _timestamp(row["fresh_until"])
            or row["freshness"] not in {"fresh", "stale", "unknown"}
            or row["trust"] not in {"trusted", "untrusted", "unknown"}
            or row["capability"] not in {"satisfied", "unsupported", "unknown"}
            or row["artifacts"] not in {"clean", "drifted", "unknown"}
            or not _digest(row["evidence_digest"])):
        _raise("PCP_OBSERVATION_INVALID")
    return row


def _provider_status(*, selected: bool, last_applied: object, observed: dict[str, object] | None,
                     diagnostics: list[dict[str, object]]) -> str:
    if not selected:
        return "not-selected"
    if any(row["severity"] == "error" for row in diagnostics):
        return "error"
    if observed is not None and observed["capability"] == "unsupported":
        return "unsupported"
    if observed is not None and observed["trust"] == "untrusted":
        return "untrusted"
    if last_applied is None:
        return "unapplied"
    if observed is None:
        return "observation-missing"
    if observed["freshness"] == "stale":
        return "observation-stale"
    if "unknown" in (observed["freshness"], observed["trust"],
                      observed["capability"], observed["artifacts"]):
        return "unknown"
    if observed["artifacts"] == "drifted":
        return "drifted"
    return "ready"


def _validate_provider(value: object, selection: dict[str, object], desired_digest: str,
                       catalog_version: str) -> tuple[str, bool, str]:
    row = _exact(value, {
        "provider_id", "selected", "desired_digest", "last_applied",
        "observed", "status", "diagnostics",
    })
    provider_id = row["provider_id"]
    if not _provider_id(provider_id):
        _raise("PCP_IDENTITY_INVALID")
    if provider_id not in selection:
        _raise("PCP_PROVIDER_SET_MISMATCH")
    selected = row["selected"]
    if not isinstance(selected, bool) or selected is not selection[provider_id]["enabled"]:
        _raise("PCP_PROVIDER_SET_MISMATCH")
    if row["desired_digest"] != desired_digest:
        _raise("PCP_DIGEST_INVALID")
    diagnostics = _validate_diagnostics(row["diagnostics"])
    if not selected and (row["last_applied"] is not None or row["observed"] is not None):
        _raise("PCP_STATUS_INCONSISTENT")
    if row["last_applied"] is not None:
        _validate_apply(row["last_applied"], desired_digest, catalog_version)
    observed = None if row["observed"] is None else _validate_observed(row["observed"])
    if row["status"] not in _PROVIDER_STATUSES:
        _raise("PCP_STATUS_UNKNOWN")
    expected = _provider_status(selected=selected, last_applied=row["last_applied"],
                                observed=observed, diagnostics=diagnostics)
    if row["status"] != expected:
        _raise("PCP_STATUS_INCONSISTENT")
    return provider_id, selected, expected


def _aggregate_status(selected_statuses: list[str]) -> str:
    if not selected_statuses:
        return "no-providers-selected"
    if "error" in selected_statuses:
        return "error"
    if any(status in {"unsupported", "untrusted"} for status in selected_statuses):
        return "blocked"
    if any(status in {"drifted", "unapplied"} for status in selected_statuses):
        return "drifted"
    if any(status in {"observation-missing", "observation-stale", "unknown"}
           for status in selected_statuses):
        return "unknown"
    return "ready"


def _validate_aggregate(value: object, rows: list[tuple[str, bool, str]]) -> None:
    aggregate = _exact(value, {"status", "selected_provider_ids", "provider_statuses"})
    if aggregate["status"] not in _AGGREGATE_STATUSES:
        _raise("PCP_STATUS_UNKNOWN")
    selected_ids = [provider_id for provider_id, selected, _ in rows if selected]
    status_map = {provider_id: status for provider_id, _, status in rows}
    if (aggregate["selected_provider_ids"] != selected_ids
            or aggregate["provider_statuses"] != status_map
            or aggregate["status"] != _aggregate_status([
                status for _, selected, status in rows if selected])):
        _raise("PCP_AGGREGATE_MISMATCH")


def validate_envelope(value: object) -> None:
    envelope = _exact(value, {"contract_version", "result", "diagnostics"})
    if not _v1_patch(envelope["contract_version"]):
        _raise("PCP_VERSION_UNSUPPORTED")
    diagnostics = _validate_diagnostics(envelope["diagnostics"])
    has_error = any(row["severity"] == "error" for row in diagnostics)
    if envelope["result"] is None:
        if not has_error:
            _raise("PCP_PARTIAL_RESULT")
        return
    if has_error:
        _raise("PCP_PARTIAL_RESULT")
    result = _exact(envelope["result"], {
        "project_id", "desired", "providers", "aggregate", "evaluated_at",
    })
    if not _stable_id(result["project_id"]):
        _raise("PCP_IDENTITY_INVALID")
    if not _timestamp(result["evaluated_at"]):
        _raise("PCP_SCHEMA_INVALID")
    selection, desired_digest, catalog_version = _validate_desired(result["desired"])
    if not isinstance(result["providers"], list):
        _raise("PCP_PROVIDER_SET_MISMATCH")
    rows = [_validate_provider(row, selection, desired_digest, catalog_version)
            for row in result["providers"]]
    provider_ids = [row[0] for row in rows]
    if (provider_ids != sorted(provider_ids) or len(provider_ids) != len(set(provider_ids))
            or set(provider_ids) != set(selection)):
        _raise("PCP_PROVIDER_SET_MISMATCH")
    _validate_aggregate(result["aggregate"], rows)


def _decode_pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        _raise("PCP_SCHEMA_INVALID")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def _apply_mutation(value: object, mutation: object) -> object:
    change = _mapping(mutation)
    operation = change.get("op")
    expected_keys = {"op", "path"} if operation == "remove" else {"op", "path", "value"}
    if set(change) != expected_keys or operation not in {"add", "remove", "replace"}:
        _raise("PCP_SCHEMA_INVALID")
    result = copy.deepcopy(value)
    parts = _decode_pointer(change["path"])
    target = result
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    leaf = parts[-1]
    if isinstance(target, list):
        index = int(leaf)
        if operation == "add":
            target.insert(index, copy.deepcopy(change["value"]))
        elif operation == "remove":
            target.pop(index)
        else:
            target[index] = copy.deepcopy(change["value"])
    elif operation == "remove":
        del target[leaf]
    else:
        target[leaf] = copy.deepcopy(change["value"])
    return result


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: {error}") from error
    return _mapping(value)


def _verify_contract_inventory(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = {
        "## Result envelope", "## DesiredSnapshot", "## Provider status row",
        "## Deterministic provider status", "## Aggregate status", "## Diagnostics",
        "## Versioning and upgrade", "## Normative fixtures and validation",
    } | _PROVIDER_STATUSES | _AGGREGATE_STATUSES | {
        "PCP_VERSION_UNSUPPORTED", "PCP_SCHEMA_INVALID", "PCP_SCHEMA_UNKNOWN",
        "PCP_IDENTITY_INVALID", "PCP_DIGEST_INVALID", "PCP_PROVENANCE_INVALID",
        "PCP_PROVIDER_SET_MISMATCH", "PCP_APPLY_INVALID", "PCP_OBSERVATION_INVALID",
        "PCP_DIAGNOSTIC_INVALID", "PCP_STATUS_UNKNOWN", "PCP_STATUS_INCONSISTENT",
        "PCP_AGGREGATE_MISMATCH", "PCP_PARTIAL_RESULT",
    }
    missing = sorted(literal for literal in required if literal not in text)
    if missing:
        raise ValueError("contract inventory missing: " + ", ".join(missing))


def _run(contract: Path, fixtures: Path) -> None:
    _verify_contract_inventory(contract)
    positive = _load_json(fixtures / "schema-positive.json")
    negative = _load_json(fixtures / "schema-negative.json")
    if positive.get("contract_version") != "1.0.0" or negative.get("contract_version") != "1.0.0":
        raise ValueError("fixture contract version mismatch")
    positive_cases = positive.get("cases")
    negative_cases = negative.get("cases")
    if not isinstance(positive_cases, list) or not positive_cases:
        raise ValueError("positive cases missing")
    if not isinstance(negative_cases, list) or not negative_cases:
        raise ValueError("negative cases missing")
    bases: dict[str, object] = {}
    for case in positive_cases:
        row = _exact(case, {"id", "envelope"})
        if not _stable_id(row["id"]) or row["id"] in bases:
            raise ValueError("positive case identity invalid")
        validate_envelope(row["envelope"])
        bases[row["id"]] = row["envelope"]
    negative_ids: set[str] = set()
    for case in negative_cases:
        row = _exact(case, {"id", "base", "mutation", "expected_code"})
        if not _stable_id(row["id"]) or row["id"] in negative_ids or row["base"] not in bases:
            raise ValueError("negative case identity/base invalid")
        negative_ids.add(row["id"])
        mutated = _apply_mutation(bases[row["base"]], row["mutation"])
        try:
            validate_envelope(mutated)
        except ContractError as error:
            if error.code != row["expected_code"]:
                raise ValueError(
                    f"{row['id']}: expected {row['expected_code']}, got {error.code}") from error
        else:
            raise ValueError(f"{row['id']}: invalid fixture was accepted")


_SUPPORT_LEVELS = ("native", "adapted", "unsupported")
_ACCEPTED_LEVELS = {"native", "adapted"}
_ACCEPTED_LEVEL_ORDER = ("adapted", "native")
_FAILURE_ORDER = {
    "NEG_PROVIDER_DISABLED": 0,
    "NEG_PROVIDER_MISMATCH": 1,
    "NEG_REQUIRED_DENIED": 2,
    "NEG_REQUIRED_MISSING": 3,
    "NEG_REQUIRED_UNSUPPORTED": 4,
    "NEG_REQUIRED_LEVEL_REJECTED": 5,
    "NEG_NATIVE_EXTENSION_INVALID": 6,
}
_MATRIX_FAMILIES = {
    "adapter-registry", "analytics", "canonical-source", "capability-manifest", "diagnostics",
    "lock", "provider-config", "provider-status-evidence", "rendered-target",
    "skill-publication",
}
_MATRIX_CARRIERS = {
    "adapter.descriptor:{provider_id}",
    "adapter.registry",
    "analytics.event.normalized",
    "analytics.reader:{provider_id}",
    "analytics.run-report",
    "analytics.store.project",
    "canonical.command-source",
    "canonical.harness-catalog",
    "canonical.instruction-source",
    "canonical.skill-core",
    "capability.manifest",
    "diagnostic.human",
    "lock.provider-artifacts:{provider_id}",
    "provider-config.carriers",
    "provider-config.effective-selection",
    "provider.evidence.last-applied:{provider_id}",
    "provider.evidence.observed:{provider_id}",
    "provider.projection-plan:{provider_id}",
    "provider.status:{provider_id}",
    "provider.target:{provider_id}",
    "skill.publication-unit:{publication_unit_id}",
    "skill.semantic-catalog",
    "status.aggregate",
}
_MATRIX_ROW_FIELDS = {
    "carrier_id", "family", "owner", "read", "write", "derived_from", "forbidden_use",
}
# Independent frozen semantics.  The JSON under validation is never used to derive these values.
_EXPECTED_MATRIX_ROWS = {
    "adapter.descriptor:{provider_id}": ("adapter-registry", "adapter-package:{provider_id}", ("core.provider.registry", "provider-renderer:{provider_id}"), ("adapter-package:{provider_id}",), ("canonical-source", "capability.manifest"), ("provider-enum-ceiling", "replace-skill-core-meaning", "read-other-provider-output")),
    "adapter.registry": ("adapter-registry", "core.provider.registry", ("control-plane", "provider-renderer:{provider_id}"), ("owning-package-registration",), (), ("filesystem-discovery", "global-mutable-registration", "output-to-output-conversion")),
    "analytics.event.normalized": ("analytics", "analyst.normalizer", ("analytics.run-report", "analytics.store.project"), ("analytics.reader:{provider_id}",), ("analytics.reader:{provider_id}", "analytics.semantic-allowlist"), ("persist-prompt-body", "persist-provider-event-name", "persist-provider-payload-shape", "persist-provider-raw-path", "persist-raw-event-body", "persist-resolved-secret", "persist-transcript")),
    "analytics.reader:{provider_id}": ("analytics", "analyst.reader:{provider_id}", ("analyst.normalizer",), ("analyst.reader:{provider_id}",), ("provider.raw-analytics:{provider_id}",), ("cross-provider-raw-read", "invent-raw-field", "leak-provider-payload", "unknown-schema-fallback", "unredacted-write")),
    "analytics.run-report": ("analytics", "analyst.run-report", ("analytics.consumer", "human-analyst"), ("analyst.run-report",), ("analytics.event.normalized", "analytics.store.project"), ("dereference-raw-evidence", "fabricate-missing-zero", "global-telemetry", "omit-contributing-provenance", "provider-payload-branch")),
    "analytics.store.project": ("analytics", "packages.analyst", ("analytics.consumer", "analytics.run-report"), ("analyst.normalizer",), ("analytics.event.normalized",), ("cross-project-raw-aggregation", "global-telemetry", "overwrite-append-only-event", "provider-owned-analytics-home", "promote-without-human")),
    "canonical.command-source": ("canonical-source", "packages.task", ("provider-renderer:{provider_id}",), ("packages.task",), (), ("adapter-write", "rendered-command-as-source")),
    "canonical.harness-catalog": ("canonical-source", "packages.harness", ("provider-renderer:{provider_id}",), ("packages.harness",), (), ("adapter-write", "provider-target-as-source")),
    "canonical.instruction-source": ("canonical-source", "packages.harness", ("provider-renderer:{provider_id}",), ("packages.harness",), (), ("adapter-write", "provider-instruction-output-as-source")),
    "canonical.skill-core": ("canonical-source", "packages.skiller", ("provider-renderer:{provider_id}",), ("packages.skiller",), (), ("adapter-write", "provider-control-field", "rendered-skill-as-source")),
    "capability.manifest": ("capability-manifest", "core.provider.manifest", ("control-plane", "core.provider.registry"), ("capability-catalog-owner",), (), ("adapter-support-override", "hidden-support-level", "provider-result-as-support")),
    "diagnostic.human": ("diagnostics", "control-plane.presenter", ("human-operator",), ("control-plane.presenter",), ("provider.status:{provider_id}", "status.aggregate"), ("semantic-input", "support-level-source", "write-authorization")),
    "lock.provider-artifacts:{provider_id}": ("lock", "core.provider.lock", ("adapter:{provider_id}", "artifact-audit:{provider_id}"), ("provider-apply-transaction:{provider_id}",), ("provider.projection-plan:{provider_id}", "provider.target:{provider_id}"), ("other-provider-semantic-input", "stale-lock-as-intent", "unowned-target-adoption")),
    "provider-config.carriers": ("provider-config", "provider-config.owner", ("core.provider.config",), ("explicit-config-operation",), (), ("adapter-write", "provider-output-as-config", "status-as-config")),
    "provider-config.effective-selection": ("provider-config", "core.provider.config", ("control-plane", "core.provider.registry"), ("core.provider.config",), ("provider-config.carriers",), ("adapter-reresolve-carriers", "implicit-peer-selection", "persist-derived-selection")),
    "provider.evidence.last-applied:{provider_id}": ("provider-status-evidence", "adapter:{provider_id}", ("control-plane", "provider-audit:{provider_id}"), ("provider-apply-transaction:{provider_id}",), ("lock.provider-artifacts:{provider_id}", "provider-config.effective-selection"), ("other-provider-read", "other-provider-write", "semantic-intent-source")),
    "provider.evidence.observed:{provider_id}": ("provider-status-evidence", "adapter:{provider_id}", ("control-plane", "provider-audit:{provider_id}"), ("provider-observer:{provider_id}",), ("provider.target:{provider_id}",), ("other-provider-read", "other-provider-write", "raw-provider-payload-storage")),
    "provider.projection-plan:{provider_id}": ("rendered-target", "adapter:{provider_id}", ("artifact-manager", "provider-audit:{provider_id}"), ("adapter:{provider_id}",), ("adapter.descriptor:{provider_id}", "canonical-source", "capability.manifest", "provider-config.effective-selection"), ("other-provider-output-input", "replace-canonical-meaning", "write-before-negotiation")),
    "provider.status:{provider_id}": ("provider-status-evidence", "adapter:{provider_id}", ("control-plane.reducer", "human-diagnostic-presenter"), ("adapter:{provider_id}",), ("provider-config.effective-selection", "provider.evidence.last-applied:{provider_id}", "provider.evidence.observed:{provider_id}"), ("other-provider-mask", "support-level-source", "user-authored-status")),
    "provider.target:{provider_id}": ("rendered-target", "adapter:{provider_id}", ("artifact-audit:{provider_id}", "provider-observer:{provider_id}"), ("provider-apply-transaction:{provider_id}",), ("provider.projection-plan:{provider_id}",), ("canonical-source", "other-provider-read", "other-provider-write")),
    "skill.publication-unit:{publication_unit_id}": ("skill-publication", "packages.skiller", ("artifact-manager", "provider-renderer:{provider_id}"), ("packages.skiller",), ("packages.skiller.package-version", "skill.semantic-catalog"), ("implicit-native-install", "output-as-membership-source", "provider-specific-member-identity", "rendered-manifest-as-unit")),
    "skill.semantic-catalog": ("skill-publication", "packages.skiller", ("provider-renderer:{provider_id}",), ("packages.skiller",), ("packages.skiller.core-policy", "packages.skiller.skill-registry"), ("filesystem-discovery", "provider-path-as-skill-id", "rendered-manifest-as-catalog", "translate-semantic-skill-id")),
    "status.aggregate": ("provider-status-evidence", "control-plane.reducer", ("human-diagnostic-presenter", "provider-health-consumer"), ("control-plane.reducer",), ("provider-config.effective-selection", "provider.status:{provider_id}"), ("hide-selected-provider-failure", "rewrite-provider-status", "support-level-source")),
}
_REQUIRED_SEAMS = ("discovery", "renderer", "invocation", "measurement", "replay")
_SEAM_FIELDS = {
    "discovery": {"unit", "budget_unit", "degradation"},
    "renderer": {"id", "version", "target_roots"},
    "invocation": {"mode", "unsupported"},
    "measurement": {"unit", "method", "bounds", "version"},
    "replay": {"fixture_set", "unavailable"},
}
_SKILL_CORE_REQUIRED_FIELDS = {
    "contract_version", "skill_id", "job", "trigger", "inputs", "outputs", "invariants",
    "capabilities", "workflow", "resources", "provenance",
}
_SKILL_CORE_OPTIONAL_FIELDS = {"failure_modes"}
_PROVIDER_CONTROL_FIELDS = {
    "provider", "provider_id", "providers", "model", "model_class", "effort", "invocation",
    "frontmatter", "target_path", "target_roots", "discovery", "renderer", "measurement",
    "replay", "claude", "claude-code", "codex",
}
_PROVIDER_PATH_FRAGMENTS = (".claude/", ".codex/", ".agents/", "claude.md", "agents.md")
_ADAPTER_REPLACEMENT_FIELDS = {
    "semantic_replacement", "job_override", "trigger_override", "invariant_override",
    "semantic_copy", "core", "skill_core", "job", "trigger", "invariants", "outputs",
}
_EVIDENCE_FIELDS = {"claim", "scope", "source", "verified_at"}
_PRODUCER_PROBES = (
    {
        "id": "producer-claude-instructions",
        "provider_id": "claude-code",
        "capability_id": "instructions.project",
        "expected": {
            "provider_id": "claude-code", "outcome": "ready",
            "required": [{"id": "instructions.project", "level": "native",
                          "state": "satisfied", "limitations": []}],
            "limitations": [], "native_extensions": [], "labels": ["supported"],
            "diagnostics": [],
        },
    },
    {
        "id": "producer-claude-skills",
        "provider_id": "claude-code",
        "capability_id": "skills.repository",
        "expected": {
            "provider_id": "claude-code", "outcome": "ready",
            "required": [{"id": "skills.repository", "level": "native",
                          "state": "satisfied", "limitations": []}],
            "limitations": [], "native_extensions": [], "labels": ["supported"],
            "diagnostics": [],
        },
    },
    {
        "id": "producer-codex-skills",
        "provider_id": "codex",
        "capability_id": "skills.repository",
        "expected": {
            "provider_id": "codex", "outcome": "ready",
            "required": [{"id": "skills.repository", "level": "native",
                          "state": "satisfied", "limitations": []}],
            "limitations": [], "native_extensions": [], "labels": ["supported"],
            "diagnostics": [],
        },
    },
)


def _require_record(value: object, fields: set[str], code: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        _raise(code)
    return value


def _require_list(value: object, code: str, *, nonempty: bool = False) -> list[object]:
    if not isinstance(value, list) or (nonempty and not value):
        _raise(code)
    return value


def _require_unique_strings(value: object, code: str, *, nonempty: bool = False) -> list[str]:
    rows = _require_list(value, code, nonempty=nonempty)
    if (not all(isinstance(item, str) and item.strip() for item in rows)
            or len(rows) != len(set(rows))):
        _raise(code)
    return rows


def _walk_no_blank_strings(value: object, code: str) -> None:
    if isinstance(value, str):
        if not value.strip():
            _raise(code)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_no_blank_strings(item, code)
    elif isinstance(value, list):
        for item in value:
            _walk_no_blank_strings(item, code)


def _walk_provider_control(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _PROVIDER_CONTROL_FIELDS:
                _raise("SKILL_CORE_PROVIDER_CONTROL")
            _walk_provider_control(item)
    elif isinstance(value, list):
        for item in value:
            _walk_provider_control(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(fragment in lowered for fragment in _PROVIDER_PATH_FRAGMENTS):
            _raise("SKILL_CORE_PROVIDER_CONTROL")


def _validate_semantic_ids(value: object) -> None:
    identities = _require_unique_strings(value, "SKILL_CORE_SEMANTIC_ID_INVALID", nonempty=True)
    forbidden_segments = {"claude", "codex", "agents", "provider", "rendered", "target", "path"}
    for identity in identities:
        segments = set(re.split(r"[.-]", identity))
        if _SEMANTIC_ID.fullmatch(identity) is None or segments & forbidden_segments:
            _raise("SKILL_CORE_SEMANTIC_ID_INVALID")


def validate_skill_core(value: object) -> None:
    if not isinstance(value, dict):
        _raise("SKILL_CORE_SCHEMA_INVALID")
    _walk_no_blank_strings(value, "SKILL_CORE_STRING_INVALID")
    _walk_provider_control(value)
    fields = set(value)
    if not _SKILL_CORE_REQUIRED_FIELDS <= fields or fields - (
            _SKILL_CORE_REQUIRED_FIELDS | _SKILL_CORE_OPTIONAL_FIELDS):
        _raise("SKILL_CORE_SCHEMA_INVALID")
    if not _v1_patch(value["contract_version"]) or not _skill_id(value["skill_id"]):
        _raise("SKILL_CORE_SCHEMA_INVALID")
    if not isinstance(value["job"], str) or not value["job"].strip():
        _raise("SKILL_CORE_SCHEMA_INVALID")
    trigger = _require_record(value["trigger"], {"positive", "negative", "explicit_only"},
                              "SKILL_CORE_TRIGGER_INVALID")
    _require_unique_strings(trigger["positive"], "SKILL_CORE_TRIGGER_INVALID", nonempty=True)
    _require_unique_strings(trigger["negative"], "SKILL_CORE_TRIGGER_INVALID", nonempty=True)
    if not isinstance(trigger["explicit_only"], bool):
        _raise("SKILL_CORE_TRIGGER_INVALID")
    for field in ("invariants", "workflow"):
        _require_unique_strings(value[field], "SKILL_CORE_SCHEMA_INVALID", nonempty=True)
    for field in ("inputs", "outputs"):
        _validate_semantic_ids(value[field])
    capability_ids: list[str] = []
    for item in _require_list(value["capabilities"], "SKILL_CORE_CAPABILITY_INVALID",
                              nonempty=True):
        row = _require_record(item, {"id", "accepted_levels", "required"},
                              "SKILL_CORE_CAPABILITY_INVALID")
        if not _stable_id(row["id"]) or not isinstance(row["required"], bool):
            _raise("SKILL_CORE_CAPABILITY_INVALID")
        accepted = _require_unique_strings(row["accepted_levels"],
                                           "SKILL_CORE_CAPABILITY_INVALID", nonempty=True)
        if (not set(accepted) <= _ACCEPTED_LEVELS
                or accepted != [level for level in _ACCEPTED_LEVEL_ORDER if level in accepted]):
            _raise("SKILL_CORE_CAPABILITY_INVALID")
        capability_ids.append(row["id"])
    if capability_ids != sorted(capability_ids) or len(capability_ids) != len(set(capability_ids)):
        _raise("SKILL_CORE_CAPABILITY_INVALID")
    resource_ids: list[str] = []
    for item in _require_list(value["resources"], "SKILL_CORE_RESOURCE_INVALID"):
        row = _require_record(item, {"id", "kind", "ref"}, "SKILL_CORE_RESOURCE_INVALID")
        if (not _stable_id(row["id"]) or row["kind"] not in {"reference", "script", "asset"}
                or not isinstance(row["ref"], str) or not row["ref"].strip()
                or row["ref"].startswith("/") or ".." in Path(row["ref"]).parts):
            _raise("SKILL_CORE_RESOURCE_INVALID")
        resource_ids.append(row["id"])
    if resource_ids != sorted(resource_ids) or len(resource_ids) != len(set(resource_ids)):
        _raise("SKILL_CORE_RESOURCE_INVALID")
    provenance = _require_record(value["provenance"],
                                 {"source_id", "sha256", "refresh_policy"},
                                 "SKILL_CORE_PROVENANCE_INVALID")
    if (not _stable_id(provenance["source_id"]) or not _digest(provenance["sha256"])
            or not isinstance(provenance["refresh_policy"], str)
            or not provenance["refresh_policy"].strip()):
        _raise("SKILL_CORE_PROVENANCE_INVALID")
    if "failure_modes" in value:
        failures = _require_list(value["failure_modes"], "SKILL_CORE_SCHEMA_INVALID", nonempty=True)
        codes: list[str] = []
        for item in failures:
            failure = _require_record(item, {"code", "condition", "outcome"},
                                      "SKILL_CORE_FAILURE_MODE_INVALID")
            if (_MACHINE_CODE.fullmatch(failure["code"])
                    if isinstance(failure["code"], str) else None) is None:
                _raise("SKILL_CORE_FAILURE_MODE_INVALID")
            if not all(isinstance(failure[field], str) and failure[field].strip()
                       for field in ("condition", "outcome")):
                _raise("SKILL_CORE_FAILURE_MODE_INVALID")
            codes.append(failure["code"])
        if len(codes) != len(set(codes)):
            _raise("SKILL_CORE_FAILURE_MODE_INVALID")


def _validate_requirement(value: object, code: str) -> dict[str, object]:
    row = _require_record(value, {"id", "accepted_levels"}, code)
    if not _stable_id(row["id"]):
        _raise(code)
    accepted = _require_unique_strings(row["accepted_levels"], code, nonempty=True)
    if (not set(accepted) <= _ACCEPTED_LEVELS
            or accepted != [level for level in _ACCEPTED_LEVEL_ORDER if level in accepted]):
        _raise(code)
    return row


def _provider_pattern(matrix: dict[str, object]) -> re.Pattern[str]:
    registration = _mapping(matrix.get("adapter_registration"), "OWNERSHIP_SCHEMA_INVALID")
    pattern = registration.get("provider_id_pattern")
    if pattern != r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$":
        _raise("OWNERSHIP_SCHEMA_INVALID")
    return re.compile(pattern)


def _validate_evidence(value: object, code: str) -> None:
    canonical: list[str] = []
    for item in _require_list(value, code, nonempty=True):
        row = _require_record(item, _EVIDENCE_FIELDS, code)
        if (not all(isinstance(row[field], str) and row[field].strip()
                    for field in ("claim", "scope", "source"))
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", row["verified_at"]) is None):
            _raise(code)
        canonical.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
    if len(canonical) != len(set(canonical)):
        _raise(code)


def _valid_json_binding(value: object) -> bool:
    if not isinstance(value, dict) or not value or not all(
            isinstance(key, str) and key.strip() for key in value):
        return False

    def valid(item: object) -> bool:
        if item is None or isinstance(item, (str, bool, int)):
            return not isinstance(item, str) or bool(item.strip())
        if isinstance(item, float):
            return math.isfinite(item)
        if isinstance(item, list):
            return all(valid(child) for child in item)
        if isinstance(item, dict):
            return all(isinstance(key, str) and key.strip() and valid(child)
                       for key, child in item.items())
        return False

    return all(valid(item) for item in value.values())


def _validate_capability_manifest(value: object, provider_id_pattern: re.Pattern[str]) -> tuple[
        list[str], dict[str, dict[str, object]], dict[str, str]]:
    _walk_no_blank_strings(value, "NEG_MANIFEST_INVALID")
    manifest = _require_record(value,
                               {"contract_version", "catalog_version", "providers",
                                "capabilities", "native_extensions"}, "NEG_MANIFEST_INVALID")
    if not _v1_patch(manifest["contract_version"]) or not _v1_patch(manifest["catalog_version"]):
        _raise("NEG_VERSION_UNSUPPORTED")
    provider_ids: list[str] = []
    for provider in _require_list(manifest["providers"], "NEG_MANIFEST_INVALID", nonempty=True):
        row = _require_record(provider, {"id", "display_name"}, "NEG_MANIFEST_INVALID")
        if (not isinstance(row["id"], str) or provider_id_pattern.fullmatch(row["id"]) is None
                or not isinstance(row["display_name"], str) or not row["display_name"].strip()):
            _raise("NEG_MANIFEST_INVALID")
        provider_ids.append(row["id"])
    if provider_ids != sorted(provider_ids) or len(provider_ids) != len(set(provider_ids)):
        _raise("NEG_MANIFEST_INVALID")
    capabilities: dict[str, dict[str, object]] = {}
    for capability in _require_list(manifest["capabilities"], "NEG_MANIFEST_INVALID",
                                    nonempty=True):
        row = _require_record(capability, {"id", "intent", "support"}, "NEG_MANIFEST_INVALID")
        if (not _stable_id(row["id"]) or not isinstance(row["intent"], str)
                or not row["intent"].strip()):
            _raise("NEG_MANIFEST_INVALID")
        support = _mapping(row["support"], "NEG_MANIFEST_INVALID")
        if set(support) != set(provider_ids):
            _raise("OWNERSHIP_MISSING_PROVIDER_ROW")
        for provider_id, support_value in support.items():
            support_row = _mapping(support_value, "NEG_MANIFEST_INVALID")
            level = support_row.get("level")
            expected = {"level", "limitations", "evidence", "diagnostic"}
            if level == "native":
                expected.add("binding")
            elif level == "adapted":
                expected.add("adapter_id")
            elif level != "unsupported":
                _raise("NEG_MANIFEST_INVALID")
            allowed = expected | ({"binding"} if level == "adapted" else set())
            if set(support_row) != expected and set(support_row) != allowed:
                _raise("NEG_MANIFEST_INVALID")
            if (not isinstance(support_row["diagnostic"], str)
                    or not support_row["diagnostic"].strip()
                    or ("binding" in support_row and not _valid_json_binding(
                        support_row["binding"]))
                    or ("adapter_id" in support_row and not _stable_id(support_row["adapter_id"]))):
                _raise("NEG_MANIFEST_INVALID")
            limitations = _require_unique_strings(support_row["limitations"],
                                                  "NEG_MANIFEST_INVALID")
            _validate_evidence(support_row["evidence"], "NEG_MANIFEST_INVALID")
            if level == "adapted" and not limitations:
                _raise("NEG_MANIFEST_INVALID")
            if level == "unsupported" and not any(
                    token in support_row["diagnostic"].lower()
                    for token in ("unsupported", "fail closed", "fail-closed", "refus",
                                  "exclude", "disabled")):
                _raise("NEG_MANIFEST_INVALID")
        if row["id"] in capabilities:
            _raise("NEG_MANIFEST_INVALID")
        capabilities[row["id"]] = support
    if list(capabilities) != sorted(capabilities):
        _raise("NEG_MANIFEST_INVALID")
    extension_owners: dict[str, str] = {}
    for extension in _require_list(manifest["native_extensions"], "NEG_MANIFEST_INVALID"):
        row = _require_record(extension,
                              {"id", "provider_id", "intent", "binding", "evidence", "diagnostic"},
                              "NEG_MANIFEST_INVALID")
        if (not _stable_id(row["id"]) or row["provider_id"] not in provider_ids
                or not row["id"].startswith(row["provider_id"] + ".")
                or not isinstance(row["intent"], str) or not row["intent"].strip()
                or not _valid_json_binding(row["binding"])
                or not isinstance(row["diagnostic"], str) or not row["diagnostic"].strip()):
            _raise("NEG_MANIFEST_INVALID")
        _validate_evidence(row["evidence"], "NEG_MANIFEST_INVALID")
        if row["id"] in extension_owners:
            _raise("NEG_MANIFEST_INVALID")
        extension_owners[row["id"]] = row["provider_id"]
    if list(extension_owners) != sorted(extension_owners):
        _raise("NEG_MANIFEST_INVALID")
    return provider_ids, capabilities, extension_owners


def _validate_negotiation_input(case: object, provider_id_pattern: re.Pattern[str]) -> tuple[
        dict[str, object], dict[str, object], dict[str, object], dict[str, dict[str, object]], dict[str, str]]:
    row = _require_record(case, {"id", "provider_id", "manifest", "desired", "descriptor", "expected"},
                          "NEG_SCHEMA_INVALID")
    if not _stable_id(row["id"]):
        _raise("NEG_SCHEMA_INVALID")
    manifest = _mapping(row["manifest"], "NEG_MANIFEST_INVALID")
    provider_ids, capabilities, extension_owners = _validate_capability_manifest(
        manifest, provider_id_pattern)
    selection_map, _, catalog_version = _validate_desired(row["desired"])
    provider_id = row["provider_id"]
    if (not isinstance(provider_id, str) or provider_id_pattern.fullmatch(provider_id) is None
            or provider_id not in provider_ids or provider_id not in selection_map
            or catalog_version != manifest["catalog_version"]):
        _raise("NEG_SCHEMA_INVALID")
    selection = selection_map[provider_id]
    descriptor = _require_record(row["descriptor"],
                                 {"provider_id", "adapter_id", "required_capabilities",
                                  "optional_capabilities", "native_extensions"},
                                 "NEG_SCHEMA_INVALID")
    if (not isinstance(descriptor["provider_id"], str)
            or provider_id_pattern.fullmatch(descriptor["provider_id"]) is None
            or not _stable_id(descriptor["adapter_id"])):
        _raise("NEG_SCHEMA_INVALID")
    descriptor_requirement_ids: list[str] = []
    for field in ("required_capabilities", "optional_capabilities"):
        requirements = [_validate_requirement(item, "NEG_SCHEMA_INVALID")
                        for item in _require_list(descriptor[field], "NEG_SCHEMA_INVALID")]
        ids = [item["id"] for item in requirements]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            _raise("NEG_SCHEMA_INVALID")
        descriptor_requirement_ids.extend(ids)
    if len(descriptor_requirement_ids) != len(set(descriptor_requirement_ids)):
        _raise("NEG_SCHEMA_INVALID")
    extensions = _require_unique_strings(descriptor["native_extensions"], "NEG_SCHEMA_INVALID")
    if not all(_stable_id(identity) for identity in extensions):
        _raise("NEG_SCHEMA_INVALID")
    return manifest, selection, descriptor, capabilities, extension_owners


def negotiate(case: object, provider_id_pattern: re.Pattern[str]) -> dict[str, object]:
    _, selection, descriptor, capabilities, extension_owners = _validate_negotiation_input(
        case, provider_id_pattern)
    provider_id = case["provider_id"]
    diagnostics: list[dict[str, str]] = []
    if not selection["enabled"]:
        diagnostics.append({"code": "NEG_PROVIDER_DISABLED", "subject_id": provider_id})
    if descriptor["provider_id"] != provider_id:
        diagnostics.append({"code": "NEG_PROVIDER_MISMATCH", "subject_id": descriptor["provider_id"]})
    support_by_id = {identity: support.get(provider_id) for identity, support in capabilities.items()}
    decisions = selection["capabilities"]
    required = []
    degraded = False
    for requirement in descriptor["required_capabilities"]:
        identity = requirement["id"]
        support = support_by_id.get(identity)
        if decisions.get(identity) is False:
            diagnostics.append({"code": "NEG_REQUIRED_DENIED", "subject_id": identity})
        elif support is None:
            diagnostics.append({"code": "NEG_REQUIRED_MISSING", "subject_id": identity})
        elif support["level"] == "unsupported":
            diagnostics.append({"code": "NEG_REQUIRED_UNSUPPORTED", "subject_id": identity})
        elif support["level"] not in requirement["accepted_levels"]:
            diagnostics.append({"code": "NEG_REQUIRED_LEVEL_REJECTED", "subject_id": identity})
        else:
            required.append({"id": identity, "level": support["level"], "state": "satisfied",
                             "limitations": list(support["limitations"])})
            degraded = degraded or support["level"] == "adapted" or bool(support["limitations"])
    limitations = []
    for requirement in descriptor["optional_capabilities"]:
        identity = requirement["id"]
        support = support_by_id.get(identity)
        if decisions.get(identity) is False:
            limitations.append({"id": identity, "level": (support or {}).get("level", "unknown"),
                                "state": "denied",
                                "limitations": list((support or {}).get("limitations", []))})
        elif support is None:
            limitations.append({"id": identity, "level": "unknown", "state": "missing",
                                "limitations": []})
        elif support["level"] == "unsupported":
            limitations.append({"id": identity, "level": "unsupported", "state": "unsupported",
                                "limitations": list(support["limitations"])})
        elif support["level"] not in requirement["accepted_levels"]:
            limitations.append({"id": identity, "level": support["level"],
                                "state": "level-rejected",
                                "limitations": list(support["limitations"])})
        else:
            degraded = degraded or support["level"] == "adapted" or bool(support["limitations"])
            if support["limitations"]:
                limitations.append({"id": identity, "level": support["level"], "state": "limited",
                                    "limitations": list(support["limitations"])})
    enabled_extensions = []
    for identity in descriptor["native_extensions"]:
        if not selection["native_extensions"].get(identity, False):
            continue
        if (not identity.startswith(provider_id + ".")
                or extension_owners.get(identity) != provider_id):
            diagnostics.append({"code": "NEG_NATIVE_EXTENSION_INVALID", "subject_id": identity})
        else:
            enabled_extensions.append(identity)
    diagnostics.sort(key=lambda item: (_FAILURE_ORDER[item["code"]], item["subject_id"]))
    if diagnostics:
        return {"provider_id": provider_id, "outcome": "blocked", "required": [], "limitations": [],
                "native_extensions": [], "labels": [], "diagnostics": diagnostics}
    labels = ["supported"]
    if degraded or limitations:
        labels.append("degraded")
    if enabled_extensions:
        labels.append("exclusive")
    return {"provider_id": provider_id, "outcome": "ready", "required": required, "limitations": limitations,
            "native_extensions": enabled_extensions, "labels": labels, "diagnostics": []}


def _producer_desired(schema_positive: object) -> dict[str, object]:
    cases = _case_map(schema_positive, "cases", "NEG_PRODUCER_INPUT_INVALID")
    case = cases.get("mixed-freshness")
    if case is None:
        _raise("NEG_PRODUCER_INPUT_INVALID")
    envelope = case.get("envelope")
    validate_envelope(envelope)
    result = _mapping(_mapping(envelope, "NEG_PRODUCER_INPUT_INVALID").get("result"),
                      "NEG_PRODUCER_INPUT_INVALID")
    return _mapping(result.get("desired"), "NEG_PRODUCER_INPUT_INVALID")


def _run_producer_probes(manifest: dict[str, object], desired: dict[str, object],
                         provider_id_pattern: re.Pattern[str]) -> None:
    _validate_desired(desired)
    for probe in _PRODUCER_PROBES:
        case = _producer_probe_case(probe, manifest, desired)
        actual = negotiate(case, provider_id_pattern)
        if actual != probe["expected"]:
            raise ValueError(f"{probe['id']}: producer negotiation mismatch: {actual!r}")


def _producer_probe_case(probe: dict[str, object], manifest: dict[str, object],
                         desired: dict[str, object]) -> dict[str, object]:
    capability_id = probe["capability_id"]
    return {
        "id": probe["id"],
        "provider_id": probe["provider_id"],
        "manifest": manifest,
        "desired": desired,
        "descriptor": {
            "provider_id": probe["provider_id"],
            "adapter_id": f"producer.{probe['provider_id']}.{capability_id}",
            "required_capabilities": [{
                "id": capability_id,
                "accepted_levels": ["adapted", "native"],
            }],
            "optional_capabilities": [],
            "native_extensions": [],
        },
        "expected": probe["expected"],
    }


def _validate_aggregate_case(value: object) -> None:
    row = _require_record(value,
                          {"id", "selected_provider_ids", "provider_outcomes", "expected"},
                          "OWNERSHIP_AGGREGATE_INVALID")
    if not _stable_id(row["id"]):
        _raise("OWNERSHIP_AGGREGATE_INVALID")
    selected = _require_unique_strings(row["selected_provider_ids"],
                                       "OWNERSHIP_AGGREGATE_INVALID")
    if (selected != sorted(selected)
            or not all(_provider_id(provider_id) for provider_id in selected)):
        _raise("OWNERSHIP_AGGREGATE_INVALID")
    outcomes = _mapping(row["provider_outcomes"], "OWNERSHIP_AGGREGATE_INVALID")
    if set(outcomes) != set(selected):
        _raise("OWNERSHIP_MISSING_PROVIDER_ROW")
    if not all(_provider_id(provider_id) for provider_id in outcomes):
        _raise("OWNERSHIP_AGGREGATE_INVALID")
    if not all(outcome in {"ready", "blocked"} for outcome in outcomes.values()):
        _raise("OWNERSHIP_AGGREGATE_INVALID")
    if not selected:
        expected = "no-providers-selected"
    else:
        expected = "blocked" if "blocked" in outcomes.values() else "ready"
    if row["expected"] not in {"ready", "blocked", "no-providers-selected"}:
        _raise("OWNERSHIP_AGGREGATE_INVALID")
    if row["expected"] != expected:
        _raise("OWNERSHIP_PARTIAL_PROVIDER_MASKING")


def _matrix_inventory(value: object) -> tuple[dict[str, object], dict[str, object]]:
    matrix = _require_record(value,
                             {"schema_version", "contract_version", "families", "rows",
                              "adapter_registration"}, "OWNERSHIP_SCHEMA_INVALID")
    if matrix["schema_version"] != 1 or not _v1_patch(matrix["contract_version"]):
        _raise("OWNERSHIP_SCHEMA_INVALID")
    families = _require_unique_strings(matrix["families"], "OWNERSHIP_SCHEMA_INVALID")
    family_set = set(families)
    missing_families = sorted(_MATRIX_FAMILIES - family_set)
    extra_families = sorted(family_set - _MATRIX_FAMILIES)
    rows = _require_list(matrix["rows"], "OWNERSHIP_SCHEMA_INVALID")
    carrier_ids = [row.get("carrier_id") for row in rows if isinstance(row, dict)]
    missing = sorted(_MATRIX_CARRIERS - set(carrier_ids))
    extra = sorted(set(carrier_ids) - _MATRIX_CARRIERS)
    duplicates = sorted(identity for identity in set(carrier_ids) if carrier_ids.count(identity) > 1)
    report = {"missing": missing + missing_families, "extra": extra + extra_families,
              "duplicate_owners": duplicates}
    return matrix, report


def validate_matrix(value: object, provider_ids: tuple[str, ...] = ()) -> dict[str, object]:
    matrix, report = _matrix_inventory(value)
    if report["missing"]:
        _raise("OWNERSHIP_CARRIER_MISSING")
    if report["extra"]:
        _raise("OWNERSHIP_CARRIER_EXTRA")
    if report["duplicate_owners"]:
        _raise("OWNERSHIP_DUPLICATE_OWNER")
    for value_row in matrix["rows"]:
        row = _require_record(value_row, _MATRIX_ROW_FIELDS, "OWNERSHIP_SCHEMA_INVALID")
        if isinstance(row["owner"], list) and len(row["owner"]) != 1:
            _raise("OWNERSHIP_DUPLICATE_OWNER")
        if not isinstance(row["owner"], str) or not row["owner"]:
            _raise("OWNERSHIP_UNOWNED_CARRIER")
        if row["family"] not in _MATRIX_FAMILIES:
            _raise("OWNERSHIP_SCHEMA_INVALID")
        for field in ("read", "write", "derived_from", "forbidden_use"):
            _require_unique_strings(row[field], "OWNERSHIP_SCHEMA_INVALID")
        all_values = [row["owner"], *row["read"], *row["write"], *row["derived_from"]]
        if any("other_provider" in item or "other-provider:" in item for item in all_values):
            _raise("OWNERSHIP_CROSS_PROVIDER")
        if "{provider_id}" in row["carrier_id"] and any(
                provider_id in item and "{provider_id}" not in item
                for item in all_values for provider_id in provider_ids):
            _raise("OWNERSHIP_CROSS_PROVIDER")
        if row["family"] == "canonical-source" and any(
                item.startswith("provider.target") or item.startswith("provider.projection")
                for item in row["derived_from"]):
            _raise("OWNERSHIP_OUTPUT_AS_SOURCE")
        expected = _EXPECTED_MATRIX_ROWS[row["carrier_id"]]
        actual = (row["family"], row["owner"], tuple(row["read"]), tuple(row["write"]),
                  tuple(row["derived_from"]), tuple(row["forbidden_use"]))
        if actual != expected:
            _raise("OWNERSHIP_ROW_MISMATCH")
    registration = _require_record(matrix["adapter_registration"],
                                   {"provider_id_pattern", "provider_enum", "required_seams",
                                    "semantic_source", "provider_output_as_input"},
                                   "OWNERSHIP_SCHEMA_INVALID")
    if registration["provider_enum"] is not None:
        _raise("OWNERSHIP_PROVIDER_ENUM_CEILING")
    if registration["provider_id_pattern"] != r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$":
        _raise("OWNERSHIP_SCHEMA_INVALID")
    if registration["required_seams"] != list(_REQUIRED_SEAMS):
        _raise("OWNERSHIP_SCHEMA_INVALID")
    if registration["semantic_source"] != "canonical.skill-core":
        _raise("OWNERSHIP_OUTPUT_AS_SOURCE")
    if registration["provider_output_as_input"] is not False:
        _raise("OWNERSHIP_OUTPUT_AS_SOURCE")
    return report


def _contains_replacement_marker(value: object) -> bool:
    if isinstance(value, dict):
        return (any(str(key).lower() in _ADAPTER_REPLACEMENT_FIELDS for key in value)
                or any(_contains_replacement_marker(item) for item in value.values()))
    if isinstance(value, list):
        return any(_contains_replacement_marker(item) for item in value)
    return False


def _validate_adapter_seam(name: str, value: object) -> None:
    row = _require_record(value, _SEAM_FIELDS[name], "ADAPTER_SEAM_INVALID")
    if name == "renderer":
        roots = _require_unique_strings(row["target_roots"], "ADAPTER_SEAM_INVALID", nonempty=True)
        if (not _stable_id(row["id"])
                or not isinstance(row["version"], str)
                or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", row["version"]) is None
                or any(not path.strip() or path.startswith("/") or ".." in Path(path).parts
                       for path in roots)):
            _raise("ADAPTER_SEAM_INVALID")
        return
    if name == "invocation":
        if (not isinstance(row["mode"], str) or not row["mode"].strip()
                or not isinstance(row["unsupported"], bool)):
            _raise("ADAPTER_SEAM_INVALID")
        return
    if not all(isinstance(row[field], str) and row[field].strip() for field in row):
        _raise("ADAPTER_SEAM_INVALID")
    if name == "measurement" and (not isinstance(row["version"], str) or re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+", row["version"]) is None):
        _raise("ADAPTER_SEAM_INVALID")


def _validate_adapter_descriptor(value: object, provider_id: str,
                                 provider_id_pattern: re.Pattern[str],
                                 skill_contracts: dict[str, dict[str, tuple[bool, tuple[str, ...]]]],
                                 capability_ids: set[str]) -> None:
    if not isinstance(value, dict):
        _raise("ADAPTER_SCHEMA_INVALID")
    if _contains_replacement_marker(value):
        _raise("ADAPTER_SEMANTIC_REPLACEMENT")
    fields = {
        "contract_version", "adapter_id", "adapter_version", "provider_id", "skill_id",
        "required_capabilities", "optional_capabilities", "native_extensions", *_REQUIRED_SEAMS,
        "status_namespace",
    }
    row = _require_record(value, fields, "ADAPTER_SCHEMA_INVALID")
    if not _skill_id(row["skill_id"]):
        _raise("ADAPTER_SCHEMA_INVALID")
    valid_skill = row["skill_id"] in skill_contracts
    if (provider_id_pattern.fullmatch(provider_id) is None
            or not _v1_patch(row["contract_version"]) or not _stable_id(row["adapter_id"])
            or not isinstance(row["adapter_version"], str)
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", row["adapter_version"]) is None
            or row["provider_id"] != provider_id or not valid_skill
            or row["status_namespace"] != f"provider:{provider_id}"):
        if isinstance(row.get("skill_id"), str) and not valid_skill:
            _raise("ADAPTER_SKILL_UNKNOWN")
        _raise("ADAPTER_SCHEMA_INVALID")
    descriptor_requirement_ids: list[str] = []
    actual_contract: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for field in ("required_capabilities", "optional_capabilities"):
        requirements = [_validate_requirement(item, "ADAPTER_SCHEMA_INVALID")
                        for item in _require_list(row[field], "ADAPTER_SCHEMA_INVALID")]
        ids = [item["id"] for item in requirements]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            _raise("ADAPTER_SCHEMA_INVALID")
        if not set(ids) <= capability_ids:
            _raise("ADAPTER_CAPABILITY_UNKNOWN")
        descriptor_requirement_ids.extend(ids)
        actual_contract.update({item["id"]: (field == "required_capabilities",
                                              tuple(item["accepted_levels"]))
                                for item in requirements})
    if len(descriptor_requirement_ids) != len(set(descriptor_requirement_ids)):
        _raise("ADAPTER_SCHEMA_INVALID")
    if actual_contract != skill_contracts[row["skill_id"]]:
        _raise("ADAPTER_SKILL_CONTRACT_MISMATCH")
    extensions = _require_unique_strings(row["native_extensions"], "ADAPTER_SCHEMA_INVALID")
    if any(not _stable_id(identity) or not identity.startswith(provider_id + ".")
           for identity in extensions):
        _raise("ADAPTER_SCHEMA_INVALID")
    for seam in _REQUIRED_SEAMS:
        _validate_adapter_seam(seam, row[seam])


def _validate_third_provider(value: object, provider_id_pattern: re.Pattern[str],
                             skill_contracts: dict[str, dict[str, tuple[bool, tuple[str, ...]]]],
                             real_capability_ids: set[str]) -> None:
    row = _require_record(value,
                          {"contract_version", "provider", "manifest", "descriptor", "registration"},
                          "ADAPTER_SCHEMA_INVALID")
    if not _v1_patch(row["contract_version"]):
        _raise("ADAPTER_SCHEMA_INVALID")
    provider = _require_record(row["provider"], {"id", "display_name"}, "ADAPTER_SCHEMA_INVALID")
    provider_id = provider["id"]
    if (not isinstance(provider_id, str) or provider_id_pattern.fullmatch(provider_id) is None
            or provider_id in {"claude-code", "codex"}
            or not isinstance(provider["display_name"], str)
            or not provider["display_name"].strip()):
        _raise("ADAPTER_PROVIDER_ID_INVALID")
    synthetic_provider_ids, synthetic_capabilities, extension_owners = (
        _validate_capability_manifest(row["manifest"], provider_id_pattern))
    if provider_id not in synthetic_provider_ids:
        _raise("ADAPTER_PROVIDER_MANIFEST_MISMATCH")
    _validate_adapter_descriptor(row["descriptor"], provider_id, provider_id_pattern,
                                 skill_contracts, set(synthetic_capabilities))
    for extension_id in row["descriptor"]["native_extensions"]:
        if extension_owners.get(extension_id) != provider_id:
            _raise("ADAPTER_EXTENSION_MANIFEST_MISMATCH")
    registration = _require_record(row["registration"], {"additions"}, "ADAPTER_SCHEMA_INVALID")
    additions = _require_list(registration["additions"], "ADAPTER_SCHEMA_INVALID", nonempty=True)
    kinds: list[str] = []
    normalized_paths: list[str] = []
    for addition in additions:
        item = _require_record(addition, {"kind", "path"}, "ADAPTER_SCHEMA_INVALID")
        if item["kind"] not in {"descriptor", *_REQUIRED_SEAMS}:
            _raise("ADAPTER_SCHEMA_INVALID")
        expected_prefix = f"adapters/{provider_id}/"
        path = item["path"]
        if (not isinstance(path, str) or not path.strip() or "\\" in path
                or path.startswith("/") or "//" in path or "/./" in path
                or path.endswith("/.") or ".." in path.split("/")
                or posixpath.normpath(path) != path
                or not item["path"].startswith(expected_prefix)
                or not path[len(expected_prefix):]):
            _raise("OWNERSHIP_CROSS_PROVIDER")
        kinds.append(item["kind"])
        normalized_paths.append(posixpath.normpath(path))
    if sorted(kinds) != sorted(["descriptor", *_REQUIRED_SEAMS]) or len(kinds) != len(set(kinds)):
        _raise("ADAPTER_SCHEMA_INVALID")
    if len(normalized_paths) != len(set(normalized_paths)):
        _raise("ADAPTER_PATH_COLLISION")


def _verify_ownership_contract_inventory(contract: Path, skill_core: Path,
                                         skill_adapters: Path) -> None:
    inventories = {
        contract: {"## Capability negotiation", "## Provider-qualified support presentation",
                   "## Ownership and provider isolation", "NEG_REQUIRED_UNSUPPORTED",
                   "supported", "degraded", "exclusive"},
        skill_core: {"## Exact record", "## Provider neutrality", "## Immutability and adapters",
                     "failure_modes", "explicit_only"},
        skill_adapters: {"## Registration record", "## Additive semantic rule",
                         "## Capability negotiation", "## Provider-qualified presentation",
                         "## Third-provider conformance and versioning"},
    }
    for path, required in inventories.items():
        text = path.read_text(encoding="utf-8")
        missing = sorted(literal for literal in required if literal not in text)
        if missing:
            raise ValueError(f"{path}: contract inventory missing: {', '.join(missing)}")


def _validate_single_mutation_cases(value: object, code: str) -> tuple[str, list[dict[str, object]]]:
    row = _require_record(value, {"contract_version", "base", "cases"}, code)
    if not _v1_patch(row["contract_version"]) or not _stable_id(row["base"]):
        _raise(code)
    cases = _require_list(row["cases"], code, nonempty=True)
    ids = []
    for item in cases:
        case = _require_record(item, {"id", "mutation", "expected_code"}, code)
        mutation = _mapping(case["mutation"], code)
        expected_keys = {"op", "path"} if mutation.get("op") == "remove" else {"op", "path", "value"}
        if (set(mutation) != expected_keys or mutation.get("op") not in {"add", "remove", "replace"}
                or not _stable_id(case["id"]) or not isinstance(case["expected_code"], str)):
            _raise(code)
        ids.append(case["id"])
    if len(ids) != len(set(ids)):
        _raise(code)
    return row["base"], cases


def _case_map(value: object, field: str, code: str) -> dict[str, dict[str, object]]:
    rows = _mapping(value, code).get(field)
    cases = _require_list(rows, code, nonempty=True)
    result = {}
    for item in cases:
        if not isinstance(item, dict) or not _stable_id(item.get("id")) or item["id"] in result:
            _raise(code)
        result[item["id"]] = item
    return result


def _validate_skill_core_positive(value: object) -> tuple[
        dict[str, dict[str, object]], dict[str, dict[str, tuple[bool, tuple[str, ...]]]]]:
    envelope = _require_record(value, {"contract_version", "cases"},
                               "SKILL_CORE_SCHEMA_INVALID")
    if not _v1_patch(envelope["contract_version"]):
        _raise("SKILL_CORE_VERSION_UNSUPPORTED")
    cases = _case_map(envelope, "cases", "SKILL_CORE_SCHEMA_INVALID")
    skill_ids: list[str] = []
    cores: list[dict[str, object]] = []
    for case in cases.values():
        row = _require_record(case, {"id", "skill_core"}, "SKILL_CORE_SCHEMA_INVALID")
        validate_skill_core(row["skill_core"])
        skill_id = row["skill_core"]["skill_id"]
        skill_ids.append(skill_id)
        cores.append(row["skill_core"])
    if len(skill_ids) != len(set(skill_ids)):
        _raise("SKILL_CORE_DUPLICATE_ID")
    contracts = {
        core["skill_id"]: {
            item["id"]: (item["required"], tuple(item["accepted_levels"]))
            for item in core["capabilities"]
        }
        for core in cores
    }
    return cases, contracts


def _exercise_negative_fixtures(fixtures: Path, provider_id_pattern: re.Pattern[str]) -> None:
    negotiation_positive = _load_json(fixtures / "negotiation-positive.json")
    negotiation_cases = _case_map(negotiation_positive, "cases", "NEG_SCHEMA_INVALID")
    base_id, negative_cases = _validate_single_mutation_cases(
        _load_json(fixtures / "negotiation-negative.json"), "NEG_SCHEMA_INVALID")
    if base_id not in negotiation_cases:
        _raise("NEG_SCHEMA_INVALID")
    for negative in negative_cases:
        mutated = _apply_mutation(negotiation_cases[base_id], negative["mutation"])
        try:
            result = negotiate(mutated, provider_id_pattern)
        except ContractError as error:
            actual = [error.code]
        else:
            actual = [item["code"] for item in result["diagnostics"]]
        if actual != [negative["expected_code"]]:
            raise ValueError(f"{negative['id']}: expected {negative['expected_code']}, got {actual}")

    skill_positive = _load_json(fixtures / "skill-core-positive.json")
    skill_cases = _case_map(skill_positive, "cases", "SKILL_CORE_SCHEMA_INVALID")
    skill_base_id, skill_negative = _validate_single_mutation_cases(
        _load_json(fixtures / "skill-core-negative.json"), "SKILL_CORE_SCHEMA_INVALID")
    if skill_base_id not in skill_cases:
        _raise("SKILL_CORE_SCHEMA_INVALID")
    skill_base = skill_cases[skill_base_id]["skill_core"]
    for negative in skill_negative:
        mutated = _apply_mutation(skill_base, negative["mutation"])
        try:
            validate_skill_core(mutated)
        except ContractError as error:
            if error.code != negative["expected_code"]:
                raise ValueError(
                    f"{negative['id']}: expected {negative['expected_code']}, got {error.code}") from error
        else:
            raise ValueError(f"{negative['id']}: invalid fixture was accepted")


def render_matrix_markdown(value: object) -> str:
    validate_matrix(value)
    lines = [
        "# Provider ownership and capability matrix",
        "",
        "> Generated by `p1-provider-control-plane-check.py`; edit the JSON source, not this file.",
        "",
        f"**Contract version:** {value['contract_version']}",
        "",
        "**Declared carrier families:** " + ", ".join(f"`{item}`" for item in value["families"]),
        "",
        "| Carrier | Family | Owner | Read | Write | Derived from | Forbidden use |",
        "|:--|:--|:--|:--|:--|:--|:--|",
    ]
    for row in sorted(value["rows"], key=lambda item: item["carrier_id"]):
        cells = [
            row["carrier_id"], row["family"], row["owner"],
            ", ".join(row["read"]) or "—", ", ".join(row["write"]) or "—",
            ", ".join(row["derived_from"]) or "—", ", ".join(row["forbidden_use"]) or "—",
        ]
        lines.append("| " + " | ".join(f"`{cell}`" if cell != "—" else cell for cell in cells) + " |")
    registration = value["adapter_registration"]
    lines += [
        "",
        "## Adapter registration",
        "",
        f"Provider identity pattern: `{registration['provider_id_pattern']}`; provider enum: `null`.",
        "",
        "Required seams: " + ", ".join(f"`{item}`" for item in registration["required_seams"]) + ".",
        "",
        "Semantic source: `canonical.skill-core`; provider output as input: `false`.",
        "",
    ]
    return "\n".join(lines)


def _run_ownership(contract: Path, skill_core: Path, skill_adapters: Path,
                   matrix_path: Path, fixtures: Path, capability_manifest: Path) -> dict[str, object]:
    observed_paths = tuple(sorted({
        contract, skill_core, skill_adapters, matrix_path, matrix_path.with_suffix(".md"),
        capability_manifest, *fixtures.glob("*.json"),
    }, key=lambda path: str(path)))
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in observed_paths}
    _verify_ownership_contract_inventory(contract, skill_core, skill_adapters)
    matrix = _load_json(matrix_path)
    provider_id_pattern = _provider_pattern(matrix)
    current_manifest = _load_json(capability_manifest)
    provider_ids, capabilities, _ = _validate_capability_manifest(current_manifest,
                                                                   provider_id_pattern)
    producer_desired = _producer_desired(_load_json(fixtures / "schema-positive.json"))
    _run_producer_probes(current_manifest, producer_desired, provider_id_pattern)
    report = validate_matrix(matrix, tuple(provider_ids))
    positive = _load_json(fixtures / "negotiation-positive.json")
    if positive.get("contract_version") != "1.0.0":
        _raise("NEG_VERSION_UNSUPPORTED")
    for case in _case_map(positive, "cases", "NEG_SCHEMA_INVALID").values():
        expected = case["expected"]
        actual = negotiate(case, provider_id_pattern)
        if actual != expected:
            raise ValueError(f"{case['id']}: negotiation mismatch: {actual!r}")
    for aggregate in _require_list(positive.get("aggregate_cases"),
                                   "OWNERSHIP_AGGREGATE_INVALID", nonempty=True):
        _validate_aggregate_case(aggregate)
    skill_positive = _load_json(fixtures / "skill-core-positive.json")
    _, skill_contracts = _validate_skill_core_positive(skill_positive)
    _exercise_negative_fixtures(fixtures, provider_id_pattern)
    _validate_third_provider(_load_json(fixtures / "third-provider.json"), provider_id_pattern,
                             skill_contracts, set(capabilities))
    generated = render_matrix_markdown(matrix)
    markdown_path = matrix_path.with_suffix(".md")
    if markdown_path.read_text(encoding="utf-8") != generated:
        _raise("OWNERSHIP_MARKDOWN_DRIFT")
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in observed_paths}
    if before != after:
        _raise("OWNERSHIP_WRITE_FORBIDDEN")
    return {**report, "capability_manifest": "validated", "producer_probes": len(_PRODUCER_PROBES),
            "markdown": "byte-identical", "no_write": "verified"}


def _expect_code(callable_, expected: str) -> None:
    try:
        callable_()
    except ContractError as error:
        if error.code != expected:
            raise ValueError(f"expected {expected}, got {error.code}") from error
    else:
        raise ValueError(f"expected refusal {expected}")


def _self_test_ownership(contract: Path, skill_core: Path, skill_adapters: Path,
                         matrix_path: Path, fixtures: Path, capability_manifest: Path) -> None:
    _run_ownership(contract, skill_core, skill_adapters, matrix_path, fixtures, capability_manifest)
    matrix = _load_json(matrix_path)
    pattern = _provider_pattern(matrix)
    current_manifest = _load_json(capability_manifest)
    provider_ids, capabilities, _ = _validate_capability_manifest(current_manifest, pattern)
    skill_positive = _load_json(fixtures / "skill-core-positive.json")
    _, skill_contracts = _validate_skill_core_positive(skill_positive)

    duplicate = copy.deepcopy(matrix)
    duplicate["rows"][0]["owner"] = ["owner.one", "owner.two"]
    _expect_code(lambda: validate_matrix(duplicate, tuple(provider_ids)), "OWNERSHIP_DUPLICATE_OWNER")

    unowned = copy.deepcopy(matrix)
    unowned["rows"][0]["owner"] = ""
    _expect_code(lambda: validate_matrix(unowned, tuple(provider_ids)), "OWNERSHIP_UNOWNED_CARRIER")

    enum_ceiling = copy.deepcopy(matrix)
    enum_ceiling["adapter_registration"]["provider_enum"] = ["claude-code", "codex"]
    _expect_code(lambda: validate_matrix(enum_ceiling, tuple(provider_ids)), "OWNERSHIP_PROVIDER_ENUM_CEILING")

    cross_provider = copy.deepcopy(matrix)
    target_row = next(row for row in cross_provider["rows"]
                      if row["carrier_id"] == "provider.target:{provider_id}")
    target_row["read"].append("adapter:codex")
    _expect_code(lambda: validate_matrix(cross_provider, tuple(provider_ids)), "OWNERSHIP_CROSS_PROVIDER")

    output_source = copy.deepcopy(matrix)
    core_row = next(row for row in output_source["rows"]
                    if row["carrier_id"] == "canonical.skill-core")
    core_row["derived_from"].append("provider.target:{provider_id}")
    _expect_code(lambda: validate_matrix(output_source, tuple(provider_ids)), "OWNERSHIP_OUTPUT_AS_SOURCE")

    for field, value in (("family", "diagnostics"), ("owner", "arbitrary.owner")):
        changed = copy.deepcopy(matrix)
        changed["rows"][0][field] = value
        _expect_code(lambda changed=changed: validate_matrix(changed, tuple(provider_ids)),
                     "OWNERSHIP_ROW_MISMATCH")
    changed_write = copy.deepcopy(matrix)
    changed_write["rows"][0]["write"] = ["arbitrary.writer"]
    _expect_code(lambda: validate_matrix(changed_write, tuple(provider_ids)),
                 "OWNERSHIP_ROW_MISMATCH")

    added_carriers = {
        "analytics.event.normalized", "analytics.reader:{provider_id}",
        "analytics.run-report", "analytics.store.project",
        "skill.publication-unit:{publication_unit_id}", "skill.semantic-catalog",
    }
    for carrier_id in added_carriers:
        deleted_carrier = copy.deepcopy(matrix)
        deleted_carrier["rows"] = [row for row in deleted_carrier["rows"]
                                   if row["carrier_id"] != carrier_id]
        _expect_code(lambda deleted_carrier=deleted_carrier: validate_matrix(
            deleted_carrier, tuple(provider_ids)), "OWNERSHIP_CARRIER_MISSING")
        mutated_carrier = copy.deepcopy(matrix)
        next(row for row in mutated_carrier["rows"]
             if row["carrier_id"] == carrier_id)["owner"] = "arbitrary.owner"
        _expect_code(lambda mutated_carrier=mutated_carrier: validate_matrix(
            mutated_carrier, tuple(provider_ids)), "OWNERSHIP_ROW_MISMATCH")

    third = _load_json(fixtures / "third-provider.json")
    replacement = copy.deepcopy(third)
    replacement["descriptor"]["renderer"]["semantic_replacement"] = {"job": "provider-owned job"}
    _expect_code(lambda: _validate_third_provider(replacement, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SEMANTIC_REPLACEMENT")

    invalid_provider = copy.deepcopy(third)
    invalid_provider["provider"]["id"] = "Orbit"
    _expect_code(lambda: _validate_third_provider(invalid_provider, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_PROVIDER_ID_INVALID")

    shared_path = copy.deepcopy(third)
    shared_path["registration"]["additions"][0]["path"] = "root/contracts/skill-core-v1.md"
    _expect_code(lambda: _validate_third_provider(shared_path, pattern, skill_contracts,
                                                   set(capabilities)),
                 "OWNERSHIP_CROSS_PROVIDER")

    missing_manifest_provider = copy.deepcopy(third)
    missing_manifest_provider["provider"]["id"] = "nova"
    _expect_code(lambda: _validate_third_provider(missing_manifest_provider, pattern,
                                                   skill_contracts, set(capabilities)),
                 "ADAPTER_PROVIDER_MANIFEST_MISMATCH")

    missing_manifest_extension = copy.deepcopy(third)
    missing_manifest_extension["manifest"]["native_extensions"] = []
    _expect_code(lambda: _validate_third_provider(missing_manifest_extension, pattern,
                                                   skill_contracts, set(capabilities)),
                 "ADAPTER_EXTENSION_MANIFEST_MISMATCH")

    duplicate_kind = copy.deepcopy(third)
    duplicate_kind["registration"]["additions"][1]["kind"] = "descriptor"
    _expect_code(lambda: _validate_third_provider(duplicate_kind, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SCHEMA_INVALID")

    for invalid_path in (
            "adapters\\orbit\\descriptor.json",
            "adapters/orbit/../shared.json",
            "adapters/nova/descriptor.json",
            "adapters/orbit//descriptor.json"):
        invalid_registration_path = copy.deepcopy(third)
        invalid_registration_path["registration"]["additions"][0]["path"] = invalid_path
        _expect_code(lambda invalid_registration_path=invalid_registration_path:
                     _validate_third_provider(invalid_registration_path, pattern,
                                              skill_contracts, set(capabilities)),
                     "OWNERSHIP_CROSS_PROVIDER")

    path_collision = copy.deepcopy(third)
    path_collision["registration"]["additions"][1]["path"] = (
        path_collision["registration"]["additions"][0]["path"])
    _expect_code(lambda: _validate_third_provider(path_collision, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_PATH_COLLISION")

    unknown_skill = copy.deepcopy(third)
    unknown_skill["descriptor"]["skill_id"] = "general/unknown"
    _expect_code(lambda: _validate_third_provider(unknown_skill, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SKILL_UNKNOWN")

    unknown_capability = copy.deepcopy(third)
    unknown_capability["descriptor"]["required_capabilities"][0]["id"] = "skills.unknown"
    _expect_code(lambda: _validate_third_provider(unknown_capability, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_CAPABILITY_UNKNOWN")

    removed_requirement = copy.deepcopy(third)
    removed_requirement["descriptor"]["required_capabilities"] = []
    _expect_code(lambda: _validate_third_provider(removed_requirement, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SKILL_CONTRACT_MISMATCH")

    downgraded_requirement = copy.deepcopy(third)
    requirement = downgraded_requirement["descriptor"]["required_capabilities"].pop()
    downgraded_requirement["descriptor"]["optional_capabilities"] = [requirement]
    _expect_code(lambda: _validate_third_provider(downgraded_requirement, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SKILL_CONTRACT_MISMATCH")

    narrowed_levels = copy.deepcopy(third)
    narrowed_levels["descriptor"]["required_capabilities"][0]["accepted_levels"] = ["native"]
    _expect_code(lambda: _validate_third_provider(narrowed_levels, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SKILL_CONTRACT_MISMATCH")

    substituted_known = copy.deepcopy(third)
    substituted_known["descriptor"]["required_capabilities"][0]["id"] = "workflows.status"
    _expect_code(lambda: _validate_third_provider(substituted_known, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SKILL_CONTRACT_MISMATCH")

    vacuous_renderer = copy.deepcopy(third)
    vacuous_renderer["descriptor"]["renderer"] = {"claim": "works"}
    _expect_code(lambda: _validate_third_provider(vacuous_renderer, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SEAM_INVALID")

    for seam in _REQUIRED_SEAMS:
        for field, scalar in third["descriptor"][seam].items():
            whitespace = copy.deepcopy(third)
            if isinstance(scalar, str):
                whitespace["descriptor"][seam][field] = " "
            elif seam == "renderer" and field == "target_roots":
                whitespace["descriptor"][seam][field] = [" "]
            else:
                continue
            _expect_code(
                lambda whitespace=whitespace: _validate_third_provider(
                    whitespace, pattern, skill_contracts, set(capabilities)),
                "ADAPTER_SEAM_INVALID")

    nested_copy = copy.deepcopy(third)
    nested_copy["descriptor"]["replay"]["nested"] = {
        "semantic_copy": {"job": "fork", "trigger": {}, "invariants": [], "outputs": []},
    }
    _expect_code(lambda: _validate_third_provider(nested_copy, pattern, skill_contracts,
                                                   set(capabilities)),
                 "ADAPTER_SEMANTIC_REPLACEMENT")

    producer_desired = _producer_desired(_load_json(fixtures / "schema-positive.json"))
    adapted_binding = copy.deepcopy(current_manifest)
    adapted_row = next(
        support for capability in adapted_binding["capabilities"]
        for support in capability["support"].values() if support["level"] == "adapted")
    adapted_row["binding"] = {"surface": "provider-native adapted fixture"}
    _validate_capability_manifest(adapted_binding, pattern)
    for field, value in (
            ("limitations", []), ("limitations", [" "]), ("evidence", []),
            ("binding", {})):
        invalid_adapted = copy.deepcopy(adapted_binding)
        invalid_row = next(
            support for capability in invalid_adapted["capabilities"]
            for support in capability["support"].values() if support["level"] == "adapted")
        invalid_row[field] = value
        _expect_code(lambda invalid_adapted=invalid_adapted: _validate_capability_manifest(
            invalid_adapted, pattern), "NEG_MANIFEST_INVALID")
    missing_adapter = copy.deepcopy(adapted_binding)
    missing_adapter_row = next(
        support for capability in missing_adapter["capabilities"]
        for support in capability["support"].values() if support["level"] == "adapted")
    del missing_adapter_row["adapter_id"]
    _expect_code(lambda: _validate_capability_manifest(missing_adapter, pattern),
                 "NEG_MANIFEST_INVALID")
    whitespace_claim = copy.deepcopy(adapted_binding)
    whitespace_evidence = next(
        support for capability in whitespace_claim["capabilities"]
        for support in capability["support"].values() if support["level"] == "adapted")
    whitespace_evidence["evidence"][0]["claim"] = " "
    _expect_code(lambda: _validate_capability_manifest(whitespace_claim, pattern),
                 "NEG_MANIFEST_INVALID")

    empty_capability_catalog = copy.deepcopy(current_manifest)
    empty_capability_catalog["capabilities"] = []
    _expect_code(lambda: _validate_capability_manifest(empty_capability_catalog, pattern),
                 "NEG_MANIFEST_INVALID")

    duplicate_evidence = copy.deepcopy(current_manifest)
    evidence_rows = duplicate_evidence["capabilities"][0]["support"]["claude-code"]["evidence"]
    evidence_rows.append(copy.deepcopy(evidence_rows[0]))
    _expect_code(lambda: _validate_capability_manifest(duplicate_evidence, pattern),
                 "NEG_MANIFEST_INVALID")

    support_drift = copy.deepcopy(current_manifest)
    drift_support = next(row for row in support_drift["capabilities"]
                         if row["id"] == "skills.repository")["support"]["claude-code"]
    drift_support.pop("binding")
    drift_support["level"] = "unsupported"
    drift_support["diagnostic"] = "unsupported: valid producer drift fixture"
    _validate_capability_manifest(support_drift, pattern)
    drift_case = _producer_probe_case(_PRODUCER_PROBES[1], support_drift, producer_desired)
    drift_result = negotiate(drift_case, pattern)
    if (drift_result["outcome"] != "blocked"
            or [row["code"] for row in drift_result["diagnostics"]]
            != ["NEG_REQUIRED_UNSUPPORTED"]):
        raise ValueError(f"valid support drift did not change negotiation: {drift_result!r}")
    try:
        _run_producer_probes(support_drift, producer_desired, pattern)
    except ValueError:
        pass
    else:
        raise ValueError("valid producer support drift was accepted against frozen probes")

    missing_provenance = copy.deepcopy(producer_desired)
    missing_provenance["provenance"].pop()
    _expect_code(lambda: _run_producer_probes(current_manifest, missing_provenance, pattern),
                 "PCP_PROVENANCE_INVALID")

    duplicate_skill = copy.deepcopy(skill_positive)
    duplicate_case = copy.deepcopy(duplicate_skill["cases"][0])
    duplicate_case["id"] = "repository-skill-audit-duplicate"
    duplicate_skill["cases"].append(duplicate_case)
    _expect_code(lambda: _validate_skill_core_positive(duplicate_skill),
                 "SKILL_CORE_DUPLICATE_ID")

    wrong_skill_version = copy.deepcopy(skill_positive)
    wrong_skill_version["contract_version"] = "2.0.0"
    _expect_code(lambda: _validate_skill_core_positive(wrong_skill_version),
                 "SKILL_CORE_VERSION_UNSUPPORTED")

    empty_core_capabilities = copy.deepcopy(skill_positive)
    empty_core_capabilities["cases"][0]["skill_core"]["capabilities"] = []
    _expect_code(lambda: _validate_skill_core_positive(empty_core_capabilities),
                 "SKILL_CORE_CAPABILITY_INVALID")

    wrong_level_order = copy.deepcopy(skill_positive)
    wrong_level_order["cases"][0]["skill_core"]["capabilities"][0]["accepted_levels"] = [
        "native", "adapted"]
    _expect_code(lambda: _validate_skill_core_positive(wrong_level_order),
                 "SKILL_CORE_CAPABILITY_INVALID")

    valid_failure_modes = copy.deepcopy(skill_positive)
    valid_failure_modes["cases"][0]["skill_core"]["failure_modes"] = [{
        "code": "SKILL_EVIDENCE_MISSING",
        "condition": "required evidence is absent",
        "outcome": "report a non-green result",
    }]
    _validate_skill_core_positive(valid_failure_modes)
    open_failure_mode = copy.deepcopy(valid_failure_modes)
    open_failure_mode["cases"][0]["skill_core"]["failure_modes"][0]["extra"] = "fork"
    _expect_code(lambda: _validate_skill_core_positive(open_failure_mode),
                 "SKILL_CORE_FAILURE_MODE_INVALID")
    duplicate_failure_mode = copy.deepcopy(valid_failure_modes)
    duplicate_failure_mode["cases"][0]["skill_core"]["failure_modes"].append(
        copy.deepcopy(duplicate_failure_mode["cases"][0]["skill_core"]["failure_modes"][0]))
    _expect_code(lambda: _validate_skill_core_positive(duplicate_failure_mode),
                 "SKILL_CORE_FAILURE_MODE_INVALID")

    for field in ("inputs", "outputs"):
        malformed = copy.deepcopy(skill_positive)
        malformed["cases"][0]["skill_core"][field][0] = "provider/output/path"
        _expect_code(lambda malformed=malformed: _validate_skill_core_positive(malformed),
                     "SKILL_CORE_SEMANTIC_ID_INVALID")
        forbidden_token = copy.deepcopy(skill_positive)
        forbidden_token["cases"][0]["skill_core"][field][0] = "provider.output.path"
        _expect_code(lambda forbidden_token=forbidden_token: _validate_skill_core_positive(
            forbidden_token), "SKILL_CORE_SEMANTIC_ID_INVALID")

    identity_sites = (
        ("/cases/0/skill_core/skill_id", "SKILL_CORE_SCHEMA_INVALID"),
        ("/cases/0/skill_core/capabilities/0/id", "SKILL_CORE_CAPABILITY_INVALID"),
        ("/cases/0/skill_core/inputs/0", "SKILL_CORE_SEMANTIC_ID_INVALID"),
        ("/cases/0/skill_core/outputs/0", "SKILL_CORE_SEMANTIC_ID_INVALID"),
        ("/cases/0/skill_core/resources/0/id", "SKILL_CORE_RESOURCE_INVALID"),
        ("/cases/0/skill_core/provenance/source_id", "SKILL_CORE_PROVENANCE_INVALID"),
    )
    for path, expected_code in identity_sites:
        for invalid_id in ("semantic:identity", "semantic_identity"):
            invalid_core_id = _apply_mutation(skill_positive, {
                "op": "replace", "path": path, "value": invalid_id,
            })
            _expect_code(lambda invalid_core_id=invalid_core_id: _validate_skill_core_positive(
                invalid_core_id), expected_code)

    translated_skill_id = copy.deepcopy(skill_positive)
    translated_skill_id["cases"][0]["skill_core"]["skill_id"] = "skills.repository-audit"
    _expect_code(lambda: _validate_skill_core_positive(translated_skill_id),
                 "SKILL_CORE_SCHEMA_INVALID")

    for path in (
            "/cases/0/skill_core/trigger/positive/0",
            "/cases/0/skill_core/trigger/negative/0",
            "/cases/0/skill_core/invariants/0",
            "/cases/0/skill_core/workflow/0",
            "/cases/0/skill_core/resources/0/ref",
            "/cases/0/skill_core/provenance/refresh_policy"):
        blank_core = _apply_mutation(skill_positive, {
            "op": "replace", "path": path, "value": " ",
        })
        _expect_code(lambda blank_core=blank_core: _validate_skill_core_positive(blank_core),
                     "SKILL_CORE_STRING_INVALID")

    for path, values, expected_code in (
            ("/cases/0/skill_core/trigger/positive",
             ["audit the declared skill set", "audit the declared skill set"],
             "SKILL_CORE_TRIGGER_INVALID"),
            ("/cases/0/skill_core/invariants",
             ["same invariant", "same invariant"], "SKILL_CORE_SCHEMA_INVALID"),
            ("/cases/0/skill_core/workflow",
             ["same step", "same step"], "SKILL_CORE_SCHEMA_INVALID")):
        duplicate_strings = _apply_mutation(skill_positive, {
            "op": "replace", "path": path, "value": values,
        })
        _expect_code(lambda duplicate_strings=duplicate_strings:
                     _validate_skill_core_positive(duplicate_strings), expected_code)

    positive = _load_json(fixtures / "negotiation-positive.json")
    for invalid_id in ("semantic:identity", "semantic_identity"):
        invalid_provider_manifest = copy.deepcopy(positive["cases"][0]["manifest"])
        original_provider = invalid_provider_manifest["providers"][0]["id"]
        invalid_provider_manifest["providers"][0]["id"] = invalid_id
        for capability in invalid_provider_manifest["capabilities"]:
            capability["support"][invalid_id] = capability["support"].pop(original_provider)
        _expect_code(lambda invalid_provider_manifest=invalid_provider_manifest:
                     _validate_capability_manifest(invalid_provider_manifest, pattern),
                     "NEG_MANIFEST_INVALID")

        invalid_capability_manifest = copy.deepcopy(current_manifest)
        invalid_capability_manifest["capabilities"][0]["id"] = invalid_id
        _expect_code(lambda invalid_capability_manifest=invalid_capability_manifest:
                     _validate_capability_manifest(invalid_capability_manifest, pattern),
                     "NEG_MANIFEST_INVALID")

        invalid_adapter_manifest = copy.deepcopy(current_manifest)
        adapted_support = next(
            support for capability in invalid_adapter_manifest["capabilities"]
            for support in capability["support"].values() if support["level"] == "adapted")
        adapted_support["adapter_id"] = invalid_id
        _expect_code(lambda invalid_adapter_manifest=invalid_adapter_manifest:
                     _validate_capability_manifest(invalid_adapter_manifest, pattern),
                     "NEG_MANIFEST_INVALID")

        extension_manifest = copy.deepcopy(next(
            case["manifest"] for case in positive["cases"]
            if case["id"] == "adapted-with-native-extension"))
        extension_manifest["native_extensions"][0]["id"] = invalid_id
        _expect_code(lambda extension_manifest=extension_manifest:
                     _validate_capability_manifest(extension_manifest, pattern),
                     "NEG_MANIFEST_INVALID")

        for path, expected_code in (
                ("/descriptor/adapter_id", "ADAPTER_SCHEMA_INVALID"),
                ("/descriptor/skill_id", "ADAPTER_SCHEMA_INVALID"),
                ("/descriptor/required_capabilities/0/id", "ADAPTER_SCHEMA_INVALID"),
                ("/descriptor/native_extensions/0", "ADAPTER_SCHEMA_INVALID"),
                ("/descriptor/renderer/id", "ADAPTER_SEAM_INVALID")):
            invalid_descriptor = _apply_mutation(third, {
                "op": "replace", "path": path, "value": invalid_id,
            })
            _expect_code(lambda invalid_descriptor=invalid_descriptor: _validate_third_provider(
                invalid_descriptor, pattern, skill_contracts, set(capabilities)), expected_code)

    aggregate = copy.deepcopy(positive["aggregate_cases"][0])
    del aggregate["provider_outcomes"]["codex"]
    _expect_code(lambda: _validate_aggregate_case(aggregate), "OWNERSHIP_MISSING_PROVIDER_ROW")

    masking = copy.deepcopy(positive["aggregate_cases"][0])
    masking["expected"] = "ready"
    _expect_code(lambda: _validate_aggregate_case(masking), "OWNERSHIP_PARTIAL_PROVIDER_MASKING")

    reversed_selected = copy.deepcopy(positive["aggregate_cases"][0])
    reversed_selected["selected_provider_ids"].reverse()
    _expect_code(lambda: _validate_aggregate_case(reversed_selected),
                 "OWNERSHIP_AGGREGATE_INVALID")

    whitespace_selected = copy.deepcopy(positive["aggregate_cases"][0])
    whitespace_selected["selected_provider_ids"][0] = " "
    _expect_code(lambda: _validate_aggregate_case(whitespace_selected),
                 "OWNERSHIP_AGGREGATE_INVALID")

    invalid_aggregate_id = copy.deepcopy(positive["aggregate_cases"][0])
    invalid_aggregate_id["id"] = "aggregate:case"
    _expect_code(lambda: _validate_aggregate_case(invalid_aggregate_id),
                 "OWNERSHIP_AGGREGATE_INVALID")

    empty_selected = {
        "id": "no-providers-selected", "selected_provider_ids": [],
        "provider_outcomes": {}, "expected": "no-providers-selected",
    }
    _validate_aggregate_case(empty_selected)
    empty_ready = copy.deepcopy(empty_selected)
    empty_ready["expected"] = "ready"
    _expect_code(lambda: _validate_aggregate_case(empty_ready),
                 "OWNERSHIP_PARTIAL_PROVIDER_MASKING")

    provenance = copy.deepcopy(positive["cases"][0])
    provenance["desired"]["provenance"].pop()
    _expect_code(lambda: negotiate(provenance, pattern), "PCP_PROVENANCE_INVALID")

    actual_shape = copy.deepcopy(positive["cases"][0])
    del actual_shape["manifest"]["capabilities"][0]["support"]["claude-code"]["diagnostic"]
    _expect_code(lambda: negotiate(actual_shape, pattern), "NEG_MANIFEST_INVALID")

    ordered = copy.deepcopy(next(case for case in positive["cases"]
                                 if case["id"] == "ordered-required-failures"))
    ordered["desired"]["selection"]["orbit"]["enabled"] = False
    semantic = {key: ordered["desired"][key] for key in (
        "provider_config_contract_version", "capability_catalog_version", "selection", "provenance")}
    ordered["desired"]["semantic_digest"] = _canonical_digest(semantic)
    ordered["descriptor"]["provider_id"] = "codex"
    actual_codes = [row["code"] for row in negotiate(ordered, pattern)["diagnostics"]]
    expected_codes = [
        "NEG_PROVIDER_DISABLED", "NEG_PROVIDER_MISMATCH", "NEG_REQUIRED_DENIED",
        "NEG_REQUIRED_MISSING", "NEG_REQUIRED_UNSUPPORTED", "NEG_REQUIRED_LEVEL_REJECTED",
    ]
    if actual_codes != expected_codes:
        raise ValueError(f"failure ordering mismatch: {actual_codes!r}")

    _exercise_negative_fixtures(fixtures, pattern)


def _migration_record(value: object, fields: set[str], code: str = "MIG_SOURCE_CORRUPT") -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        _raise(code)
    return value


def _migration_version(source_class: str, version: object) -> None:
    if source_class == "legacy-absent-config":
        if version != "0":
            _raise("MIG_SOURCE_VERSION_UNSUPPORTED")
        return
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        _raise("MIG_SOURCE_VERSION_UNSUPPORTED")
    major, minor, _ = (int(part) for part in version.split("."))
    if major > 1:
        _raise("MIG_SOURCE_NEWER_MAJOR")
    if major != 1 or minor != 0:
        _raise("MIG_SOURCE_VERSION_UNSUPPORTED")


def _migration_refusal(code: str, providers: dict[str, str], rollback: str) -> dict[str, object]:
    return {
        "outcome": "refused",
        "action_code": code,
        "writes": [],
        "rollback": rollback,
        "providers": providers,
    }


def validate_migration_case(value: object, *, check_expected: bool = True) -> dict[str, object]:
    case = _migration_record(value, {"id", "source", "target_snapshot", "operation", "expected"})
    if not _stable_id(case["id"]):
        _raise("MIG_SOURCE_CORRUPT")
    source = _migration_record(case["source"], {
        "class", "version", "config_state", "corrupt", "classification_complete", "artifacts",
    })
    source_class = source["class"]
    if source_class not in _MIGRATION_SOURCE_CLASSES:
        _raise("MIG_SOURCE_CLASS_UNKNOWN")
    _migration_version(source_class, source["version"])
    if source["corrupt"] is not False:
        _raise("MIG_SOURCE_CORRUPT")
    if not isinstance(source["classification_complete"], bool):
        _raise("MIG_SOURCE_CORRUPT")
    if not source["classification_complete"]:
        _raise("MIG_CLASSIFICATION_INCOMPLETE")
    artifacts = source["artifacts"]
    if not isinstance(artifacts, list):
        _raise("MIG_SOURCE_CORRUPT")
    artifact_ids: list[str] = []
    provider_ids: list[str] = []
    for item in artifacts:
        artifact = _migration_record(item, {
            "artifact_id", "provider_id", "classification", "ownership", "ownership_evidence",
            "target_path", "expected_preimage", "observed_preimage", "backup_path",
            "expected_postimage",
        })
        if (not _stable_id(artifact["artifact_id"])
                or not _provider_id(artifact["provider_id"])
                or artifact["classification"] not in _MIGRATION_CLASSIFICATIONS
                or not _digest(artifact["ownership_evidence"])
                or not isinstance(artifact["target_path"], str)
                or artifact["target_path"].startswith("/")
                or ".." in Path(artifact["target_path"]).parts
                or not isinstance(artifact["backup_path"], str)
                or artifact["backup_path"].startswith("/")
                or ".." in Path(artifact["backup_path"]).parts
                or not _digest(artifact["expected_preimage"])
                or not _digest(artifact["observed_preimage"])
                or not _digest(artifact["expected_postimage"])):
            _raise("MIG_SOURCE_CORRUPT")
        if artifact["classification"] == "ambiguous":
            _raise("MIG_CLASSIFICATION_AMBIGUOUS")
        if artifact["classification"] == "local-override":
            _raise("MIG_LOCAL_OVERRIDE")
        if artifact["ownership"] != "managed":
            _raise("MIG_OWNERSHIP_UNPROVEN")
        if artifact["observed_preimage"] != artifact["expected_preimage"]:
            _raise("MIG_PREIMAGE_CHANGED")
        artifact_ids.append(artifact["artifact_id"])
        provider_ids.append(artifact["provider_id"])
    if artifact_ids != sorted(artifact_ids) or len(artifact_ids) != len(set(artifact_ids)):
        _raise("MIG_SOURCE_CORRUPT")

    snapshot = _migration_record(case["target_snapshot"], {
        "complete", "valid", "desired_digest", "providers",
    })
    if snapshot["complete"] is not True:
        _raise("MIG_TARGET_SNAPSHOT_INCOMPLETE")
    if snapshot["valid"] is not True or not _digest(snapshot["desired_digest"]):
        _raise("MIG_TARGET_SNAPSHOT_INVALID")
    selected = snapshot["providers"]
    if (not isinstance(selected, list) or selected != sorted(selected)
            or len(selected) != len(set(selected))
            or not all(_provider_id(provider_id) for provider_id in selected)):
        _raise("MIG_PROVIDER_SET_MISMATCH")
    if source_class == "legacy-absent-config":
        if source["config_state"] != "absent" or artifacts or selected != ["claude-code", "codex"]:
            _raise("MIG_SOURCE_CORRUPT")
    elif source["config_state"] != "present" or set(selected) != set(provider_ids):
        _raise("MIG_PROVIDER_SET_MISMATCH")

    operation = _migration_record(case["operation"], {
        "mode", "authorization", "writes", "backup_artifact_ids", "provider_results",
        "rollback", "readback", "second_reconcile_actions",
    })
    mode = operation["mode"]
    if mode not in _MIGRATION_NO_WRITE_MODES | {"apply"}:
        _raise("MIG_SOURCE_CORRUPT")
    if (not isinstance(operation["writes"], list)
            or not isinstance(operation["backup_artifact_ids"], list)
            or not isinstance(operation["provider_results"], dict)
            or not isinstance(operation["second_reconcile_actions"], list)):
        _raise("MIG_SOURCE_CORRUPT")
    if mode in _MIGRATION_NO_WRITE_MODES:
        if operation["writes"] or operation["backup_artifact_ids"]:
            _raise("MIG_WRITE_FORBIDDEN")
        if (operation["authorization"] is not None or operation["provider_results"]
                or operation["rollback"] != "not-required"
                or operation["readback"] != "not-run"
                or operation["second_reconcile_actions"]):
            _raise("MIG_WRITE_FORBIDDEN")
        if source_class == "legacy-absent-config":
            result = {
                "outcome": "compatibility-noop",
                "action_code": "MIG_COMPATIBILITY_NOOP",
                "writes": [],
                "rollback": "not-required",
                "providers": {"claude-code": "ready", "codex": "not-selected"},
            }
        else:
            result = {
                "outcome": "plan-ready",
                "action_code": "MIG_PLAN_READY",
                "writes": [],
                "rollback": "not-required",
                "providers": {provider_id: "planned" for provider_id in selected},
            }
    else:
        authorization = operation["authorization"]
        if not isinstance(authorization, dict):
            _raise("MIG_AUTHORITY_REQUIRED")
        authorization = _migration_record(authorization, {"decision_id", "action_digest", "status"},
                                          "MIG_AUTHORITY_REQUIRED")
        if (not _stable_id(authorization["decision_id"])
                or not _digest(authorization["action_digest"])
                or authorization["status"] != "accepted"):
            _raise("MIG_AUTHORITY_REQUIRED")
        if operation["writes"] != _MIGRATION_WRITE_ORDER:
            _raise("MIG_SOURCE_CORRUPT")
        if operation["backup_artifact_ids"] != artifact_ids:
            _raise("MIG_BACKUP_SET_MISMATCH")
        results = operation["provider_results"]
        if set(results) != set(selected) or not all(
                outcome in {"success", "failure"} for outcome in results.values()):
            _raise("MIG_PROVIDER_SET_MISMATCH")
        if "failure" in results.values():
            if operation["rollback"] != "restored":
                result = _migration_refusal("MIG_ROLLBACK_FAILED", results, operation["rollback"])
            else:
                result = _migration_refusal("MIG_PROVIDER_PARTIAL", results, "restored")
        elif operation["readback"] != "match":
            result = _migration_refusal("MIG_READBACK_FAILED", results, operation["rollback"])
        elif operation["second_reconcile_actions"]:
            result = _migration_refusal(
                "MIG_SECOND_RECONCILE_NONEMPTY", results, operation["rollback"])
        elif operation["rollback"] != "not-required":
            result = _migration_refusal("MIG_ROLLBACK_FAILED", results, operation["rollback"])
        else:
            result = {
                "outcome": "applied",
                "action_code": "MIG_APPLIED",
                "writes": list(_MIGRATION_WRITE_ORDER),
                "rollback": "not-required",
                "providers": results,
            }
    if check_expected and case["expected"] != result:
        raise ValueError(f"{case['id']}: migration outcome mismatch: {result!r}")
    return result


def _markdown_table(text: str, heading: str, headers: tuple[str, ...]) -> list[dict[str, str]]:
    marker = f"## {heading}"
    if marker not in text:
        raise ValueError(f"missing section: {heading}")
    section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    if len(lines) < 3:
        raise ValueError(f"missing table: {heading}")
    observed = tuple(cell.strip() for cell in lines[0].strip("|").split("|"))
    if observed != headers:
        raise ValueError(f"table schema mismatch: {heading}")
    rows = []
    for line in lines[2:]:
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != len(headers):
            raise ValueError(f"table row width mismatch: {heading}")
        rows.append(dict(zip(headers, cells)))
    return rows


def _row_digest(row: dict[str, str]) -> str:
    return _canonical_digest(row)


def _verify_predecessor_crosswalk(contract: Path) -> None:
    predecessor = contract.parents[3] / "archive/2026.07.19-DUAL-PROVIDER/root/contracts/provider-migration-gates.md"
    predecessor_rows = _markdown_table(
        predecessor.read_text(encoding="utf-8"), "Preconditions", _PREDECESSOR_GATE_HEADERS)
    if [row["Gate"] for row in predecessor_rows] != list(_PREDECESSOR_GATES):
        raise ValueError("predecessor G01-G11 order or exact set mismatch")
    source_digests = {row["Gate"]: _row_digest(row) for row in predecessor_rows}
    contract_text = contract.read_text(encoding="utf-8")
    crosswalk = _markdown_table(contract_text, "Exact G01-G11 predecessor crosswalk",
                                _CROSSWALK_HEADERS)
    if [row["Gate"] for row in crosswalk] != list(_PREDECESSOR_GATES):
        raise ValueError("G01-G11 crosswalk order or exact set mismatch")
    for row in crosswalk:
        if row["Source row SHA-256"] != source_digests[row["Gate"]]:
            raise ValueError(f"predecessor obligation weakened or changed: {row['Gate']}")
        if not row["Preserved obligation"] or not row["P1.3 enforcement"]:
            raise ValueError(f"empty predecessor crosswalk field: {row['Gate']}")
    if "G01–G11 MUST NOT be weakened" not in contract_text:
        raise ValueError("explicit G01-G11 no-weaken rule missing")


def _verify_migration_contract_inventory(contract: Path) -> None:
    text = contract.read_text(encoding="utf-8")
    required = {
        "## Legacy source classes and admission",
        "## Migration transaction",
        "## Rollback and convergence",
        "## Exact G01-G11 predecessor crosswalk",
        "## Approved Owner decision set C1-C6",
        "APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN",
        "MIG_COMPATIBILITY_NOOP", "MIG_PLAN_READY", "MIG_APPLIED",
        *_MIGRATION_NEGATIVE_CODES,
    }
    missing = sorted(literal for literal in required if literal not in text)
    if missing:
        raise ValueError("migration contract inventory missing: " + ", ".join(missing))


def _run_migration(contract: Path, fixtures: Path) -> None:
    _verify_migration_contract_inventory(contract)
    _verify_predecessor_crosswalk(contract)
    positive = _load_json(fixtures / "migration-positive.json")
    negative = _load_json(fixtures / "migration-negative.json")
    if positive.get("contract_version") != "1.0.0" or negative.get("contract_version") != "1.0.0":
        raise ValueError("migration fixture contract version mismatch")
    bases = _case_map(positive, "cases", "MIG_SOURCE_CORRUPT")
    for case in bases.values():
        validate_migration_case(case)
    negatives = _require_list(negative.get("cases"), "MIG_SOURCE_CORRUPT", nonempty=True)
    seen_ids: set[str] = set()
    covered_codes: set[str] = set()
    for value in negatives:
        row = _migration_record(value, {"id", "base", "mutation", "expected_code"})
        if (not _stable_id(row["id"]) or row["id"] in seen_ids or row["base"] not in bases
                or row["expected_code"] not in _MIGRATION_NEGATIVE_CODES):
            _raise("MIG_SOURCE_CORRUPT")
        seen_ids.add(row["id"])
        covered_codes.add(row["expected_code"])
        mutated = _apply_mutation(bases[row["base"]], row["mutation"])
        try:
            result = validate_migration_case(mutated, check_expected=False)
        except ContractError as error:
            actual = error.code
        else:
            actual = result["action_code"]
        if actual != row["expected_code"]:
            raise ValueError(f"{row['id']}: expected {row['expected_code']}, got {actual}")
    if covered_codes != _MIGRATION_NEGATIVE_CODES:
        missing = sorted(_MIGRATION_NEGATIVE_CODES - covered_codes)
        raise ValueError("migration negative-code coverage missing: " + ", ".join(missing))


def _contract_metadata(text: str, field: str) -> str:
    match = re.search(rf"^\*\*{re.escape(field)}:\*\*\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing contract metadata: {field}")
    return match.group(1).strip()


def _verify_owner_freeze(contract: Path) -> None:
    text = contract.read_text(encoding="utf-8")
    if _contract_metadata(text, "Version") != "v1.0.0" or _contract_metadata(text, "Status") != "frozen":
        raise ValueError("P1.3 contract is not frozen v1.0.0")
    approval = _contract_metadata(text, "Approval")
    match = re.fullmatch(r"(D[0-9]+), [0-9]{4}-[0-9]{2}-[0-9]{2}", approval)
    if match is None:
        raise ValueError("exact Owner D# is required")
    decision_id = match.group(1)
    decisions_dir = contract.parents[2] / "decisions"
    paths = [path for path in decisions_dir.glob(f"{decision_id}-*.md")
             if not path.name.startswith("_")]
    if len(paths) != 1:
        raise ValueError("exact immutable Owner decision record is required")
    decision_text = paths[0].read_text(encoding="utf-8")
    if ("status: accepted" not in decision_text
            or "item: P1.3" not in decision_text
            or "APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN" not in decision_text):
        raise ValueError("accepted atomic C1-C6 Owner reply is required")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage", choices=("schema", "ownership", "migration", "final"))
    mode.add_argument("--self-test", choices=("schema", "ownership", "migration", "all"))
    mode.add_argument("--generate-matrix-md", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--skill-core", type=Path)
    parser.add_argument("--skill-adapters", type=Path)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--fixtures", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    plan_root = Path(__file__).resolve().parents[1]
    contract = args.contract or plan_root / "root/contracts/provider-control-plane-v1.md"
    skill_core = args.skill_core or plan_root / "root/contracts/skill-core-v1.md"
    skill_adapters = args.skill_adapters or plan_root / "root/contracts/provider-skill-adapter-v1.md"
    matrix = args.matrix or plan_root / "artifacts/P1-provider-ownership-capability-matrix.json"
    fixtures = args.fixtures or plan_root / "artifacts/P1-control-plane-fixtures"
    capability_manifest = plan_root.parents[1] / "configs/provider-capabilities.json"
    if args.generate_matrix_md:
        value = _load_json(matrix)
        matrix.with_suffix(".md").write_text(render_matrix_markdown(value), encoding="utf-8")
        print(f"generated: {matrix.with_suffix('.md')}")
        return 0
    if args.stage in {"schema", "migration", "final"} and (
            args.contract is None or args.fixtures is None):
        raise ValueError(f"--stage {args.stage} requires --contract and --fixtures")
    if args.stage == "ownership" and any(value is None for value in (
            args.contract, args.skill_core, args.skill_adapters, args.matrix, args.fixtures)):
        raise ValueError(
            "--stage ownership requires --contract, --skill-core, --skill-adapters, --matrix and --fixtures")
    if args.stage == "final" and args.matrix is None:
        raise ValueError("--stage final requires --matrix")
    if args.stage == "schema" or args.self_test == "schema":
        _run(contract, fixtures)
        print("schema: pass" if args.stage else "self-test schema: pass")
        return 0
    if args.stage == "ownership":
        report = _run_ownership(contract, skill_core, skill_adapters, matrix, fixtures,
                                capability_manifest)
        print("ownership: pass")
        print("ownership inventory: " + json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    if args.stage == "migration" or args.self_test == "migration":
        _run_migration(contract, fixtures)
        print("migration: pass" if args.stage else "self-test migration: pass")
        return 0
    if args.stage == "final":
        _run(contract, fixtures)
        print("schema: pass")
        _run_ownership(contract, skill_core, skill_adapters, matrix, fixtures,
                       capability_manifest)
        print("ownership: pass")
        _run_migration(contract, fixtures)
        print("migration: pass")
        print("predecessor-crosswalk: pass")
        _verify_owner_freeze(contract)
        return 0
    if args.self_test == "all":
        _run(contract, fixtures)
        _self_test_ownership(contract, skill_core, skill_adapters, matrix, fixtures,
                             capability_manifest)
        _run_migration(contract, fixtures)
        print("self-test all: pass")
        return 0
    _self_test_ownership(contract, skill_core, skill_adapters, matrix, fixtures,
                         capability_manifest)
    print("self-test ownership: pass")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, ValueError, OSError) as error:
        print(f"check: fail: {error}", file=sys.stderr)
        raise SystemExit(1)
