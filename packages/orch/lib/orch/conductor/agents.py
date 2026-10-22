"""Catalog of the agent runs of a conductor run: one folder per start of a role.

Every start of a model role (the executor, the reviewer, the report-fixer that mends a result, and so on) is an *agent run* with
an id ``agent-<run suffix>-<n>`` and the folder ``<run>/<item>/agents/<agent_run_id>/``:

- ``request.json`` is written when the role starts: ``agent_run_id``, ``role``, ``route`` (provider, model, effort), ``step``,
  ``attempt`` (of the step), ``prompt`` (the prompt file, relative to the project), ``parent_agent_run_id`` (set for the
  report-fixer: the role whose answer it mends), ``causation`` (the step that caused the start; for the advisor the
  problem it advises on, ``question:<id>@<revision>``, ``checks:<round>`` or ``findings:<review round>``) and ``started_at``;
- ``result.json`` is written when it ends, however it ends: ``exit``, ``error`` (an ``error/v1`` document when the failure was
  classified, else ``{code, message}`` of the stop), ``decisions`` (of ``retry.decide``), ``duration_s``, ``stream`` (relative
  path) and ``lingered``;
- ``usage.json``: ``input``, ``cached``, ``output`` tokens of all the attempts and ``usage_complete`` (true/false/null).

The three are ``records/v1`` kinds ``agent-request``, ``agent-result`` and ``agent-usage``: checked and replaced
crash-safely when written, checked when read (a file that does not match is ``RECORD_INVALID``).

The prompts and the streams stay where they were (``prompts/``, ``streams/``); the catalog only points at them.
A folder without ``result.json`` is a role still running, or one that died with the process.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from orch.conductor import records

AGENTS = "agents"
USAGE_KEYS = ("input", "cached", "output")


def agent_id(run_id: str, number: int) -> str:
    """``agent-<run suffix>-<n>`` for the conductor run ``cnd-<suffix>``."""
    return f"agent-{run_id[4:] if run_id.startswith('cnd-') else run_id}-{number}"


def _write(path: Path, doc: dict, kind: str) -> None:
    records.write(path, doc, kind)


def start(item_directory: Path, agent: str, *, role: str, route: dict, step: str, attempt: int, prompt: str,
          parent: Optional[str], started_at: str, causation: Optional[str] = None) -> dict:
    """Write ``request.json``; the returned dict is the handle the engine keeps until :func:`finish`."""
    directory = Path(item_directory) / AGENTS / agent
    request = {"agent_run_id": agent, "role": role, "route": route, "step": step, "attempt": attempt, "prompt": prompt,
               "causation": causation or step, "started_at": started_at}
    if parent:
        request["parent_agent_run_id"] = parent
    _write(directory / "request.json", request, "agent-request")
    return {"id": agent, "directory": directory, "role": role, "step": step, "parent": parent,
            "usage": dict.fromkeys(USAGE_KEYS, 0)}


def add_usage(handle: dict, usage: dict) -> None:
    for key in USAGE_KEYS:
        handle["usage"][key] += int(usage.get(key, 0))


def finish(handle: dict, *, exit_code: Optional[int], error: Optional[dict], decisions: list, duration_s: float,
           stream: Optional[str], lingered: bool) -> None:
    """Write ``result.json`` and ``usage.json``."""
    result = {"exit": exit_code, "decisions": decisions, "duration_s": round(duration_s, 1), "stream": stream,
              "lingered": bool(lingered)}
    if error:
        result["error"] = error
    _write(handle["directory"] / "result.json", result, "agent-result")
    _write(handle["directory"] / "usage.json", {**handle["usage"], "usage_complete": handle.get("usage_complete")},
           "agent-usage")


def orphan(directory: Path) -> bool:
    """Close an unfinished agent on resume, preserving any result and usage already recorded.

    The interrupted process cannot supply an exit, duration or final usage, so none is invented.
    Return whether a new result was written (also the guard against duplicate failure events).
    """
    path = Path(directory) / "result.json"
    if path.exists():
        return False
    _write(path, {"error": {"code": "ORPHANED", "message": "the conductor died; the role was stopped on resume"}},
           "agent-result")
    return True


def read(item_directory: Path) -> list:
    """``[{agent_run_id, role, step, status, tokens}]`` of an item, in start order. ``status``: ``running`` (no result),
    ``failed`` (an error or a non-zero exit), else ``ok``. A request that cannot be read is skipped; a file that is not
    JSON is ``STATE_CORRUPT``, one that does not match its schema ``RECORD_INVALID``."""
    rows = []
    for request_file in sorted(Path(item_directory, AGENTS).glob("*/request.json"),
                               key=lambda path: _order(path.parent.name)):
        request = _load(request_file, "agent-request")
        if request is None:
            continue
        result = _load(request_file.parent / "result.json", "agent-result")
        usage = _load(request_file.parent / "usage.json", "agent-usage") or {}
        status = "running" if result is None else "failed" if result.get("error") or result.get("exit") else "ok"
        rows.append({"agent_run_id": request.get("agent_run_id"), "role": request.get("role"),
                     "step": request.get("step"), "status": status,
                     "tokens": {key: int(usage.get(key, 0)) for key in USAGE_KEYS}})
    return rows


def _order(name: str) -> int:
    tail = name.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _load(path: Path, kind: str) -> Optional[dict]:
    """The checked record at ``path``; ``None`` when there is none or it cannot be read (no access, a folder)."""
    try:
        return records.read(path, kind)
    except OSError:
        return None
