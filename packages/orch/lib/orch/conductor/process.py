"""Start one role as a child process and read what it returned.

The prompt goes on stdin; stdout is written as it comes into the raw stream file (``<step>.jsonl`` or ``.txt``) and
stderr beside it, both under the ignored runtime folder of the run. The final text, the session, the model and the
token usage are read back from the stream by its transport: ``text`` (stdout is the answer), ``jsonl`` (the
stream-json of claude-code and grok: ``system/init`` and ``result``; the event stream of codex: ``thread.started``,
``item.completed`` agent messages and ``turn.completed`` / ``turn.failed``). ``acp`` is not driven by the conductor.

A failed role is classified here from normalized signals (see ``aicore.provider.errors``): the stream gives the
structured ones (``is_error``, ``http_status``, ``retry_category``, ``api_retries``, the ``limit_*`` of a rate-limit
event, ``terminal``) and the text of the failure (``fatal_text``); the process gives ``exit_code`` and ``stderr_tail``.
Text of tools and of model answers never enters a signal. Deciding what to do about the failure is the engine's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import gzip
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from typing import Callable, Mapping, Optional

from aicore.provider import errors as provider_errors
from aicore.util.redact import env_secrets, redact_text

from orch.conductor import records
from orch.conductor.signals import (CPU_PROGRESS_S, CPU_SAMPLE_S, PROGRESS_MARKERS, CpuWatch, StreamScan,  # noqa: F401 — re-exported
                                    TickInfo, command_of, markers_of, tree_cpu_ticks)
from orch.conductor.infrastructure.clock import utc_now

STDERR_TAIL_CHARS = 4000
INIT_FIELDS = ("tools", "mcp_servers", "skills", "plugins", "slash_commands")  # what an init event says was loaded


@dataclass
class RoleRun:
    """Outcome of one role process. ``error`` is a stable code when the run itself failed."""

    exit: Optional[int]
    text: str = ""
    session: Optional[str] = None
    model: Optional[str] = None
    usage: dict = field(default_factory=lambda: {"input": 0, "cached": 0, "output": 0})
    duration_s: float = 0.0
    raw: Optional[str] = None
    error: Optional[str] = None
    detail: Optional[str] = None
    lingered: bool = False  # the final result was out but the process did not exit: it was reaped after the grace
    error_doc: Optional[dict] = None  # error/v1 of a failed role the rules of aicore recognize (``provider`` known)
    api_retries: int = 0  # how many times the provider CLI itself repeated the request (claude ``api_retry`` events)
    denials: list = field(default_factory=list)  # ``[{tool_name}]``: tool calls refused without a prompt (never their input)
    reset_at: Optional[int] = None  # unix time the provider itself gave for the end of a limit (claude ``resetsAt``), as seen
    usage_complete: Optional[bool] = None  # text or not started: None; jsonl: terminal usage with fresh tokens
    init: Optional[dict] = None  # the names of the first init event (``INIT_FIELDS``), None when the stream has none


def available(argv: list) -> bool:
    """Whether the launcher and the command after its ``--`` are installed; cached for this process."""
    if not argv:
        return False
    if not _command_available(argv[0]):
        return False
    if "--" in argv:
        split = argv.index("--")
        return split + 1 < len(argv) and _command_available(argv[split + 1])
    return True


@lru_cache(maxsize=None)
def _command_available(command: str) -> bool:
    if os.sep in command:
        return os.path.isfile(command) and os.access(command, os.X_OK)
    return shutil.which(command) is not None


def _usage(found: object) -> dict:
    if not isinstance(found, dict):
        return {"input": 0, "cached": 0, "output": 0}
    def count(*keys: str) -> int:
        return sum(found[key] for key in keys if _is_int(found.get(key)) and found[key] >= 0)
    # ``cached`` (cache reads) is reported apart: it re-counts the whole context each turn and is not spend
    cached = found.get("cached_input_tokens")
    if _is_int(cached):  # Codex/OpenAI includes cache reads in input_tokens; invalid counts are ignored
        cached = count("cached_input_tokens")
        return {"input": max(0, count("input_tokens") - cached), "cached": cached, "output": count("output_tokens")}
    return {"input": count("input_tokens", "cache_creation_input_tokens"),
            "cached": count("cache_read_input_tokens"), "output": count("output_tokens")}


def parse_stream(transport: str, data: str) -> dict:
    """``{text, session, model, usage, usage_complete, is_error, signals, denials}`` of a captured stdout.

    ``is_error`` rests on ``result.is_error`` whatever its ``subtype`` (``success`` can come with ``is_error: true``)
    or on a codex ``turn.failed``; codex ``error`` events are notifications, not a failure. ``signals`` holds only the
    normalized failure signals the stream gives (see ``aicore.provider.errors.SIGNAL_TYPES``). ``denials`` are the tool
    calls Claude refused without asking (``--permission-prompts none``): the ``permission_denied`` system messages and
    ``result.permission_denials``, once per ``tool_use_id``; only the tool name and a safe hint (:func:`denial_hint`) are
    kept, ``tool_input`` may hold secrets. ``init`` (only when the stream has one) holds the names of :data:`INIT_FIELDS`
    of the first ``system/init`` event (claude-code, grok); an entry that is an object gives its ``name``.
    """
    if transport == "text":
        return {"text": data.strip(), "session": None, "model": None, "usage": {"input": 0, "cached": 0, "output": 0},
                "usage_complete": None, "is_error": False, "signals": {}, "denials": []}
    found = {"text": "", "session": None, "model": None, "usage": {"input": 0, "cached": 0, "output": 0}, "is_error": False,
             "usage_complete": False, "signals": {}, "denials": []}
    denied: dict = {}  # tool_use_id -> (tool name, hint), in order of first sight
    signals, retry_status, retries, last = found["signals"], None, 0, {}  # last: the final terminal event only
    messages, answers, complete = [], [], True  # answers: texts of the results that did not fail
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
            found.setdefault("init", {name: _names(doc.get(name)) for name in INIT_FIELDS})
        elif kind == "system" and doc.get("subtype") == "permission_denied":
            _deny(denied, doc)
        elif kind == "result":
            for entry in doc.get("permission_denials") if isinstance(doc.get("permission_denials"), list) else []:
                _deny(denied, entry)
            # Claude closes a turn with a ``result``; a background task that finishes later opens one more turn in the
            # same process (``task_notification``), so one answer can span several results: their texts are joined
            # (the contract block of an earlier turn stays visible) and their usage, counted per turn, is summed.
            # The text of a failed turn is not part of the answer; a final failure keeps its own text.
            result = doc.get("result")
            text = result if isinstance(result, str) else ""
            usage = _usage(doc.get("usage"))
            found["session"] = doc.get("session_id") or found["session"]
            found["usage"] = {key: found["usage"].get(key, 0) + usage[key] for key in usage}
            complete = complete and bool(usage["input"] or usage["output"])
            found["usage_complete"] = complete
            found["is_error"] = bool(doc.get("is_error"))
            if found["is_error"]:
                found["text"] = text or found["text"]
            else:
                answers = [*answers, text] if text.strip() else answers
                found["text"] = "\n\n".join(answers)
            last = {"terminal": True}
            if found["is_error"]:
                if isinstance(doc.get("result"), str):
                    last["fatal_text"] = doc["result"]
                if _is_int(doc.get("api_error_status")):
                    last["http_status"] = doc["api_error_status"]
        elif kind == "system" and doc.get("subtype") == "api_retry":  # claude: the CLI repeated the request itself
            retries += 1
            if isinstance(doc.get("error"), str):
                signals["retry_category"] = doc["error"]
            retry_status = doc["error_status"] if _is_int(doc.get("error_status")) else None
        elif kind == "rate_limit_event" and isinstance(doc.get("rate_limit_info"), dict):  # claude: quota telemetry
            info = doc["rate_limit_info"]
            for name, key in (("limit_status", "status"), ("limit_window", "rateLimitType")):
                if isinstance(info.get(key), str):
                    signals[name] = info[key]
            reset = info.get("resetsAt")
            if isinstance(reset, (int, float)) and not isinstance(reset, bool) and math.isfinite(reset):
                signals["limit_resets_at"] = int(reset)
        elif kind == "turn.failed":  # codex: the only fatal outcome; there is no structured code, only the text
            found["is_error"] = True
            found["usage_complete"] = False
            last = {"terminal": True}
            error = doc.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                last["fatal_text"] = error["message"]
        elif kind == "thread.started":  # codex exec --json
            found["session"] = doc.get("thread_id") or found["session"]
        elif kind == "item.completed" and isinstance(doc.get("item"), dict):
            item = doc["item"]
            if item.get("type") in ("agent_message", "assistant_message") and isinstance(item.get("text"), str):
                messages.append(item["text"])
        elif kind == "turn.completed":  # a turn that completes after a failed one is the outcome
            found["is_error"] = False
            last = {"terminal": True}
            usage = _usage(doc.get("usage"))
            found["usage"] = {key: found["usage"].get(key, 0) + usage[key] for key in usage}
            found["usage_complete"] = bool(usage["input"] or usage["output"])
    found["denials"] = [{"tool_name": name, **({"hint": hint} if hint else {})} for name, hint in denied.values()]
    if not found["text"] and messages:
        found["text"] = messages[-1]
    signals.update(last)
    if retries:
        signals["api_retries"] = retries
        if "http_status" not in signals and retry_status is not None:
            signals["http_status"] = retry_status
    if found["is_error"]:
        signals["is_error"] = True
    return found


def denial_hint(tool: str, tool_input: object) -> str:
    """A safe word for a refused call: the program of a Bash command (past ``cd <dir> &&``; ``+heredoc`` when it writes
    one) or the path of a file tool, shortened. Never the whole input: it may hold secrets."""
    if not isinstance(tool_input, dict):
        return ""
    if tool == "Bash" and isinstance(tool_input.get("command"), str):
        command = tool_input["command"].strip()
        segments = [part.strip() for part in re.split(r"&&|;|\n", command) if part.strip()]
        head = next((part for part in segments if not part.startswith("cd ")), segments[0] if segments else "")
        words = head.split()
        while words and "=" in words[0] and not words[0].startswith(("=", "-")):
            words = words[1:]  # VAR=value prefixes
        word = Path(words[0]).name if words else ""
        return (word[:40] + ("+heredoc" if "<<" in command else "")) if word else ""
    for key in ("file_path", "path", "notebook_path"):
        if isinstance(tool_input.get(key), str) and tool_input[key]:
            return tool_input[key][-120:]
    return ""


def _deny(denied: dict, doc: object) -> None:
    """Note one refused tool call; the system message and the final result name the same call by ``tool_use_id``."""
    if isinstance(doc, dict) and isinstance(doc.get("tool_name"), str) and doc["tool_name"]:
        key = doc.get("tool_use_id") if isinstance(doc.get("tool_use_id"), str) else f"#{len(denied)}"
        hint = denial_hint(doc["tool_name"], doc.get("tool_input"))
        if key not in denied or (hint and not denied[key][1]):
            denied[key] = (doc["tool_name"], hint)


def _names(value: object) -> list:
    """The sorted names of a list of an init event; an entry that is an object gives its ``name``."""
    entries = value if isinstance(value, list) else []
    return sorted(str(entry.get("name", "")) if isinstance(entry, dict) else str(entry) for entry in entries)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def partial_usage(data: str) -> dict:
    """Tokens of a stream that ended without its ``result`` line (a cancelled or stopped role): the usage of each
    assistant message, counted once per message id; the result line wins when there is one."""
    parsed = parse_stream("jsonl", data)
    if any(parsed["usage"].values()):
        return parsed["usage"]
    total, seen = {"input": 0, "cached": 0, "output": 0}, {}
    for raw in data.splitlines():
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        message = doc.get("message") if isinstance(doc, dict) and doc.get("type") == "assistant" else None
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            seen[message.get("id") or len(seen)] = _usage(message["usage"])
    for usage in seen.values():
        for key in total:
            total[key] += usage[key]
    return total


# Processes of the provider's own plumbing, not work of the role: the Claude sandbox proxies (socat over the
# claude-http socket and its TCP listeners), bubblewrap, the codex code-mode host. They live as long as the role, sit at
# 0 % CPU and would fill a listing sorted by age, so a healthy model call looked like a hang (P7/P8 STAGE_SLOW).
INFRA_PROCESS_MARKERS = ("claude-http-", "TCP6-LISTEN:", "TCP-LISTEN:", "codex-code-mode-host")
INFRA_PROCESS_HEADS = ("bwrap", "socat")


def infra_process(args: str) -> bool:
    """True for a process of the provider's sandbox or host plumbing (see :data:`INFRA_PROCESS_MARKERS`)."""
    head = Path(args.split(None, 1)[0]).name if args.strip() else ""
    return any(marker in args for marker in INFRA_PROCESS_MARKERS) or (
        head in INFRA_PROCESS_HEADS and ("claude" in args or "LISTEN" in args or head == "bwrap"))


def freshness(idle: Optional[float], info: Optional[TickInfo] = None) -> str:
    """``stream grew 42s ago, 1.2 MB, tree CPU 311s``: how fresh the output of a role is, for a beacon."""
    parts = [] if idle is None else [f"stream grew {int(idle)}s ago"]
    if info is not None:
        size = info.stream_bytes
        parts.append(f"{size / 1_000_000:.1f} MB" if size >= 1_000_000 else f"{size // 1000} KB")
        if info.tree_cpu_s is not None:
            parts.append(f"tree CPU {int(info.tree_cpu_s)}s")
    return ", ".join(parts)


def activity(pid: Optional[int], raw_path: Path, idle: Optional[float] = None, info: Optional[TickInfo] = None) -> str:
    """What a running role does now, for a beacon: how fresh its stream is (when the tick knows it), its last command
    (from the stream) and the processes of its tree other than the provider CLI and its sandbox plumbing, the busiest
    first and then the newest."""
    parts = []
    fresh = freshness(idle, info)
    if fresh:
        parts.append(fresh)
    last = _last_command(raw_path)
    if last:
        parts.append(f"last command: {last}")
    if pid:
        try:
            # stat and pcpu tell a process asleep on its input (S, 0.0 %) from one at work (R or a share of the CPU)
            listing = subprocess.run(["ps", "-eo", "pid=,ppid=,etimes=,stat=,pcpu=,args="], capture_output=True,
                                     text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            listing = ""
        table = {}
        for line in listing.splitlines():
            fields = line.split(None, 5)
            if len(fields) == 6 and all(field.isdigit() for field in fields[:3]):
                table[int(fields[0])] = (int(fields[1]), int(fields[2]), fields[5], fields[3], fields[4])
        below, grew = {pid}, True
        while grew:  # the whole tree under the provider CLI: its tool shells may sit in sessions of their own
            grew = False
            for number, row in table.items():
                if row[0] in below and number not in below:
                    below.add(number)
                    grew = True
        rows = [table[number][1:] for number in below if number != pid and number in table]
        rows = [row for row in rows if not row[1].startswith(("ps ", "/bin/sh -c ps"))]
        work = [row for row in rows if not infra_process(row[1])]
        if work:
            def busy(row: tuple) -> tuple:
                try:
                    cpu = float(row[3])
                except ValueError:
                    cpu = 0.0
                return (-cpu, row[0])
            shown = ", ".join(f"{args[:120]} ({seconds}s, {stat} {cpu}% cpu)"
                              for seconds, args, stat, cpu in sorted(work, key=busy)[:3])
            parts.append(f"running: {shown}")
        elif rows:
            parts.append("only the provider's sandbox processes: the model call is in progress")
        else:
            parts.append("no child process: the model call itself is silent")
    return "; ".join(parts) or "nothing observed"


def open_stream(path: Path, mode: str = "rb"):
    """Open the raw stream file ``path`` (``.jsonl``, ``.txt``, ``.stderr``, ``.times``) for reading or, when it is not
    there, the ``<path>.gz`` that ``conduct prune --compress-older-than`` left in its place: ``rb`` (the default) gives
    bytes, ``r`` UTF-8 text with what does not decode replaced. ``FileNotFoundError`` when neither is there."""
    path = Path(path)
    binary = "b" in mode
    try:
        return open(path, "rb") if binary else open(path, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        packed = path.with_name(path.name + ".gz")
        if not packed.is_file():
            raise
        return gzip.open(packed, "rb") if binary else gzip.open(packed, "rt", encoding="utf-8", errors="replace")


def _last_command(raw_path: Path, tail: int = 200_000) -> str:
    """The input of the last tool call in the stream (a command, a file), shortened."""
    try:
        with open_stream(raw_path) as handle:
            if isinstance(handle, gzip.GzipFile):  # no seek from the end in a gzip file
                blob = handle.read()[-tail:]
            else:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - tail))
                blob = handle.read()
    except (OSError, EOFError):
        return ""
    data = blob.decode("utf-8", errors="replace") if isinstance(blob, bytes) else blob
    found = ""
    for raw in data.splitlines():
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        message = doc.get("message") if isinstance(doc, dict) else None
        for block in (message.get("content") if isinstance(message, dict) else None) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                found = command_of(block)
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


def _group_alive(pgid: int) -> bool:
    """Whether a process of group ``pgid`` still runs; a zombie (dead, waiting for a parent that is not the conductor)
    does not count. Without ``/proc`` the group counts as alive while ``killpg(pgid, 0)`` reaches it."""
    proc = Path("/proc")
    if not proc.is_dir():
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        return True
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):
            return True
    return False


def _reap_group(pgid: int, grace_s: float = 5.0) -> bool:
    """End what a finished role left in its process group (a server or a watcher started in the background): SIGTERM,
    then SIGKILL after ``grace_s``. True when something was left. A process that left the group (``setsid``) is not
    reached; the conductor has no handle on it."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        if not _group_alive(pgid):
            return True
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    return True


POLL_S = 5  # how often a running role is looked at
RESULT_GRACE_S = 30  # how long a process may live on after its final ``result`` line (a provider CLI waits for its
# background tasks, for example a monitor loop that never ends, even though the role has answered)
def _wait(process: subprocess.Popen, prompt: str, raw_path: Path, *, timeout_s: int, idle_timeout_s: int,
          cancel: Optional[threading.Event] = None, on_tick: Optional[Callable] = None,
          result_grace_s: float = 0, transport: str = "jsonl", provider: Optional[str] = None) -> Optional[str]:
    """Feed ``prompt`` and wait for the child; ``None`` when it ended, else why it was stopped.

    ``timeout_s`` is a ceiling on the whole run, ``idle_timeout_s`` a limit on the silence of the output file; 0 switches
    either off (the default of the conductor: a long role is reported by beacons, never stopped). Silence ends when the
    stream grows or when the CPU of the process tree grows by ``CPU_PROGRESS_S`` between two measures (measured every
    ``CPU_SAMPLE_S`` and once more before the idle stop): a test run that writes nothing for an hour is at work, a sleeping
    tree is not. ``on_tick(elapsed, idle, pid, info)`` is called on every look at the child, ``info`` a :class:`TickInfo`.
    With ``result_grace_s`` > 0 a child that is still alive that long after its final ``result`` line is given up as
    ``lingering`` (the answer is complete). Every growth of the stream is stamped in ``<stream>.times``
    (``seconds-since-start size`` per line): providers whose stream has no times of its own can be profiled with it.
    """
    writer = threading.Thread(target=_feed, args=(process, prompt.encode("utf-8")), daemon=True)
    writer.start()
    started = last_growth = time.monotonic()
    size = -1
    times = raw_path.with_name(raw_path.name + ".times")
    scan, cpu, answered = StreamScan(raw_path, markers_of(transport, provider)), CpuWatch(process.pid), None
    while True:
        try:
            process.wait(timeout=POLL_S)
            return None
        except subprocess.TimeoutExpired:
            pass
        if cancel is not None and cancel.is_set():
            return "cancelled"
        now = time.monotonic()
        try:
            current = raw_path.stat().st_size
        except OSError:
            current = size
        kind, commands = None, []
        if current != size:
            size, last_growth = current, now
            found, kind, commands = scan.advance()
            if found and result_grace_s > 0 and answered is None:
                answered = now
            try:
                with open(times, "a", encoding="utf-8") as handle:
                    handle.write(f"{now - started:.1f} {current}\n")
            except OSError:
                pass
        if answered is not None and now - answered >= result_grace_s:
            return "lingering"
        if cpu.due(now) and cpu.sample(now):  # work that writes nothing is not silence
            last_growth, kind = now, kind or "cpu"
        if on_tick is not None:
            on_tick(now - started, now - last_growth, process.pid,
                    TickInfo(kind, max(size, 0), cpu.seconds, tuple(commands)))
        if timeout_s > 0 and now - started > timeout_s:
            return f"no result within {timeout_s} s"
        if idle_timeout_s > 0 and now - last_growth > idle_timeout_s:
            if cpu.sample(now):  # one more look before the stop: the tree may have worked since the last measure
                last_growth = now
            else:
                return f"no output for {idle_timeout_s} s"


def _feed(process: subprocess.Popen, data: bytes) -> None:
    try:
        process.stdin.write(data)
        process.stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        pass


def start_ticks(pid: int) -> Optional[int]:
    """Field 22 after the last closing parenthesis of Linux /proc/<pid>/stat."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def boot_id() -> Optional[str]:
    """The id of this boot of the machine (``/proc/sys/kernel/random/boot_id``), ``None`` without ``/proc``."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def run_role(argv: list, prompt: str, *, transport: str, cwd: Path, timeout_s: int, raw_path: Path,
             env: Optional[Mapping[str, str]] = None, idle_timeout_s: int = 0,
             cancel: Optional[threading.Event] = None, on_tick: Optional[Callable] = None,
             result_grace_s: float = RESULT_GRACE_S, provider: Optional[str] = None,
             agent_directory: Optional[Path] = None) -> RoleRun:
    """Run ``argv`` with ``prompt`` on stdin; never raises for a failure of the child.

    ``provider`` (an aicore provider id such as ``claude-code``) lets a failed run be classified into ``error_doc``;
    without it only ``error`` and ``detail`` are set.
    """
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
            return RoleRun(exit=None, error="PROVIDER_UNAVAILABLE", detail=redact_text(str(error), secrets=env_secrets(env)),
                           raw=str(raw_path))
        try:
            if agent_directory is not None:
                records.write(Path(agent_directory) / "process.json", {"pid": process.pid, "pgid": process.pid,
                              "start_ticks": start_ticks(process.pid), "started_at": utc_now()}, "process")
            stopped = _wait(process, prompt, raw_path, timeout_s=timeout_s, idle_timeout_s=idle_timeout_s, cancel=cancel,
                            on_tick=on_tick, result_grace_s=result_grace_s if transport != "text" else 0,
                            transport=transport, provider=provider)
        except BaseException:
            _kill(process)
            raise
        lingered = stopped == "lingering"
        if lingered:
            _kill(process)
        elif not stopped:
            _reap_group(process.pid)  # the role ended; what it started in the background must not outlive it
        elif stopped:
            _kill(process)
            data = raw_path.read_text(encoding="utf-8", errors="replace")
            parsed = parse_stream(transport, data)
            usage = partial_usage(data) if transport == "jsonl" else parsed["usage"]
            return RoleRun(exit=process.returncode, error="CANCELLED" if stopped == "cancelled" else "TIMEOUT", detail=stopped,
                           duration_s=time.monotonic() - started, raw=str(raw_path),
                           usage=usage, usage_complete=parsed["usage_complete"])
    duration = time.monotonic() - started
    data = raw_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_stream(transport, data)
    usage = partial_usage(data) if transport == "jsonl" and not parsed["usage_complete"] else parsed["usage"]
    run = RoleRun(exit=process.returncode, text=parsed["text"], session=parsed["session"], model=parsed["model"],
                  usage=usage, duration_s=duration, raw=str(raw_path), lingered=lingered,
                  usage_complete=parsed["usage_complete"],
                  api_retries=parsed["signals"].get("api_retries", 0), denials=parsed["denials"],
                  reset_at=parsed["signals"].get("limit_resets_at"), init=parsed.get("init"))
    if lingered:
        run.exit = 0
    if (process.returncode != 0 and not lingered) or parsed["is_error"]:
        stderr = redact_text(err_path.read_text(encoding="utf-8", errors="replace").strip(),
                             secrets=env_secrets(env))  # the raw .stderr file keeps what the role printed
        tail = stderr.splitlines()[-3:]
        run.error, run.detail = "ROLE_FAILED", f"exit {process.returncode}" + (f": {' | '.join(tail)}" if tail else "")
        if provider:
            signals = {**parsed["signals"], "exit_code": process.returncode, "stderr_tail": stderr[-STDERR_TAIL_CHARS:]}
            found = provider_errors.classify_signals(provider, signals, now=time.time())
            run.error_doc = found.to_dict() if found else None
    elif not run.text:
        run.error, run.detail = "ROLE_OUTPUT_EMPTY", "the role returned no final text"
    return run
