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
- ``usage.json``: ``input``, ``cached``, ``output`` tokens of all the attempts of the agent run.

The prompts and the streams stay where they were (``prompts/``, ``streams/``); the catalog only points at them.
A folder without ``result.json`` is a role still running, or one that died with the process.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

AGENTS = "agents"
USAGE_KEYS = ("input", "cached", "output")


def agent_id(run_id: str, number: int) -> str:
    """``agent-<run suffix>-<n>`` for the conductor run ``cnd-<suffix>``."""
    return f"agent-{run_id[4:] if run_id.startswith('cnd-') else run_id}-{number}"


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def start(item_directory: Path, agent: str, *, role: str, route: dict, step: str, attempt: int, prompt: str,
          parent: Optional[str], started_at: str, causation: Optional[str] = None) -> dict:
    """Write ``request.json``; the returned dict is the handle the engine keeps until :func:`finish`."""
    directory = Path(item_directory) / AGENTS / agent
    request = {"agent_run_id": agent, "role": role, "route": route, "step": step, "attempt": attempt, "prompt": prompt,
               "causation": causation or step, "started_at": started_at}
    if parent:
        request["parent_agent_run_id"] = parent
    _write(directory / "request.json", request)
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
    _write(handle["directory"] / "result.json", result)
    _write(handle["directory"] / "usage.json", handle["usage"])


def read(item_directory: Path) -> list:
    """``[{agent_run_id, role, step, status, tokens}]`` of an item, in start order. ``status``: ``running`` (no result),
    ``failed`` (an error or a non-zero exit), else ``ok``."""
    rows = []
    for request_file in sorted(Path(item_directory, AGENTS).glob("*/request.json"),
                               key=lambda path: _order(path.parent.name)):
        try:
            request = json.loads(request_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        result = _load(request_file.parent / "result.json")
        usage = _load(request_file.parent / "usage.json") or {}
        status = "running" if result is None else "failed" if result.get("error") or result.get("exit") else "ok"
        rows.append({"agent_run_id": request.get("agent_run_id"), "role": request.get("role"),
                     "step": request.get("step"), "status": status,
                     "tokens": {key: int(usage.get(key, 0)) for key in USAGE_KEYS}})
    return rows


def _order(name: str) -> int:
    tail = name.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _load(path: Path) -> Optional[dict]:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None
