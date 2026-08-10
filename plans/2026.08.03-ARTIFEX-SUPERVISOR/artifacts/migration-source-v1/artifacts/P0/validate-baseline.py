#!/usr/bin/env python3
"""Validate an Artifex P0 baseline catalog with deterministic stdlib diagnostics."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


LANES = {"manual", "workflow", "harness-run"}
CLASSIFICATIONS = {"measured", "synthetic", "baseline_pending", "ineligible"}
EVIDENCE_CLASSES = {"committed", "machine_local"}
HASH_FIELDS = {"source_hash", "plan_hash", "scope_hash", "acceptance_hash", "validation_hash"}
METRIC_FIELDS = {
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cost_usd",
    "turns",
    "duration_ms",
    "provider_calls",
    "retries",
    "accepted_slices",
    "owner_interventions",
}
ROW_FIELDS = {
    "id",
    "lane",
    "classification",
    "evidence_class",
    "source_anchor",
    "repository",
    "plan_id",
    "provider",
    "model_class",
    "effort",
    *HASH_FIELDS,
    "metrics",
    "unknown_reason",
    "eligible_for_matching",
    "eligible_for_battle_wave",
    "notes",
}
ROOT_FIELDS = {
    "schema_version",
    "captured_on",
    "source_tree_ref",
    "selection_policy",
    "candidates",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _load(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["$: root must be an object"]
    missing_root = sorted(ROOT_FIELDS - set(value))
    unknown_root = sorted(set(value) - ROOT_FIELDS)
    if missing_root:
        errors.append(f"$: missing root fields: {missing_root}")
    if unknown_root:
        errors.append(f"$: unknown root fields: {unknown_root}")
    if errors:
        return errors

    if value["schema_version"] != "artifex-baseline-catalog/v1":
        errors.append("$.schema_version: expected artifex-baseline-catalog/v1")
    if not isinstance(value["captured_on"], str) or not value["captured_on"]:
        errors.append("$.captured_on: expected non-empty string")
    if not isinstance(value["source_tree_ref"], str) or not GIT_SHA.fullmatch(value["source_tree_ref"]):
        errors.append("$.source_tree_ref: expected full lowercase Git SHA")
    if not isinstance(value["selection_policy"], str) or not value["selection_policy"]:
        errors.append("$.selection_policy: expected non-empty string")

    rows = value["candidates"]
    if not isinstance(rows, list):
        return errors + ["$.candidates: expected array"]
    ids: list[str] = []
    observed_lanes: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"$.candidates[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}: expected object")
            continue
        missing = sorted(ROW_FIELDS - set(row))
        unknown = sorted(set(row) - ROW_FIELDS)
        if missing:
            errors.append(f"{prefix}: missing fields: {missing}")
        if unknown:
            errors.append(f"{prefix}: unknown fields: {unknown}")
        if missing:
            continue

        row_id = row["id"]
        if not isinstance(row_id, str) or not row_id:
            errors.append(f"{prefix}.id: expected non-empty string")
        else:
            ids.append(row_id)
        lane = row["lane"]
        if lane not in LANES:
            errors.append(f"{prefix}.lane: expected one of {sorted(LANES)}")
        else:
            observed_lanes.add(lane)
        classification = row["classification"]
        if classification not in CLASSIFICATIONS:
            errors.append(
                f"{prefix}.classification: expected one of {sorted(CLASSIFICATIONS)}"
            )
        if row["evidence_class"] not in EVIDENCE_CLASSES:
            errors.append(
                f"{prefix}.evidence_class: expected one of {sorted(EVIDENCE_CLASSES)}"
            )
        for field in ("source_anchor", "repository", "notes"):
            if not isinstance(row[field], str) or not row[field]:
                errors.append(f"{prefix}.{field}: expected non-empty string")
        for field in ("plan_id", "provider", "model_class", "effort"):
            if row[field] is not None and (not isinstance(row[field], str) or not row[field]):
                errors.append(f"{prefix}.{field}: expected non-empty string or null")
        for field in HASH_FIELDS:
            field_value = row[field]
            if field_value is not None and (
                not isinstance(field_value, str) or not SHA256.fullmatch(field_value)
            ):
                errors.append(f"{prefix}.{field}: expected lowercase SHA-256 or null")

        unknown_reason = row["unknown_reason"]
        if not isinstance(unknown_reason, dict):
            errors.append(f"{prefix}.unknown_reason: expected object")
            unknown_reason = {}
        else:
            for field, reason in sorted(unknown_reason.items()):
                if not isinstance(field, str) or not field:
                    errors.append(f"{prefix}.unknown_reason: keys must be non-empty strings")
                if not isinstance(reason, str) or not reason:
                    errors.append(f"{prefix}.unknown_reason.{field}: expected non-empty string")

        metrics = row["metrics"]
        if not isinstance(metrics, dict):
            errors.append(f"{prefix}.metrics: expected object")
            metrics = {}
        else:
            metric_missing = sorted(METRIC_FIELDS - set(metrics))
            metric_unknown = sorted(set(metrics) - METRIC_FIELDS)
            if metric_missing:
                errors.append(f"{prefix}.metrics: missing fields: {metric_missing}")
            if metric_unknown:
                errors.append(f"{prefix}.metrics: unknown fields: {metric_unknown}")
        for field in sorted(METRIC_FIELDS & set(metrics)):
            metric = metrics[field]
            if metric is not None and (not _is_number(metric) or metric < 0):
                errors.append(f"{prefix}.metrics.{field}: expected non-negative number or null")
            if metric is None and field not in unknown_reason:
                errors.append(f"{prefix}.metrics.{field}: null requires unknown_reason")
        for field in sorted(HASH_FIELDS | {"plan_id", "provider", "model_class", "effort"}):
            if row[field] is None and field not in unknown_reason:
                errors.append(f"{prefix}.{field}: null requires unknown_reason")

        for field in ("eligible_for_matching", "eligible_for_battle_wave"):
            if not isinstance(row[field], bool):
                errors.append(f"{prefix}.{field}: expected boolean")
        if classification == "synthetic" and row["eligible_for_battle_wave"] is not False:
            errors.append(f"{prefix}: synthetic evidence cannot be battle-wave eligible")
        if classification in {"baseline_pending", "ineligible"} and row["eligible_for_matching"] is not False:
            errors.append(f"{prefix}: pending/ineligible evidence cannot be matching-eligible")
        if classification == "measured" and not row["eligible_for_matching"]:
            errors.append(f"{prefix}: measured evidence must be matching-eligible")

    if len(ids) != len(set(ids)):
        errors.append("$.candidates: ids must be unique")
    if ids != sorted(ids):
        errors.append("$.candidates: rows must be sorted by id")
    missing_lanes = sorted(LANES - observed_lanes)
    if missing_lanes:
        errors.append(f"$.candidates: missing incumbent lanes: {missing_lanes}")
    return sorted(errors)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <baseline-catalog.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        value = _load(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"baseline-catalog: ERROR: {exc}", file=sys.stderr)
        return 1
    errors = validate(value)
    if errors:
        for error in errors:
            print(f"baseline-catalog: ERROR: {error}", file=sys.stderr)
        return 1
    rows = value["candidates"]
    classes = sorted({row["classification"] for row in rows})
    print(
        "baseline-catalog: OK — "
        f"{len(rows)} rows; lanes={','.join(sorted(LANES))}; "
        f"classes={','.join(classes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
