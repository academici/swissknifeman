"""Durable files for the existing review transport, never a second scheduler."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time


def write(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def identity(pid: int) -> dict:
    # Linux start ticks prevent a reused PID from authorizing a signal.
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": stat[19], "state": stat[0]}
    except (OSError, IndexError):
        return {"pid": pid, "start_ticks": None}


def alive(process: dict | None) -> bool | None:
    if not process or not process.get("start_ticks"):
        return None
    observed = identity(process["pid"])
    return observed["start_ticks"] == process["start_ticks"] and observed.get("state") != "Z"


def create(directory: Path, manifest: dict) -> Path:
    number = max((int(path.name.split("-")[1]) for path in directory.glob("attempt-*")
                  if path.is_dir() and path.name.split("-")[1].isdigit()), default=0) + 1
    attempt = directory / f"attempt-{number:04d}"
    attempt.mkdir()
    write(attempt / "started.json", {"schema_version": "review-job/v1",
        "owner": identity(os.getpid()), "started_at": time.time(), "manifest": manifest})
    return attempt


def pending(directory: Path) -> list[Path]:
    return [path for path in sorted(directory.glob("attempt-*"))
            if (path / "started.json").exists() and not (path / "receipt.json").exists()]


def status(attempt: Path) -> dict:
    started = json.loads((attempt / "started.json").read_text())
    live = json.loads((attempt / "job.json").read_text()) if (attempt / "job.json").exists() else {}
    owner_alive = alive(started["owner"])
    provider_alive = alive(live.get("process"))
    saved = (attempt / "transport-result.json").exists()
    state = ("terminal-unpublished" if saved else "running" if owner_alive is True
             else "orphaned" if provider_alive is True else "unknown")
    heartbeat = None
    path = attempt / "heartbeats.jsonl"
    if path.exists():
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 8192))
            lines = stream.read().splitlines()
        if lines:
            heartbeat = json.loads(lines[-1])
    return {"schema_version": "review-job-status/v1", "status": state,
            "action": "reconcile-review" if saved else "wait" if state == "running" else "reconcile-or-cancel",
            "attempt": str(attempt), "owner_alive": owner_alive, "provider_alive": provider_alive,
            "session_id": live.get("session_id"), "request_id": live.get("request_id"),
            "phase": live.get("phase"), "updated_at": live.get("updated_at"),
            "heartbeat": heartbeat,
            "cancel_requested": (attempt / "cancel.json").exists()}


def cancel(attempt: Path) -> dict:
    write(attempt / "cancel.json", {"requested_at": time.time()})
    value = status(attempt)
    value["action"] = "waiting-cancellation"
    # The live owner sends ACP cancel and reaps its child. A dead owner cannot
    # do so: signal only an attested process group, never an arbitrary PID.
    if value["owner_alive"] is False and value["provider_alive"] is True:
        import signal
        live = json.loads((attempt / "job.json").read_text())
        pid = live["process"]["pid"]
        if os.getpgid(pid) == pid and alive(live["process"]) is True:
            os.killpg(pid, signal.SIGTERM)
    return value
