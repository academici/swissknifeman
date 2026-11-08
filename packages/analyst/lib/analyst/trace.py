"""trace — schema owner of Unified Agent Trace v1 (P3.1,
).

Links requirement→contract→route→dispatch→finding→public outcome into one record so
P3.2/P3.3 derive metrics from one instrument instead of re-parsing provider logs per
consumer. This is a DISTINCT schema from the D90 normalized analytics envelope
(`analyst.events`/`runs`/`readers`, `run_reports.EventEnvelope`) — different consumers,
different closed field set; the two are never merged (contract § Boundaries).

Provider readers (`harness.provider_trace`) build a RAW payload; this module owns all
validation, completeness/quality math, privacy fail-closed and resume/fork dedup.
stdlib-only."""
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "unified-agent-trace/v1"
PROVIDER_IDS = frozenset(("claude-code", "codex", "cursor", "grok", "antigravity"))
PRIVACY_EXCLUDED = ("raw_transcript", "chain_of_thought", "tool_payload", "secret")
DISPATCH_STATES = frozenset((
    "READY", "EXECUTING", "VERIFYING", "FIXING", "DONE", "INCIDENT",
    "OWNER_BOUNDARY", "ESCALATED", "SKIPPED",
))
DISPATCH_EVENTS = frozenset((
    "dispatch", "pre-mutation-allow", "pre-mutation-deny", "mutation-complete",
    "validation-green", "validation-red", "typed-finding", "same-finding-third",
    "pre-final-allow", "pre-final-deny", "close-committed", "audit-verdict",
    "owner-decision", "escalation-trigger", "skip-by-decision",
))
PUBLIC_OUTCOME_SCOPES = frozenset(("public", "internal"))

# Nullable top-level fields whose (non-)presence drives `quality.completeness` —
# `provenance`/`occurred_at`/`schema_version`/`trace_id` are never optional (contract
# § Field set: their absence is a build-time error, not a quality signal).
_NULLABLE_FIELDS = ("plan_ref", "contract_ref", "route", "dispatch", "public_outcome",
                    "finding_refs")
_TOP_FIELDS = frozenset((
    "schema_version", "trace_id", "provenance", "occurred_at", "plan_ref",
    "contract_ref", "route", "dispatch", "finding_refs", "public_outcome",
    "quality", "reasons", "privacy",
))
_PROVENANCE_FIELDS = frozenset(("provider_id", "raw_ref", "sha256", "reader_id", "reader_version"))
_SHA256_RE_LEN = 64
# Raw-input key names that plausibly carry an excluded privacy class (contract
# § Provenance and privacy) — refused outright, never silently redacted.
_PRIVACY_KEY_MARKERS = ("prompt", "reasoning", "chain_of_thought", "tool_input",
                        "tool_result", "secret", "token", "api_key")


class TraceError(ValueError):
    """Base for every `TRACE_*` fail-closed condition this module raises."""


def trace_id(provider_id, project_id, identity, turn_id):
    """Deterministic sha256 id — same natural key always yields the same id, the
    direct mechanism `dedup_records` relies on (contract § trace_id and resume/fork
    dedup)."""
    if not all(isinstance(v, str) and v for v in (provider_id, project_id, identity, turn_id)):
        raise TraceError("TRACE_MISSING_IDENTITY: provider_id/project_id/identity/turn_id "
                          "must be non-empty strings")
    key = f"provider_id={provider_id}|project_id={project_id}|identity={identity}|turn={turn_id}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _check_privacy(raw):
    def _walk(value, path):
        if isinstance(value, dict):
            for k, v in value.items():
                lowered = str(k).lower()
                if any(marker in lowered for marker in _PRIVACY_KEY_MARKERS):
                    raise TraceError(f"TRACE_PRIVACY_VIOLATION: excluded-class key "
                                     f"'{path}.{k}' present in raw input")
                _walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                _walk(v, f"{path}[{i}]")

    _walk(raw, "raw")


def _validate_provenance(provenance, source_bytes, declared_sha256):
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_FIELDS:
        raise TraceError("TRACE_MISSING_IDENTITY: provenance must carry exactly "
                         f"{sorted(_PROVENANCE_FIELDS)}")
    if provenance["provider_id"] not in PROVIDER_IDS:
        raise TraceError(f"TRACE_UNKNOWN_PROVIDER: '{provenance['provider_id']}'")
    if not all(isinstance(provenance[name], str) and provenance[name]
               for name in ("raw_ref", "sha256", "reader_id", "reader_version")):
        raise TraceError("TRACE_MISSING_IDENTITY: provenance fields must be non-empty strings")
    if len(provenance["sha256"]) != _SHA256_RE_LEN:
        raise TraceError("TRACE_CORRUPT_RECORD: provenance.sha256 must be a sha256 hex digest")
    if source_bytes is not None:
        computed = hashlib.sha256(source_bytes).hexdigest()
        declared = declared_sha256 if declared_sha256 is not None else provenance["sha256"]
        if computed != declared:
            raise TraceError("TRACE_CORRUPT_RECORD: declared sha256 does not match source bytes")


def _validate_dispatch(dispatch):
    if dispatch is None:
        return
    if not isinstance(dispatch, dict) or set(dispatch) != {"state", "event"}:
        raise TraceError("TRACE_CORRUPT_RECORD: dispatch must carry exactly state/event")
    if dispatch["state"] not in DISPATCH_STATES:
        raise TraceError(f"TRACE_CORRUPT_RECORD: unknown dispatch.state '{dispatch['state']}'")
    if dispatch["event"] not in DISPATCH_EVENTS:
        raise TraceError(f"TRACE_CORRUPT_RECORD: unknown dispatch.event '{dispatch['event']}'")


def _validate_public_outcome(public_outcome):
    if public_outcome is None:
        return
    if not isinstance(public_outcome, dict) or set(public_outcome) != {"scope", "check", "evidence_ref"}:
        raise TraceError("TRACE_CORRUPT_RECORD: public_outcome must carry exactly "
                         "scope/check/evidence_ref")
    if public_outcome["scope"] not in PUBLIC_OUTCOME_SCOPES:
        raise TraceError("TRACE_CORRUPT_RECORD: public_outcome.scope must be public|internal")


def build_trace_record(raw, *, provider_id, project_id, identity, turn_id,
                       source_bytes=None, declared_sha256=None):
    """Build and validate one closed-schema `TraceRecord` from a provider RAW payload.

    `raw` carries the nullable fields this record may fill (`plan_ref`, `contract_ref`,
    `route`, `dispatch`, `finding_refs`, `public_outcome`) plus `provenance`/
    `occurred_at`/`reasons` for whichever of those the reader could not fill. Every
    field absent from `raw` degrades to `null` + an explicit reason rather than being
    silently omitted (Scope Included: "Missing fields remain null with reason/quality").
    """
    if not isinstance(raw, dict):
        raise TraceError("TRACE_CORRUPT_RECORD: raw payload must be a dict")
    _check_privacy(raw)

    provenance = raw.get("provenance")
    _validate_provenance(provenance, source_bytes, declared_sha256)
    if provenance["provider_id"] != provider_id:
        raise TraceError("TRACE_UNKNOWN_PROVIDER: provenance.provider_id does not match "
                         "the declared provider_id")

    occurred_at = raw.get("occurred_at")
    if not isinstance(occurred_at, str) or not occurred_at.endswith("Z"):
        raise TraceError("TRACE_MISSING_IDENTITY: occurred_at must be a UTC ISO-8601 string")

    dispatch = raw.get("dispatch")
    _validate_dispatch(dispatch)
    public_outcome = raw.get("public_outcome")
    _validate_public_outcome(public_outcome)
    finding_refs = raw.get("finding_refs") or []
    if not isinstance(finding_refs, list) or not all(isinstance(f, str) and f for f in finding_refs):
        raise TraceError("TRACE_CORRUPT_RECORD: finding_refs must be a list of non-empty strings")

    reasons_in = raw.get("reasons") or {}
    if not isinstance(reasons_in, dict):
        raise TraceError("TRACE_CORRUPT_RECORD: reasons must be a dict")

    record = {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id(provider_id, project_id, identity, turn_id),
        "provenance": dict(provenance),
        "occurred_at": occurred_at,
        "plan_ref": raw.get("plan_ref"),
        "contract_ref": raw.get("contract_ref"),
        "route": raw.get("route"),
        "dispatch": dispatch,
        "finding_refs": list(finding_refs),
        "public_outcome": public_outcome,
        "privacy": {"excluded": list(PRIVACY_EXCLUDED)},
    }

    missing = sorted(name for name in _NULLABLE_FIELDS
                     if (record[name] is None) or (name == "finding_refs" and not record[name]))
    reasons = {}
    for name in missing:
        reason = reasons_in.get(name)
        if not isinstance(reason, str) or not reason:
            raise TraceError(f"TRACE_MISSING_IDENTITY: missing field '{name}' has no reason")
        reasons[name] = reason

    total = len(_NULLABLE_FIELDS)
    present = total - len(missing)
    record["quality"] = {
        "completeness": present / total,
        "missing": missing,
        "degraded": bool(missing),
    }
    record["reasons"] = reasons

    assert set(record) == _TOP_FIELDS  # closed set — a code defect if this ever trips
    _validate_record(record)
    return record


def _validate_record(record):
    """Refuse a record the unified-agent-trace schema does not accept."""
    from aicore.util.schema import load_contract, validate
    directory = Path(__file__).resolve().parents[2] / "schemas" / "unified-agent-trace" / "v1"
    registry, kind = load_contract(directory, urn_prefix="urn:swissknifeman:analyst:")
    issues = validate(record, kind, registry)
    if issues:
        raise TraceError("TRACE_SCHEMA_INVALID: " + "; ".join(issue.message for issue in issues[:5]))


def dedup_records(records):
    """Resume/fork dedup by `trace_id`: keep the higher-completeness record per id
    (ties keep the first-seen), never a field-level merge (contract § trace_id and
    resume/fork dedup — merging would hide which provenance produced which field)."""
    best = {}
    order = []
    for record in records:
        tid = record["trace_id"]
        if tid not in best:
            order.append(tid)
            best[tid] = record
        elif record["quality"]["completeness"] > best[tid]["quality"]["completeness"]:
            best[tid] = record
    return [best[tid] for tid in order]


def record_to_json(record):
    """Canonical byte-stable serialization (sorted keys, no ensure_ascii collapse of
    provenance strings) — the same convention `analyst.events.append_event` uses."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False)
