"""review_policy — typed finding/review enforcement and loop breaker
(2026.07.24-AGENT-RELIABILITY P2.3).

Implements exactly `root/contracts/risk-review-loop-budget-v1.md` (2026.07.24-AGENT-RELIABILITY P2.1, frozen) as
executable policy: finding identity derived from the defect's SEAM (never report
wording — split-ban), the `reopens_product` predicate, the `same_finding_max = 2`
loop budget where the THIRD occurrence of one stable identity becomes an incident
with no inline repair, and the authority-profile-parameterized cap subject (D68 —
the subject is a parameter, never hardcoded). Validation cadence follows the same
contract: full once per phase-terminal item, targeted after each bounded fix.

This module is the ONE new call-site `packages/task/lib/task/task_contract.py`
gains for it (`evaluate_finding`, 2026.07.24-AGENT-RELIABILITY P2.2's approved policy hook) — the compiler's own
pre-mutation/pre-final predicates are untouched and never import this module, so
P2.2's independently-green test suite does not depend on it.

Reason codes are reused verbatim from `artifacts/P2.1/state-transition-cases.json`
`new_reason_codes` (P2.1, frozen; never re-minted here):
`FINDING_IDENTITY_UNSTABLE`, `REOPEN_WITHOUT_PRODUCT_FINDING`,
`AUTHORITY_PROFILE_UNDECLARED`.

stdlib-only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

# risk-review-loop-budget-v1.md §Declared sets (D51/D65) — closed enums, cited not re-minted.
FINDING_TYPES = ("product", "evidence", "process")
SEVERITIES = ("blocker", "major", "minor", "nit")
AUTHORITY_PROFILES = ("owner-gated", "self-host")
SIGNAL_CLASSES = (
    "procedural", "transient", "dependency-not-ready", "unrelated-pre-existing",
    "acceptance", "safety", "authority",
)
TERMINAL_SIGNAL_CLASSES = frozenset({"acceptance", "safety", "authority"})

# risk-review-loop-budget-v1.md §Loop budget and cadence.
SAME_FINDING_MAX = 2
AUDIT_ROUNDS_MAX = 2
POSITIVE_CASE_MINIMUM = 5

# risk-review-loop-budget-v1.md §Authority profiles — the subject at an exhausted
# cap is a parameter of the profile, never hardcoded (D68).
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

# `LoopBudget.from_committed` (2026.07.24-AGENT-RELIABILITY P2.6, F5) — locates each `## Audit <phase_id>` block
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
        """§Loop budget and cadence + F5 (2026.07.24-AGENT-RELIABILITY P2.6) — reconstructs ONE finding's
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
        `plans/2026.07.24-AGENT-RELIABILITY/findings/P2.6-contract-mapping.md`.
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
    parameterized by `profile` (D68). Never re-derives the 135-cell matrix: this is
    the ONE call site the compiler owns for a single finding, not a second copy of
    the abstract validator (2026.07.24-AGENT-RELIABILITY `artifacts/P2.1/validate_state_cases.py`, which proves
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
    """§Validation cadence — full validation runs once on the terminal item of a
    phase; targeted checks run after each bounded fix."""
    return "full" if is_phase_terminal_item else "targeted"
