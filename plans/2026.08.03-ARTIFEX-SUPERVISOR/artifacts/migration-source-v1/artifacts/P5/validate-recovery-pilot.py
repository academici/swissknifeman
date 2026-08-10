#!/usr/bin/env python3
"""Independent P5.3 recovery-pilot-results validator.

Reads only already-written evidence; issues no provider process and mutates no
byte. Kept deliberately separate from ``run-recovery-pilot.py`` — it must not
import or trust that harness's own bookkeeping, only independently re-derive
and recheck it against the live G2B manifests, the D105 admission index and
Git.

Six catalogued trials, one is expected to carry a second (duplicate-refusal)
row — the validator asserts that shape exactly, not a bare count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
ORDER = ("p5.3-call-01-crash-after-intent", "p5.3-call-02-crash-after-observation",
          "p5.3-call-03-duplicate-dispatch", "p5.3-call-04-timeout",
          "p5.3-call-05-schema-refusal", "p5.3-call-06-third-state")
EXPECTED_VERSION = {"codex": "codex-cli 0.146.0", "claude-code": "2.1.222 (Claude Code)"}
EXPECTED_PROVIDER = {"p5.3-call-01-crash-after-intent": "codex", "p5.3-call-02-crash-after-observation": "claude-code",
                     "p5.3-call-03-duplicate-dispatch": "codex", "p5.3-call-04-timeout": "codex",
                     "p5.3-call-05-schema-refusal": "claude-code", "p5.3-call-06-third-state": "claude-code"}
REAL_CRASH_TRIALS = ("p5.3-call-01-crash-after-intent", "p5.3-call-02-crash-after-observation")
FAKE_BINARY_TRIALS = {"p5.3-call-04-timeout": "WALL_TIMEOUT", "p5.3-call-05-schema-refusal": "PROVIDER_PROTOCOL_UNKNOWN"}
OWNER_MARKER = "[OWNER-GRANT:G-OWNER-P5-BUSINESS]"


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


def check_admission_untouched(trial_id: str, admission_hash: str, plan: Path, index_rows: dict) -> dict:
    """Re-check the on-disk D105 admission fixture is byte-identical to the index and its
    usage/replay counters were never mutated by anything this pilot ran — the package persists
    no usage state at all, so this also proves the one-shot discipline was purely harness-side,
    exactly as it must be for the duplicate-refusal proof to mean anything."""
    row = index_rows.get(trial_id)
    if row is None:
        raise Invalid(f"{trial_id}: not present in the D105 admission index")
    admission_path = plan / row["path"]
    admission = load(admission_path)
    if digest(admission_path) != row.get("sha256"):
        raise Invalid(f"admission bytes mutated: {trial_id}")
    if admission.get("admission_hash") != admission_hash:
        raise Invalid(f"{trial_id}: results admission_hash does not match the on-disk admission")
    if admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}:
        raise Invalid(f"admission usage mutated: {trial_id}")
    replay = admission.get("replay", {})
    if replay.get("events") != [] or replay.get("used_slices") != 0:
        raise Invalid(f"admission replay mutated: {trial_id}")
    grant, task = admission.get("grant", {}), admission.get("task", {})
    if grant.get("owner_decision") != "D105" or grant.get("owner_marker") != OWNER_MARKER:
        raise Invalid(f"admission is not D105/{OWNER_MARKER}-bound: {trial_id}")
    if task.get("parent_item_id") != "P5.3" or task.get("purpose") != "business-trial":
        raise Invalid(f"{trial_id}: admission does not belong to P5.3 (G2/P3-smoke/probe reuse guard)")
    if grant.get("max_slices") != 1:
        raise Invalid(f"admission is not a one-slice grant: {trial_id}")
    return admission


def main() -> int:
    here = Path(__file__).resolve().parent  # .../artifacts/P5
    plan = here.parent.parent  # .../plans/2026.08.03-ARTIFEX-SUPERVISOR
    repo_default = plan.parent.parent  # repository root

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=repo_default)
    parser.add_argument("--results", type=Path, default=here / "recovery-pilot-results-v1.json")
    parser.add_argument("--admission-index", type=Path, default=here / "trial-admission-index-v1.json")
    parser.add_argument("--generation", type=Path, default=here / "business-successor-generation-v1.json")
    parser.add_argument("--assurance", type=Path, default=here / "business-successor-assurance-v1.json")
    parser.add_argument("--ledger", type=Path, default=here / "g2b-generation-ledger-v1.json")
    args = parser.parse_args()

    try:
        repo = args.repo_root.resolve()
        results = load(args.results)
        if results.get("schema_version") != "artifex-recovery-pilot-results-v1":
            raise Invalid(f"unexpected results schema_version: {results.get('schema_version')!r}")
        if results.get("main_tree_delta") is not False:
            raise Invalid("main_tree_delta must be exactly false")

        # Self-test: the crash-timing mechanism's own correctness proof, required before any
        # real trial and re-checked here rather than merely trusted from the results file.
        self_test = results.get("self_test")
        if not isinstance(self_test, dict):
            raise Invalid("self_test missing — crash mechanism was never validated before real trials")
        for key, flag in (("child_spawn_detection", "all_detected"), ("reap_window_detection", "all_detected"),
                          ("orphan_after_parent_kill", "all_orphaned")):
            block = self_test.get(key, {})
            if block.get("trials", 0) < 3 or block.get(flag) is not True:
                raise Invalid(f"self_test.{key} did not pass ({block!r})")

        # G2/G2B must be re-derived live, never trusted from the results file alone.
        generation, assurance = load(args.generation), load(args.assurance)
        live_g2, live_g2b = generation.get("predecessor", {}).get("digest"), generation.get("generation_hash")
        if not live_g2 or not live_g2b:
            raise Invalid("live generation manifest missing predecessor digest or generation_hash")
        if assurance.get("g2_predecessor") != live_g2 or assurance.get("g2b_generation_hash") != live_g2b:
            raise Invalid("live generation/assurance manifests are internally inconsistent")
        if results.get("g2_predecessor") != live_g2:
            raise Invalid(f"results g2_predecessor stale: {results.get('g2_predecessor')!r} != live {live_g2!r}")

        # D130/D133 repair (1): a recorded g2b_generation_hash is valid when it is a
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

        probe = results.get("version_probe")
        if not isinstance(probe, dict) or set(probe) != {"codex", "claude-code"}:
            raise Invalid("version_probe missing or malformed")
        for provider, expected in EXPECTED_VERSION.items():
            row = probe.get(provider, {})
            if row.get("version") != expected:
                raise Invalid(f"{provider} version_probe drift: expected {expected!r}, recorded {row.get('version')!r}")

        trials = results.get("trials")
        if not isinstance(trials, list) or len(trials) != 7:
            found = len(trials) if isinstance(trials, list) else type(trials).__name__
            raise Invalid(f"expected exactly 7 rows (6 catalogued + 1 duplicate-refusal), found {found}")
        real_rows = [row for row in trials if isinstance(row, dict) and not row.get("duplicate_refused")]
        dup_rows = [row for row in trials if isinstance(row, dict) and row.get("duplicate_refused")]
        real_ids = tuple(row.get("trial_id") for row in real_rows)
        if real_ids != ORDER:
            raise Invalid(f"real trials are not the six catalogued rows in order: {real_ids} != {ORDER}")
        if len(dup_rows) != 1 or dup_rows[0].get("trial_id") != "p5.3-call-03-duplicate-dispatch":
            raise Invalid("expected exactly one duplicate-refusal row, for call-03")
        if dup_rows[0].get("process_spawned") is not False or dup_rows[0].get("reason") != "SLICE_ALREADY_RUN":
            raise Invalid("duplicate-refusal row did not prove a pre-intent refusal with zero subprocess spawned")
        # The duplicate row must be positioned immediately after call-03's real row — proving the
        # second attempt was made (and refused) after the first, not interleaved elsewhere.
        call03_index = next(i for i, row in enumerate(trials) if row.get("trial_id") == "p5.3-call-03-duplicate-dispatch"
                            and not row.get("duplicate_refused"))
        if trials[call03_index + 1] is not dup_rows[0]:
            raise Invalid("duplicate-refusal row is not immediately adjacent to call-03's real dispatch")

        index = load(args.admission_index)
        index_rows = {row.get("trial_id"): row for row in index.get("admissions", []) if isinstance(row, dict)}

        for trial_id, row in zip(ORDER, real_rows):
            if row.get("provider") != EXPECTED_PROVIDER[trial_id]:
                raise Invalid(f"{trial_id}: provider mismatch, got {row.get('provider')!r}")
            admission_hash = row.get("admission_hash")
            if not admission_hash:
                raise Invalid(f"{trial_id}: missing admission_hash")
            check_admission_untouched(trial_id, admission_hash, plan, index_rows)

            if trial_id in REAL_CRASH_TRIALS:
                if row.get("crash_verified") is not True:
                    raise Invalid(f"{trial_id}: crash was not verified against a real process")
                outcome = row.get("reconcile", {}).get("outcome")
                if outcome not in ("postimage", "preimage", "rollback"):
                    raise Invalid(f"{trial_id}: crash trial did not reach a definitive reconcile outcome ({outcome!r})")
                if outcome != "preimage" and row.get("rollback") is not True:
                    raise Invalid(f"{trial_id}: non-preimage reconcile without a proven rollback")
            elif trial_id in FAKE_BINARY_TRIALS:
                if row.get("fake_binary") is not True:
                    raise Invalid(f"{trial_id}: must use the deterministic fake-binary path")
                if row.get("reason_code") != FAKE_BINARY_TRIALS[trial_id]:
                    raise Invalid(f"{trial_id}: expected reason_code {FAKE_BINARY_TRIALS[trial_id]!r}, "
                                  f"got {row.get('reason_code')!r}")
                if row.get("accepted") is not False or row.get("rollback") is not True:
                    raise Invalid(f"{trial_id}: fake-binary trial must refuse and roll back cleanly")
            elif trial_id == "p5.3-call-03-duplicate-dispatch":
                if row.get("crashed") is not False or row.get("process_count") != 1:
                    raise Invalid(f"{trial_id}: real half must be an uninstrumented single-process dispatch")
            elif trial_id == "p5.3-call-06-third-state":
                if row.get("crash_verified") is not True or row.get("child_pid_discarded") is not True:
                    raise Invalid(f"{trial_id}: must prove a real crash with deliberately discarded PID tracking")
                reconcile = row.get("reconcile", {})
                if reconcile.get("outcome") != "owner_unknown" or reconcile.get("reason") != "PID_TRACKING_DISCARDED_BY_DESIGN":
                    raise Invalid(f"{trial_id}: must reconcile to owner_unknown by design, not a guessed verdict")
                if "accepted" in row or "rollback" in row:
                    raise Invalid(f"{trial_id}: zero further mutation — must not record accepted/rollback")
                if not isinstance(row.get("preserved_worktree"), str) or not row["preserved_worktree"]:
                    raise Invalid(f"{trial_id}: must record the preserved worktree path for owner inspection")

        # Independent re-derivation of "zero main_tree_delta": don't just trust the flag.
        status = git(repo, "status", "--porcelain=v1", "--", "packages/artifex")
        if status.returncode != 0:
            raise Invalid(f"git status failed: {status.stderr.decode('utf-8', 'replace')}")
        if status.stdout.strip():
            raise Invalid(f"packages/artifex is not clean in the main tree: {status.stdout.decode('utf-8', 'replace')!r}")
        gen_rel = f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json"
        assur_rel = f"plans/{PLAN_ID}/artifacts/P5/business-successor-assurance-v1.json"
        diff = git(repo, "diff", "--exit-code", "--", "packages/artifex", gen_rel, assur_rel)
        if diff.returncode != 0:
            raise Invalid(f"unstaged diff on the guarded G2B surface: {diff.stdout.decode('utf-8', 'replace')}")
    except (OSError, ValueError, KeyError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        print(f"P5.3 recovery-pilot validator: FAIL: {exc}", file=sys.stderr)
        return 1
    print("P5.3 recovery-pilot validator: OK "
          "(6/6 catalogued trials + 1 pre-intent duplicate refusal; self-test passed; "
          "crash trials definitively reconciled; call-06 correctly left owner_unknown; "
          "G2B live; main tree clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
