"""Start one role as a child process and read what it returned.

The prompt goes on stdin; stdout is written as it comes into the raw stream file (``<step>.jsonl`` or ``.txt``) and
stderr beside it, both under the ignored runtime folder of the run. The final text, the session, the model and the
token usage are read back from the stream by its transport: ``text`` (stdout is the answer), ``jsonl`` (the
stream-json of claude-code and grok: ``system/init`` and ``result``; the event stream of codex: ``thread.started``,
``item.completed`` agent messages and ``turn.completed``). ``acp`` is not driven by the conductor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from typing import Mapping, Optional


@dataclass
class RoleRun:
    """Outcome of one role process. ``error`` is a stable code when the run itself failed."""

    exit: Optional[int]
    text: str = ""
    session: Optional[str] = None
    model: Optional[str] = None
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0})
    duration_s: float = 0.0
    raw: Optional[str] = None
    error: Optional[str] = None
    detail: Optional[str] = None


def available(argv: list) -> bool:
    """Whether the command of ``argv`` can be started (an absolute path or a command on PATH)."""
    if not argv:
        return False
    command = argv[0]
    if os.sep in command:
        return os.path.isfile(command) and os.access(command, os.X_OK)
    return shutil.which(command) is not None


def _usage(found: object) -> dict:
    if not isinstance(found, dict):
        return {"input": 0, "output": 0}
    total_in = sum(int(found.get(key) or 0) for key in ("input_tokens", "cache_read_input_tokens",
                                                        "cache_creation_input_tokens", "cached_input_tokens")
                   if isinstance(found.get(key), int))
    total_out = int(found.get("output_tokens") or 0) if isinstance(found.get("output_tokens"), int) else 0
    return {"input": total_in, "output": total_out}


def parse_stream(transport: str, data: str) -> dict:
    """``{text, session, model, usage, is_error}`` of a captured stdout."""
    if transport == "text":
        return {"text": data.strip(), "session": None, "model": None, "usage": {"input": 0, "output": 0},
                "is_error": False}
    found = {"text": "", "session": None, "model": None, "usage": {"input": 0, "output": 0}, "is_error": False}
    messages = []
    for raw in data.splitlines():
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(doc, dict):
            continue
        kind = doc.get("type")
        if kind == "system" and doc.get("subtype") == "init":
            found["session"] = doc.get("session_id") or found["session"]
            found["model"] = doc.get("model") or found["model"]
        elif kind == "result":
            found["text"] = doc.get("result") if isinstance(doc.get("result"), str) else found["text"]
            found["session"] = doc.get("session_id") or found["session"]
            found["usage"] = _usage(doc.get("usage"))
            found["is_error"] = bool(doc.get("is_error"))
        elif kind == "thread.started":  # codex exec --json
            found["session"] = doc.get("thread_id") or found["session"]
        elif kind == "item.completed" and isinstance(doc.get("item"), dict):
            item = doc["item"]
            if item.get("type") in ("agent_message", "assistant_message") and isinstance(item.get("text"), str):
                messages.append(item["text"])
        elif kind == "turn.completed":
            usage = _usage(doc.get("usage"))
            found["usage"] = {key: found["usage"][key] + usage[key] for key in usage}
    if not found["text"] and messages:
        found["text"] = messages[-1]
    return found


def _kill(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.wait()


def run_role(argv: list, prompt: str, *, transport: str, cwd: Path, timeout_s: int, raw_path: Path,
             env: Optional[Mapping[str, str]] = None) -> RoleRun:
    """Run ``argv`` with ``prompt`` on stdin; never raises for a failure of the child."""
    if transport == "acp":
        return RoleRun(exit=None, error="TRANSPORT_UNSUPPORTED", detail="the conductor does not drive acp roles")
    if not available(argv):
        return RoleRun(exit=None, error="PROVIDER_UNAVAILABLE", detail=f"{argv[0] if argv else '-'} not found")
    raw_path = Path(raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    err_path = raw_path.with_suffix(".stderr")
    started = time.monotonic()
    with open(raw_path, "wb") as out, open(err_path, "wb") as err:
        try:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err, cwd=str(cwd),
                                       env=None if env is None else dict(env), start_new_session=True)
        except OSError as error:
            return RoleRun(exit=None, error="PROVIDER_UNAVAILABLE", detail=str(error), raw=str(raw_path))
        try:
            process.communicate(prompt.encode("utf-8"), timeout=timeout_s if timeout_s > 0 else None)
        except subprocess.TimeoutExpired:
            _kill(process)
            return RoleRun(exit=process.returncode, error="TIMEOUT", detail=f"no result within {timeout_s} s",
                           duration_s=time.monotonic() - started, raw=str(raw_path))
        except BaseException:
            _kill(process)
            raise
    duration = time.monotonic() - started
    parsed = parse_stream(transport, raw_path.read_text(encoding="utf-8", errors="replace"))
    run = RoleRun(exit=process.returncode, text=parsed["text"], session=parsed["session"], model=parsed["model"],
                  usage=parsed["usage"], duration_s=duration, raw=str(raw_path))
    if process.returncode != 0 or parsed["is_error"]:
        tail = err_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
        run.error, run.detail = "ROLE_FAILED", f"exit {process.returncode}" + (f": {' | '.join(tail)}" if tail else "")
    elif not run.text:
        run.error, run.detail = "ROLE_OUTPUT_EMPTY", "the role returned no final text"
    return run
