"""Best-effort CPU activity diagnostics; missing telemetry never implies idle death."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skm.kernel.json_types import JsonObject

__all__: list[str] = []


def infra_process(command: str) -> bool:
    words = command.strip().split()
    return bool(words) and (
        Path(words[0]).name == "ps"
        or (len(words) >= 4 and Path(words[0]).name == "sh" and words[1:3] == ["-c", "ps"])
        or (len(words) == 3 and Path(words[0]).name == "sh" and words[1:] == ["-c", "ps"])
    )


def tree_cpu_ticks(pid: int) -> int | None:
    """Diagnostic /proc snapshot. This is never used as ownership or empty-containment proof."""
    facts: dict[int, tuple[int, int, bool]] = {}
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                raw = (entry / "stat").read_bytes()
                fields = raw.rsplit(b")", 1)[1].split()
                command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
                facts[int(entry.name)] = (
                    int(fields[1]),
                    int(fields[11]) + int(fields[12]),
                    infra_process(command),
                )
            except (FileNotFoundError, ProcessLookupError):
                continue
    except (OSError, ValueError, IndexError):
        return None
    if pid not in facts:
        return None
    owned = {pid}
    frontier = [pid]
    children: dict[int, list[int]] = {}
    for child, (parent, _, _) in facts.items():
        children.setdefault(parent, []).append(child)
    while frontier:
        for child in children.get(frontier.pop(), ()):
            if child not in owned:
                owned.add(child)
                frontier.append(child)
    return sum(facts[child][1] for child in owned if not facts[child][2])


@dataclass
class TreeCpuWatch:
    pid: int
    sample_seconds: float = 30.0
    progress_seconds: float = 1.0
    read_ticks: Callable[[int], int | None] = tree_cpu_ticks
    ticks_per_second: float = float(os.sysconf("SC_CLK_TCK"))
    last_sample: float = 0.0
    last_growth: float = 0.0
    _baseline: int | None = None

    def due(self, now: float) -> bool:
        return now - self.last_sample >= self.sample_seconds

    def sample(self, now: float) -> bool:
        ticks = self.read_ticks(self.pid)
        self.last_sample = now
        if ticks is None:
            return False
        grew = self._baseline is not None and (
            ticks - self._baseline >= self.progress_seconds * self.ticks_per_second
        )
        if self._baseline is None or grew or ticks < self._baseline:
            self._baseline = ticks
        if grew:
            self.last_growth = now
        return grew


def read_activity() -> JsonObject:
    return {"reads_total": None, "coverage": "unavailable"}
