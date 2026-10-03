"""route_evidence — normalized route/budget evidence.

Captures what a dispatch ACTUALLY ran under — model class, effort, capability
support, token/duration/tool-call budget — as evidence carrying its own source and
timestamp, never inferred from static config, an actor string or the requested model
(`phases/P2.md` P2.4 Code Guidance). `findings/02-telemetry-2026-07-20-24.md`: actor
has 34 observed spellings and no live effort signal, so item compliance was not
reproducible from prose — this module is the typed replacement.

Layered strictly UPSTREAM of `task.task_contract.pre_mutation`: that
predicate's own route check assumes an already-resolved `route` (`.index()` lookups
that crash on `None`), so `dispatch_guard` below is the fail-closed boundary that
never lets an `unknown` axis reach it — a guard refusal here stops before any Task
Contract compiles. `build_task_contract_route` only assembles the exact
`root/contracts/task-contract-v1.schema.json` `$defs/route` shape (`required`/
`actual`/`capabilities`, `additionalProperties: false`) once the guard already
allowed; it is a repeat proof over validated axes, not a second gate.

Reuses `task.task_contract.MODEL_CLASS_ORDER`/`EFFORT_ORDER` (frozen route
ladder, D6 single owner — never re-declared) for classification, and
`task.command_catalog.CommandRecord` for the deterministic REQUIRED side
(`command-routing.json`, — unmodified by this item: its exact-set schema is
owned by `command_catalog.py`, outside this item's Files).

stdlib-only.
"""
from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from core.provider.projection import load_projection_catalog, projection_spec
from core.provider.values import ProviderId
from task.command_catalog import CommandRecord
from task.task_contract import EFFORT_ORDER, MODEL_CLASS_ORDER

try:
    # core.term.now_iso — same format journal.py pins (`2026-07-18T18:42:07Z`).
    from core.term import now_iso as _now_iso
except ImportError:  # pragma: no cover - standalone fallback, byte-identical to journal.py
    from datetime import datetime, timezone

    def _now_iso():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# §Scope — evidence provenance a captured ACTUAL route may declare. Static config
# alone never proves a live route; `provider-thread-state` is different because it
# is selected by the current provider thread identity and records the active turn.
# `self-attested` is restricted to unknown axes: it records absent provider evidence
# and never turns a selector into proof of the route that actually ran.
SOURCES = (
    "self-attested", "provider-doctor", "provider-config", "cli-flag",
    "provider-thread-state", "provider-attestation",
)

# Usage/context budget axes — token/duration/tool counts only, no pricing (Code
# Guidance). Naming matches `analyst.readers` `usage.totals` keys (`in`/`out`/
# `cache_read`/`cache_creation`) so this item's Pending Work (P3 Unified Trace) can
# consume both without a translation layer.
BUDGET_AXES = ("in", "out", "cache_read", "cache_creation", "duration_ms", "tool_calls")

CLASSIFICATIONS = ("exact", "over", "under", "unknown")

# execution-state-machine-v1.md §Declared sets — the `route` deny class partitions
# exactly these two frozen pre-mutation codes (never re-minted here).
ROUTE_UNDERSHOOT = "ROUTE_UNDERSHOOT"
ROUTE_UNVERIFIABLE = "ROUTE-UNVERIFIABLE"
CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"

ATTESTATION_SCHEMA = "provider-attestation/v1"
ATTESTATION_BOUNDARIES = ("workflow-guard", "security-boundary")
_ATTESTATION_FIELDS = frozenset({
    "schema_version", "boundary", "issuer", "provider", "subject", "command",
    "arguments", "cwd", "plan_id", "item_id", "action_digest", "issued_at",
    "expires_at", "nonce", "proof", "adapter_version",
})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class RouteEvidenceError(ValueError):
    """A refusal named by its own typed reason code — never a silent downgrade."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def resolve_model_class(provider: str, model: str, metadata: dict) -> str:
    """Class of an actual model from the provider pool (`model_inventory.entries`).

    The pool is the one place models are listed. A model matches by class pin, id,
    `aliases` or regex `patterns`; roles may overlap, and the admitted class is the
    highest class among its roles, so a stronger model never trips a lower-class
    plan. A model absent from the pool is `ROUTE_MODEL_UNKNOWN` (nonterminal
    evidence-missing): add it to `command-routing.json`, do not rewrite the plan.
    """
    mapping = metadata.get("mappings", {}).get(provider, {})
    classes = set()
    for model_class, selectors in mapping.get("class_selectors", {}).items():
        if model in selectors:
            classes.add(model_class)
    for entry in mapping.get("model_inventory", {}).get("entries", ()):
        if entry.get("status") == "retired":
            continue  # out of the current pool; flip status instead of editing plans
        if (model == entry.get("id") or model in entry.get("aliases", ())
                or any(re.fullmatch(pattern, model, re.IGNORECASE)
                       for pattern in entry.get("patterns", ()))):
            classes.update(role for role in entry.get("roles", ()) if role in MODEL_CLASS_ORDER)
    classes &= set(MODEL_CLASS_ORDER)
    if not classes:
        raise RouteEvidenceError(
            "ROUTE_MODEL_UNKNOWN",
            f"{provider} model {model!r} is not in the model pool; add it to "
            "packages/task/configs/command-routing.json model_inventory")
    return max(classes, key=MODEL_CLASS_ORDER.index)


def proc_parent_argv(pid: int, *, label: str) -> tuple[int, tuple[str, ...]]:
    """Read one ``/proc`` parent and argv. Adapters share this; the label names the provider."""
    root = Path("/proc") / str(pid)
    try:
        status = (root / "status").read_text(encoding="utf-8")
        raw_argv = (root / "cmdline").read_bytes()
    except OSError as error:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"{label} process ancestry is unreadable: {error}") from error
    parent = None
    for line in status.splitlines():
        if line.startswith("PPid:"):
            _, value = line.split(":", 1)
            parent = int(value.strip())
            break
    argv = tuple(
        value.decode("utf-8", errors="surrogateescape")
        for value in raw_argv.split(b"\0") if value
    )
    if parent is None or not argv:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"process {pid} has no readable parent/argv")
    return parent, argv


def launch_option_values(argv: tuple[str, ...], short: str, long: str) -> tuple[str, ...]:
    """Collect ``-m`` / ``--model`` style values, including ``--model=value``."""
    values = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in (short, long):
            if index + 1 >= len(argv):
                raise RouteEvidenceError(
                    "ROUTE_LAUNCH_MISMATCH", f"launch option {token} has no value")
            values.append(argv[index + 1])
            index += 2
            continue
        if long and token.startswith(long + "="):
            values.append(token.split("=", 1)[1])
        index += 1
    return tuple(values)


def exactly_one(values: tuple[str, ...], label: str) -> str:
    if len(values) != 1:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", f"expected exactly one {label}, observed {len(values)}")
    return values[0]


def mapped_model_class(provider: str, model: str, routing_path: Path) -> str:
    from task.command_catalog import load_routing_metadata

    return resolve_model_class(provider, model, load_routing_metadata(routing_path))


def mapped_effort(provider: str, selector: str, routing_path: Path, *, label: str) -> str:
    from task.command_catalog import load_routing_metadata

    metadata = load_routing_metadata(routing_path)
    mapping = metadata.get("mappings", {}).get(provider, {})
    matches = [
        effort
        for effort, selectors in mapping.get("effort_selectors", {}).items()
        if selector in selectors
    ]
    return exactly_one(tuple(matches), f"{label} effort mapping for {selector!r}")


def invocation_extends(actual: str, expected: str) -> bool:
    """True when ``actual`` is ``expected`` or ``expected`` plus a whitespace continuation."""
    if actual == expected:
        return True
    if not actual.startswith(expected):
        return False
    rest = actual[len(expected):]
    return bool(rest) and rest[0].isspace()


def owner_followup_revokes(text: str) -> bool:
    """Conservative explicit stop/revoke markers for the local workflow guard."""
    return bool(re.search(r"OWNER-REVOKE|\b(?:revoke|cancel|stop)\b|review only|review|cancel|cancel|stop|stop|review only|do not execute", text, re.IGNORECASE))


def build_owner_attestation(evidence: dict, *, provider: str, plan_id: str,
                            item_id: str, action_digest: str, audience: str,
                            expires_at: str, nonce: str) -> dict:
    """Normalize local provider evidence without overstating its trust boundary.

    Current Codex/Claude adapters read agent-accessible local state.  Their output is
    therefore useful for workflow continuity but can never become a protected owner
    assertion merely because it has a digest.  A future provider adapter may return a
    security-boundary envelope only through ``verify_owner_attestation`` with an
    independent verifier and nonce consumer.
    """
    required = {
        "source", "source_version", "thread_id", "cwd", "invocation", "ts",
        "owner_message_digest",
    }
    if not isinstance(evidence, dict) or not required <= set(evidence):
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "provider evidence is incomplete")
    invocation = evidence["invocation"]
    if not isinstance(invocation, str) or not invocation:
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "invocation is absent")
    command, _, arguments = invocation.removeprefix("$ ").removeprefix("/").partition(" ")
    if not command.startswith("task:") or not arguments:
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "invocation is not a Task command")
    values = (provider, plan_id, item_id, audience, expires_at, nonce)
    if any(not isinstance(value, str) or not value for value in values) \
            or not _DIGEST_RE.fullmatch(str(action_digest)):
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "attestation binding is incomplete")
    return {
        "schema_version": ATTESTATION_SCHEMA,
        "boundary": "workflow-guard",
        "issuer": f"local:{evidence['source']}",
        "provider": provider,
        "subject": {"session_id": evidence["thread_id"],
                    "owner_message_digest": evidence["owner_message_digest"],
                    "audience": audience},
        "command": command,
        "arguments": arguments,
        "cwd": evidence["cwd"],
        "plan_id": plan_id,
        "item_id": item_id,
        "action_digest": action_digest,
        "issued_at": evidence["ts"],
        "expires_at": expires_at,
        "nonce": nonce,
        "proof": None,
        "adapter_version": evidence["source_version"],
    }


def verify_owner_attestation(attestation: dict, *, expected: dict,
                             verifier=None, nonce_consumer=None,
                             now: datetime | None = None,
                             protected: bool = True) -> dict:
    """Verify exact binding; protected mode requires an out-of-principal adapter.

    ``verifier`` and ``nonce_consumer`` are provider-owned callables.  Task never
    manufactures a signing key or silently substitutes its local durable store for a
    provider nonce service.
    """
    if (not isinstance(attestation, dict) or set(attestation) != _ATTESTATION_FIELDS
            or attestation.get("schema_version") != ATTESTATION_SCHEMA
            or attestation.get("boundary") not in ATTESTATION_BOUNDARIES):
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "unsupported exact envelope")
    subject = attestation.get("subject")
    if (not isinstance(subject, dict)
            or set(subject) != {"session_id", "owner_message_digest", "audience"}
            or any(not isinstance(subject.get(field), str) or not subject[field]
                   for field in ("session_id", "owner_message_digest", "audience"))
            or not _DIGEST_RE.fullmatch(subject["owner_message_digest"])
            or any(not isinstance(attestation.get(field), str) or not attestation[field]
                   for field in ("issuer", "provider", "command", "arguments", "cwd",
                                 "plan_id", "item_id", "action_digest", "nonce",
                                 "adapter_version"))
            or not _DIGEST_RE.fullmatch(attestation["action_digest"])):
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "attestation fields are malformed")
    for field in ("provider", "cwd", "plan_id", "item_id", "action_digest"):
        if attestation.get(field) != expected.get(field):
            raise RouteEvidenceError("OWNER_ATTESTATION_MISMATCH", f"{field} changed")
    if attestation.get("command") != expected.get("command") \
            or attestation.get("arguments") != expected.get("arguments"):
        raise RouteEvidenceError("OWNER_ATTESTATION_MISMATCH", "command binding changed")
    for field in ("session_id", "owner_message_digest", "audience"):
        if subject[field] != expected.get(field):
            raise RouteEvidenceError("OWNER_ATTESTATION_MISMATCH", f"subject.{field} changed")
    try:
        issued = datetime.strptime(attestation["issued_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        expires = datetime.strptime(attestation["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise RouteEvidenceError("OWNER_ATTESTATION_INVALID", "attestation time is invalid") from exc
    observed = now or datetime.now(timezone.utc)
    if expires <= issued or observed < issued or observed >= expires:
        raise RouteEvidenceError("OWNER_ATTESTATION_EXPIRED", "attestation is outside its validity window")
    if protected:
        if attestation["boundary"] != "security-boundary" or verifier is None or nonce_consumer is None:
            raise RouteEvidenceError(
                "OWNER_ATTESTATION_UNSUPPORTED",
                "protected mode requires provider proof and an independent nonce store",
            )
        if (attestation["issuer"] != f"provider:{attestation['provider']}"
                or not isinstance(attestation["proof"], str) or not attestation["proof"]):
            raise RouteEvidenceError(
                "OWNER_ATTESTATION_INVALID", "protected proof has no provider-owned issuer")
        if not verifier(attestation):
            raise RouteEvidenceError("OWNER_ATTESTATION_FORGED", "provider proof rejected")
        if not nonce_consumer(attestation["issuer"], attestation["nonce"],
                              attestation["action_digest"]):
            raise RouteEvidenceError("OWNER_ATTESTATION_REPLAYED", "nonce was already consumed")
    elif attestation["boundary"] != "workflow-guard" or attestation["proof"] is not None \
            or not attestation["issuer"].startswith("local:"):
        raise RouteEvidenceError(
            "OWNER_ATTESTATION_INVALID", "workflow guard must carry local unsigned provenance")
    return {"verified": True, "boundary": attestation["boundary"],
            "action_digest": attestation["action_digest"]}


def provider_owner_verification(provider: str):
    """Return a provider-owned verifier/nonce consumer, or an unsupported pair.

    Local Task state must not register these functions.  A provider adapter may add
    them only when the provider exposes an out-of-agent verification channel.
    """
    module_name = {"codex": "task.route_evidence_codex",
                   "claude-code": "task.route_evidence_claude"}.get(provider)
    if module_name is None:
        return None, None
    adapter = importlib.import_module(module_name)
    return (getattr(adapter, "verify_owner_attestation", None),
            getattr(adapter, "consume_owner_nonce", None))


def authority_preflight(boundary: str, *, provider: str | None = None) -> tuple:
    """Check capability before asking for an owner invocation or writing carriers."""
    if boundary == "owner-session":
        return None, None
    if boundary != "provider-proof":
        raise RouteEvidenceError("AUTHORITY_BOUNDARY", "unknown boundary authority")
    if provider is None:
        from task.session_context import resolve, SessionContextError
        try:
            provider = resolve().provider
        except SessionContextError as exc:
            raise RouteEvidenceError("AUTHORITY_PROVIDER_UNAVAILABLE", str(exc)) from exc
    verifier, consumer = provider_owner_verification(provider)
    if not callable(verifier) or not callable(consumer):
        raise RouteEvidenceError(
            "AUTHORITY_PROVIDER_UNAVAILABLE",
            "provider-proof requires external verifier and nonce store; connect approval channel "
            "or declare separately local-source item with owner-session. New session capability will not add")
    return verifier, consumer


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

    `model` — optional concrete provider model name (e.g. `"sonnet"`),
    a SEPARATE axis from `model_class`: the class stays the frozen route axis
    `dispatch_guard`/`classify` compare against Required; `model` is new evidence
    `canonical_actor` reads instead of stripping the actor spelling down to the
    class (F8 — `required` and `actual` had collapsed to the same string once the
    class was all `canonical_actor` had to work with)."""
    if source not in SOURCES:
        raise RouteEvidenceError(
            "ROUTE_ACTUAL_SOURCE_UNDECLARED", f"undeclared route evidence source {source!r}")
    if source == "self-attested" and any(value is not None for value in (model_class, effort, model)):
        raise RouteEvidenceError(
            "ROUTE_ACTUAL_SOURCE_UNDECLARED",
            "self-attested actual route must keep model, class, and effort unknown")
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
    """Fail-closed BEFORE any Task Contract compiles. Reuses the two frozen
    route boundary.  A measured lower route is `ROUTE_UNDERSHOOT`; absent provider
    evidence is the distinct nonterminal `ROUTE-UNVERIFIABLE`.  Conflating these two
    cases used to manufacture false routing blocks for Claude sessions.  Capability
    support remains the next ordered check."""
    classification = classify(required, actual)
    if classification == "unknown":
        return ROUTE_UNVERIFIABLE
    if classification == "under":
        return ROUTE_UNDERSHOOT
    for capability in capabilities:
        if capability["support"] not in ("native", "adapted"):
            return CAPABILITY_UNSUPPORTED
    return None


def capture_launch(*, expected_invocation: str, expected_cwd: str | Path,
                   provider: str | None = None, **adapter_options) -> dict:
    """Provider-neutral entry point for current launch provenance.

    Provider selection is bound to the current session identity unless a provider is
    injected explicitly by a test.  Canonical Task commands call only this function;
    provider-specific state formats stay inside their additive adapters.
    """
    if provider is None:
        from task.session_context import SessionContextError, resolve
        try:
            provider = resolve().provider
        except SessionContextError as exc:
            raise RouteEvidenceError("ROUTE_LAUNCH_UNAVAILABLE", str(exc)) from exc
    semantic = expected_invocation.strip()
    if semantic.startswith("$ "):
        semantic = semantic[2:]
    if semantic.startswith("/"):
        semantic = semantic[1:]
    if not semantic.startswith("task:"):
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_MISMATCH", "expected invocation must use semantic task:<command> form")
    catalog = load_projection_catalog()
    spec = projection_spec(catalog, ProviderId(provider))
    if spec is None:
        raise RouteEvidenceError(
            "ROUTE_LAUNCH_UNAVAILABLE", f"provider {provider!r} has no route adapter")
    module = importlib.import_module(f"task.{spec.route_evidence.adapter}")
    native_invocation = spec.route_evidence.semantic_prefix + semantic
    return module.capture_current(
        expected_invocation=native_invocation,
        expected_cwd=expected_cwd,
        **adapter_options,
    )


def build_run_receipt(*, plan_id: str, item_id: str, attempt: int, session_id: str,
                      run_id: str, evidence: dict) -> dict:
    """Bind validated route evidence to one immutable item run."""
    for field, value in (("plan_id", plan_id), ("item_id", item_id),
                         ("session_id", session_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value:
            raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", f"{field} is required")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "attempt must be int >= 1")
    required = {"model_class", "effort", "source", "ts", "model", "thread_id",
                "source_version", "cwd", "invocation"}
    if not isinstance(evidence, dict) or not required <= set(evidence):
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "route evidence is incomplete")
    if evidence.get("thread_id") != session_id:
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "route thread/session mismatch")
    return {
        "schema_version": "route-run-receipt/v1",
        "plan_id": plan_id,
        "item_id": item_id,
        "attempt": attempt,
        "session_id": session_id,
        "run_id": run_id,
        "evidence": {key: evidence[key] for key in sorted(required)},
    }


def start_decision(receipt: dict) -> dict:
    verify_run_receipt(receipt)
    return {
        "signal_class": "route",
        "scope_class": "run",
        "action": "route-bound",
        "recovered": True,
        "terminal": False,
        "route_receipt": receipt,
    }


def verify_run_receipt(receipt: dict, *, plan_id: str | None = None,
                       item_id: str | None = None, attempt: int | None = None,
                       session_id: str | None = None, run_id: str | None = None,
                       current_evidence: dict | None = None,
                       max_age_seconds: int = 86400,
                       now: datetime | None = None) -> bool:
    expected = {"schema_version", "plan_id", "item_id", "attempt", "session_id", "run_id",
                "evidence"}
    if not isinstance(receipt, dict) or set(receipt) != expected \
            or receipt.get("schema_version") != "route-run-receipt/v1":
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "unsupported run receipt")
    for field, value in (("plan_id", plan_id), ("item_id", item_id), ("attempt", attempt),
                         ("session_id", session_id), ("run_id", run_id)):
        if value is not None and receipt.get(field) != value:
            raise RouteEvidenceError("ROUTE_RECEIPT_MISMATCH", f"{field} changed")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict):
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "evidence is absent")
    try:
        captured = datetime.strptime(evidence["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "capture timestamp is invalid") from exc
    observed_now = now or datetime.now(timezone.utc)
    age_seconds = (observed_now - captured).total_seconds()
    if age_seconds < 0:
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", "capture timestamp is in the future")
    if max_age_seconds < 1 or age_seconds > max_age_seconds:
        raise RouteEvidenceError("ROUTE_RECEIPT_EXPIRED", "route receipt expired")
    if current_evidence is not None:
        axes = ("model", "model_class", "effort", "thread_id", "cwd", "invocation")
        if any(current_evidence.get(axis) != evidence.get(axis) for axis in axes):
            raise RouteEvidenceError("ROUTE_RECEIPT_MISMATCH", "current route changed")
    return True


def run_receipt_from_journal(plan_dir, run_id: str) -> dict:
    """Load the unique route receipt persisted on this run's start event."""
    path = Path(plan_dir) / "journal.jsonl"
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RouteEvidenceError("ROUTE_RECEIPT_INVALID", str(exc)) from exc
    matches = []
    for raw in rows:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        decision = event.get("decision") if isinstance(event, dict) else None
        if (event.get("run_id") == run_id and event.get("result") == "in-progress"
                and isinstance(decision, dict) and isinstance(decision.get("route_receipt"), dict)):
            matches.append(decision["route_receipt"])
    if len(matches) != 1:
        raise RouteEvidenceError(
            "ROUTE_RECEIPT_INVALID", f"run {run_id!r} has {len(matches)} start receipts")
    verify_run_receipt(matches[0], run_id=run_id)
    return matches[0]


def route_change_boundary(before: dict, after: dict) -> dict:
    """Detects a mid-item route change between two `capture_actual` evidence records
    (e.g. a session model/effort switch between an item's dispatch capture and a
    later re-check). Evidence only, no new machine event: the frozen state machine
 owns transitions — this returns the comparison a caller reports against
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
    model from it: that was exactly F8 (`journal.jsonl` rows carry
    `"implementation/high"` instead of `"sonnet/high"` — `required` and
    `actual` collapsed to the same string once the class was all this
    function had). An absent or non-string `model` renders the literal
    `unknown` — the same principle `effort` already uses — never a class
    substituted for a missing model.

    Breaking signature change: the ONE internal consumer,
    `journal.py --route-evidence`, is repaired in this same item."""
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
    cap.add_argument("--model-class", required=True, choices=(*MODEL_CLASS_ORDER, "unknown"))
    cap.add_argument("--effort", required=True, choices=(*EFFORT_ORDER, "unknown"))
    cap.add_argument("--source", required=True, choices=SOURCES)
    cap.add_argument("--ts", default=None)

    guard = sub.add_parser("guard", help="evaluate dispatch_guard over required/actual evidence files")
    guard.add_argument("--required", required=True, help="path to a required_route() JSON")
    guard.add_argument("--actual", required=True, help="path to a capture_actual() JSON")
    guard.add_argument("--capability", action="append", default=[],
                       help="id=support (native|adapted|unsupported), repeatable")

    args = parser.parse_args(argv)
    if args.cmd == "capture":
        evidence = capture_actual(
            None if args.model_class == "unknown" else args.model_class,
            None if args.effort == "unknown" else args.effort,
            source=args.source, ts=args.ts)
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
