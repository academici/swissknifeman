#!/usr/bin/env python3
"""Deterministic conformance validator for economy-evidence-v1 and its additive
successor economy-evidence-v2 (P5.7, D123).

The v1 code path, its literals and its expectations are untouched: `--contract-version
1.0.0` (the default, and the argument list P1.5 froze) runs exactly the former program.
`--contract-version 2.0.0` adds the v2 path, which never re-implements adjudication —
it gates the two v2 carriers (`inclusion_bases`, `zero_bases`) and then calls the v1
`adjudicate` over the v1 view of the v2 input, so no threshold, formula, denominator or
reason code can diverge between the versions by construction. The same path re-runs
every frozen `economy-evidence-cases-v1` case under v2 and asserts each v1 verdict is
unchanged; a v2 that moves a v1 verdict is a regression, not an upgrade.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


TOP_KEYS = {
    "schema_version",
    "contract_version",
    "evidence",
    "provider_scope",
    "floor_results",
    "waves",
    "lanes",
    "owner_decision_events",
    "attention_events",
    "dispatched_non_synthetic_slices",
    "unknown_reasons",
}
EVIDENCE_KEYS = {
    "run_id",
    "repository_hash",
    "plan_hash",
    "scope_hash",
    "acceptance_hash",
    "validation_hash",
    "contract_set_hash",
    "provider_matrix_hash",
    "baseline_catalog_hash",
    "privacy_status",
}
MATCH_KEYS = {
    "repository_hash",
    "base_hash",
    "scope_hash",
    "acceptance_hash",
    "validation_hash",
    "provider_hash",
    "model_hash",
    "effort_hash",
    "capabilities_hash",
    "accepted_slice_definition_hash",
}
ATTEMPT_KEYS = {
    "attempt_id",
    "slice_id",
    "accepted",
    "exit_class_ref",
    "rollback_event_ref",
    "worker",
    "coordinator",
}
METRIC_FIELDS = {
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cost_microunits",
    "duration_ms",
    "turns",
}
TOKEN_FIELDS = {
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
}
COMMON_FLOORS = {
    "REL-ACCEPTED-SCOPE",
    "REL-RECOVERY",
    "REL-IDEMPOTENCY",
    "REL-VALIDATION",
    "REL-BUDGET",
    "SEC-AUTHORITY",
    "SEC-PRIVACY",
    "SEC-WORKTREE",
    "SEC-HOOK-INTEGRITY",
    "EVD-SOURCE-HASHES",
    "EVD-INDEPENDENT-ADJUDICATOR",
    "EVD-UNKNOWN-PRESERVATION",
}
PRIVATE_KEYS = {
    "raw_provider_stream",
    "request_content",
    "private_reasoning",
    "tool_input_output",
    "credential",
    "environment_value",
    "private_material",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

# --- economy-evidence-v2 (P5.7, D123) -----------------------------------------
# Additive: every name below is new. Nothing above this block changed.
V2_ONLY_KEYS = {"inclusion_bases", "zero_bases"}
TOP_KEYS_V2 = TOP_KEYS | V2_ONLY_KEYS
INCLUSION_ENTRY_KEYS = {"provider", "contained_field", "containing_field", "evidence_ref"}
ZERO_ENTRY_KEYS = {"component", "path", "statement"}
# `declared-set: inclusion_basis_instantiations` — closed at exactly one row.
INCLUSION_BASIS_INSTANTIATIONS = (("claude-code", "reasoning_tokens", "output_tokens"),)
# `declared-set: zero_basis_components` — closed at exactly one component.
ZERO_BASIS_COMPONENTS = ("coordinator",)
COMPONENTS = ("worker", "coordinator")


class InvalidEvidence(ValueError):
    """The input is structurally invalid and cannot be adjudicated."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise InvalidEvidence(f"{label}: expected closed keys {sorted(expected)}")
    return value


def require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidEvidence(f"{label}: expected non-negative integer")
    return value


def decode_pointer(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise InvalidEvidence(f"invalid JSON pointer: {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def pointer_parent(document: Any, pointer: str) -> tuple[Any, str]:
    parts = decode_pointer(pointer)
    if not parts:
        raise InvalidEvidence("root mutation is forbidden")
    current = document
    for part in parts[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise InvalidEvidence(f"unresolved pointer: {pointer}") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise InvalidEvidence(f"unresolved pointer: {pointer}")
    return current, parts[-1]


def apply_mutations(base: dict[str, Any], mutations: Any) -> dict[str, Any]:
    if not isinstance(mutations, list):
        raise InvalidEvidence("mutations must be a list")
    document = copy.deepcopy(base)
    for mutation in mutations:
        if not isinstance(mutation, dict) or set(mutation) not in ({"op", "path"}, {"op", "path", "value"}):
            raise InvalidEvidence("mutation has an open or incomplete shape")
        parent, leaf = pointer_parent(document, mutation["path"])
        operation = mutation["op"]
        if isinstance(parent, list):
            try:
                index = int(leaf)
            except ValueError as exc:
                raise InvalidEvidence(f"list pointer is not an index: {mutation['path']}") from exc
            if operation == "remove":
                try:
                    parent.pop(index)
                except IndexError as exc:
                    raise InvalidEvidence(f"unresolved pointer: {mutation['path']}") from exc
            elif operation == "set" and "value" in mutation:
                if index < 0 or index >= len(parent):
                    raise InvalidEvidence(f"unresolved pointer: {mutation['path']}")
                parent[index] = copy.deepcopy(mutation["value"])
            else:
                raise InvalidEvidence(f"unsupported mutation: {operation}")
        elif isinstance(parent, dict):
            if operation == "remove":
                if leaf not in parent:
                    raise InvalidEvidence(f"unresolved pointer: {mutation['path']}")
                del parent[leaf]
            elif operation == "set" and "value" in mutation:
                parent[leaf] = copy.deepcopy(mutation["value"])
            else:
                raise InvalidEvidence(f"unsupported mutation: {operation}")
        else:
            raise InvalidEvidence(f"unresolved pointer: {mutation['path']}")
    return document


def contains_private_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key.lower() in PRIVATE_KEYS or contains_private_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_private_key(child) for child in value)
    return False


def metric_pointer(lane: str, attempt_index: int, component: str, field: str) -> str:
    return f"/lanes/{lane}/attempts/{attempt_index}/{component}/{field}"


def validate_shape(document: dict[str, Any], baseline_hash: str, provider_hash: str) -> None:
    require_exact_keys(document, TOP_KEYS, "input")
    if document["schema_version"] != "economy-evidence-input-v1" or document["contract_version"] != "1.0.0":
        raise InvalidEvidence("unsupported evidence schema/version")

    evidence = require_exact_keys(document["evidence"], EVIDENCE_KEYS, "evidence")
    for key in EVIDENCE_KEYS - {"run_id", "privacy_status"}:
        if not isinstance(evidence[key], str) or not SHA256_RE.fullmatch(evidence[key]):
            raise InvalidEvidence(f"evidence.{key}: expected lowercase SHA-256")
    if not isinstance(evidence["run_id"], str) or not evidence["run_id"]:
        raise InvalidEvidence("evidence.run_id is required")
    if evidence["baseline_catalog_hash"] != baseline_hash or evidence["provider_matrix_hash"] != provider_hash:
        raise InvalidEvidence("pinned P0 source hash mismatch")

    provider_scope = require_exact_keys(document["provider_scope"], {"mode", "provider", "owner_grant_ref"}, "provider_scope")
    if provider_scope["mode"] == "parity":
        if provider_scope["provider"] is not None or provider_scope["owner_grant_ref"] is not None:
            raise InvalidEvidence("parity scope must not carry a provider or grant")
    elif provider_scope["mode"] == "single-provider":
        if provider_scope["provider"] not in {"codex", "claude-code"}:
            raise InvalidEvidence("single-provider scope has an unsupported provider")
    else:
        raise InvalidEvidence("unknown provider scope mode")

    floors = document["floor_results"]
    if not isinstance(floors, dict) or set(floors) != COMMON_FLOORS:
        raise InvalidEvidence("common floor set mismatch")
    if any(value not in {"pass", "fail", "unknown"} for value in floors.values()):
        raise InvalidEvidence("invalid common floor state")

    waves = document["waves"]
    if not isinstance(waves, list):
        raise InvalidEvidence("waves must be a list")
    wave_ids: set[str] = set()
    for index, wave in enumerate(waves):
        require_exact_keys(wave, {"wave_id", "predeclared", "synthetic", "terminal", "accepted"}, f"waves[{index}]")
        if not isinstance(wave["wave_id"], str) or not wave["wave_id"] or wave["wave_id"] in wave_ids:
            raise InvalidEvidence("wave IDs must be unique non-empty strings")
        wave_ids.add(wave["wave_id"])
        if any(not isinstance(wave[key], bool) for key in ("predeclared", "synthetic", "terminal", "accepted")):
            raise InvalidEvidence("wave predicates must be booleans")

    unknown_reasons = document["unknown_reasons"]
    if not isinstance(unknown_reasons, dict) or any(not isinstance(key, str) or not isinstance(value, str) or not value.strip() for key, value in unknown_reasons.items()):
        raise InvalidEvidence("unknown_reasons must map pointers to non-empty source reasons")

    lanes = require_exact_keys(document["lanes"], {"candidate", "baseline", "workflow"}, "lanes")
    observed_nulls: set[str] = set()
    for lane_name, lane in lanes.items():
        require_exact_keys(lane, {"match", "attempts"}, f"lanes.{lane_name}")
        match = require_exact_keys(lane["match"], MATCH_KEYS, f"lanes.{lane_name}.match")
        if any(not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in match.values()):
            raise InvalidEvidence(f"lanes.{lane_name}.match must contain SHA-256 values")
        attempts = lane["attempts"]
        if not isinstance(attempts, list) or not attempts:
            raise InvalidEvidence(f"lanes.{lane_name}.attempts must be non-empty")
        attempt_ids: set[str] = set()
        rollback_refs: set[str] = set()
        for index, attempt in enumerate(attempts):
            require_exact_keys(attempt, ATTEMPT_KEYS, f"lanes.{lane_name}.attempts[{index}]")
            if not isinstance(attempt["attempt_id"], str) or not attempt["attempt_id"] or attempt["attempt_id"] in attempt_ids:
                raise InvalidEvidence(f"duplicate/empty attempt identity in {lane_name}")
            attempt_ids.add(attempt["attempt_id"])
            if not isinstance(attempt["slice_id"], str) or not attempt["slice_id"]:
                raise InvalidEvidence("slice_id must be a non-empty string")
            if not isinstance(attempt["accepted"], bool) or not isinstance(attempt["exit_class_ref"], str) or not attempt["exit_class_ref"]:
                raise InvalidEvidence("attempt acceptance/exit reference is invalid")
            rollback_ref = attempt["rollback_event_ref"]
            if rollback_ref is not None:
                if not isinstance(rollback_ref, str) or not rollback_ref or rollback_ref in rollback_refs:
                    raise InvalidEvidence(f"duplicate/invalid rollback reference in {lane_name}")
                rollback_refs.add(rollback_ref)
            for component in ("worker", "coordinator"):
                metrics = require_exact_keys(attempt[component], METRIC_FIELDS, f"{lane_name}.{index}.{component}")
                for field, value in metrics.items():
                    pointer = metric_pointer(lane_name, index, component, field)
                    if value is None:
                        observed_nulls.add(pointer)
                    else:
                        require_nonnegative_int(value, pointer)
        accepted_ids = {attempt["slice_id"] for attempt in attempts if attempt["accepted"]}
        if not accepted_ids:
            raise InvalidEvidence(f"{lane_name}: zero accepted-slice denominator")

    if observed_nulls != set(unknown_reasons):
        raise InvalidEvidence("null measurements and unknown_reasons pointers differ")
    require_nonnegative_int(document["owner_decision_events"], "owner_decision_events")
    require_nonnegative_int(document["attention_events"], "attention_events")
    if require_nonnegative_int(document["dispatched_non_synthetic_slices"], "dispatched_non_synthetic_slices") == 0:
        raise InvalidEvidence("intervention denominator must be positive")


def lane_units(lane: dict[str, Any]) -> dict[str, Fraction | None]:
    attempts = lane["attempts"]
    denominator = len({attempt["slice_id"] for attempt in attempts if attempt["accepted"]})
    token_total = 0
    cost_total = 0
    duration_total = 0
    turns_total = 0
    token_unknown = False
    cost_unknown = False
    for attempt in attempts:
        for component in ("worker", "coordinator"):
            for field in TOKEN_FIELDS:
                value = attempt[component][field]
                if value is None:
                    token_unknown = True
                else:
                    token_total += value
            value = attempt[component]["cost_microunits"]
            if value is None:
                cost_unknown = True
            else:
                cost_total += value
            duration_total += attempt[component]["duration_ms"]
            turns_total += attempt[component]["turns"]
    return {
        "tokens": None if token_unknown else Fraction(token_total, denominator),
        "cost": None if cost_unknown else Fraction(cost_total, denominator),
        "duration": Fraction(duration_total, denominator),
        "turns": Fraction(turns_total, denominator),
        "retries": Fraction(len(attempts) - len({attempt["slice_id"] for attempt in attempts}), 1),
        "rollbacks": Fraction(sum(attempt["rollback_event_ref"] is not None for attempt in attempts), 1),
    }


def fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def adjudicate(document: dict[str, Any], baseline_hash: str, provider_hash: str) -> dict[str, Any]:
    if contains_private_key(document) or document.get("evidence", {}).get("privacy_status") != "clean":
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["PRIVACY_REFUSED"], "metrics": {}}
    try:
        validate_shape(document, baseline_hash, provider_hash)
    except InvalidEvidence:
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["EVIDENCE_INVALID"], "metrics": {}}

    scope = document["provider_scope"]
    if scope["mode"] == "single-provider" and not isinstance(scope["owner_grant_ref"], str):
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["PROVIDER_SCOPE_INELIGIBLE"], "metrics": {}}
    if scope["mode"] == "single-provider" and not re.fullmatch(r"D[1-9][0-9]*", scope["owner_grant_ref"]):
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["PROVIDER_SCOPE_INELIGIBLE"], "metrics": {}}

    candidate = document["lanes"]["candidate"]
    baseline = document["lanes"]["baseline"]
    workflow = document["lanes"]["workflow"]
    match_b1 = candidate["match"] == baseline["match"]
    match_b2 = candidate["match"] == workflow["match"]
    if not match_b1 and not match_b2:
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["UNMATCHED_SCOPE"], "metrics": {}}

    candidate_units = lane_units(candidate)
    baseline_units = lane_units(baseline)
    workflow_units = lane_units(workflow)
    candidate_tokens, candidate_cost = candidate_units["tokens"], candidate_units["cost"]
    baseline_tokens, baseline_cost = baseline_units["tokens"], baseline_units["cost"]
    workflow_tokens, workflow_cost = workflow_units["tokens"], workflow_units["cost"]
    intervention = Fraction(document["owner_decision_events"], document["dispatched_non_synthetic_slices"])
    metrics: dict[str, str] = {
        "owner_intervention_ratio": fraction_text(intervention),
        "attention_events": f"{document['attention_events']}/1",
        "candidate_total_duration_ms": fraction_text(candidate_units["duration"]),
        "candidate_total_turns": fraction_text(candidate_units["turns"]),
        "candidate_retry_attempts": fraction_text(candidate_units["retries"]),
        "candidate_rollback_attempts": fraction_text(candidate_units["rollbacks"]),
    }
    if candidate_tokens is not None:
        metrics["candidate_total_tokens"] = fraction_text(candidate_tokens)
    if candidate_cost is not None:
        metrics["candidate_total_cost"] = fraction_text(candidate_cost)
    if candidate_tokens not in (None, 0) and workflow_tokens is not None:
        metrics["workflow_token_gain"] = fraction_text(workflow_tokens / candidate_tokens)
    if candidate_cost not in (None, 0) and workflow_cost is not None:
        metrics["workflow_cost_gain"] = fraction_text(workflow_cost / candidate_cost)

    b1_reasons: list[str] = []
    eligible_waves = {
        wave["wave_id"]
        for wave in document["waves"]
        if wave["predeclared"] and not wave["synthetic"] and wave["terminal"] and wave["accepted"]
    }
    if len(eligible_waves) != 5:
        b1_reasons.append("BRANCH1_WAVES_NOT_5")
    if intervention >= Fraction(1, 4):
        b1_reasons.append("BRANCH1_INTERVENTION_NOT_LT_25_PERCENT")
    if not match_b1:
        b1_reasons.append("UNMATCHED_SCOPE")
    elif None in (candidate_tokens, candidate_cost, baseline_tokens, baseline_cost):
        b1_reasons.append("BRANCH1_UNKNOWN")
    elif candidate_tokens > baseline_tokens or candidate_cost > baseline_cost:
        b1_reasons.append("BRANCH1_WORSE_THAN_BASELINE")

    b2_reasons: list[str] = []
    if not match_b2:
        b2_reasons.append("UNMATCHED_SCOPE")
    elif None in (candidate_tokens, candidate_cost, workflow_tokens, workflow_cost) or candidate_tokens == 0 or candidate_cost == 0:
        b2_reasons.append("BRANCH2_UNKNOWN")
    elif workflow_tokens / candidate_tokens < 2 or workflow_cost / candidate_cost < 2:
        b2_reasons.append("BRANCH2_GAIN_LT_2X")

    eligible: list[str] = []
    if not b1_reasons:
        eligible.append("D14-B1")
    if not b2_reasons:
        eligible.append("D14-B2")

    floor_reasons = [f"FLOOR_FAILED:{key}" for key, value in document["floor_results"].items() if value == "fail"]
    floor_reasons += [f"FLOOR_UNKNOWN:{key}" for key, value in document["floor_results"].items() if value == "unknown"]
    if floor_reasons:
        return {"verdict": "NO-GO", "eligible_branches": eligible, "reason_codes": sorted(floor_reasons), "metrics": metrics}
    if eligible:
        reasons = ["GO_BRANCH_1" if branch == "D14-B1" else "GO_BRANCH_2" for branch in eligible]
        return {"verdict": "GO", "eligible_branches": eligible, "reason_codes": reasons, "metrics": metrics}
    reasons: list[str] = []
    for reason in b1_reasons + b2_reasons:
        if reason not in reasons:
            reasons.append(reason)
    return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": reasons, "metrics": metrics}


def validate_contract(contract: Path, rubric: Path, baseline: Path, providers: Path) -> tuple[str, str]:
    text = contract.read_text(encoding="utf-8")
    required_fragments = (
        "`economy-evidence-v1` is frozen at `1.0.0`",
        "owner_intervention_ratio",
        "strictly below",
        "Exactly 25% fails",
        "Exactly 2x passes",
        "not zero",
        "candidate-independent",
        "independent adjudicator",
    )
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise InvalidEvidence(f"contract missing normative fragments: {missing}")
    rubric_text = rubric.read_text(encoding="utf-8")
    missing_floors = sorted(floor for floor in COMMON_FLOORS if floor not in rubric_text)
    if missing_floors:
        raise InvalidEvidence(f"rubric missing common floors: {missing_floors}")
    baseline_hash = sha256(baseline)
    provider_hash = sha256(providers)
    if baseline_hash not in text or provider_hash not in text:
        raise InvalidEvidence("contract does not pin supplied P0 source hashes")
    return baseline_hash, provider_hash


def v1_view(document: dict[str, Any]) -> dict[str, Any]:
    """The v1 projection of a v2 input: the two v2-only carriers removed and the two
    version strings restored. Every other byte is shared, so v1's `validate_shape` and
    `adjudicate` see exactly the document they were frozen against."""
    view = {key: value for key, value in document.items() if key not in V2_ONLY_KEYS}
    view["schema_version"] = "economy-evidence-input-v1"
    view["contract_version"] = "1.0.0"
    return view


def resolve_pointer(document: Any, pointer: str) -> Any:
    parent, leaf = pointer_parent(document, pointer)
    if isinstance(parent, list):
        try:
            return parent[int(leaf)]
        except (ValueError, IndexError) as exc:
            raise InvalidEvidence(f"unresolved pointer: {pointer}") from exc
    if isinstance(parent, dict) and leaf in parent:
        return parent[leaf]
    raise InvalidEvidence(f"unresolved pointer: {pointer}")


def is_measured_zero(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def envelope_parts(pointer: str, label: str) -> tuple[str, int, str]:
    """`/lanes/<lane>/attempts/<index>/<component>` decoded, or a refusal naming the
    exact pointer that failed."""
    parts = decode_pointer(pointer)
    if len(parts) != 5 or parts[0] != "lanes" or parts[2] != "attempts" or parts[4] not in COMPONENTS:
        raise InvalidEvidence(f"{label}: {pointer} is not an attempt envelope pointer")
    try:
        index = int(parts[3])
    except ValueError as exc:
        raise InvalidEvidence(f"{label}: {pointer} carries a non-numeric attempt index") from exc
    return parts[1], index, parts[4]


def validate_zero_bases(document: dict[str, Any], tree_root: Path) -> None:
    """Rule (2) — structural zero envelope, both directions."""
    zero_bases = document["zero_bases"]
    if not isinstance(zero_bases, dict) or any(not isinstance(key, str) for key in zero_bases):
        raise InvalidEvidence("zero_bases must map envelope pointers to declared bases")
    for pointer in sorted(zero_bases):
        entry = require_exact_keys(zero_bases[pointer], ZERO_ENTRY_KEYS, f"zero_bases[{pointer}]")
        _, _, component = envelope_parts(pointer, "zero_bases")
        if entry["component"] != component:
            raise InvalidEvidence(f"zero_bases[{pointer}]: component {entry['component']!r} does not name the pointed envelope")
        if component not in ZERO_BASIS_COMPONENTS:
            raise InvalidEvidence(f"zero_bases[{pointer}]: {component!r} can call a model and is never a structural zero")
        envelope = resolve_pointer(document, pointer)
        if not all(is_measured_zero(envelope[field]) for field in METRIC_FIELDS):
            raise InvalidEvidence(f"zero_bases[{pointer}]: a structural zero requires every metric field to be the integer 0")
        path = entry["path"]
        if not isinstance(path, str) or not path.strip():
            raise InvalidEvidence(f"zero_bases[{pointer}]: path must be a non-empty repository-relative path")
        if path.startswith("/") or ".." in Path(path).parts:
            raise InvalidEvidence(f"zero_bases[{pointer}]: path {path!r} must be repository-relative and must not escape the tree root")
        if not (tree_root / path).exists():
            raise InvalidEvidence(f"zero_bases[{pointer}]: path {path!r} does not resolve under {tree_root}")
        if not isinstance(entry["statement"], str) or not entry["statement"].strip():
            raise InvalidEvidence(f"zero_bases[{pointer}]: statement must be a non-empty basis for the zero")
    for lane_name, lane in document["lanes"].items():
        for index, attempt in enumerate(lane["attempts"]):
            for component in ZERO_BASIS_COMPONENTS:
                pointer = f"/lanes/{lane_name}/attempts/{index}/{component}"
                if all(is_measured_zero(value) for value in attempt[component].values()) and pointer not in zero_bases:
                    raise InvalidEvidence(f"{pointer}: an all-zero {component} envelope requires a zero_bases entry")


def validate_inclusion_bases(document: dict[str, Any]) -> None:
    """Rules (1) and (3) — provider-structural inclusion, both directions, and the
    single-provider attribution boundary."""
    inclusion_bases = document["inclusion_bases"]
    if not isinstance(inclusion_bases, dict) or any(not isinstance(key, str) for key in inclusion_bases):
        raise InvalidEvidence("inclusion_bases must map metric-field pointers to declared bases")
    scope = document["provider_scope"]
    for pointer in sorted(inclusion_bases):
        entry = require_exact_keys(inclusion_bases[pointer], INCLUSION_ENTRY_KEYS, f"inclusion_bases[{pointer}]")
        if scope["mode"] != "single-provider":
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: an inclusion basis is admissible only under a single-provider scope")
        if entry["provider"] != scope["provider"]:
            raise InvalidEvidence(
                f"inclusion_bases[{pointer}]: attributes the measurement to provider {entry['provider']!r}, "
                f"not to the declared {scope['provider']!r}"
            )
        triple = (entry["provider"], entry["contained_field"], entry["containing_field"])
        if triple not in INCLUSION_BASIS_INSTANTIATIONS:
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: undeclared instantiation {':'.join(str(part) for part in triple)}")
        parts = decode_pointer(pointer)
        if len(parts) != 6 or parts[5] not in METRIC_FIELDS:
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: pointer does not name a metric field")
        envelope_pointer = pointer.rsplit("/", 1)[0]
        envelope_parts(envelope_pointer, "inclusion_bases")
        if parts[5] != entry["contained_field"]:
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: contained_field {entry['contained_field']!r} does not name the pointed field")
        if not is_measured_zero(resolve_pointer(document, pointer)):
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: an inclusion basis requires the measured integer 0")
        containing = resolve_pointer(document, envelope_pointer)[entry["containing_field"]]
        if containing is None or isinstance(containing, bool) or not isinstance(containing, int):
            raise InvalidEvidence(
                f"inclusion_bases[{pointer}]: containing field {entry['containing_field']!r} is not a measured integer"
            )
        if not isinstance(entry["evidence_ref"], str) or not entry["evidence_ref"].strip():
            raise InvalidEvidence(f"inclusion_bases[{pointer}]: evidence_ref must be a non-empty reference")
    if scope["mode"] != "single-provider":
        return
    contained_fields = sorted(
        field for provider, field, _ in INCLUSION_BASIS_INSTANTIATIONS if provider == scope["provider"]
    )
    zero_bases = document["zero_bases"]
    for lane_name, lane in document["lanes"].items():
        for index, attempt in enumerate(lane["attempts"]):
            for component in COMPONENTS:
                envelope_pointer = f"/lanes/{lane_name}/attempts/{index}/{component}"
                if envelope_pointer in zero_bases:
                    continue
                for field in contained_fields:
                    pointer = f"{envelope_pointer}/{field}"
                    if is_measured_zero(attempt[component][field]) and pointer not in inclusion_bases:
                        raise InvalidEvidence(
                            f"{pointer}: a bare 0 for a field that {scope['provider']!r} does not report "
                            "separately requires an inclusion_bases entry"
                        )


def validate_shape_v2(document: Any, baseline_hash: str, provider_hash: str, tree_root: Path) -> None:
    require_exact_keys(document, TOP_KEYS_V2, "input")
    if document["schema_version"] != "economy-evidence-input-v2" or document["contract_version"] != "2.0.0":
        raise InvalidEvidence("unsupported evidence schema/version")
    validate_shape(v1_view(document), baseline_hash, provider_hash)
    validate_zero_bases(document, tree_root)
    validate_inclusion_bases(document)


def adjudicate_v2(document: dict[str, Any], baseline_hash: str, provider_hash: str, tree_root: Path) -> dict[str, Any]:
    """The v2 verdict IS the v1 verdict: the two v2 carriers are gated here, and the
    terminal computation is v1's own `adjudicate` over the v1 view."""
    if contains_private_key(document) or document.get("evidence", {}).get("privacy_status") != "clean":
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["PRIVACY_REFUSED"], "metrics": {}}
    try:
        validate_shape_v2(document, baseline_hash, provider_hash, tree_root)
    except InvalidEvidence:
        return {"verdict": "NO-GO", "eligible_branches": [], "reason_codes": ["EVIDENCE_INVALID"], "metrics": {}}
    return adjudicate(v1_view(document), baseline_hash, provider_hash)


def validate_contract_v2(contract: Path, rubric: Path, baseline: Path, providers: Path) -> tuple[str, str]:
    text = contract.read_text(encoding="utf-8")
    required_fragments = (
        "`economy-evidence-v2` is frozen at `2.0.0`",
        "additive successor",
        "owner_intervention_ratio",
        "strictly below",
        "Exactly 25% fails",
        "Exactly 2x passes",
        "not zero",
        "candidate-independent",
        "independent adjudicator",
        "declared-set: inclusion_basis_instantiations",
        "claude-code:reasoning_tokens:output_tokens",
        "declared-set: zero_basis_components",
        "inclusion_bases",
        "zero_bases",
        "never implies parity",
        "never rendered as parity",
    )
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise InvalidEvidence(f"contract missing normative fragments: {missing}")
    forbidden_fragments = ("`economy-evidence-v1` is frozen at `1.0.0`",)
    present = [fragment for fragment in forbidden_fragments if fragment in text]
    if present:
        raise InvalidEvidence(f"v2 contract restates the v1 freeze line: {present}")
    rubric_text = rubric.read_text(encoding="utf-8")
    missing_floors = sorted(floor for floor in COMMON_FLOORS if floor not in rubric_text)
    if missing_floors:
        raise InvalidEvidence(f"rubric missing common floors: {missing_floors}")
    baseline_hash = sha256(baseline)
    provider_hash = sha256(providers)
    if baseline_hash not in text or provider_hash not in text:
        raise InvalidEvidence("contract does not pin supplied P0 source hashes")
    return baseline_hash, provider_hash


def lift_v1_base_input(base_input: dict[str, Any]) -> dict[str, Any]:
    """The mechanical v1→v2 lift, asserted to be exactly four operations: the two
    version strings and the two empty carriers. Nothing else may differ, or the
    regression assertion below would be comparing two different inputs."""
    lifted = copy.deepcopy(base_input)
    lifted["schema_version"] = "economy-evidence-input-v2"
    lifted["contract_version"] = "2.0.0"
    lifted["inclusion_bases"] = {}
    lifted["zero_bases"] = {}
    if set(lifted) - set(base_input) != V2_ONLY_KEYS:
        raise InvalidEvidence("the v1 lift added a key outside the two v2 carriers")
    changed = sorted(key for key in base_input if lifted[key] != base_input[key])
    if changed != ["contract_version", "schema_version"]:
        raise InvalidEvidence(f"the v1 lift changed {changed}, not only the two version strings")
    return lifted


def check_cases(
    base_input: dict[str, Any],
    cases: Any,
    baseline_hash: str,
    provider_hash: str,
    tree_root: Path,
    label: str,
) -> int:
    if not isinstance(cases, list) or not cases:
        raise InvalidEvidence(f"{label}: case bank must be non-empty")
    case_ids: set[str] = set()
    for case in cases:
        require_exact_keys(case, {"id", "mutations", "expected"}, f"{label} case")
        if not isinstance(case["id"], str) or not case["id"] or case["id"] in case_ids:
            raise InvalidEvidence(f"{label}: case IDs must be unique non-empty strings")
        case_ids.add(case["id"])
        expected = require_exact_keys(
            case["expected"], {"verdict", "eligible_branches", "reason_codes", "metrics"}, f"{label} case {case['id']} expected"
        )
        actual = adjudicate_v2(apply_mutations(base_input, case["mutations"]), baseline_hash, provider_hash, tree_root)
        for key in ("verdict", "eligible_branches", "reason_codes"):
            if actual[key] != expected[key]:
                raise InvalidEvidence(f"{label} case {case['id']}: {key} expected {expected[key]!r}, got {actual[key]!r}")
        if not isinstance(expected["metrics"], dict):
            raise InvalidEvidence(f"{label} case {case['id']}: expected.metrics must be an object")
        for key, value in expected["metrics"].items():
            if actual["metrics"].get(key) != value:
                raise InvalidEvidence(
                    f"{label} case {case['id']}: metric {key} expected {value!r}, got {actual['metrics'].get(key)!r}"
                )
    return len(cases)


def run_v2(args: argparse.Namespace) -> int:
    try:
        if args.v1_cases is None or args.tree_root is None:
            raise InvalidEvidence("--contract-version 2.0.0 requires --v1-cases and --tree-root")
        tree_root = args.tree_root
        if not tree_root.is_dir():
            raise InvalidEvidence(f"--tree-root {tree_root} is not a directory")
        baseline_hash, provider_hash = validate_contract_v2(args.contract, args.rubric, args.baseline, args.providers)
        case_bank = load_json(args.cases)
        require_exact_keys(case_bank, {"schema_version", "contract_version", "base_input", "cases"}, "case bank")
        if case_bank["schema_version"] != "economy-evidence-cases-v2" or case_bank["contract_version"] != "2.0.0":
            raise InvalidEvidence("case bank version mismatch")
        validate_shape_v2(case_bank["base_input"], baseline_hash, provider_hash, tree_root)
        v2_count = check_cases(case_bank["base_input"], case_bank["cases"], baseline_hash, provider_hash, tree_root, "v2")

        v1_bank = load_json(args.v1_cases)
        require_exact_keys(v1_bank, {"schema_version", "contract_version", "base_input", "cases"}, "v1 case bank")
        if v1_bank["schema_version"] != "economy-evidence-cases-v1" or v1_bank["contract_version"] != "1.0.0":
            raise InvalidEvidence("v1 case bank version mismatch")
        lifted = lift_v1_base_input(v1_bank["base_input"])
        validate_shape_v2(lifted, baseline_hash, provider_hash, tree_root)
        v1_count = check_cases(lifted, v1_bank["cases"], baseline_hash, provider_hash, tree_root, "v1-regression")
    except (InvalidEvidence, OSError, json.JSONDecodeError) as exc:
        print(f"economy-evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"economy-evidence: OK ({v2_count} v2 cases; rules 1/2/3 closed and both directions enforced; "
        f"{v1_count} v1 cases re-run under v2 with unchanged verdicts)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--providers", required=True, type=Path)
    parser.add_argument("--contract-version", choices=("1.0.0", "2.0.0"), default="1.0.0")
    parser.add_argument("--v1-cases", type=Path, default=None)
    parser.add_argument("--tree-root", type=Path, default=None)
    args = parser.parse_args()
    if args.contract_version == "2.0.0":
        return run_v2(args)
    if args.v1_cases is not None or args.tree_root is not None:
        print("economy-evidence: FAIL: --v1-cases/--tree-root belong to --contract-version 2.0.0", file=sys.stderr)
        return 1
    try:
        baseline_hash, provider_hash = validate_contract(args.contract, args.rubric, args.baseline, args.providers)
        case_bank = load_json(args.cases)
        require_exact_keys(case_bank, {"schema_version", "contract_version", "base_input", "cases"}, "case bank")
        if case_bank["schema_version"] != "economy-evidence-cases-v1" or case_bank["contract_version"] != "1.0.0":
            raise InvalidEvidence("case bank version mismatch")
        validate_shape(case_bank["base_input"], baseline_hash, provider_hash)
        cases = case_bank["cases"]
        if not isinstance(cases, list) or not cases:
            raise InvalidEvidence("case bank must be non-empty")
        case_ids: set[str] = set()
        for case in cases:
            require_exact_keys(case, {"id", "mutations", "expected"}, "case")
            if not isinstance(case["id"], str) or not case["id"] or case["id"] in case_ids:
                raise InvalidEvidence("case IDs must be unique non-empty strings")
            case_ids.add(case["id"])
            expected = require_exact_keys(case["expected"], {"verdict", "eligible_branches", "reason_codes", "metrics"}, f"case {case['id']} expected")
            actual = adjudicate(apply_mutations(case_bank["base_input"], case["mutations"]), baseline_hash, provider_hash)
            for key in ("verdict", "eligible_branches", "reason_codes"):
                if actual[key] != expected[key]:
                    raise InvalidEvidence(f"case {case['id']}: {key} expected {expected[key]!r}, got {actual[key]!r}")
            if not isinstance(expected["metrics"], dict):
                raise InvalidEvidence(f"case {case['id']}: expected.metrics must be an object")
            for key, value in expected["metrics"].items():
                if actual["metrics"].get(key) != value:
                    raise InvalidEvidence(f"case {case['id']}: metric {key} expected {value!r}, got {actual['metrics'].get(key)!r}")
    except (InvalidEvidence, OSError, json.JSONDecodeError) as exc:
        print(f"economy-evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"economy-evidence: OK ({len(cases)} cases; 5-wave and 25%/2x boundaries; all-attempt accounting)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
