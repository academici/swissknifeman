#!/usr/bin/env python3
"""Materialize the two frozen D74 no-write admissions without provider activity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "supervisor"))
from artifex import dispatch  # noqa: E402


IDENTITIES = {
    "p3-smoke-codex-v1": ("p3-smoke-run-codex-001", "p3-smoke-codex-v1:1", "1" * 64),
    "p3-smoke-claude-code-v1": ("p3-smoke-run-claude-code-001", "p3-smoke-claude-code-v1:1", "2" * 64),
}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(tasks_path: Path, grants_path: Path, replay_path: Path, manifest_index_path: Path,
          admission_index_path: Path, output_dir: Path) -> None:
    tasks_doc, grants_doc = _load(tasks_path), _load(grants_path)
    if set(tasks_doc) != {"schema_version", "set_version", "tasks"} or tasks_doc.get("schema_version") != "dispatch-task-set-v1":
        raise ValueError("task set shape")
    if set(grants_doc) != {"schema_version", "set_version", "grants"} or grants_doc.get("schema_version") != "dispatch-grant-set-v1":
        raise ValueError("grant set shape")
    tasks, grants = tasks_doc.get("tasks"), grants_doc.get("grants")
    if not isinstance(tasks, list) or not isinstance(grants, list) or len(tasks) != 2 or len(grants) != 2:
        raise ValueError("exactly two frozen rows required")
    grants_by_task = {row.get("task_id"): row for row in grants if isinstance(row, dict)}
    if len(grants_by_task) != 2:
        raise ValueError("duplicate grant task")
    records, manifest_rows, admission_rows = [], [], []
    for task in sorted(tasks, key=lambda row: row.get("task_id", "")):
        if not isinstance(task, dict):
            raise ValueError("task row")
        task_id = task.get("task_id")
        if task_id not in IDENTITIES or task_id not in grants_by_task:
            raise ValueError("unexpected smoke task")
        run_id, slice_id, key = IDENTITIES[task_id]
        row = {"schema_version": "dispatch-replay-v1", "run_id": run_id, "task_id": task_id,
               "grant_id": grants_by_task[task_id].get("grant_id"), "events": []}
        records.append(row)
        result = dispatch.project(task, grants_by_task[task_id], row["events"], run_id=run_id,
                                  slice_id=slice_id, attempt=1, idempotency_key=key)
        manifest, admission = result["manifest"], result["admission"]
        filename = f"{task['provider']}.json"
        target = output_dir / filename
        _write(target, admission)
        base = admission_index_path.parent.parent.parent
        relative = target.resolve().relative_to(base.resolve()).as_posix()
        admission_rows.append({"task_id": task_id, "provider": task["provider"], "path": relative,
                               "sha256": dispatch.file_hash(target), "admission_hash": admission["admission_hash"]})
        manifest_rows.append({"task_id": task_id, "provider": task["provider"], "run_id": run_id,
                              "slice_id": slice_id, "manifest_hash": manifest["manifest_hash"],
                              "task_hash": task["task_hash"], "grant_hash": grants_by_task[task_id]["grant_hash"]})
    replay_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")
    _write(manifest_index_path, {"schema_version": "p3-smoke-dispatch-manifest-index-v1", "index_version": "1.0.0",
                                 "manifests": manifest_rows})
    _write(admission_index_path, {"schema_version": "p3-smoke-admission-index-v1", "index_version": "1.0.0",
                                  "admissions": admission_rows})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", required=True, type=Path); parser.add_argument("--grants", required=True, type=Path)
    parser.add_argument("--replay", required=True, type=Path); parser.add_argument("--manifest-index", required=True, type=Path)
    parser.add_argument("--admission-index", required=True, type=Path); parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.tasks, args.grants, args.replay, args.manifest_index, args.admission_index, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError, dispatch.DispatchRefusal) as exc:
        print(f"p3-smoke admissions: ERROR: {exc}", file=sys.stderr)
        return 1
    print("p3-smoke admissions: OK (2 provider-specific no-write admissions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
