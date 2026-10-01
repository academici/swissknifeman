"""Finding identity, read-only review outcomes and bounded review recurrence.

Historical finding/authority records remain readable. Audit budgets do not revoke
executor repair authority; validation breadth follows impact and declared checks.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# risk-review-loop-budget-v1.md §Declared sets — closed enums, cited not re-minted.
FINDING_TYPES = ("product", "evidence", "process")
SEVERITIES = ("blocker", "major", "minor", "nit")
AUTHORITY_PROFILES = ("owner-gated", "self-host")
SIGNAL_CLASSES = (
    "procedural", "transient", "dependency-not-ready", "unrelated-pre-existing",
    "acceptance", "safety", "authority",
)
TERMINAL_SIGNAL_CLASSES = frozenset({"acceptance", "safety", "authority"})
AUDIT_FIXER_BOUNDARIES = frozenset({"acceptance", "authority", "safety", "public-frozen"})
AUTHORITY_VERDICTS = frozenset({"delegated", "approval_required", "denied"})
BLOCK_ACTIONS = frozenset({
    "repair-candidate", "continue-local-repair", "gather-rag", "request-isolated-review",
    "repair-review", "gather-evidence", "terminal-block",
})
PHASE_AUDIT_TERMINAL_ACTIONS = frozenset({
    "approval-required", "authority-denied", "terminal-block",
})
_PHASE_AUDIT_SUBJECT_RE = re.compile(r"^(P[0-9]+)(?:\s+—\s+режим фазы)?$")

# risk-review-loop-budget-v1.md §Loop budget and cadence.
SAME_FINDING_MAX = 2
AUDIT_ROUNDS_MAX = 2
POSITIVE_CASE_MINIMUM = 5

# risk-review-loop-budget-v1.md §Authority profiles — the subject at an exhausted
# cap is a parameter of the profile, never hardcoded.
CAP_SUBJECT_BY_PROFILE = {
    "owner-gated": "owner",
    "self-host": "agent",
}

# execution-state-machine-v1.md §Load-bearing paths / `state-transition-cases.json`
# cells for `event = typed-finding` — the states that own the `reopens_product`
# guard and where its `true` branch lands. States absent here either have no
# guard (EXECUTING/FIXING/INCIDENT self-loop on every finding) or never reach this
# policy call (impossibility classes I1/I10/I13/I16/I17).
_READY_OR_DONE_REOPEN_TARGET = "ESCALATED"
_VERIFYING_REOPEN_TARGET = "FIXING"

# `LoopBudget.from_committed` — locates each `## Audit <phase_id>` block
# in a committed phase file, the same append-only audit region `plan-audit.md`'s
# own two-round-cap grep already reads.
_AUDIT_BLOCK_HEADER_RE = re.compile(r"^##\s+Audit\s+(P\d+)\b")


def classify_signal(signal_class: str, *, reproduced: bool, scope_class: str,
                    fingerprint: str, recovered: bool = False) -> dict:
    """Map one observed failure to the lean D12 action boundary.

    Raw tool/status/audit output is not accepted here as a terminal verdict: a
    terminal class becomes terminal only after minimal reproduction.  Callers keep
    their actual PID/diff/baseline checks; this helper owns only the closed taxonomy.
    """
    if signal_class not in SIGNAL_CLASSES:
        raise ReviewPolicyError(
            "FINDING_IDENTITY_UNSTABLE", f"unknown signal class {signal_class!r}")
    if not isinstance(scope_class, str) or not scope_class:
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", "scope_class is required")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", "fingerprint is required")
    terminal = reproduced and signal_class in TERMINAL_SIGNAL_CLASSES and not recovered
    actions = {
        "procedural": "repair-local",
        "transient": "retry-bounded",
        "dependency-not-ready": "wait-or-continue-independent",
        "unrelated-pre-existing": "record-baseline-delta-and-continue",
        "acceptance": "stop-affected-item" if terminal else "reproduce-impact",
        "safety": "reconcile-or-stop" if terminal else "reconcile-state",
        "authority": "owner-gate" if terminal else "verify-authority",
    }
    return {
        "signal_class": signal_class,
        "scope_class": scope_class,
        "fingerprint": fingerprint,
        "action": actions[signal_class],
        "recovered": bool(recovered),
        "terminal": terminal,
    }


def audit_fixer_action(*, in_scope: bool, bounded_incidental: bool = False,
                       repeated_fingerprint: int = 0, material_risk: bool = False,
                       reviewer_returns: int = 0, boundary: str | None = None,
                       authority_verdict: str | None = None,
                       block_action: str | None = None) -> dict:
    """Compatibility entry point for a read-only reviewer finding.

    Product repair belongs to the executor. Repeated review evidence never
    grants this reviewer write authority or forces another independent audit.
    """
    if not isinstance(in_scope, bool) or not isinstance(bounded_incidental, bool):
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", "scope flags must be bool")
    if (isinstance(repeated_fingerprint, bool) or not isinstance(repeated_fingerprint, int)
            or repeated_fingerprint < 0):
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", "repeated_fingerprint must be int >= 0")
    if not isinstance(material_risk, bool) or (isinstance(reviewer_returns, bool)
            or not isinstance(reviewer_returns, int) or reviewer_returns < 0):
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", "review inputs are invalid")
    if boundary is not None and boundary not in AUDIT_FIXER_BOUNDARIES:
        raise ReviewPolicyError("FINDING_IDENTITY_UNSTABLE", f"unknown audit boundary {boundary!r}")
    if authority_verdict is not None and authority_verdict not in AUTHORITY_VERDICTS:
        raise ReviewPolicyError(
            "FINDING_IDENTITY_UNSTABLE", f"unknown authority verdict {authority_verdict!r}")
    if block_action is not None and block_action not in BLOCK_ACTIONS:
        raise ReviewPolicyError(
            "FINDING_IDENTITY_UNSTABLE", f"unknown block action {block_action!r}")
    if boundary == "acceptance":
        return {"action": "return-owning-continuation", "terminal": False,
                "reason": "acceptance-failure-is-work"}
    if boundary in {"authority", "public-frozen"}:
        if authority_verdict is None:
            return {"action": "request-authority", "terminal": False,
                    "reason": f"{boundary}-boundary-unresolved"}
        if authority_verdict == "delegated":
            return {"action": "return-owning-continuation", "terminal": False,
                    "reason": "authority-delegated"}
        if authority_verdict == "approval_required":
            return {"action": "approval-required", "terminal": True,
                    "reason": "authority-approval-required"}
        return {"action": "authority-denied", "terminal": True,
                "reason": "authority-denied"}
    if boundary == "safety":
        if block_action is None:
            return {"action": "confirm-block", "terminal": False,
                    "reason": "safety-boundary-unconfirmed"}
        if block_action == "terminal-block":
            return {"action": "terminal-block", "terminal": True,
                    "reason": "safety-block-confirmed"}
        return {"action": "return-owning-continuation", "terminal": False,
                "reason": f"block-reducer-{block_action}"}
    if not in_scope:
        return {"action": "record-non-gating", "terminal": False,
                "reason": "out-of-scope-non-product"}
    return {"action": "return-owning-continuation", "terminal": False,
            "reason": "safe-in-scope"}


def phase_audit_subject(item_id: object) -> str | None:
    """Return canonical ``Pn`` for a phase-audit journal subject.

    Historical commands used both ``P1`` and ``P1 — режим фазы``.  Normalising at
    the policy boundary prevents delivery from silently treating the latter as an
    unrelated event and falling back to a stale generic handoff.
    """
    match = _PHASE_AUDIT_SUBJECT_RE.fullmatch(item_id) if isinstance(item_id, str) else None
    return match.group(1) if match else None


def phase_audit_terminal_policy(entry: dict, *, plan_dir=None) -> dict:
    """Separate reviewer completion from phase closure; preserve old RED outcomes."""
    if not isinstance(entry, dict) or entry.get("command") != "plan-audit":
        raise ReviewPolicyError("AUDIT_TERMINAL_EVENT_INVALID", "entry is not plan-audit")
    phase_id = phase_audit_subject(entry.get("item_id"))
    if phase_id is None:
        raise ReviewPolicyError("AUDIT_TERMINAL_EVENT_INVALID", "subject is not phase mode")
    result = entry.get("result")
    if result == "audit-green":
        return {"allow": True, "phase_id": phase_id, "action": "close",
                "continuation": None, "terminal": True}
    evidence = entry.get("decision")
    if result in {"audit-attention", "audit-red"} and isinstance(evidence, dict) and evidence.get("action") == "return-owning-continuation":
        continuation = evidence.get("continuation")
        ids = evidence.get("evidence_ids")
        plan_id = entry.get("plan_id", "")
        pattern = rf"(?:exec-items: task:plan-exec|run-items: task:plan-run) {re.escape(plan_id)} ({phase_id}\.[0-9]+)"
        if (not isinstance(continuation, str) or re.fullmatch(pattern, continuation) is None
                or evidence.get("recovered") is not False
                or evidence.get("terminal") is not False
                or not isinstance(ids, list) or not ids
                or not all(isinstance(value, str) and value for value in ids)
                or len(ids) != len(set(ids))
                or not isinstance(evidence.get("reason_code"), str) or not evidence["reason_code"]):
            raise ReviewPolicyError("AUDIT_TERMINAL_EVIDENCE_REQUIRED",
                                    "замечание требует evidence и точный owning item той же фазы")
        owner_item = continuation.rsplit(" ", 1)[1]
        if evidence.get("scope_class") != owner_item:
            raise ReviewPolicyError("AUDIT_TERMINAL_EVIDENCE_REQUIRED",
                                    "scope_class должен называть exact owning item")
        if plan_dir is not None:
            from task import plan_layout, plan_bundle
            try:
                spec = plan_layout.carrier_path(plan_dir, "item-spec", item_id=owner_item)
                if not spec.is_file():
                    raise ValueError(f"owning item отсутствует: {owner_item}")
                plan_bundle.producer_readiness(plan_dir, owner_item)
            except ValueError as exc:
                raise ReviewPolicyError("AUDIT_TERMINAL_CONTINUATION_INVALID", str(exc)) from exc
        return {"allow": True, "phase_id": phase_id,
                "action": "return-owning-continuation", "continuation": continuation,
                "terminal": True, "phase_closed": False}
    if result == "audit-attention":
        raise ReviewPolicyError("AUDIT_ATTENTION_NONTERMINAL",
                                "ATTENTION требует доказанное замечание и owning continuation")
    if result != "audit-red":
        raise ReviewPolicyError(
            "AUDIT_TERMINAL_EVENT_INVALID", f"unsupported phase audit result {result!r}")

    evidence = entry.get("decision")
    required = {
        "signal_class", "scope_class", "action", "recovered", "terminal",
        "reason_code", "evidence_ids", "continuation",
    }
    if not isinstance(evidence, dict) or not required <= set(evidence):
        raise ReviewPolicyError(
            "AUDIT_TERMINAL_EVIDENCE_REQUIRED",
            "audit-red requires reducer action, evidence ids and exact continuation",
        )
    action = evidence.get("action")
    evidence_ids = evidence.get("evidence_ids")
    continuation = evidence.get("continuation")
    if (action not in PHASE_AUDIT_TERMINAL_ACTIONS
            or evidence.get("terminal") is not True
            or evidence.get("recovered") is not False
            or not isinstance(evidence.get("reason_code"), str)
            or not evidence["reason_code"]
            or not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or not all(isinstance(value, str) and value for value in evidence_ids)
            or not isinstance(continuation, str)
            or not continuation):
        raise ReviewPolicyError(
            "AUDIT_TERMINAL_EVIDENCE_REQUIRED", "audit-red reducer evidence is incomplete")
    prefix = "waiting:" if action == "approval-required" else "terminal:"
    if not continuation.startswith(prefix):
        raise ReviewPolicyError(
            "AUDIT_TERMINAL_CONTINUATION_INVALID",
            f"{action} requires continuation form {prefix}",
        )
    return {"allow": True, "phase_id": phase_id, "action": action,
            "continuation": continuation, "terminal": True}


def validate_phase_audit_continuation(entry: dict, *, plan_id: str,
                                      next_exact: str, plan_dir=None) -> dict:
    """Bind a persisted audit outcome to the only successor its reducer permits."""
    policy = phase_audit_terminal_policy(entry, plan_dir=plan_dir)
    if entry.get("result") == "audit-green":
        expected = f"close: task:plan-close {plan_id} {policy['phase_id']}"
    else:
        expected = policy["continuation"]
    if next_exact != expected:
        raise ReviewPolicyError(
            "AUDIT_TERMINAL_CONTINUATION_INVALID",
            f"audit outcome requires exact continuation {expected!r}, got {next_exact!r}",
        )
    return policy


def pending_phase_repair(plan_dir, item_id: str) -> bool:
    """A reviewer return permits one owning recovery, until its next terminal event."""
    from task import journal
    path = Path(plan_dir) / journal.FILENAME
    if not path.is_file():
        return False
    for raw in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not raw.strip():
            continue
        entry = json.loads(raw)
        journal.validate_entry(entry)
        if entry.get("item_id") == item_id and entry.get("result") in journal.TERMINAL_CLOSE_RESULTS:
            return False
        if (entry.get("command") == "plan-audit"
                and phase_audit_subject(entry.get("item_id")) == item_id.split(".")[0]
                and entry.get("result") in {"audit-green", "audit-attention", "audit-red"}):
            policy = phase_audit_terminal_policy(entry, plan_dir=plan_dir)
            return (policy["action"] == "return-owning-continuation"
                    and entry["decision"]["scope_class"] == item_id)
    return False


def _audit_blocks(phase_lines, phase_id: str):
    """Yields `(start, end)` slice bounds for each `## Audit <phase_id>` block in
    `phase_lines` — `phase_lines[start:end]` is that block's full text, header
    included, up to (not including) the next top-level `## ` heading or EOF."""
    section_starts = [i for i, ln in enumerate(phase_lines) if ln.startswith("## ")]
    boundaries = sorted(set(section_starts) | {len(phase_lines)})
    for i, ln in enumerate(phase_lines):
        m = _AUDIT_BLOCK_HEADER_RE.match(ln.strip())
        if m and m.group(1) == phase_id:
            end = min(b for b in boundaries if b > i)
            yield i, end


class ReviewPolicyError(ValueError):
    """A refusal named by its own frozen reason code — never a silent downgrade."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def finding_id(*, file: str, rule_or_contract_locus: str, defect_class: str) -> str:
    """§Finding identity — derived from the SEAM only (`file`, `rule_or_contract_locus`,
    `defect_class`), never from report wording, severity label, report section split
    or reviewer identity (split-ban): splitting one seam into several reports must not
    create several identities, or the cap is evaded cosmetically."""
    for name, value in (("file", file), ("rule_or_contract_locus", rule_or_contract_locus),
                        ("defect_class", defect_class)):
        if not isinstance(value, str) or not value:
            raise ReviewPolicyError(
                "FINDING_IDENTITY_UNSTABLE",
                f"seam field {name!r} must be a non-empty str, got {value!r}")
    seam = "\x00".join((file, rule_or_contract_locus, defect_class))
    return hashlib.sha256(seam.encode("utf-8")).hexdigest()[:16]


def identity_of(finding: dict) -> str:
    """The stable identity a finding counts against: its own seam-derived id, or —
    when it carries `reopen_of` — the id of the finding it re-raises (the pair counts
    as ONE identity against `same_finding_max`, §Finding identity)."""
    fid = finding.get("finding_id") or finding_id(
        file=finding["file"], rule_or_contract_locus=finding["rule_or_contract_locus"],
        defect_class=finding["defect_class"])
    return finding.get("reopen_of") or fid


def reopens_product(finding: dict) -> bool:
    """§The reopen predicate:
    `finding.type == "product" OR finding.severity == "blocker" OR
    finding.invalidates_acceptance == True`. Only a branch whose guard value is
    `true` may target a repair state (`REOPEN_WITHOUT_PRODUCT_FINDING` otherwise) —
    an evidence/process finding does NOT reopen a product already proven green."""
    if finding.get("type") not in FINDING_TYPES:
        raise ReviewPolicyError(
            "FINDING_IDENTITY_UNSTABLE", f"unknown finding type {finding.get('type')!r}")
    if finding.get("severity") not in SEVERITIES:
        raise ReviewPolicyError(
            "FINDING_IDENTITY_UNSTABLE", f"unknown severity {finding.get('severity')!r}")
    return (finding["type"] == "product"
            or finding["severity"] == "blocker"
            or finding.get("invalidates_acceptance", False) is True)


def cap_subject(profile: str) -> str:
    """§Authority profiles — the subject at an exhausted cap is supplied by the
    caller and never inferred; an undeclared profile fails closed
    (`AUTHORITY_PROFILE_UNDECLARED`)."""
    if profile not in AUTHORITY_PROFILES:
        raise ReviewPolicyError(
            "AUTHORITY_PROFILE_UNDECLARED", f"undeclared authority profile {profile!r}")
    return CAP_SUBJECT_BY_PROFILE[profile]


class LoopBudget:
    """Tracks fix-round occurrences per stable identity (`identity_of`) and enforces
    `same_finding_max` — the executable form of `state-transition-cases.json` cells
    `(*, same-finding-third) -> INCIDENT`. A round is counted only when a finding
    actually reopens product and enters `FIXING` (I3: "the same-finding counter
    counts fix rounds; a state that has had none cannot reach its third")."""

    def __init__(self, *, same_finding_max: int = SAME_FINDING_MAX):
        self.same_finding_max = same_finding_max
        self._rounds: dict[str, int] = {}

    def occurrences(self, finding: dict) -> int:
        return self._rounds.get(identity_of(finding), 0)

    def record_fix_round(self, finding: dict) -> int:
        """One more repair round against this finding's stable identity. Returns the
        resulting occurrence count (the caller compares it to `same_finding_max`)."""
        identity = identity_of(finding)
        self._rounds[identity] = self._rounds.get(identity, 0) + 1
        return self._rounds[identity]

    @classmethod
    def from_committed(cls, plan_dir, phase_id: str, finding: dict, *,
                       same_finding_max: int = SAME_FINDING_MAX):
        """§Loop budget and cadence + F5 — reconstructs ONE finding's
        cross-session occurrence count from the two committed carriers this
        contract already names: `journal.jsonl` `command == "plan-audit"`
        entries and `## Audit <phase_id>` blocks in the phase file.
        `LoopBudget._rounds` alone cannot survive a process restart — F5's
        exact failure scenario is three independent `plan-audit` sessions
        each observing `occurrences() == 0` for the identical recurring
        finding, so the cap never trips.

        Returns `(budget, count)`. `count` is either a non-negative int (both
        carriers were checked — a verified zero IS a real zero) or the
        literal `"unknown"` (the phase file itself is absent — nothing to
        check against, never silently coerced to `0`; that coercion is
        exactly F5's defect: an invisible count passed off as zero).

        `finding` must carry `rule_or_contract_locus` — the same seam field
        `finding_id`/`identity_of` already require (no second identity
        vocabulary): it is used, verbatim, as the substring searched for in
        both carriers. Distinct from `task_contract._count_audit_rounds`
        (phase-level `authority.observed_rounds`, not per-finding) —
        .
        """
        locus = finding.get("rule_or_contract_locus")
        if not isinstance(locus, str) or not locus:
            raise ReviewPolicyError(
                "FINDING_IDENTITY_UNSTABLE",
                f"rule_or_contract_locus must be a non-empty str, got {locus!r}")
        budget = cls(same_finding_max=same_finding_max)
        plan_dir = Path(plan_dir)
        from task import plan_layout
        if not (plan_dir / "plan.md").is_file():
            # Historical unit fixtures predate layout declarations; preserve their
            # legacy observational semantics without granting a real v2 plan a
            # silent fallback.
            phase_path = plan_dir / "phases" / f"{phase_id}.md"
        else:
            try:
                phase_path = plan_layout.phase_path(plan_dir, phase_id)
            except plan_layout.PlanLayoutError as exc:
                raise ReviewPolicyError("CARRIER_UNRESOLVED", f"носитель фазы не резолвится: {exc}") from exc
        try:
            phase_lines = phase_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            if not (plan_dir / "plan.md").is_file():
                return budget, "unknown"
            raise ReviewPolicyError("CARRIER_UNREADABLE", f"носитель фазы не читается: {exc}") from exc

        phase_count = 0
        for start, end in _audit_blocks(phase_lines, phase_id):
            if any(locus in ln for ln in phase_lines[start:end]):
                phase_count += 1

        journal_count = 0
        journal_path = plan_dir / "journal.jsonl"
        if journal_path.is_file():
            for line in journal_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("command") == "plan-audit" and locus in (entry.get("note") or ""):
                    journal_count += 1

        count = max(phase_count, journal_count)
        budget._rounds[identity_of(finding)] = count
        return budget, count


def review_transition(state: str, finding: dict, *, budget: LoopBudget, profile: str) -> dict:
    """One `typed-finding` event over the frozen machine
    (`execution-state-machine-v1.md`, `state-transition-cases.json` cells for
    `event = typed-finding` / `same-finding-third`). Evaluates the `reopens_product`
    guard for the calling state, records a fix round when the guard fires from
    `VERIFYING`, and converts the round that reaches `same_finding_max + 1` into the
    `same-finding-third` event — `INCIDENT` with no inline repair, its cap subject
    parameterized by `profile`. Never re-derives the 135-cell matrix: this is
    the ONE call site the compiler owns for a single finding, not a second copy of
    the abstract validator (which proves
    the matrix itself and is not imported here)."""
    reopens = reopens_product(finding)

    if state == "VERIFYING":
        if not reopens:
            return {"decision": "continue-next", "to_state": "VERIFYING", "journal": None,
                    "reopened": False, "occurrence": budget.occurrences(finding)}
        occurrence = budget.record_fix_round(finding)
        if occurrence >= budget.same_finding_max + 1:
            return {"decision": "incident", "to_state": "INCIDENT", "journal": "blocked",
                    "reopened": True, "occurrence": occurrence,
                    "cap_subject": cap_subject(profile)}
        return {"decision": "retry-fix", "to_state": _VERIFYING_REOPEN_TARGET,
                "journal": None, "reopened": True, "occurrence": occurrence}

    if state in ("READY", "DONE"):
        if reopens:
            return {"decision": "escalate-design", "to_state": _READY_OR_DONE_REOPEN_TARGET,
                    "journal": "escalated", "reopened": True,
                    "occurrence": budget.occurrences(finding)}
        return {"decision": "continue-next", "to_state": state, "journal": "no-op",
                "reopened": False, "occurrence": budget.occurrences(finding)}

    if state in ("EXECUTING", "FIXING", "INCIDENT"):
        # No guard at these states (`state-transition-cases.json`): every finding is
        # either repaired inline (EXECUTING/FIXING) or recorded against the already
        # open incident (INCIDENT) — the reopen question does not arise here.
        return {"decision": "continue-next", "to_state": state, "journal": None,
                "reopened": False, "occurrence": budget.occurrences(finding)}

    raise ReviewPolicyError(
        "REOPEN_WITHOUT_PRODUCT_FINDING",
        f"typed-finding evaluated in a state that owns no such guard: {state!r}")


def same_finding_third(state: str, finding: dict, *, budget: LoopBudget, profile: str) -> dict:
    """The `same-finding-third` event: unconditional `INCIDENT` from every state that
    can carry an open loop, once the caller has already observed the cap breached
    (`occurrences(finding) >= same_finding_max`). `INCIDENT` itself self-loops
    (recording, not a second incident); `READY`/`SKIPPED` cannot reach this event by
    construction (I3 — no fix round exists for them) and are refused."""
    if state in ("READY", "SKIPPED"):
        raise ReviewPolicyError(
            "REOPEN_WITHOUT_PRODUCT_FINDING",
            f"{state!r} carries no fix round for same-finding-third to close (I3)")
    if state == "INCIDENT":
        return {"decision": "continue-next", "to_state": "INCIDENT", "journal": None,
                "cap_subject": cap_subject(profile)}
    return {"decision": "incident", "to_state": "INCIDENT", "journal": "blocked",
            "cap_subject": cap_subject(profile)}


def validation_cadence(*, is_phase_terminal_item: bool) -> str:
    """Compatibility hint; terminal item numbering does not establish risk.

    Declared Validation and impact selection own any wider qualification.
    """
    return "targeted"
