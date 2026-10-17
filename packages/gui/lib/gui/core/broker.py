"""ExecutionBroker: runs of catalog commands (decision D7); asyncio, stdlib + aicore.

``argv`` commands run as a process in a new session (``start_new_session``), so cancel, timeout and shutdown reach
the whole group: SIGTERM, ``runs.cancel_grace_s``, SIGKILL; after the leader exits, a group that is still alive is
killed. Limits (global, per project, per owner, per ``concurrency_key``) are checked before a run exists: there is no
queue (``CONCURRENCY_LIMIT``). Output is read per stream in blocks, decoded incrementally, cleaned of ANSI/OSC and
control characters, redacted while an end that could begin a secret waits for the next block (a secret is never
split by a block border), written to
``runs/<run_id>/<stream>.jsonl`` and only then published (I6). Every state change goes through the RunStore before
anyone hears of it (I11); every step writes an audit row; runs of a project are also journaled as
``gui.run.<verb>`` events. ``invoke`` commands call the owner's handler at ``gui:command`` once.
"""
from __future__ import annotations

import asyncio
import codecs
import json
import logging
import os
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from aicore.ext.environment import clean_environment
from aicore.util.redact import redact_document, redact_text

from . import argv as argv_mod, procinfo
from .plugins import enforcement
from .runs import RunStore, group_alive
from ..errors import GuiError
from ..storage.db import audit, now

log = logging.getLogger("gui.broker")

TIMEOUT_CODES = frozenset({"PROCESS_TIMEOUT", "PLUGIN_TIMEOUT"})
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ESC2 = re.compile(r"\x1b[ -/]*[0-~]")  # other escapes: ESC, intermediates, a final byte (ESC ( B, ESC 7, ...)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f\x80-\x9f]")
_MAX_CARRY = 512
_VERBS = {"running": "started", "succeeded": "succeeded", "failed": "failed", "cancelled": "cancelled",
          "timed_out": "timed_out", "lost": "lost", "denied": "denied", "failed_to_start": "failed"}


def sanitize(text: str) -> str:
    """Drop OSC and CSI sequences, other escapes and C0/C1 controls except tab, newline and carriage return."""
    text = _OSC.sub("", text)
    text = _CSI.sub("", text)
    text = _ESC2.sub("", text)
    return _CONTROL.sub("", text)


def _incomplete_escape(text: str) -> int:
    """Index of a trailing escape sequence that may continue in the next block, else -1."""
    index = text.rfind("\x1b")
    if index < 0 or len(text) - index > _MAX_CARRY:
        return -1
    tail = text[index:]
    if len(tail) == 1:
        return index
    if tail[1] == "]":
        return -1 if _OSC.match(tail) else index
    if tail[1] == "[":
        return -1 if _CSI.match(tail) else index
    return -1


def error_doc(code: str, message: str, correlation_id: str, **details: Any) -> Dict[str, Any]:
    error = GuiError(code, message, details=details or None)
    return error.envelope(correlation_id)["error"]


def signal_name(number: int) -> str:
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"SIG{number}"


class LogSink:
    """One output stream of a run: decode → clean → redact (tail held back) → JSONL file → publish."""

    def __init__(self, run: Mapping[str, Any], stream: str, folder: Path, *, limit: int, chunk_bytes: int,
                 secrets: Sequence[str], publish: Callable[..., Any]) -> None:
        self.run = run
        self.stream = stream
        self.path = folder / f"{stream}.jsonl"
        self.limit = limit
        self.chunk_bytes = chunk_bytes
        self.secrets = [value for value in secrets if value]
        self.publish = publish
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.carry = ""
        self.hold = ""
        self.chunk = 0
        self.bytes = 0
        self.truncated = False

    def feed(self, data: bytes, *, final: bool = False) -> None:
        text = self.carry + self.decoder.decode(data, final=final)
        self.carry = ""
        if not final:
            index = _incomplete_escape(text)
            if index >= 0:
                text, self.carry = text[:index], text[index:]
        buffer = self.hold + sanitize(text)
        cut = len(buffer) if final else len(buffer) - self._prefix_tail(buffer)
        cut = self._safe_cut(buffer, cut)
        out, self.hold = buffer[:cut], buffer[cut:]
        if out:
            self._write(redact_text(out, secrets=self.secrets))

    def close(self) -> None:
        self.feed(b"", final=True)

    def _prefix_tail(self, buffer: str) -> int:
        """Length of the longest end of ``buffer`` that is the beginning of a secret: only that much waits for the
        next block, so ordinary output is never delayed and a secret is never cut in two."""
        longest = 0
        for secret in self.secrets:
            for size in range(min(len(secret) - 1, len(buffer)), longest, -1):
                if buffer.endswith(secret[:size]):
                    longest = size
                    break
        return longest

    def _safe_cut(self, buffer: str, cut: int) -> int:
        """Move ``cut`` back to the start of any secret it would split."""
        moved = True
        while moved:
            moved = False
            for secret in self.secrets:
                start = buffer.find(secret, max(0, cut - len(secret) + 1))
                while 0 <= start < cut:
                    if start + len(secret) > cut:
                        cut, moved = start, True
                        break
                    start = buffer.find(secret, start + 1)
        return cut

    def _write(self, text: str) -> None:
        if self.truncated:
            return
        encoded = text.encode("utf-8")
        last = False
        if self.bytes + len(encoded) > self.limit:
            encoded = encoded[:max(0, self.limit - self.bytes)]
            text = encoded.decode("utf-8", errors="ignore")
            last = True
        pieces = [text] if len(text.encode("utf-8")) <= self.chunk_bytes else _split(text, self.chunk_bytes)
        for position, piece in enumerate(pieces):
            truncated = last and position == len(pieces) - 1
            record = {"chunk": self.chunk, "at": now(), "text": piece, "truncated": truncated}
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.bytes += len(piece.encode("utf-8"))
            self.publish(self.run, self.stream, self.chunk, piece, truncated)
            self.chunk += 1
        if last:
            self.truncated = True
            if not pieces:
                record = {"chunk": self.chunk, "at": now(), "text": "", "truncated": True}
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")
                self.publish(self.run, self.stream, self.chunk, "", True)
                self.chunk += 1


def _split(text: str, size: int) -> List[str]:
    pieces, current, used = [], [], 0
    for char in text:
        width = len(char.encode("utf-8"))
        if used + width > size and current:
            pieces.append("".join(current))
            current, used = [], 0
        current.append(char)
        used += width
    if current:
        pieces.append("".join(current))
    return pieces


@dataclass
class Active:
    run_id: str
    project_id: Optional[str]
    owner: str
    key: Optional[str]
    command: Mapping[str, Any]
    project_root: Optional[str]
    correlation_id: str
    process: Optional[asyncio.subprocess.Process] = None
    waiter: Optional[asyncio.Task] = None
    task: Optional[asyncio.Task] = None
    cancel: bool = False
    timed_out: Optional[str] = None
    ticket: Any = None  # the PluginHost ticket of the work (admit); finished with the run
    judged: bool = False  # the outcome says something about the plugin (a cancel or an own stop does not)
    plugin_code: Optional[str] = None  # code of a judged outcome; ``None`` is a success
    started: float = field(default_factory=time.monotonic)
    last_output: float = field(default_factory=time.monotonic)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class Broker:
    def __init__(self, *, store: RunStore, hub, settings: Callable[[], Any], conn, db_lock, env: Mapping[str, str],
                 runs_dir: Path, secrets: Callable[[], List[str]], emit: Optional[Callable[..., Any]] = None) -> None:
        self.store = store
        self.hub = hub
        self._settings = settings
        self.conn = conn
        self.db_lock = db_lock
        self.env = env
        self.runs_dir = runs_dir
        self.secrets = secrets
        self.emit = emit
        self.active: Dict[str, Active] = {}

    @property
    def settings(self):
        """The current settings of the backend (read at every use: a test or a reload may replace them)."""
        return self._settings()

    # --- admission ---------------------------------------------------------------------------------------------

    def _key(self, command: Mapping[str, Any], context: Mapping[str, Any]) -> Optional[str]:
        template = command.get("concurrency_key")
        if not template:
            return None
        return re.sub(r"\{(project_id|plan_id|item_id)\}", lambda m: str(context.get(m.group(1), "")), template)

    def _admit(self, project_id: Optional[str], owner: str, key: Optional[str]) -> None:
        limits = self.settings.runs
        running = list(self.active.values())
        reason = None
        if len(running) >= limits.max_global:
            reason = f"{limits.max_global} runs are active on this machine"
        elif project_id is not None and sum(r.project_id == project_id for r in running) >= limits.max_per_project:
            reason = f"{limits.max_per_project} runs are active in this project"
        elif sum(r.owner == owner for r in running) >= limits.max_per_owner:
            reason = f"{limits.max_per_owner} runs of {owner} are active"
        elif key is not None and any(r.key == key for r in running):
            reason = f"a run with the concurrency key {key} is active"
        if reason:
            raise GuiError("CONCURRENCY_LIMIT", reason + "; try again when one ends")

    def _audit(self, action: str, target: str, decision: str, details: Mapping[str, Any], correlation_id: str) -> None:
        with self.db_lock:
            audit(self.conn, actor="user", action=action, target=target, decision=decision, details=details,
                  correlation_id=correlation_id)

    def _journal(self, run: Mapping[str, Any], project_root: Optional[str]) -> None:
        verb = _VERBS.get(run["state"])
        if self.emit is None or verb is None or project_root is None:
            return
        data = {"run_id": run["run_id"], "command": run["command"], "owner": run["owner"], "state": run["state"]}

        def emit():
            try:
                self.emit(f"gui.run.{verb}", data, subject=run["run_id"], project=project_root)
            except Exception as exc:  # noqa: BLE001 - a journal problem never changes the run
                log.warning("gui.run.%s of %s was not journaled: %s", verb, run["run_id"], exc)

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, emit)

    # --- runs --------------------------------------------------------------------------------------------------

    async def submit(self, *, owner: str, owner_root: Path, trusted: bool, command: Mapping[str, Any],
                     context: Mapping[str, Any], project_root: Optional[str], values: Mapping[str, Any],
                     dry_run: bool, confirmed: bool, correlation_id: str, actor: Mapping[str, str],
                     invoke: Optional[Callable[[], Any]] = None, ticket: Any = None) -> Dict[str, Any]:
        """Admit, record and start one run; returns its ``run/v1`` document (``running`` or a terminal state).

        ``ticket`` is the :class:`~gui.core.plugins.Ticket` the PluginHost gave for this work: its grants go into
        ``permission.grants``, the enforcement of each effect is told by ``plugins.enforcement`` and the broker
        finishes it when the run ends. Without one (no plugin gate) every effect is ``advisory``."""
        project_id = context.get("project_id")
        key = self._key(command, context)
        self._admit(project_id, owner, key)
        execution = command["exec"]
        built = None
        child_env: Dict[str, str] = {}
        secret_values: List[str] = []
        cwd: Optional[str] = None
        if execution["kind"] == "argv":
            built = argv_mod.build(command, owner_root, values, dry_run=dry_run)
            if built.cwd_kind == "project":
                if project_root is None:
                    raise GuiError("INPUT_INVALID", "this command runs in a project: context.project_id is required",
                                   issues=[{"pointer": "/context/project_id", "code": "required",
                                            "message": "required"}])
                cwd = project_root
            else:
                cwd = os.path.realpath(owner_root)
            child_env, secret_values = clean_environment(dict(self.env), permissions={"env": list(execution.get(
                "env", ()))}, trusted=trusted)
        secrets = [*secret_values, *self.secrets()]
        decision = "denied" if not trusted else "confirmed" if confirmed else "allowed"
        if ticket is None:
            permission = {"decision": decision, "grants": [],
                          "effects": [{"effect": effect, "enforcement": "advisory"} for effect in command["effects"]]}
        else:
            permission = {"decision": decision, "grants": list(ticket.grants),
                          "effects": [{"effect": effect, "enforcement": enforcement(effect, ticket.source)}
                                      for effect in command["effects"]]}
        redacted_input = redact_document(dict(values), secrets=secrets)
        run = self.store.create(command=command["id"], owner=owner, dry_run=dry_run, context=context,
                                input=redacted_input, actor=actor, permission=permission,
                                correlation_id=correlation_id)
        run_id = run["run_id"]
        active = Active(run_id, project_id, owner, key, command, project_root, correlation_id, ticket=ticket)
        self.active[run_id] = active
        try:
            self._audit("run.requested", run_id, "pending", {"command": command["id"], "owner": owner,
                                                             "input": redacted_input, "dry_run": dry_run},
                        correlation_id)
            self.store.transition(run_id, "authorizing")
            self._audit("run.decided", run_id, decision, {"effects": permission["effects"]}, correlation_id)
            if decision == "denied":
                run = self.store.transition(run_id, "denied", error=error_doc(
                    "PERMISSION_DENIED", f"extension {owner} is not trusted", correlation_id))
                self._finish(active, run)
                return run
            if built is None:
                run = self.store.transition(run_id, "starting")
                run = self.store.transition(run_id, "running", started_at=now())
                self._journal(run, project_root)
                active.task = asyncio.create_task(self._invoke(active, invoke, secrets))
                return run
            argv_redacted = [redact_text(part, secrets=secrets) for part in built.argv]
            run = self.store.transition(run_id, "starting", executable={"path": built.executable,
                                                                        "digest": built.digest},
                                        argv_redacted=argv_redacted, cwd=cwd)
            folder = self.runs_dir / run_id
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                process = await asyncio.create_subprocess_exec(
                    *built.argv, cwd=cwd, env=child_env, stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)
            except OSError as exc:
                active.judged, active.plugin_code = True, "PROCESS_SPAWN"
                run = self.store.transition(run_id, "failed_to_start", error=error_doc(
                    "HANDLER_FAILED", f"the program could not start: {exc.strerror or exc.__class__.__name__}",
                    correlation_id))
                self._finish(active, run)
                return run
            active.process = process
            active.started = active.last_output = time.monotonic()
            run = self.store.transition(run_id, "running", started_at=now(), pid=process.pid,
                                        pid_start=procinfo.start_time(process.pid))
            self._audit("run.started", run_id, decision, {"executable": {"path": built.executable,
                                                                          "digest": built.digest},
                                                          "argv_redacted": argv_redacted, "cwd": cwd},
                        correlation_id)
            self._journal(run, project_root)
            active.task = asyncio.create_task(self._watch(active, run, secrets))
            return run
        except BaseException:
            if not active.task:
                self._finish_ticket(active)
                self.active.pop(run_id, None)
                active.done.set()
            raise

    def _finish_ticket(self, active: Active) -> None:
        """Report the outcome of the run to the PluginHost: a failure to start or a protocol fault of the handler is
        judged, a non-zero exit, a timeout, a cancel or a lost run is not."""
        ticket = active.ticket
        if ticket is None:
            return
        try:
            if active.judged:
                ticket.finish(active.plugin_code)
            else:
                ticket.finish(cancelled=True)
        except Exception:  # noqa: BLE001 - the books of the plugin never block the end of a run
            log.exception("ticket of %s was not finished", active.run_id)

    def _finish(self, active: Active, run: Mapping[str, Any]) -> None:
        self._finish_ticket(active)
        self._audit("run.finished", active.run_id, run["state"],
                    {"state": run["state"], "exit": run.get("exit"),
                     "duration_ms": int((time.monotonic() - active.started) * 1000)}, active.correlation_id)
        self._journal(run, active.project_root)
        self.active.pop(active.run_id, None)
        active.done.set()

    def _sinks(self, run: Mapping[str, Any], secrets: Sequence[str]) -> Dict[str, LogSink]:
        folder = self.runs_dir / run["run_id"]
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        return {name: LogSink(run, name, folder, limit=self.settings.runs.log_max_bytes,
                              chunk_bytes=self.settings.runs.chunk_bytes, secrets=secrets,
                              publish=self.hub.publish_log) for name in ("stdout", "stderr")}

    async def _read(self, stream: asyncio.StreamReader, sink: LogSink, active: Active) -> None:
        while True:
            data = await stream.read(self.settings.runs.chunk_bytes)
            if not data:
                break
            active.last_output = time.monotonic()
            sink.feed(data)

    async def _watch(self, active: Active, run: Mapping[str, Any], secrets: Sequence[str]) -> None:
        process = active.process
        sinks = self._sinks(run, secrets)
        readers = [asyncio.create_task(self._read(process.stdout, sinks["stdout"], active)),
                   asyncio.create_task(self._read(process.stderr, sinks["stderr"], active))]
        active.waiter = asyncio.create_task(process.wait())
        limits = self.settings.runs
        deadline = active.started + int(active.command.get("timeout_s", 30))
        try:
            while not active.waiter.done():
                moment = time.monotonic()
                idle_at = active.last_output + limits.idle_timeout_s if limits.idle_timeout_s else float("inf")
                await asyncio.wait({active.waiter}, timeout=max(0.01, min(deadline, idle_at, moment + 1.0) - moment))
                if active.waiter.done() or active.cancel or active.timed_out:
                    continue
                moment = time.monotonic()
                if moment >= deadline:
                    active.timed_out = "total"
                elif limits.idle_timeout_s and moment >= active.last_output + limits.idle_timeout_s:
                    active.timed_out = "idle"
                if active.timed_out:
                    asyncio.create_task(self.stop(active))
            code = active.waiter.result()
            if group_alive(process.pid):  # the leader is gone; nothing of its group outlives it
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            done, pending = await asyncio.wait(readers, timeout=5)
            for reader in pending:
                reader.cancel()
            for sink in sinks.values():
                sink.close()
            log_doc = {"stdout_bytes": sinks["stdout"].bytes, "stderr_bytes": sinks["stderr"].bytes,
                       "truncated": sinks["stdout"].truncated or sinks["stderr"].truncated}
            exit_doc = {"code": code if code >= 0 else None, "signal": signal_name(-code) if code < 0 else None}
            if active.cancel:
                state, error = "cancelled", None
            elif active.timed_out:
                state = "timed_out"
                error = error_doc("HANDLER_TIMEOUT", f"the run was stopped: {active.timed_out} timeout",
                                  active.correlation_id, reason=active.timed_out)
            elif code == 0:
                active.judged = True
                state, error = "succeeded", None
            else:
                active.judged = True  # a non-zero exit of the program is the program's answer, not a plugin fault
                state = "failed"
                error = error_doc("HANDLER_FAILED", f"the program ended with {exit_doc['signal'] or exit_doc['code']}",
                                  active.correlation_id)
            fields: Dict[str, Any] = {"log": log_doc}
            if error is not None:
                fields["error"] = error
            final = self.store.transition(active.run_id, state, exit=exit_doc, **fields)
            self._finish(active, final)
        except Exception as exc:  # noqa: BLE001 - a broken watcher must not leave the run open
            log.exception("watcher of %s failed", active.run_id)
            self._abandon(active, exc)

    def _abandon(self, active: Active, exc: BaseException) -> None:
        if active.process is not None and group_alive(active.process.pid):
            try:
                os.killpg(active.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        row = self.store.row(active.run_id)
        if row is not None and row["state"] not in ("succeeded", "failed", "cancelled", "timed_out", "lost",
                                                     "denied", "failed_to_start"):
            final = self.store.transition(active.run_id, "lost", error=error_doc(
                "INTERNAL", "the backend lost track of the run", active.correlation_id))
            self._finish(active, final)
        else:
            self._finish_ticket(active)
            self.active.pop(active.run_id, None)
            active.done.set()

    async def _invoke(self, active: Active, invoke: Callable[[], Any], secrets: Sequence[str]) -> None:
        run = self.store.get(active.run_id)
        sinks = self._sinks(run, secrets)
        try:
            result = await asyncio.to_thread(invoke)
            active.judged = True
            active.plugin_code = None if result.status == "ok" else (result.code or result.status)
            if result.output is not None:
                sinks["stdout"].feed(json.dumps(redact_document(result.output, secrets=list(secrets)),
                                                ensure_ascii=False, indent=2).encode("utf-8"))
            for sink in sinks.values():
                sink.close()
            log_doc = {"stdout_bytes": sinks["stdout"].bytes, "stderr_bytes": 0, "truncated": sinks["stdout"].truncated}
            if result.status == "ok":
                final = self.store.transition(active.run_id, "succeeded", log=log_doc)
            else:
                code = result.code or result.status
                error = error_doc("HANDLER_TIMEOUT", "the handler did not answer in time", active.correlation_id) \
                    if code in TIMEOUT_CODES else error_doc("HANDLER_FAILED", "the handler failed",
                                                            active.correlation_id, plugin_code=str(code)[:64])
                final = self.store.transition(active.run_id, "failed", log=log_doc, error=error)
            self._finish(active, final)
        except Exception as exc:  # noqa: BLE001
            log.exception("invoke of %s failed", active.run_id)
            self._abandon(active, exc)

    async def stop(self, active: Active) -> None:
        """SIGTERM to the group, ``runs.cancel_grace_s`` for the leader to end, then SIGKILL to the group."""
        process = active.process
        if process is None or process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(asyncio.shield(active.waiter or asyncio.ensure_future(process.wait())), timeout=self.settings.runs.cancel_grace_s)
        except asyncio.TimeoutError:
            pass
        if group_alive(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    async def cancel(self, run_id: str, *, system: bool = False) -> Dict[str, Any]:
        """``queued`` → ``cancelled``; ``running`` → ``cancelling`` and the group is stopped in the background."""
        row = self.store.row(run_id)
        if row is None:
            raise GuiError("NOT_FOUND", f"no run {run_id}")
        active = self.active.get(run_id)
        state = row["state"]
        if state == "queued":
            run = self.store.transition(run_id, "cancelled")
            if active is not None:
                self._finish(active, run)
            return run
        supports = set((active.command if active else {}).get("supports", ()))
        if state != "running" or active is None or active.process is None or not (system or "cancel" in supports):
            raise GuiError("RUN_NOT_CANCELLABLE", f"run {run_id} is {state} and cannot be cancelled")
        active.cancel = True
        run = self.store.transition(run_id, "cancelling")
        self._journal(run, active.project_root)
        asyncio.create_task(self.stop(active))
        return run

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Cancel every active run and wait for the runs to end."""
        for run_id, active in list(self.active.items()):
            if active.process is not None and not active.cancel:
                try:
                    await self.cancel(run_id, system=True)
                except GuiError:
                    pass
        waits = [active.done.wait() for active in self.active.values()]
        if waits:
            await asyncio.wait([asyncio.ensure_future(w) for w in waits], timeout=timeout)
