#!/usr/bin/env python3
"""Build and validate the frozen P5 trial/shadow proposal without dispatching a provider."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
SCHEMA = "artifex-p5-shadow-v1"
ROUTE = {"model_class": "implementation", "effort": "high"}
CAPABILITIES = {
    "codex": ["structured_output", "machine_events", "permission_boundary", "ephemeral_session"],
    "claude-code": ["structured_output", "machine_events", "permission_boundary"],
}
DEFAULT_CAPS = {
    "max_slices": 1,
    "timeout_ms": 180000,
    "max_envelope_bytes": 65536,
    "max_event_count": 64,
    "max_turns": 8,
    "max_output_bytes": 16384,
    "token_limit": 8000,
    "cost_limit_microunits": 5_000_000,
}
ARCHIVE_PATHS = [
    "plans/archive/2026.07.18-FOREMAN/root/contracts/artifex-run-folder.md",
    "plans/archive/2026.07.18-FOREMAN/plan.md",
    "plans/archive/2026.07.18-FOREMAN/journal.jsonl",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P2.1/state-transition-cases.json",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/cases.json",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/graders.json",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/reliability-bank-v1/bank-manifest.json",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P3.10/layer2-manifest.json",
    "plans/archive/2026.07.24-AGENT-RELIABILITY/findings/P3.10-layer2-paired.md",
]
CURRENT_CONTRACTS = {
    "run": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/supervisor-run-v1.md",
    "slice": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/slice-manifest-v1.md",
    "authority": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/authority-policy-v1.md",
    "worker": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/worker-envelope-v1.md",
    "economy": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/economy-evidence-v1.md",
    "admission": "plans/2026.08.03-ARTIFEX-SUPERVISOR/root/contracts/dispatch-admission-v1.md",
}
PILOT_COMMIT = "e3c932aa0f2d364aefc7c64a9dc6c052e3c3df95"
PILOT_SLICES = [
    (
        "p5.2-slice-01-worktree-core",
        "codex",
        [
            "packages/artifex/lib/artifex/worktree.py",
            "packages/artifex/tests/test_worktree_isolation.py",
        ],
    ),
    (
        "p5.2-slice-02-worktree-binding",
        "claude-code",
        [
            "packages/artifex/lib/artifex/cli.py",
            "packages/artifex/lib/artifex/scheduler.py",
            "packages/artifex/lib/artifex/worker.py",
        ],
    ),
    (
        "p5.2-slice-03-worktree-evidence",
        "codex",
        [
            "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/validate-worktree.py",
            "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/worktree-cases-v1.json",
            "plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P4/worktree-results-v1.json",
        ],
    ),
]
RECOVERY_CALLS = [
    ("p5.3-call-01-crash-after-intent", "codex", "crash-after-intent"),
    ("p5.3-call-02-crash-after-observation", "claude-code", "crash-after-observation"),
    ("p5.3-call-03-duplicate-dispatch", "codex", "duplicate-dispatch"),
    ("p5.3-call-04-timeout", "codex", "provider-timeout"),
    ("p5.3-call-05-schema-refusal", "claude-code", "schema-refusal"),
    ("p5.3-call-06-third-state", "claude-code", "unknown-third-state"),
]
BATTLE_WAVES = [
    ("p5.4-wave-01-recovery-fixture", "bde07fb080074280540ea82e9354965af53049bf", "codex", "live-manual"),
    ("p5.4-wave-02-worktree-isolation", PILOT_COMMIT, "claude-code", "live-harness-run"),
    ("p5.4-wave-03-security-boundary", "7607b0c09a8552ea4227feb93495944048d9f4c8", "claude-code", "live-workflow"),
    ("p5.4-wave-04-telemetry-assurance", "23f71d344252280ece3117b810e8cb991de0d226", "codex", "live-manual"),
    ("p5.4-wave-05-committed-gates", "138b2424a3e5dcce4afb66b4bc553dfef0ded0f3", "claude-code", "live-harness-run"),
]


class ShadowError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any, *, omit: str | None = None) -> str:
    body = {key: item for key, item in value.items() if key != omit} if isinstance(value, dict) and omit else value
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    run = subprocess.run(["git", *args], cwd=root, capture_output=True, text=not binary, check=False)
    if run.returncode:
        error = run.stderr.decode(errors="replace") if binary else run.stderr
        raise ShadowError(error.strip() or f"git {' '.join(args)} failed")
    return run.stdout


def commit_record(root: Path, commit: str) -> dict[str, Any]:
    full = str(git(root, "rev-parse", f"{commit}^{{commit}}")).strip()
    parent = str(git(root, "rev-parse", f"{full}^" )).strip()
    subject = str(git(root, "show", "-s", "--format=%s", full)).strip()
    paths = sorted(line for line in str(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", full)).splitlines() if line)
    patch = bytes(git(root, "show", "--format=", "--binary", full, binary=True))
    return {
        "commit": full,
        "base_commit": parent,
        "subject": subject,
        "files": paths,
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
    }


def package_digest(rows: list[dict[str, str]]) -> str:
    return canonical_hash(sorted(rows, key=lambda row: row["path"]))


def source_hashes(root: Path) -> dict[str, str]:
    return {name: digest(root / path) for name, path in CURRENT_CONTRACTS.items()}


def trial_row(*, trial_id: str, item: str, order: int, provider: str, kind: str,
              base_commit: str, files: list[str], patch_sha256: str | None,
              baseline_lane: str | None, scenario: str) -> dict[str, Any]:
    acceptance = [
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
        "PRV-PARITY-SCOPE",
    ]
    return {
        "trial_id": trial_id,
        "item": item,
        "kind": kind,
        "order": order,
        "provider": provider,
        "route": ROUTE,
        "capabilities": CAPABILITIES[provider],
        "repository": "swissknifeman-controlled-disposable",
        "controlled_root": f"mktemp:p5-{item.lower().replace('.', '-')}-{trial_id}",
        "base_commit": base_commit,
        "files": files,
        "historical_patch_sha256": patch_sha256,
        "scenario": scenario,
        "acceptance_refs": acceptance,
        "validation": ["scoped-git-diff", "frozen-acceptance", "rollback-to-exact-base"],
        "baseline_lane": baseline_lane,
        "baseline_evidence_class": "live-paired" if baseline_lane else "not-economic",
        "budgets": DEFAULT_CAPS,
        "purpose": "business-trial",
        "candidate_dispatch": True,
    }


def build_catalog(root: Path, assurance: dict[str, Any], *, source_tree_ref: str | None = None) -> dict[str, Any]:
    history = {record[1]: commit_record(root, record[1]) for record in BATTLE_WAVES}
    pilot = commit_record(root, PILOT_COMMIT)
    rows: list[dict[str, Any]] = []
    for index, (trial_id, provider, files) in enumerate(PILOT_SLICES, 1):
        if not set(files).issubset(set(pilot["files"])):
            raise ShadowError(f"pilot slice outside historical commit: {trial_id}")
        rows.append(trial_row(
            trial_id=trial_id, item="P5.2", order=index, provider=provider,
            kind="repository-slice", base_commit=pilot["base_commit"], files=files,
            patch_sha256=pilot["patch_sha256"], baseline_lane=None,
            scenario=f"reconstruct bounded subset of {pilot['subject']}",
        ))
    for offset, (trial_id, provider, scenario) in enumerate(RECOVERY_CALLS, 4):
        rows.append(trial_row(
            trial_id=trial_id, item="P5.3", order=offset, provider=provider,
            kind="recovery-call", base_commit=pilot["base_commit"], files=pilot["files"],
            patch_sha256=pilot["patch_sha256"], baseline_lane=None, scenario=scenario,
        ))
    for offset, (trial_id, commit, provider, baseline) in enumerate(BATTLE_WAVES, 10):
        record = history[commit]
        rows.append(trial_row(
            trial_id=trial_id, item="P5.4", order=offset, provider=provider,
            kind="battle-wave", base_commit=record["base_commit"], files=record["files"],
            patch_sha256=record["patch_sha256"], baseline_lane=baseline,
            scenario=record["subject"],
        ))
    rows.sort(key=lambda row: row["order"])
    value = {
        "schema_version": "artifex-trial-catalog-v1",
        "catalog_version": "1.0.0",
        "frozen_before_candidate_event": True,
        "source_tree_ref": source_tree_ref or str(git(root, "rev-parse", "HEAD")).strip(),
        "assurance": {
            "path": f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json",
            "sha256": digest(root / f"plans/{PLAN_ID}/artifacts/P4/assurance-manifest-v1.json"),
            "readiness": assurance["readiness"],
            "package_digest": package_digest(assurance["g2"]["package_files"]),
        },
        "contract_sha256": source_hashes(root),
        "historical_commits": sorted(history.values(), key=lambda row: row["commit"]),
        "trials": rows,
        "counts": {
            "candidate_dispatches": len(rows),
            "p5_2_slices": sum(row["item"] == "P5.2" for row in rows),
            "p5_3_calls": sum(row["item"] == "P5.3" for row in rows),
            "p5_4_battle_waves": sum(row["item"] == "P5.4" for row in rows),
        },
        "economic_claim": None,
    }
    value["catalog_hash"] = canonical_hash(value, omit="catalog_hash")
    return value


def rubric_map(case: dict[str, Any]) -> list[str]:
    tags = {tag for assertion in case.get("assertions", []) for tag in assertion.get("tags", [])}
    mapped = {"EVD-INDEPENDENT-ADJUDICATOR"}
    if "requirement_retention" in tags or "public_acceptance" in tags:
        mapped.update({"REL-ACCEPTED-SCOPE", "EVD-SOURCE-HASHES"})
    if "no_redundant_approval" in tags or case.get("owner_gate_required"):
        mapped.add("SEC-AUTHORITY")
    if "control_no_false_block" in tags:
        mapped.add("REL-VALIDATION")
    if "portability" in tags:
        mapped.add("EVD-SOURCE-HASHES")
    if "provider_neutrality" in tags:
        mapped.add("PRV-PARITY-SCOPE")
    return sorted(mapped)


def build_mapping(root: Path) -> dict[str, Any]:
    inventory = [
        {"path": path, "sha256": digest(root / path), "bytes": (root / path).stat().st_size}
        for path in ARCHIVE_PATHS
    ]
    state_cases = load(root / ARCHIVE_PATHS[3])
    bank = load(root / ARCHIVE_PATHS[4])
    matrix_rows = []
    for row in state_cases["cells"]:
        mapped = "REL-VALIDATION"
        if row["event"] in {"pre-mutation-allow", "pre-mutation-deny", "owner-decision", "escalation-trigger"}:
            mapped = "SEC-AUTHORITY"
        elif row["event"] in {"pre-final-allow", "pre-final-deny", "close-committed"}:
            mapped = "REL-ACCEPTED-SCOPE"
        matrix_rows.append({
            "case_id": f"{row['state']}::{row['event']}",
            "source_kind": row["kind"],
            "mapped_rubric": mapped,
            "expected_hash": canonical_hash(row),
        })
    bank_rows = [{
        "case_id": case["case_id"],
        "kind": case["kind"],
        "family": case["family"],
        "owner_gate_required": case["owner_gate_required"],
        "mapped_rubrics": rubric_map(case),
        "expected_actions_hash": canonical_hash(case["expected_actions"]),
        "forbidden_actions_hash": canonical_hash(case["forbidden_actions"]),
        "assertions_hash": canonical_hash(case["assertions"]),
    } for case in bank["cases"]]
    return {
        "schema_version": "artifex-archive-mapping-v1",
        "mapping_version": "1.0.0",
        "archive_inventory": inventory,
        "foreman_mapping": [
            {"source": "artifex-run-folder.md#state/journal/resume", "current": ["supervisor-run-v1"], "status": "mapped-data-only"},
            {"source": "artifex-run-folder.md#mandate", "current": ["authority-policy-v1"], "status": "mapped-data-only"},
            {"source": "FOREMAN plan/handoff parser semantics", "current": [], "status": "historical-only-obsolete"},
            {"source": "FOREMAN journal blocked rows", "current": ["economy-evidence-v1"], "status": "mapped-unknown-preserved"},
        ],
        "state_transition_mapping": matrix_rows,
        "reliability_bank_mapping": bank_rows,
        "layer2_mapping": {
            "status": "shadow-only-not-economic",
            "declared_subset": "5/31",
            "owner_intervention_ratio": None,
            "unknown_reason": "owner_question is unmappable in the historical carrier",
        },
        "counts": {
            "archive_files": len(inventory),
            "state_transition_cells": len(matrix_rows),
            "bank_cases": len(bank_rows),
            "bank_controls": sum(row["kind"] == "control" for row in bank_rows),
        },
    }


def build_shadow(mapping: dict[str, Any]) -> dict[str, Any]:
    state_rows = mapping["state_transition_mapping"]
    bank_rows = mapping["reliability_bank_mapping"]
    outcomes = [
        {"case_id": row["case_id"], "result": "mapped", "expected_hash": row["expected_hash"]}
        for row in state_rows
    ]
    outcomes.extend(
        {"case_id": row["case_id"], "result": "expected-and-forbidden-preserved", "kind": row["kind"]}
        for row in bank_rows
    )
    return {
        "schema_version": "artifex-shadow-results-v1",
        "shadow_version": "1.0.0",
        "candidate_calls": 0,
        "economic_evidence": False,
        "archive_code_imported": False,
        "outcomes": outcomes,
        "summary": {
            "mapped": len(state_rows) + len(bank_rows),
            "unknown": 1,
            "unknown_reasons": [mapping["layer2_mapping"]["unknown_reason"]],
            "positive_controls": sum(row["kind"] == "control" for row in bank_rows),
        },
    }


def build_request(root: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    providers = sorted({row["provider"] for row in catalog["trials"]})
    roots = sorted({row["controlled_root"] for row in catalog["trials"]})
    value = {
        "schema_version": "artifex-business-grant-request-v1",
        "request_version": "1.0.0",
        "owner_marker": "[OWNER-GRANT:G-OWNER-P5-BUSINESS]",
        "catalog_path": f"plans/{PLAN_ID}/artifacts/P5/trial-catalog-v1.json",
        "catalog_hash": catalog["catalog_hash"],
        "assurance_sha256": catalog["assurance"]["sha256"],
        "g2_package_digest": catalog["assurance"]["package_digest"],
        "providers": providers,
        "controlled_roots": roots,
        "trial_ids": [row["trial_id"] for row in catalog["trials"]],
        "maximum_dispatch_count": catalog["counts"]["candidate_dispatches"],
        "per_trial_caps": DEFAULT_CAPS,
        "expiry_rule": "grant marker date + 7 days at 23:59:59Z",
        "revocation_rule": "any later Decision Log row naming this request_hash with revoked=true",
        "grant_scope": "one non-reusable purpose=business-trial grant/admission per trial_id",
        "forbidden_substitutions": ["D74", "G-OWNER-P5.4-SINGLE", "provider-readiness-smoke", "historical-g1"],
    }
    value["request_hash"] = canonical_hash(value, omit="request_hash")
    return value


def validate(root: Path, out: Path, package: Path, assurance_path: Path) -> None:
    catalog = load(out / "trial-catalog-v1.json")
    mapping = load(out / "archive-mapping-v1.json")
    shadow = load(out / "shadow-results-v1.json")
    request = load(out / "business-grant-request-v1.json")
    assurance = load(assurance_path)
    if assurance.get("schema_version") != "artifex-p4-assurance-manifest-v1" or assurance.get("readiness") != "green":
        raise ShadowError("terminal P4 assurance is not exact green")
    expected_rows = assurance.get("g2", {}).get("package_files")
    actual_rows = []
    for row in expected_rows:
        path = root / row["path"]
        actual_rows.append({"path": row["path"], "sha256": digest(path)})
    if actual_rows != expected_rows or package_digest(actual_rows) != catalog["assurance"]["package_digest"]:
        raise ShadowError("current package differs from G2")
    if package.resolve() != (root / "packages/artifex").resolve():
        raise ShadowError("package root mismatch")
    help_run = subprocess.run([str(package / "bin/artifex"), "--help"], cwd=root, text=True, capture_output=True)
    if help_run.returncode or "usage: artifex" not in help_run.stdout:
        raise ShadowError("standalone CLI identity unavailable")
    if catalog != build_catalog(root, assurance, source_tree_ref=catalog.get("source_tree_ref")):
        raise ShadowError("trial catalog drift")
    if mapping != build_mapping(root):
        raise ShadowError("archive mapping/hash drift")
    if shadow != build_shadow(mapping):
        raise ShadowError("shadow result drift")
    if request != build_request(root, catalog):
        raise ShadowError("business request drift")
    trials = catalog["trials"]
    ids = [row["trial_id"] for row in trials]
    if len(ids) != len(set(ids)) or [row["order"] for row in trials] != list(range(1, len(trials) + 1)):
        raise ShadowError("trial identity/order drift")
    if catalog["counts"] != {"candidate_dispatches": 14, "p5_2_slices": 3, "p5_3_calls": 6, "p5_4_battle_waves": 5}:
        raise ShadowError("trial count drift")
    if request["maximum_dispatch_count"] != len(trials) or set(request["providers"]) != set(CAPABILITIES):
        raise ShadowError("request scope/count drift")
    if any((out / name).exists() for name in (
        "business-grants-v1.json", "trial-dispatch-manifest-index-v1.json",
        "trial-replay-v1.jsonl", "trial-admission-index-v1.json",
        "build-trial-admissions.py", "validate-trial-admissions.py",
    )) or (out / "trial-admissions").exists():
        raise ShadowError("business carriers exist before exact owner grant")
    print(
        "P5 shadow validator: OK "
        f"({len(mapping['archive_inventory'])} archive files; "
        f"{mapping['counts']['state_transition_cells']} transition cells; "
        f"{mapping['counts']['bank_cases']} bank cases; 14 frozen dispatches; 0 provider calls)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--assurance", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    out = Path(__file__).resolve().parent
    try:
        assurance = load(args.assurance)
        if args.write:
            catalog = build_catalog(root, assurance)
            mapping = build_mapping(root)
            write(out / "trial-catalog-v1.json", catalog)
            write(out / "archive-mapping-v1.json", mapping)
            write(out / "shadow-results-v1.json", build_shadow(mapping))
            write(out / "business-grant-request-v1.json", build_request(root, catalog))
            print("P5 shadow artifacts: written")
        validate(root, out, args.package, args.assurance)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ShadowError) as exc:
        print(f"P5 shadow validator: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
