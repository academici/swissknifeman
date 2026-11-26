"""RunStore: command runs in ``gui.db`` (migration 2), their transitions and their ``run/v1`` documents.

Every state change goes through :meth:`RunStore.transition`: one ``BEGIN IMMEDIATE`` transaction checks
``run_states.can_transition``, updates the row and appends a ``run_transitions`` row; the ``publish`` callback sees
the new state only after ``COMMIT`` (I11). :meth:`RunStore.mark_lost` runs once when the backend starts: no run of
an earlier backend is ever watched again; a process of such a run that is still alive (same PID and start time) is
killed with its group.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from . import procinfo, run_states
from ..storage.db import now

CONTRACT = "urn:swissknifeman:gui:run:v1"

# Keyword fields of transition() and their columns; JSON fields are stored as text.
_JSON_FIELDS = {"executable": "executable_json", "argv_redacted": "argv_json", "permission": "permission_json",
                "log": "log_json", "error": "error_json"}
_PLAIN_FIELDS = {"started_at": "started_at", "finished_at": "finished_at", "pid": "pid", "pid_start": "pid_start",
                 "cwd": "cwd"}


def new_run_id() -> str:
    return "run-" + uuid.uuid4().hex


def _loads(text: Optional[str]) -> Any:
    return None if text is None else json.loads(text)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def document(row: sqlite3.Row) -> Dict[str, Any]:
    """The ``run/v1`` document of a row (internal fields such as the PID stay out)."""
    doc: Dict[str, Any] = {"$schema": CONTRACT, "run_id": row["run_id"], "command": row["command"],
                           "owner": row["owner"], "state": row["state"], "dry_run": bool(row["dry_run"]),
                           "context": _loads(row["context_json"]), "input": _loads(row["input_json"]),
                           "created_at": row["created_at"]}
    for name in ("started_at", "finished_at", "cwd"):
        if row[name] is not None:
            doc[name] = row[name]
    if row["exit_code"] is not None or row["exit_signal"] is not None:
        doc["exit"] = {"code": row["exit_code"], "signal": row["exit_signal"]}
    for name in ("executable", "argv_redacted"):
        value = _loads(row[_JSON_FIELDS[name]])
        if value is not None:
            doc[name] = value
    doc["actor"] = _loads(row["actor_json"])
    doc["permission"] = _loads(row["permission_json"])
    doc["log"] = _loads(row["log_json"])
    error = _loads(row["error_json"])
    if error is not None:
        doc["error"] = error
    doc["correlation_id"] = row["correlation_id"]
    return doc


def frame_run(doc: Mapping[str, Any]) -> Dict[str, Any]:
    """The ``run`` object of a ``stream/v1`` run frame."""
    out = {"run_id": doc["run_id"], "state": doc["state"]}
    for name in ("exit", "finished_at"):
        if name in doc:
            out[name] = doc[name]
    return out


class RunStore:
    """Runs over an open ``gui.db``; ``lock`` serializes this connection between threads."""

    def __init__(self, conn: sqlite3.Connection, *, lock: Optional[threading.RLock] = None,
                 publish: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.conn = conn
        self.lock = lock or threading.RLock()
        self.publish = publish

    def create(self, *, command: str, owner: str, dry_run: bool, context: Mapping[str, Any],
               input: Mapping[str, Any], actor: Mapping[str, str], permission: Mapping[str, Any],
               correlation_id: str) -> Dict[str, Any]:
        """A new run in ``queued``; ``input`` must already be redacted."""
        run_id = new_run_id()
        created = now()
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "INSERT INTO runs (run_id, command, owner, state, dry_run, project_id, context_json, input_json, "
                    "created_at, actor_json, permission_json, log_json, correlation_id) "
                    "VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, command, owner, int(dry_run), context.get("project_id"), _dumps(dict(context)),
                     _dumps(dict(input)), created, _dumps(dict(actor)), _dumps(dict(permission)),
                     _dumps({"stdout_bytes": 0, "stderr_bytes": 0, "truncated": False}), correlation_id))
                self.conn.execute("INSERT INTO run_transitions (run_id, seq, from_state, to_state, at) "
                                  "VALUES (?, 0, NULL, 'queued', ?)", (run_id, created))
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        doc = self.get(run_id)
        self._publish(doc)
        return doc

    def transition(self, run_id: str, target: str, *, exit: Optional[Mapping[str, Any]] = None,
                   **fields: Any) -> Dict[str, Any]:
        """Move a run to ``target`` and store ``fields``; ``RuntimeError`` for a transition the table forbids."""
        unknown = set(fields) - set(_JSON_FIELDS) - set(_PLAIN_FIELDS)
        if unknown:
            raise ValueError(f"unknown run fields {sorted(unknown)}")
        at = now()
        if run_states.is_terminal(target):
            fields.setdefault("finished_at", at)
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute("SELECT state FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                if row is None:
                    raise KeyError(run_id)
                source = row["state"]
                if not run_states.can_transition(source, target):
                    raise RuntimeError(f"run {run_id}: {source} -> {target} is not a run transition")
                assignments, values = ["state = ?"], [target]
                for name, value in fields.items():
                    column = _JSON_FIELDS.get(name) or _PLAIN_FIELDS[name]
                    assignments.append(f"{column} = ?")
                    values.append(_dumps(value) if name in _JSON_FIELDS else value)
                if exit is not None:
                    assignments += ["exit_code = ?", "exit_signal = ?"]
                    values += [exit.get("code"), exit.get("signal")]
                self.conn.execute(f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ?", (*values, run_id))
                seq = self.conn.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM run_transitions WHERE run_id = ?",
                                        (run_id,)).fetchone()[0]
                self.conn.execute("INSERT INTO run_transitions (run_id, seq, from_state, to_state, at) "
                                  "VALUES (?, ?, ?, ?, ?)", (run_id, seq, source, target, at))
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        doc = self.get(run_id)
        self._publish(doc)
        return doc

    def update(self, run_id: str, **fields: Any) -> None:
        """Store fields without a state change (for example the log sizes while a run is going)."""
        if not fields:
            return
        assignments, values = [], []
        for name, value in fields.items():
            column = _JSON_FIELDS.get(name) or _PLAIN_FIELDS[name]
            assignments.append(f"{column} = ?")
            values.append(_dumps(value) if name in _JSON_FIELDS else value)
        with self.lock:
            self.conn.execute(f"UPDATE runs SET {', '.join(assignments)} WHERE run_id = ?", (*values, run_id))

    def _publish(self, doc: Dict[str, Any]) -> None:
        if self.publish is not None:
            self.publish(doc)

    def row(self, run_id: str) -> Optional[sqlite3.Row]:
        with self.lock:
            return self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()

    def get(self, run_id: str) -> Dict[str, Any]:
        row = self.row(run_id)
        if row is None:
            raise KeyError(run_id)
        return document(row)

    def transitions(self, run_id: str) -> List[tuple]:
        with self.lock:
            return [(row["from_state"], row["to_state"]) for row in self.conn.execute(
                "SELECT * FROM run_transitions WHERE run_id = ? ORDER BY seq", (run_id,))]

    def list(self, *, project_id: Optional[str] = None, state: Optional[str] = None, limit: int = 50,
             before: Optional[str] = None) -> List[Dict[str, Any]]:
        """Newest first; ``before`` (a ``created_at|run_id`` cursor) continues a page."""
        clauses, values = [], []
        if project_id is not None:
            clauses.append("project_id = ?")
            values.append(project_id)
        if state is not None:
            clauses.append("state = ?")
            values.append(state)
        if before is not None:
            created, _, run_id = before.partition("|")
            clauses.append("(created_at < ? OR (created_at = ? AND run_id < ?))")
            values += [created, created, run_id]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.lock:
            rows = self.conn.execute(f"SELECT * FROM runs {where} ORDER BY created_at DESC, run_id DESC LIMIT ?",
                                     (*values, int(limit))).fetchall()
        return [document(row) for row in rows]

    def active(self) -> List[str]:
        with self.lock:
            return [row["run_id"] for row in self.conn.execute(
                "SELECT run_id FROM runs WHERE state NOT IN (%s)" % ",".join("?" * len(run_states.TERMINAL)),
                tuple(sorted(run_states.TERMINAL)))]

    def mark_lost(self, *, grace_s: float = 5.0) -> List[str]:
        """Every unfinished run of an earlier backend becomes ``lost``; a still running process of one (same PID and
        start time) is stopped with its group first. Returns the run ids."""
        lost = []
        for run_id in self.active():
            row = self.row(run_id)
            killed = False
            if row["state"] in run_states.WITH_PROCESS and row["pid"] and \
                    procinfo.same_process(int(row["pid"]), row["pid_start"]):
                killed = stop_group(int(row["pid"]), grace_s, row["pid_start"])
            error = {"code": "INTERNAL", "class": "internal", "retryable": False, "correlation_id": row["correlation_id"],
                     "message": "the backend stopped while the run was active; its outcome is unknown",
                     "details": {"orphan_killed": killed}}
            self.transition(run_id, "lost", error=error)
            lost.append(run_id)
        return lost


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_group(pgid: int, grace_s: float, started: Optional[str] = None) -> bool:
    """SIGTERM to the process group, ``grace_s`` to end, then SIGKILL; returns whether a signal was sent.
    With ``started`` the leader must still be that process (a reused PID is never signalled)."""
    if started is not None and not procinfo.same_process(pgid, started):
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline and group_alive(pgid):
        time.sleep(0.05)
    if group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return True


def read_log(runs_dir: os.PathLike, run_id: str, stream: str, cursor: int = 0, limit: int = 200
             ) -> List[Dict[str, Any]]:
    """Stored chunks of one stream from chunk number ``cursor`` on (at most ``limit``); broken lines are skipped."""
    path = os.path.join(runs_dir, run_id, f"{stream}.jsonl")
    found: List[Dict[str, Any]] = []
    try:
        handle = open(path, encoding="utf-8")
    except FileNotFoundError:
        return found
    with handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or not isinstance(record.get("chunk"), int):
                continue
            if record["chunk"] >= cursor:
                found.append({"chunk": record["chunk"], "at": record.get("at"), "text": record.get("text", ""),
                              "truncated": bool(record.get("truncated"))})
                if len(found) >= limit:
                    break
    return found


def prune_logs(runs_dir: os.PathLike, *, max_age_days: int, max_total_mb: int, keep: Iterable[str] = (),
               now_s: Optional[float] = None) -> List[str]:
    """Remove run log folders older than ``max_age_days`` (0: no age limit), then the oldest ones while the total
    is above ``max_total_mb`` (0: no size limit); ``keep`` (active runs) is never removed. Returns the removed ids."""
    import shutil

    keep = set(keep)
    moment = time.time() if now_s is None else now_s
    folders = []
    try:
        entries = list(os.scandir(runs_dir))
    except FileNotFoundError:
        return []
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False) or not entry.name.startswith("run-") or entry.name in keep:
            continue
        size = 0
        for child in os.scandir(entry.path):
            if child.is_file(follow_symlinks=False):
                size += child.stat(follow_symlinks=False).st_size
        folders.append((entry.stat(follow_symlinks=False).st_mtime, entry.name, entry.path, size))
    folders.sort()
    removed = []
    total = sum(item[3] for item in folders)
    for mtime, name, path, size in folders:
        too_old = max_age_days and moment - mtime > max_age_days * 86400
        too_big = max_total_mb and total > max_total_mb * 1024 * 1024
        if too_old or too_big:
            shutil.rmtree(path, ignore_errors=True)
            total -= size
            removed.append(name)
    return removed
