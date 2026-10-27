"""Explicit bounded continuation of an interrupted executor; ordinary resume/retry retains its legacy semantics."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from orch.conductor import records, options as opts
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, launch_budget
from orch.conductor.infrastructure.files import OPTIONS_COPY, safe


def _keep(path: Path, raw: bytes):
    if path.exists():
        if path.read_bytes() != raw:
            raise Stop("FRESH_CONTEXT_SNAPSHOT_CONFLICT", f"pending fresh-context evidence differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def activate(owner):
    """Recover the run options pointer after a crash between state and run-record writes."""
    for item in owner.state.get("items", {}).values():
        history = item.get("fresh_contexts") or []
        if not history:
            continue
        record = history[-1]
        path = owner.directory / record["snapshot"]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != record["options_sha256"]:
            raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "the frozen invocation options are missing or changed")
        if owner.run_doc.get("options_file") != str(path):
            owner.run_doc["options_file"] = str(path)
            owner.store.save_run(owner.run_doc)


def prepare(owner, refs, options_file: Path, ceiling: int):
    """Prevalidate before writes, retain immutable before evidence, then invalidate only interrupted preparation.

    This initial API deliberately supports a one-piece run with per-item sessions, no fallback, and a rules-only
    invocation amendment. Changing route/budgets/authority requires their existing explicit owning contracts.
    """
    if len(refs) != 1 or list(owner.run_doc.get("items") or []) != list(refs) or len(owner.state["items"]) != 1:
        raise Stop("FRESH_CONTEXT_UNSUPPORTED", "fresh-context currently requires one explicit item in a one-piece run")
    ref = refs[0]
    item = owner.state["items"].get(ref)
    if owner.state.get("status") != "stopped" or not item or item.get("outcome") != "stopped":
        raise Stop("FRESH_CONTEXT_NOT_STOPPED", "fresh-context requires a stopped, unfinished item")
    steps = item.get("steps", {})
    unfinished = [key for key, value in steps.items() if value.get("status") in ("started", "stopped")]
    if len(unfinished) != 1 or not unfinished[0].startswith("executor."):
        raise Stop("FRESH_CONTEXT_NOT_INTERRUPTED", "one unfinished executor stage is required; completed work is not regenerated")
    directory = owner.directory / safe(ref)
    baseline_doc = records.read(directory / "options.json", "item-options")
    if baseline_doc is None:
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "recorded item options are missing")
    baseline = baseline_doc["options"]
    try:
        raw = Path(options_file).read_bytes()
        proposed = json.loads(raw)
    except (OSError, ValueError) as error:
        raise Stop("OPTIONS_INVALID", str(error)) from None
    issues = opts.layer_problems(proposed)
    if issues:
        raise Stop("OPTIONS_INVALID", "; ".join(issues[:3]))
    if {k: v for k, v in proposed.items() if k != "rules"} != {k: v for k, v in baseline.items() if k != "rules"}:
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "supply the full recorded effective options with only rules changed")
    if baseline.get("session", {}).get("executor") != "per-item" or baseline.get("fallback_routes"):
        raise Stop("FRESH_CONTEXT_UNSUPPORTED", "per-item fresh sessions and no fallback routes are required")
    found = launch_budget.inventory(directory)
    if len(found["requests"]) != owner.state.get("agents", 0) or not found["requests"]:
        raise Stop("MODEL_LAUNCH_HISTORY_UNKNOWN", "preserved requests must account for every historical agent run")
    history = item.get("fresh_contexts") or []
    if ceiling <= len(found["launches"]) or (history and ceiling > history[-1]["ceiling"]):
        raise Stop("MODEL_LAUNCH_CEILING", "total ceiling must admit work and cannot raise a prior continuation ceiling")
    stage = unfinished[0]
    candidates = [request for request in found["requests"] if request["role"] == "executor" and request["step"] == stage]
    if not candidates:
        raise Stop("FRESH_CONTEXT_NOT_INTERRUPTED", "the interrupted executor must have a preserved physical actor")
    latest = max(candidates, key=lambda value: value["started_at"])
    if any(request["started_at"] >= latest["started_at"] and
           (request["role"] != "executor" or request["step"] != stage) for request in found["requests"]):
        raise Stop("FRESH_CONTEXT_NOT_INTERRUPTED", "another physical actor ran later or its order cannot be proved")
    folder = directory / "fresh-context" / str(len(history) + 1)
    # Copies precede any state change. A repeat after a preparation crash accepts identical bytes only.
    for source, name in ((owner.directory / "run.json", "run.json"), (owner.directory / "state.json", "state.json"),
                         (directory / "input.json", "input.json"), (directory / "options.json", "item-options.json"),
                         (owner.directory / OPTIONS_COPY, "invocation-options.json")):
        if source.is_file():
            _keep(folder / "before" / name, source.read_bytes())
    _keep(folder / "invocation-options.json", raw)
    from orch.conductor.application import run_service
    dropped = [key for key in ("brief", "prepare", stage) if key in steps]
    run_service.archive_attempt(owner, ref, item, dropped, include_unfinished=True, copy_files=True)
    record = {"since": clock.utc_now(), "stage": stage, "ceiling": ceiling, "route": latest["route"],
              "tree_mark": owner._tree_mark(), "baseline": found["protected"], "admissions": {},
              "before": (folder / "before").relative_to(owner.directory).as_posix(),
              "snapshot": (folder / "invocation-options.json").relative_to(owner.directory).as_posix(),
              "options_sha256": sha256(raw).hexdigest()}
    item.setdefault("fresh_contexts", []).append(record)
    for key in dropped:
        steps.pop(key)
    for key in ("outcome", "stop", "skills_auto", "skills_checked"):
        item.pop(key, None)
    item["retried"] = record["since"]
    owner._save()
    activate(owner)
    owner.progress.emit("info", item=ref, reason_code="FRESH_CONTEXT_PREPARED",
                        message=f"{len(found['launches'])} historical launch admissions; total ceiling {ceiling}; counters preserved")
