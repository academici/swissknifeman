"""route_evidence — normalized route/budget evidence (2026.07.24-AGENT-RELIABILITY P2.4).

Captures what a dispatch ACTUALLY ran under — model class, effort, capability
support, token/duration/tool-call budget — as evidence carrying its own source and
timestamp, never inferred from static config, an actor string or the requested model
(`phases/P2.md` P2.4 Code Guidance). `findings/02-telemetry-2026-07-20-24.md`: actor
has 34 observed spellings and no live effort signal, so item compliance was not
reproducible from prose — this module is the typed replacement.

Layered strictly UPSTREAM of `task.task_contract.pre_mutation` (2026.07.24-AGENT-RELIABILITY P2.2, frozen): that
predicate's own route check assumes an already-resolved `route` (`.index()` lookups
that crash on `None`), so `dispatch_guard` below is the fail-closed boundary that
never lets an `unknown` axis reach it — a guard refusal here stops before any Task
Contract compiles. `build_task_contract_route` only assembles the exact
`root/contracts/task-contract-v1.schema.json` `$defs/route` shape (`required`/
`actual`/`capabilities`, `additionalProperties: false`) once the guard already
allowed; it is a repeat proof over validated axes, not a second gate.

Reuses `task.task_contract.MODEL_CLASS_ORDER`/`EFFORT_ORDER` (frozen 2026.07.24-AGENT-RELIABILITY P0.2 route
ladder, D6 single owner — never re-declared) for classification, and
`task.command_catalog.CommandRecord` for the deterministic REQUIRED side
(`command-routing.json`, 2026.07.24-AGENT-RELIABILITY P1/P2.2 — unmodified by this item: its exact-set schema is
owned by `command_catalog.py`, outside this item's Files).

stdlib-only.
"""
from __future__ import annotations

from task.command_catalog import CommandRecord
from task.task_contract import EFFORT_ORDER, MODEL_CLASS_ORDER

try:
    # core.term.now_iso — same format journal.py pins (`2026-07-18T18:42:07Z`).
    from core.term import now_iso as _now_iso
except ImportError:  # pragma: no cover - standalone fallback, byte-identical to journal.py
    from datetime import datetime, timezone

    def _now_iso():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# §Scope — evidence provenance a captured ACTUAL route may declare. Never "requested"
# or "config": those are exactly the static-config/actor-string stand-ins Code
# Guidance forbids for a live actual.
SOURCES = ("self-attested", "provider-doctor", "cli-flag")

# Usage/context budget axes — token/duration/tool counts only, no pricing (Code
# Guidance). Naming matches `analyst.readers` `usage.totals` keys (`in`/`out`/
# `cache_read`/`cache_creation`) so this item's Pending Work (P3 Unified Trace) can
# consume both without a translation layer.
BUDGET_AXES = ("in", "out", "cache_read", "cache_creation", "duration_ms", "tool_calls")

CLASSIFICATIONS = ("exact", "over", "under", "unknown")

# execution-state-machine-v1.md §Declared sets — the `route` deny class partitions
# exactly these two frozen 2026.07.24-AGENT-RELIABILITY P0.2 pre-mutation codes (never re-minted here).
ROUTE_UNDERSHOOT = "ROUTE_UNDERSHOOT"
CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"


class RouteEvidenceError(ValueError):
    """A refusal named by its own typed reason code — never a silent downgrade."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def required_route(record: CommandRecord, *, inherited_minimum: tuple | None = None) -> dict:
    """The REQUIRED side, deterministic — never self-reported. `fixed` mode reads
    `record.routing` (`command-routing.json`); `inherited-plan` mode (`task:plan-run`)
    carries no fixed axes of its own (`command_catalog._routing` already enforces
    `routing-required`/`routing-required` there) and must receive the plan item's own
    §3 Routing minimum — the same value `command_render.plan_provider_invocation`
    requires as `inherited_minimum`. A `fixed` record must not also receive one: the
    two derivations never mix."""
    mode = record.routing.mode
    if mode == "inherited-plan":
        if inherited_minimum is None:
            raise RouteEvidenceError(
                "ROUTE_REQUIRED_UNRESOLVED",
                f"{record.command_id}: inherited-plan routing needs the plan item's "
                "§3 Routing minimum")
        model_class, effort = inherited_minimum
    elif mode == "fixed":
        if inherited_minimum is not None:
            raise RouteEvidenceError(
                "ROUTE_REQUIRED_UNRESOLVED",
                f"{record.command_id}: fixed routing does not take an inherited minimum")
        model_class, effort = record.routing.model_class, record.routing.effort
    else:  # pragma: no cover - command_catalog already rejects unknown modes at load
        raise RouteEvidenceError("ROUTE_REQUIRED_UNRESOLVED", f"unknown routing mode {mode!r}")
    if model_class not in MODEL_CLASS_ORDER or effort not in EFFORT_ORDER:
        raise RouteEvidenceError(
            "ROUTE_REQUIRED_UNRESOLVED",
            f"{record.command_id}: required route {model_class!r}/{effort!r} is "
            "outside the frozen ladder")
    return {"model_class": model_class, "effort": effort, "source": "command-routing.json", "ts": None}


def capture_actual(model_class, effort, *, source: str, ts: str | None = None,
                   model: str | None = None) -> dict:
    """The ACTUAL side — supplied by the caller from one named, real source. Never
    inferred here: an omitted axis (`None`) is evidence of absence, not a guess, and
    survives unchanged into `classify`/`dispatch_guard` as `unknown`.

    `model` (2026.07.24-AGENT-RELIABILITY P2.6/D72) — optional concrete provider model name (e.g. `"sonnet"`),
    a SEPARATE axis from `model_class`: the class stays the frozen 2026.07.24-AGENT-RELIABILITY P0.2 route axis
    `dispatch_guard`/`classify` compare against Required; `model` is new evidence
    `canonical_actor` reads instead of stripping the actor spelling down to the
    class (F8 — `required` and `actual` had collapsed to the same string once the
    class was all `canonical_actor` had to work with)."""
    if source not in SOURCES:
        raise RouteEvidenceError(
            "ROUTE_ACTUAL_SOURCE_UNDECLARED", f"undeclared route evidence source {source!r}")
    for axis, value, ladder in (("model_class", model_class, MODEL_CLASS_ORDER),
                               ("effort", effort, EFFORT_ORDER)):
        if value is not None and value not in ladder:
            raise RouteEvidenceError(
                "ROUTE_ACTUAL_SOURCE_UNDECLARED",
                f"actual {axis} {value!r} is outside the frozen ladder")
    return {"model_class": model_class, "effort": effort, "source": source,
           "ts": ts or _now_iso(), "model": model}


def classify(required: dict, actual: dict) -> str:
    """Four-way descriptive label (`exact/over/under/unknown`, Scope Included) —
    reporting/telemetry only, distinct from `dispatch_guard`'s two-code fail-closed
    verdict below. `unknown` wins over every other axis call (one axis never
    compensates the other, Code Guidance): an unresolved model class does not let a
    generous effort call the whole route "over"."""
    axis_calls = []
    for axis, ladder in (("model_class", MODEL_CLASS_ORDER), ("effort", EFFORT_ORDER)):
        act = actual[axis]
        if act is None or act not in ladder:
            axis_calls.append("unknown")
            continue
        req_rank, act_rank = ladder.index(required[axis]), ladder.index(act)
        axis_calls.append("exact" if act_rank == req_rank else "over" if act_rank > req_rank else "under")
    if "unknown" in axis_calls:
        return "unknown"
    if "under" in axis_calls:
        return "under"
    if "over" in axis_calls:
        return "over"
    return "exact"


def capability_support(capability_requirements, capability_bindings) -> tuple:
    """`route.capabilities` (`task-contract-v1.schema.json` `$defs/route`) — one
    `{"id", "support"}` entry per required capability, `support` read from the acting
    provider's binding or `"unsupported"` when the provider declares none (never
    inferred as `"native"` by absence)."""
    bindings = dict(capability_bindings)
    return tuple({"id": name, "support": bindings.get(name, "unsupported")}
                for name in capability_requirements)


def dispatch_guard(required: dict, actual: dict, capabilities) -> str | None:
    """Fail-closed BEFORE any Task Contract compiles. Reuses the two frozen 2026.07.24-AGENT-RELIABILITY P0.2
    `route` deny codes verbatim (`execution-state-machine-v1.md` §Declared sets,
    never re-minted): `ROUTE_UNDERSHOOT` for an under OR unknown axis — "Missing
    actual effort is unknown and fails a route-required dispatch" (Implementation
    Rules) — `CAPABILITY_UNSUPPORTED` for any capability the acting provider does not
    bind as `native`/`adapted`. Route is checked first (task_contract.pre_mutation's
    own declared order: route before capability, both before authority)."""
    if classify(required, actual) in ("under", "unknown"):
        return ROUTE_UNDERSHOOT
    for capability in capabilities:
        if capability["support"] not in ("native", "adapted"):
            return CAPABILITY_UNSUPPORTED
    return None


def route_change_boundary(before: dict, after: dict) -> dict:
    """Detects a mid-item route change between two `capture_actual` evidence records
    (e.g. a session model/effort switch between an item's dispatch capture and a
    later re-check). Evidence only, no new machine event: the frozen state machine
    (2026.07.24-AGENT-RELIABILITY P2.1) owns transitions — this returns the comparison a caller reports against
    it, never a decision of its own."""
    changed = (before["model_class"], before["effort"]) != (after["model_class"], after["effort"])
    return {"changed": changed, "before": dict(before), "after": dict(after)}


def capture_budget(**axes) -> dict:
    """Token/duration/tool-call evidence only — no pricing (Code Guidance). An
    undeclared key (e.g. a cost field) or a negative/non-numeric count fails closed
    rather than silently dropping or clamping. Omitted axes are `None` (evidence of
    absence), matching `capture_actual`."""
    unknown = sorted(set(axes) - set(BUDGET_AXES))
    if unknown:
        raise RouteEvidenceError(
            "ROUTE_BUDGET_AXIS_UNKNOWN", f"not a declared budget axis: {unknown}")
    for name, value in axes.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or value < 0):
            raise RouteEvidenceError(
                "ROUTE_BUDGET_AXIS_UNKNOWN", f"{name}: must be a non-negative number, got {value!r}")
    return {axis: axes.get(axis) for axis in BUDGET_AXES}


def canonical_actor(model, effort) -> str:
    """The one canonical `<model>/<effort>` journal `actor` spelling (D72/F8
    repair of `findings/02`'s 34 observed spellings). `model_class` remains a
    SEPARATE route-evidence axis (`capture_actual`'s own field, `route.actual.
    model_class` in the compiled contract) — this function never derives a
    model from it: that was exactly F8 (`journal.jsonl` 2026.07.24-AGENT-RELIABILITY P2.4/P2.5 rows carry
    `"implementation/high"` instead of `"sonnet/high"` — `required` and
    `actual` collapsed to the same string once the class was all this
    function had). An absent or non-string `model` renders the literal
    `unknown` — the same principle `effort` already uses — never a class
    substituted for a missing model.

    Breaking signature change (D23/D72): the ONE internal consumer,
    `journal.py --route-evidence`, is repaired in this same item (2026.07.24-AGENT-RELIABILITY P2.6)."""
    model_part = model if isinstance(model, str) and model else "unknown"
    effort_part = effort if effort in EFFORT_ORDER else "unknown"
    return f"{model_part}/{effort_part}"


def build_task_contract_route(required: dict, actual: dict, capabilities) -> dict:
    """Assembles the exact `route` shape `task-contract-v1.schema.json` `$defs/route`
    declares (`required`/`actual` each exactly `{model_class, effort}`,
    `capabilities` a list of `{id, support}` — `additionalProperties: false`
    throughout). Callers MUST run `dispatch_guard` first and only call this once it
    returned `None`; this is a repeat proof over already-validated axes, never the
    fail-closed boundary itself."""
    return {
        "required": {"model_class": required["model_class"], "effort": required["effort"]},
        "actual": {"model_class": actual["model_class"], "effort": actual["effort"]},
        "capabilities": [{"id": c["id"], "support": c["support"]} for c in capabilities],
    }


# --------------------------------------------------------------------------
# CLI — `python3 -m task.route_evidence capture|guard …`
# --------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    import json
    from pathlib import Path
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Route/budget evidence (P2.4) — capture an actual route or evaluate the "
                    "dispatch guard over required/actual evidence files.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="print one capture_actual() evidence record")
    cap.add_argument("--model-class", required=True, choices=MODEL_CLASS_ORDER)
    cap.add_argument("--effort", required=True, choices=EFFORT_ORDER)
    cap.add_argument("--source", required=True, choices=SOURCES)
    cap.add_argument("--ts", default=None)

    guard = sub.add_parser("guard", help="evaluate dispatch_guard over required/actual evidence files")
    guard.add_argument("--required", required=True, help="path to a required_route() JSON")
    guard.add_argument("--actual", required=True, help="path to a capture_actual() JSON")
    guard.add_argument("--capability", action="append", default=[],
                       help="id=support (native|adapted|unsupported), repeatable")

    args = parser.parse_args(argv)
    if args.cmd == "capture":
        evidence = capture_actual(args.model_class, args.effort, source=args.source, ts=args.ts)
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd != "guard":  # pragma: no cover - argparse already gates choices
        return 1
    required = _load_json(args.required)
    actual = _load_json(args.actual)
    capabilities = []
    for pair in args.capability:
        name, _, support = pair.partition("=")
        capabilities.append({"id": name, "support": support})
    code = dispatch_guard(required, actual, capabilities)
    print(json.dumps({"classification": classify(required, actual),
                      "dispatch_guard": code or "allow"}, ensure_ascii=False, sort_keys=True))
    return 0 if code is None else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
