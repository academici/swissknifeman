"""Visibility of a conductor run: one progress line per event on stderr and in ``progress.jsonl``.

Every line is a ``conductor/v1`` ``progress-line``. stderr gets a readable line (``text``), the JSON line
(``json-lines``) or nothing (``quiet``); the journal always gets the JSON line, appended and flushed at once, so
``orch conduct status`` and the observer can read a run that is still going.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
from typing import Callable, Optional

from aicore.util.redact import env_secrets, redact_document

MODES = ("text", "json-lines", "quiet")
# ``info`` lines that report a long or costly run without stopping it; the latest one of the running step is the
# answer to "why is it taking so long" (``orch conduct status`` prints it)
BEACONS = ("STAGE_SLOW", "STAGE_IDLE", "CHECK_SLOW", "BUDGET_OVER", "LIMIT_OVER", "PROVIDER_WAIT", "ROUTE_FALLBACK",
           "CAPACITY_GATED", "WORK_SOURCE_NO_NOTE", "RESULT_SILENT_DENIAL", "DISK_LOW")
PROGRESS_FILE = "progress.jsonl"
WORDS = {"run.start": "run start", "run.resume": "run resume", "run.end": "run end", "item.start": "item start",
         "item.end": "item end", "stage.start": "start", "stage.end": "end", "stage.skip": "skip", "info": "info"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def text_line(line: dict) -> str:
    """The readable form: time, item, stage, role and route, what happened, verdict, duration and detail."""
    parts = [line["ts"], line.get("item", "-"), line.get("stage", "-")]
    if line.get("role"):
        parts.append(line["role"] + (f" {line['route']}" if line.get("route") else ""))
    parts.append(WORDS.get(line["event"], line["event"]))
    for key in ("verdict", "outcome"):
        if line.get(key):
            parts.append(line[key])
    if line.get("duration_s") is not None:
        parts.append(human_duration(line["duration_s"]))
    if line.get("tokens"):
        parts.append(f"tokens {line['tokens']['input']}/{line['tokens']['output']}")
    if line.get("reason_code"):
        parts.append(line["reason_code"])
    if line.get("message"):
        parts.append("— " + line["message"])
    return "  ".join(parts)


class Progress:
    """Writes the progress lines of run ``run_id`` into ``directory/progress.jsonl`` and onto ``stream``."""

    def __init__(self, run_id: str, directory: Path, mode: str = "text", stream=None,
                 clock: Optional[Callable[[], str]] = None):
        if mode not in MODES:
            raise ValueError(f"progress mode must be one of {', '.join(MODES)}")
        self.run_id = run_id
        self.path = Path(directory) / PROGRESS_FILE
        self.mode = mode
        self.stream = stream
        self.clock = clock or utc_now
        self._lock = threading.Lock()  # beacons of checks come from worker threads

    def emit(self, event: str, **fields) -> dict:
        with self._lock:
            return self._emit(event, **fields)

    def _emit(self, event: str, **fields) -> dict:
        fields = redact_document(fields, secrets=env_secrets())  # before the message is cut: a cut token no longer matches
        line = {"ts": self.clock(), "run": self.run_id, "event": event,
                **{key: value for key, value in fields.items() if value is not None and value != ""}}
        if "message" in line:
            line["message"] = " ".join(str(line["message"]).split())[:500] or "-"
        encoded = json.dumps(line, ensure_ascii=False, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        stream = self.stream if self.stream is not None else sys.stderr
        try:
            if self.mode == "text":
                print(text_line(line), file=stream, flush=True)
            elif self.mode == "json-lines":
                print(encoded, file=stream, flush=True)
        except (OSError, ValueError):  # a closed stderr never stops the run; the journal has the line
            pass
        return line


def read_lines(directory: Path) -> list:
    """The complete lines of ``progress.jsonl``; a torn last line is skipped."""
    try:
        data = (Path(directory) / PROGRESS_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    lines = []
    for raw in data.splitlines():
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if isinstance(doc, dict):
            lines.append(doc)
    return lines


def summarize(lines: list) -> dict:
    """State of a run from its journal: status, the stage running now, and per item its last stage and outcome."""
    items: dict = {}
    status, reason, current, beacon = "unknown", None, None, None
    for line in lines:
        if line.get("event") == "info" and line.get("reason_code") in BEACONS:
            beacon = line
        event = line.get("event")
        if event in ("run.start", "run.resume"):
            status, reason = "running", None
        elif event == "run.end":
            status, reason = line.get("outcome", "finished"), line.get("reason_code")
            current = None
        item = line.get("item")
        if item:
            row = items.setdefault(item, {"item": item, "stages": 0, "outcome": None, "last": None})
            if event == "stage.start":
                current = {"item": item, "stage": line.get("stage"), "role": line.get("role"),
                           "route": line.get("route"), "since": line["ts"]}
            elif event in ("stage.end", "stage.skip"):
                beacon = None if beacon and beacon.get("stage") == line.get("stage") else beacon
                row["stages"] += 1
                row["last"] = {"stage": line.get("stage"), "verdict": line.get("verdict"), "ts": line["ts"]}
                current = None
            elif event == "item.end":
                row["outcome"] = line.get("outcome")
                row["reason_code"] = line.get("reason_code")
            elif event == "info" and line.get("reason_code") == "SETTLED" and line.get("outcome"):
                row["outcome"], row["reason_code"] = line["outcome"], "SETTLED"  # set by hand after the run stopped
    return {"status": status, "reason_code": reason, "current": current, "beacon": beacon if current else None,
            "items": list(items.values()),
            "lines": len(lines), "last_ts": lines[-1]["ts"] if lines else None}
