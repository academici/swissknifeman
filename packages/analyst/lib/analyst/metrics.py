"""metrics — reliability metric arithmetic and paired digest (P3.2,
 P3.2).

Derives paired reliability metrics from committed `analyst.trace.TraceRecord`s and the
frozen P0.3 reliability bank (`artifacts/reliability-bank-v1/bank-manifest.json`) — never
from re-parsing provider logs a second way (`unified-agent-trace-v1.md` § Consumers). This
module owns metric arithmetic only: no trace schema (`analyst.trace` still owns
`TraceRecord`), no eval adapter, no canary dispatch.

Proof-class discipline (`source-evidence-verification-v1.md`, `reliability-acceptance-v1.md`):
a baseline whose `baseline_proof_class` is `pinned-not-recomputable`/`unknown` can never be
silently promoted to a recomputed comparator or GREEN predicate — `pair_metric`
enforces this rather than restating it in prose. The proof-class vocabulary is cited from
those two contracts, not imported: analyst does not depend on `task` hard (mirrors
`doctor.py`'s optional `task.route_evidence` check), and each contract owns its own closed
enum rather than sharing a runtime module across an unrelated boundary.

`project_id` slicing: the frozen `TraceRecord` (`unified-agent-trace-v1.md` § Field set) does
not carry `project_id` as a top-level field (only `trace_id`'s hash consumes it, one-way) —
widening that frozen schema for a slicing convenience would be a major bump for an unrelated
consumer's need. Callers here that want project slices pass `{"project_id": ..., "trace":
record}` entries: this module's own aggregation input, not a change to the frozen schema.
"""
import json

from .trace import SCHEMA_VERSION as TRACE_SCHEMA_VERSION
from .trace import dedup_records

SCHEMA_VERSION = "reliability-metrics-digest/v1"

# Closed proof-class vocabulary (source-evidence-verification-v1.md § Proof classes,
# reliability-acceptance-v1.md § proof-class rule) — cited here, not imported.
PROOF_CLASSES = frozenset(("recomputed", "cross-checked", "pinned-not-recomputable", "unknown"))
# The two classes a floor/metric may rest a deterministic acceptance predicate on.
COMPARABLE_PROOF_CLASSES = frozenset(("recomputed", "cross-checked"))
SLICE_AXES = frozenset(("project", "plan", "item"))


class MetricError(ValueError):
    """Base for every `METRIC_*` fail-closed condition this module raises."""


def build_metric_record(metric, *, numerator, denominator, baseline_proof_class,
                         exclusions=(), source_traces=(), note=None):
    """One `MetricRecord`: numerator/denominator/exclusions/completeness/source trace
    refs/baseline proof class — the exact shape Implementation Rules require for every
    metric this module emits. `source_traces` — zero or more `analyst.trace.TraceRecord`
    dicts this metric was derived from; empty for a bank-count metric that predates the
    trace instrument (completeness then reflects denominator presence, not trace quality).
    Resume/fork duplicates are collapsed via `analyst.trace.dedup_records` before being
    counted (Implementation Rules: "Resume/fork dedup is mandatory for candidate
    traces") — a caller never needs to dedup its own candidate trace list first.
    """
    if not isinstance(metric, str) or not metric:
        raise MetricError("METRIC_MISSING_ID: metric must be a non-empty string")
    if baseline_proof_class not in PROOF_CLASSES:
        raise MetricError(f"METRIC_UNKNOWN_PROOF_CLASS: '{baseline_proof_class}'")
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        raise MetricError("METRIC_NON_NUMERIC_INPUT: numerator/denominator must be numeric")
    if numerator < 0 or denominator < 0:
        raise MetricError("METRIC_NEGATIVE_INPUT: numerator/denominator must be >= 0")
    if denominator and numerator > denominator:
        raise MetricError("METRIC_NUMERATOR_EXCEEDS_DENOMINATOR")
    for trace in source_traces:
        if trace.get("schema_version") != TRACE_SCHEMA_VERSION:
            raise MetricError("METRIC_TRACE_SCHEMA_MISMATCH: source_traces must be "
                              f"'{TRACE_SCHEMA_VERSION}' records")
    source_traces = dedup_records(source_traces) if source_traces else source_traces

    value = (numerator / denominator) if denominator else None
    if source_traces:
        completeness = sum(t["quality"]["completeness"] for t in source_traces) / len(source_traces)
    else:
        completeness = 1.0 if denominator else 0.0
    return {
        "metric": metric,
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
        "exclusions": list(exclusions),
        "completeness": completeness,
        "source_trace_ids": [t["trace_id"] for t in source_traces],
        "baseline_proof_class": baseline_proof_class,
        "note": note,
    }


def pair_metric(baseline, candidate):
    """Pair a baseline `MetricRecord` against a candidate one, or `None` when the

    live paired run has not produced it yet — never a silent zero (Execution Rules:
    "Missing evidence/route/capability остаётся unknown/red... ноль и silent skip
    запрещены"). Layer-2 absence is reported as `status: "deferred"`, exactly what
    `bank-manifest.json::baseline_layers.layer-2-live-paired.status` already says
    ("required before any relative floor is claimed")."""
    if candidate is not None and baseline["metric"] != candidate["metric"]:
        raise MetricError("METRIC_MISMATCHED_PAIR: baseline/candidate metric ids differ")
    if candidate is None:
        return {"metric": baseline["metric"], "status": "deferred", "baseline": baseline,
                "candidate": None, "delta": None,
                "note": "layer-2 live paired run not yet produced (P3.3)"}
    if baseline["baseline_proof_class"] not in COMPARABLE_PROOF_CLASSES:
        raise MetricError(
            f"METRIC_PINNED_BASELINE_FORBIDDEN: '{baseline['metric']}' baseline is "
            f"{baseline['baseline_proof_class']!r}; cannot be a recomputed comparator (D30)")
    delta = None
    if baseline["value"] is not None and candidate["value"] is not None:
        delta = candidate["value"] - baseline["value"]
    return {"metric": baseline["metric"], "status": "paired", "baseline": baseline,
            "candidate": candidate, "delta": delta, "note": None}


def slice_by(entries, axis):
    """Group `{'project_id', 'plan_ref'?, 'trace'}`-shaped entries by `project`/`plan`/
    `item` — the three slice axes Scope Included names. `plan`/`item` come from the
    entry's `trace['plan_ref']` when present; both degrade to the `None` bucket rather
    than raising, mirroring the trace schema's own nullable `plan_ref`."""
    if axis not in SLICE_AXES:
        raise MetricError(f"METRIC_UNKNOWN_SLICE_AXIS: '{axis}'")
    groups = {}
    for entry in entries:
        groups.setdefault(_slice_key(entry, axis), []).append(entry)
    return groups


def _slice_key(entry, axis):
    if axis == "project":
        return entry.get("project_id")
    plan_ref = entry["trace"].get("plan_ref")
    if plan_ref is None:
        return None
    return plan_ref["plan_id"] if axis == "plan" else plan_ref["item_id"]


def find_anomalies(pairs, *, regression_tolerance=0.0):
    """Paired metrics whose candidate regressed past `regression_tolerance` below
    baseline — refs point at the exact contributing `trace_id`s, never a bare delta
    number without an anchor (§ «Якорь дерева для чисел»: a number is reproducible from
    its own cited source, here the trace ids that produced each side)."""
    anomalies = []
    for pair in pairs:
        if pair["status"] != "paired" or pair["delta"] is None:
            continue
        if pair["delta"] < -abs(regression_tolerance):
            anomalies.append({
                "metric": pair["metric"],
                "delta": pair["delta"],
                "baseline_trace_ids": pair["baseline"]["source_trace_ids"],
                "candidate_trace_ids": pair["candidate"]["source_trace_ids"],
            })
    return anomalies


def build_digest(pairs, *, generated_at, slices=None, regression_tolerance=0.0):
    """Compact paired reliability digest: frozen metric pairs, optional project/plan/item
    slice index, anomaly refs and an overall completeness figure — the one CLI/digest
    shape Code Guidance asks for (no dashboard, no ranking)."""
    if not isinstance(generated_at, str) or not generated_at.endswith("Z"):
        raise MetricError("METRIC_MISSING_TIMESTAMP: generated_at must be a UTC ISO-8601 string")
    completeness_values = [pair["baseline"]["completeness"] for pair in pairs]
    overall_completeness = (sum(completeness_values) / len(completeness_values)
                             if completeness_values else 0.0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "pairs": pairs,
        "slices": slices or {},
        "anomalies": find_anomalies(pairs, regression_tolerance=regression_tolerance),
        "overall_completeness": overall_completeness,
    }


def digest_to_json(digest):
    """Canonical byte-stable serialization — the same convention `analyst.trace.record_to_json`
    and `analyst.events.append_event` use (sorted keys, no ensure_ascii collapse)."""
    return json.dumps(digest, sort_keys=True, ensure_ascii=False)
