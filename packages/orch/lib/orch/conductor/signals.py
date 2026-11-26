"""Signs that a running role or check works, besides the growth of its output file: the tool steps in the stream of a
provider (``PROGRESS_MARKERS``), the CPU of its process tree (``CpuWatch``), and the repeat of one command or a stream that
grows without a tool step (``StallWatch``). Read by ``process._wait``, ``checks`` and the beacons of the roles; they only
observe: what stops a role or a check are the explicit limits."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Optional

_RESULT_LINE = (b'"type":"result"', b'"type": "result"')
CPU_PROGRESS_S = 1.0  # CPU seconds the process tree must spend between two measures to count as work, not as silence
CPU_SAMPLE_S = 30  # the tree is measured at most this often (a walk over /proc), and once more before an idle stop
_TAIL_MAX = 1_000_000  # a line of the stream this long without its newline is no marker line
_CLAUDE_MARKERS = {"tool_use": (b'"type":"tool_use"', b'"type": "tool_use"'),
                   "tool_result": (b'"type":"tool_result"', b'"type": "tool_result"')}
_CODEX_MARKERS = {"tool_use": (b'"type":"item.started"', b'"type": "item.started"'),
                  "tool_result": (b'"type":"item.completed"', b'"type": "item.completed"')}
# The lines of a stream that show a role at work, by provider (the transport ``text`` has none): a tool call starts or
# ends. A provider that is not listed is read for the markers of all of them.
PROGRESS_MARKERS = {"claude-code": _CLAUDE_MARKERS, "grok": _CLAUDE_MARKERS, "antigravity": _CLAUDE_MARKERS, "codex": _CODEX_MARKERS}


def markers_of(transport: str, provider: Optional[str]) -> dict:
    """``{kind: (bytes, ...)}`` the stream of ``provider`` over ``transport`` shows tool steps by."""
    if transport == "text":
        return {}
    if provider in PROGRESS_MARKERS:
        return PROGRESS_MARKERS[provider]
    return {kind: _CLAUDE_MARKERS[kind] + _CODEX_MARKERS[kind] for kind in _CLAUDE_MARKERS}


@dataclass
class TickInfo:
    """What a look at a running role saw besides the time (``on_tick`` gets it as its last argument): ``progress_kind`` is the
    latest sign of work since the look before (``tool_use``, ``tool_result``, or ``cpu`` when only the CPU of the
    process tree grew; ``None`` when nothing), ``stream_bytes`` the size of the stream, ``tree_cpu_s`` the CPU seconds of
    the tree at its last measure (``None`` without /proc), ``commands`` the tool calls that began since the look before."""
    progress_kind: Optional[str] = None
    stream_bytes: int = 0
    tree_cpu_s: Optional[float] = None
    commands: tuple = ()

    @property
    def new_tool_use(self) -> bool:
        return bool(self.commands) or self.progress_kind == "tool_use"

    @property
    def command(self) -> str:
        return self.commands[-1] if self.commands else ""


def _clock_ticks() -> int:
    try:
        return int(os.sysconf("SC_CLK_TCK")) or 100
    except (ValueError, OSError, AttributeError):
        return 100


def tree_cpu_ticks(pid: int) -> Optional[int]:
    """User and system clock ticks spent by ``pid`` and all its descendants (``/proc/<n>/stat`` fields 14 and 15, found by
    the parent pid, field 4), plus those of the descendants each of them has already waited for (fields 16 and 17: a
    finished child leaves the tree, its time moves to the ``cutime`` and ``cstime`` of its parent, so the sum never drops
    when a child ends); ``None`` without ``/proc`` or when ``pid`` is gone."""
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    rows: dict = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()
            rows[int(entry.name)] = (int(fields[1]), sum(int(fields[index]) for index in (11, 12, 13, 14)))
        except (OSError, IndexError, ValueError):
            continue
    if pid not in rows:
        return None
    below, grew = {pid}, True
    while grew:
        grew = False
        for number, (parent, _ticks) in rows.items():
            if parent in below and number not in below:
                below.add(number)
                grew = True
    return sum(rows[number][1] for number in below)


class CpuWatch:
    """CPU of a process tree, measured now and then: work that writes nothing is not silence. ``sample`` says whether the
    tree spent ``CPU_PROGRESS_S`` or more since the measure before; the first measure is only the baseline. Without
    /proc nothing is ever measured and nothing counts as work."""

    def __init__(self, pid: int, every_s: float = CPU_SAMPLE_S):
        self.pid, self.every_s = pid, every_s
        self.seconds: Optional[float] = None
        self.next_at = 0.0

    def due(self, now: float) -> bool:
        return now >= self.next_at

    def sample(self, now: float) -> bool:
        ticks = tree_cpu_ticks(self.pid)
        if ticks is None:
            return False
        seconds = ticks / _clock_ticks()
        grew = self.seconds is not None and seconds - self.seconds >= CPU_PROGRESS_S
        self.seconds, self.next_at = seconds, now + self.every_s
        return grew


class StreamScan:
    """The new bytes of a role stream, read once per look: whether a final ``result`` line is there, the latest tool marker
    and the tool calls that began. A line that is not finished yet waits for its newline."""

    def __init__(self, raw_path: Path, markers: dict):
        self.raw_path, self.markers = raw_path, markers
        self.offset, self.tail = 0, b""

    def advance(self) -> tuple:
        """``(final result seen, latest marker kind or None, commands begun)`` in the bytes added since the last call."""
        try:
            with open(self.raw_path, "rb") as handle:
                handle.seek(self.offset)
                data = handle.read()
        except OSError:
            return False, None, []
        self.offset += len(data)
        data = self.tail + data
        cut = data.rfind(b"\n") + 1
        done, self.tail = data[:cut], data[cut:]
        if len(self.tail) > _TAIL_MAX:
            self.tail = b""
        kind, commands = None, []
        for line in done.split(b"\n") if self.markers else ():
            for name, patterns in self.markers.items():
                if any(pattern in line for pattern in patterns):
                    kind = name
                    if name == "tool_use":
                        commands += line_commands(line)
        return any(marker in data for marker in _RESULT_LINE), kind, commands


def line_commands(line: bytes) -> list:
    """The tool calls a stream line starts: the ``tool_use`` blocks of a message (claude, grok) or the item of a codex
    ``item.started``; one entry (the line itself) when the line cannot be read."""
    try:
        doc = json.loads(line)
    except ValueError:
        return ["tool"]
    if not isinstance(doc, dict):
        return ["tool"]
    if doc.get("type") == "item.started":
        found = doc.get("item")
        found = found if isinstance(found, dict) else {}
        return [f"{found.get('type', 'item')}: {' '.join(str(found.get('command') or found.get('path') or '').split())[:160]}"]
    message = doc.get("message")
    blocks = (message.get("content") if isinstance(message, dict) else None) or []
    return [command_of(block) for block in blocks if isinstance(block, dict) and block.get("type") == "tool_use"] or ["tool"]


def command_of(block: dict) -> str:
    """The input of a ``tool_use`` block (a command, a file), shortened."""
    given = block.get("input") or {}
    value = given.get("command") or given.get("file_path") or given.get("path") or given.get("pattern") \
        if isinstance(given, dict) else given
    return f"{block.get('name', 'tool')}: {' '.join(str(value or '').split())[:160]}"


class StallWatch:
    """Whether a running role loops or only talks, from its ticks (``feed``): the same tool command ``repeat_n`` times in a row,
    or a stream that keeps growing for ``window_s`` seconds without a tool step (0 switches either off; the second needs a
    provider whose stream shows tool steps). Each reason is said once per command, the window once per ``window_s``. It
    only reports: nothing is stopped."""

    def __init__(self, repeat_n: int = 0, window_s: int = 0, *, steps: bool = True, now: float = 0.0):
        self.repeat_n, self.window_s, self.steps = repeat_n, window_s, steps
        self.command, self.count = "", 0
        self.said: set = set()
        self.last_step, self.size = now, -1

    @property
    def repeat(self) -> Optional[dict]:
        return {"command": self.command, "count": self.count} if self.command else None

    def feed(self, now: float, info: TickInfo) -> list:
        """The reasons to warn about after this look, as texts for a ``STALL_SUSPECTED`` beacon."""
        said = []
        for command in info.commands:
            self.command, self.count = command, self.count + 1 if command == self.command else 1
            if self.repeat_n and self.count >= self.repeat_n and command not in self.said:
                self.said.add(command)
                said.append(f"same command {self.count} times: {command}")
        grew, self.size = info.stream_bytes > self.size >= 0, info.stream_bytes
        if info.commands or info.progress_kind in ("tool_use", "tool_result"):
            self.last_step = now
        elif self.window_s and self.steps and grew and now - self.last_step > self.window_s:
            said.append(f"stream grew without a tool step for {int(now - self.last_step)} s")
            self.last_step = now
        return said


def process_stopped(pid: int) -> bool:
    """Whether the process is stopped (SIGSTOP, as an observer does to a check while the disk is freed): its state ``T``."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] in ("T", "t")
    except (OSError, IndexError):
        return False


def file_size(out) -> int:
    """The size of the open file ``out`` (the log of a check), -1 when it cannot be read."""
    try:
        return os.fstat(out.fileno()).st_size
    except (OSError, ValueError, AttributeError):
        return -1
