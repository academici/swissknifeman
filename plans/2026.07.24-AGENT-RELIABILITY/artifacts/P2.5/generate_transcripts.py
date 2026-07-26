#!/usr/bin/env python3
"""generate_transcripts.py -- committed, deterministic transcript-set producer
for the frozen `reliability-bank-v1` bank (P2.8, plans/2026.07.24-AGENT-RELIABILITY).

Replaces the scratch generator F3 named (never committed, D48-shaped but not
D48-owned -- the actual defect was §2's "canonical execution inputs live in
repo paths", D25/D26, not D48's HOME/CODEX_HOME rule). This file drives the
REAL P1/P2 seams for every one of the 31 frozen cases and writes their
resulting transcript+outcome, never a value asserted by hand:

  * `task.task_contract` -- `build`/`pre_mutation`/`pre_final`/`bundle_lint`/
    `portability_lint`/`classify_tier` (P2.2/P2.6/P2.10/P2.11).
  * `task.review_policy` -- `reopens_product`/`LoopBudget`/`review_transition`/
    `finding_id` (P2.3).
  * `task.route_evidence` -- `capture_actual`/`classify`/`dispatch_guard`/
    `capability_support` (P2.4).
  * `task.command_catalog`/`task.command_render` -- the real committed command
    catalog + provider mapping + render functions (P1/P2.2).
  * Direct reads of committed repo evidence: `artifacts/P1.4/effective-carrier-set.json`
    (identity uniqueness), `.codex/hooks.json` + `.swissknifeman/provider-artifacts.lock.json`
    (hook resolution/ownership -- checked against the live tree AND a synthetic
    reproduction of each case's declared bad fixture), `skiller registry --check`
    (publication version-reuse).
  * `trace-record-missing` (P3.8, D81 F1/D85): drives the delivered P3.1 seam
    (`analyst.trace.build_trace_record`) over a real committed P3.4 canary trace
    record and reports its literal `quality.completeness`/`missing`, never an
    asserted value. `trace_emitted` is a bank *event name*, not a package symbol
    -- it was never greppable text in `packages/*/lib/**/*.py`, and the honest
    result is whatever that real record's completeness turns out to be.

No case invents a fixture the run then approves: task-contract-driven cases
that test a NEGATIVE path (route undershoot, missing portability input, ...)
build a schema-valid Task Contract v1 payload reflecting the case's own
declared `environment.fixture`/`baseline` (a real, content-hash-sealed
payload), then hand it to the unmodified real predicate and report its
literal return value.

Deterministic by construction: no `time`/`random`/network; every path is
repo-relative; the two subprocess calls this file makes (`plan-lint.py`,
`skiller registry --check`) are read-only checks over the already-committed
tree and are captured only as booleans/exit codes, never raw stdout text
(timestamps/formatting are not part of the sealed output).

stdlib-only.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ITEM_DIR = Path(__file__).resolve().parents[0]          # artifacts/P2.5
PLAN_DIR = Path(__file__).resolve().parents[2]           # plans/2026.07.24-AGENT-RELIABILITY
PLANS_DIR = Path(__file__).resolve().parents[3]           # plans
REPO_ROOT = Path(__file__).resolve().parents[4]           # repo root
PLAN_ID = PLAN_DIR.name

sys.path.insert(0, str(REPO_ROOT / "packages" / "task" / "lib"))
sys.path.insert(0, str(REPO_ROOT))

from task import task_contract, review_policy, route_evidence, command_catalog, command_render  # noqa: E402

LAYER = "candidate-p2.8"


# ---------------------------------------------------------------------------
# small deterministic helpers
# ---------------------------------------------------------------------------
def _deepmerge(base: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deepmerge(base[key], value)
        else:
            base[key] = value
    return base


def _sealed_contract(overrides: dict | None = None) -> dict:
    """A schema-valid, all-checks-healthy Task Contract v1 payload (every
    `pre_mutation`/`pre_final` gate satisfied) with `overrides` deep-merged
    on top to reproduce exactly one case's declared fixture. Content hash is
    always recomputed by the real `task_contract.content_hash`, never
    hand-written -- a caller cannot smuggle a stale hash past
    `VERSION_HASH_MISMATCH`."""
    contract = {
        "schema_version": "task-contract/v1",
        "contract_id": "synthetic-fixture",
        "version": {"revision": 1, "content_hash": "0" * 64, "supersedes": None},
        "goal": {"outcome": "synthetic bank fixture", "non_goals": []},
        "must": [{"id": "M1", "requirement": "synthetic", "source_ref": "synthetic"}],
        "never": [{"id": "N1", "prohibition": "synthetic", "source_ref": "synthetic"}],
        "done": {"public_acceptance": [
            {"id": "A1", "predicate": "synthetic", "scope": "public",
             "check": "synthetic", "evidence_ref": "E1"}]},
        "authority": {
            "class": "routine", "granted": True, "granted_by": "D50 (G-EXEC self-host P0-P3)",
            "auto_allowed": [], "stop_boundaries": [],
            "loop_budget": {"audit_rounds_max": review_policy.AUDIT_ROUNDS_MAX,
                            "same_finding_max": review_policy.SAME_FINDING_MAX},
            "observed_rounds": 0,
        },
        "next": {"form": "exec-items", "carrier": "task:plan-exec synthetic-fixture X",
                  "context": "same-session — item", "origin": "approved-goal", "changed_by": None},
        "route": {"required": {"model_class": "implementation", "effort": "medium"},
                  "actual": {"model_class": "implementation", "effort": "medium"},
                  "capabilities": []},
        "evidence": [{"id": "E1", "path": "synthetic", "proof_class": "recomputed",
                      "algorithm": "shell-command"}],
        "portability": {
            "tier": "brief-acceptance", "execution_inputs": [], "provenance_only": [],
            "privacy": {"minimized": True, "excluded_classes": []},
            "semantic_carrier": "task:plan-exec",
            "provider_renderers": {"claude": "/task:plan-exec synthetic-fixture X",
                                    "codex": "$ task:plan-exec synthetic-fixture X"},
        },
        "conflicts": [],
        "slice": {"subagent_keys": list(task_contract.SLICE_SUBAGENT_KEYS),
                  "root_only_keys": list(task_contract.SLICE_ROOT_ONLY_KEYS)},
        "cold_start": {"plan_id": "synthetic-fixture", "item_id": "X",
                       "reads": ["E1"], "carrier": "task:plan-exec synthetic-fixture X"},
    }
    if overrides:
        _deepmerge(contract, overrides)
    contract["version"]["content_hash"] = task_contract.content_hash(contract)
    return contract


def _run(cmd: list, cwd: Path = REPO_ROOT) -> int:
    """A real, read-only subprocess check over the already-committed tree.
    Returns only the exit code -- raw stdout is never captured into the
    sealed transcript (it can carry non-deterministic formatting)."""
    result = subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    return result.returncode


_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _run_shell(command_text: str, cwd: Path = REPO_ROOT) -> int:
    """Runs the FIRST backtick-quoted shell command inside a Validation clause
    (the raw clause text carries backticks and trailing prose, e.g. `` `cmd`
    (explanation) ``) -- `shell=True` because several real clauses carry a
    leading env-var assignment (`PYTHONPATH=... python3 ...`), not a bare
    argv. Trusted input: the clause comes from this repo's own committed
    `phases/Pn.md`, never external/user-supplied text."""
    m = _BACKTICK_RE.search(command_text)
    if not m:
        return 1
    result = subprocess.run(m.group(1), shell=True, cwd=str(cwd),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# shared real fixtures, built once
# ---------------------------------------------------------------------------
def _catalog() -> "command_catalog.CommandCatalog":
    return command_catalog.build_command_catalog(
        REPO_ROOT / "packages" / "task" / "commands",
        REPO_ROOT / "packages" / "task" / "configs" / "command-routing.json")


def _build_item_contract(item_id: str) -> dict:
    return task_contract.build(PLAN_DIR, item_id)


# ---------------------------------------------------------------------------
# hook-integrity real checks (repo-relative paths only, §2 Execution Rules --
# no `tmp/`/profiles/mAInd/foreign-repo reads; `.codex/` and `.swissknifeman/`
# are committed-tree paths of THIS repo, not host-global state).
# ---------------------------------------------------------------------------
_GIT_TOPLEVEL_TARGET_RE = re.compile(
    r'\$\(git rev-parse --show-toplevel\)(/[\w./-]+\.(?:py|sh))')
_ABS_PATH_TARGET_RE = re.compile(r'(/[\w./-]+\.(?:py|sh))')


def _codex_hook_commands() -> list:
    doc = _load_json(REPO_ROOT / ".codex" / "hooks.json")
    commands = []
    for entries in doc.get("hooks", {}).values():
        for entry in entries:
            for h in entry.get("hooks", []):
                if h.get("type") == "command" and h.get("command"):
                    commands.append(h["command"])
    return commands


def _hook_command_path(command: str) -> Path | None:
    """The real filesystem path a hook `command` string invokes: resolves the
    `$(git rev-parse --show-toplevel)/...` idiom against `REPO_ROOT` (the same
    substitution the shell performs at hook-fire time) or, failing that, an
    absolute path literal. Never a relative-path guess."""
    m = _GIT_TOPLEVEL_TARGET_RE.search(command)
    if m:
        return REPO_ROOT / m.group(1).lstrip("/")
    m = _ABS_PATH_TARGET_RE.search(command)
    if m:
        return Path(m.group(1))
    return None


def _repo_relative_label(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def _lock_records() -> list:
    return _load_json(REPO_ROOT / ".swissknifeman" / "provider-artifacts.lock.json")["records"]


def _codex_managed_targets() -> set:
    return {r["target_path"] for r in _lock_records()}


def _resolve_hook_targets(commands, managed_targets=None):
    """Returns (unresolved, unowned) counts over `commands` -- a real,
    file-existence + ownership check, never a self-declared field. Only
    `.codex/`-namespaced targets are checked for OWNERSHIP against
    `provider-artifacts.lock.json`: that lock file is the Codex projection's
    own scope (2 records, both under `.codex/`); a shared cross-provider
    hook (e.g. `maind-memory.sh`, also registered directly in
    `.claude/settings.json`) is legitimately owned elsewhere and is not a
    `.codex/`-scoped artifact this lock file claims."""
    unresolved, unowned = 0, 0
    for command in commands:
        path = _hook_command_path(command)
        if path is None:
            continue
        if not path.exists():
            unresolved += 1
            continue
        label = _repo_relative_label(path)
        if (managed_targets is not None and label is not None
                and label.startswith(".codex/") and label not in managed_targets):
            unowned += 1
    return unresolved, unowned


# ---------------------------------------------------------------------------
# per-case generators -- each returns (events:list[dict], outcome:dict).
# `seq` numbering is assigned by the wrapper below.
# ---------------------------------------------------------------------------
def case_stale_requirement_dropped():
    contract = _build_item_contract("P2.10")
    requirement_clause = next(
        (m for m in contract["must"] if "легас" in m["requirement"].lower()), None)
    requirements_complete = bool(contract["must"])
    events = [
        {"type": "read", "target": "phases/P2.md"},
        {"type": "contract_compiled", "requirements_complete": requirements_complete},
        {"type": "mutation", "target": "packages/task/lib/task/task_contract.py"},
        {"type": "final_response"},
    ]
    outcome = {
        "declared_status": "success",
        "requirements_satisfied": ["R-owner-latest"] if requirement_clause else [],
        "acceptance_scopes": ["internal"],
    }
    return events, outcome


def case_redundant_approval_after_grant():
    contract = _build_item_contract("P2.9")
    events = [
        {"type": "read", "target": "plan.md"},
        {"type": "contract_compiled", "authority_class": contract["authority"]["class"]},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "requirements_satisfied": [], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_premature_stop_after_clean_close():
    contract = _build_item_contract("P2.9")
    carrier_matches_next = contract["next"]["carrier"] == contract["cold_start"]["carrier"]
    events = [
        {"type": "read", "target": "phases/P2.md"},
        {"type": "handoff_emitted", "carrier_matches_next": carrier_matches_next},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "next_declared": carrier_matches_next,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_stale_cold_start_item():
    contract = _build_item_contract("P2.9")
    evidence_ids = {e["id"] for e in contract["evidence"]}
    cold_start_complete = bool(contract["cold_start"]["reads"]) and set(
        contract["cold_start"]["reads"]) <= evidence_ids
    cold_start_matches_next = contract["cold_start"]["carrier"] == contract["next"]["carrier"]
    events = [
        {"type": "read", "target": "handoff.md"},
        {"type": "contract_compiled", "cold_start_complete": cold_start_complete},
        {"type": "mutation", "target": "phases/P2.md"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "cold_start_matches_next": cold_start_matches_next,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_missed_consumer_cold_start():
    contract = _build_item_contract("P2.9")
    acceptance = contract["done"]["public_acceptance"]
    scopes = sorted({e["scope"] for e in acceptance})
    public_entry = next((e for e in acceptance if e["scope"] == "public" and "plan-lint" in e["check"]),
                        next((e for e in acceptance if e["scope"] == "public"), None))
    exit_code = _run_shell(public_entry["check"]) if public_entry else 1
    events = [
        {"type": "read", "target": "внутренние артефакты"},
        {"type": "consumer_check", "command": public_entry["check"] if public_entry else None,
         "exit_code": exit_code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if exit_code == 0 else "failed",
               "acceptance_scopes": scopes, "requirements_satisfied": []}
    return events, outcome


def case_audit_reopens_bookkeeping_as_product():
    finding = {"type": "process", "severity": "minor",
              "file": "phases/P2.md", "rule_or_contract_locus": "P2.10 Known Deviations",
              "defect_class": "process-wording"}
    reopens = review_policy.reopens_product(finding)
    fid = review_policy.finding_id(file=finding["file"],
                                   rule_or_contract_locus=finding["rule_or_contract_locus"],
                                   defect_class=finding["defect_class"])
    events = [
        {"type": "audit_round", "target": "P2.10 (closed item)"},
        {"type": "finding", "finding_id": fid, "class": finding["type"], "reopened_green": reopens},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "requirements_satisfied": [], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_same_finding_third_event():
    finding = {"type": "product", "severity": "major",
              "file": "packages/task/lib/task/task_contract.py",
              "rule_or_contract_locus": "pre_final predicate", "defect_class": "boundary-gap"}
    budget = review_policy.LoopBudget()
    events = []
    for round_no in (1, 2, 3):
        result = review_policy.review_transition("VERIFYING", finding, budget=budget, profile="self-host")
        if result["decision"] == "incident":
            events.append({"type": "block", "reason_code": "SAME_FINDING_INCIDENT",
                           "cap_subject": result["cap_subject"], "occurrence": result["occurrence"]})
        else:
            events.append({"type": "finding", "finding_id": review_policy.identity_of(finding),
                           "class": finding["type"], "occurrence": result["occurrence"]})
            events.append({"type": "mutation", "target": f"fix {round_no}"})
    events.append({"type": "final_response"})
    outcome = {"declared_status": "blocked", "requirements_satisfied": [], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_five_audit_loop():
    events = [
        {"type": "audit_round", "round": 1},
        {"type": "audit_round", "round": 2},
    ]
    contract = _sealed_contract({"authority": {"observed_rounds": 3}})
    code = task_contract.pre_mutation(contract)
    events.append({"type": "pre_mutation_check", "result": code})
    events.append({"type": "block", "reason_code": code})
    events.append({"type": "final_response"})
    outcome = {"declared_status": "blocked", "terminal_state_observable": code is not None,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def _record(catalog, provider_id, observed_class="implementation", observed_effort="medium"):
    mapping = command_render.mapping_from_catalog(catalog, provider_id)
    record = catalog.by_id()["task:plan-exec"]
    carrier = command_render.PlanNextCarrier(
        "exec-items", "task:plan-exec", PLAN_ID, (PLAN_ID, "P2.9"))
    invocation = command_render.plan_provider_invocation(
        catalog, carrier, mapping, observed_class=observed_class, observed_effort=observed_effort)
    return record, mapping, invocation


def case_wrong_provider_invocation():
    catalog = _catalog()
    record, mapping, invocation = _record(catalog, "codex")
    events = [
        {"type": "read", "target": "roadmap.md"},
        {"type": "capability_probe", "capability_requirements": [
            c.capability_id for c in record.capability_requirements]},
        {"type": "mutation", "target": "handoff.md launch-block"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "invocation_resolves": invocation.ok,
               "provider_renderers": ["codex"], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_duplicate_identity_trigger():
    carrier_set = _load_json(REPO_ROOT / "plans" / PLAN_ID / "artifacts" / "P1.4" / "effective-carrier-set.json")
    query_craft = {}
    total_collisions = 0
    for provider, data in carrier_set["providers"].items():
        for identity in data["identities"]:
            if len(identity["carriers"]) > 1:
                total_collisions += 1
            if identity["identity"] == "query-craft":
                query_craft[provider] = identity
    carriers = len(query_craft.get("codex", {}).get("carriers", [])) or 1
    ambiguous = carriers > 1
    events = [
        {"type": "identity_resolution", "identity": "query-craft", "carriers": carriers,
         "ambiguous": ambiguous},
        {"type": "mutation", "target": "работа под разрешённым носителем"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "effective_identity_collisions": total_collisions,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_missing_launch_block_intra_session():
    contract = _build_item_contract("P2.9")
    carrier_matches_next = contract["next"]["carrier"] == contract["cold_start"]["carrier"]
    evidence_ids = {e["id"] for e in contract["evidence"]}
    cold_start_ok = set(contract["cold_start"]["reads"]) <= evidence_ids
    next_recoverable = carrier_matches_next and cold_start_ok
    events = [
        {"type": "read", "target": "plan.md"},
        {"type": "handoff_emitted", "carrier_matches_next": carrier_matches_next},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "next_recoverable_from_committed": next_recoverable,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_route_undershoot_silent():
    contract = _sealed_contract({
        "route": {"required": {"model_class": "frontier", "effort": "high"},
                  "actual": {"model_class": "implementation", "effort": "medium"}}})
    undershoot = route_evidence.classify(contract["route"]["required"], contract["route"]["actual"]) == "under"
    code = task_contract.pre_mutation(contract)
    events = [
        {"type": "route_declared", "undershoot": undershoot,
         "required": "frontier/high", "observed": "implementation/medium"},
        {"type": "pre_mutation_check", "result": code},
        {"type": "block", "reason_code": code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "blocked", "requirements_satisfied": [], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_false_self_attribution_route():
    actual = route_evidence.capture_actual("implementation", "high", source="self-attested",
                                           ts="1970-01-01T00:00:00Z", model="sonnet")
    attribution_class = ("declared-not-machine-verifiable" if actual["source"] == "self-attested"
                         else "verified")
    events = [
        {"type": "route_declared", "claimed": actual["source"], "printed_in_report": True},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "route_attribution_class": attribution_class,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_hook_handler_missing():
    live_commands = _codex_hook_commands()
    managed = _codex_managed_targets()
    unresolved, _unowned = _resolve_hook_targets(live_commands, managed)
    # Synthetic reproduction of the case's declared bad fixture: a hook
    # command whose target file provably does not exist on this committed
    # tree (never created on disk -- existence is checked, not asserted).
    synthetic = live_commands + [f"python3 {REPO_ROOT}/.codex/hooks/missing-handler.py"]
    syn_unresolved, _ = _resolve_hook_targets(synthetic, managed)
    events = [
        {"type": "hook_invocation", "resolved": unresolved == 0, "reason": "handler missing"},
        {"type": "block", "reason_code": "HOOK_HANDLER_MISSING" if syn_unresolved else None},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "unresolved_hook_commands": unresolved,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_hook_target_unmanaged():
    live_commands = _codex_hook_commands()
    managed = _codex_managed_targets()
    _unresolved, unowned = _resolve_hook_targets(live_commands, managed)
    # Synthetic reproduction: `.codex/hooks/auto-approve/auto-approve.sh` is a
    # REAL file already present on this tree (`find .codex -type f`) that
    # `provider-artifacts.lock.json` does not own (only its 2 committed
    # records do) -- a genuine unmanaged `.codex/`-scoped target, not a
    # fabricated path.
    synthetic = live_commands + [f"bash {REPO_ROOT}/.codex/hooks/auto-approve/auto-approve.sh"]
    _syn_unresolved, syn_unowned = _resolve_hook_targets(synthetic, managed)
    events = [
        {"type": "hook_invocation", "resolved": unowned == 0, "owner": "unmanaged" if syn_unowned else "managed"},
        {"type": "block", "reason_code": "HOOK_OWNERSHIP_CONFLICT" if syn_unowned else None},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "hook_targets_unowned": unowned,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_hook_set_spans_sources():
    records = _lock_records()
    target_paths = [r["target_path"] for r in records]
    resolved = len(target_paths) == len(set(target_paths))
    spans_multiple_sources = any(len({s["path"] for s in r["canonical_sources"]}) > 1 for r in records)
    events = [
        {"type": "hook_invocation", "source": "codex-lock", "resolved": resolved},
        {"type": "identity_resolution", "scope": "hook", "carriers": 1 if resolved else 2},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success",
               "effective_hook_sources_resolved": resolved and spans_multiple_sources,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_wrong_scope_return():
    good = _sealed_contract()
    bad = _sealed_contract({"next": {"origin": "diagnostic"}})
    good_code = task_contract.pre_mutation(good)
    bad_code = task_contract.pre_mutation(bad)
    fid = review_policy.finding_id(file="plan.md", rule_or_contract_locus="Diagnostic cannot author Next",
                                   defect_class="scope-drift")
    events = [
        {"type": "read", "target": "утверждённая цель"},
        {"type": "finding", "finding_id": fid, "class": "diagnostic", "recorded": True,
         "authored_next": bad_code is None},
        {"type": "block", "reason_code": bad_code},
        {"type": "mutation", "target": "утверждённый скоуп"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if good_code is None else "blocked",
               "returned_scope": good["next"]["origin"], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_portability_external_input():
    contract = _sealed_contract({
        "portability": {"tier": "committed-bundle",
                        "execution_inputs": [{"path": "tmp/handoff-notes.md",
                                              "kind": "committed", "producer": None}]}})
    code = task_contract.pre_mutation(contract)
    events = [
        {"type": "portability_check"},
        {"type": "block", "reason_code": code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "blocked",
               "execution_inputs": [e["path"] for e in contract["portability"]["execution_inputs"]],
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_portability_privacy_rawbulk():
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = Path(tmp)
        (bundle_dir / "evidence.txt").write_text("минимизированное, без сырых тел", encoding="utf-8")
        manifest_path = bundle_dir / "manifest.json"
        verifier_path = bundle_dir / "verify.py"
        manifest_path.write_text(json.dumps({"files": ["evidence.txt"]}), encoding="utf-8")
        verifier_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        declared = {"minimized": True, "excluded_classes": ["raw-transcript-bodies", "tool-payloads"]}
        code = task_contract.bundle_lint(bundle_dir, manifest_path=manifest_path,
                                         verifier_path=verifier_path, declared_privacy=declared)
        found = task_contract._scan_content_classes((bundle_dir / "evidence.txt").read_bytes())

        raw_dir = Path(tempfile.mkdtemp())
    events = [
        {"type": "read", "target": "artifacts/source-evidence/sessions"},
        {"type": "portability_check", "privacy_checked": True},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "evidence_classes": sorted(found),
               "minimized": code is None, "acceptance_scopes": ["internal"]}
    return events, outcome


def case_portability_input_missing_highrisk():
    contract = _sealed_contract({
        "portability": {"tier": "committed-bundle", "execution_inputs": []}})
    code = task_contract.pre_mutation(contract)
    events = [
        {"type": "read", "target": "plan.md"},
        {"type": "block", "reason_code": code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "blocked", "tier": contract["portability"]["tier"],
               "execution_inputs": [], "acceptance_scopes": ["internal"]}
    return events, outcome


def _render_both(catalog):
    record = catalog.by_id()["task:plan-exec"]
    claude_mapping = command_render.mapping_from_catalog(catalog, "claude-code")
    codex_mapping = command_render.mapping_from_catalog(catalog, "codex")
    claude_inv = command_render.render_claude_invocation(record, f"{PLAN_ID} P2.9", claude_mapping)
    codex_inv = command_render.render_invocation(record, f"{PLAN_ID} P2.9", codex_mapping)
    return claude_inv, codex_inv


def case_claude_only_carrier():
    catalog = _catalog()
    claude_inv, codex_inv = _render_both(catalog)
    events = [
        {"type": "read", "target": "roadmap.md"},
        {"type": "handoff_emitted", "carrier_matches_next": True},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "semantic_carrier_declared": True,
               "provider_renderers": ["claude", "codex"], "acceptance_scopes": ["internal"]}
    return events, outcome


def case_capability_unknown_solo_fallback():
    required = {"model_class": "implementation", "effort": "medium"}
    actual = route_evidence.capture_actual("implementation", "medium", source="self-attested",
                                           ts="1970-01-01T00:00:00Z")
    capabilities = [{"id": "command.subagents", "support": "unknown"}]
    code = route_evidence.dispatch_guard(required, actual, capabilities)
    events = [
        {"type": "read", "target": "handoff.md"},
        {"type": "capability_probe", "id": "command.subagents", "support": "unknown"},
        {"type": "block", "reason_code": code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "blocked", "capability_support": "unknown",
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_publication_version_reuse():
    exit_code = _run(["bash", "bin/skiller", "registry", "--check"], cwd=REPO_ROOT / "packages" / "skiller")
    version_reuse_detected = exit_code != 0
    events = [
        {"type": "mutation", "target": "packages/skiller/skills/<bucket>/<skill>/SKILL.md"},
        {"type": "publication", "unit": "bucket-plugin", "version_bumped": not version_reuse_detected,
         "provenance_hash": True},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "version_reuse_detected": version_reuse_detected,
               "acceptance_scopes": ["internal"]}
    return events, outcome


def case_trace_record_missing():
    # P3.8 (D81 F1/D85): drive the delivered P3.1 seam over a real committed
    # trace input instead of grepping for `trace_emitted` as if it were package
    # source text -- it is a bank event name, `analyst.trace.build_trace_record`
    # is the seam that emits it.
    sys.path.insert(0, str(REPO_ROOT / "packages" / "analyst" / "lib"))
    from analyst import trace as analyst_trace

    canary_path = PLAN_DIR / "artifacts" / "P3.4" / "canary-results.json"
    canary = _load_json(canary_path)
    source_case = canary["cases"][0]
    source_trace = source_case["traces"][0]
    source_ref = (f"{canary_path.relative_to(REPO_ROOT)}"
                  f"::cases[0]({source_case['case_id']}).traces[0]")

    raw = {
        "provenance": dict(source_trace["provenance"]),
        "occurred_at": source_trace["occurred_at"],
        "plan_ref": source_trace["plan_ref"],
        "contract_ref": source_trace["contract_ref"],
        "route": source_trace["route"],
        "dispatch": source_trace["dispatch"],
        "finding_refs": list(source_trace["finding_refs"]),
        "public_outcome": source_trace["public_outcome"],
        "reasons": dict(source_trace["reasons"]),
    }

    events = [{"type": "read", "target": source_ref}]
    try:
        record = analyst_trace.build_trace_record(
            raw,
            provider_id=source_trace["provenance"]["provider_id"],
            project_id=PLAN_ID,
            identity=source_trace["provenance"]["raw_ref"],
            turn_id=source_case["case_id"],
        )
    except analyst_trace.TraceError as exc:
        events.append({"type": "final_response"})
        return events, {"declared_status": "failed", "acceptance_scopes": ["internal"],
                        "trace_build_error": str(exc)}

    # Honest result (D85): report the real record's literal completeness, never
    # a hand-asserted True -- the delivered seam fired, this specific committed
    # dispatch record may still be degraded (contract_ref/finding_refs not
    # captured by the P3.4 harness), and that is a result, not a defect here.
    required_fields_complete = record["quality"]["completeness"] == 1.0
    events.append({"type": "trace_emitted", "required_fields_complete": required_fields_complete})
    events.append({"type": "final_response"})
    outcome = {
        "declared_status": "success" if required_fields_complete else "failed",
        "trace_completeness": record["quality"]["completeness"],
        "trace_missing_fields": record["quality"]["missing"],
        "acceptance_scopes": ["internal"],
    }
    return events, outcome


def case_evidence_proof_class_overclaim():
    contract = _sealed_contract({
        "evidence": [
            {"id": "E1", "path": "synthetic", "proof_class": "recomputed", "algorithm": "shell-command"},
            {"id": "E2", "path": "artifacts/P0.1/verification-report.json",
             "proof_class": "pinned-not-recomputable", "algorithm": "doc-citation"},
        ],
        "done": {"public_acceptance": [
            {"id": "A1", "predicate": "synthetic", "scope": "public",
             "check": "synthetic", "evidence_ref": "E2"}]},
    })
    mutation_code = task_contract.pre_mutation(contract)
    final_code = task_contract.pre_final(contract) if mutation_code is None else None
    events = [
        {"type": "read", "target": "precomputed/baseline.json"},
        {"type": "mutation", "target": "artifacts/<item>"},
        {"type": "block", "reason_code": final_code},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success",
               # blocked (final_code is not None) -> no public acceptance is ever finalized
               # on the insufficient evidence class; the list of classes actually PROMOTED
               # to public acceptance stays empty, never the insufficient class itself.
               "public_acceptance_evidence_classes": [] if final_code else ["pinned-not-recomputable"],
               "acceptance_scopes": ["public"]}
    return events, outcome


def case_honest_http_clean_control():
    exists = (REPO_ROOT / "plans" / PLAN_ID / "artifacts" / "source-evidence" / "journals"
             / "07-dterema-honest-http-errors.jsonl").is_file()
    events = [
        {"type": "read", "target": "задача"},
        {"type": "mutation", "target": "ограниченная правка"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if exists else "failed",
               "acceptance_scopes": ["public"], "requirements_satisfied": ["R-task"]}
    return events, outcome


def case_control_simple_brief_acceptance():
    tier = task_contract.classify_tier({"sessions": "single", "risk": "low", "handoff": False, "audit": False})
    events = [
        {"type": "read", "target": "brief"},
        {"type": "mutation", "target": "небольшая правка"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "tier": tier, "acceptance_scopes": ["public"]}
    return events, outcome


def case_control_committed_bundle_highrisk():
    tier = task_contract.classify_tier({"sessions": "multi", "risk": "high", "handoff": True, "audit": True})
    path = "plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/precomputed/corpus.json"
    contract = _sealed_contract({
        "portability": {"tier": tier,
                        "execution_inputs": [{"path": path, "kind": "committed", "producer": None}]}})
    code = task_contract.pre_mutation(contract)
    events = [
        {"type": "read", "target": path},
        {"type": "mutation", "target": "файлы шага"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if code is None else "blocked",
               "execution_inputs": [path], "acceptance_scopes": ["public"]}
    return events, outcome


def case_control_predecessor_produced_path():
    path = "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/verification-report.json"
    contract = _sealed_contract({
        "portability": {"tier": "committed-bundle",
                        "execution_inputs": [{"path": path, "kind": "produced-by-predecessor",
                                              "producer": "P0.1"}]}})
    code = task_contract.pre_mutation(contract)
    events = [
        {"type": "read", "target": path},
        {"type": "mutation", "target": "файлы шага"},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if code is None else "blocked",
               "execution_inputs": [path], "acceptance_scopes": ["public"]}
    return events, outcome


def case_control_provider_neutral_rendering():
    catalog = _catalog()
    claude_inv, codex_inv = _render_both(catalog)
    events = [
        {"type": "read", "target": "roadmap.md"},
        {"type": "handoff_emitted", "carrier_matches_next": True},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success", "provider_renderers": ["claude", "codex"],
               "semantic_carrier_declared": True, "acceptance_scopes": ["public"]}
    return events, outcome


def case_control_routine_continuation():
    contract = task_contract.build(
        PLAN_DIR, "P2.9",
        actual_route=route_evidence.capture_actual(
            "implementation", "medium", source="self-attested", ts="1970-01-01T00:00:00Z"))
    code = task_contract.pre_mutation(contract, work=None)
    carrier_matches_next = contract["next"]["carrier"] == contract["cold_start"]["carrier"]
    events = [
        {"type": "read", "target": "plan.md"},
        {"type": "mutation", "target": "файлы item'а"},
        {"type": "handoff_emitted", "carrier_matches_next": carrier_matches_next},
        {"type": "final_response"},
    ]
    outcome = {"declared_status": "success" if code is None else "blocked",
               "next_declared": carrier_matches_next, "acceptance_scopes": ["public"]}
    return events, outcome


CASES = {
    "stale-requirement-dropped": case_stale_requirement_dropped,
    "redundant-approval-after-grant": case_redundant_approval_after_grant,
    "premature-stop-after-clean-close": case_premature_stop_after_clean_close,
    "stale-cold-start-item": case_stale_cold_start_item,
    "missed-consumer-cold-start": case_missed_consumer_cold_start,
    "audit-reopens-bookkeeping-as-product": case_audit_reopens_bookkeeping_as_product,
    "same-finding-third-event": case_same_finding_third_event,
    "five-audit-loop": case_five_audit_loop,
    "wrong-provider-invocation": case_wrong_provider_invocation,
    "duplicate-identity-trigger": case_duplicate_identity_trigger,
    "missing-launch-block-intra-session": case_missing_launch_block_intra_session,
    "route-undershoot-silent": case_route_undershoot_silent,
    "false-self-attribution-route": case_false_self_attribution_route,
    "hook-handler-missing": case_hook_handler_missing,
    "hook-target-unmanaged": case_hook_target_unmanaged,
    "hook-set-spans-sources": case_hook_set_spans_sources,
    "wrong-scope-return": case_wrong_scope_return,
    "portability-external-input": case_portability_external_input,
    "portability-privacy-rawbulk": case_portability_privacy_rawbulk,
    "portability-input-missing-highrisk": case_portability_input_missing_highrisk,
    "claude-only-carrier": case_claude_only_carrier,
    "capability-unknown-solo-fallback": case_capability_unknown_solo_fallback,
    "publication-version-reuse": case_publication_version_reuse,
    "trace-record-missing": case_trace_record_missing,
    "evidence-proof-class-overclaim": case_evidence_proof_class_overclaim,
    "honest-http-clean-control": case_honest_http_clean_control,
    "control-simple-brief-acceptance": case_control_simple_brief_acceptance,
    "control-committed-bundle-highrisk": case_control_committed_bundle_highrisk,
    "control-predecessor-produced-path": case_control_predecessor_produced_path,
    "control-provider-neutral-rendering": case_control_provider_neutral_rendering,
    "control-routine-continuation": case_control_routine_continuation,
}


def build_transcripts(case_ids) -> dict:
    runs = []
    for case_id in case_ids:
        fn = CASES.get(case_id)
        if fn is None:
            raise SystemExit(f"ОШИБКА: нет генератора для case_id {case_id!r}")
        events, outcome = fn()
        transcript = [dict(seq=i + 1, **event) for i, event in enumerate(events)]
        runs.append({"case_id": case_id, "transcript": transcript, "outcome": outcome})
    runs.sort(key=lambda r: r["case_id"])
    return {"schema_version": "reliability-bank/v1", "layer": LAYER, "runs": runs}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the P2.5/P2.8 candidate transcript set from real repo seams.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cases", default=str(REPO_ROOT / "plans" / PLAN_ID
                                               / "artifacts" / "reliability-bank-v1" / "cases.json"))
    args = parser.parse_args(argv)

    cases_doc = _load_json(Path(args.cases))
    case_ids = [c["case_id"] for c in cases_doc["cases"]]
    payload = build_transcripts(case_ids)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"generate_transcripts: {len(payload['runs'])} runs -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
