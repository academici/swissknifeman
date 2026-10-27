"""Explicit bounded continuation of an interrupted executor; ordinary resume/retry retains its legacy semantics."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from orch.conductor import records, options as opts
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, launch_budget
from orch.conductor.infrastructure.files import OPTIONS_COPY, safe


def _tightens_only(baseline: dict, proposed: dict) -> bool:
    """Allow explicitly bounded reductions; every unspecified option stays identical."""
    from copy import deepcopy

    expected = deepcopy(baseline)
    expected["rules"] = proposed.get("rules")
    for key in ("retries", "repairs", "corrections", "check_fixes"):
        before, after = baseline["limits"][key], proposed["limits"][key]
        if type(after) is not int or not 0 <= after <= before:
            return False
        expected["limits"][key] = after
    if proposed.get("fallback_routes") not in (baseline.get("fallback_routes"), []):
        return False
    expected["fallback_routes"] = proposed.get("fallback_routes")
    for key in ("outside", "outside_module"):
        before, after = baseline["scope"][key], proposed["scope"][key]
        if after != before and not (before == "deviation" and after == "block"):
            return False
        expected["scope"][key] = after
    before, after = baseline["scope"]["fence"], proposed["scope"]["fence"]
    if after != before and not (before == "project" and after == "plan"):
        return False
    expected["scope"]["fence"] = after
    before, after = baseline["checks"]["parallel"], proposed["checks"]["parallel"]
    if type(after) is not int or not 1 <= after <= before:
        return False
    expected["checks"]["parallel"] = after
    for key, allowed in (("reuse", (True, False)), ("fail_fast", (False, True))):
        before, after = baseline["checks"][key], proposed["checks"][key]
        if type(after) is not bool or (after != before and (before, after) != allowed):
            return False
        expected["checks"][key] = after
    return expected == proposed


def _keep(path: Path, raw: bytes):
    if path.exists():
        if path.read_bytes() != raw:
            raise Stop("FRESH_CONTEXT_SNAPSHOT_CONFLICT", f"pending fresh-context evidence differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def prepare_requested(owner, refs, options_file: Path | None, ceiling: int | None):
    if options_file is None or ceiling is None:
        raise Stop("OPTIONS_INVALID", "fresh-context requires options and a physical launch ceiling")
    prepare(owner, refs, options_file, ceiling)


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

    This API supports one piece with per-item sessions and no fallback. It admits only explicit monotonic
    tightening of retry/check limits and scope; routes and all other authority remain unchanged.
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
    if not _tightens_only(baseline, proposed):
        raise Stop("FRESH_CONTEXT_OPTIONS_CHANGED", "only explicitly bounded tightening and rules changes are allowed")
    if proposed.get("session", {}).get("executor") != "per-item" or proposed.get("fallback_routes"):
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
