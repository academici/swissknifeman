"""Detached conductor processes and their nonce-bound, validated startup acknowledgement.

A successful spawn proves only that a process exists. Only the child, after acquiring ownership and opening its
state, can acknowledge startup. The caller waits for that acknowledgement, never for the run to finish.

A child of the autopilot also passes the startup fence (``startup_fence``) before it takes the checkout lock and the run
lease: under ``<runs root>/autopilot-launch.lock`` it reads the launch intent of ``autopilot.json`` and starts only when the
intent still names its run and launch id; it writes its started acknowledgement before it lets the lock go. Order of locks:
the launch lock, the checkout lock, the run lease.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from typing import Optional

from aicore.util.lock import FileLock

from orch.conductor import contract, process, records, runs
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import runs_root

RUN_ID = re.compile(r"cnd-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
ACK_RUN_ID = re.compile(r"cnd-[A-Za-z0-9-]+")
NONCE = re.compile(r"[0-9a-f]{16}")
ACK_TIMEOUT_S = 20
_ACK_ENV = ("SKM_ORCH_DETACH_ACK", "SKM_ORCH_DETACH_NONCE")
STATE_ENV, LAUNCH_ENV = "SKM_ORCH_AUTOPILOT_STATE", "SKM_ORCH_AUTOPILOT_LAUNCH_ID"
_FENCE_ENV = (STATE_ENV, LAUNCH_ENV)
GATE_ENV = "SKM_ORCH_FENCE_GATE"  # fault injection of the tests: ``<before|locked|ack>:<fifo>`` holds the child there
LAUNCH_LOCK = "autopilot-launch.lock"
LAUNCH_LOCK_WAIT_S = 30  # the launch lock is held only for short transitions, never while a child or an ack is awaited
CANCELLED = "AUTOPILOT_LAUNCH_CANCELLED"
_FENCE: list = []  # the launch lock this process holds while its startup is fenced
_CHILDREN: list = []  # retain Popen handles and reap with poll, without waiting for a detached run
CONDUCT = Path(__file__).resolve().parents[4] / "scripts" / "conduct.py"


def subprocess_env(environ: dict | None = None) -> dict:
    """Copy a role's environment without the conductor's launch authority, metadata or acknowledgement channel."""
    return {name: value for name, value in (os.environ if environ is None else environ).items()
            if name not in ("SKM_ORCH_DETACHED", "SKM_ORCH_LAUNCHER", *_ACK_ENV, *_FENCE_ENV, GATE_ENV)}


def poll_children() -> None:
    _CHILDREN[:] = [child for child in _CHILDREN if child.poll() is None]


def spawn(argv: list, *, project: Path, launcher: str, log_dir: Path, env: dict | None = None,
          ack_nonce: Optional[str] = None) -> dict:
    """Start a session with no terminal and a private ``<run>.log``. ``env`` supplies per-launch variables.

    ``argv`` must name the run with ``--run-id`` (new run) or ``--run`` (resume). The child acknowledges its startup in
    ``<log_dir>/<run>.<nonce>.ack.json``; ``ack_nonce`` is generated when not given (the autopilot gives its launch id).
    Return ``{pid, start_ticks, log, ack, nonce}``; neither process completion nor run ownership is implied by this result.
    """
    run_id = next((token.split("=", 1)[1] for token in argv if token.startswith(("--run=", "--run-id="))), None)
    if run_id is None:
        flag = "--run-id" if "--run-id" in argv else "--run"
        run_id = argv[argv.index(flag) + 1]
    if ACK_RUN_ID.fullmatch(run_id) is None:
        raise Stop("RUN_UNKNOWN", "detached argv must name a safe conductor run id")
    nonce = secrets.token_hex(8) if ack_nonce is None else ack_nonce
    if NONCE.fullmatch(nonce) is None:
        raise Stop("RECORD_INVALID", "the acknowledgement nonce of a detached launch must be 16 lowercase hex digits")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir.chmod(0o700)
    log, ack = log_dir / f"{run_id}.log", log_dir / f"{run_id}.{nonce}.ack.json"
    child_env = {key: value for key, value in os.environ.items() if key not in (*_ACK_ENV, *_FENCE_ENV)}
    child_env.update(env or {})
    child_env.update(SKM_ORCH_DETACHED="1", SKM_ORCH_LAUNCHER=launcher, SKM_ORCH_DETACH_ACK=str(ack),
                     SKM_ORCH_DETACH_NONCE=nonce)
    poll_children()
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as output:
        child = subprocess.Popen(argv, cwd=project, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True, close_fds=True, env=child_env)
    _CHILDREN.append(child)
    return {"pid": child.pid, "start_ticks": process.start_ticks(child.pid), "log": str(log), "ack": str(ack),
            "nonce": nonce}


def launch_lock(root: Path, timeout: float) -> Optional[FileLock]:
    """``<runs root>/autopilot-launch.lock`` held by the caller, ``None`` when it stays busy for ``timeout`` seconds."""
    Path(root).mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = FileLock(Path(root) / LAUNCH_LOCK)
    return lock if lock.acquire(blocking=True, timeout=timeout) else None


def _gate(point: str) -> None:
    at, _, fifo = os.environ.get(GATE_ENV, "").partition(":")
    if at == point and fifo:
        os.environ.pop(GATE_ENV)
        os.close(os.open(fifo, os.O_RDONLY))  # blocks until the test opens the FIFO for writing


def _intent_problem(state: Path, run_id: str, launch_id: str) -> Optional[str]:
    """Why ``autopilot.json`` does not hold the launch intent of this child (``None``: it does)."""
    if os.environ.get("SKM_ORCH_DETACH_NONCE", launch_id) != launch_id:
        return "the acknowledgement nonce differs from the launch id"
    try:
        current = ((records.read(state, "autopilot-state") or {}).get("current")) or {}
    except Stop as error:
        return f"{error.code}: {error.message}"
    if (current.get("run_id"), current.get("launch_id"), current.get("state")) == (run_id, launch_id, "launching"):
        return None
    return (f"the intent is {current['state']} launch {current['launch_id']} of run {current['run_id']}" if current
            else "the autopilot has no launch intent")


@contextmanager
def startup_fence(project: Path, run_id: str):
    """The startup fence of a child of the autopilot (``SKM_ORCH_AUTOPILOT_STATE`` and ``SKM_ORCH_AUTOPILOT_LAUNCH_ID`` set),
    entered before the checkout lock and the run lease: take the launch lock, require ``current`` of the autopilot state to be
    ``launching`` with this run and launch id, else ``AUTOPILOT_LAUNCH_CANCELLED`` (nothing is created, claimed or started).
    The lock stays held until ``acknowledge`` (or the end of the block). A fence entered again in the same process (``continue``
    goes through ``resume``) and any other launch pass through unchanged."""
    state, launch_id = (os.environ.get(key) for key in _FENCE_ENV)
    if _FENCE or not (state or launch_id):
        yield
        return
    root = runs_root(Path(project))
    try:
        if not state or not launch_id or Path(state).resolve().parent != root.resolve():
            raise Stop(CANCELLED, "the autopilot launch context is incomplete or names another runs root; nothing was started")
        _gate("before")
        lock = launch_lock(root, LAUNCH_LOCK_WAIT_S)
        if lock is None:
            raise Stop(CANCELLED, f"{root / LAUNCH_LOCK} stayed busy for {LAUNCH_LOCK_WAIT_S} s: the launch intent cannot be "
                       "confirmed; nothing was started")
        _FENCE.append(lock)
        _gate("locked")
        problem = _intent_problem(Path(state), run_id, launch_id)
        if problem:
            raise Stop(CANCELLED, f"launch {launch_id} of run {run_id} is not the launch intent of the autopilot ({problem}): "
                       "it was cancelled or replaced; nothing was started")
        yield
    finally:
        release_fence()


def release_fence() -> None:
    while _FENCE:
        _FENCE.pop().release()


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
    _gate("ack")
    _write_ack("started", run_id=run_id)


def refuse(code: str, message: str) -> None:
    """Refuse startup if no acknowledgement has been sent yet. Later run failures keep the started ack."""
    _write_ack("refused", code=code, message=message)


def _write_ack(status: str, *, run_id: str | None = None, code: str | None = None, message: str | None = None) -> None:
    context = _ack_context()
    if context is not None:
        path, nonce, expected = context
        if run_id is not None and run_id != expected:
            raise Stop("RECORD_INVALID", "detached acknowledgement run id differs from the requested run")
        doc = {"nonce": nonce, "run_id": expected, "pid": os.getpid(), "start_ticks": process.start_ticks(os.getpid()),
               "status": status, "at": clock.utc_now()}
        if status == "refused":
            doc.update(code=code, message=runs.display(message))
        records.write(path, doc, "detach-ack")
    for key in (*_ACK_ENV, *_FENCE_ENV):  # roles and nested launches must not inherit the parent's acknowledgement channel
        os.environ.pop(key, None)
    release_fence()  # the started acknowledgement is on disk under the launch lock: the run keeps its own locks


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
    log_dir = runs_root(project) / "detached"
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
        child = spawn(command, project=project, launcher=launcher, log_dir=log_dir)
        wait_ack(Path(child["ack"]), child["nonce"], run_id, child)
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
