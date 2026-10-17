"""The list of conductor runs of a project: ``orch conduct runs [--limit N] [--json]``.

Reads only the run folders of the orch state of the project (``run.json`` and ``progress.jsonl``): the id, the status
and reason code of the journal, when the run started, the pieces of work it carries and how often it was resumed.
Newest first, then by run id; an empty project gives an empty list; a run whose ``run.json`` cannot be read is listed as
``{run_id, status: "unreadable"}`` instead of failing the command.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from orch.conductor import progress
from orch.conductor.infrastructure.files import RUN_FILE, runs_root


def _row(directory: Path) -> dict:
    run_id = directory.name
    try:
        doc = json.loads((directory / RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {"run_id": run_id, "status": "unreadable"}
    if not isinstance(doc, dict):
        return {"run_id": run_id, "status": "unreadable"}
    lines = progress.read_lines(directory)
    found = progress.summarize(lines)
    items = [row["item"] for row in found["items"]]
    if not items and isinstance(doc.get("items"), list):
        items = [item for item in doc["items"] if isinstance(item, str)]
    return {"run_id": run_id, "status": found["status"], "reason_code": found["reason_code"],
            "created": lines[0]["ts"] if lines else None, "items": items,
            "resumes": sum(1 for line in lines if line.get("event") == "run.resume")}


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
