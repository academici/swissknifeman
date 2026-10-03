"""provider_trace — thin Unified Agent Trace v1 (P3.1,
) readers.

Maps an already-captured provider structure into the RAW payload keys
`analyst.trace.build_trace_record` consumes. Contains no validation and no
completeness math — those live only in `analyst.trace` (contract § Provider reader
boundary: "no normalization logic lives here"). stdlib-only, no import of `analyst`
(harness stays independently testable, mirroring the rest of the package)."""
import hashlib

PROVIDER_IDS = ("claude-code", "codex", "cursor", "grok")
READER_VERSION = "1.0.0"

# Same six nullable fields `analyst.trace` scores completeness over — kept here as a
# literal tuple (not imported) so this reader has zero dependency on `analyst`.
_NULLABLE_FIELDS = ("plan_ref", "contract_ref", "route", "dispatch", "public_outcome",
                    "finding_refs")


def _provenance(provider_id, raw_ref, source_bytes):
    return {
        "provider_id": provider_id,
        "raw_ref": raw_ref,
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reader_id": "harness.provider_trace",
        "reader_version": READER_VERSION,
    }


def _degrade_missing(raw, *, reason_fn):
    reasons = {}
    for name in _NULLABLE_FIELDS:
        value = raw[name]
        empty = value is None or (name == "finding_refs" and not value)
        if empty:
            reasons[name] = reason_fn(name)
    raw["reasons"] = reasons
    return raw


def build_claude_raw(run_report, *, raw_ref, occurred_at, source_bytes=None, plan_ref=None,
                     contract_ref=None, route=None, dispatch=None, finding_refs=None,
                     public_outcome=None):
    """Build a RAW Claude payload from an already-parsed SCHEMA=2 run-report dict
    (`packages/harness/configs/claude-code/hooks/run-report/_lib.py::parse_events`).

    `run_report` is consulted only for its presence/shape check — this reader does not
    re-parse it: the fields a `TraceRecord` needs beyond raw tool/file counts
    (`plan_ref`/`contract_ref`/`route`/`dispatch`/`public_outcome`) are caller-supplied,
    because inferring plan/contract/route linkage from tool-call shapes would duplicate
    logic `task.journal`/`task.route_evidence` already own."""
    if not isinstance(run_report, dict):
        raise ValueError("run_report must be a dict (harness run-report SCHEMA=2 shape)")
    raw = {
        "provenance": _provenance("claude-code", raw_ref, source_bytes or b""),
        "occurred_at": occurred_at,
        "plan_ref": plan_ref,
        "contract_ref": contract_ref,
        "route": route,
        "dispatch": dispatch,
        "finding_refs": list(finding_refs) if finding_refs else [],
        "public_outcome": public_outcome,
    }
    return _degrade_missing(raw, reason_fn=lambda name: f"{name}: not captured by this run-report dispatch")


def _build_unintegrated_raw(provider_id, *, raw_ref, occurred_at, source_bytes=None,
                            plan_ref=None, contract_ref=None, route=None, dispatch=None,
                            finding_refs=None, public_outcome=None, reason):
    raw = {
        "provenance": _provenance(provider_id, raw_ref, source_bytes or b""),
        "occurred_at": occurred_at,
        "plan_ref": plan_ref,
        "contract_ref": contract_ref,
        "route": route,
        "dispatch": dispatch,
        "finding_refs": list(finding_refs) if finding_refs else [],
        "public_outcome": public_outcome,
    }
    return _degrade_missing(raw, reason_fn=lambda _name: reason)


def build_codex_raw(*, raw_ref, occurred_at, source_bytes=None, plan_ref=None, contract_ref=None,
                    route=None, dispatch=None, finding_refs=None, public_outcome=None):
    """Build a RAW Codex payload. No Codex hook in this repository captures a
    structure comparable to the Claude run-report yet (contract § Boundaries) — every
    field the caller does not explicitly pass degrades to null +
    `codex-hook-not-integrated` rather than a guessed value. A caller that DOES supply
    a field (e.g. route captured from `-c model_reasoning_effort=...`) fills it exactly
    like the Claude reader — the degradation only covers what neither side captured."""
    return _build_unintegrated_raw(
        "codex", raw_ref=raw_ref, occurred_at=occurred_at, source_bytes=source_bytes,
        plan_ref=plan_ref, contract_ref=contract_ref, route=route, dispatch=dispatch,
        finding_refs=finding_refs, public_outcome=public_outcome,
        reason="codex-hook-not-integrated")


def build_grok_raw(*, raw_ref, occurred_at, source_bytes=None, plan_ref=None, contract_ref=None,
                   route=None, dispatch=None, finding_refs=None, public_outcome=None):
    """Grok lifecycle hooks are Codex-shaped; capture completeness follows the same
    unintegrated envelope until a dedicated run-report lands."""
    return _build_unintegrated_raw(
        "grok", raw_ref=raw_ref, occurred_at=occurred_at, source_bytes=source_bytes,
        plan_ref=plan_ref, contract_ref=contract_ref, route=route, dispatch=dispatch,
        finding_refs=finding_refs, public_outcome=public_outcome,
        reason="grok-hook-not-integrated")
