#!/usr/bin/env python3
"""Stdlib-only conformance checker for provider-control-plane v1 fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
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
    return isinstance(value, str) and _ID.fullmatch(value) is not None and "/" not in value


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
                or not isinstance(row["message"], str) or not row["message"]
                or not _stable_id(row["source_ref"])):
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
    if not selection or not all(_stable_id(provider_id) for provider_id in selection):
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
                or not _stable_id(source["id"])
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
    if not _stable_id(provider_id):
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


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage", choices=("schema",))
    mode.add_argument("--self-test", choices=("schema",))
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--fixtures", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    plan_root = Path(__file__).resolve().parents[1]
    contract = args.contract or plan_root / "root/contracts/provider-control-plane-v1.md"
    fixtures = args.fixtures or plan_root / "artifacts/P1-control-plane-fixtures"
    if args.stage and (args.contract is None or args.fixtures is None):
        raise ValueError("--stage requires --contract and --fixtures")
    _run(contract, fixtures)
    print("schema: pass" if args.stage else "self-test schema: pass")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, ValueError, OSError) as error:
        print(f"schema: fail: {error}", file=sys.stderr)
        raise SystemExit(1)
