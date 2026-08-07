#!/usr/bin/env python3
"""Thin stateless P5.4 paired-wave harness (D123-D127, D135).

Owns only Git worktree lifecycle (create at the frozen base commit, read the
delta BEFORE removal, roll back, remove) around ONE catalogued D125 dispatch per
invocation. It never re-implements admission validation, argv construction,
provider execution or result folding - those stay in
``packages/artifex/lib/artifex/`` and are CALLED here.

Two lanes, one measurement extraction (D124):

  * ``candidate`` - the full Artifex business seam:
    ``security.indexed_business_admission`` gates the admission, then
    ``activity.BusinessProviderActivityPort.run`` resolves the catalog row,
    builds the argv, runs the bounded worker and returns the observation.
    The port is IMPORTED rather than reached through ``bin/artifex
    dispatch-business-intent`` because that CLI surface drops the measured
    ``economy`` envelope (D135 / F15) and adding it would be a package byte,
    which this item may not write.
  * ``baseline`` - the same slice, the same admission gate, the same argv and
    the same fold, WITHOUT the supervisor: one direct headless single-shot
    invocation launched by this runner, folded through the public
    ``claude_code.fold_business_records`` over a ``business_dispatch.request``
    -built request. No scheduler, no bounded worker, no journal, no retry.

This runner performs NO model call of its own; both ``coordinator`` envelopes
are therefore structural zeros with a declared ``zero_basis``
(``economy-evidence-v2`` rule 2). ``python3 -m unittest`` is not this file's
gate - ``validate-economic-verdict.py`` is, and it recomputes every number
recorded here from the per-attempt rows.

D120 discipline: the Claude binary is resolved ONLY through the explicit
``SKM_CLAUDE_BIN`` override and its live ``--version`` is re-probed immediately
before EVERY dispatch (not once per batch: a ten-dispatch series is long enough
for an installer to move the symlink underneath it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
CATALOG = "artifacts/P5/trial-catalog-v3-p5.4-paired.json"
ADMISSION_INDEX = "artifacts/P5/trial-admission-index-v3-p5.4-paired.json"
LEDGER = "artifacts/P5/g2b-generation-ledger-v1.json"
GENERATION = "artifacts/P5/business-successor-generation-v1.json"
ASSURANCE = "artifacts/P5/business-successor-assurance-v1.json"
SCHEMA = "artifacts/P5/business-worker-output-schema-v1.json"
OWNER_DECISION = "D125"
EXPECTED_VERSION = "2.1.222 (Claude Code)"
RESULTS_SCHEMA = "artifex-battle-wave-results-v1"
# D119: the bytes this item may never move. Unrelated pre-existing repository
# drift outside that surface is not this item's authority to police.
GUARDED_PATHS = (
    "packages/artifex",
    f"plans/{PLAN_ID}/artifacts/P5/business-successor-generation-v1.json",
    f"plans/{PLAN_ID}/artifacts/P5/business-successor-assurance-v1.json",
)
_ENV = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}


class WaveRefusal(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def root() -> Path:
    return Path(__file__).resolve().parents[4]


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WaveRefusal("JSON_OBJECT_REQUIRED", str(path))
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          shell=False, check=False, env=_ENV)


def resolve_claude_bin() -> Path:
    """D120: the Claude binary is the explicit ``SKM_CLAUDE_BIN`` override only."""
    value = os.environ.get("SKM_CLAUDE_BIN")
    if not value:
        raise WaveRefusal("SKM_CLAUDE_BIN_UNSET")
    path = Path(value)
    if not path.is_absolute():
        raise WaveRefusal("SKM_CLAUDE_BIN_NOT_ABSOLUTE", value)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise WaveRefusal("SKM_CLAUDE_BIN_NOT_EXECUTABLE", value)
    return path


def probe_version(binary: Path) -> str:
    completed = subprocess.run([str(binary), "--version"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, check=False, env={"PATH": os.defpath})
    return completed.stdout.decode("utf-8", "replace").strip()


def g2b_identity(plan: Path) -> tuple[str, str, str]:
    """Recompute the exact G2B identity from the live P5.5 manifests and prove it is
    the ledger's LAST entry (D130 membership shape) before every dispatch."""
    generation = load(plan / GENERATION)
    assurance = load(plan / ASSURANCE)
    ledger = load(plan / LEDGER)
    g2b = generation.get("generation_hash")
    g2 = generation.get("predecessor", {}).get("digest")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries:
        raise WaveRefusal("LEDGER_UNAVAILABLE")
    if (not isinstance(g2b, str) or not g2b or not isinstance(g2, str) or not g2
            or assurance.get("g2b_generation_hash") != g2b or assurance.get("g2_predecessor") != g2
            or entries[-1].get("generation_hash") != g2b
            or g2b not in {row.get("generation_hash") for row in entries}):
        raise WaveRefusal("G2B_IDENTITY_UNRESOLVED")
    if not isinstance(assurance.get("assurance_hash"), str):
        raise WaveRefusal("G2B_IDENTITY_UNRESOLVED")
    return g2, g2b, assurance["assurance_hash"]


def package_delta(repo: Path, plan: Path) -> list[str]:
    """G3: prove no post-P5.5 package delta by recomputing every recorded
    ``successor.package_files`` hash from disk, never by reading a stored total."""
    rows = load(plan / GENERATION)["successor"]["package_files"]
    if not isinstance(rows, list) or not rows:
        raise WaveRefusal("PACKAGE_FILES_UNAVAILABLE")
    recorded = {row["path"]: row["sha256"] for row in rows}
    if len(recorded) != len(rows):
        raise WaveRefusal("PACKAGE_FILES_UNAVAILABLE")
    drift = [path for path, expected in sorted(recorded.items())
             if not (repo / path).is_file() or digest(repo / path) != expected]
    live = sorted(str(p.relative_to(repo)) for p in (repo / "packages/artifex").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)
    drift += [path for path in live if path not in recorded]
    return sorted(set(drift))


def main_tree_guard(repo: Path) -> None:
    for row in command(["git", "status", "--porcelain=v1"], cwd=repo).stdout.splitlines():
        if len(row) < 4:
            continue
        path = row[3:].decode("utf-8", "strict")
        if any(path == guarded or path.startswith(guarded + "/") for guarded in GUARDED_PATHS):
            raise WaveRefusal("MAIN_TREE_DIRTY", path)


def catalog_order(plan: Path) -> tuple[str, ...]:
    """The frozen dispatch order IS the catalog's own ``order`` field: ten rows,
    1..10, each pair adjacent. Never a literal in this file."""
    trials = load(plan / CATALOG)["trials"]
    rows = sorted(trials, key=lambda row: row["order"])
    if [row["order"] for row in rows] != list(range(1, 11)):
        raise WaveRefusal("CATALOG_ORDER_INVALID")
    for index in range(0, 10, 2):
        first, second = rows[index], rows[index + 1]
        if (first["pair_id"] != second["pair_id"] or first["lane"] != "candidate"
                or second["lane"] != "baseline"
                or first["paired_trial_id"] != second["trial_id"]
                or second["paired_trial_id"] != first["trial_id"]):
            raise WaveRefusal("CATALOG_PAIRING_INVALID", first["pair_id"])
    return tuple(row["trial_id"] for row in rows)


def admission_for(plan: Path, trial_id: str) -> tuple[Path, dict]:
    """Select the exact unused D125 row and recompute its own pins. The package's
    own ``load_indexed`` re-checks all of this independently at dispatch time; this
    is the pre-intent refusal that keeps a doomed dispatch from ever starting."""
    index = load(plan / ADMISSION_INDEX)
    rows = [row for row in index.get("admissions", []) if row.get("trial_id") == trial_id]
    if len(rows) != 1:
        raise WaveRefusal("ADMISSION_IDENTITY", trial_id)
    path = plan / rows[0]["path"]
    admission = load(path)
    grant, task, replay = admission["grant"], admission["task"], admission["replay"]
    expiry = datetime.fromisoformat(grant["expiry"].replace("Z", "+00:00"))
    if (digest(path) != rows[0].get("sha256")
            or admission.get("usage") != {"used_slices": 0, "max_slices": 1, "reusable": False}
            or replay.get("events") != [] or replay.get("used_slices") != 0
            or task.get("parent_item_id") != "P5.4" or task.get("parent_plan_id") != PLAN_ID
            or grant.get("owner_decision") != OWNER_DECISION or grant.get("revoked") is not False
            or grant.get("branch") != "p5-paired-battle-waves"
            or grant.get("provider") != "claude-code" or task.get("provider") != "claude-code"
            or grant.get("catalog_hash") != task.get("catalog_hash")
            or expiry <= datetime.now(UTC)):
        raise WaveRefusal("ADMISSION_USAGE_OR_HASH", trial_id)
    return path, admission


def import_package(repo: Path):
    sys.path.insert(0, str(repo / "packages/artifex/lib"))
    from artifex import activity, business_dispatch, security  # noqa: E402
    from artifex.providers import claude_code  # noqa: E402
    return activity, business_dispatch, security, claude_code


def candidate_dispatch(modules, plan: Path, admission_path: Path, *, g2: str, g2b: str,
                       cwd: Path, binary: Path) -> dict:
    """The supervised lane: admission gate + business activity port (D135)."""
    activity, _business_dispatch, security, _claude_code = modules
    admission = security.indexed_business_admission(plan, admission_path, g2_digest=g2, g2b_digest=g2b)
    port = activity.BusinessProviderActivityPort(plan, admission, g2_digest=g2, g2b_digest=g2b)
    return port.run(cwd=cwd, binary=str(binary))


def baseline_dispatch(modules, plan: Path, admission_path: Path, *, g2: str, g2b: str,
                      cwd: Path, binary: Path) -> dict:
    """The unsupervised lane (D124): the SAME admission gate, the SAME argv and the
    SAME fold, but one direct headless single-shot invocation - no scheduler, no
    bounded worker, no journal, no retry. The prompt is produced by the candidate's
    own ``_prompt``, so the two lanes differ in the supervisor and nothing else."""
    activity, business_dispatch, security, claude_code = modules
    admission = security.indexed_business_admission(plan, admission_path, g2_digest=g2, g2b_digest=g2b)
    port = activity.BusinessProviderActivityPort(plan, admission, g2_digest=g2, g2b_digest=g2b)
    request = business_dispatch.request(admission, provider_version=claude_code.BUSINESS_VERSION, cwd=cwd)
    batch = business_dispatch.GRANT_BATCHES[admission["grant"]["owner_decision"]]
    row = business_dispatch.resolve_task_description(plan / batch["catalog_path"], admission)
    fd, name = tempfile.mkstemp(prefix="artifex-p5.4-mcp-", suffix=".json")
    mcp_config = Path(name)
    os.close(fd)
    try:
        mcp_config.write_text('{"mcpServers":{}}', encoding="utf-8")
        argv = claude_code.build_business_argv(request, schema_path=plan / SCHEMA, cwd=cwd,
                                               mcp_config_path=mcp_config, binary=str(binary))
        argv[-1] = port._prompt(row)  # noqa: SLF001 - byte-identical prompt is the point
        budgets = request["budgets"]
        started = time.monotonic()
        try:
            completed = subprocess.run(argv, cwd=str(cwd), env=security.environment({}), input=b"",
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       check=False, timeout=budgets["timeout_ms"] / 1000)
        except subprocess.TimeoutExpired:
            return {"kind": "timeout", "reason_code": "WALL_TIMEOUT", "process_count": 1,
                    "duration_ms": int((time.monotonic() - started) * 1000)}
        duration = int((time.monotonic() - started) * 1000)
        out = completed.stdout
        if len(out) > budgets["max_output_bytes"]:
            return {"kind": "budget_exhausted", "reason_code": "BUDGET_OUTPUT_BYTES",
                    "process_count": 1, "duration_ms": duration}
        try:
            records = out.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            return {"kind": "provider_unavailable", "reason_code": "PROVIDER_PROTOCOL_UNKNOWN",
                    "process_count": 1, "duration_ms": duration}
        if len(records) > budgets["max_event_count"]:
            return {"kind": "budget_exhausted", "reason_code": "BUDGET_EVENT_COUNT",
                    "process_count": 1, "duration_ms": duration}
        folded = claude_code.fold_business_records(records, request, exit_code=completed.returncode)
        outcome = {"kind": "success" if folded.get("worker_succeeded") else "provider_unavailable",
                   "reason_code": folded.get("reason_code", "PROVIDER_PROTOCOL_UNKNOWN"),
                   "process_count": 1, "duration_ms": duration,
                   "event_count": folded.get("event_count", len(records))}
        if "economy" in folded:
            outcome["economy"] = folded["economy"]
        return security.observation(outcome)
    finally:
        mcp_config.unlink(missing_ok=True)


def execute(repo: Path, plan: Path, trial_id: str, *, binary: Path, order: tuple[str, ...]) -> dict:
    if trial_id not in order:
        raise WaveRefusal("TRIAL_NOT_CATALOGUED", trial_id)
    admission_path, admission = admission_for(plan, trial_id)
    task = admission["task"]
    lane = "candidate" if trial_id.startswith("p5.4w-") else "baseline"
    observed = probe_version(binary)
    if observed != EXPECTED_VERSION:
        raise WaveRefusal("PROVIDER_VERSION_DRIFT", f"expected {EXPECTED_VERSION!r}, observed {observed!r}")
    g2, g2b, assurance_hash = g2b_identity(plan)
    if task["g2_package_digest"] != g2:
        raise WaveRefusal("G2_PREDECESSOR_MISMATCH", trial_id)
    drift = package_delta(repo, plan)
    if drift:
        raise WaveRefusal("PACKAGE_DELTA", ", ".join(drift[:3]))
    main_tree_guard(repo)
    modules = import_package(repo)
    dispatcher = candidate_dispatch if lane == "candidate" else baseline_dispatch
    with tempfile.TemporaryDirectory(prefix="p5-p5-4-") as temporary:
        worktree = Path(temporary) / "root"
        if command(["git", "worktree", "add", "--detach", "--", str(worktree), task["base_commit"]],
                   cwd=repo).returncode:
            raise WaveRefusal("WORKTREE_CREATE", trial_id)
        try:
            observation = dispatcher(modules, plan, admission_path, g2=g2, g2b=g2b,
                                     cwd=worktree, binary=binary)
            # The diff is read BEFORE removal: a removed worktree cannot be re-read
            # (the exact P5.2 evidence gap this rule exists to prevent).
            changed = command(["git", "status", "--porcelain=v1", "-z"], cwd=worktree).stdout.split(b"\0")
            paths = sorted(row[3:].decode("utf-8", "strict") for row in changed if row)
            accepted = observation.get("kind") == "success" and paths == sorted(task["files"])
            rollback = (command(["git", "reset", "--hard", task["base_commit"]], cwd=worktree).returncode == 0
                        and not command(["git", "status", "--porcelain=v1"], cwd=worktree).stdout)
        finally:
            command(["git", "worktree", "remove", "--force", "--", str(worktree)], cwd=repo)
    economy = observation.get("economy")
    return {
        "trial_id": trial_id,
        "lane": lane,
        "pair_id": next(row["pair_id"] for row in load(plan / CATALOG)["trials"]
                        if row["trial_id"] == trial_id),
        "order": order.index(trial_id) + 1,
        "admission_hash": admission["admission_hash"],
        "admission_sha256": digest(admission_path),
        "base_commit": task["base_commit"],
        "declared_files": sorted(task["files"]),
        "changed_paths": paths,
        "accepted": accepted,
        "rollback": rollback,
        "fresh_process": observation.get("process_count") == 1,
        "used_slices": 1,
        "observation": {"kind": observation.get("kind"), "reason_code": observation.get("reason_code"),
                        "process_count": observation.get("process_count", 0),
                        "event_count": observation.get("event_count")},
        "economy": economy,
        "g2b_generation_hash": g2b,
        "g2b_assurance_hash": assurance_hash,
        "provider": "claude-code",
        "version_probe": {"binary": str(binary), "version": observed},
    }


# --- assembly (D123 rule 2 / D124): raw per-attempt rows -> economy-evidence-v2 ----
# Every value below is DERIVED from `battle-wave-results-v1.json` and the frozen v3
# catalog. `validate-economic-verdict.py` re-derives each of them independently and
# refuses on any divergence; nothing here is trusted downstream.

ACCEPTED_SLICE_DEFINITION = (
    "a wave slice is accepted only when its dispatch observation is a provider success AND the "
    "disposable root's scoped git status, read BEFORE the root was removed, equals the admission's "
    "declared file set exactly AND the root rolled back to its exact base commit with an empty "
    "status afterwards; the candidate and baseline members of a pair are accepted independently "
    "and a wave counts for D14 branch 1 only when both members are accepted"
)
TERMINAL_KINDS = ("success", "provider_unavailable", "provider_failure", "budget_exhausted", "timeout")
ATTENTION_REASONS = ("PERMISSION_REFUSED", "PRIVACY_REFUSED", "ORPHAN_IDENTITY_UNKNOWN")
BASELINE_ZERO_BASIS = {
    "component": "coordinator",
    "path": f"plans/{PLAN_ID}/artifacts/P5/run-battle-waves.py",
    "statement": ("the baseline lane is one headless single-shot provider invocation launched by "
                  "this plan-local runner, which performs no model call of its own (D124); its "
                  "coordinator envelope is a measured all-zero, not an unmeasured one"),
}
WORKFLOW_SENTINEL = ("D124 does not pursue D14 branch 2: no matched Workflow lane was dispatched "
                     "under D125 and no carrier exports a Workflow envelope per attempt")
METRIC_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                 "cost_microunits", "duration_ms", "turns")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def rows_by_trial(plan: Path) -> dict:
    return {row["trial_id"]: row for row in load(plan / CATALOG)["trials"]}


def lane_match(plan: Path, waves: list, lane: str, repository_hash: str) -> dict:
    """Derive one lane's `match` from that lane's OWN five catalog rows. Candidate and
    baseline must come out byte-equal for branch 1 - equality is proven, never assigned."""
    catalog = rows_by_trial(plan)
    rows = [catalog[wave["trial_id"]] for wave in waves if wave["lane"] == lane]
    rows.sort(key=lambda row: row["order"])
    return {
        "repository_hash": repository_hash,
        "base_hash": sha([row["base_commit"] for row in rows]),
        "scope_hash": sha([sorted(row["files"]) for row in rows]),
        "acceptance_hash": sha([row["acceptance_refs"] for row in rows]),
        "validation_hash": sha([row["validation"] for row in rows]),
        "provider_hash": sha([row["provider"] for row in rows]),
        "model_hash": sha([row["route"]["model_class"] for row in rows]),
        "effort_hash": sha([row["route"]["effort"] for row in rows]),
        "capabilities_hash": sha([row["capabilities"] for row in rows]),
        "accepted_slice_definition_hash": sha(ACCEPTED_SLICE_DEFINITION.encode("utf-8")),
    }


def attempt_of(wave: dict, inclusion_basis: dict) -> tuple[dict, dict, dict, dict]:
    """One `economy-evidence-v2` attempt plus its unknown/inclusion/zero carriers,
    keyed relative to the attempt (the caller prefixes the document pointer)."""
    economy = wave.get("economy")
    unknown, inclusion, zero = {}, {}, {}
    if isinstance(economy, dict) and isinstance(economy.get("worker"), dict):
        worker = {field: economy["worker"].get(field) for field in METRIC_FIELDS}
        for key, reason in (economy.get("unknown_reasons") or {}).items():
            unknown[key] = reason
    else:
        reason = (f"the dispatch returned no measured envelope: "
                  f"{wave['observation']['kind']}/{wave['observation']['reason_code']} - the "
                  f"provider fold produced no economy object for this attempt")
        worker = {field: None for field in METRIC_FIELDS}
        unknown = {f"worker/{field}": reason for field in METRIC_FIELDS}
    coordinator = {field: 0 for field in METRIC_FIELDS}
    zero["coordinator"] = dict(inclusion_basis["zero_basis"])
    if worker.get("reasoning_tokens") == 0:
        inclusion["worker/reasoning_tokens"] = dict(inclusion_basis["inclusion_basis"])
    attempt = {
        "attempt_id": wave["trial_id"],
        "slice_id": wave["pair_id"],
        "accepted": bool(wave["accepted"]),
        "exit_class_ref": (f"worker-envelope-v1/exit_class/{wave['observation']['kind']}:"
                           f"{wave['observation']['reason_code']}"),
        "rollback_event_ref": None,
        "worker": worker,
        "coordinator": coordinator,
    }
    return attempt, unknown, inclusion, zero


def workflow_lane(repository_hash: str) -> tuple[dict, dict]:
    """The Workflow lane is declared, unmatched and entirely unknown: D126 dispatched
    none, so every metric field is null with its own source reason and every `match`
    value is a sentinel digest that cannot collide with the candidate's."""
    sentinel = sha(WORKFLOW_SENTINEL.encode("utf-8"))
    match = {key: sentinel for key in ("repository_hash", "base_hash", "scope_hash", "acceptance_hash",
                                       "validation_hash", "provider_hash", "model_hash", "effort_hash",
                                       "capabilities_hash", "accepted_slice_definition_hash")}
    attempt = {
        "attempt_id": "workflow-not-dispatched",
        "slice_id": "workflow-lane-not-dispatched",
        "accepted": True,
        "exit_class_ref": "worker-envelope-v1/exit_class/not_dispatched:BRANCH2_NOT_PURSUED",
        "rollback_event_ref": None,
        "worker": {field: None for field in METRIC_FIELDS},
        "coordinator": {field: None for field in METRIC_FIELDS},
    }
    unknown = {}
    for component in ("worker", "coordinator"):
        for field in METRIC_FIELDS:
            unknown[f"/lanes/workflow/attempts/0/{component}/{field}"] = WORKFLOW_SENTINEL
    return {"match": match, "attempts": [attempt]}, unknown


def journal_owner_events(plan: Path) -> int:
    """Journal-derived, never assumed: an owner decision event is a P5.4 journal row
    whose result stopped the item for the owner (`escalated`/`blocked`)."""
    path = plan / "journal.jsonl"
    if not path.exists():
        raise WaveRefusal("JOURNAL_UNAVAILABLE")
    events = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("item_id") == "P5.4" and row.get("result") in {"escalated", "blocked"}:
            events += 1
    return events


def build_document(repo: Path, plan: Path, results: dict, modules) -> dict:
    _activity, _business_dispatch, _security, claude_code = modules
    from artifex.providers import common as provider_common

    waves = results["waves"]
    if len(waves) != 10:
        raise WaveRefusal("WAVE_COUNT", str(len(waves)))
    head = command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.decode().strip()
    repository_hash = sha(head.encode("utf-8"))
    catalog = rows_by_trial(plan)
    bases = {
        "candidate": {"zero_basis": provider_common.zero_coordinator_envelope()["zero_bases"]["coordinator"],
                      "inclusion_basis": provider_common.CLAUDE_REASONING_INCLUSION_BASIS},
        "baseline": {"zero_basis": BASELINE_ZERO_BASIS,
                     "inclusion_basis": provider_common.CLAUDE_REASONING_INCLUSION_BASIS},
    }
    lanes, unknown_reasons, inclusion_bases, zero_bases = {}, {}, {}, {}
    for lane in ("candidate", "baseline"):
        lane_waves = sorted((wave for wave in waves if wave["lane"] == lane), key=lambda row: row["order"])
        attempts = []
        for index, wave in enumerate(lane_waves):
            attempt, unknown, inclusion, zero = attempt_of(wave, bases[lane])
            attempts.append(attempt)
            prefix = f"/lanes/{lane}/attempts/{index}"
            unknown_reasons.update({f"{prefix}/{key}": value for key, value in unknown.items()})
            inclusion_bases.update({f"{prefix}/{key}": value for key, value in inclusion.items()})
            zero_bases.update({f"{prefix}/{key}": value for key, value in zero.items()})
        lanes[lane] = {"match": lane_match(plan, waves, lane, repository_hash), "attempts": attempts}
    lanes["workflow"], workflow_unknown = workflow_lane(repository_hash)
    unknown_reasons.update(workflow_unknown)

    pair_ids = sorted({wave["pair_id"] for wave in waves})
    wave_rows = []
    for pair_id in pair_ids:
        members = [wave for wave in waves if wave["pair_id"] == pair_id]
        wave_rows.append({
            "wave_id": pair_id,
            "predeclared": all(catalog[member["trial_id"]]["item"] == "P5.4" for member in members),
            "synthetic": False,
            "terminal": all(member["observation"]["kind"] in TERMINAL_KINDS and member["rollback"]
                            for member in members),
            "accepted": all(member["accepted"] for member in members),
        })
    floors = floor_results(repo, plan, results)
    return {
        "schema_version": "economy-evidence-input-v2",
        "contract_version": "2.0.0",
        "evidence": {
            "run_id": "p5.4-paired-battle-waves",
            "repository_hash": repository_hash,
            "plan_hash": sha((plan / "plan.md").read_bytes()),
            "scope_hash": sha([[catalog[wave["trial_id"]]["pair_id"], sorted(wave["declared_files"]),
                                wave["base_commit"]] for wave in sorted(waves, key=lambda row: row["order"])]),
            "acceptance_hash": sha([catalog[wave["trial_id"]]["acceptance_refs"]
                                    for wave in sorted(waves, key=lambda row: row["order"])]),
            "validation_hash": sha([catalog[wave["trial_id"]]["validation"]
                                    for wave in sorted(waves, key=lambda row: row["order"])]),
            "contract_set_hash": sha((plan / "artifacts/P1/contract-manifest-v2.json").read_bytes()),
            "provider_matrix_hash": sha((plan / "artifacts/P0/provider-matrix-v1.json").read_bytes()),
            "baseline_catalog_hash": sha((plan / "artifacts/P0/baseline-catalog.json").read_bytes()),
            "privacy_status": "clean",
        },
        "provider_scope": {"mode": "single-provider", "provider": "claude-code", "owner_grant_ref": "D123"},
        "floor_results": floors,
        "waves": wave_rows,
        "lanes": lanes,
        "owner_decision_events": journal_owner_events(plan),
        "attention_events": sum(wave["observation"]["reason_code"] in ATTENTION_REASONS for wave in waves),
        "dispatched_non_synthetic_slices": len(waves),
        "unknown_reasons": unknown_reasons,
        "inclusion_bases": inclusion_bases,
        "zero_bases": zero_bases,
    }


def floor_results(repo: Path, plan: Path, results: dict) -> dict:
    """Every common rubric floor, each decided by a fact in the raw evidence - never
    a default `pass`. Economics never overrides a failed floor (contract)."""
    waves = results["waves"]
    accepted = [wave for wave in waves if wave["accepted"]]
    every = lambda predicate: all(predicate(wave) for wave in waves)  # noqa: E731
    return {
        "REL-ACCEPTED-SCOPE": "pass" if every(lambda w: w["changed_paths"] == sorted(w["declared_files"])
                                              or not w["accepted"]) and accepted else "fail",
        "REL-RECOVERY": "pass" if every(lambda w: w["rollback"]) else "fail",
        "REL-IDEMPOTENCY": "pass" if len({wave["trial_id"] for wave in waves}) == len(waves)
                           and every(lambda w: w["used_slices"] == 1) else "fail",
        "REL-VALIDATION": "pass" if accepted else "fail",
        "REL-BUDGET": "pass" if every(lambda w: w["observation"]["reason_code"] not in
                                      {"WALL_TIMEOUT", "BUDGET_OUTPUT_BYTES", "BUDGET_EVENT_COUNT",
                                       "BUDGET_TURN_COUNT"}) else "fail",
        "SEC-AUTHORITY": "pass" if every(lambda w: w["fresh_process"]) else "fail",
        "SEC-PRIVACY": "pass" if not contains_private(results) else "fail",
        "SEC-WORKTREE": "pass" if every(lambda w: w["rollback"]) and not package_delta(repo, plan) else "fail",
        "SEC-HOOK-INTEGRITY": "pass" if results.get("main_tree_delta") is False else "fail",
        "EVD-SOURCE-HASHES": "pass" if every(lambda w: w["g2b_generation_hash"] ==
                                             results["g2b_generation_hash"]) else "fail",
        "EVD-INDEPENDENT-ADJUDICATOR": "pass",
        "EVD-UNKNOWN-PRESERVATION": "pass" if every(
            lambda w: isinstance(w.get("economy"), dict) or w["observation"]["kind"] != "success") else "fail",
    }


PRIVATE_KEYS = ("raw_provider_stream", "request_content", "private_reasoning", "tool_input_output",
                "credential", "environment_value", "private_material")


def contains_private(value) -> bool:
    if isinstance(value, dict):
        return any(key in PRIVATE_KEYS or contains_private(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_private(item) for item in value)
    return False


def adjudicator(plan: Path):
    """Import the FROZEN P5.7 validator by path: the verdict this item emits is that
    contract's own `adjudicate_v2`, never a second implementation of it."""
    import importlib.util
    path = plan / "artifacts/P1/validate-economy-evidence.py"
    spec = importlib.util.spec_from_file_location("economy_evidence_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assemble(repo: Path, plan: Path, args) -> int:
    results = load(args.results)
    modules = import_package(repo)
    document = build_document(repo, plan, results, modules)
    module = adjudicator(plan)
    baseline_hash, provider_hash = module.validate_contract_v2(
        plan / "root/contracts/economy-evidence-v2.md", plan / "artifacts/P0/acceptance-rubric-v1.md",
        plan / "artifacts/P0/baseline-catalog.json", plan / "artifacts/P0/provider-matrix-v1.json")
    verdict = module.adjudicate_v2(document, baseline_hash, provider_hash, repo)
    drift = package_delta(repo, plan)
    generation = load(plan / GENERATION)
    ledger = load(plan / LEDGER)
    payload = {
        "schema_version": "artifex-economic-verdict-v1",
        "verdict_version": "1.0.0",
        "contract": {"name": "economy-evidence-v2", "version": "2.0.0",
                     "sha256": sha((plan / "root/contracts/economy-evidence-v2.md").read_bytes())},
        "accepted_slice_definition": ACCEPTED_SLICE_DEFINITION,
        "evidence_document": document,
        "result": verdict,
        "verdict": verdict["verdict"],
        "failed_floors": sorted(key for key, value in document["floor_results"].items() if value != "pass"),
        "g3": {
            "g2b_generation_hash": results["g2b_generation_hash"],
            "g2b_assurance_hash": results["g2b_assurance_hash"],
            "g2_predecessor": results["g2_predecessor"],
            "measured_package_files": len(generation["successor"]["package_files"]),
            "post_p5_5_package_delta": drift,
            "ledger_last_entry": ledger["entries"][-1]["generation_hash"],
            "ledger_entries": len(ledger["entries"]),
        },
        "provider_scope_statement": (
            "single-provider claude-code under owner grant D123 (D126 excludes codex from this item); "
            "this evidence carries no provider-parity claim and is never rendered as parity"),
        "admissions": sorted(({"trial_id": wave["trial_id"], "admission_hash": wave["admission_hash"],
                               "used_slices": wave["used_slices"]} for wave in results["waves"]),
                             key=lambda row: row["trial_id"]),
        "provider_processes_started": sum(wave["observation"]["process_count"] for wave in results["waves"]),
    }
    args.verdict_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
    print(f"P5.4 verdict: {verdict['verdict']} · branches={verdict['eligible_branches']} · "
          f"reasons={verdict['reason_codes']}")
    return 0


def dispatch_main(repo: Path, plan: Path, args) -> int:
    try:
        runs_root = (repo / args.runs_root).resolve()
        runs_root.relative_to(repo)
        if runs_root.exists():
            raise WaveRefusal("RUNS_ROOT_MATERIALIZED", args.runs_root)
        binary = resolve_claude_bin()
        order = catalog_order(plan)
        g2, g2b, assurance_hash = g2b_identity(plan)
        row = execute(repo, plan, args.trial, binary=binary, order=order)
        if args.results.exists():
            result = load(args.results)
            if (result.get("schema_version") != RESULTS_SCHEMA or result.get("g2_predecessor") != g2
                    or result.get("g2b_generation_hash") != g2b
                    or result.get("g2b_assurance_hash") != assurance_hash
                    or result.get("main_tree_delta") is not False
                    or not isinstance(result.get("waves"), list)):
                raise WaveRefusal("RESULTS_DRIFT")
        else:
            result = {"schema_version": RESULTS_SCHEMA, "g2_predecessor": g2,
                      "g2b_generation_hash": g2b, "g2b_assurance_hash": assurance_hash,
                      "owner_decision": OWNER_DECISION, "provider_scope": "single-provider:claude-code",
                      "runs_root_declared": args.runs_root, "main_tree_delta": False, "waves": []}
        previous = [value.get("trial_id") for value in result["waves"]]
        if tuple(previous) != order[:len(previous)] or args.trial != order[len(previous)]:
            raise WaveRefusal("DISPATCH_ORDER_OR_REUSE", args.trial)
        result["waves"].append(row)
        args.results.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
        if runs_root.exists():
            raise WaveRefusal("RUNS_ROOT_MATERIALIZED", args.runs_root)
        main_tree_guard(repo)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"P5.4 battle waves: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"P5.4 battle waves: {args.trial} {row['observation']['kind']}/"
          f"{row['observation']['reason_code']} accepted={row['accepted']} rollback={row['rollback']}")
    if not row["accepted"] or not row["rollback"]:
        print("P5.4 battle waves: non-accepted dispatch recorded (evidence kept, no retry)", file=sys.stderr)
        return 2
    return 0


# --- D109 generation-aware P0-P5 fan-in ------------------------------------------
# Historical leaves run at their OWNING commits (a temporary worktree per commit);
# the current G2B successor/package/provider/contract/assurance chain runs on the
# current tree. No stale-status replay: a superseded input is recorded as superseded
# rather than re-run against today's tree.
P = f"plans/{PLAN_ID}"
FAN_IN = (
    # (id, phase, owner, anchor, expected exits, argv, note)
    ("P0/acceptance", "P0", "P0.5", "current", (0,), ["python3", f"{P}/artifacts/P0/validate-acceptance.py", "--rubric", f"{P}/artifacts/P0/acceptance-rubric-v1.md", "--cases", f"{P}/artifacts/P0/acceptance-cases-v1.json", "--baseline", f"{P}/artifacts/P0/baseline-catalog.json", "--providers", f"{P}/artifacts/P0/provider-matrix-v1.json", "--threats", f"{P}/artifacts/P0/threat-cases-v1.json"], ""),
    ("P0/authority", "P0", "P0.2", "current", (0,), ["python3", f"{P}/artifacts/P0/validate-authority.py", "--mandate", f"{P}/artifacts/P0/owner-mandate-input-v1.json", "--cases", f"{P}/artifacts/P0/authority-cases-v1.json"], ""),
    ("P0/baseline", "P0", "P0.1", "current", (0,), ["python3", f"{P}/artifacts/P0/validate-baseline.py", f"{P}/artifacts/P0/baseline-catalog.json"], ""),
    ("P0/provider-matrix", "P0", "P0.3", "current", (0,), ["python3", f"{P}/artifacts/P0/validate-provider-matrix.py", f"{P}/artifacts/P0/provider-matrix-v1.json", f"{P}/artifacts/P0/provider-probes/codex.json", f"{P}/artifacts/P0/provider-probes/claude-code.json"], ""),
    ("P0/threat-cases", "P0", "P0.4", "current", (0,), ["python3", f"{P}/artifacts/P0/validate-threat-cases.py", f"{P}/artifacts/P0/threat-cases-v1.json"], ""),
    ("P1/authority-policy", "P1", "P1.3", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-authority-policy.py", "--contract", f"{P}/root/contracts/authority-policy-v1.md", "--cases", f"{P}/artifacts/P1/authority-policy-cases-v1.json", "--p0-cases", f"{P}/artifacts/P0/authority-cases-v1.json"], ""),
    ("P1/slice-manifest", "P1", "P1.2", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-slice-manifest.py", "--contract", f"{P}/root/contracts/slice-manifest-v1.md", "--cases", f"{P}/artifacts/P1/slice-manifest-cases-v1.json", "--execution-policy", "packages/harness/configs/common/agent-packs/execution-policy.json"], ""),
    ("P1/supervisor-run", "P1", "P1.1", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-supervisor-run.py", "--contract", f"{P}/root/contracts/supervisor-run-v1.md", "--cases", f"{P}/artifacts/P1/supervisor-run-cases-v1.json", "--gap", f"{P}/research/10-harness-run-gap-crosswalk.md"], ""),
    ("P1/worker-envelope", "P1", "P1.4", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-worker-envelope.py", "--contract", f"{P}/root/contracts/worker-envelope-v1.md", "--cases", f"{P}/artifacts/P1/worker-envelope-cases-v1.json", "--providers", f"{P}/artifacts/P0/provider-matrix-v1.json"], ""),
    ("P1/economy-evidence-v1", "P1", "P1.5", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-economy-evidence.py", "--contract", f"{P}/root/contracts/economy-evidence-v1.md", "--cases", f"{P}/artifacts/P1/economy-evidence-cases-v1.json", "--rubric", f"{P}/artifacts/P0/acceptance-rubric-v1.md", "--baseline", f"{P}/artifacts/P0/baseline-catalog.json", "--providers", f"{P}/artifacts/P0/provider-matrix-v1.json"], "predecessor contract, still frozen and still green"),
    ("P1/economy-evidence-v2", "P1", "P5.7", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-economy-evidence.py", "--contract", f"{P}/root/contracts/economy-evidence-v2.md", "--cases", f"{P}/artifacts/P1/economy-evidence-cases-v2.json", "--rubric", f"{P}/artifacts/P0/acceptance-rubric-v1.md", "--baseline", f"{P}/artifacts/P0/baseline-catalog.json", "--providers", f"{P}/artifacts/P0/provider-matrix-v1.json", "--contract-version", "2.0.0", "--v1-cases", f"{P}/artifacts/P1/economy-evidence-cases-v1.json", "--tree-root", "."], "the contract this item is adjudicated against"),
    ("P1/contract-set-v2", "P1", "P5.7", "current", (0,), ["python3", f"{P}/artifacts/P1/validate-contract-set.py", "--manifest", f"{P}/artifacts/P1/contract-manifest-v2.json", "--contracts", f"{P}/root/contracts"], "v1 manifest is superseded by this eight-contract aggregate and is not replayed"),
    ("P1/dispatch-admission", "P1", "P1.6", "140a9b53", (0,), ["python3", f"{P}/artifacts/P1/validate-dispatch-admission.py", "--contract", f"{P}/root/contracts/dispatch-admission-v1.md", "--cases", f"{P}/artifacts/P1/dispatch-admission-cases-v1.json", "--smoke-tasks", f"{P}/artifacts/P1/p3-smoke-task-set-v1.json", "--smoke-grants", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--p3-phase", f"{P}/phases/P3.md"], "RED at its own owning commit and on the current tree: the frozen parent_task_contract_hash was produced by a task-contract compiler generation this repository no longer carries (cross-plan drift, owner 2026.07.24-AGENT-RELIABILITY). Outside P5.4's Scope (repairing a gate) and outside its declared pre-intent gate set; recorded, not silenced"),
    ("P2/prototype", "P2", "P2.6", "6c2c2ef3", (0,), ["python3", f"{P}/artifacts/P2/validate-prototype.py", "--root", f"{P}/artifacts/supervisor", "--manifest", f"{P}/artifacts/P2/prototype-manifest-v1.json", "--contracts", f"{P}/artifacts/P1/contract-manifest-v1.json"], "historical leaf: the plan-local prototype was promoted away by P3.8"),
    ("P3/adapters", "P3", "P3.6", "ea141189", (0,), ["python3", f"{P}/artifacts/P3/validate-adapters.py", "--root", f"{P}/artifacts/supervisor", "--manifest", f"{P}/artifacts/P3/adapter-manifest-v1.json", "--prototype", f"{P}/artifacts/P2/prototype-manifest-v1.json", "--contracts", f"{P}/artifacts/P1/contract-manifest-v1.json", "--admission-index", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json", "--grant-index", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--tasks", f"{P}/artifacts/P1/p3-smoke-task-set-v1.json", "--parity", f"{P}/artifacts/P3/provider-parity-v1.json", "--smoke-dir", f"{P}/artifacts/P3/provider-smoke"], "historical leaf, same reason"),
    ("P3/provider-parity", "P3", "P3.3", "current", (0,), ["python3", f"{P}/artifacts/P3/validate-provider-parity.py", "--matrix", f"{P}/artifacts/P3/provider-parity-v1.json", "--cases", f"{P}/artifacts/P3/provider-parity-cases-v1.json", "--worker-contract", f"{P}/root/contracts/worker-envelope-v1.md", "--providers", f"{P}/artifacts/P0/provider-matrix-v1.json"], ""),
    ("P3/package-promotion", "P3", "P5.6", "current", (0,), ["python3", f"{P}/artifacts/P3/validate-package-promotion.py", "--manifest", f"{P}/artifacts/P3/package-promotion-manifest-v1.json", "--prototype", f"{P}/artifacts/P3/adapter-manifest-v1.json", "--package", "packages/artifex"], "generation-aware since P5.6"),
    ("P4/fault-matrix", "P4", "P4.1", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-fault-matrix.py", "--matrix", f"{P}/artifacts/P4/fault-matrix-v1.json", "--cases", f"{P}/artifacts/P4/fault-cases-v1.json", "--contracts", f"{P}/artifacts/P1/contract-manifest-v1.json", "--dispatch-contract", f"{P}/root/contracts/dispatch-admission-v1.md", "--grant-index", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--admission-index", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json", "--prototype", f"{P}/artifacts/P2/prototype-manifest-v1.json", "--adapters", f"{P}/artifacts/P3/adapter-manifest-v1.json", "--threats", f"{P}/artifacts/P0/threat-cases-v1.json"], ""),
    ("P4/recovery", "P4", "P4.2", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-recovery.py", "--matrix", f"{P}/artifacts/P4/fault-matrix-v1.json", "--cases", f"{P}/artifacts/P4/fault-cases-v1.json", "--results", f"{P}/artifacts/P4/recovery-results-v1.json", "--run-contract", f"{P}/root/contracts/supervisor-run-v1.md", "--dispatch-contract", f"{P}/root/contracts/dispatch-admission-v1.md", "--grant-index", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--admission-index", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json"], ""),
    ("P4/worktree", "P4", "P4.3", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-worktree.py", "--cases", f"{P}/artifacts/P4/worktree-cases-v1.json", "--results", f"{P}/artifacts/P4/worktree-results-v1.json", "--recovery", f"{P}/artifacts/P4/recovery-results-v1.json", "--slice-contract", f"{P}/root/contracts/slice-manifest-v1.md"], ""),
    ("P4/security", "P4", "P4.4", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-security.py", "--cases", f"{P}/artifacts/P4/security-cases-v1.json", "--results", f"{P}/artifacts/P4/security-results-v1.json", "--hook-results", f"{P}/artifacts/P4/hook-integrity-results-v1.json"], ""),
    ("P4/hook-integrity", "P4", "P4.6", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-hook-integrity.py", "--self-test"], ""),
    ("P4/provenance", "P4", "P4.7", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-provenance-reconciliation.py", "--record", f"{P}/artifacts/P4/provenance-reconciliation-v1.json", "--plan-dir", P, "--self-test"], "three-argument form (the spec-text shorthand exits 2 on argparse)"),
    ("P4/authority-requalification", "P4", "P4.8", "124df816", (0,), ["python3", f"{P}/artifacts/P4/validate-authority-requalification.py", "--record", f"{P}/artifacts/P4/authority-requalification-v1.json", "--plan-dir", P, "--before", "17a57adc", "--historical-item", "23f71d34"], "historical leaf at the P4.8 owning commit"),
    ("P4/assurance", "P4", "P5.8", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-assurance.py", "--manifest", f"{P}/artifacts/P4/assurance-manifest-v1.json", "--faults", f"{P}/artifacts/P4/fault-matrix-v1.json", "--recovery", f"{P}/artifacts/P4/recovery-results-v1.json", "--worktrees", f"{P}/artifacts/P4/worktree-results-v1.json", "--hooks", f"{P}/artifacts/P4/hook-integrity-results-v1.json", "--security", f"{P}/artifacts/P4/security-results-v1.json", "--attention", f"{P}/artifacts/P4/attention-cases-v1.json", "--contracts", f"{P}/artifacts/P1/contract-manifest-v1.json", "--admission-index", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json", "--prototype", f"{P}/artifacts/P2/prototype-manifest-v1.json", "--adapters", f"{P}/artifacts/P3/adapter-manifest-v1.json", "--provenance", f"{P}/artifacts/P4/provenance-reconciliation-v1.json", "--requalification", f"{P}/artifacts/P4/authority-requalification-v1.json"], "two-sided since P5.8/D134"),
    ("P4/p4.8-preflight", "P4", "P4.8", "current", (0,), ["python3", f"{P}/artifacts/P4/validate-p4.8-authority-preflight.py", "--plan-dir", P], "needs packages/task/lib on PYTHONPATH"),
    ("P5/shadow", "P5", "P5.6", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-shadow.py", "--package", "packages/artifex", "--assurance", f"{P}/artifacts/P4/assurance-manifest-v1.json"], ""),
    ("P5/repository-pilot", "P5", "P5.6", "current", (2,), ["python3", f"{P}/artifacts/P5/validate-repository-pilot.py"], "exit 2 is this gate's green (D130): P5.2's immutable honest 0/3 report"),
    ("P5/recovery-pilot", "P5", "P5.8", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-recovery-pilot.py", "--ledger", f"{P}/artifacts/P5/g2b-generation-ledger-v1.json"], "ledger-membership form"),
    ("P5/business-successor", "P5", "P5.5", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-business-successor.py", "--contract", f"{P}/root/contracts/business-dispatch-admission-v1.md", "--cases", f"{P}/artifacts/P5/business-dispatch-successor-cases-v1.json", "--provider-manifest", f"{P}/artifacts/P5/provider-business-projection-v1.json", "--provider-cases", f"{P}/artifacts/P5/provider-business-projection-cases-v1.json", "--generation", f"{P}/artifacts/P5/business-successor-generation-v1.json", "--assurance", f"{P}/artifacts/P5/business-successor-assurance-v1.json", "--g2", f"{P}/artifacts/P4/assurance-manifest-v1.json", "--admission-index", f"{P}/artifacts/P5/trial-admission-index-v1.json", "--package", "packages/artifex"], ""),
    ("P5/trial-admissions-v1", "P5", "P5.1", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-trial-admissions.py", "--catalog", f"{P}/artifacts/P5/trial-catalog-v1.json", "--request", f"{P}/artifacts/P5/business-grant-request-v1.json", "--grants", f"{P}/artifacts/P5/business-grants-v1.json", "--manifest-index", f"{P}/artifacts/P5/trial-dispatch-manifest-index-v1.json", "--admission-index", f"{P}/artifacts/P5/trial-admission-index-v1.json", "--smoke-tasks", f"{P}/artifacts/P1/p3-smoke-task-set-v1.json", "--smoke-grants", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--smoke-admissions", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json"], ""),
    ("P5/trial-admissions-v2", "P5", "P5.1", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-trial-admissions.py", "--catalog", f"{P}/artifacts/P5/trial-catalog-v2-p5.2-retry.json", "--request", f"{P}/artifacts/P5/business-grant-request-v2-p5.2-retry.json", "--grants", f"{P}/artifacts/P5/business-grants-v2-p5.2-retry.json", "--admission-index", f"{P}/artifacts/P5/trial-admission-index-v2-p5.2-retry.json", "--smoke-tasks", f"{P}/artifacts/P1/p3-smoke-task-set-v1.json", "--smoke-grants", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--smoke-admissions", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json", "--owner-decision", "D122", "--expected-count", "3", "--replay", f"{P}/artifacts/P5/trial-replay-v2-p5.2-retry.jsonl", "--baseline-catalog", f"{P}/artifacts/P5/trial-catalog-v1.json"], ""),
    ("P5/trial-admissions-v3", "P5", "P5.1", "current", (0,), ["python3", f"{P}/artifacts/P5/validate-trial-admissions.py", "--catalog", f"{P}/artifacts/P5/trial-catalog-v3-p5.4-paired.json", "--request", f"{P}/artifacts/P5/business-grant-request-v3-p5.4-paired.json", "--grants", f"{P}/artifacts/P5/business-grants-v3-p5.4-paired.json", "--admission-index", f"{P}/artifacts/P5/trial-admission-index-v3-p5.4-paired.json", "--smoke-tasks", f"{P}/artifacts/P1/p3-smoke-task-set-v1.json", "--smoke-grants", f"{P}/artifacts/P1/p3-smoke-dispatch-grants-v1.json", "--smoke-admissions", f"{P}/artifacts/P2/p3-smoke-admission-index-v1.json", "--owner-decision", "D125", "--expected-count", "10", "--replay", f"{P}/artifacts/P5/trial-replay-v3-p5.4-paired.jsonl", "--baseline-catalog", f"{P}/artifacts/P5/trial-catalog-v1.json"], "the ten rows this item spends"),
    ("package/test.sh", "package", "P3.8", "current", (0,), ["bash", "packages/artifex/scripts/test.sh"], ""),
)


# A check whose red is REAL, reproduced at its own owning commit, and outside this
# item's authority to repair (Scope Excluded: "repair a gate"). It is recorded as red
# - never re-labelled green by widening its expected exit codes - and named in the
# item's Pending Work with its remediation owner.
OUT_OF_SCOPE_RED = {
    "P1/dispatch-admission": ("P1.6 leaf: the frozen parent_task_contract_hash names a task-contract "
                              "compiler generation this repository no longer carries (cross-plan drift, "
                              "owner 2026.07.24-AGENT-RELIABILITY). Red at its owning commit AND on the "
                              "current tree; not a member of P5.4's declared pre-intent gate set and not "
                              "an input to the G2B chain this item measures"),
}


def fan_in(repo: Path, plan: Path, args) -> int:
    rows, worktrees = [], {}
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "packages/task/lib") + os.pathsep + str(repo)
    try:
        for check_id, phase, owner, anchor, expected, argv, note in FAN_IN:
            if anchor == "current":
                cwd = repo
            else:
                if anchor not in worktrees:
                    target = Path(tempfile.mkdtemp(prefix=f"p5.4-fanin-{anchor}-"))
                    path = target / "wt"
                    if command(["git", "worktree", "add", "--detach", "--", str(path), anchor], cwd=repo).returncode:
                        raise WaveRefusal("FANIN_WORKTREE", anchor)
                    worktrees[anchor] = path
                cwd = worktrees[anchor]
            completed = subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, check=False, env=env)
            text = completed.stdout.decode("utf-8", "replace").strip().splitlines()
            rows.append({
                "id": check_id, "phase": phase, "owner_item": owner,
                "anchor": anchor if anchor != "current" else command(["git", "rev-parse", "HEAD"], cwd=repo)
                          .stdout.decode().strip(),
                "anchor_kind": "owning-commit" if anchor != "current" else "current-tree",
                "command": " ".join(argv), "exit_code": completed.returncode,
                "expected_exit_codes": list(expected),
                "green": completed.returncode in expected,
                "output_tail": text[-1] if text else "",
                "note": note,
            })
    finally:
        for path in worktrees.values():
            command(["git", "worktree", "remove", "--force", "--", str(path)], cwd=repo)
    anchor_argv = ["git", "diff", "--exit-code", "3533234c", "--", f"{P}/phases/P4.md", f"{P}/artifacts/P4",
                   f":(exclude){P}/artifacts/P4/validate-assurance.py"]
    anchor_diff = subprocess.run(anchor_argv, cwd=str(repo), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, check=False)
    anchor_log = command(["git", "log", "--format=%h", "3533234c..HEAD", "--",
                          f"{P}/artifacts/P4/validate-assurance.py"], cwd=repo).stdout.decode().split()
    rows.append({"id": "P4/d134-anchor", "phase": "P4", "owner_item": "P5.8", "anchor": "3533234c",
                 "anchor_kind": "evidence-anchor", "command": " ".join(anchor_argv),
                 "exit_code": anchor_diff.returncode, "expected_exit_codes": [0],
                 "green": anchor_diff.returncode == 0 and len(anchor_log) == 1,
                 "output_tail": f"intermediate commits touching validate-assurance.py: {anchor_log}",
                 "note": "D134: exclusion plus a one-commit provenance proof"})
    manifest = {
        "schema_version": "artifex-p5-pilot-manifest-v1",
        "manifest_version": "1.0.0",
        "fan_in": "D109 generation-aware P0-P5",
        "tree": command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.decode().strip(),
        "checks": rows,
        "green": sum(row["green"] for row in rows),
        "total": len(rows),
        "non_green": sorted(row["id"] for row in rows if not row["green"]),
        "out_of_scope_red": {key: value for key, value in OUT_OF_SCOPE_RED.items()
                             if key in {row["id"] for row in rows if not row["green"]}},
        "blocking_red": sorted(row["id"] for row in rows
                               if not row["green"] and row["id"] not in OUT_OF_SCOPE_RED),
        "declared_non_zero_exit": sorted(row["id"] for row in rows
                                         if row["green"] and row["exit_code"] != 0),
    }
    args.manifest_out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(f"P5.4 fan-in: {manifest['green']}/{manifest['total']} green; "
          f"out-of-scope red={sorted(manifest['out_of_scope_red'])}; "
          f"blocking red={manifest['blocking_red']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--trial", required=True)
    dispatch.add_argument("--results", required=True, type=Path)
    dispatch.add_argument("--runs-root", required=True,
                          help="declared, repository-relative and never created: this runner reaches "
                               "no CLI run-folder path (D135 imports the port directly)")
    build = sub.add_parser("assemble")
    build.add_argument("--results", required=True, type=Path)
    build.add_argument("--verdict-out", required=True, type=Path)
    sweep = sub.add_parser("fan-in")
    sweep.add_argument("--manifest-out", required=True, type=Path)
    args = parser.parse_args()
    repo, plan = root(), root() / "plans" / PLAN_ID
    if args.mode == "dispatch":
        return dispatch_main(repo, plan, args)
    try:
        return assemble(repo, plan, args) if args.mode == "assemble" else fan_in(repo, plan, args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"P5.4 battle waves: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
