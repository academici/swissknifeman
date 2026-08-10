#!/usr/bin/env python3
"""Independent P5.2 repository-pilot-results validator.

Reads only already-written evidence; issues no provider process and mutates no
byte. Kept deliberately separate from ``run-pilot.py`` — it must not import or
trust that harness's own bookkeeping, only independently re-derive and recheck
it against the live G2B manifests, the D122 admission index and Git.

D121/D122 re-run (2026-08-06): re-pinned from the historical v1 three-slice
batch (`repository-pilot-results-v1.json`, preserved read-only, never touched
by this script again) to the three D122 replacement identities and P5.1's
reopened v2 admission index/catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
ORDER = ("p5.2r-slice-01-worktree-core", "p5.2r-slice-02-worktree-binding", "p5.2r-slice-03-worktree-evidence")
EXPECTED_VERSION = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}
EXPECTED_PROVIDER = {"p5.2r-slice-01-worktree-core": "codex", "p5.2r-slice-02-worktree-binding": "claude-code",
                     "p5.2r-slice-03-worktree-evidence": "codex"}
V1_TRIAL_FOR = {"p5.2r-slice-01-worktree-core": "p5.2-slice-01-worktree-core",
               "p5.2r-slice-02-worktree-binding": "p5.2-slice-02-worktree-binding",
               "p5.2r-slice-03-worktree-evidence": "p5.2-slice-03-worktree-evidence"}
OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5.2-RETRY]"
RAISED_PROVIDER, RAISED_TIMEOUT_MS, BASE_TIMEOUT_MS = "claude-code", 600000, 180000


class Invalid(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Invalid(f"object required: {path}")
    return value


def git(repo: Path, *argv: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *argv], cwd=str(repo), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          shell=False, check=False)


def check_admission(index_row: dict, plan: Path) -> dict:
    """Re-check the on-disk v2 admission fixture is byte-identical to the index and its
    usage/replay counters were never mutated by the seam it fed, and that its grant carries
    the exact D122 owner binding (not a silently substituted D105 row)."""
    admission_path = plan / index_row["path"]
    admission = load(admission_path)
    trial_id = index_row.get("trial_id")
    if digest(admission_path) != index_row.get("sha256"):
        raise Invalid(f"admission bytes mutated: {trial_id}")
    if admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}:
        raise Invalid(f"admission usage mutated: {trial_id}")
    replay = admission.get("replay", {})
    if replay.get("events") != [] or replay.get("used_slices") != 0:
        raise Invalid(f"admission replay mutated: {trial_id}")
    grant = admission.get("grant", {})
    if (admission.get("task", {}).get("budgets", {}).get("max_slices") != 1 or grant.get("max_slices") != 1):
        raise Invalid(f"admission is not a one-slice grant: {trial_id}")
    if grant.get("owner_decision") != "D122" or grant.get("owner_marker") != OWNER_MARKER:
        raise Invalid(f"admission is not D122/{OWNER_MARKER}-bound: {trial_id}")
    return admission


def check_budget_raise(trial_id: str, task: dict, baseline_catalog: dict) -> None:
    """D122 rule: every replacement row's budgets equal its v1 counterpart field-for-field,
    except the one authorized `claude-code` wall-clock raise 180000 -> 600000."""
    v1_trial_id = V1_TRIAL_FOR[trial_id]
    source = next((row for row in baseline_catalog.get("trials", []) if row.get("trial_id") == v1_trial_id), None)
    if source is None:
        raise Invalid(f"{trial_id}: v1 baseline row unavailable: {v1_trial_id}")
    budgets, frozen = task.get("budgets"), source.get("budgets")
    if not isinstance(budgets, dict) or not isinstance(frozen, dict) or set(budgets) != set(frozen):
        raise Invalid(f"{trial_id}: budget key set diverges from v1")
    for key, value in frozen.items():
        raised = key == "timeout_ms" and task.get("provider") == RAISED_PROVIDER and value == BASE_TIMEOUT_MS
        expected = RAISED_TIMEOUT_MS if raised else value
        if budgets[key] != expected:
            raise Invalid(f"{trial_id}: budget {key} outside the D122 grant: {budgets[key]} != {expected}")


def main() -> int:
    here = Path(__file__).resolve().parent  # .../artifacts/P5
    plan = here.parent.parent  # .../plans/2026.08.03-ARTIFEX-SUPERVISOR
    repo_default = plan.parent.parent  # repository root

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_default)
    parser.add_argument("--results", type=Path, default=here / "repository-pilot-results-v2.json")
    parser.add_argument("--admission-index", type=Path, default=here / "trial-admission-index-v2-p5.2-retry.json")
    parser.add_argument("--baseline-catalog", type=Path, default=here / "trial-catalog-v1.json")
    parser.add_argument("--generation", type=Path, default=here / "business-successor-generation-v1.json")
    parser.add_argument("--assurance", type=Path, default=here / "business-successor-assurance-v1.json")
    parser.add_argument("--ledger", type=Path, default=here / "g2b-generation-ledger-v1.json")
    args = parser.parse_args()

    try:
        repo = args.repo_root.resolve()

        results = load(args.results)
        if results.get("schema_version") != "artifex-repository-pilot-results-v1":
            raise Invalid(f"unexpected results schema_version: {results.get('schema_version')!r}")
        if results.get("main_tree_delta") is not False:
            raise Invalid("main_tree_delta must be exactly false")

        slices = results.get("slices")
        if not isinstance(slices, list) or len(slices) != 3:
            found = len(slices) if isinstance(slices, list) else type(slices).__name__
            raise Invalid(f"expected exactly 3 slices, found {found}")
        trial_ids = tuple(row.get("trial_id") if isinstance(row, dict) else None for row in slices)
        if trial_ids != ORDER:
            raise Invalid(f"slices are not the three D122 replacement rows in catalog order: {trial_ids} != {ORDER}")

        # G2/G2B must be re-derived live, never trusted from the results file alone.
        generation = load(args.generation)
        assurance = load(args.assurance)
        live_g2 = generation.get("predecessor", {}).get("digest")
        live_g2b = generation.get("generation_hash")
        if not live_g2 or not live_g2b:
            raise Invalid("live generation manifest missing predecessor digest or generation_hash")
        if assurance.get("g2_predecessor") != live_g2 or assurance.get("g2b_generation_hash") != live_g2b:
            raise Invalid("live generation/assurance manifests are internally inconsistent")
        if assurance.get("d105_used_rows") != 0:
            raise Invalid(f"D105 usage is nonzero: {assurance.get('d105_used_rows')!r}")
        if results.get("g2_predecessor") != live_g2:
            raise Invalid(f"results g2_predecessor stale: {results.get('g2_predecessor')!r} != live {live_g2!r}")

        # D130/repair (3a): a recorded g2b_generation_hash is valid when it is a
        # member of the append-only ledger AND the ledger's last entry equals the
        # live generation — a pilot measured at an earlier legitimate freeze stays
        # valid without its evidence being edited. A hash absent from the ledger
        # is still the real regression case.
        ledger = load(args.ledger)
        if ledger.get("schema_version") != "artifex-g2b-generation-ledger-v1":
            raise Invalid(f"unexpected ledger schema_version: {ledger.get('schema_version')!r}")
        ledger_entries = ledger.get("entries")
        if not isinstance(ledger_entries, list) or not ledger_entries:
            raise Invalid("ledger has no entries")
        ledger_hashes = [entry.get("generation_hash") for entry in ledger_entries]
        if ledger_hashes[-1] != live_g2b:
            raise Invalid(f"ledger last entry does not equal live generation_hash: {ledger_hashes[-1]!r} != {live_g2b!r}")
        recorded_g2b = results.get("g2b_generation_hash")
        if recorded_g2b not in ledger_hashes:
            raise Invalid(f"results g2b_generation_hash not a ledger member: {recorded_g2b!r}")

        # The Claude Code pin: recorded once for the whole batch, never bumped past 2.1.222.
        probe = results.get("version_probe")
        if not isinstance(probe, dict) or set(probe) != {"codex", "claude-code"}:
            raise Invalid("version_probe missing or malformed")
        for provider, expected in EXPECTED_VERSION.items():
            row = probe.get(provider, {})
            if row.get("version") != expected:
                raise Invalid(f"{provider} version_probe drift: expected {expected!r}, recorded {row.get('version')!r}")
            binary = row.get("binary")
            if not isinstance(binary, str) or not Path(binary).is_absolute():
                raise Invalid(f"{provider} version_probe binary is not an absolute path: {binary!r}")
        claude_binary = probe["claude-code"]["binary"]
        if "2.1.222" not in claude_binary:
            raise Invalid(f"claude-code binary does not name the pinned 2.1.222 build: {claude_binary!r}")

        index = load(args.admission_index)
        index_rows = {row.get("trial_id"): row for row in index.get("admissions", []) if isinstance(row, dict)}
        baseline_catalog = load(args.baseline_catalog)

        for trial_id, row in zip(ORDER, slices):
            if row.get("provider") != EXPECTED_PROVIDER[trial_id]:
                raise Invalid(f"{trial_id}: provider mismatch, got {row.get('provider')!r}")
            if row.get("fresh_process") is not True:
                raise Invalid(f"{trial_id}: fresh_process is not true")
            observation = row.get("observation", {})
            if observation.get("process_count") != 1:
                raise Invalid(f"{trial_id}: process_count != 1 (got {observation.get('process_count')!r})")

            index_row = index_rows.get(trial_id)
            if index_row is None:
                raise Invalid(f"{trial_id}: not present in the D122 admission index")
            admission = check_admission(index_row, plan)
            task = admission["task"]
            if task.get("parent_item_id") != "P5.2":
                raise Invalid(f"{trial_id}: admission does not belong to P5.2")
            if row.get("base_commit") != task.get("base_commit"):
                raise Invalid(f"{trial_id}: base_commit mismatch")
            if row.get("admission_hash") != admission.get("admission_hash"):
                raise Invalid(f"{trial_id}: admission_hash mismatch")
            check_budget_raise(trial_id, task, baseline_catalog)

            declared_files = sorted(task.get("files", []))
            changed = row.get("changed_paths")
            gap = row.get("evidence_gap")
            if changed is None:
                if not isinstance(gap, str) or not gap:
                    raise Invalid(f"{trial_id}: changed_paths is null without a recorded evidence_gap reason")
                if row.get("accepted") is not False:
                    raise Invalid(f"{trial_id}: an evidence-gap slice must not be recorded as accepted")
            elif not isinstance(changed, list) or (row.get("accepted") is True and changed != declared_files):
                raise Invalid(f"{trial_id}: accepted slice's changed_paths not scope-only: {changed} != {declared_files}")
            if row.get("accepted") is True and row.get("rollback") is not True:
                raise Invalid(f"{trial_id}: accepted without a proven rollback")
            if row.get("accepted") is True and row.get("dispatch_business", {}).get("intent_written") is not True:
                raise Invalid(f"{trial_id}: accepted without intent_written")

        # Independent re-derivation of "zero main_tree_delta": don't just trust the flag.
        status = git(repo, "status", "--porcelain=v1", "--", "packages/artifex")
        if status.returncode != 0:
            raise Invalid(f"git status failed: {status.stderr.decode('utf-8', 'replace')}")
        if status.stdout.strip():
            raise Invalid(f"packages/artifex is not clean in the main tree: {status.stdout.decode('utf-8', 'replace')!r}")
        gen_rel = f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json"
        assur_rel = f"plans/{PLAN_ID}/artifacts/P5/business-successor-assurance-v1.json"
        v1_results_rel = f"plans/{PLAN_ID}/artifacts/P5/repository-pilot-results-v1.json"
        diff = git(repo, "diff", "--exit-code", "--", "packages/artifex", gen_rel, assur_rel, v1_results_rel)
        if diff.returncode != 0:
            raise Invalid(f"unstaged diff on the guarded G2B/v1-evidence surface: {diff.stdout.decode('utf-8', 'replace')}")

        # D130/repair (3b): the exit code distinguishes "evidence is structurally
        # intact" from "evidence shows acceptance". Every failure class above
        # (schema, admission binding, version pin, budget, staleness, mutated
        # bytes, unclean tree) still returns 1. Evidence intact with an honest
        # partial/zero-acceptance report returns 2, not 1: P5.2's `0/3` is
        # immutable recorded evidence (its three D122 admissions are one-shot and
        # spent), so this is this item's own permanent green for this gate.
        accepted_count = sum(1 for row in slices if row.get("accepted") is True)
        not_accepted = [row["trial_id"] for row in slices if row.get("accepted") is not True]
        if not_accepted:
            print(f"P5.2 D122 repository-pilot validator: FAIL: not accepted: {not_accepted} "
                  f"({accepted_count}/3 accepted) — honest report, not a validator defect", file=sys.stderr)
            return 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"P5.2 repository-pilot validator: FAIL: {exc}", file=sys.stderr)
        return 1
    print("P5.2 D122 repository-pilot validator: OK "
          "(3/3 catalog-ordered D122 slices; fresh, scope-only, accepted, rolled back; G2B live; main tree clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
