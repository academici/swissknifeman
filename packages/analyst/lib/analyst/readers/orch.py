"""Reader of what orch leaves behind, through its contracts only (knowledge/p12-observability#analyst).

Three sources, none of them an internal file of orch beyond its published formats:

* the event journal (``event/v1``, types ``orch.*``; data per ``orch/schemas/event-data/v1``), read through
  ``aicore.ext.events``;
* the artifacts of a piece in ``<project>/plans/<plan>/artifacts/<item>/``: ``stage-report.json`` (``stage-report``)
  and ``review-verdict.json`` (``orch-conductor-review-verdict/v1``);
* the run folder of the conductor (``<project state>/orch/conductor/<run>/<item>/``): ``risk.json`` and the
  ``prompts/*.manifest.json`` (``prompt-manifest/v1``).

A missing or unreadable source gives an empty part and a line in ``problems``; nothing is guessed. The result is plain
data (no ids or times of events) so a report on it is reproducible.
"""
import json
from pathlib import Path

from aicore.ext import events as aicore_events
from aicore.state.locations import project_state_dir

EVENT_TYPES = ("orch.*",)


def _load(path, problems):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        problems.append(f"{path}: {exc}")
        return None


def read_events(project, run=None, problems=None):
    """``[{type, subject, data}]`` of the ``orch.*`` events (of run ``run`` when given), in journal order."""
    problems = [] if problems is None else problems
    try:
        found, broken = aicore_events.read_events(project, types=list(EVENT_TYPES))
    except aicore_events.ExtError as exc:
        problems.append(f"event journal: {exc}")
        return []
    problems.extend(f"event journal offset {row['offset']}: {row['code']}" for row in broken)
    rows = [{"type": event.type, "subject": event.subject, "data": dict(event.data or {})} for event in found]
    if run:
        rows = [row for row in rows if row["data"].get("run_id") == run]
    return rows


def read_artifacts(project, plan, problems):
    """``{item: {stage_report, review_verdict}}`` of the artifact folders of plan ``plan``."""
    items = {}
    root = Path(project) / "plans" / plan / "artifacts"
    if not root.is_dir():
        problems.append(f"no artifact folder {root}")
        return items
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        row = {name: _load(folder / file, problems) for name, file in
               (("stage_report", "stage-report.json"), ("review_verdict", "review-verdict.json"))}
        if any(row.values()):
            items[folder.name] = row
    return items


def read_runs(project, run, problems):
    """``{item: {risk, manifests: [prompt-manifest/v1]}}`` of one conductor run, or of every run when ``run`` is None."""
    items = {}
    root = project_state_dir(project, "orch") / "conductor"
    if not root.is_dir():
        return items
    for folder in sorted(path for path in root.iterdir() if path.is_dir() and (run is None or path.name == run)):
        for item_dir in sorted(path for path in folder.iterdir() if path.is_dir()):
            manifests = [_load(path, problems) for path in sorted((item_dir / "prompts").glob("*.manifest.json"))]
            risk = _load(item_dir / "risk.json", problems)
            if risk or manifests:
                row = items.setdefault(item_dir.name, {"risk": None, "manifests": []})
                row["risk"] = risk or row["risk"]
                row["manifests"].extend(doc for doc in manifests if isinstance(doc, dict))
    return items


def read(project, run=None, plan=None):
    """``{events, artifacts, runs, problems}`` of a project."""
    problems = []
    events = read_events(project, run, problems)
    return {"events": events, "artifacts": read_artifacts(project, plan, problems) if plan else {},
            "runs": read_runs(project, run, problems), "problems": problems}
