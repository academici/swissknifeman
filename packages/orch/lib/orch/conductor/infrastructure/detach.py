"""Detached conductor processes and their nonce-bound, validated startup acknowledgement.

A successful spawn proves only that a process exists. Only the child, after acquiring ownership and opening its
state, can acknowledge startup. The caller waits for that acknowledgement, never for the run to finish.
"""
from __future__ import annotations

from functools import wraps
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

from orch.conductor import contract, process, records, runs
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import runs_root

RUN_ID = re.compile(r"cnd-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
ACK_RUN_ID = re.compile(r"cnd-[A-Za-z0-9-]+")
ACK_TIMEOUT_S = 20
_ACK_ENV = ("SKM_ORCH_DETACH_ACK", "SKM_ORCH_DETACH_NONCE")
_CHILDREN: list = []  # retain Popen handles and reap with poll, without waiting for a detached run
CONDUCT = Path(__file__).resolve().parents[4] / "scripts" / "conduct.py"


def subprocess_env(environ: dict | None = None) -> dict:
    """Copy a role's environment without the conductor's launch authority, metadata or acknowledgement channel."""
    return {name: value for name, value in (os.environ if environ is None else environ).items()
            if name not in ("SKM_ORCH_DETACHED", "SKM_ORCH_LAUNCHER", *_ACK_ENV)}


def poll_children() -> None:
    _CHILDREN[:] = [child for child in _CHILDREN if child.poll() is None]


def spawn(argv: list, *, project: Path, launcher: str, log_dir: Path, env: dict | None = None) -> dict:
    """Start a session with no terminal and a private ``<run>.log``. ``env`` supplies per-launch handshake variables.

    ``argv`` must name the run with ``--run-id`` (new run) or ``--run`` (resume). Return ``{pid, start_ticks, log}``;
    neither process completion nor run ownership is implied by this result.
    """
    run_id = next((token.split("=", 1)[1] for token in argv if token.startswith(("--run=", "--run-id="))), None)
    if run_id is None:
        flag = "--run-id" if "--run-id" in argv else "--run"
        run_id = argv[argv.index(flag) + 1]
    if ACK_RUN_ID.fullmatch(run_id) is None:
        raise Stop("RUN_UNKNOWN", "detached argv must name a safe conductor run id")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir.chmod(0o700)
    log = log_dir / f"{run_id}.log"
    child_env = {key: value for key, value in os.environ.items() if key not in _ACK_ENV}
    child_env.update(env or {})
    child_env.update(SKM_ORCH_DETACHED="1", SKM_ORCH_LAUNCHER=launcher)
    poll_children()
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as output:
        child = subprocess.Popen(argv, cwd=project, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True, env=child_env)
    _CHILDREN.append(child)
    return {"pid": child.pid, "start_ticks": process.start_ticks(child.pid), "log": str(log)}


def _ack_context() -> tuple | None:
    path, nonce = (os.environ.get(key) for key in _ACK_ENV)
    if os.environ.get("SKM_ORCH_DETACHED") != "1" or not path or not nonce:
        return None
    name = Path(path).name
    suffix = f".{nonce}.ack.json"
    run_id = name[:-len(suffix)] if name.endswith(suffix) else ""
    if ACK_RUN_ID.fullmatch(run_id) is None or re.fullmatch(r"[0-9a-f]{16}", nonce) is None:
        raise Stop("RECORD_INVALID", "invalid internal detached acknowledgement context")
    return Path(path), nonce, run_id


def acknowledge(run_id: str) -> None:
    """Called only under checkout lock + run lease, after state initialization succeeded."""
    _write_ack("started", run_id=run_id)


def refuse(code: str, message: str) -> None:
    """Refuse startup if no acknowledgement has been sent yet. Later run failures keep the started ack."""
    _write_ack("refused", code=code, message=message)


def _write_ack(status: str, *, run_id: str | None = None, code: str | None = None, message: str | None = None) -> None:
    context = _ack_context()
    if context is None:
        return
    path, nonce, expected = context
    if run_id is not None and run_id != expected:
        raise Stop("RECORD_INVALID", "detached acknowledgement run id differs from the requested run")
    doc = {"nonce": nonce, "run_id": expected, "pid": os.getpid(), "start_ticks": process.start_ticks(os.getpid()),
           "status": status, "at": clock.utc_now()}
    if status == "refused":
        doc.update(code=code, message=runs.display(message))
    records.write(path, doc, "detach-ack")
    for key in _ACK_ENV:  # roles and nested launches must not inherit the parent's acknowledgement channel
        os.environ.pop(key, None)


def refuse_errors(function):
    """A startup refusal must reach the waiting parent even when ownership or state validation failed."""
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except BaseException as error:
            code = getattr(error, "code", "CONDUCTOR_CRASHED")
            refuse(code if isinstance(code, str) else "DETACH_FAILED", getattr(error, "message", str(error)))
            raise
    return guarded


def _exited(pid: int) -> bool:
    child = next((child for child in _CHILDREN if child.pid == pid), None)
    return child is not None and child.poll() is not None


def wait_ack(path: Path, nonce: str, run_id: str, child: dict) -> dict:
    """A matching started ack is success even if the run already finished. A stale run.json proves nothing."""
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while True:
        exited = _exited(child["pid"])  # probe before reading: an ack written just before exit must still win
        ack = records.read(path, "detach-ack")
        if ack and (ack["nonce"], ack["pid"], ack["run_id"]) == (nonce, child["pid"], run_id):
            if ack["status"] == "started":
                return ack
            raise Stop(ack.get("code", "DETACH_FAILED"), ack.get("message", "child refused startup"))
        if exited:
            try:
                with open(child["log"], "rb") as log:
                    log.seek(0, os.SEEK_END)
                    log.seek(max(0, log.tell() - 16384))
                    tail = runs.display(log.read().decode("utf-8", "replace").splitlines()[-20:])
            except OSError:
                tail = []
            raise Stop("DETACH_FAILED", f"child exited before acknowledging; log {child['log']}"
                       + ("\n" + "\n".join(tail) if tail else ""))
        left = deadline - time.monotonic()
        if left <= 0:
            raise Stop("DETACH_FAILED", f"no acknowledgement within 20 s (pid {child['pid']} may still run); log {child['log']}")
        time.sleep(min(0.1, left))


def launch(argv: list, *, project: Path, run_id: str, launcher: str, new_run: bool) -> int:
    """The CLI parent: reconstruct this command, start its child and print validated JSON only after its ack."""
    nonce = secrets.token_hex(8)
    log_dir = runs_root(project) / "detached"
    ack = log_dir / f"{run_id}.{nonce}.ack.json"
    command = [sys.executable, str(CONDUCT), "--project", str(project)]
    skip = False
    path_value = False
    path_flags = {"--config", "--input", "--options", "--model-catalog", "--plans-root", "--allow-path"}
    for token in argv:
        if skip:
            skip = False
        elif path_value:
            command.append(str(Path(token).resolve()))
            path_value = False
        elif token == "--project":
            skip = True
        elif token != "--detach" and not token.startswith("--project="):
            flag, separator, value = token.partition("=")
            command.append(f"{flag}={Path(value).resolve()}" if flag in path_flags and separator else token)
            path_value = token in path_flags
    if new_run:
        command += ["--run-id", run_id]
    try:
        child = spawn(command, project=project, launcher=launcher, log_dir=log_dir,
                      env={"SKM_ORCH_DETACH_ACK": str(ack), "SKM_ORCH_DETACH_NONCE": nonce})
        wait_ack(ack, nonce, run_id, child)
        doc = {"$schema": "urn:swissknifeman:orch:conductor:detach-result:v1", "run_id": run_id,
               "pid": child["pid"], "log": child["log"], "detached": True}
        problems = contract.problems(doc, "detach-result")
        if problems:
            raise Stop("RECORD_INVALID", "; ".join(problems))
        print(json.dumps(doc), flush=True)
        return 0
    except (OSError, Stop) as error:
        print(runs.display(f"{getattr(error, 'code', 'DETACH_FAILED')}: {getattr(error, 'message', error)}"), file=sys.stderr)
        return 1
