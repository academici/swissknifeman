"""Collect bounded metrics from Claude Code's local session JSONL."""

from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from itertools import islice
from json import dumps, loads
from os import O_NOFOLLOW, O_NONBLOCK, O_RDONLY, close, fdopen, fstat, geteuid
from os import open as open_fd
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from typing import Any, BinaryIO, cast
from uuid import UUID

from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock, LockTimeout
from skm.platform.logging.redaction import Redactor

__all__ = ["MAX_TRANSCRIPT_BYTES", "SessionSummarySpool", "summarize_session"]

MAX_TRANSCRIPT_BYTES = 50_000_000
_MAX_LINE_BYTES = 1_048_576
_MAX_NAMES = 10_000
_READ_TOOLS = {"read", "read_file"}
_WRITE_TOOLS = {"edit", "write", "multiedit", "notebookedit"}
_USAGE = {
    "input_tokens": "usage_input",
    "cache_read_input_tokens": "usage_cache_read",
    "cache_creation_input_tokens": "usage_cache_write",
}
_READ_METRICS = ("reads_total", "reads_unique", "top_rereads")
_TRANSCRIPT_METRICS = ("tools_total", *_READ_METRICS, "error_loops", "files_changed", *_USAGE.values())
_UNSUPPORTED_METRICS = (
    "checks",
    "retrieval_calls",
    "retrieval_result_chars",
    "retrieval_repeated_queries",
    "cache_hit",
    "agents",
    "context_window_tokens",
    "protected_writes",
    "workarounds",
    "workflow_relaunches",
    "outcome",
    "task_outcome",
)


class _Metrics:
    def __init__(self, root: Path, redactor: Redactor) -> None:
        self.root = root
        self.redactor = redactor
        self.complete = True
        self.tail_complete = False
        self.reads: Counter[str] = Counter()
        self.reads_complete = True
        self.files: set[str] = set()
        self.files_complete = True
        self.tools_total = 0
        self.calls: dict[str, tuple[str, str | None]] = {}
        self.error_run: tuple[str, int] | None = None
        self.errors: Counter[str] = Counter()
        self.usage: Counter[str] = Counter()
        self.usage_missing: set[str] = set()
        self.messages: set[str] = set()
        self.matched = False

    def _safe_path(self, raw: object) -> str | None:
        if not isinstance(raw, str) or not raw or len(raw) > 4096 or "\0" in raw:
            return None
        try:
            raw.encode("utf-8")
        except UnicodeEncodeError:
            return None
        path = self.root.joinpath(raw)
        if not path.is_relative_to(self.root) or ".." in path.parts:
            return None
        # Record a checkout-relative name only. Tool inputs and file contents are omitted.
        return self.redactor.text(path.relative_to(self.root).as_posix())[:240]

    def _call(self, block: dict[str, Any]) -> None:
        name = block.get("name")
        call_id = block.get("id")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(call_id, str)
            or not call_id
            or call_id in self.calls
            or len(self.calls) >= _MAX_NAMES
        ):
            self.complete = False
            return
        tool = name.lower()
        # Keep only known tool labels, never names taken from an arbitrary server or prompt.
        label = tool if tool in _READ_TOOLS | _WRITE_TOOLS | {"bash", "grep", "glob", "agent"} else "other"
        args = block.get("input")
        path = (
            self._safe_path(cast("dict[str, Any]", args).get("file_path")) if isinstance(args, dict) else None
        )
        self.calls[call_id] = (label, path if label in _WRITE_TOOLS else None)
        self.tools_total += 1
        if label in _READ_TOOLS:
            if path is None or len(self.reads) >= _MAX_NAMES:
                self.reads_complete = False
            else:
                self.reads[path] += 1
        if label in ("bash", "agent", "other"):
            # These tools can write without a structured file edit in this transcript.
            self.files_complete = False

    def _result(self, block: dict[str, Any]) -> None:
        call_id = block.get("tool_use_id")
        call = self.calls.pop(call_id, None) if isinstance(call_id, str) else None
        if call is None or type(block.get("is_error", False)) is not bool:
            self.complete = False
            return
        tool, path = call
        if block.get("is_error") is True:
            previous, count = self.error_run or ("", 0)
            length = count + 1 if previous == tool else 1
            self.error_run = (tool, length)
            self.errors[tool] = max(self.errors[tool], length)
        else:
            self.error_run = None
            if path is not None and len(self.files) < _MAX_NAMES:
                self.files.add(path)
            elif tool in _WRITE_TOOLS:
                self.files_complete = False

    def _record_usage(self, message_id: object, usage: object) -> None:
        if not isinstance(message_id, str) or len(self.messages) >= _MAX_NAMES:
            self.usage_missing.update(_USAGE)
            return
        if message_id in self.messages:
            return
        self.messages.add(message_id)
        for key in _USAGE:
            value = cast("dict[str, Any]", usage).get(key) if isinstance(usage, dict) else None
            if type(value) is int and value >= 0:
                self.usage[key] += value
            else:
                self.usage_missing.add(key)

    def observe(self, data: dict[str, Any], session_id: str) -> None:
        if data.get("sessionId") != session_id:
            return
        kind = data.get("type")
        if not isinstance(kind, str):
            self.matched = True
            self.complete = False
            return
        if kind not in ("assistant", "user"):
            return
        self.matched = True
        self.tail_complete = False
        raw_message = data.get("message")
        if not isinstance(raw_message, dict):
            self.complete = False
            return
        message = cast("dict[str, Any]", raw_message)
        if kind == "assistant":
            self._record_usage(message.get("id") or data.get("uuid"), message.get("usage"))
        content = message.get("content")
        if isinstance(content, str) and kind == "user":
            return
        if not isinstance(content, list):
            self.complete = False
            return
        for raw_block in cast("list[object]", content):
            if not isinstance(raw_block, dict):
                self.complete = False
                continue
            block = cast("dict[str, Any]", raw_block)
            block_type = block.get("type")
            if not isinstance(block_type, str):
                self.complete = False
            elif block_type == "tool_use":
                self._call(block)
            elif block_type == "tool_result":
                self._result(block)
        stop_reason = message.get("stop_reason")
        if stop_reason is not None and not isinstance(stop_reason, str):
            self.complete = False
        self.tail_complete = kind == "assistant" and stop_reason in ("end_turn", "stop_sequence")

    def document(self) -> JsonObject:
        if not self.complete or not self.tail_complete or self.calls:
            return {}
        data: JsonObject = {"tools_total": self.tools_total}
        for key, field in _USAGE.items():
            if key in self.usage and key not in self.usage_missing:
                data[field] = self.usage[key]
        if self.reads_complete:
            data.update(reads_total=sum(self.reads.values()), reads_unique=len(self.reads))
            data["top_rereads"] = [
                {"path": path, "count": count} for path, count in self.reads.most_common(20) if count > 1
            ]
        data["error_loops"] = [
            {"tool": tool, "length": count} for tool, count in sorted(self.errors.items()) if count > 1
        ]
        if self.files_complete and len(self.files) <= 50:
            data["files_changed"] = cast("list[JsonValue]", sorted(self.files))
        return data

    def coverage(self, document: JsonObject) -> JsonObject:
        coverage: JsonObject = dict.fromkeys(_UNSUPPORTED_METRICS, "unknown")
        if not document:
            coverage.update(dict.fromkeys(_TRANSCRIPT_METRICS, "partial"))
            return coverage
        coverage.update(dict.fromkeys(document, "complete"))
        if not self.reads_complete:
            coverage.update(dict.fromkeys(_READ_METRICS, "partial"))
        if "files_changed" not in document:
            coverage["files_changed"] = "partial"
        for key, field in _USAGE.items():
            if field not in document:
                coverage[field] = "partial" if key in self.usage else "unknown"
        return coverage


def _collect(stream: BinaryIO, session_id: str, metrics: _Metrics) -> bool:
    remaining = MAX_TRANSCRIPT_BYTES
    while remaining:
        line = stream.readline(min(remaining, _MAX_LINE_BYTES) + 1)
        if not line:
            return True
        remaining -= len(line)
        if remaining < 0 or len(line) > _MAX_LINE_BYTES:
            return False
        try:
            data = loads(line)
        except (ValueError, RecursionError):
            metrics.complete = False
            continue
        if isinstance(data, dict):
            metrics.observe(cast("dict[str, Any]", data), session_id)
        else:
            metrics.complete = False
    return True


def summarize_session(
    path: Path,
    *,
    session_id: str,
    checkout: Path,
    observed_at: datetime,
    redactor: Redactor | None = None,
) -> JsonObject | None:
    """Read a caller-authorized regular file and emit only neutral, redacted metrics."""
    if not session_id.strip() or observed_at.utcoffset() is None:
        return None
    metrics = _Metrics(checkout, redactor or Redactor())
    try:
        key = sha256(session_id.encode()).hexdigest()
        fd = open_fd(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        try:
            stat = fstat(fd)
            if not S_ISREG(stat.st_mode) or stat.st_uid != geteuid() or stat.st_size > MAX_TRANSCRIPT_BYTES:
                return None
            with fdopen(fd, "rb", closefd=False) as stream:
                if not _collect(stream, session_id, metrics) or not metrics.matched:
                    return None
            after = fstat(fd)
            if after.st_size > MAX_TRANSCRIPT_BYTES:
                return None
            if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                metrics.tail_complete = False
        finally:
            close(fd)
    except (OSError, ValueError):
        return None
    document = metrics.document()
    return {
        "schema": "urn:skm:learning:activity-summary:v1",
        "source_kind": "client_session",
        "source_key": f"claude_code:{key}",
        "outcome": "unknown",
        "exposure_coverage": "unknown",
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "adapter_id": "claude_code",
        "adapter_version": "1",
        "parser_version": "1",
        "source_format": "claude_code_jsonl",
        "metric_coverage": metrics.coverage(document),
        **document,
    }


_MAX_PENDING = 128
_MAX_JOB_BYTES = 16_384


class SessionSummarySpool:
    """Queue local transcript references for a separate drain process."""

    def __init__(
        self, folder: Path, transcript_root: Path, *, wake: Callable[[], None], now: Callable[[], datetime]
    ) -> None:
        self._folder = folder
        self._transcript_root = transcript_root
        self._wake = wake
        self._now = now

    def _ensure_private(self) -> None:
        self._folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self._folder.lstat()
        if not S_ISDIR(info.st_mode) or info.st_uid != geteuid() or info.st_mode & 0o077:
            raise ValueError("Unsafe session summary queue directory")

    def _authorized_path(self, transcript: str, session_id: str) -> Path | None:
        path = Path(transcript)
        if (
            not path.is_absolute()
            or len(transcript) > 4096
            or not 1 <= len(session_id) <= 200
            or path.name != session_id + ".jsonl"
        ):
            return None
        root = self._transcript_root.resolve()
        parent = path.parent.resolve()
        return parent / path.name if parent.is_relative_to(root) else None

    def enqueue(self, project: str, checkout: str, session_id: str, transcript: str) -> None:
        path = self._authorized_path(transcript, session_id)
        if path is None or len(checkout) > 4096:
            return
        project = str(UUID(project))
        key = sha256(f"{project}:{session_id}".encode()).hexdigest()
        self._ensure_private()
        target = self._folder / (key + ".json")
        with suppress(LockTimeout), FileLock(self._folder / ".enqueue.lock").hold(timeout_seconds=0):
            if (
                not target.exists()
                and len(tuple(islice(self._folder.glob("*.json"), _MAX_PENDING))) < _MAX_PENDING
            ):
                data = dumps(
                    {
                        "project": project,
                        "checkout": checkout,
                        "session_id": session_id,
                        "transcript": str(path),
                        "observed_at": self._now().isoformat(),
                    }
                ).encode()
                if len(data) <= _MAX_JOB_BYTES:
                    atomic_write(target, data, mode=0o600)
        # This callback starts the drain and returns. It never reads a transcript or dispatches.
        self._wake()

    def drain(
        self,
        *,
        enabled: Callable[[str], bool],
        dispatch: Callable[[str, JsonObject], None],
        summarize: Callable[[Path, str, Path, datetime], JsonObject | None] | None = None,
        checkout_allowed: Callable[[str, Path], bool] | None = None,
    ) -> int:
        self._ensure_private()
        completed = 0
        # A worker launched after the current drain took its snapshot can process newly queued jobs.
        with suppress(LockTimeout), FileLock(self._folder / ".drain.lock").hold(timeout_seconds=30):
            for job in sorted(islice(self._folder.glob("*.json"), _MAX_PENDING)):
                with job.open("rb") as stream:
                    data = stream.read(_MAX_JOB_BYTES + 1)
                if len(data) > _MAX_JOB_BYTES:
                    job.unlink()
                    continue
                work = loads(data)
                checkout = Path(work["checkout"])
                if enabled(work["project"]) and (
                    checkout_allowed is None or checkout_allowed(work["project"], checkout)
                ):
                    transcript = self._authorized_path(work["transcript"], work["session_id"])
                    if transcript is not None:
                        session_id = work["session_id"]
                        observed = datetime.fromisoformat(work["observed_at"])
                        summary = (
                            summarize(transcript, session_id, checkout, observed)
                            if summarize is not None
                            else summarize_session(
                                transcript, session_id=session_id, checkout=checkout, observed_at=observed
                            )
                        )
                        if summary is not None:
                            dispatch(work["project"], summary)
                            completed += 1
                job.unlink()
        return completed
