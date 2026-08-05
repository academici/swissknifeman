"""Explicit-root command surface for the plan-local Artifex P2 candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import activity, authority, compiler, dispatch, scheduler, store, worktree

MAX_RESULT_BYTES = 32_768
EXIT_OK, EXIT_REFUSAL, EXIT_NOT_FOUND, EXIT_ERROR = 0, 2, 3, 1


class CliRefusal(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_name(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise CliRefusal("RUN_IDENTITY_MISMATCH")
    return value


def _inside(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise CliRefusal("PATH_EXTERNAL", str(candidate)) from exc
    return resolved


def _directory(path: Path, *, create: bool = False) -> Path:
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as exc:
        raise CliRefusal("PATH_MISSING", str(path)) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise CliRefusal("PATH_UNSAFE", str(path))
    return path.resolve(strict=True)


def _file(path: Path) -> Path:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as exc:
        raise CliRefusal("PATH_MISSING", str(path)) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or os.lstat(path).st_nlink != 1:
        raise CliRefusal("PATH_UNSAFE", str(path))
    return path.resolve(strict=True)


def _roots(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    repo = _directory(Path(args.repo_root))
    plan_root = _inside(repo, repo / args.plan_dir)
    plan = _file(plan_root / "plan.md").parent
    runs = _inside(repo, repo / args.runs_root)
    if runs.exists():
        _directory(runs)
    elif args.command == "start":
        _directory(runs, create=True)
    return repo, plan, runs


def _rules(plan: Path) -> tuple[dict, set[str], set[str]]:
    cases = json.loads(_file(plan / "artifacts/P1/supervisor-run-cases-v1.json").read_text(encoding="utf-8"))
    return cases["state_rules"], set(cases["declared"]["states"]), set(cases["declared"]["events"])


def _run_dir(runs: Path, run_id: str) -> Path:
    if not runs.exists():
        raise CliRefusal("RUN_NOT_FOUND", run_id)
    return _inside(runs, runs / _safe_name(run_id))


def _open(runs: Path, run_id: str, rules: dict, states: set[str], events: set[str]) -> store.RunStore:
    target = _run_dir(runs, run_id)
    if not target.exists():
        raise CliRefusal("RUN_NOT_FOUND", run_id)
    return store.RunStore.open(target, rules=rules, states=states, events=events)


def _payload(run: store.RunStore, event: str, *, slice_id: str | None = None, attempt: int | None = None,
             key: str | None = None, evidence: dict | None = None) -> dict:
    replay = run.replay()
    state = replay["state"] or "CREATED"
    expected = run.rules.get(state, {}).get("on", {}).get(event)
    if expected is None:
        raise CliRefusal(run.rules.get(state, {}).get("otherwise", "ILLEGAL_TRANSITION"))
    return {"ts": _now(), "run_id": run.run_dir.name, "slice_id": slice_id, "attempt": attempt,
            "event": event, "state_before": state, "state_after": expected,
            "idempotency_key": key, "input_hashes": {}, "evidence": evidence or {}, "redaction": {"status": "clean"}}


def _last_identity(replay: dict) -> tuple[str, int, str]:
    for row in reversed(replay["records"]):
        if row.get("slice_id") and row.get("idempotency_key"):
            return row["slice_id"], row["attempt"], row["idempotency_key"]
    raise CliRefusal("UNRESOLVED_INTENT_MISSING")


def _start(args: argparse.Namespace, repo: Path, plan: Path, runs: Path) -> dict:
    run_id = _safe_name(args.run_id)
    if args.phase != args.item.split(".", 1)[0]:
        raise CliRefusal("RUN_IDENTITY_MISMATCH", "phase/item")
    mandate = _file(_inside(repo, repo / args.mandate))
    manifest = compiler.compile_slice(repo, plan, args.item)
    rules, states, events = _rules(plan)
    identity = {"schema_version": "supervisor-run-v1", "contract_version": "1.0.0", "run_id": run_id,
                "repository_root_hash": _digest(str(repo).encode()), "base_commit": manifest["source_hashes"]["base_commit"],
                "plan_id": manifest["plan_id"], "plan_hash": manifest["source_hashes"]["plan"],
                "mandate_hash": _digest(mandate.read_bytes()), "acceptance_hash": _digest(json.dumps(manifest["scope"]["validation"], sort_keys=True).encode()),
                "created_at": _now(), "redaction_policy_hash": _digest(b"p2-redacted-report-v1")}
    run = store.RunStore.create(runs, args.run_id, identity, rules=rules, states=states, events=events)
    with run.acquire_writer():
        run.append_event(_payload(run, "freeze_run", evidence={"manifest_hash": manifest["content_hash"]}))
        snapshot = run.rebuild_snapshot()
    return {"status": "ready", "run_id": args.run_id, "state": "READY", "manifest_hash": manifest["content_hash"], "snapshot": snapshot["snapshot"]}


def _status(args: argparse.Namespace, _repo: Path, plan: Path, runs: Path) -> dict:
    rules, states, events = _rules(plan)
    replay = _open(runs, args.run_id, rules, states, events).replay()
    return {"status": "ok", "run_id": args.run_id, "state": replay["state"], "seq": replay["seq"], "tail_hash": replay["tail_hash"]}


def _reconcile(args: argparse.Namespace, _repo: Path, plan: Path, runs: Path) -> dict:
    rules, states, events = _rules(plan)
    run = _open(runs, args.run_id, rules, states, events)
    replay = run.replay()
    slice_id, attempt, key = _last_identity(replay)
    event = {"preimage": "reconcile_preimage", "postimage": "reconcile_postimage", "partial": "reconcile_partial", "third": "reconcile_third_state"}[args.observed]
    with run.acquire_writer():
        row = run.append_event(_payload(run, event, slice_id=slice_id, attempt=attempt, key=key, evidence={"reconcile": args.observed}))
        if args.observed == "postimage":
            row = run.append_event(_payload(run, "validation_green", slice_id=slice_id, attempt=attempt, key=key, evidence={"validation": "deterministic"}))
        run.rebuild_snapshot()
    return {"status": "reconciled", "run_id": args.run_id, "state": row["state_after"], "reason": args.observed}


def _resume(args: argparse.Namespace, repo: Path, plan: Path, runs: Path) -> dict:
    return _reconcile(args, repo, plan, runs) if args.observed else _status(args, repo, plan, runs)


def _stop(args: argparse.Namespace, _repo: Path, plan: Path, runs: Path) -> dict:
    rules, states, events = _rules(plan)
    run = _open(runs, args.run_id, rules, states, events)
    replay = run.replay()
    if replay["state"] == "ABORTED":
        return {"status": "stopped", "run_id": args.run_id, "state": "ABORTED", "idempotent": True}
    with run.acquire_writer():
        replay = run.replay()
        if replay["state"] == "CREATED":
            row = run.append_event(_payload(run, "owner_decision_abort", evidence={"stop": "explicit"}))
        else:
            try:
                slice_id, attempt, key = _last_identity(replay)
            except CliRefusal:
                slice_id = attempt = key = None
            row = run.append_event(_payload(run, "owner_decision_abort", slice_id=slice_id, attempt=attempt, key=key, evidence={"stop": "explicit"}))
        run.rebuild_snapshot()
    return {"status": "stopped", "run_id": args.run_id, "state": row["state_after"], "idempotent": False}


def _report(args: argparse.Namespace, _repo: Path, plan: Path, runs: Path) -> dict:
    rules, states, events = _rules(plan)
    replay = _open(runs, args.run_id, rules, states, events).replay()
    counts: dict[str, int] = {}
    for row in replay["records"]:
        counts[row["event"]] = counts.get(row["event"], 0) + 1
    return {"status": "report", "run_id": args.run_id, "state": replay["state"], "events": counts,
            "replay": {"seq": replay["seq"], "tail_hash": replay["tail_hash"]}, "redacted": True}


def _dispatch(args: argparse.Namespace, repo: Path, plan: Path, runs: Path) -> dict:
    """Consume exactly one indexed admission through the P2 no-provider port."""
    admission_path = _file(_inside(repo, repo / args.admission))
    admission = dispatch.load_indexed_admission(plan, admission_path)
    identity = admission["dispatch"]
    if args.run_id != identity["run_id"]:
        raise CliRefusal("IDENTITY_MISMATCH", "run/admission")
    rules, states, events = _rules(plan)
    run = _open(runs, args.run_id, rules, states, events)
    replay = run.replay()
    if replay["state"] != "READY":
        raise CliRefusal("ILLEGAL_TRANSITION", str(replay["state"]))
    if any(row.get("event") == "append_intent" and row.get("idempotency_key") == identity["idempotency_key"]
           for row in replay["records"]):
        raise CliRefusal("USAGE_LIMIT_EXCEEDED")
    if args.provider is not None and args.provider != admission["task"]["provider"]:
        raise CliRefusal("PROVIDER_MISMATCH")
    admitted = authority.load_admitted_authority(plan, admission)
    authority_input = dict(admitted.frozen.cases["base_input"])
    authority_input.update({"operation": "dispatch_worker", "requested_class": "AUTO"})
    projected = dispatch.scheduler_slice(admission, authority_input)
    # Omission preserves the P2 provider-free refusal; an explicit provider is
    # selected only after the indexed admission has bound task and provider.
    selected_activity = None if args.provider is None else activity.ProviderActivityPort(plan, admission)
    result = scheduler.Scheduler(run, admitted, now=_now, activity=selected_activity).schedule([projected])
    run.rebuild_snapshot()
    observation = result.get("observation", {})
    return {"status": result["status"], "run_id": args.run_id, "task_id": admitted.task_id,
            "admission_hash": admission["admission_hash"], "process_count": observation.get("process_count", 0)}


def _worktree_inventory(args: argparse.Namespace, repo: Path, _plan: Path, _runs: Path) -> dict:
    """Expose the parseable linked-worktree inventory without mutating repository state."""
    manager = worktree.WorktreeManager(repo)
    return {"status": "ok", "worktrees": manager.inventory()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="artifex")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--runs-root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start"); start.add_argument("--run-id", required=True); start.add_argument("--phase", required=True); start.add_argument("--item", required=True); start.add_argument("--mandate", required=True)
    for name in ("status", "stop", "report"):
        sub.add_parser(name).add_argument("--run-id", required=True)
    for name in ("resume", "reconcile"):
        command = sub.add_parser(name); command.add_argument("--run-id", required=True); command.add_argument("--observed", choices=("preimage", "postimage", "partial", "third"), required=name == "reconcile")
    dispatch_command = sub.add_parser("dispatch")
    dispatch_command.add_argument("--run-id", required=True)
    dispatch_command.add_argument("--admission", required=True)
    dispatch_command.add_argument("--provider", choices=("codex", "claude-code"))
    sub.add_parser("worktree-inventory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo, plan, runs = _roots(args)
        result = {"start": _start, "status": _status, "resume": _resume, "reconcile": _reconcile, "stop": _stop, "report": _report, "dispatch": _dispatch,
                  "worktree-inventory": _worktree_inventory}[args.command](args, repo, plan, runs)
        code = EXIT_OK
    except (CliRefusal, compiler.CompileRefusal, dispatch.DispatchRefusal, store.StoreRefusal, scheduler.SchedulerRefusal) as exc:
        result, code = {"status": "refused", "reason": getattr(exc, "reason", str(exc))}, EXIT_NOT_FOUND if getattr(exc, "reason", "") == "RUN_NOT_FOUND" else EXIT_REFUSAL
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(payload.encode()) > MAX_RESULT_BYTES:
        payload, code = '{"reason":"RESULT_TOO_LARGE","status":"refused"}', EXIT_REFUSAL
    print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
