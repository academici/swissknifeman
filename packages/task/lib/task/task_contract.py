"""task_contract — Task Contract v1 compiler.

The single checked seam `packages/task/commands/plan-*.md` call at the pre-mutation and
pre-final boundaries instead of restating the rule in prose. It owns exactly what the
frozen contracts assign it and nothing else:

  * content-hash recomputation and the precedence/conflict resolution ladder
    (`root/contracts/task-contract-v1.md` §Version / §Precedence,, frozen);
  * the twelve ordered pre-mutation reason codes and the three ordered pre-final reason
    codes of the same contract (frozen; reused verbatim, never re-minted);
  * the slice-partition and cold-start checks of the same contract (frozen);
  * the portability tier classification and lint predicate of
,
    including the one new reason code that layer adds
    (`PORTABILITY_TIER_MISCLASSIFIED`,.json`
    `new_reason_codes`).

Authoring pattern reused from
 (a frozen
plan artifact, never imported or modified — the item's Required Reads name it as the
pattern to follow, not a library to import); this module is the first executable version
that lives in the package and is called by name from the canonical plan commands.

stdlib-only.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "task-contract/v1"

# Ordered ladders — index = rank, a lower index outranks a higher one
# (task-contract-v1.md §Precedence ladder / §Route, frozen enums).
CARRIER_PRECEDENCE = (
    "owner-instruction",
    "plan-decision",
    "item-spec",
    "package-canon",
    "handoff-carrier",
    "incidental-diagnostic",
)
MODEL_CLASS_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")

# task-contract-v1.md §Public acceptance — proof classes that may satisfy a deterministic
# acceptance predicate: `pinned-not-recomputable`/`unknown` never do.
DETERMINISTIC_PROOF_CLASSES = ("recomputed", "cross-checked")

# task-contract-v1.md §Root/subagent slice — the eleven payload keys, partitioned exactly.
SLICE_PARTITION_KEYS = frozenset({
    "goal", "must", "never", "done", "authority", "next", "route", "version",
    "evidence", "portability", "conflicts",
})
SLICE_SUBAGENT_REQUIRED = frozenset(
    {"goal", "must", "never", "done", "authority", "next", "route", "version"})
SLICE_ROOT_ONLY_REQUIRED = frozenset({"evidence", "portability", "conflicts"})

# task-contract-v1.md §Portability — an execution input that is absolute, `~`-rooted,
# parent-escaping, `tmp/`-rooted or URL-shaped is external BY CONSTRUCTION once its ROLE
# (execution input vs provenance) is already decided — this is the frozen string test
# over an ALREADY-CLASSIFIED input, not the D47 role test itself. The role test (which path
# even belongs in `execution_inputs` in the first place) lives upstream of this compiler, in
# whatever builds the `portability` block (root supervisor / `plan_lint`'s tiered-portability
# check) — it is a POSITIONAL test (does the item read this path in Inputs/Required
# Reads/Validation), never a substring match on `tmp/` (D47, plan-portability-v1.md
# §Provenance vs execution input).
_EXTERNAL_PREFIXES = ("/", "~", "../", "tmp/")
_EXTERNAL_SUBSTRINGS = ("/../", "/tmp/", "://")

# --------------------------------------------------------------------------
# build() — Task Contract v1 producer. Field-mapping table lives in
#.
# --------------------------------------------------------------------------

# New reason codes — not pre-declared by 's frozen
#::new_reason_codes` (this item introduces
# them directly, same authoring discipline: a distinct_from a frozen code, never a
# redefinition — D64).
BUNDLE_ARTIFACT_MISSING = "BUNDLE_ARTIFACT_MISSING"
BUNDLE_PRIVACY_MISMATCH = "BUNDLE_PRIVACY_MISMATCH"
BUNDLE_POLICY_DENIED = "BUNDLE_POLICY_DENIED"
BUNDLE_PATH_INVALID = "BUNDLE_PATH_INVALID"
BUNDLE_PATH_EXTERNAL = "BUNDLE_PATH_EXTERNAL"
BUNDLE_MEMBER_DUPLICATE = "BUNDLE_MEMBER_DUPLICATE"
BUNDLE_MEMBER_UNSAFE = "BUNDLE_MEMBER_UNSAFE"
PORTABILITY_INPUT_INVALID = "PORTABILITY_INPUT_INVALID"

PUBLIC_REASON_MESSAGES = {
    "schema-invalid": "Fix the input or selected schema version before retrying.",
    "evidence-missing": "Produce the required evidence before retrying.",
    "evidence-stale": "Recompute the evidence against the current state.",
    "evidence-forged": "Do not reuse this evidence; inspect its producer and binding.",
    "policy-denied": "Change the requested action or obtain the required authority.",
    "conflict": "Read the authoritative winner and reconcile before retrying.",
    "corrupt-state": "Stop mutation and repair the authoritative state separately.",
    "durability-failed": "Treat the outcome as unknown and reconcile before retrying.",
}

_PUBLIC_REASON_EXACT = {
    "VERSION_HASH_MISMATCH": "evidence-forged",
    "CONFLICT_UNRESOLVED": "conflict",
    "CONFLICT_PRECEDENCE_VIOLATION": "conflict",
    "NEXT_CHANGED_WITHOUT_TRANSITION": "policy-denied",
    "PORTABILITY_TIER_MISCLASSIFIED": "policy-denied",
    "PORTABILITY_INPUT_MISSING": "evidence-missing",
    "PORTABILITY_EXTERNAL_INPUT": "policy-denied",
    PORTABILITY_INPUT_INVALID: "schema-invalid",
    "ROUTE-UNVERIFIABLE": "evidence-missing",
    "ROUTE_UNDERSHOOT": "policy-denied",
    "CAPABILITY_UNSUPPORTED": "policy-denied",
    "AUTHORITY_BOUNDARY": "policy-denied",
    "SLICE_INCOMPLETE": "schema-invalid",
    "COLD_START_INCOMPLETE": "evidence-missing",
    "SELF_INVALIDATING_EVIDENCE_ANCHOR": "conflict",
    "ACCEPTANCE_NOT_PUBLIC": "schema-invalid",
    "EVIDENCE_REF_UNKNOWN": "schema-invalid",
    "VALIDATION_RECEIPT_MISSING": "evidence-missing",
    "VALIDATION_RECEIPT_STALE": "evidence-stale",
    "VALIDATION_RECEIPT_NONZERO": "policy-denied",
    "EVIDENCE_PROOF_CLASS_INSUFFICIENT": "policy-denied",
    "PLAN_LAYOUT_V1_RETIRED": "schema-invalid",
    "PLAN_CONTEXT_TRUNCATED": "evidence-missing",
    "PLAN_CONTEXT_DIGEST_MISMATCH": "evidence-forged",
    "BATCH_AMBIGUOUS": "schema-invalid",
    "BATCH_REQUIRED": "policy-denied",
    "BATCH_STALE": "evidence-stale",
    BUNDLE_ARTIFACT_MISSING: "evidence-missing",
    BUNDLE_PRIVACY_MISMATCH: "policy-denied",
    BUNDLE_POLICY_DENIED: "policy-denied",
    BUNDLE_PATH_INVALID: "schema-invalid",
    BUNDLE_PATH_EXTERNAL: "policy-denied",
    BUNDLE_MEMBER_DUPLICATE: "schema-invalid",
    BUNDLE_MEMBER_UNSAFE: "policy-denied",
    "OWNER_ATTESTATION_EXPIRED": "evidence-stale",
    "OWNER_ATTESTATION_FORGED": "evidence-forged",
    "OWNER_ATTESTATION_INVALID": "schema-invalid",
    "OWNER_ATTESTATION_MISMATCH": "evidence-forged",
    "OWNER_ATTESTATION_REPLAYED": "conflict",
    "OWNER_ATTESTATION_UNSUPPORTED": "policy-denied",
    "AUTHORITY_PROVIDER_UNAVAILABLE": "policy-denied",
    "P5_DECISION_DIGEST_MISMATCH": "evidence-forged",
    "P5_DECISION_OBSERVATION_UNVERIFIED": "evidence-missing",
    "P5_DECISION_POLICY_ERROR": "policy-denied",
    "P5_DECISION_RECLASSIFICATION_REQUIRED": "policy-denied",
    "P5_DECISION_REJECTED": "policy-denied",
    "P5_DECISION_RESPONSE_REUSED": "conflict",
    "P5_DECISION_STORE_REQUIRED": "evidence-missing",
    "P5_DECISION_UNCLASSIFIED_KIND": "schema-invalid",
    "P5_DECISION_UNKNOWN_OPTION": "schema-invalid",
    "JOURNAL_CONFLICT": "conflict",
    "JOURNAL_CORRUPT": "corrupt-state",
    "JOURNAL_DURABILITY_FAILED": "durability-failed",
    "ROUTE_ACTUAL_SOURCE_UNDECLARED": "evidence-forged",
    "ROUTE_BUDGET_AXIS_UNKNOWN": "schema-invalid",
    "ROUTE_LAUNCH_MISMATCH": "evidence-forged",
    "ROUTE_LAUNCH_UNAVAILABLE": "evidence-missing",
    "ROUTE_MODEL_UNKNOWN": "evidence-missing",
    "ROUTE_RECEIPT_EXPIRED": "evidence-stale",
    "ROUTE_RECEIPT_INVALID": "schema-invalid",
    "ROUTE_RECEIPT_MISMATCH": "evidence-forged",
    "ROUTE_REQUIRED_UNRESOLVED": "evidence-missing",
}


def public_reason(internal_code: str | None) -> dict | None:
    """Map internal diagnostics to the small public recovery taxonomy.

    Internal codes remain available for precise debugging. The additive public code is
    stable across module-specific spellings and gives CLI/JSON consumers one recovery
    action without collapsing the underlying diagnostic.
    """
    if internal_code is None:
        return None
    code = internal_code.removeprefix("block:")
    category = _PUBLIC_REASON_EXACT.get(code, "policy-denied")
    return {
        "code": category,
        "internal_code": code,
        "message": PUBLIC_REASON_MESSAGES[category],
    }


@dataclass(frozen=True)
class BundleInputPolicy:
    """Policy-owned Bundle v1 privacy and filesystem boundary."""

    schema_version: str = "BundleInputPolicy/v1"
    minimized: bool = True
    forbidden_classes: frozenset[str] = frozenset({
        "raw-transcript-bodies", "chain-of-thought", "tool-payloads", "secrets",
    })

    def privacy(self) -> dict:
        return {
            "minimized": self.minimized,
            "excluded_classes": sorted(self.forbidden_classes),
        }


BUNDLE_INPUT_POLICY = BundleInputPolicy()

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:(?:[\\/]|$)")
_WINDOWS_UNC_RE = re.compile(r"^(?:\\\\|//)[^/\\]+[\\/]")
_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ENV_PATH_RE = re.compile(r"(?:^|/)(?:\$[A-Za-z_{]|%[A-Za-z_][A-Za-z0-9_]*%)")


def classify_execution_input(value: str) -> dict:
    """Classify one logical path without expanding host state or following links."""
    original = value if isinstance(value, str) else ""
    path = original.strip()
    result = {"original": original, "normalized": path, "path_kind": "invalid",
              "rejection": PORTABILITY_INPUT_INVALID}
    if not path or "\x00" in path or path.endswith("/"):
        return result
    if (_WINDOWS_DRIVE_RE.match(path) or _WINDOWS_UNC_RE.match(path)
            or path.startswith(("/", "~", "tmp/")) or _URI_RE.match(path)
            or _ENV_PATH_RE.search(path)):
        return {**result, "path_kind": "external",
                "rejection": "PORTABILITY_EXTERNAL_INPUT"}
    if "\\" in path:
        return result
    parts = PurePosixPath(path).parts
    if not parts or any(part == ".." for part in parts):
        return result
    normalized = PurePosixPath(*[part for part in parts if part != "."]).as_posix()
    if not normalized or normalized == ".":
        return result
    return {"original": original, "normalized": normalized,
            "path_kind": "internal", "rejection": None}


def contained_regular_path(root, logical_path: str) -> Path:
    """Resolve one internal logical name without accepting links or special files."""
    root = Path(root)
    classified = classify_execution_input(logical_path)
    if classified["path_kind"] != "internal":
        raise ValueError(classified["rejection"])
    if root.is_symlink() or not root.is_dir():
        raise ValueError(BUNDLE_MEMBER_UNSAFE)
    root_resolved = root.resolve(strict=True)
    current = root
    parts = PurePosixPath(classified["normalized"]).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ValueError(BUNDLE_ARTIFACT_MISSING) from exc
        if stat.S_ISLNK(mode):
            raise ValueError(BUNDLE_MEMBER_UNSAFE)
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            raise ValueError(BUNDLE_MEMBER_UNSAFE)
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ValueError(BUNDLE_MEMBER_UNSAFE)
    try:
        current.resolve(strict=True).relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise ValueError(BUNDLE_MEMBER_UNSAFE) from exc
    return current

_SCOPE_CLAUSE_SPLIT_RE = re.compile(r";\s*")
_INPUTS_SPLIT_RE = re.compile(r"\s*·\s*")
_VALIDATION_SPLIT_RE = re.compile(r"\s*·\s*|\n(?=-[ \t]+)")
_REQUIRED_READS_SPLIT_RE = re.compile(r"(?:^|\s)\d+\)\s+")
_IMPL_RULE_SPLIT_RE = re.compile(r"\*\*\(\d+\)\*\*\s*")
_ANTI_CLAUSE_SPLIT_RE = re.compile(r"\*{0,2}(?:Anti|Anti)[\w-]*\s*:\*{0,2}\s*")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_ROUTING_HEADER_RE = re.compile(r"^##\s+3\.\s+Routing\s*$")
_ROUTING_RANGE_RE = re.compile(r"^(P\d+)\.(\d+)\s*[–-]\s*(P\d+)\.(\d+)$")
_AUDIT_BLOCK_HEADER_RE = re.compile(r"^##\s+Audit\s+(P\d+)\b")
_OWNER_GRANT_RE = re.compile(r"\[OWNER-GRANT:([A-Z0-9][A-Z0-9.-]+)\]")
_OWNER_REVOKE_RE = re.compile(r"\[OWNER-REVOKE:([A-Z0-9][A-Z0-9.-]+)\]")
_NEEDS_CLARIFICATION_RE = re.compile(r"\[NEEDS\s+CLARIFICATION\s*:", re.IGNORECASE)
_AUTHORITY_DECLARATION_RE = re.compile(
    r"^\[OWNER-GATE:(?P<gate_id>[A-Z0-9][A-Z0-9.-]+)\]\s+"
    r"branch=`(?P<branch>[^`\n]+)`;\s*scope=`(?P<scope>[^`\n]+)`"
    r"(?:;\s*boundary=`(?P<boundary>provider-proof|owner-session)`"
    r"(?:;\s*effect=`(?P<effect>[^`\n]+)`;\s*environment=`(?P<environment>[^`\n]+)`)?\s*)?$")
# Migration diagnostic only: machine authority is always the explicit declaration.
_LEGACY_AUTHORITY_RE = re.compile(
    r"durable\s+owner\s+authori[sz]ation|only\s+after\s+owner\s+authori[sz]ation|"
    r"only\s+after\s+(?:durable\s+)?owner\s+authorization", re.IGNORECASE)
# Protected authority is deliberately a small, exact Decision Log record rather than
# prose searched by substring.  Backticks make the three values unambiguous even when
# a branch or scope contains ordinary punctuation.  The Decision Log must reference a
# separately recorded repository-owner message in the plan's Layer-0 brief; a copyable
# Meta ``Approval Owner`` label is identity metadata, not an authority carrier.
_OWNER_GRANT_RECORD_RE = re.compile(
    r"^\[OWNER-GRANT:(?P<gate_id>[A-Z0-9][A-Z0-9.-]+)\]\s+"
    r"branch=`(?P<branch>[^`\n]+)`;\s*"
    r"scope=`(?P<scope>[^`\n]+)`;\s*"
    r"owner-message=`(?P<owner_message>brief/[A-Za-z0-9][A-Za-z0-9._-]*\.md"
    r"#[A-Za-z0-9][A-Za-z0-9._-]*)`$")
_OWNER_MESSAGE_REF_RE = re.compile(
    r"^brief/(?P<filename>[A-Za-z0-9][A-Za-z0-9._-]*\.md)"
    r"#(?P<message_id>[A-Za-z0-9][A-Za-z0-9._-]*)$")
_OWNER_MESSAGE_RECORD_RE = re.compile(
    r"^\[REPOSITORY-OWNER-MESSAGE:(?P<message_id>[A-Za-z0-9][A-Za-z0-9._-]*)\]\s+"
    r"\[OWNER-GRANT:(?P<gate_id>[A-Z0-9][A-Z0-9.-]+)\]\s+"
    r"branch=`(?P<branch>[^`\n]+)`;\s*"
    r"scope=`(?P<scope>[^`\n]+)`;\s*"
    r"provenance=`repository-owner`$")

SLICE_SUBAGENT_KEYS = ("goal", "must", "never", "done", "authority", "next", "route", "version")
SLICE_ROOT_ONLY_KEYS = ("evidence", "portability", "conflicts")


class TaskContractBuildError(ValueError):
    """A typed refusal to compile a Task Contract — never a fabricated
    placeholder value (Implementation Rules (2), anti-padding). Carries
    the offending item and field name so the caller can act on it directly,
    the same shape `RouteEvidenceError`/`ReviewPolicyError` already use."""

    def __init__(self, item_id: str, field: str, message: str):
        super().__init__(f"{item_id}: {field}: {message}")
        self.item_id = item_id
        self.field = field


def _split_nonempty(text: str, pattern: "re.Pattern") -> list:
    return [p.strip() for p in pattern.split(text or "") if p and p.strip()]


def _first_backtick_or_text(clause: str) -> str:
    m = _BACKTICK_RE.search(clause)
    return m.group(1) if m else clause.strip()


def _marker_clauses(text: str, marker_re: "re.Pattern") -> list:
    """Splits `text` at each match of `marker_re` (a labelled/numbered marker —
    `**(N)**`, `N) `, `**Anti-…:**`), discarding any text before the FIRST
    marker (ordinary prose, not a clause of the marked kind). No marker
    present → `[]`, never "the whole text as one accidental clause" (unlike
    `_split_nonempty`'s `; `/`·` semicolon-style split, where a single
    unmarked sentence legitimately IS one clause)."""
    markers = list(marker_re.finditer(text or ""))
    clauses = []
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        clause = text[m.end():end].strip()
        if clause:
            clauses.append(clause)
    return clauses


def _anti_clauses(code_guidance_text: str) -> list:
    """Code Guidance anti-clauses (`**Anti-fitting:** …` / `Anti-…:` — bold or
    plain, both observed in the fleet) feeding `never[]`. An item that spells
    no anti-clause at all yields `[]` — `never[]` still satisfies its
    minItems via `Scope Excluded` alone."""
    return _marker_clauses(code_guidance_text, _ANTI_CLAUSE_SPLIT_RE)


def _require_field(item_id: str, fields: dict, name: str):
    value, lineno = fields.get(name, ("", None))
    value = (value or "").strip()
    if not value or value == "—":
        raise TaskContractBuildError(item_id, name,
                                     "field is empty (\"—\") — build refuses to fabricate a value")
    return value, lineno


def _count_audit_rounds(plan_dir: Path, phase_lines, phase_id: str) -> int:
    """Count fingerprinted phase-candidate audits in the append-only journal.

    Historical design/closed-phase audit blocks predate the candidate fingerprint
    protocol and must not consume a current item's repair budget.  The journal
    fingerprint is the distinguishing carrier: D14 candidate audits require it,
    while legacy blocks/events do not.  The phase Markdown still participates as
    an integrity bound — a journal event without a matching audit block is ignored
    here and remains an audit/lint defect rather than silently spending budget.
    """
    block_count = sum(
        1 for ln in phase_lines
        if (match := _AUDIT_BLOCK_HEADER_RE.match(ln.strip())) and match.group(1) == phase_id)
    if block_count == 0:
        return 0

    journal_path = Path(plan_dir) / "journal.jsonl"
    if not journal_path.is_file():
        return 0
    fingerprinted = 0
    for raw in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if (event.get("command") == "plan-audit"
                and event.get("item_id") == phase_id
                and event.get("result") in {"audit-green", "audit-attention", "audit-red"}
                and isinstance(event.get("fingerprint"), str)
                and event["fingerprint"]):
            fingerprinted += 1
    return min(block_count, fingerprinted)


def _has_audit_cap_remediation_grant(plan_dir: Path, item_id: str) -> bool:
    """Accept only a recorded direct-close remediation, never chat prose."""
    for path in sorted((Path(plan_dir) / "decisions").glob("D*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts = text.split("---", 2)
        if len(parts) != 3:
            continue
        fields = dict(line.split(":", 1) for line in parts[1].splitlines() if ":" in line)
        body = parts[2]
        if (fields.get("status", "").strip() == "accepted"
                and fields.get("item", "").strip() == item_id
                and "AUDIT-CAP" in body
                and "P5.6 must close" in body
                and "third Audit P5" in body):
            return True
        normalized_body = " ".join(body.split())
        recovery_clause = re.search(
            r"repeat (?:the )?original Validation for (?P<items>.+?) only in fresh native roots",
            normalized_body,
        )
        if (fields.get("status", "").strip() == "accepted"
                and "AUDIT-CAP" in normalized_body
                and "provider-attested" in normalized_body
                and "new terminal attempts" in normalized_body
                and recovery_clause is not None
                and item_id in set(re.findall(r"P\d+\.\d+", recovery_clause.group("items")))):
            return True
    return False


def _authority_request(item_id: str, protected_transition):
    """Validate the narrow request shape for a protected plan transition.

    Ordinary item execution never supplies this value: its authority is the checked item
    carrier.  A validator for an explicitly protected branch may supply the three facts
    it is asking the plan to prove.  The facts are *not* authority themselves; the
    Decision Log resolver below must still find the matching committed grant.
    """
    if protected_transition is None:
        return None
    if not isinstance(protected_transition, dict):
        raise TaskContractBuildError(item_id, "authority", "protected_transition must be a mapping")
    expected = {"gate_id", "branch", "scope"}
    if not expected <= set(protected_transition) or set(protected_transition) - expected - {"boundary", "effect", "environment", "contract_digest"}:
        raise TaskContractBuildError(
            item_id, "authority",
            "protected_transition must contain exactly gate_id, branch and scope")
    request = dict(protected_transition)
    if any(not isinstance(value, str) or not value.strip() for value in request.values()):
        raise TaskContractBuildError(item_id, "authority",
                                     "protected_transition values must be non-empty strings")
    if not _OWNER_GRANT_RE.fullmatch(f"[OWNER-GRANT:{request['gate_id']}]"):
        raise TaskContractBuildError(item_id, "authority", "gate_id has an illegal form")
    return {key: value.strip() for key, value in request.items()}


def declared_authority(item_id: str, fields: dict, *, for_execution: bool = False):
    """Read a finite item gate; prose can flag migration but cannot grant authority.

    An unresolved clarification marker is an explicit statement that the item lacks
    an execution-critical binding.  It must not silently fall through to the routine
    path merely because the author did not also write an ``Authority`` field.
    """
    def text(name):
        value = fields.get(name, "")
        return value[0] if isinstance(value, tuple) else value
    # Design lint and bundle rendering still need to inspect an unfinished item;
    # this becomes a hard boundary only when an executor/recovery path asks to act.
    if (for_execution
            and any(_NEEDS_CLARIFICATION_RE.search(str(text(name)) or "") for name in fields)):
        raise TaskContractBuildError(
            item_id, "Authority",
            "AUTHORITY_CONTRACT_GAP: unresolved NEEDS CLARIFICATION requires a finite Authority gate")
    declaration = (text("Authority") or "").strip()
    if declaration and declaration != "routine":
        match = _AUTHORITY_DECLARATION_RE.fullmatch(declaration)
        if match is None:
            raise TaskContractBuildError(item_id, "authority", "AUTHORITY_CONTRACT_GAP: invalid declaration Authority")
        request = {key: value for key, value in match.groupdict().items() if value is not None}
        if request.get("boundary") == "owner-session":
            if (request.get("effect") != "local-source"
                    or not re.fullmatch(r"checkout|[A-Za-z0-9_]+_test", request.get("environment", ""))):
                raise TaskContractBuildError(item_id, "authority", "AUTHORITY_BOUNDARY: owner-session requires local-source and checkout or *_test")
            validation = str(text("Validation"))
            if (re.search(r"\b(?:deploy|release|fleet|production|secret(?:s)?|rotate[- ]?key)\b", validation, re.IGNORECASE)
                    or re.search(r"\b(?:DB_DATABASE|PGDATABASE)=(?!" + re.escape(request["environment"]) + r"(?:\s|$))", validation)
                    or (request["environment"] == "checkout" and re.search(r"\b(?:migrate|psql)\b", validation))):
                raise TaskContractBuildError(item_id, "authority", "AUTHORITY_BOUNDARY: externalities require provider-proof")
            # Bind executable scope, not progress/status prose. Changing a target,
            # validation command or declared file invalidates the local activation.
            bound = {name: text(name) for name in ("Authority", "Files", "Validation",
                     "Scope Included", "Scope Excluded", "Implementation Rules")}
            request["contract_digest"] = hashlib.sha256(json.dumps(
                bound, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return _authority_request(item_id, request)
    if _LEGACY_AUTHORITY_RE.search("\n".join(str(text(name)) for name in fields)):
        raise TaskContractBuildError(item_id, "authority", "AUTHORITY_CONTRACT_GAP: owner authorization requires finite Authority gate")
    return None


def _decision_number(value: str):
    match = re.fullmatch(r"D(\d+)", (value or "").strip())
    return int(match.group(1)) if match else None


def _materialize_owner_invocation_locked(plan_dir, item_id: str, *, command="plan-run") -> dict:
    """Bind the live owner's exact invocation to an already declared finite gate.

    No caller-supplied evidence, actor, branch or scope is accepted. The provider
    adapter must observe the user message in this session before any carrier write.
    """
    from task import plan_authority, plan_lint, plan_layout, plan_decisions, route_evidence
    plan_dir = Path(plan_dir).resolve()
    if command != "plan-run" or not re.fullmatch(r"P\d+\.\d+", item_id):
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: required exact plan-run item")
    phase_id = item_id.split(".")[0]
    phase_path = plan_layout.phase_path(plan_dir, phase_id)
    phase = plan_lint.parse_phase_md(phase_path, phase_id, plan_lint.Diagnostics(),
                                     layout=plan_layout.layout_version(plan_dir))
    occurrences = phase["items"].get(item_id, []) if phase else []
    if len(occurrences) != 1:
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: item is ambiguous")
    request = declared_authority(item_id, occurrences[0]["fields"], for_execution=True)
    if request is None:
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: finite gate not declared")
    boundary = request.get("boundary", "provider-proof")
    if boundary == "owner-session" and occurrences[0]["fields"].get("Status", ("", None))[0] in plan_lint.TERMINAL_STATUSES:
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: run is already completed")
    verifier, nonce_consumer = route_evidence.authority_preflight(boundary)
    checkout = plan_dir.parent.parent
    semantic = f"task:plan-run {plan_dir.name} {item_id}"
    capture_options = {"allow_additive_owner_followup": True} if boundary == "owner-session" else {}
    evidence = route_evidence.capture_launch(expected_invocation=semantic, expected_cwd=checkout,
                                           require_current_owner_invocation=True, **capture_options)
    # The CLI process fallback proves route flags, not a current owner user message.
    if (evidence.get("source") != "provider-thread-state"
            or evidence.get("invocation") not in ("$ " + semantic, "/" + semantic)
            or evidence.get("cwd") != str(checkout)
            or not evidence.get("thread_id") or not evidence.get("source_version")):
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_UNATTESTED: needed current user-message adapter")
    action = {"plan_id": plan_dir.name, "item_id": item_id, "gate": request,
              "command": semantic, "cwd": str(checkout)}
    action_digest = hashlib.sha256(json.dumps(
        action, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # A retry after successful activation reuses the same decision. It must still
    # observe this session's invocation and pass the full current scope resolver.
    existing = plan_authority.DurableAuthorityStore.for_plan(plan_dir).activation(
        f"{plan_dir.name}\0{item_id}\0{request['gate_id']}")
    if boundary == "owner-session" and existing is not None:
        authority = _resolve_authority(plan_lint, [], plan_dir, item_id, phase_path, "", None, request)
        if not authority[1]:
            raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: grant withdrawn, completed or scope/session changed")
        return {"granted": True, "granted_by": authority[2], "reused": True,
                "boundary": "workflow-guard"}
    try:
        issued = datetime.strptime(evidence["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise TaskContractBuildError(
            item_id, "authority", "OWNER_INVOCATION_UNATTESTED: invalid provider timestamp") from exc
    expires = (issued.timestamp() + 300)
    expires_at = datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    provider = "codex" if evidence["invocation"].startswith("$ ") else "claude-code"
    attestation = evidence.get("owner_attestation")
    if attestation is None:
        attestation = route_evidence.build_owner_attestation(
            evidence, provider=provider, plan_id=plan_dir.name, item_id=item_id,
            action_digest=action_digest, audience="task.owner-authority",
            expires_at=expires_at, nonce=evidence["owner_message_digest"],
        )
    expected_attestation = {**action, "provider": provider,
                            "command": "task:plan-run",
                            "action_digest": action_digest,
                            "audience": "task.owner-authority",
                            "arguments": f"{plan_dir.name} {item_id}",
                            "session_id": evidence["thread_id"],
                            "owner_message_digest": evidence["owner_message_digest"]}
    route_evidence.verify_owner_attestation(
        attestation, expected=expected_attestation, verifier=verifier,
        nonce_consumer=nonce_consumer, protected=boundary == "provider-proof",
    )
    decisions = plan_decisions.load_decisions(plan_dir)
    rows = [({"D#": decision.identifier}, 1) for decision in decisions]
    if not _has_contiguous_decision_identities(rows):
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: Decision Log discontinuity")
    gate_id = request["gate_id"]
    marker = f"[OWNER-GRANT:{gate_id}]"
    if any(marker in decision.decision_text or gate_id in _OWNER_REVOKE_RE.findall(decision.decision_text)
           for decision in decisions):
        authority = _resolve_authority(plan_lint, [], plan_dir, item_id, phase_path, "", None, request)
        if not authority[1]:
            raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: existing grant withdrawn or ambiguous")
        return {"granted": True, "granted_by": authority[2], "reused": True}
    digest = hashlib.sha256(json.dumps({"plan": plan_dir.name, "item": item_id,
                                       "gate": request, "attestation": attestation},
                                      sort_keys=True).encode()).hexdigest()
    message_id = f"invocation-{digest[:16]}"
    filename = f"owner-invocation-{digest[:16]}.md"
    reference = f"brief/{filename}#{message_id}"
    message_path = plan_dir / "brief" / filename
    if message_path.parent.is_symlink() or not message_path.parent.is_dir():
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: brief carrier")
    message = (f"# Exact owner invocation: {plan_dir.name} {item_id}\n\n"
               f"[REPOSITORY-OWNER-MESSAGE:{message_id}] {marker} "
               f"branch=`{request['branch']}`; scope=`{request['scope']}`; provenance=`repository-owner`\n\n"
               f"Boundary: `{attestation['boundary']}` ({boundary}).\n\n"
               "```provider-attestation/v1\n" + json.dumps(attestation, ensure_ascii=False, sort_keys=True)
               + "\n```\n")
    identifier = f"D{len(decisions) + 1}"
    decision_path = plan_dir / "decisions" / f"{identifier}-owner-invocation.md"
    date = str(evidence.get("ts", ""))[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or decision_path.parent.is_symlink():
        raise TaskContractBuildError(item_id, "authority", "OWNER_INVOCATION_INVALID: provenance date/path")
    decision = (f"---\nid: {identifier}\ndate: {date}\nstatus: accepted\nitem: {item_id}\n"
                f"items: [{item_id}]\nsupersedes: []\nsuperseded_by: null\n---\n\n## Solution\n\n"
                f"{marker} branch=`{request['branch']}`; scope=`{request['scope']}`; owner-message=`{reference}`\n\n"
                "## Why\n\nExact provider-attested owner invocation; declared finite scope only.\n")
    from task import plan_bundle
    created = []
    try:
        # The files are prepared under the plan lock, but remain inactive until the
        # durable activation record is published after every validation succeeds.
        for path, payload in ((message_path, message), (decision_path, decision)):
            with path.open("x", encoding="utf-8") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            created.append(path)
        plan_decisions.build_views(plan_dir)
        plan_bundle.build(plan_dir, item_id)
        activation_key = f"{plan_dir.name}\0{item_id}\0{gate_id}"
        activation = {
            "schema_version": "owner-activation/v1", "plan_id": plan_dir.name,
            "item_id": item_id, "gate_id": gate_id, "decision_id": identifier,
            "owner_message": reference, "action_digest": action_digest,
            "attestation_sha256": hashlib.sha256(json.dumps(
                attestation, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest(),
            "boundary": attestation["boundary"],
            "provider": provider, "session_id": evidence["thread_id"],
            "owner_message_digest": evidence["owner_message_digest"],
        }
        if not plan_authority.DurableAuthorityStore.for_plan(plan_dir).activate(
                activation_key, activation):
            raise TaskContractBuildError(item_id, "authority", "OWNER_ACTIVATION_CONFLICT")
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            plan_decisions.build_views(plan_dir)
            plan_bundle.build(plan_dir, item_id)
        except Exception:
            pass
        raise
    return {"granted": boundary == "owner-session", "prepared": True,
            "granted_by": f"decisions/{identifier}:1 {marker}",
            "reused": False, "boundary": attestation["boundary"]}


def materialize_owner_invocation(plan_dir, item_id: str, *, command="plan-run") -> dict:
    """Serialize preparation and publish the authority activation last."""
    root = Path(plan_dir).resolve()
    lock_path = root / ".plan-cache" / "owner-materialization.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _materialize_owner_invocation_locked(root, item_id, command=command)


def _has_contiguous_decision_identities(rows) -> bool:
    """Whether the whole Decision Log is the one checked, append-only carrier.

    A protected grant is meaningful only when its ``D#`` is an identity in the
    plan's actual Decision Log, rather than a syntactically valid row pasted into
    the table.  The plan protocol's log is append-only ``D1`` … ``Dn``: reject a
    gap, duplicate, malformed ID, or reordered old decision here.  This is a
    resolver-local authority check, deliberately not a new plan-wide lint rule;
    ordinary Task Contract builds do not need an owner grant.
    """
    identities = [_decision_number(row.get("D#", "")) for row, _lineno in rows]
    return identities == list(range(1, len(identities) + 1))


def _owner_message_matches(plan_dir: Path, reference: str, request: dict) -> bool:
    """Validate the explicit Layer-0 repository-owner message a grant cites.

    The compact reference is confined to one committed ``brief/*.md`` file.  Its
    referenced line must independently restate the gate, branch and finite scope and
    declare repository-owner provenance.  Copying an owner identity into a Decision
    Log row is therefore insufficient to mint authority.
    """
    reference_match = _OWNER_MESSAGE_REF_RE.fullmatch(reference or "")
    if reference_match is None:
        return False
    message_path = plan_dir / "brief" / reference_match.group("filename")
    try:
        if not message_path.is_file() or message_path.is_symlink():
            return False
        records = [_OWNER_MESSAGE_RECORD_RE.fullmatch(line.strip())
                   for line in message_path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError):
        return False
    matches = [record for record in records
               if record is not None
               and record.group("message_id") == reference_match.group("message_id")]
    return (len(matches) == 1
            and matches[0].group("gate_id") == request["gate_id"]
            and matches[0].group("branch") == request["branch"]
            and matches[0].group("scope") == request["scope"])


def _resolve_authority(plan_lint, plan_lines, plan_dir: Path, item_id: str,
                       phase_path: Path, implementation_rules: str,
                       protected_transition, declared=None):
    """Derive authority only from committed plan-native carriers.

    The routine path is backed by the item block that `build()` already parsed.  A
    protected branch additionally needs one exact Decision Log carrier: marker, branch,
    finite scope, and an explicit repository-owner message reference must parse and bind
    together.  A later revocation wins.  An invalid or absent grant returns an ungranted
    owner gate so `pre_mutation()` emits the frozen `AUTHORITY_BOUNDARY` code instead of
    inventing a new bypass code.
    """
    item_carrier_path = phase_path.parent / f"{item_id}.md"
    item_carrier = f"{item_carrier_path.relative_to(plan_dir).as_posix()}:{item_id}"
    requested = _authority_request(item_id, protected_transition)
    if declared is not None and requested is not None and requested != declared:
        return "owner-gate", False, item_carrier
    request = declared if declared is not None else requested
    if request is None:
        return "routine", True, item_carrier

    marker = f"[OWNER-GRANT:{request['gate_id']}]"
    # The item must itself declare this exact protected transition.  A caller cannot
    # redirect a valid grant to another item/branch merely by supplying kwargs.
    if declared is None and marker not in implementation_rules:
        return "owner-gate", False, item_carrier

    from task import plan_decisions
    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except plan_decisions.DecisionError:
        return "owner-gate", False, item_carrier
    rows = [({"D#": decision.identifier, "Solution": decision.decision_text}, 1)
            for decision in decisions]
    if not _has_contiguous_decision_identities(rows):
        return "owner-gate", False, item_carrier

    grant_rows = []
    revocations = []
    for row, lineno in rows:
        decision_id = _decision_number(row.get("D#", ""))
        decision = (row.get("Solution", "") or "").strip()
        if decision_id is None:
            continue
        if marker in decision:
            grant_rows.append((decision_id, lineno, decision))
        if request["gate_id"] in _OWNER_REVOKE_RE.findall(decision):
            revocations.append(decision_id)

    # Count every exact gate marker before parsing.  A malformed duplicate is still an
    # ambiguity, not a harmless line the resolver may silently skip.
    if len(grant_rows) != 1:
        return "owner-gate", False, item_carrier
    decision_id, lineno, decision = grant_rows[0]
    matched_decision = decisions[decision_id - 1]
    if (matched_decision.status != "accepted" or matched_decision.superseded_by is not None
            or (declared is not None and item_id not in matched_decision.items)):
        return "owner-gate", False, item_carrier
    record = _OWNER_GRANT_RECORD_RE.fullmatch(decision)
    if (record is None
            or record.group("gate_id") != request["gate_id"]
            or record.group("branch") != request["branch"]
            or record.group("scope") != request["scope"]
            or not _owner_message_matches(plan_dir, record.group("owner_message"), request)
            or any(revocation > decision_id for revocation in revocations)):
        return "owner-gate", False, item_carrier
    # Legacy message/decision pairs stay readable but inactive.  Only the durable
    # activation-last record can turn the workflow guard into an executable grant.
    from task import plan_authority
    activation_key = f"{plan_dir.name}\0{item_id}\0{request['gate_id']}"
    try:
        activation = plan_authority.DurableAuthorityStore.for_plan(plan_dir).activation(
            activation_key)
    except plan_authority.AuthorityFrameError:
        return "owner-gate", False, item_carrier
    expected_action = {"plan_id": plan_dir.name, "item_id": item_id,
                       "gate": request,
                       "command": f"task:plan-run {plan_dir.name} {item_id}",
                       "cwd": str(plan_dir.parent.parent)}
    expected_digest = hashlib.sha256(json.dumps(
        expected_action, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    if (not isinstance(activation, dict)
            or activation.get("schema_version") != "owner-activation/v1"
            or activation.get("plan_id") != plan_dir.name
            or activation.get("item_id") != item_id
            or activation.get("gate_id") != request["gate_id"]
            or activation.get("decision_id") != f"D{decision_id}"
            or activation.get("owner_message") != record.group("owner_message")
            or activation.get("action_digest") != expected_digest
            or activation.get("boundary") != ("workflow-guard" if request.get("boundary") == "owner-session" else "security-boundary")):
        return "owner-gate", False, item_carrier
    if request.get("boundary") == "owner-session":
        from task import route_evidence
        try:
            evidence = route_evidence.capture_launch(
                expected_invocation=expected_action["command"], expected_cwd=plan_dir.parent.parent,
                require_current_owner_invocation=True, allow_additive_owner_followup=True)
            # Completion consumes this finite run even while its decision remains
            # auditable. A later run needs a new gate, never an old activation.
            phase = plan_lint.parse_phase_md(phase_path, item_id.split(".")[0], plan_lint.Diagnostics(), layout="v2")
            item = phase["items"][item_id][0]
            completed = item["fields"].get("Status", ("", None))[0] in plan_lint.TERMINAL_STATUSES
        except (route_evidence.RouteEvidenceError, KeyError, TypeError):
            return "owner-gate", False, item_carrier
        if (completed or evidence.get("thread_id") != activation.get("session_id")
                or not evidence.get("invocation", "").startswith("$ " if activation.get("provider") == "codex" else "/")
                or evidence.get("owner_message_digest") != activation.get("owner_message_digest")):
            return "owner-gate", False, item_carrier
        return "owner-gate", True, f"decisions/D{decision_id}:1 {marker}"
    # The activation record is local agent-writable state.  Current providers expose
    # no independently re-verifiable grant channel, so protected execution stays
    # fail-closed even when legacy/local carriers are internally consistent.
    return "owner-gate", False, item_carrier


# D78/ — closed literal set of §3 Routing route-column headers `plan-protocol` §9
# Back-compat declares VALID today: the canon form plus exactly the two legacy spellings
# measured live on the fleet (`findings/14` M4.1). Preference order matters (canon first);
# no fuzzy/normalized/regex match — a header outside this tuple is an unrecognized table,
# never a guess (Implementation Rules (2)).
_ROUTING_HEADER_CANON = "Model class/effort"
_ROUTING_HEADER_CANDIDATES = (_ROUTING_HEADER_CANON,)
_EXECUTABLE_ROUTING_COLUMNS = (
    "Batch", "Items", "Model class/effort", "Exec", "Review", "Why",
)
# Canonical Exec spellings; the rest are legacy aliases of `run`.
EXEC_MODE_RUN = "run"
EXEC_MODE_DESIGN = "plan-design"
_EXEC_MODES = {"run": EXEC_MODE_RUN, "plan-run": EXEC_MODE_RUN,
               "plan-exec": EXEC_MODE_RUN, "manual": EXEC_MODE_RUN,
               "plan-design": EXEC_MODE_DESIGN}


def resolve_exec(value: str) -> str:
    """Resolve a Routing `Exec` cell to its one execution mode (`run` or `plan-design`).

    Legacy `plan-exec`/`manual`/`plan-run` resolve to `run`; the raw cell stays in the
    table digest and item projection.
    """
    modes = _EXEC_MODES
    try:
        return modes[value.strip()]
    except (KeyError, AttributeError) as exc:
        raise TaskContractBuildError("routing", "Routing", f"invalid Exec {value!r}") from exc

_EXECUTABLE_ROUTING_REVIEW_VALUES = frozenset(("full", "light", "none"))

# Default location of the committed provider routing carrier this module reads
# `mappings.*.class_selectors` from (D78 Implementation Rules (1) — one name-to-class
# carrier, never a second table in this module). Package-relative, same convention
# `command_render.mapping_from_catalog` already uses for its own sibling config
# (`Path(__file__).resolve().parents[N] / "configs/..."`) — never cwd/env discovery
# (`command_catalog`'s own module docstring bans that for the loader this calls).
_DEFAULT_ROUTING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "command-routing.json"
_REVIEW_ORDER = ("none", "light", "full")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _model_class_name_map(routing_metadata: dict) -> dict:
    """`{model-name: {classes it is bound to}}` built fresh from every provider's
    `mappings.<provider>.class_selectors` (committed `command-routing.json`, read via
    `command_catalog.load_routing_metadata` by the caller — this function never opens a
    file itself). A name bound to more than one class is ambiguous by construction of the
    fleet-wide carrier; `_resolve_model_class` below refuses it rather than picking
    either winner (D78: "name ... occurring in two different classes gives the same
    typed failure")."""
    name_to_classes: dict = {}
    for provider in routing_metadata.get("mappings", {}).values():
        for model_class, names in provider.get("class_selectors", {}).items():
            for name in names:
                name_to_classes.setdefault(name, set()).add(model_class)
    return name_to_classes


def _resolve_model_class(token: str, name_to_classes: dict, item_id: str, raw_cell: str) -> str:
    """Route-column model token → frozen `MODEL_CLASS_ORDER` class. Already a class name
    (the canon form this plan's own §3 uses) → returned as-is. A provider model name (the
    FOREMAN §3 form, e.g. `opus`) → looked up through the committed carrier ONLY — this
    module never grows its own name table (D78 Implementation Rules (1), D6). Unknown or
    ambiguous (bound to two classes at once) → typed refusal naming the offending cell,
    never a guessed class."""
    if token in MODEL_CLASS_ORDER:
        return token
    classes = name_to_classes.get(token)
    if not classes or len(classes) != 1:
        raise TaskContractBuildError(
            item_id, "Routing",
            f"route cell {raw_cell!r}: model token {token!r} is neither a class "
            f"{MODEL_CLASS_ORDER} nor an unambiguous name in command-routing.json "
            f"class_selectors (resolved classes: {sorted(classes) if classes else []})")
    return next(iter(classes))


def _routing_digest(plan_dir: Path, items: tuple[str, ...]) -> tuple[str, str]:
    """Return the two immutable inputs a batch receipt must bind.

    The Routing table remains the only authority.  Item specs are included only
    as an invalidation boundary: editing a member's contract invalidates an old
    continuation receipt without manufacturing a second routing carrier.
    """
    from task import plan_layout

    plan_bytes = (plan_dir / "plan.md").read_bytes()
    spec_bytes = b"".join(
        plan_layout.carrier_path(plan_dir, "item-spec", item_id=item).read_bytes()
        for item in items
    )
    return hashlib.sha256(plan_bytes).hexdigest(), hashlib.sha256(spec_bytes).hexdigest()


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def executable_routing_table(plan_dir: Path | str) -> dict:
    """Return the sole executable ``§3 Routing`` table for a v2 plan.

    A Routing section may contain explanatory or provider-mapping tables.  They
    are not executable Routing merely because they have pipe-delimited rows.
    The exact six-column header bounds the one executable table.  A second
    matching header is ambiguity, never a later table to silently prefer.
    """
    from task import plan_lint

    plan_dir = Path(plan_dir)
    lines = plan_lint._read_lines(plan_dir / "plan.md") or []
    _index, body, start = plan_lint._find_section(lines, _ROUTING_HEADER_RE)
    if body is None:
        raise TaskContractBuildError(
            "routing", "Routing", "no `## 3. Routing` section found in plan.md")

    def cells(raw: str) -> tuple[str, ...]:
        value = raw.strip()
        if value.startswith("|"):
            value = value[1:]
        if value.endswith("|"):
            value = value[:-1]
        return tuple(cell.strip() for cell in value.split("|"))

    matches: list[tuple[int, list[tuple[dict[str, object], int]]]] = []
    for index, raw in enumerate(body):
        if not raw.strip().startswith("|") or cells(raw) != _EXECUTABLE_ROUTING_COLUMNS:
            continue
        separator_index = index + 1
        if separator_index >= len(body):
            raise TaskContractBuildError(
                "routing", "Routing", f"line {start + index}: executable table has no separator")
        separator = cells(body[separator_index])
        if (len(separator) != len(_EXECUTABLE_ROUTING_COLUMNS)
                or not all(re.fullmatch(r":?-{2,}:?", cell) for cell in separator)):
            raise TaskContractBuildError(
                "routing", "Routing", f"line {start + index}: executable table has an invalid separator")
        rows: list[tuple[dict[str, object], int]] = []
        row_index = separator_index + 1
        while row_index < len(body) and body[row_index].strip().startswith("|"):
            values = cells(body[row_index])
            if len(values) != len(_EXECUTABLE_ROUTING_COLUMNS):
                raise TaskContractBuildError(
                    "routing", "Routing", f"line {start + row_index}: executable table must have exactly six columns")
            row = dict(zip(_EXECUTABLE_ROUTING_COLUMNS, values))
            items = plan_lint._routing_items(row["Items"].strip().strip("`"))
            if not items:
                raise TaskContractBuildError(
                    "routing", "Routing", f"line {start + row_index}: invalid Items form")
            row["_items"] = tuple(items)
            rows.append((row, start + row_index))
            row_index += 1
        matches.append((start + index, rows))

    if not matches:
        raise TaskContractBuildError(
            "routing", "Routing",
            "no executable table with exact header `Batch | Items | Model class/effort | Exec | Review | Why`")
    if len(matches) != 1:
        lines = ", ".join(str(line) for line, _rows in matches)
        raise TaskContractBuildError(
            "routing", "Routing", f"duplicate executable Routing tables at lines {lines}")
    header_line, rows = matches[0]
    if not rows:
        raise TaskContractBuildError(
            "routing", "Routing", "executable Routing table may not be empty")
    owners: set[str] = set()
    for row, line in rows:
        for item_id in row["_items"]:
            if item_id in owners:
                raise TaskContractBuildError(
                    item_id, "Routing", f"line {line}: item is assigned more than once")
            owners.add(item_id)
    digest_payload = "\n".join(
        ["|".join(_EXECUTABLE_ROUTING_COLUMNS)]
        + ["|".join(row[column] for column in _EXECUTABLE_ROUTING_COLUMNS) for row, _line in rows]
    )
    return {
        "headers": _EXECUTABLE_ROUTING_COLUMNS,
        "header_line": header_line,
        "rows": tuple(rows),
        "digest": hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    }


def compile_batch_routing(plan_dir, *, routing_config_path=None) -> dict:
    """Compile Routing once into item and batch projections.

    This compiler accepts only the exact executable v2 table.  Historical
    item-route spellings remain isolated in ``build()``'s legacy resolver and
    never acquire an inferred execution group.
    """
    from task import command_catalog, plan_lint

    plan_dir = Path(plan_dir)
    table = executable_routing_table(plan_dir)
    rows = table["rows"]
    route_header = _ROUTING_HEADER_CANON

    metadata = command_catalog.load_routing_metadata(
        routing_config_path or _DEFAULT_ROUTING_CONFIG_PATH)
    names = _model_class_name_map(metadata)

    def parse_route(raw: str, item: str) -> tuple[str, str]:
        model, sep, effort = (raw or "").partition("/")
        model, effort = model.strip(), effort.strip()
        if not sep or not model or effort not in EFFORT_ORDER:
            raise TaskContractBuildError(item, "Routing", f"route cell {raw!r} does not parse as '<model>/<effort>'")
        return _resolve_model_class(model, names, item, raw), effort

    item_rows: dict[str, dict] = {}
    groups: dict[str, list[dict]] = {}
    for row, line in rows:
        items = row["_items"]
        batch = (row.get("Batch") or "solo").strip()
        if not batch or not plan_lint._ROUTING_BATCH_RE.fullmatch(batch):
            raise TaskContractBuildError("routing", "Routing", f"line {line}: invalid Batch {batch!r}")
        declared_exec = (row.get("Exec") or "").strip()
        exec_mode = resolve_exec(declared_exec)
        review = (row.get("Review") or "").strip()
        if review not in _EXECUTABLE_ROUTING_REVIEW_VALUES:
            raise TaskContractBuildError("routing", "Routing", f"line {line}: invalid Review {review!r}")
        batches = [batch] * len(items)
        for item, item_batch in zip(items, batches):
            if item in item_rows:
                raise TaskContractBuildError(item, "Routing", "item is assigned more than once")
            model_class, effort = parse_route(row.get(route_header, ""), item)
            batch_key = f"solo:{item}" if item_batch.lower() == "solo" else item_batch
            entry = {"item_id": item, "batch": item_batch, "batch_key": batch_key, "route": {
                "model_class": model_class, "effort": effort},
                "exec": exec_mode, "declared_exec": declared_exec, "review": review, "line": line,
                "recommended": row.get("Why", "").strip().startswith("recommended:")}
            item_rows[item] = entry
            groups.setdefault(batch_key, []).append(entry)

    compiled = {}
    for batch_key, members in groups.items():
        batch = members[0]["batch"]
        members.sort(key=lambda entry: (entry["item_id"].split(".")[0], int(entry["item_id"].split(".")[1])))
        items = tuple(entry["item_id"] for entry in members)
        phases = {item.split(".")[0] for item in items}
        execs = {entry["exec"] for entry in members}
        if batch.lower() == "solo":
            if len(members) != 1:
                # Legacy projections are split above, so this is a new-plan error.
                raise TaskContractBuildError("routing", "Routing", "Batch solo may contain one item")
        elif len(members) < 2 or len(phases) != 1 or len(execs) != 1:
            raise TaskContractBuildError("routing", "Routing", f"Batch {batch!r} is not a phase-local execution unit")
        numbers = [int(item.split(".")[1]) for item in items]
        if batch.lower() != "solo" and numbers != list(range(numbers[0], numbers[-1] + 1)):
            raise TaskContractBuildError("routing", "Routing", f"Batch {batch!r} is not adjacent")
        route = {"model_class": max((entry["route"]["model_class"] for entry in members), key=MODEL_CLASS_ORDER.index),
                 "effort": max((entry["route"]["effort"] for entry in members), key=EFFORT_ORDER.index)}
        review = max((entry["review"] for entry in members), key=lambda value: _REVIEW_ORDER.index(value)
                     if value in _REVIEW_ORDER else len(_REVIEW_ORDER))
        routing_digest, spec_digest = _routing_digest(plan_dir, items)
        compiled[batch_key] = {"batch_id": batch, "items": items, "route": route,
                           "exec": next(iter(execs)), "review": review,
                           "routing_digest": routing_digest, "spec_digest": spec_digest,
                           "handoff_digest": _file_digest(plan_dir / "handoff.md"),
                           "recommended": all(entry["recommended"] for entry in members)}
    return {"items": item_rows, "batches": compiled, "routing_digest": table["digest"]}


def normalize_batch_request(request) -> tuple[str, ...]:
    """Normalize the closed item/range request grammar without accepting prose."""
    from task import plan_lint

    tokens = (request,) if isinstance(request, str) else tuple(request or ())
    expanded = []
    for token in tokens:
        if not isinstance(token, str):
            raise ValueError("BATCH_AMBIGUOUS: item request must contain strings")
        items = plan_lint._routing_items(token.strip().strip("`"))
        if not items:
            raise ValueError(f"BATCH_AMBIGUOUS: invalid request {token!r}")
        expanded.extend(items)
    if not expanded or len(set(expanded)) != len(expanded):
        raise ValueError("BATCH_AMBIGUOUS: request is empty or repeats an item")
    return tuple(expanded)


def build_batch_receipt(batch: dict, *, membership=None, completed_prefix=(), handoff_digest=None) -> dict:
    """Create a durable checkpoint for the owner-authorized batch workset.

    Recommended Routing groups may admit an ordered subset.  ``membership`` binds that
    exact invocation scope; it never silently widens to every advisory group member.
    """
    prefix = tuple(completed_prefix)
    declared = tuple(batch["items"])
    items = tuple(declared if membership is None else membership)
    positions = [declared.index(item) for item in items if item in declared]
    if (not items or len(positions) != len(items) or positions != sorted(positions)
            or len(set(items)) != len(items)):
        raise ValueError("BATCH_STALE: membership is not an ordered batch subset")
    if items[:len(prefix)] != prefix:
        raise ValueError("BATCH_STALE: completed prefix is not a batch prefix")
    if handoff_digest is None:
        handoff_digest = batch.get("handoff_digest")
    if handoff_digest is not None and not _SHA256_RE.fullmatch(handoff_digest):
        raise ValueError("BATCH_STALE: handoff digest must be SHA-256")
    return {"schema_version": "batch-receipt/v1", "batch_id": batch["batch_id"],
            "membership": list(items),
            "invocation_digest": hashlib.sha256("\n".join(items).encode()).hexdigest(),
            "completed_prefix": list(prefix), "routing_digest": batch["routing_digest"],
            "spec_digest": batch["spec_digest"], "handoff_digest": handoff_digest,
            "stop_disposition": "continue"}


def validate_batch_receipt(receipt: dict) -> None:
    required = {"schema_version", "batch_id", "membership", "invocation_digest", "completed_prefix",
                "routing_digest", "spec_digest", "handoff_digest", "stop_disposition"}
    if not isinstance(receipt, dict) or set(receipt) != required or receipt.get("schema_version") != "batch-receipt/v1":
        raise ValueError("BATCH_STALE: malformed receipt")
    members, prefix = receipt["membership"], receipt["completed_prefix"]
    if (not isinstance(receipt["batch_id"], str) or not members or not all(isinstance(item, str) for item in members)
            or members[:len(prefix)] != prefix or receipt["stop_disposition"] != "continue"):
        raise ValueError("BATCH_STALE: malformed receipt")
    if receipt["invocation_digest"] != hashlib.sha256("\n".join(members).encode()).hexdigest():
        raise ValueError("BATCH_STALE: invocation digest mismatch")
    if any(not isinstance(receipt[key], str) or not _SHA256_RE.fullmatch(receipt[key])
           for key in ("invocation_digest", "routing_digest", "spec_digest")):
        raise ValueError("BATCH_STALE: malformed receipt digest")
    if receipt["handoff_digest"] is not None and not _SHA256_RE.fullmatch(receipt["handoff_digest"]):
        raise ValueError("BATCH_STALE: malformed handoff digest")


def _derived_completed_prefix(plan_dir, membership) -> tuple[str, ...]:
    """Read the contiguous GREEN prefix from authoritative terminal evidence."""
    from task import plan_item_state, terminal_policy

    prefix = []
    for item in membership:
        try:
            evidence = plan_item_state.material_terminal_evidence(plan_dir, item)
        except plan_item_state.ItemStateError:
            break
        if evidence.get("result") not in {"closed-green", "closed-deviations"}:
            break
        try:
            terminal_policy.validate(
                evidence.get("decision"), result=evidence["result"],
                plan_dir=Path(plan_dir), item_id=item,
            )
        except terminal_policy.TerminalPolicyError as exc:
            raise ValueError(f"BATCH_STALE: invalid terminal evidence for {item}: {exc}") from exc
        prefix.append(item)
    return tuple(prefix)


def _receipt_matches_batch(receipt: dict, batch: dict, membership) -> bool:
    return (
        receipt["batch_id"] == batch["batch_id"]
        and receipt["membership"] == list(membership)
        and receipt["routing_digest"] == batch["routing_digest"]
        and receipt["spec_digest"] == batch["spec_digest"]
        and receipt["handoff_digest"] == batch.get("handoff_digest")
    )


def admit_batch(plan_dir, request, *, receipt=None, routing_config_path=None, repeat_admission=None) -> dict:
    """Return the sole pre-mutation batch verdict; this function never mutates state."""
    try:
        requested = normalize_batch_request(request)
    except ValueError:
        return {"verdict": "BATCH_AMBIGUOUS", "batch": None, "requested": [], "canonical": None}
    compiled = compile_batch_routing(plan_dir, routing_config_path=routing_config_path)
    owners = [compiled["items"].get(item, {}).get("batch_key") for item in requested]
    if not all(owners) or len(set(owners)) != 1:
        return {"verdict": "BATCH_AMBIGUOUS", "batch": None, "requested": list(requested), "canonical": None}
    batch = compiled["batches"][owners[0]]
    exact = tuple(batch["items"])
    if repeat_admission is not None:
        from task import plan_repeat
        try:
            plan_repeat.validate(plan_dir, repeat_admission, requested=requested)
        except (ValueError, OSError) as exc:
            return {"verdict": "REPEAT_ADMISSION_REJECTED", "batch": batch,
                    "requested": list(requested), "canonical": list(exact), "reason": str(exc)}
        if batch["batch_id"].lower() != "solo" or requested != exact:
            return {"verdict": "BATCH_REQUIRED", "batch": batch,
                    "requested": list(requested), "canonical": list(exact)}
        return {"verdict": "ALLOW", "batch": batch, "requested": list(requested),
                "canonical": list(exact), "repeat_admission": repeat_admission}
    if batch["recommended"]:
        # Membership/order and the currently runnable frontier are separate
        # predicates.  Future consumers are checked only after their producers
        # have durable terminal evidence; no future GREEN is fabricated here.
        from task import plan_bundle, plan_admission, plan_item_state, terminal_policy, review_policy
        declared_positions = [exact.index(item) for item in requested]
        if declared_positions != sorted(declared_positions):
            return {"verdict": "BATCH_REQUIRED", "batch": batch,
                    "requested": list(requested), "canonical": sorted(requested, key=exact.index)}
        if receipt is None:
            workset = requested
            try:
                prefix = _derived_completed_prefix(plan_dir, workset)
            except ValueError as exc:
                return {"verdict": "BATCH_STALE", "batch": batch,
                        "requested": list(requested), "canonical": list(workset),
                        "reason": str(exc)}
            checkpoint = build_batch_receipt(
                batch, membership=workset, completed_prefix=prefix)
        else:
            try:
                validate_batch_receipt(receipt)
            except ValueError:
                return {"verdict": "BATCH_STALE", "batch": batch,
                        "requested": list(requested), "canonical": list(requested)}
            workset = tuple(receipt["membership"])
            if (receipt["batch_id"] != batch["batch_id"]
                    or receipt["routing_digest"] != batch["routing_digest"]
                    or receipt["spec_digest"] != batch["spec_digest"]
                    or receipt["handoff_digest"] != batch.get("handoff_digest")
                    or any(item not in exact for item in workset)
                    or [exact.index(item) for item in workset] != sorted(exact.index(item) for item in workset)):
                return {"verdict": "BATCH_STALE", "batch": batch,
                        "requested": list(requested), "canonical": list(workset)}
            try:
                prefix = _derived_completed_prefix(plan_dir, workset)
            except ValueError as exc:
                return {"verdict": "BATCH_STALE", "batch": batch,
                        "requested": list(requested), "canonical": list(workset),
                        "reason": str(exc)}
            if tuple(receipt["completed_prefix"]) != prefix:
                return {"verdict": "BATCH_STALE", "batch": batch,
                        "requested": list(requested), "canonical": list(workset),
                        "reason": "completed prefix does not match terminal evidence"}
            suffix = workset[len(prefix):]
            if requested != suffix:
                return {"verdict": "BATCH_REQUIRED", "batch": batch,
                        "requested": list(requested), "canonical": list(suffix)}
            checkpoint = receipt
        try:
            for item in prefix:
                evidence = plan_item_state.material_terminal_evidence(plan_dir, item)
                if evidence["result"] not in {"closed-green", "closed-deviations"}:
                    raise plan_bundle.BundleError(f"completed-prefix-not-terminal: {item}")
                terminal_policy.validate(evidence["decision"], result=evidence["result"],
                                         plan_dir=Path(plan_dir), item_id=item)
            frontier = requested[0] if requested else None
            if frontier is None:
                raise plan_bundle.BundleError("workset-complete")
            state = plan_item_state.state_model(plan_dir, frontier)[0]["state"]["position"]
            if (state["status"] not in {"⬜ Not started", "🟡 In progress"}
                    and not review_policy.pending_phase_repair(plan_dir, frontier)):
                raise plan_bundle.BundleError(f"item-not-ready: {frontier}: {state['status']}")
            # Dry rendering validates declarations without requiring a persistent
            # bundle before the preparation owner has had a chance to build it.
            plan_bundle.model(plan_dir, frontier)
            plan_bundle.producer_readiness(plan_dir, frontier)
            fields = plan_bundle._fields(Path(plan_dir), frontier)
            for field in ("Inputs", "Required Reads"):
                for raw in plan_bundle._raw_entries(fields.get(field, ""), field):
                    producer = plan_admission.producer_annotation(raw)
                    if producer:
                        evidence = plan_item_state.material_terminal_evidence(plan_dir, producer)
                        if evidence["result"] not in {"closed-green", "closed-deviations"}:
                            raise plan_bundle.BundleError(f"dependency-not-ready: {producer}")
                        terminal_policy.validate(evidence["decision"], result=evidence["result"],
                                                 plan_dir=Path(plan_dir), item_id=producer)
        except (plan_bundle.BundleError, plan_item_state.ItemStateError,
                terminal_policy.TerminalPolicyError, review_policy.ReviewPolicyError) as exc:
            return {"verdict": "BATCH_STALE", "batch": batch,
                    "requested": list(requested), "canonical": list(workset),
                    "reason": str(exc)}
        return {"verdict": "ALLOW", "batch": batch,
                "requested": list(requested), "canonical": list(workset),
                "batch_receipt": checkpoint}
    try:
        derived_prefix = _derived_completed_prefix(plan_dir, exact)
    except ValueError as exc:
        return {"verdict": "BATCH_STALE", "batch": batch,
                "requested": list(requested), "canonical": list(exact),
                "reason": str(exc)}
    if requested == exact and not derived_prefix:
        return {"verdict": "ALLOW", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if batch["batch_id"].lower() == "solo":
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if receipt is None:
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    try:
        validate_batch_receipt(receipt)
    except ValueError:
        return {"verdict": "BATCH_STALE", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if not _receipt_matches_batch(receipt, batch, exact):
        return {"verdict": "BATCH_STALE", "batch": batch, "requested": list(requested), "canonical": list(exact)}
    if tuple(receipt["completed_prefix"]) != derived_prefix:
        return {"verdict": "BATCH_STALE", "batch": batch,
                "requested": list(requested), "canonical": list(exact),
                "reason": "completed prefix does not match terminal evidence"}
    suffix = exact[len(derived_prefix):]
    if requested != suffix:
        return {"verdict": "BATCH_REQUIRED", "batch": batch, "requested": list(requested), "canonical": list(suffix)}
    return {"verdict": "ALLOW", "batch": batch, "requested": list(requested), "canonical": list(suffix)}


def _find_routing_row(plan_lint_mod, plan_lines, item_id: str, routing_metadata: dict):
    """Reuses `plan_lint`'s own generic table parser (`_find_section`/
    `_parse_table` — already the SSOT for Meta/Status Board/Phase Status tables) over the
    `## 3. Routing` section instead of a second parser. Returns `(model_class, effort)` —
    both already frozen-ladder members — or raises `TaskContractBuildError` naming the
    item, field `"Routing"` and the concrete cause (D78: no fabricated empty pair ever
    reaches `build()`'s caller, no unrecognized form is silently guessed at).

    An `Items` cell that is a comma list covering this item (`P8.5, P8.6` — the shape that
    blocked 7 live fleet items, `research/25` §1) gets a DIAGNOSTIC refusal naming the cell,
    its line and both legal forms; it stays a refusal — the list is not a legal form (D124,
    P8.10). Every other unrecognized cell keeps the historical blind text."""
    _, body, start = plan_lint_mod._find_section(plan_lines, _ROUTING_HEADER_RE)
    if body is None:
        raise TaskContractBuildError(item_id, "Routing", "no `## 3. Routing` section found in plan.md")
    headers, rows, _ = plan_lint_mod._parse_table(body, start)
    if headers is None:
        raise TaskContractBuildError(item_id, "Routing", "`## 3. Routing` section carries no table")
    header = next((candidate for candidate in _ROUTING_HEADER_CANDIDATES if candidate in headers), None)
    if header is None:
        raise TaskContractBuildError(
            item_id, "Routing",
            f"no recognized route-column header among {headers!r}; supported (closed set): "
            f"{_ROUTING_HEADER_CANDIDATES!r}")

    phase_token = item_id.split(".")[0]
    try:
        item_n = int(item_id.split(".")[1])
    except (IndexError, ValueError):
        item_n = None
    name_to_classes = _model_class_name_map(routing_metadata)

    def _resolve(raw_cell: str):
        model_token, sep, effort = raw_cell.partition("/")
        model_token, effort = model_token.strip(), effort.strip()
        if not sep or not model_token or not effort:
            raise TaskContractBuildError(
                item_id, "Routing", f"route cell {raw_cell!r} does not parse as '<model>/<effort>'")
        model_class = _resolve_model_class(model_token, name_to_classes, item_id, raw_cell)
        if effort not in EFFORT_ORDER:
            raise TaskContractBuildError(
                item_id, "Routing",
                f"route cell {raw_cell!r}: effort {effort!r} is outside the frozen ladder {EFFORT_ORDER}")
        return model_class, effort

    for row, _lineno in rows:
        cell = (row.get("Items", "") or "").strip().strip("`")
        if cell == item_id:
            return _resolve(row.get(header, ""))
        m = _ROUTING_RANGE_RE.match(cell)
        if m and item_n is not None and m.group(1) == phase_token == m.group(3):
            lo, hi = int(m.group(2)), int(m.group(4))
            if lo <= item_n <= hi:
                return _resolve(row.get(header, ""))

    def _token_covers(token: str) -> bool:
        """The same two matchers the loop above uses, applied to ONE token of a comma
        list — for DIAGNOSIS ONLY. A covering token never yields a route (the list stays
        illegal, D124: «failure remains failure»); it only proves the refusal is about the
        cell's FORM, not about a missing row."""
        if token == item_id:
            return True
        match = _ROUTING_RANGE_RE.match(token)
        return bool(match and item_n is not None and match.group(1) == phase_token == match.group(3)
                    and int(match.group(2)) <= item_n <= int(match.group(4)))

    range_form = f"{phase_token}.a–{phase_token}.b"
    for row, lineno in rows:
        cell = (row.get("Items", "") or "").strip().strip("`")
        # Narrow by construction (Code Guidance): a comma AND a token that covers this item.
        # Any other unparsed cell keeps the blind text below — a diagnostic that guessed the
        # cause on a foreign shape would lie about the fix.
        if "," not in cell or not any(_token_covers(t.strip().strip("`")) for t in cell.split(",")):
            continue
        raise TaskContractBuildError(
            item_id, "Routing",
            f"§3 Routing row {cell!r} (line {lineno}) is a comma list — an illegal `Items` "
            f"cell form; legal forms (closed set, plan-protocol §9): {item_id!r} (a single item) "
            f"or {range_form!r} (a single-phase range). Split the row per item; the batch "
            f"belongs in the `Batch` column.")
    raise TaskContractBuildError(item_id, "Routing", "no §3 Routing row found for this item")


def build(plan_dir, item_id, *, actual_route=None, capabilities=(), bundle_privacy=None,
         protected_transition=None,
         next_form="run-items", next_context=None,
         next_origin="approved-goal", next_changed_by=None, carrier=None,
         routing_config_path=None, admission_route=None) -> dict:
    """Task Contract v1 producer — compiles `phases/Pn.md` + `plan.md`
    §3/§0 fields for one item into the exact 15-key schema
    `task-contract-v1.schema.json` declares. Full field-mapping table:
    .

    Reuses `task.plan_lint`'s own field parser (`parse_phase_md`/`parse_plan_md`,
    plus its generic `_find_section`/`_parse_table` table reader for §3 Routing)
    via a LAZY import — the same circular-import pattern `evaluate_finding`
    already uses for `review_policy` (`plan_lint` imports `task_contract` at
    module level; `task_contract` importing `plan_lint` back at module level
    would be circular). Never a second parser of item fields (Code Guidance,
    anti-duplicate-SSOT).

    Deterministic by default: two calls over the same committed tree produce
    byte-identical JSON (`content_hash` included) — `actual_route` is NOT
    captured live unless the caller supplies one, since a bare CLI invocation
    must be repeatable across processes/sessions.

    Anti-padding (Implementation Rules (2)): an item field that is empty
    (the canonical `"—"` placeholder) where the schema requires a value
    raises `TaskContractBuildError` naming the field and item — never a
    fabricated placeholder dressed up as data.

    `protected_transition` — an optional exact request (`gate_id`, `branch`, `scope`) for
    a branch that the item itself declares as owner-gated. It never grants authority by
    itself: `_resolve_authority` verifies a later Decision Log marker. The former
    `authority_*` kwargs are deliberately absent, so a caller cannot restore a foreign
    D-number or fabricate an allow result.

    `routing_config_path` — the committed routing carrier
    `_find_routing_row`/`_resolve_model_class` read `mappings.*.class_selectors` from,
    via `command_catalog.load_routing_metadata` (never a second name table in this
    module). Defaults to this package's own `configs/command-routing.json`
    (`_DEFAULT_ROUTING_CONFIG_PATH`, derived from `__file__` — the same
    package-relative convention `command_render.mapping_from_catalog` already uses for
    its sibling config); a caller MAY override it, but never supplies cwd/env instead.
    """
    from task import plan_lint  # lazy — avoids a plan_lint↔task_contract circular import
    from task import plan_layout
    from task import route_evidence  # lazy — same reasoning, route assembly only
    from task import review_policy  # lazy — reuse of loop_budget constants only
    from task import command_catalog  # lazy — same reasoning, class_selectors carrier only
    from task import plan_weight  # lazy — shared execution-path tokenization

    plan_dir = Path(plan_dir)
    phase_token = item_id.split(".")[0]
    diag = plan_lint.Diagnostics()
    layout = plan_layout.layout_version(plan_dir)
    if next_context is None:
        next_context = "continue-root" if layout == "v2" else "same-session — item"
    plan_meta, _ = plan_lint.parse_plan_md(plan_layout.plan_core_path(plan_dir), diag)
    # `parse_plan_md` resolves v2 Version/Status/Last Updated from the owner
    # projection. Keep this compiler on that single path rather than reopening
    # plan.md and accidentally restoring the legacy monolith as a source.
    for field in ("Version", "Status", "Last Updated"):
        if not plan_meta or field not in plan_meta:
            raise TaskContractBuildError(item_id, "Meta", f"no field {field!r} in owner view")
    phase_path = plan_layout.phase_path(plan_dir, phase_token)
    phase = plan_lint.parse_phase_md(phase_path, phase_token, diag, layout=layout)
    occurrences = phase["items"].get(item_id) if phase else None
    if not occurrences:
        raise TaskContractBuildError(item_id, "item", f"no item block found in {phase_path}")
    fields = occurrences[0]["fields"]
    declared = declared_authority(item_id, fields, for_execution=True)

    def field_text(name):
        value, _ = fields.get(name, ("", None))
        return (value or "").strip()

    _require_field(item_id, fields, "Intent")
    scope_included, scope_included_ln = _require_field(item_id, fields, "Scope Included")
    scope_excluded, scope_excluded_ln = _require_field(item_id, fields, "Scope Excluded")
    impl_rules_text = field_text("Implementation Rules")
    impl_rules_ln = fields.get("Implementation Rules", ("", None))[1]
    code_guidance_text = field_text("Code Guidance")
    code_guidance_ln = fields.get("Code Guidance", ("", None))[1]
    inputs_text = field_text("Inputs")
    required_reads_text = field_text("Required Reads")
    validation_text, _ = _require_field(item_id, fields, "Validation")
    deliverables, _ = _require_field(item_id, fields, "Deliverables")

    outcome = field_text("Intent")
    non_goals = _split_nonempty(scope_excluded, _SCOPE_CLAUSE_SPLIT_RE)

    must = []
    for clause in _split_nonempty(scope_included, _SCOPE_CLAUSE_SPLIT_RE):
        must.append({"id": f"M{len(must) + 1}", "requirement": clause,
                    "source_ref": f"phases/{phase_token}.md:{scope_included_ln}"})
    for clause in _marker_clauses(impl_rules_text, _IMPL_RULE_SPLIT_RE):
        must.append({"id": f"M{len(must) + 1}", "requirement": clause,
                    "source_ref": f"phases/{phase_token}.md:{impl_rules_ln}"})
    if not must:
        raise TaskContractBuildError(item_id, "Scope Included", "no requirement clause found")

    never = []
    for clause in non_goals:
        never.append({"id": f"N{len(never) + 1}", "prohibition": clause,
                     "source_ref": f"phases/{phase_token}.md:{scope_excluded_ln}"})
    for clause in _anti_clauses(code_guidance_text):
        never.append({"id": f"N{len(never) + 1}", "prohibition": clause,
                     "source_ref": f"phases/{phase_token}.md:{code_guidance_ln}"})
    if not never:
        raise TaskContractBuildError(item_id, "Scope Excluded", "no prohibition clause found")

    evidence = []
    execution_inputs = []

    def add_execution_inputs(clause: str) -> None:
        # Preserve every explicit execution path until policy has classified it.
        # The legacy ``kind`` remains readable by v1 consumers; the additive
        # path_kind/original/normalized/rejection fields carry BundleInputPolicy/v1.
        paths = [token for token, declared in plan_weight.path_candidates(clause) if declared]
        for path in paths:
            classified = classify_execution_input(path)
            execution_inputs.append({
                "path": classified["normalized"] or classified["original"],
                "kind": "committed",
                "producer": None,
                **classified,
            })

    for clause in _split_nonempty(inputs_text, _INPUTS_SPLIT_RE):
        path = _first_backtick_or_text(clause)
        evidence.append({"id": f"E{len(evidence) + 1}", "path": path,
                         "proof_class": "unknown", "algorithm": "doc-citation"})
        if _BACKTICK_RE.search(clause):
            add_execution_inputs(clause)
    required_reads_ids = []
    for clause in _marker_clauses(required_reads_text, _REQUIRED_READS_SPLIT_RE):
        path = _first_backtick_or_text(clause)
        eid = f"E{len(evidence) + 1}"
        evidence.append({"id": eid, "path": path, "proof_class": "unknown",
                         "algorithm": "doc-citation"})
        required_reads_ids.append(eid)
        if _BACKTICK_RE.search(clause):
            add_execution_inputs(clause)
    if not evidence:
        raise TaskContractBuildError(item_id, "Required Reads", "no evidence entry found")

    public_acceptance = []
    for clause in _split_nonempty(validation_text, _VALIDATION_SPLIT_RE):
        eid = f"E{len(evidence) + 1}"
        evidence.append({"id": eid, "path": clause, "proof_class": "declared",
                         "algorithm": "shell-command"})
        path_tokens = plan_lint.PORTABILITY_PATH_RE.findall(clause)
        scope = "internal" if any(is_external_path(tok) for tok in path_tokens) else "public"
        public_acceptance.append({"id": f"A{len(public_acceptance) + 1}", "predicate": deliverables,
                                  "scope": scope, "check": clause, "evidence_ref": eid})
    if not public_acceptance:
        raise TaskContractBuildError(item_id, "Validation", "no check clause found")

    plan_lines = plan_lint._read_lines(plan_dir / "plan.md") or []
    routing_metadata = command_catalog.load_routing_metadata(
        routing_config_path or _DEFAULT_ROUTING_CONFIG_PATH)
    # The canonical executable header may follow a non-executable mapping
    # table.  Ask the compiler first; legacy spellings retain their isolated
    # resolver only when the canonical table is absent altogether.
    try:
        compiled = compile_batch_routing(plan_dir, routing_config_path=routing_config_path)
    except TaskContractBuildError as exc:
        if "no executable table with exact header" not in str(exc):
            raise
        routing = _find_routing_row(plan_lint, plan_lines, item_id, routing_metadata)
    else:
        try:
            routing_entry = compiled["items"][item_id]
            routing = routing_entry["route"]
        except KeyError as exc:
            raise TaskContractBuildError(item_id, "Routing", "no §3 Routing row found for this item") from exc
        if admission_route is not None:
            batch_route = compiled["batches"][routing_entry["batch_key"]]["route"]
            if admission_route != batch_route:
                raise TaskContractBuildError(
                    item_id, "Routing",
                    "BATCH_ROUTE_MISMATCH: admission route must equal the compiled batch maximum")
            routing = batch_route
        # A stronger/costlier actual route than declared is recorded as `over`, never a stop.
        routing = (routing["model_class"], routing["effort"])
    required_route = {"model_class": routing[0], "effort": routing[1]}
    if actual_route is None:
        actual_route = route_evidence.capture_actual(
            None, None, source="self-attested", ts="1970-01-01T00:00:00Z")
    route = route_evidence.build_task_contract_route(required_route, actual_route, capabilities)

    tier = "committed-bundle" if plan_lint._plan_declares_committed_bundle_tier(plan_dir) \
        else "brief-acceptance"
    policy_privacy = BUNDLE_INPUT_POLICY.privacy()
    if bundle_privacy is not None and bundle_privacy != policy_privacy:
        raise TaskContractBuildError(
            item_id, "portability.privacy",
            "BUNDLE_POLICY_DENIED: caller declaration cannot weaken BundleInputPolicy/v1",
        )
    bundle_privacy = policy_privacy

    plan_id = plan_dir.name
    if carrier is None:
        carrier = f"task:plan-run {plan_id} {item_id}"
    claude_render = f"/task:plan-run {plan_id} {item_id}"
    codex_render = f"$ task:plan-run {plan_id} {item_id}"

    phase_lines = plan_lint._read_lines(phase_path) or []
    observed_rounds = _count_audit_rounds(plan_dir, phase_lines, phase_token)
    audit_cap_remediation = _has_audit_cap_remediation_grant(plan_dir, item_id)
    authority_class, authority_granted, authority_granted_by = _resolve_authority(
        plan_lint, plan_lines, plan_dir, item_id, phase_path, impl_rules_text,
        protected_transition, declared)

    contract = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": f"{plan_id.lower()}-{item_id.lower().replace('.', '-')}",
        "version": {"revision": 1, "content_hash": "0" * 64, "supersedes": None},
        "goal": {"outcome": outcome, "non_goals": non_goals},
        "must": must,
        "never": never,
        "done": {"public_acceptance": public_acceptance},
        "authority": {
            "class": authority_class,
            "granted": authority_granted,
            "granted_by": authority_granted_by,
            "auto_allowed": ["write the item's declared Files", "run the item's Validation",
                            "close the item with the two-commit topology"],
            "stop_boundaries": ["tag/push/release", "fleet rollout", "consumer repositories",
                               "FOREMAN outward parts"],
            "loop_budget": {"audit_rounds_max": review_policy.AUDIT_ROUNDS_MAX,
                           "same_finding_max": review_policy.SAME_FINDING_MAX},
            "observed_rounds": observed_rounds,
            "audit_cap_remediation": audit_cap_remediation,
        },
        "next": {"form": next_form, "carrier": carrier, "context": next_context,
                "origin": next_origin, "changed_by": next_changed_by},
        "route": route,
        "evidence": evidence,
        "portability": {
            "tier": tier,
            "execution_inputs": execution_inputs,
            "provenance_only": [],
            "privacy": bundle_privacy,
            "semantic_carrier": "task:plan-run",
            "provider_renderers": {"claude": claude_render, "codex": codex_render},
        },
        "conflicts": [],
        "slice": {"subagent_keys": list(SLICE_SUBAGENT_KEYS),
                 "root_only_keys": list(SLICE_ROOT_ONLY_KEYS)},
        "cold_start": {"plan_id": plan_id, "item_id": item_id, "reads": required_reads_ids,
                      "carrier": carrier},
    }
    contract["version"]["content_hash"] = content_hash(contract)
    return contract


# --------------------------------------------------------------------------
# bundle_lint() — evidence-bundle privacy/minimization predicate.
# --------------------------------------------------------------------------

_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
    re.compile(rb"(?i)(?:api|secret)[_-]?key[\"']?\s*[:=]\s*[\"'][A-Za-z0-9/+=_-]{16,}"),
)
_CHAIN_OF_THOUGHT_PATTERNS = (
    re.compile(rb"<thinking>"),
    re.compile(rb"<scratchpad>"),
    re.compile(rb"(?i)chain[- ]of[- ]thought"),
)
_TOOL_PAYLOAD_PATTERNS = (
    re.compile(rb'"tool_use"'),
    re.compile(rb'"tool_result"'),
    re.compile(rb"<tool_call>"),
)
_RAW_TRANSCRIPT_PATTERNS = (
    re.compile(rb'"role"\s*:\s*"(?:user|assistant)"'),
    re.compile(rb"(?m)^(?:Human|Assistant|User|System):\s"),
)
_CONTENT_CLASS_PATTERNS = (
    ("secrets", _SECRET_PATTERNS),
    ("chain-of-thought", _CHAIN_OF_THOUGHT_PATTERNS),
    ("tool-payloads", _TOOL_PAYLOAD_PATTERNS),
    ("raw-transcript-bodies", _RAW_TRANSCRIPT_PATTERNS),
)
# A single stray "Human:"-shaped line is not a transcript — require repetition
# before calling it a raw conversational body (avoids a false positive on a
# doc that merely quotes one line of dialogue).
_RAW_TRANSCRIPT_MIN_HITS = 3


def _scan_content_classes(data: bytes) -> set:
    found = set()
    for class_name, patterns in _CONTENT_CLASS_PATTERNS:
        for pattern in patterns:
            hits = len(pattern.findall(data))
            if hits == 0:
                continue
            if class_name == "raw-transcript-bodies" and hits < _RAW_TRANSCRIPT_MIN_HITS:
                continue
            found.add(class_name)
            break
    return found


def _bundle_regular_members(bundle_dir: Path) -> tuple[dict[str, Path] | None, str | None]:
    """Walk a bundle without following links or reading special files."""
    members: dict[str, Path] = {}

    def visit(directory: Path, prefix: PurePosixPath) -> str | None:
        try:
            entries = tuple(os.scandir(directory))
        except OSError:
            return BUNDLE_MEMBER_UNSAFE
        for entry in entries:
            logical = (prefix / entry.name).as_posix()
            try:
                if entry.is_symlink():
                    return BUNDLE_MEMBER_UNSAFE
                if entry.is_dir(follow_symlinks=False):
                    code = visit(Path(entry.path), prefix / entry.name)
                    if code:
                        return code
                elif entry.is_file(follow_symlinks=False):
                    members[logical] = Path(entry.path)
                else:
                    return BUNDLE_MEMBER_UNSAFE
            except OSError:
                return BUNDLE_MEMBER_UNSAFE
        return None

    if bundle_dir.is_symlink() or not bundle_dir.is_dir():
        return None, BUNDLE_ARTIFACT_MISSING
    code = visit(bundle_dir, PurePosixPath())
    return (None, code) if code else (members, None)


def bundle_lint(bundle_dir, *, manifest_path, verifier_path,
                declared_privacy=None, policy: BundleInputPolicy = BUNDLE_INPUT_POLICY) -> str | None:
    """Enforce BundleInputPolicy/v1 over bytes and no-follow filesystem facts.

    ``declared_privacy`` is a compatibility assertion only: it must exactly match
    the frozen policy and can never remove a forbidden class. Minimization is the
    normalized manifest set against regular no-follow members; content classes
    are detected from the actual bytes.

    New reason codes (not pre-declared by 's frozen
    `state-transition-cases.json::new_reason_codes`; this item introduces
    them directly, same discipline as that file's own entries):

      * `BUNDLE_ARTIFACT_MISSING` — distinct_from `PORTABILITY_INPUT_MISSING`
        (that fires on an absent EXECUTION INPUT path already inside a
        compiled contract; this fires on the bundle's own internal manifest
        or verifier file being absent on disk — a different object, checked
        before any Task Contract exists).
      * `BUNDLE_PRIVACY_MISMATCH` — distinct_from `PORTABILITY_TIER_MISCLASSIFIED`
        (that fires on the TIER assignment against the classification rule;
        this fires on the computed content-class scan disagreeing with the
        item's declared `privacy` block — never about tier).

    `manifest_path` — a JSON file `{"files": [<bundle-relative path>, ...]}`
    declaring the bundle's exact expected member set (this item's own minimal
    manifest contract — no existing generic manifest schema is reusable
    across the fleet's several bundle-specific formats, e.g. 's
    `manifests/bundle-manifest.json` vs 's `result-manifest.json`).
    `verifier_path` — existence-checked only (never executed: running an
    arbitrary committed script from inside a library predicate is its own
    hazard and outside this item's Scope).

    Existing extension points surveyed first: `is_external_path` (a
    path-STRING test, reused nowhere here — bundle_lint scans byte CONTENT,
    a different object) and `plan-portability-v1.md`'s bundle-requirements
    prose (stated but never executable before this function). Alternatives
    considered: (a) trust the declared `privacy` block as-is — rejected,
    exactly F4's defect; (b) hash-only manifest check without content-class
    scanning — rejected, leaves secrets/raw-bulk undetected even when file
    counts match. Named consumers: (write-site), (P2.5 bundle
    rerun). SemVer: new public function, additive to `task_contract`'s
    surface.
    """
    bundle_dir = Path(bundle_dir)
    manifest_path = Path(manifest_path)
    verifier_path = Path(verifier_path)
    expected_privacy = policy.privacy()
    if declared_privacy is not None and declared_privacy != expected_privacy:
        return BUNDLE_POLICY_DENIED

    required_relatives = []
    for required in (manifest_path, verifier_path):
        try:
            relative = required.relative_to(bundle_dir).as_posix()
            contained_regular_path(bundle_dir, relative)
        except (ValueError, OSError):
            return BUNDLE_ARTIFACT_MISSING
        required_relatives.append(relative)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared_files = manifest["files"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return BUNDLE_PATH_INVALID
    if not isinstance(declared_files, list):
        return BUNDLE_PATH_INVALID
    if "privacy" in manifest and manifest["privacy"] != expected_privacy:
        return BUNDLE_POLICY_DENIED

    declared_names = []
    for entry in declared_files:
        value = entry.get("path") if isinstance(entry, dict) else entry
        classified = classify_execution_input(value)
        if classified["path_kind"] == "external":
            return BUNDLE_PATH_EXTERNAL
        if classified["path_kind"] != "internal":
            return BUNDLE_PATH_INVALID
        declared_names.append(classified["normalized"])
    if len(declared_names) != len(set(declared_names)):
        return BUNDLE_MEMBER_DUPLICATE

    members, code = _bundle_regular_members(bundle_dir)
    if code:
        return code
    assert members is not None
    actual_set = set(members) - set(required_relatives)
    declared_set = set(declared_names)
    if actual_set != declared_set:
        return BUNDLE_PRIVACY_MISMATCH
    for relative in declared_names:
        try:
            contained_regular_path(bundle_dir, relative)
        except ValueError:
            return BUNDLE_MEMBER_UNSAFE

    found_classes = set()
    for rel in actual_set:
        try:
            found_classes |= _scan_content_classes(members[rel].read_bytes())
        except OSError:
            return BUNDLE_MEMBER_UNSAFE
    if found_classes & policy.forbidden_classes:
        return BUNDLE_POLICY_DENIED
    return None


def canonical_payload(contract: dict) -> dict:
    """The hashed payload: the contract minus its own declared hash
    (task-contract-v1.md §Version, content_hash is recomputed, never trusted as written)."""
    payload = copy.deepcopy(contract)
    payload.get("version", {}).pop("content_hash", None)
    return payload


def content_hash(contract: dict) -> str:
    blob = json.dumps(canonical_payload(contract), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rank(order: tuple, value: str) -> int:
    return order.index(value)


def _rank_or_none(order: tuple, value) -> int | None:
    """D78/ route-ladder guard: `None` (never an `IndexError`/`ValueError`) when
    `value` is outside `order`. Used ONLY by `pre_mutation`'s route check below — the
    `CARRIER_PRECEDENCE` conflict-resolution use of `_rank` above is unrelated scope
    (D78/`findings/14` measured the route axes specifically) and stays untouched. An
    out-of-ladder value never crashes the predicate.  The caller distinguishes a
    malformed required route from missing actual provider evidence below."""
    return order.index(value) if value in order else None


def classify_tier(work: dict) -> str:
    """plan-portability-v1.md §Classification rule — `tier(work)`.

    `work` carries the four symptoms: `sessions` (`"single"`/`"multi"`), `risk`
    (`"low"`/`"high"`), `handoff` (bool), `audit` (bool)."""
    if (work.get("sessions") == "multi" or work.get("risk") == "high"
            or work.get("handoff") or work.get("audit")):
        return "committed-bundle"
    return "brief-acceptance"


def is_external_path(path: str) -> bool:
    """task-contract-v1.md §Portability — string test over a path ALREADY known to be an
    execution input (role decided elsewhere). Not the D47 role test."""
    classified = classify_execution_input(path)
    return (classified["path_kind"] == "external"
            or path.startswith(_EXTERNAL_PREFIXES)
            or any(s in path for s in _EXTERNAL_SUBSTRINGS))


def portability_lint(portability: dict, *, work: dict | None = None) -> str | None:
    """plan-portability-v1.md §Classification rule + §Lint predicate — ordered check over
    an already-compiled `portability` block. Returns `None` (allow) or a typed reason code:
    `PORTABILITY_TIER_MISCLASSIFIED` (new —.json`
    `new_reason_codes`) · `PORTABILITY_INPUT_MISSING` / `PORTABILITY_EXTERNAL_INPUT`
.

    Order, exactly as declared in plan-portability-v1.md §Classification rule:
    (1) tier contradicts the rule for the declared `work` · (2) `committed-bundle` with no
    `execution_inputs` · (3) a path listed as both execution input and provenance ·
    (4) a host-bound input · (5) a `produced-by-predecessor` input without a producer."""
    tier = portability["tier"]
    if work is not None and classify_tier(work) != tier:
        return "PORTABILITY_TIER_MISCLASSIFIED"

    execution_inputs = portability["execution_inputs"]
    if tier == "committed-bundle" and not execution_inputs:
        return "PORTABILITY_INPUT_MISSING"

    provenance_only = set(portability["provenance_only"])
    for entry in execution_inputs:
        path = entry["path"]
        if path in provenance_only:
            return "PORTABILITY_TIER_MISCLASSIFIED"
        path_kind = entry.get("path_kind")
        if path_kind == "invalid":
            return PORTABILITY_INPUT_INVALID
        if path_kind == "external":
            return "PORTABILITY_EXTERNAL_INPUT"
        if is_external_path(path):
            return "PORTABILITY_EXTERNAL_INPUT"
        if entry["kind"] == "produced-by-predecessor" and not entry["producer"]:
            return "PORTABILITY_INPUT_MISSING"

    return None


def pre_mutation(contract: dict, *, work: dict | None = None,
                 evidence_graph: dict | None = None,
                 requires_closure_freshness: bool = False) -> str | None:
    """task-contract-v1.md §Pre-mutation predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code.

    `work` — optional signs for the portability tier-classification sub-check (rank
    5-6 of the frozen table); omitted when the contract's own declared tier is trusted
    as-is (e.g. re-checking an already-classified contract)."""
    if contract["version"]["content_hash"] != content_hash(contract):
        return "VERSION_HASH_MISMATCH"

    for conflict in contract["conflicts"]:
        if conflict["resolution"] == "unknown":
            return "CONFLICT_UNRESOLVED"
    for conflict in contract["conflicts"]:
        winner = _rank(CARRIER_PRECEDENCE, conflict["winner"]["carrier_class"])
        loser = _rank(CARRIER_PRECEDENCE, conflict["loser"]["carrier_class"])
        if winner >= loser:
            return "CONFLICT_PRECEDENCE_VIOLATION"

    nxt = contract["next"]
    if nxt["origin"] == "diagnostic":
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "typed-finding" and nxt["changed_by"] is None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "approved-goal" and nxt["changed_by"] is not None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"

    portability_code = portability_lint(contract["portability"], work=work)
    if portability_code:
        return portability_code

    route = contract["route"]
    required_class_rank = _rank_or_none(MODEL_CLASS_ORDER, route["required"]["model_class"])
    actual_class_rank = _rank_or_none(MODEL_CLASS_ORDER, route["actual"]["model_class"])
    if required_class_rank is None:
        return "ROUTE_UNDERSHOOT"
    if actual_class_rank is None:
        return "ROUTE-UNVERIFIABLE"
    if actual_class_rank < required_class_rank:
        return "ROUTE_UNDERSHOOT"
    required_effort_rank = _rank_or_none(EFFORT_ORDER, route["required"]["effort"])
    actual_effort_rank = _rank_or_none(EFFORT_ORDER, route["actual"]["effort"])
    if required_effort_rank is None:
        return "ROUTE_UNDERSHOOT"
    if actual_effort_rank is None:
        return "ROUTE-UNVERIFIABLE"
    if actual_effort_rank < required_effort_rank:
        return "ROUTE_UNDERSHOOT"
    for capability in route["capabilities"]:
        if capability["support"] not in ("native", "adapted"):
            return "CAPABILITY_UNSUPPORTED"

    authority = contract["authority"]
    # Audit budget limits repeated review, not already authorized repair.
    # Keep historical audit_cap_remediation readable without requiring it.
    if authority["class"] == "owner-gate" and not authority["granted"]:
        return "AUTHORITY_BOUNDARY"

    subagent = set(contract["slice"]["subagent_keys"])
    root_only = set(contract["slice"]["root_only_keys"])
    if subagent & root_only:
        return "SLICE_INCOMPLETE"
    if subagent | root_only != SLICE_PARTITION_KEYS:
        return "SLICE_INCOMPLETE"
    if not SLICE_SUBAGENT_REQUIRED <= subagent:
        return "SLICE_INCOMPLETE"
    if not SLICE_ROOT_ONLY_REQUIRED <= root_only:
        return "SLICE_INCOMPLETE"

    evidence_ids = {item["id"] for item in contract["evidence"]}
    cold_start = contract["cold_start"]
    if not set(cold_start["reads"]) <= evidence_ids:
        return "COLD_START_INCOMPLETE"
    if cold_start["carrier"] != nxt["carrier"]:
        return "COLD_START_INCOMPLETE"

    if evidence_graph is not None:
        from task import plan_evidence
        try:
            plan_evidence.admit_pre_mutation(
                evidence_graph,
                requires_closure_freshness=requires_closure_freshness,
            )
        except plan_evidence.EvidenceError as exc:
            return exc.code

    return None


_VALIDATION_CONTEXT_FIELDS = {
    "schema_version", "spec_sha256", "head", "tree", "environment_sha256",
}
_VALIDATION_RECEIPT_FIELDS = {
    "schema_version", "evidence_id", "command", "contract_sha256", "spec_sha256",
    "head", "tree", "environment_sha256", "exit_code", "executed_at",
}
_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40,64}$")


def current_validation_context(plan_dir, item_id: str) -> dict:
    """Bind runtime validation to the current spec, Git state and Python environment."""
    from task import plan_evidence, plan_layout, plan_weight

    root = Path(plan_dir).resolve()
    repo_root = plan_weight.repo_root_for(root)

    def git(*args):
        result = subprocess.run(
            ("git", *args), cwd=repo_root, text=True, capture_output=True, check=False,
        )
        if result.returncode:
            raise TaskContractBuildError(
                item_id, "Validation", f"git {' '.join(args)}: {result.stderr.strip()}")
        return result.stdout.strip()

    # Stable identity only: interpreter family, major.minor and OS family. The exact patch
    # version, kernel string and interpreter path change between sessions/providers without
    # changing what a check proves, and used to stale every receipt.
    environment = {
        "implementation": platform.python_implementation(),
        "python": ".".join(platform.python_version_tuple()[:2]),
        "system": platform.system(),
    }
    environment_sha = hashlib.sha256(json.dumps(
        environment, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    spec = plan_layout.carrier_path(root, "item-spec", item_id=item_id)
    product_members = []
    for relative in plan_evidence.material_product_paths(root, item_id):
        path = repo_root / relative
        if path.is_symlink():
            member = {"path": relative, "state": "symlink", "target": str(path.readlink())}
        elif path.is_file():
            member = {"path": relative, "state": "file",
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        else:
            member = {"path": relative, "state": "missing"}
        product_members.append(member)
    product_tree_sha = hashlib.sha256(json.dumps(
        product_members, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "schema_version": "validation-context/v1",
        "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        "head": git("rev-parse", "HEAD"),
        "tree": product_tree_sha,
        "environment_sha256": environment_sha,
    }


def _validate_validation_context(context: dict) -> None:
    if (not isinstance(context, dict) or set(context) != _VALIDATION_CONTEXT_FIELDS
            or context.get("schema_version") != "validation-context/v1"
            or not _SHA256_RE.fullmatch(str(context.get("spec_sha256", "")))
            or not _GIT_OBJECT_RE.fullmatch(str(context.get("head", "")))
            or not _GIT_OBJECT_RE.fullmatch(str(context.get("tree", "")))
            or not _SHA256_RE.fullmatch(str(context.get("environment_sha256", "")))):
        raise ValueError("VALIDATION_RECEIPT_STALE: invalid validation context")


def build_validation_receipt(contract: dict, evidence_id: str, *, exit_code: int,
                             context: dict, executed_at: str | None = None) -> dict:
    """Create a versioned execution receipt for one declared validation carrier."""
    _validate_validation_context(context)
    matches = [entry for entry in contract.get("evidence", [])
               if entry.get("id") == evidence_id]
    if len(matches) != 1 or matches[0].get("algorithm") != "shell-command":
        raise ValueError("VALIDATION_RECEIPT_STALE: evidence is not one shell command")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise ValueError("VALIDATION_RECEIPT_STALE: exit_code must be int")
    return {
        "schema_version": "validation-receipt/v1",
        "evidence_id": evidence_id,
        "command": matches[0]["path"],
        "contract_sha256": content_hash(contract),
        "spec_sha256": context["spec_sha256"],
        "head": context["head"],
        "tree": context["tree"],
        "environment_sha256": context["environment_sha256"],
        "exit_code": exit_code,
        "executed_at": executed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _validation_receipt_code(contract: dict, evidence: dict, receipts, context) -> str | None:
    if context is None:
        return "VALIDATION_RECEIPT_MISSING"
    try:
        _validate_validation_context(context)
    except ValueError:
        return "VALIDATION_RECEIPT_STALE"
    matches = [receipt for receipt in receipts
               if isinstance(receipt, dict) and receipt.get("evidence_id") == evidence["id"]]
    if not matches:
        return "VALIDATION_RECEIPT_MISSING"
    if len(matches) != 1:
        return "VALIDATION_RECEIPT_STALE"
    receipt = matches[0]
    if (set(receipt) != _VALIDATION_RECEIPT_FIELDS
            or receipt.get("schema_version") != "validation-receipt/v1"
            or receipt.get("command") != evidence.get("path")
            or receipt.get("contract_sha256") != content_hash(contract)
            # `head` is provenance only: an ordinary commit or bookkeeping move does not change
            # the product bytes (`tree`), so it never invalidates a receipt by itself.
            or any(receipt.get(key) != context.get(key)
                   for key in ("spec_sha256", "tree", "environment_sha256"))
            or not isinstance(receipt.get("executed_at"), str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                receipt.get("executed_at", ""))):
        return "VALIDATION_RECEIPT_STALE"
    exit_code = receipt.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return "VALIDATION_RECEIPT_STALE"
    if exit_code != 0:
        return "VALIDATION_RECEIPT_NONZERO"
    return None


def pre_final(contract: dict, *, validation_receipts=(),
              validation_context: dict | None = None) -> str | None:
    """task-contract-v1.md §Pre-final predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code. Caller is responsible for the `n/a`
    branch (task-contract-v1.md: evaluated only when pre-mutation allowed)."""
    acceptance = contract["done"]["public_acceptance"]
    if not any(entry["scope"] == "public" for entry in acceptance):
        return "ACCEPTANCE_NOT_PUBLIC"

    by_id = {item["id"]: item for item in contract["evidence"]}
    for entry in acceptance:
        if entry["evidence_ref"] not in by_id:
            return "EVIDENCE_REF_UNKNOWN"

    for entry in acceptance:
        if entry["scope"] != "public":
            continue
        evidence = by_id[entry["evidence_ref"]]
        if evidence.get("algorithm") == "shell-command" or evidence.get("proof_class") == "declared":
            receipt_code = _validation_receipt_code(
                contract, evidence, tuple(validation_receipts or ()), validation_context)
            if receipt_code:
                return receipt_code
            continue
        proof_class = evidence["proof_class"]
        if proof_class not in DETERMINISTIC_PROOF_CLASSES:
            return "EVIDENCE_PROOF_CLASS_INSUFFICIENT"

    return None


def evaluate(contract: dict, *, work: dict | None = None,
             evidence_graph: dict | None = None,
             requires_closure_freshness: bool = False,
             validation_receipts=(), validation_context: dict | None = None) -> dict:
    """Run both boundaries in the canonical order and return a compact typed result —
    the shape a plan command reports verbatim (journal/handoff/subagent slice,
    Code Guidance): `{"pre_mutation": "allow"|"block:<CODE>", "pre_final":
    "allow"|"block:<CODE>"|"n/a", "reason_codes": {<boundary>: <public reason|null>},
    "content_hash": <sha256>}`."""
    mutation_code = pre_mutation(
        contract, work=work, evidence_graph=evidence_graph,
        requires_closure_freshness=requires_closure_freshness,
    )
    final_code = None
    if mutation_code is None:
        final_code = pre_final(
            contract, validation_receipts=validation_receipts,
            validation_context=validation_context,
        )
        final = "allow" if final_code is None else f"block:{final_code}"
    else:
        final = "n/a"
    return {
        "pre_mutation": "allow" if mutation_code is None else f"block:{mutation_code}",
        "pre_final": final,
        "reason_codes": {
            "pre_mutation": public_reason(mutation_code),
            "pre_final": public_reason(final_code),
        },
        "content_hash": content_hash(contract),
    }


# --------------------------------------------------------------------------
# CLI — `python3 -m task.task_contract check --contract <path> [--work <path>]`
#     · `python3 -m task.task_contract build --plan-dir <dir> --item <Pn.m>`
# --------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Task Contract v1 compiler — evaluate pre-mutation/pre-final.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="evaluate a compiled contract JSON file")
    check.add_argument("--contract", required=True, help="path to a Task Contract v1 JSON payload")
    check.add_argument("--work", default=None,
                       help="optional JSON {sessions,risk,handoff,audit} for the portability "
                            "tier-classification sub-check")
    check.add_argument("--validation-receipts", default=None,
                       help="JSON array of validation-receipt/v1 records")
    check.add_argument("--validation-context", default=None,
                       help="JSON validation-context/v1 record for current state")
    build_cmd = sub.add_parser("build", help="compile one item's Task Contract v1 JSON")
    build_cmd.add_argument("--plan-dir", required=True, help="plans/<PLAN-ID>")
    build_cmd.add_argument("--item", required=True, help="Pn.m")
    args = parser.parse_args(argv)

    if args.cmd == "build":
        contract = build(args.plan_dir, args.item)
        print(json.dumps(contract, ensure_ascii=False, sort_keys=True))
        return 0

    if args.cmd != "check":  # pragma: no cover - argparse already gates choices
        return 1
    contract = _load_json(args.contract)
    work = _load_json(args.work) if args.work else None
    receipts = _load_json(args.validation_receipts) if args.validation_receipts else ()
    context = _load_json(args.validation_context) if args.validation_context else None
    result = evaluate(
        contract, work=work, validation_receipts=receipts,
        validation_context=context,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if (result["pre_mutation"] == "allow"
                 and result["pre_final"] == "allow") else 1



# --------------------------------------------------------------------------
# Review/loop-budget policy hook — the one extension point
# `root/contracts/risk-review-loop-budget-v1.md`'s Contribution gate names:
# this compiler owns the pre-mutation/pre-final boundaries above and nothing
# about what happens to an item BETWEEN them when a typed finding is raised
# against it. `task.review_policy` owns that lifecycle; this function is the
# only place this module knows the module exists — a lazy import, so
# `pre_mutation`/`pre_final`/`evaluate` above stay untouched and this
# compiler's own test suite never needs `review_policy` importable.
# --------------------------------------------------------------------------

def evaluate_finding(state: str, finding: dict, *, budget=None, profile: str) -> dict:
    """Delegates one `typed-finding` event to `task.review_policy.review_transition`
. `budget` defaults to a fresh `LoopBudget` when the caller tracks no
    cross-finding state of its own; passing the same `LoopBudget` across calls is
    what lets `same_finding_max` count occurrences across an item's fix rounds."""
    from task.review_policy import LoopBudget, review_transition
    return review_transition(state, finding, budget=budget or LoopBudget(), profile=profile)


if __name__ == "__main__":
    import sys
    sys.exit(main())
