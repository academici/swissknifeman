"""Frozen, deterministic authority evaluator for the plan-local Artifex prototype.

The evaluator never executes an action.  It turns the immutable authority-policy
inputs into one closed decision record that later scheduler code may consume.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
import re
from pathlib import Path


CONTRACT_VERSION = "1.0.0"
OPERATIONS = (
    "compile_slice", "supersede_pending", "dispatch_worker", "validate_result",
    "integrate_owned_delta", "project_plan_bookkeeping",
)
ACTION_CLASSES = ("AUTO", "AUTO-FIX", "OWNER")
ATTENTION_CLASSES = ("none", "batched", "immediate")
OPERATION_REQUIREMENTS = {
    "compile_slice": ("task_contract_allow", "dependency_ready", "input_hashes_current"),
    "supersede_pending": ("prior_pending", "supersedes_hash_exact"),
    "dispatch_worker": ("intent_durable", "route_frozen"),
    "validate_result": ("observation_durable", "validation_argv_frozen"),
    "integrate_owned_delta": ("owned_delta", "backup_verified", "serialized_writer"),
    "project_plan_bookkeeping": ("acceptance_durable", "projection_exact"),
}
REASON_SOURCES = {
    "AUTO_LEGAL": ("authority-policy", "root-instructions"),
    "ROUTINE_CHOICE_SELECTED": ("authority-policy",),
    "AUTO_FIX_BOUNDED": ("authority-policy", "risk-review-loop-budget"),
    "OWNER_REQUIRED_BY_MANDATE": ("owner-brief",),
    "PROTECTED_SECURITY": ("root-instructions", "authority-policy"),
    "PROTECTED_DESTRUCTIVE": ("root-instructions", "authority-policy"),
    "PROTECTED_IRREVERSIBLE": ("owner-intent", "authority-policy"),
    "PROTECTED_EXTERNAL": ("owner-intent", "authority-policy"),
    "PROTECTED_PUBLIC_CONTRACT": ("owner-intent", "authority-policy"),
    "PROTECTED_DEPENDENCY": ("root-instructions", "authority-policy"),
    "PROTECTED_PACKAGE_TOPOLOGY": ("root-instructions", "authority-policy"),
    "THIRD_STATE": ("owner-intent", "execution-state-machine"),
    "UNKNOWN_CAPABILITY": ("authority-policy",),
    "SAME_LEVEL_CONFLICT": (),
    "HIGHER_PRECEDENCE_OWNER": (),
    "ROUTINE_CHOICE_UNRESOLVED": ("authority-policy",),
    "FINDING_IDENTITY_CHANGED": ("risk-review-loop-budget",),
    "ACCEPTANCE_CHANGED": ("authority-policy",),
    "RETRY_BUDGET_EXHAUSTED": ("risk-review-loop-budget",),
    "MANDATE_WIDENS_FILES": ("root-instructions", "owner-refinements"),
    "MANDATE_WIDENS_TOOLS": ("owner-mandate-input",),
    "MANDATE_WIDENS_PROVIDER": ("owner-mandate-input",),
    "MANDATE_WIDENS_MODEL": ("owner-mandate-input",),
    "MANDATE_WIDENS_EFFORT": ("owner-mandate-input",),
    "MANDATE_WIDENS_BUDGET": ("owner-mandate-input", "risk-review-loop-budget"),
    "MANDATE_WEAKENS_VALIDATION": ("owner-mandate-input",),
    "MANDATE_WIDENS_ACTION_CLASS": ("owner-mandate-input",),
    "SCOPE_NOT_EXACT": ("authority-policy", "slice-manifest-v1"),
    "ACCEPTANCE_NOT_DETERMINISTIC": ("authority-policy", "acceptance-rubric-v1"),
    "SOURCE_DRIFT": ("authority-policy", "slice-manifest-v1"),
    "PREIMAGE_MISMATCH": ("authority-policy", "supervisor-run-v1"),
    "BUDGET_EXHAUSTED": ("authority-policy", "risk-review-loop-budget"),
    "OPERATION_CLASS_FORBIDDEN": ("authority-policy", "slice-manifest-v1"),
    "OPERATION_PRECONDITION_FAILED": ("authority-policy", "slice-manifest-v1"),
    "UNKNOWN_OPERATION": ("authority-policy", "slice-manifest-v1"),
}
IMMEDIATE_REASONS = frozenset({
    "PROTECTED_SECURITY", "PROTECTED_DESTRUCTIVE", "PROTECTED_IRREVERSIBLE",
})
DECISION_KEYS = frozenset({
    "decision_id", "operation", "requested_class", "resolved_class", "allowed",
    "reason_code", "attention", "controlling_sources", "source_set_hash", "mandate_hash",
    "selected_alternative", "rejected_alternatives", "intent_sequence", "side_effect_authorized",
})
_DECLARED_SET_RE = re.compile(r"<!-- declared-set: (?P<name>[a-z_]+) -->\s*```text\n(?P<body>.*?)\n```", re.DOTALL)


class AuthorityRefusal(ValueError):
    """Frozen inputs are malformed, missing, escaping, or not authority-policy v1."""


@dataclass(frozen=True)
class FrozenAuthority:
    contract_path: Path
    contract_hash: str
    cases: dict
    p0_cases: dict
    mandate: dict
    case_bank_hash: str
    mandate_hash: str
    source_set_hash: str


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise AuthorityRefusal(f"AUTHORITY_INPUT_EXTERNAL: {relative}") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise AuthorityRefusal(f"AUTHORITY_INPUT_MISSING: {relative}")
    return candidate


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorityRefusal(f"AUTHORITY_INPUT_INVALID: {label}") from exc
    if not isinstance(value, dict):
        raise AuthorityRefusal(f"AUTHORITY_INPUT_INVALID: {label}")
    return value


def _declared_sets(contract_text: str) -> dict[str, tuple[str, ...]]:
    sets = {
        match["name"]: tuple(line.strip() for line in match["body"].splitlines() if line.strip())
        for match in _DECLARED_SET_RE.finditer(contract_text)
    }
    expected = {
        "operations": OPERATIONS,
        "action_classes": ACTION_CLASSES,
        "attention_classes": ATTENTION_CLASSES,
        "reason_codes": tuple(REASON_SOURCES),
    }
    for name, values in expected.items():
        if sets.get(name) != values:
            raise AuthorityRefusal(f"AUTHORITY_CONTRACT_DRIFT: {name}")
    return sets


def load_frozen_authority(plan_dir: str | Path) -> FrozenAuthority:
    """Load exactly the frozen P0/P1 inputs and fail before a decision on drift."""
    root = Path(plan_dir).resolve()
    contract = _safe_file(root, "root/contracts/authority-policy-v1.md")
    cases_path = _safe_file(root, "artifacts/P1/authority-policy-cases-v1.json")
    p0_cases_path = _safe_file(root, "artifacts/P0/authority-cases-v1.json")
    mandate_path = _safe_file(root, "artifacts/P0/owner-mandate-input-v1.json")
    try:
        contract_text = contract.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AuthorityRefusal("AUTHORITY_INPUT_INVALID: contract") from exc
    if not contract_text.startswith("# Authority Policy Contract v1\n"):
        raise AuthorityRefusal("AUTHORITY_CONTRACT_DRIFT: title")
    _declared_sets(contract_text)
    cases = _read_json(cases_path, "cases")
    p0_cases = _read_json(p0_cases_path, "p0_cases")
    mandate = _read_json(mandate_path, "mandate")
    if cases.get("schema_version") != "authority-policy-cases-v1" or cases.get("contract_version") != CONTRACT_VERSION:
        raise AuthorityRefusal("AUTHORITY_CONTRACT_DRIFT: cases")
    if p0_cases.get("schema_version") != 1 or not isinstance(p0_cases.get("cases"), list):
        raise AuthorityRefusal("AUTHORITY_INPUT_INVALID: p0_cases")
    if mandate.get("schema_version") != 1 or mandate.get("status") != "unsigned-input":
        raise AuthorityRefusal("AUTHORITY_INPUT_INVALID: mandate")
    if cases.get("legacy_mandate_file") != mandate_path.name:
        raise AuthorityRefusal("AUTHORITY_CONTRACT_DRIFT: legacy_mandate_file")
    if not isinstance(mandate.get("source_set"), dict) or not isinstance(mandate.get("envelope"), dict):
        raise AuthorityRefusal("AUTHORITY_INPUT_INVALID: mandate")
    return FrozenAuthority(
        contract_path=contract,
        contract_hash=hashlib.sha256(contract_text.encode("utf-8")).hexdigest(),
        cases=cases,
        p0_cases=p0_cases,
        mandate=mandate,
        case_bank_hash=digest(cases),
        mandate_hash=digest(mandate),
        source_set_hash=digest(mandate["source_set"]),
    )


def mutate(base: dict, mutations: list[dict]) -> dict:
    """Apply an independently authored frozen case mutation without changing its bank."""
    value = copy.deepcopy(base)
    for mutation in mutations:
        path = mutation.get("path")
        if not isinstance(path, list) or not path:
            raise AuthorityRefusal("AUTHORITY_CASE_INVALID: mutation path")
        target = value
        try:
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = copy.deepcopy(mutation["value"])
        except (KeyError, TypeError) as exc:
            raise AuthorityRefusal("AUTHORITY_CASE_INVALID: mutation path") from exc
    return value


def normalize_legacy(base: dict, case: dict) -> dict:
    """The contract's compatibility adapter; P0 expected outcomes remain untouched."""
    requested = case.get("requested_class")
    operation = {"AUTO": "validate_result", "AUTO-FIX": "integrate_owned_delta", "OWNER": "project_plan_bookkeeping"}.get(
        requested, "validate_result")
    value = copy.deepcopy(base)
    value["operation"] = operation
    value["requested_class"] = requested
    for key, item in case.get("input", {}).items():
        value[key] = copy.deepcopy(item)
    return value


def _sources_for(reason: str, authority_sources: object) -> list[str]:
    rows = authority_sources if isinstance(authority_sources, list) else []
    if reason == "SAME_LEVEL_CONFLICT":
        return [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]
    if reason == "HIGHER_PRECEDENCE_OWNER":
        levels = [row.get("level") for row in rows if isinstance(row, dict) and isinstance(row.get("level"), int)]
        if not levels:
            return []
        strongest = min(levels)
        return [row["id"] for row in rows if row.get("level") == strongest and row.get("directive") == "OWNER"]
    return list(REASON_SOURCES[reason])


def _decision(value: dict, frozen: FrozenAuthority, decision_id: str, reason: str,
              selected: str | None = None, rejected: list[str] | None = None) -> dict:
    allowed = reason in {"AUTO_LEGAL", "ROUTINE_CHOICE_SELECTED", "AUTO_FIX_BOUNDED"}
    record = {
        "decision_id": decision_id,
        "operation": value.get("operation"),
        "requested_class": value.get("requested_class"),
        "resolved_class": value.get("requested_class") if allowed else "OWNER",
        "allowed": allowed,
        "reason_code": reason,
        "attention": "none" if allowed else ("immediate" if reason in IMMEDIATE_REASONS else "batched"),
        "controlling_sources": _sources_for(reason, value.get("authority_sources")),
        "source_set_hash": frozen.source_set_hash,
        "mandate_hash": frozen.mandate_hash,
        "selected_alternative": selected,
        "rejected_alternatives": list(rejected or []),
        "intent_sequence": value.get("intent_sequence"),
        "side_effect_authorized": allowed,
    }
    validate_record(record)
    return record


def _precedence(value: dict) -> tuple[str | None, list[dict]]:
    rows = value.get("authority_sources", [])
    if not rows:
        return None, []
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and isinstance(row.get("id"), str)
        and isinstance(row.get("level"), int) and row["level"] >= 1
        and row.get("directive") in {"ALLOW", "OWNER"} for row in rows
    ):
        return "SAME_LEVEL_CONFLICT", []
    strongest_level = min(row["level"] for row in rows)
    controlling = [row for row in rows if row["level"] == strongest_level]
    if len({row["directive"] for row in controlling}) != 1:
        return "SAME_LEVEL_CONFLICT", controlling
    return ("HIGHER_PRECEDENCE_OWNER" if controlling[0]["directive"] == "OWNER" else None), controlling


def _protected_reason(value: dict) -> str | None:
    checks = (
        (value.get("security") is True, "PROTECTED_SECURITY"),
        (value.get("destructive") is True, "PROTECTED_DESTRUCTIVE"),
        (value.get("reversible") is not True, "PROTECTED_IRREVERSIBLE"),
        (value.get("external") is True, "PROTECTED_EXTERNAL"),
        (value.get("public_contract") is True, "PROTECTED_PUBLIC_CONTRACT"),
        (value.get("dependency_change") is True, "PROTECTED_DEPENDENCY"),
        (value.get("package_topology_change") is True, "PROTECTED_PACKAGE_TOPOLOGY"),
        (value.get("state") != "known", "THIRD_STATE"),
        (value.get("capability") != "known" or value.get("capability_known") is not True, "UNKNOWN_CAPABILITY"),
    )
    return next((reason for applies, reason in checks if applies), None)


def _narrowing_reason(value: dict, envelope: dict) -> str | None:
    if not set(value.get("files", [])).issubset(envelope.get("files", [])):
        return "MANDATE_WIDENS_FILES"
    if not set(value.get("tools", [])).issubset(envelope.get("tools", [])):
        return "MANDATE_WIDENS_TOOLS"
    if value.get("provider") not in envelope.get("providers", []):
        return "MANDATE_WIDENS_PROVIDER"
    if value.get("model_class") not in envelope.get("model_classes", []):
        return "MANDATE_WIDENS_MODEL"
    if value.get("effort") not in envelope.get("efforts", []):
        return "MANDATE_WIDENS_EFFORT"
    budget, maxima = value.get("budget"), envelope.get("budget_max", {})
    if (not isinstance(budget, dict) or set(budget) != set(maxima)
            or any(not isinstance(budget.get(key), int) or budget[key] < 0 or budget[key] > maximum
                   for key, maximum in maxima.items())):
        return "MANDATE_WIDENS_BUDGET"
    if not set(envelope.get("required_validations", [])).issubset(value.get("validations", [])):
        return "MANDATE_WEAKENS_VALIDATION"
    return None


def _routine_choice(value: dict) -> tuple[str | None, list[str]] | str | None:
    alternatives = value.get("alternatives", [])
    if not alternatives:
        return None
    if not isinstance(alternatives, list) or not all(
        isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("rank"), list)
        for row in alternatives
    ) or len({row["id"] for row in alternatives}) != len(alternatives):
        return "ROUTINE_CHOICE_UNRESOLVED"
    try:
        best_rank = min(tuple(row["rank"]) for row in alternatives)
    except TypeError:
        return "ROUTINE_CHOICE_UNRESOLVED"
    best = [row for row in alternatives if tuple(row["rank"]) == best_rank]
    if len(best) != 1:
        return "ROUTINE_CHOICE_UNRESOLVED"
    return best[0]["id"], [row["id"] for row in alternatives if row["id"] != best[0]["id"]]


def evaluate(value: dict, frozen: FrozenAuthority, decision_id: str) -> dict:
    """Return a total, closed authority record; all unknowns fail to OWNER."""
    if not isinstance(value, dict):
        value = {}
    operation, requested = value.get("operation"), value.get("requested_class")
    if operation not in OPERATIONS:
        return _decision(value, frozen, decision_id, "UNKNOWN_OPERATION")
    if requested not in ACTION_CLASSES:
        return _decision(value, frozen, decision_id, "MANDATE_WIDENS_ACTION_CLASS")
    precedence, sources = _precedence(value)
    if precedence:
        source_value = copy.deepcopy(value)
        source_value["authority_sources"] = sources
        return _decision(source_value, frozen, decision_id, precedence)
    protected = _protected_reason(value)
    if protected:
        return _decision(value, frozen, decision_id, protected)
    narrowing = _narrowing_reason(value, frozen.mandate["envelope"])
    if narrowing:
        return _decision(value, frozen, decision_id, narrowing)
    for key, reason in (
        ("scope_exact", "SCOPE_NOT_EXACT"),
        ("acceptance_deterministic", "ACCEPTANCE_NOT_DETERMINISTIC"),
        ("source_set_current", "SOURCE_DRIFT"),
        ("preimage_exact", "PREIMAGE_MISMATCH"),
        ("budget_available", "BUDGET_EXHAUSTED"),
    ):
        if value.get(key) is not True:
            return _decision(value, frozen, decision_id, reason)
    context = value.get("operation_context", {})
    if not isinstance(context, dict) or any(context.get(key) is not True for key in OPERATION_REQUIREMENTS[operation]):
        return _decision(value, frozen, decision_id, "OPERATION_PRECONDITION_FAILED")
    routine = _routine_choice(value)
    if routine == "ROUTINE_CHOICE_UNRESOLVED":
        return _decision(value, frozen, decision_id, routine)
    selected, rejected = routine if routine else (None, [])
    if requested == "OWNER":
        return _decision(value, frozen, decision_id, "OWNER_REQUIRED_BY_MANDATE")
    if requested == "AUTO-FIX" and operation != "integrate_owned_delta":
        return _decision(value, frozen, decision_id, "OPERATION_CLASS_FORBIDDEN")
    if requested == "AUTO-FIX":
        if value.get("finding_id") != value.get("prior_finding_id"):
            return _decision(value, frozen, decision_id, "FINDING_IDENTITY_CHANGED")
        if value.get("acceptance_hash") != value.get("prior_acceptance_hash"):
            return _decision(value, frozen, decision_id, "ACCEPTANCE_CHANGED")
        retry_count = value.get("retry_count")
        if not isinstance(retry_count, int) or retry_count < 0 or retry_count >= 2:
            return _decision(value, frozen, decision_id, "RETRY_BUDGET_EXHAUSTED")
        return _decision(value, frozen, decision_id, "ROUTINE_CHOICE_SELECTED" if selected else "AUTO_FIX_BOUNDED", selected, rejected)
    return _decision(value, frozen, decision_id, "ROUTINE_CHOICE_SELECTED" if selected else "AUTO_LEGAL", selected, rejected)


def validate_record(record: dict) -> None:
    if set(record) != DECISION_KEYS:
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: keys")
    if record["resolved_class"] not in ACTION_CLASSES or record["attention"] not in ATTENTION_CLASSES:
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: enum")
    if record["reason_code"] not in REASON_SOURCES or record["allowed"] != record["side_effect_authorized"]:
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: authority")
    if record["resolved_class"] == "OWNER" and record["side_effect_authorized"]:
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: owner side effect")
    if not isinstance(record["intent_sequence"], int) or record["intent_sequence"] < 1:
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: intent sequence")
    if not all(isinstance(record[key], str) and re.fullmatch(r"[0-9a-f]{64}", record[key])
               for key in ("source_set_hash", "mandate_hash")):
        raise AuthorityRefusal("AUTHORITY_DECISION_INVALID: hash")
