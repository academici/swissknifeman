"""Private, redacted capture with one reservation and a joint pre-write ceiling."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from skm.kernel.json_types import JsonValue
from skm.platform.fs.storage_budget import BudgetedFile, ReservationExceeded, WriteReservation
from skm.platform.logging.redaction import MASK, Redactor

from .stream import LINE_BYTES

__all__: list[str] = []


class TranscriptWriter:
    def __init__(
        self,
        step_dir: Path,
        reservation: WriteReservation,
        *,
        max_stream_bytes: int,
        workdir: Path,
        redactor: Redactor | None = None,
    ) -> None:
        if step_dir.resolve().is_relative_to(workdir.resolve()):
            raise ValueError("transcript must be outside workdir")
        if max_stream_bytes <= 0 or step_dir.parent.name != "steps":
            raise ValueError("transcript needs a positive ceiling and state_dir/steps/<step_id>")
        step_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if step_dir.is_symlink() or step_dir.stat().st_mode & 0o077:
            raise ValueError("transcript directory must be private")
        self.step_dir, self.reservation = step_dir, reservation
        self.max_stream_bytes = max_stream_bytes
        self.redactor = redactor if redactor is not None else Redactor()
        self.used = 0
        self.bytes_dropped = 0  # Raw ingress lost from primary capture; sidecars are not raw bytes.
        self.exceeded = False
        self.failed = False
        self.stderr_tail = ""
        self._lock = threading.RLock()
        self._closed = False
        self._pending = {"stdout": bytearray(), "stderr": bytearray()}
        self._discard: set[str] = set()
        self._secret_spellings: tuple[str, ...] = ()
        self._files: dict[str, BudgetedFile] = {}
        try:
            for key, name in (
                ("stdout", "stream.jsonl"),
                ("stderr", "stream.stderr"),
                ("times", "stream.times"),
            ):
                self._files[key] = reservation.open_file(step_dir / name)
        except BaseException as primary:
            try:
                reservation.close()
            except BaseException as cleanup:  # noqa: BLE001 - preserve startup failure
                if cleanup is not primary:
                    primary.add_note(f"transcript cleanup failed: {type(cleanup).__name__}")
            raise

    def register_secret(self, value: str) -> None:
        with self._lock:
            if value:
                spellings = {
                    *self._secret_spellings,
                    value,
                    json.dumps(value, ensure_ascii=False)[1:-1],
                    json.dumps(value, ensure_ascii=True)[1:-1],
                }
                self._secret_spellings = tuple(sorted(spellings, key=lambda text: (-len(text), text)))
                self.redactor.register_secret(value)

    def redact(self, text: str) -> str:
        for value in self._secret_spellings:
            text = text.replace(value, MASK)
        return self.redactor.text(text)

    def _redact_json(self, value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            result: dict[str, JsonValue] = {}
            for key, entry in value.items():
                safe_key = self.redact(key)
                clean = self._redact_json(entry)
                if not isinstance(clean, (dict, list)):
                    # Keep named credential patterns that originally matched across a key and value.
                    field = json.dumps({safe_key: clean}, ensure_ascii=False)
                    if self.redactor.text(field) != field:
                        clean = MASK
                result[safe_key] = clean
            return result
        if isinstance(value, list):
            return [self._redact_json(entry) for entry in value]
        if isinstance(value, str):
            return self.redact(value)
        encoded = json.dumps(value)
        return MASK if self.redact(encoded) != encoded else value

    def _redact_line(self, stream: str, text: str) -> str:
        if stream == "stdout":
            duplicates = False
            masked_token = False

            def object_from_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
                nonlocal duplicates
                result = dict(pairs)
                duplicates |= len(result) != len(pairs)
                return result

            def number(token: str, convert: type[int] | type[float]) -> JsonValue:
                nonlocal masked_token
                if self.redact(token) != token:
                    masked_token = True
                    return MASK
                return convert(token)

            try:
                record: JsonValue = json.loads(
                    text,
                    object_pairs_hook=object_from_pairs,
                    parse_int=lambda token: number(token, int),
                    parse_float=lambda token: number(token, float),
                    parse_constant=lambda token: number(token, float),
                )
                clean = self._redact_json(record)
                if clean == record and not (duplicates or masked_token):
                    return text
                ending = "\r\n" if text.endswith("\r\n") else "\n" if text.endswith("\n") else ""
                return json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + ending
            except (ValueError, RecursionError):
                # An unfinished or over-nested provider record still needs text masking.
                pass
        return self.redact(text)

    def charge(self, size: int) -> bool:
        with self._lock:
            if size < 0:
                raise ValueError("negative reservation")
            if self.exceeded or size > self.max_stream_bytes - self.used:
                self.exceeded = True
                return False
            self.used += size
            return True

    def _flush_line(self, stream: str) -> str:
        pending = self._pending[stream]
        safe = self._redact_line(stream, pending.decode("utf-8", "replace"))
        raw_size = len(pending)
        pending.clear()
        data = safe.encode("utf-8", "backslashreplace")
        # Replace the pending reservation with its one on-disk representation.
        self.used -= raw_size
        if not self.charge(len(data)):
            self.bytes_dropped += raw_size
            return ""
        try:
            self._files[stream].write(data)
        except (OSError, ReservationExceeded):
            self.bytes_dropped += raw_size
            raise
        if stream == "stderr":
            self.stderr_tail = (self.stderr_tail + safe)[-4000:]
        return safe

    def write(self, stream: str, chunk: bytes) -> tuple[bool, str]:
        """Reserve buffered ingress, replacing it with written bytes when redacted.

        Lines are held until complete so secrets split across pipe callbacks cannot escape.
        An overlong line is discarded, never flushed in unredacted fragments.
        """
        with self._lock:
            if self._closed:
                raise ValueError("transcript closed")
            if not self.charge(len(chunk)):
                self.bytes_dropped += len(chunk)
                return False, ""
            safe: list[str] = []
            offset = end = 0
            try:
                while offset < len(chunk):
                    newline = chunk.find(b"\n", offset)
                    end = len(chunk) if newline < 0 else newline + 1
                    pending = self._pending[stream]
                    if len(pending) + end - offset > LINE_BYTES + int(newline >= 0):
                        self.used -= len(pending)
                        self.bytes_dropped += len(pending)
                        pending.clear()
                        self._discard.add(stream)
                    if stream in self._discard:
                        self.used -= end - offset
                        self.bytes_dropped += end - offset
                    else:
                        pending.extend(memoryview(chunk)[offset:end])
                        if newline >= 0:
                            safe.append(self._flush_line(stream))
                    if newline >= 0:
                        self._discard.discard(stream)
                    offset = end
                    if self.exceeded:
                        self.used -= len(chunk) - offset
                        self.bytes_dropped += len(chunk) - offset
                        break
            except (OSError, ReservationExceeded):
                self.failed = True
                self.used -= len(chunk) - end
                self.bytes_dropped += len(chunk) - end
                return False, ""
            return not self.exceeded, "".join(safe)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                for stream, pending in self._pending.items():
                    if pending and not self.exceeded:
                        self._flush_line(stream)
                    elif pending:
                        self.used -= len(pending)
                        self.bytes_dropped += len(pending)
                        pending.clear()
            finally:
                self.reservation.close()

    def stamp(self, elapsed: float, size: int) -> bool:
        with self._lock:
            data = f"{elapsed:.1f} {size}\n".encode("ascii")
            if not self.charge(len(data)):
                return False
            try:
                self._files["times"].write(data)
            except (OSError, ReservationExceeded):
                self.failed = True
                return False
            return True
