"""The list of conductor runs of a project: ``orch conduct runs [--limit N] [--json]``.

Reads only the run folders of the orch state of the project (``run.json`` and ``progress.jsonl``): the id, the status
and reason code of the journal, when the run started, the pieces of work it carries and how often it was resumed.
Newest first, then by run id; an empty project gives an empty list; a run whose ``run.json`` cannot be read is listed as
``{run_id, status: "unreadable"}`` instead of failing the command.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import List, Optional

from aicore.ext.plugins import safe_text
from aicore.util import timefmt
from aicore.util.redact import env_secrets, redact_text

from orch.conductor import health as health_mod, options as opts, progress, records
from orch.conductor.infrastructure.files import REPORTS, RUN_FILE, STATE_FILE, runs_root, safe
from orch.conductor.infrastructure import heartbeat as heartbeat_mod
from orch.conductor.infrastructure.lease import RunLease
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.work_source import FALLBACK_ARTIFACTS  # <run id>/<piece>: a source without its own folder

PRUNABLE = {"done", "done_with_deviations", "finished", "blocked", "stopped", "orphaned"}


def display(value, limit: int = 500):
    """Redact before shortening display data, including keys in diagnostic objects."""
    if isinstance(value, str):
        return safe_text(redact_text(value, secrets=env_secrets()), limit)
    if isinstance(value, dict):
        labels = {"id", "run", "run_id", "item", "status", "reason_code", "role", "stage", "provider", "model",
                  "effort", "class", "model_class", "host", "started_at", "command", "label"}
        return {display(key, 64): display(entry, 64 if key in labels else limit) for key, entry in value.items()}
    if isinstance(value, list):
        return [display(entry, limit) for entry in value]
    return value


def public_route(route) -> dict:
    """Only routing labels, never the executable, environment or other launch data."""
    if not isinstance(route, dict):
        return {}
    labels = {key: route.get(key, route.get("model_class") if key == "class" else None)
              for key in ("provider", "model", "effort", "class")}
    return display({key: value if isinstance(value, str) else None for key, value in labels.items()}, 64)


def live_owner(directory: Path):
    """Lease metadata is meaningful only while an independent probe finds the lock busy."""
    held = RunLease.held(directory)
    if held is None:
        return {"lock": "unavailable"}  # read-only here: whether a conductor holds the run is unknown
    if not held:
        return None
    owner = RunLease.owner(directory)
    shown = {key: owner.get(key) for key in ("pid", "host", "started_at", "command")}
    shown.update({key: owner[key] for key in ("start_ticks", "boot_id", "launcher") if key in owner})  # the identity (I13)
    return display(shown, 64) if owner else None


def latest_run_id(project: Path) -> Optional[str]:
    """The run whose journal changed last (the default run of ``status``), or ``None``."""
    found = sorted((path for path in runs_root(project).glob("cnd-*") if (path / RUN_FILE).is_file()),
                   key=lambda path: (path / progress.PROGRESS_FILE).stat().st_mtime
                   if (path / progress.PROGRESS_FILE).exists() else 0)
    return found[-1].name if found else None


STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z")


def reset_until(lines: list) -> Optional[float]:
    """The epoch time the last provider wait or capacity gate of the journal ends (the last time in its message), or ``None``."""
    found = None
    for line in lines:
        if line.get("event") == "info" and line.get("reason_code") in ("PROVIDER_WAIT", "CAPACITY_GATED"):
            stamps = STAMP.findall(line.get("message") or "")
            found = timefmt.epoch(stamps[-1]) if stamps else found
    return found


def thresholds_of(directory: Path, found: dict, hung_after_s: Optional[int] = None) -> health_mod.Thresholds:
    """The health thresholds of the run: the stall limits of the piece it is on (its ``options.json``), else the defaults;
    ``hung_after_s`` (``[orch.supervisor]``, given by the supervisor) replaces the default age of a heartbeat."""
    ref = (found.get("current") or {}).get("item") or (found["items"][-1]["item"] if found.get("items") else None)
    limits: dict = {}
    if ref:
        try:
            limits = ((records.read(directory / safe(ref) / "options.json", "item-options") or {}).get("options") or {}).get("limits") or {}
        except (OSError, Stop):
            limits = {}
    return health_mod.Thresholds(**{key: int(limits.get(key, opts.DEFAULT_LIMITS[key]))
                                    for key in ("stall_window_s", "stall_repeat_n")},
                                 **({"hung_after_s": int(hung_after_s)} if hung_after_s else {}))


def health_of(directory: Path, found: dict, state: Optional[dict] = None, lines: Optional[list] = None,
              now: Optional[float] = None, hung_after_s: Optional[int] = None) -> dict:
    """``health.classify`` of a run from its files: reads the heartbeat, probes the lease, writes nothing. ``found`` is the
    journal summary (``effective_status``); a document that cannot be read is a class of its own (``unknown``), never a failure."""
    try:
        doc = records.read(directory / RUN_FILE, "run") or {}
    except (OSError, Stop):
        doc = {}
    flag = doc.get("lease") is True
    held = RunLease.held(directory) if flag else None
    lease = {"flag": flag, "held": held, "owner": RunLease.owner(directory) if held else None}
    beat, problem = heartbeat_mod.read(directory)
    summary = dict(found, reset_until=reset_until(lines if lines is not None else progress.read_lines(directory)))
    if beat is None and problem != "HEARTBEAT_MISSING":
        beat = {health_mod.INVALID: problem}
    return health_mod.classify(summary, state or {}, beat, lease, time.time() if now is None else now,
                               thresholds_of(directory, found, hung_after_s))


def health_text(directory: Path, found: dict) -> str:
    """The ``health:`` line of the text status, with its line break."""
    found_health = health_of(directory, found, found.get("state"))
    silent = found_health["silent_s"]
    return (f"\n  health: {found_health['health']}" + (f" (silent {progress.human_duration(silent)})" if silent is not None else "")
            + (f" — {found_health['reason_code']}: {found_health['detail']}" if found_health["reason_code"] else ""))


def status_details(directory: Path, found: dict) -> dict:
    """Add read-only observability to the journal summary without rebuilding routes or options."""
    state = found["state"]
    doc = records.read(directory / RUN_FILE, "run") or {}
    raises = state.get("limit_raises") or []
    limits = {}
    if doc.get("limits_run") or raises:
        limits = {"items": {}, **(doc.get("limits_run") or {}), "limit_raises": raises}
    for row in found["items"]:
        ref = row["item"]
        item_state = (state.get("items") or {}).get(ref) or {}
        folder = directory / safe(ref)
        recorded = records.read(folder / "routes.json", "item-routes") or {}
        row.update(tokens=item_state.get("tokens"), usage_incomplete=item_state.get("usage_incomplete"),
                   routes={role: public_route(route) for role, route in recorded.items()
                           if isinstance(route, dict)})
        options = records.read(folder / "options.json", "item-options") or {}
        item_limits = (options.get("options") or {}).get("limits") or {}
        if item_limits:
            limits.setdefault("items", {})[ref] = {key: item_limits.get(key, 0)
                                                   for key in ("tokens_max", "tokens_hard_max")}
    if limits:
        limits.setdefault("limit_raises", raises)
        for change in raises:
            key = change["key"]
            if key == "tokens_hard_max":
                for ref, entry in limits.get("items", {}).items():
                    if change.get("item") in (None, ref):  # a raise names its piece; an old record holds for all
                        entry[key] = change["to"]
            elif key == "run_tokens_hard_max":
                limits[key] = {**limits.get(key, {}), "value": change["to"], "source": "invocation:--raise-limit"}
    codes = {"BUDGET_OVER", "BUDGET_UNMETERED", "STAGE_INTERRUPTED", "ROLE_ORPHAN_KILLED", "LIMIT_RAISED", "CATALOG_CHANGED",
             "WRITE_PROTECTED_PATH", "STAGE_SLOW", "STAGE_IDLE", "CHECK_SLOW", "CHECK_IDLE", "DISK_LOW", "STALL_SUSPECTED"}
    beacons = {}
    for line in progress.read_lines(directory):
        if line.get("event") == "info" and line.get("reason_code") in codes:
            code = line["reason_code"]
            beacons.pop(code, None)
            beacons[code] = line
    return {"lease": live_owner(directory), "limits": limits, "beacons": list(beacons.values()),
            "health": health_of(directory, found, state),
            **({"catalog_digests": doc["catalog_digests"]} if isinstance(doc.get("catalog_digests"), dict) else {})}


def effective_status(directory: Path, summary: dict, doc=None, *, owned: bool = False) -> dict:
    """Refine a journal summary using an independent flock probe; summarize stays pure."""
    if doc is None:
        doc = records.read(directory / RUN_FILE, "run") or {}  # RUN_INVALID / STATE_CORRUPT stop the caller
    if summary["status"] != "running" or not isinstance(doc, dict) or doc.get("lease") is not True:
        return summary
    held = None if owned else RunLease.held(directory)
    if owned or held is False:
        return dict(summary, status="orphaned", reason_code="RUN_ORPHANED")
    if held is None:  # read-only context: the lock cannot be probed, so the run is not called orphaned
        return dict(summary, lease="unknown")
    return summary


def _row(directory: Path, *, owned: bool = False) -> dict:
    run_id = directory.name
    try:
        doc = records.read(directory / RUN_FILE, "run")
    except (OSError, Stop):  # not JSON, or not a records/v1 run: listed, never a failure of the listing
        doc = None
    if not isinstance(doc, dict):
        return {"run_id": display(run_id, 64), "status": "unreadable", "owner": live_owner(directory)}
    lines = progress.read_lines(directory)
    found = effective_status(directory, progress.summarize(lines), doc, owned=owned)
    items = [row["item"] for row in found["items"]]
    if not items and isinstance(doc.get("items"), list):
        items = [item for item in doc["items"] if isinstance(item, str)]
    state = {}
    if found["status"] == "stopped":  # only a stopped run needs its state (a quota reset)
        try:
            state = records.read(directory / STATE_FILE, "state") or {}
        except (OSError, Stop):
            state = {}
    return display({"run_id": run_id, "health": None if owned else health_of(directory, found, state, lines)["health"], "status": found["status"], "reason_code": found["reason_code"],
            "created": lines[0]["ts"] if lines else None, "items": display(items, 64),
            "resumes": sum(1 for line in lines if line.get("event") == "run.resume"),
            "owner": None if owned else live_owner(directory)})


def listing(project: Path, limit: Optional[int] = None) -> List[dict]:
    """The runs of ``project``, newest first and by run id; at most ``limit`` of them when given."""
    root = runs_root(project)
    try:
        directories = sorted(path for path in root.glob("cnd-*") if (path / RUN_FILE).is_file())
    except OSError:
        return []
    rows = [_row(path) for path in directories]  # by run id ...
    rows.sort(key=lambda row: row.get("created") or "", reverse=True)  # ... then newest first (the sort is stable)
    return rows[:limit] if limit is not None else rows


def text(rows: List[dict]) -> str:
    if not rows:
        return "no conductor runs"
    out = []
    for row in rows:
        if row["status"] == "unreadable":
            out.append(f"{row['run_id']}: unreadable")
            continue
        reason = f" ({row['reason_code']})" if row.get("reason_code") else ""
        out.append(f"{row['run_id']}: {row['status']}{reason}, started {row['created'] or '-'}, "
                   f"{len(row['items'])} item(s), {row['resumes']} resume(s)")
    return "\n".join(out)


def _age_days(directory: Path, now: float) -> float:
    """Days since the last journal line of the run (its folder time when the journal is empty or unreadable)."""
    last = progress.summarize(progress.read_lines(directory))["last_ts"]
    stamp = timefmt.epoch(last) if isinstance(last, str) else None
    if stamp is None:
        try:
            stamp = directory.stat().st_mtime
        except OSError:
            return 0.0
    return max(0.0, (now - stamp) / 86400)


def _remove(path: Path) -> bool:
    if path.is_symlink():
        path.unlink()
        return True
    if path.is_dir():
        shutil.rmtree(path)
        return True
    if path.is_file():
        path.unlink()
        return True
    return False


def prune(project: Path, older_than_days: int, apply: bool = False, now: Optional[float] = None) -> List[dict]:
    """Runs that ended more than ``older_than_days`` days ago, with the folders that belong to them: the run state, the
    observer reports and ``.swissknifeman/orch-artifacts/<run id>``. The latest run and a run that is running now are
    never listed; a run whose ``run.json`` cannot be read is left alone. Only ``apply`` removes anything. Rows:
    ``{run_id, status, age_days, paths, removed}``. Pieces whose brief names its own ``artifacts_dir`` and the aicore event
    journal are not touched."""
    root = runs_root(project)
    keep = latest_run_id(project)
    clock = time.time() if now is None else now
    rows: List[dict] = []
    try:
        directories = sorted(path for path in root.glob("cnd-*") if (path / RUN_FILE).is_file())
    except OSError:
        return rows
    for directory in directories:
        run_id = directory.name
        if run_id == keep:
            continue
        row = _row(directory)
        if row["status"] not in PRUNABLE:
            continue
        age = _age_days(directory, clock)
        if age < older_than_days:
            continue
        paths = [directory] + [project / base / run_id for base in (REPORTS, FALLBACK_ARTIFACTS)
                               if (project / base / run_id).exists() or (project / base / run_id).is_symlink()]
        log = root / "detached" / f"{run_id}.log"
        if log.exists() or log.is_symlink():
            paths.append(log)
        local = project / FALLBACK_ARTIFACTS / run_id
        # the local records of a source without its own folder (the file source) are the only copy of its evidence
        evidence = sorted(str(path.relative_to(project)) for path in local.glob("*/evidence/*.json")) \
            if local.is_dir() and not local.is_symlink() else []
        removed = False
        reason = None
        if apply:
            lease = RunLease(directory)
            try:
                lease.acquire("prune")
            except Stop as error:
                reason = f"{error.code}: {error.message}"
            except FileNotFoundError:
                reason = "run was removed by another prune"
            else:
                try:
                    row = _row(directory, owned=True)
                    age = _age_days(directory, clock)
                    if (row["status"] not in PRUNABLE or age < older_than_days
                            or run_id == latest_run_id(project)):
                        reason = "run is no longer eligible"
                    else:
                        target = root / f".pruning-{run_id}"
                        directory.rename(target)
                        removed = _remove(target)
                        for path in paths[1:]:
                            removed = _remove(path) or removed
                finally:
                    lease.release()
        rows.append({"run_id": run_id, "status": row["status"], "age_days": round(age, 1),
                     "paths": [str(path.relative_to(project)) if project in path.parents else str(path) for path in paths],
                     "removed": removed, **({"reason": reason} if reason else {}),
                     **({"local_evidence": evidence} if evidence else {})})
    return rows


def prune_text(rows: List[dict], apply: bool) -> str:
    if not rows:
        return "no runs to prune"
    out = [f"{row['run_id']}: {row['status']}, {row['age_days']} day(s) old, "
           f"{('skipped: ' + row['reason']) if row.get('reason') else 'removed' if row['removed'] else 'would remove'} "
           f"{', '.join(row['paths'])}"
           + (f"; warning: {len(row['local_evidence'])} local evidence file(s) of the run go with it"
              if row.get("local_evidence") else "") for row in rows]
    if not apply:
        out.append(f"{len(rows)} run(s) would be removed; repeat with --apply")
    return "\n".join(out)
