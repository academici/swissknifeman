#!/usr/bin/env python3
"""Independent stdlib conformance validator for worker-envelope-v1."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

ENVELOPE_KEYS = frozenset({"schema_version", "contract_version", "request", "events", "result"})
REQUEST_KEYS = frozenset({
    "schema_version", "request_id", "run_id", "slice_id", "attempt", "idempotency_key",
    "trace_id", "provider", "route", "permissions", "bundle", "budgets", "child_policy",
    "redaction_policy_hash", "created_at",
})
PROVIDER_KEYS = frozenset({
    "id", "cli_version", "mapping_id", "mapping_version", "mapping_state",
    "degraded_route_grant_hash",
})
ROUTE_KEYS = frozenset({"model_class", "model", "effort", "capabilities"})
CAPABILITY_KEYS = frozenset({"id", "state", "required", "source", "unknown_reason"})
PERMISSION_KEYS = frozenset({
    "authority_profile", "approval_mode", "sandbox_mode", "network_mode",
    "filesystem_scope_hash", "source",
})
BUNDLE_KEYS = frozenset({
    "slice_manifest_hash", "task_contract_hash", "authority_policy_hash", "output_schema_hash",
    "validation_hash", "content_refs",
})
CONTENT_REF_KEYS = frozenset({"ref", "sha256"})
BUDGET_KEYS = frozenset({
    "timeout_ms", "max_envelope_bytes", "max_event_count", "max_turns", "max_output_bytes",
    "token_limit", "token_limit_unknown_reason", "cost_limit_microunits",
    "cost_limit_unknown_reason",
})
CHILD_KEYS = frozenset({"mode", "max_children", "allowed_capabilities"})
EVENT_KEYS = frozenset({
    "schema_version", "sequence", "event_type", "occurred_at", "request_id", "run_id",
    "slice_id", "attempt", "idempotency_key", "trace_id", "provider_id",
    "provider_event_type", "provider_event_type_unknown_reason", "turn_index", "usage",
    "usage_unknown_reason", "diagnostic_code", "diagnostic_hash",
})
RESULT_KEYS = frozenset({
    "schema_version", "request_id", "run_id", "slice_id", "attempt", "idempotency_key",
    "trace_id", "provider_id", "worker_succeeded", "acceptance_state", "exit_class",
    "reason_code", "output", "usage", "event_count", "turn_count", "duration_ms",
    "diagnostic_codes", "redaction",
})
OUTPUT_KEYS = frozenset({"status", "schema_hash", "content_hash", "bytes", "stored_ref"})
USAGE_KEYS = frozenset({
    "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
    "cost_microunits",
})
OBSERVATION_KEYS = frozenset({"value", "unit", "source", "unknown_reason"})
REDACTION_KEYS = frozenset({"status", "excluded_classes", "excluded_count", "refused_key_count"})

SUPPORT_STATES = frozenset({"supported", "degraded", "unsupported", "unknown"})
EVENT_TYPES = frozenset({
    "worker_started", "session_observed", "turn_started", "turn_finished", "output_observed",
    "usage_observed", "permission_denied", "capability_observed", "provider_diagnostic",
    "worker_finished",
})
EXIT_CLASSES = frozenset({
    "success", "schema_failure", "permission_denied", "timeout", "quota_exhausted",
    "budget_exhausted", "capability_unsupported", "provider_failure", "internal_failure",
    "orphaned",
})
REASON_CODES = frozenset({
    "OK", "OUTPUT_SCHEMA_INVALID", "PERMISSION_REFUSED", "WALL_TIMEOUT", "PROVIDER_QUOTA",
    "BUDGET_TIMEOUT", "BUDGET_ENVELOPE_BYTES", "BUDGET_OUTPUT_BYTES",
    "BUDGET_EVENT_COUNT", "BUDGET_TURN_COUNT", "BUDGET_TOKEN_LIMIT", "BUDGET_COST_LIMIT",
    "CAPABILITY_UNSUPPORTED", "CAPABILITY_UNKNOWN", "DEGRADED_ROUTE_NOT_AUTHORIZED",
    "PROVIDER_UNAVAILABLE", "PROVIDER_NONZERO", "PROVIDER_PROTOCOL_UNKNOWN", "MAPPING_UNKNOWN",
    "INTERNAL_VALIDATOR", "PRIVACY_REFUSED", "UNKNOWN_SCHEMA_VERSION", "UNKNOWN_FIELD",
    "LINKAGE_MISMATCH", "PROVIDER_EVIDENCE_MISMATCH", "ORPHAN_CONFIRMED",
    "ORPHAN_IDENTITY_UNKNOWN",
})
EXIT_REASONS = {
    "success": frozenset({"OK"}),
    "schema_failure": frozenset({"OUTPUT_SCHEMA_INVALID"}),
    "permission_denied": frozenset({"PERMISSION_REFUSED"}),
    "timeout": frozenset({"WALL_TIMEOUT"}),
    "quota_exhausted": frozenset({"PROVIDER_QUOTA"}),
    "budget_exhausted": frozenset(code for code in REASON_CODES if code.startswith("BUDGET_")),
    "capability_unsupported": frozenset({
        "CAPABILITY_UNSUPPORTED", "CAPABILITY_UNKNOWN", "DEGRADED_ROUTE_NOT_AUTHORIZED",
    }),
    "provider_failure": frozenset({
        "PROVIDER_UNAVAILABLE", "PROVIDER_NONZERO", "PROVIDER_PROTOCOL_UNKNOWN", "MAPPING_UNKNOWN",
    }),
    "internal_failure": frozenset({
        "INTERNAL_VALIDATOR", "PRIVACY_REFUSED", "UNKNOWN_SCHEMA_VERSION", "UNKNOWN_FIELD",
        "LINKAGE_MISMATCH", "PROVIDER_EVIDENCE_MISMATCH",
    }),
    "orphaned": frozenset({"ORPHAN_CONFIRMED", "ORPHAN_IDENTITY_UNKNOWN"}),
}
PROVIDERS = frozenset({"codex", "claude-code"})
EXCLUDED_CLASSES = (
    "raw_provider_stream", "request_content", "private_reasoning", "tool_input_output",
    "credential", "environment_value",
)
PRIVATE_KEYS = frozenset({
    "secret", "credential_value", "raw_stdout", "raw_stderr", "raw_stream", "input_content",
    "private_reasoning", "tool_input", "tool_output", "environment_value",
})

DECLARED = {
    "envelope_keys": ENVELOPE_KEYS,
    "request_keys": REQUEST_KEYS,
    "event_keys": EVENT_KEYS,
    "result_keys": RESULT_KEYS,
    "support_states": SUPPORT_STATES,
    "event_types": EVENT_TYPES,
    "exit_classes": EXIT_CLASSES,
    "reason_codes": REASON_CODES,
}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read JSON {path}: {error}") from error


def _declared_sets(text: str):
    found = {}
    pattern = re.compile(r"<!-- declared-set: ([a-z_]+) -->\s*```text\n(.*?)\n```", re.DOTALL)
    for name, body in pattern.findall(text):
        values = frozenset(line.strip() for line in body.splitlines() if line.strip())
        if name in found:
            raise ValueError(f"duplicate declared set: {name}")
        found[name] = values
    return found


def _exact(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def _nonempty(value):
    return isinstance(value, str) and bool(value)


def _hash(value):
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _private_key_present(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in PRIVATE_KEYS:
                return True
            if _private_key_present(child):
                return True
    elif isinstance(value, list):
        return any(_private_key_present(child) for child in value)
    return False


def _observation_valid(value):
    if not _exact(value, OBSERVATION_KEYS):
        return False
    if not _nonempty(value["unit"]) or not _nonempty(value["source"]):
        return False
    measured = value["value"] is not None
    if measured:
        return _nonnegative_int(value["value"]) and value["unknown_reason"] is None
    return _nonempty(value["unknown_reason"])


def _provider_rows(matrix):
    if not isinstance(matrix, dict) or matrix.get("schema_version") != "provider-matrix-v1":
        raise ValueError("providers input is not provider-matrix-v1")
    rows = matrix.get("providers")
    if not isinstance(rows, list):
        raise ValueError("provider matrix has no provider rows")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("provider") in result:
            raise ValueError("provider matrix contains malformed or duplicate provider row")
        provider = row.get("provider")
        capabilities = row.get("capabilities")
        if provider not in PROVIDERS or not isinstance(capabilities, dict):
            raise ValueError("provider matrix provider/capabilities mismatch")
        if not capabilities or any(state not in SUPPORT_STATES for state in capabilities.values()):
            raise ValueError("provider matrix contains an unknown support state")
        result[provider] = row
    if set(result) != set(PROVIDERS):
        raise ValueError("provider matrix must contain exactly both providers")
    return result


def _shape_valid(envelope):
    if not _exact(envelope, ENVELOPE_KEYS):
        return "UNKNOWN_FIELD"
    request, events, result = envelope.get("request"), envelope.get("events"), envelope.get("result")
    if not _exact(request, REQUEST_KEYS) or not isinstance(events, list) or not _exact(result, RESULT_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("provider"), PROVIDER_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("route"), ROUTE_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("permissions"), PERMISSION_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("bundle"), BUNDLE_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("budgets"), BUDGET_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(request.get("child_policy"), CHILD_KEYS):
        return "UNKNOWN_FIELD"
    if any(not _exact(event, EVENT_KEYS) for event in events):
        return "UNKNOWN_FIELD"
    if not _exact(result.get("output"), OUTPUT_KEYS):
        return "UNKNOWN_FIELD"
    if not _exact(result.get("usage"), USAGE_KEYS):
        return "UNKNOWN_FIELD"
    if any(not _exact(item, OBSERVATION_KEYS) for item in result["usage"].values()):
        return "UNKNOWN_FIELD"
    if not _exact(result.get("redaction"), REDACTION_KEYS):
        return "UNKNOWN_FIELD"
    return None


def _request_valid(request):
    provider = request["provider"]
    if provider["id"] not in PROVIDERS or not _nonempty(provider["cli_version"]):
        return False
    if not _nonempty(provider["mapping_id"]) or not SEMVER_RE.fullmatch(str(provider["mapping_version"])):
        return False
    if provider["mapping_state"] not in SUPPORT_STATES:
        return False
    grant = provider["degraded_route_grant_hash"]
    if grant is not None and not _hash(grant):
        return False
    for key in ("request_id", "run_id", "slice_id"):
        if not _nonempty(request[key]):
            return False
    if not _positive_int(request["attempt"]):
        return False
    for key in ("idempotency_key", "trace_id", "redaction_policy_hash"):
        if not _hash(request[key]):
            return False
    if not UTC_RE.fullmatch(str(request["created_at"])):
        return False
    route = request["route"]
    if not all(_nonempty(route[key]) for key in ("model_class", "model", "effort")):
        return False
    capabilities = route["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        return False
    seen = set()
    for row in capabilities:
        if not _exact(row, CAPABILITY_KEYS) or not _nonempty(row["id"]) or row["id"] in seen:
            return False
        seen.add(row["id"])
        if row["state"] not in SUPPORT_STATES or not isinstance(row["required"], bool):
            return False
        if not _nonempty(row["source"]):
            return False
        if (row["state"] == "unknown") != _nonempty(row["unknown_reason"]):
            return False
        if row["state"] != "unknown" and row["unknown_reason"] is not None:
            return False
    permissions = request["permissions"]
    if not all(_nonempty(permissions[key]) for key in (
            "authority_profile", "approval_mode", "sandbox_mode", "network_mode", "source")):
        return False
    if not _hash(permissions["filesystem_scope_hash"]):
        return False
    bundle = request["bundle"]
    for key in ("slice_manifest_hash", "task_contract_hash", "authority_policy_hash",
                "output_schema_hash", "validation_hash"):
        if not _hash(bundle[key]):
            return False
    refs = bundle["content_refs"]
    if not isinstance(refs, list) or not refs:
        return False
    if any(not _exact(row, CONTENT_REF_KEYS) or not _nonempty(row["ref"]) or not _hash(row["sha256"])
           for row in refs):
        return False
    budgets = request["budgets"]
    for key in ("timeout_ms", "max_envelope_bytes", "max_event_count", "max_turns", "max_output_bytes"):
        if not _positive_int(budgets[key]):
            return False
    for value_key, reason_key in (("token_limit", "token_limit_unknown_reason"),
                                  ("cost_limit_microunits", "cost_limit_unknown_reason")):
        value, reason = budgets[value_key], budgets[reason_key]
        if value is None:
            if not _nonempty(reason):
                return False
        elif not _positive_int(value) or reason is not None:
            return False
    child = request["child_policy"]
    if child["mode"] not in {"forbidden", "bounded_read_only"}:
        return False
    if not _nonnegative_int(child["max_children"]) or not isinstance(child["allowed_capabilities"], list):
        return False
    if child["mode"] == "forbidden" and (child["max_children"] != 0 or child["allowed_capabilities"]):
        return False
    if child["mode"] == "bounded_read_only" and child["max_children"] == 0:
        return False
    supported = {row["id"] for row in capabilities if row["state"] == "supported"}
    if not set(child["allowed_capabilities"]).issubset(supported):
        return False
    return True


def _events_valid(events):
    for sequence, event in enumerate(events, 1):
        if event["schema_version"] != "worker-event-v1":
            return "UNKNOWN_SCHEMA_VERSION"
        if event["sequence"] != sequence or event["event_type"] not in EVENT_TYPES:
            return "INTERNAL_VALIDATOR"
        if not UTC_RE.fullmatch(str(event["occurred_at"])) or event["provider_id"] not in PROVIDERS:
            return "INTERNAL_VALIDATOR"
        if event["turn_index"] is not None and not _positive_int(event["turn_index"]):
            return "INTERNAL_VALIDATOR"
        provider_event = event["provider_event_type"]
        provider_reason = event["provider_event_type_unknown_reason"]
        if (provider_event is None and not _nonempty(provider_reason)) or (
                provider_event is not None and (not _nonempty(provider_event) or provider_reason is not None)):
            return "INTERNAL_VALIDATOR"
        usage, usage_reason = event["usage"], event["usage_unknown_reason"]
        if (usage is None and not _nonempty(usage_reason)) or (
                usage is not None and (not isinstance(usage, dict) or usage_reason is not None)):
            return "INTERNAL_VALIDATOR"
        if (event["diagnostic_code"] is None) != (event["diagnostic_hash"] is None):
            return "INTERNAL_VALIDATOR"
        if event["diagnostic_hash"] is not None and not _hash(event["diagnostic_hash"]):
            return "INTERNAL_VALIDATOR"
    return None


def _linkage_valid(request, events, result):
    keys = ("request_id", "run_id", "slice_id", "attempt", "idempotency_key", "trace_id")
    expected = tuple(request[key] for key in keys)
    if tuple(result[key] for key in keys) != expected or result["provider_id"] != request["provider"]["id"]:
        return False
    return all(tuple(event[key] for key in keys) == expected
               and event["provider_id"] == request["provider"]["id"] for event in events)


def _evidence_valid(request, provider_rows):
    provider_id = request["provider"]["id"]
    expected = provider_rows[provider_id]["capabilities"]
    actual = {row["id"]: row["state"] for row in request["route"]["capabilities"]}
    return actual == expected


def _result_shape_valid(result, request):
    output = result["output"]
    if output["status"] not in {"valid", "invalid", "absent"} or not _nonnegative_int(output["bytes"]):
        return False
    if not _hash(output["schema_hash"]):
        return False
    if output["status"] == "valid":
        if not _hash(output["content_hash"]) or not _nonempty(output["stored_ref"]):
            return False
    elif output["content_hash"] is not None or output["stored_ref"] is not None or output["bytes"] != 0:
        return False
    if any(not _observation_valid(row) for row in result["usage"].values()):
        return False
    if not all(_nonnegative_int(result[key]) for key in ("event_count", "turn_count", "duration_ms")):
        return False
    if not isinstance(result["diagnostic_codes"], list) or not all(
            _nonempty(value) for value in result["diagnostic_codes"]):
        return False
    redaction = result["redaction"]
    if redaction["status"] != "clean" or tuple(redaction["excluded_classes"]) != EXCLUDED_CLASSES:
        return False
    return _nonnegative_int(redaction["excluded_count"]) and _nonnegative_int(redaction["refused_key_count"])


def validate_envelope(envelope, provider_rows):
    if _private_key_present(envelope):
        return False, "PRIVACY_REFUSED"
    shape_reason = _shape_valid(envelope)
    if shape_reason:
        return False, shape_reason
    if envelope["schema_version"] != "worker-envelope-v1" or envelope["contract_version"] != "1.0.0":
        return False, "UNKNOWN_SCHEMA_VERSION"
    request, events, result = envelope["request"], envelope["events"], envelope["result"]
    if request["schema_version"] != "worker-request-v1" or result["schema_version"] != "worker-result-v1":
        return False, "UNKNOWN_SCHEMA_VERSION"
    if not _request_valid(request) or not _result_shape_valid(result, request):
        return False, "INTERNAL_VALIDATOR"
    event_reason = _events_valid(events)
    if event_reason:
        return False, event_reason
    if not _linkage_valid(request, events, result):
        return False, "LINKAGE_MISMATCH"
    if not _evidence_valid(request, provider_rows):
        return False, "PROVIDER_EVIDENCE_MISMATCH"
    capabilities = request["route"]["capabilities"]
    degraded_required = any(row["required"] and row["state"] == "degraded" for row in capabilities)
    if (request["provider"]["mapping_state"] == "degraded" or degraded_required) and not _hash(
            request["provider"]["degraded_route_grant_hash"]):
        return False, "DEGRADED_ROUTE_NOT_AUTHORIZED"
    budgets = request["budgets"]
    encoded = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > budgets["max_envelope_bytes"]:
        return False, "BUDGET_ENVELOPE_BYTES"
    if result["output"]["bytes"] > budgets["max_output_bytes"]:
        return False, "BUDGET_OUTPUT_BYTES"
    if len(events) > budgets["max_event_count"] or result["event_count"] > budgets["max_event_count"]:
        return False, "BUDGET_EVENT_COUNT"
    if result["turn_count"] > budgets["max_turns"]:
        return False, "BUDGET_TURN_COUNT"
    if result["output"]["schema_hash"] != request["bundle"]["output_schema_hash"]:
        return False, "OUTPUT_SCHEMA_INVALID"
    if result["event_count"] != len(events):
        return False, "INTERNAL_VALIDATOR"
    observed_turn = max((event["turn_index"] or 0 for event in events), default=0)
    if result["turn_count"] != observed_turn:
        return False, "INTERNAL_VALIDATOR"
    exit_class, reason = result["exit_class"], result["reason_code"]
    if exit_class not in EXIT_CLASSES:
        return False, "PROVIDER_PROTOCOL_UNKNOWN"
    if reason not in REASON_CODES or reason not in EXIT_REASONS[exit_class]:
        return False, "INTERNAL_VALIDATOR"
    if result["worker_succeeded"] is not (exit_class == "success"):
        return False, "INTERNAL_VALIDATOR"
    if result["acceptance_state"] != "not_evaluated":
        return False, "INTERNAL_VALIDATOR"
    unavailable = [row for row in capabilities if row["required"] and row["state"] in {"unsupported", "unknown"}]
    if unavailable:
        expected = "CAPABILITY_UNSUPPORTED" if unavailable[0]["state"] == "unsupported" else "CAPABILITY_UNKNOWN"
        if exit_class != "capability_unsupported" or reason != expected:
            return False, "INTERNAL_VALIDATOR"
    return True, reason


def _set_pointer(value, pointer, replacement):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer!r}")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    target = value
    for part in parts[:-1]:
        if isinstance(target, list):
            target = target[int(part)]
        elif isinstance(target, dict) and part in target:
            target = target[part]
        else:
            raise ValueError(f"pointer does not resolve: {pointer}")
    leaf = parts[-1]
    if isinstance(target, list):
        target[int(leaf)] = copy.deepcopy(replacement)
    elif isinstance(target, dict):
        target[leaf] = copy.deepcopy(replacement)
    else:
        raise ValueError(f"pointer parent is scalar: {pointer}")


def _materialize(base, case):
    envelope = copy.deepcopy(base)
    for mutation in case["mutations"]:
        if not _exact(mutation, {"op", "path", "value"}) or mutation["op"] != "set":
            raise ValueError(f"case {case['id']}: unsupported mutation shape")
        _set_pointer(envelope, mutation["path"], mutation["value"])
    return envelope


def validate_carriers(contract_text, bank, provider_matrix):
    declared = _declared_sets(contract_text)
    for name, expected in DECLARED.items():
        if declared.get(name) != expected:
            raise ValueError(f"contract declared set mismatch: {name}")
    if not _exact(bank, {"schema_version", "contract_version", "base_envelope", "cases"}):
        raise ValueError("case bank envelope is not closed")
    if bank["schema_version"] != "worker-envelope-cases-v1" or bank["contract_version"] != "1.0.0":
        raise ValueError("case bank version mismatch")
    cases = bank["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("case bank has no cases")
    provider_rows = _provider_rows(provider_matrix)
    ids = set()
    observed_exits, observed_providers, observed_states, negative_reasons = set(), set(), set(), set()
    allowed_count = refused_count = 0
    for case in cases:
        if not _exact(case, {"id", "mutations", "expected"}) or not _nonempty(case["id"]):
            raise ValueError("case shape is not closed")
        if case["id"] in ids:
            raise ValueError(f"duplicate case ID: {case['id']}")
        ids.add(case["id"])
        if not isinstance(case["mutations"], list) or not _exact(case["expected"], {"allowed", "reason"}):
            raise ValueError(f"case {case['id']}: invalid mutations/expected shape")
        if not isinstance(case["expected"]["allowed"], bool) or case["expected"]["reason"] not in REASON_CODES:
            raise ValueError(f"case {case['id']}: invalid independent expectation")
        envelope = _materialize(bank["base_envelope"], case)
        actual = validate_envelope(envelope, provider_rows)
        expected = (case["expected"]["allowed"], case["expected"]["reason"])
        if actual != expected:
            raise ValueError(f"case {case['id']}: expected {expected}, got {actual}")
        if actual[0]:
            allowed_count += 1
            observed_exits.add(envelope["result"]["exit_class"])
            observed_providers.add(envelope["request"]["provider"]["id"])
            observed_states.update(row["state"] for row in envelope["request"]["route"]["capabilities"])
        else:
            refused_count += 1
            negative_reasons.add(actual[1])
    if observed_exits != set(EXIT_CLASSES):
        raise ValueError(f"exit coverage mismatch: {sorted(set(EXIT_CLASSES) - observed_exits)}")
    if observed_providers != set(PROVIDERS):
        raise ValueError("both providers must have an allowed conformance envelope")
    if not {"supported", "degraded", "unsupported", "unknown"}.issubset(observed_states):
        raise ValueError("support-state preservation coverage is incomplete")
    required_refusals = {
        "PRIVACY_REFUSED", "UNKNOWN_FIELD", "UNKNOWN_SCHEMA_VERSION", "LINKAGE_MISMATCH",
        "PROVIDER_EVIDENCE_MISMATCH", "DEGRADED_ROUTE_NOT_AUTHORIZED", "BUDGET_ENVELOPE_BYTES",
        "BUDGET_OUTPUT_BYTES", "BUDGET_EVENT_COUNT", "BUDGET_TURN_COUNT",
        "OUTPUT_SCHEMA_INVALID", "PROVIDER_PROTOCOL_UNKNOWN", "INTERNAL_VALIDATOR",
    }
    if not required_refusals.issubset(negative_reasons):
        raise ValueError(f"refusal coverage incomplete: {sorted(required_refusals - negative_reasons)}")
    return allowed_count, refused_count, len(cases)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--providers", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        contract_text = args.contract.read_text(encoding="utf-8")
        allowed, refused, total = validate_carriers(
            contract_text, _read_json(args.cases), _read_json(args.providers))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError) as error:
        print(f"worker-envelope: RED — {error}", file=sys.stderr)
        return 1
    print(
        "worker-envelope: OK — "
        f"{total} cases ({allowed} conforming, {refused} refused); "
        f"{len(EXIT_CLASSES)} exits; {len(EVENT_TYPES)} events; both providers; "
        "unknown/degraded/unsupported preserved; caps/linkage/privacy closed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
