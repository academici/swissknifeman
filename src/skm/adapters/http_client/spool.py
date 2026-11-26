"""Bounded local FIFO spool (R3-8): 50 MB cap, 24h TTL, fencing, and historical-only heartbeat replay.

CRITICAL R3-8 INVARIANT:
Spooled heartbeats are strictly recorded as historical observations with their ORIGINAL timestamp.
Replay MUST NEVER call ``execution.renew_lease`` or ``workspace.record_worker_heartbeat``, and MUST NEVER
mutate host state, worker state, or host runtime offers.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Final, cast
from uuid import uuid4

from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, Conflict, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.platform.fs.atomic_write import atomic_write

__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_TTL",
    "FORBIDDEN_REPLAY_OPERATIONS",
    "HEARTBEAT_OBSERVATION_OP",
    "BoundedLocalSpool",
    "HistoricalObservation",
    "ReplayReport",
    "SpoolEntry",
    "SpoolItemKind",
]

DEFAULT_MAX_BYTES: Final[int] = 50 * 1024 * 1024  # 50 MiB
DEFAULT_TTL: Final[timedelta] = timedelta(hours=24)
HEARTBEAT_OBSERVATION_OP: Final[str] = "observation.worker_heartbeat"
FORBIDDEN_REPLAY_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "execution.renew_lease",
        "workspace.record_worker_heartbeat",
        "runtimes.record_host_runtimes",
        "workspace.register_host",
        "workspace.register_worker",
        "workspace.set_worker_state",
    }
)
_FENCE_FILE: Final[str] = "fence.json"
_ENTRY_PREFIX: Final[str] = "item-"
_ENTRY_SUFFIX: Final[str] = ".json"


class SpoolItemKind(StrEnum):
    """Spool item classification separating commands from historical heartbeat observations."""

    COMMAND = "command"
    HEARTBEAT_OBSERVATION = "heartbeat_observation"


@dataclass(frozen=True, slots=True)
class SpoolEntry:
    """One persisted FIFO spool entry."""

    seq: int
    item_id: str
    kind: SpoolItemKind
    operation: str
    fence_token: int
    recorded_at: datetime
    payload: JsonObject
    size_bytes: int


@dataclass(frozen=True, slots=True)
class HistoricalObservation:
    """Historical heartbeat observation delivered during spool replay without live state mutation."""

    item_id: str
    fence_token: int
    observed_at: datetime
    replayed_at: datetime
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """Outcome summary of one bounded spool replay pass."""

    replayed_commands: int
    recorded_observations: tuple[HistoricalObservation, ...]
    rejected_stale_fence: int
    expired_dropped: int
    evicted_fifo: int


def _ensure_private_dir(root: Path) -> None:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "Local spool directory must be private (0700)"
        )


def _require_aware_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Spool timestamps must be timezone-aware")
    return ts


def _serialize_entry(
    *,
    seq: int,
    item_id: str,
    kind: SpoolItemKind,
    operation: str,
    fence_token: int,
    recorded_at: datetime,
    payload: JsonObject,
) -> bytes:
    doc = {
        "seq": seq,
        "item_id": item_id,
        "kind": kind.value,
        "operation": operation,
        "fence_token": fence_token,
        "recorded_at": recorded_at.isoformat(),
        "payload": payload,
    }
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _parse_entry(path: Path) -> tuple[SpoolEntry, int] | None:
    try:
        raw = path.read_bytes()
        data = cast("dict[str, Any]", json.loads(raw.decode("utf-8")))
        entry = SpoolEntry(
            seq=int(data["seq"]),
            item_id=str(data["item_id"]),
            kind=SpoolItemKind(str(data["kind"])),
            operation=str(data["operation"]),
            fence_token=int(data["fence_token"]),
            recorded_at=datetime.fromisoformat(str(data["recorded_at"])),
            payload=cast("JsonObject", data["payload"]),
            size_bytes=len(raw),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return entry, len(raw)


class BoundedLocalSpool:
    """Durable, bounded FIFO local spool with 50 MB cap, 24h TTL, and R3-8 fencing & replay invariants."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Clock,
        max_bytes: int = DEFAULT_MAX_BYTES,
        ttl: timedelta = DEFAULT_TTL,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if ttl <= timedelta(0):
            raise ValueError("ttl must be positive")
        self._lock = RLock()
        self._root = root
        self._clock = clock
        self._max_bytes = max_bytes
        self._ttl = ttl
        _ensure_private_dir(self._root)
        self._fence = self._load_fence()
        self._next_seq = self._discover_next_seq()
        self._evicted_total = 0

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def ttl(self) -> timedelta:
        return self._ttl

    @property
    def current_fence(self) -> int:
        return self._fence

    def _fence_path(self) -> Path:
        return self._root / _FENCE_FILE

    def _load_fence(self) -> int:
        path = self._fence_path()
        if not path.exists():
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            value = raw.get("fence_token", 0)
            return int(value) if type(value) is int and value >= 0 else 0
        except (OSError, ValueError, AttributeError):
            return 0

    def _save_fence(self, fence_token: int) -> None:
        raw = json.dumps({"fence_token": fence_token}, separators=(",", ":")).encode("utf-8")
        atomic_write(self._fence_path(), raw, mode=0o600)

    def _entry_paths(self) -> list[Path]:
        return sorted(self._root.glob(f"{_ENTRY_PREFIX}*{_ENTRY_SUFFIX}"))

    def _discover_next_seq(self) -> int:
        highest = 0
        for path in self._entry_paths():
            parsed = _parse_entry(path)
            if parsed is not None:
                highest = max(highest, parsed[0].seq)
        return highest + 1

    def _entries_with_paths(self) -> list[tuple[Path, SpoolEntry]]:
        items: list[tuple[Path, SpoolEntry]] = []
        for path in self._entry_paths():
            parsed = _parse_entry(path)
            if parsed is None:
                with suppress(OSError):
                    path.unlink()
                continue
            items.append((path, parsed[0]))
        items.sort(key=lambda pair: pair[1].seq)
        return items

    def total_bytes(self) -> int:
        """Current on-disk bytes occupied by spooled items."""
        return sum(entry.size_bytes for _, entry in self._entries_with_paths())

    def entries(self) -> tuple[SpoolEntry, ...]:
        """Current spooled entries in strict FIFO order."""
        return tuple(entry for _, entry in self._entries_with_paths())

    def advance_fence(self, new_fence: int) -> int:
        """Advance the monotonic fence token; any spooled item with ``fence_token < new_fence`` is stale."""
        with self._lock:
            if type(new_fence) is not int or new_fence < 0:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "fence_token must be a non-negative integer")
            if new_fence < self._fence:
                raise Conflict(
                    ErrorCode.VERSION_CONFLICT,
                    "Cannot regress spool fence token",
                    details={"current_fence": self._fence, "requested_fence": new_fence},
                )
            if new_fence > self._fence:
                self._save_fence(new_fence)
                self._fence = new_fence
            return self._fence

    def purge_expired(self, *, now: datetime | None = None) -> int:
        """Drop entries older than ``ttl`` (default 24h) and return the count dropped."""
        current_time = _require_aware_utc(now if now is not None else self._clock.now())
        dropped = 0
        for path, entry in self._entries_with_paths():
            if current_time - entry.recorded_at > self._ttl:
                with suppress(OSError):
                    path.unlink()
                dropped += 1
        return dropped

    def enqueue_heartbeat(
        self,
        payload: JsonObject,
        *,
        fence_token: int,
        observed_at: datetime | None = None,
        item_id: str | None = None,
    ) -> SpoolEntry:
        """Spool a heartbeat strictly as a historical observation preserving its original timestamp."""
        return self.enqueue(
            HEARTBEAT_OBSERVATION_OP,
            payload,
            fence_token=fence_token,
            kind=SpoolItemKind.HEARTBEAT_OBSERVATION,
            recorded_at=observed_at,
            item_id=item_id,
        )

    def enqueue(
        self,
        operation: str,
        payload: JsonObject,
        *,
        fence_token: int,
        kind: SpoolItemKind = SpoolItemKind.COMMAND,
        recorded_at: datetime | None = None,
        item_id: str | None = None,
    ) -> SpoolEntry:
        """Append an item to the bounded FIFO spool, evicting oldest entries to respect ``max_bytes``."""
        with self._lock:
            if type(fence_token) is not int or fence_token < 0:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "fence_token must be a non-negative integer")
            if kind is SpoolItemKind.COMMAND and operation in FORBIDDEN_REPLAY_OPERATIONS:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    f"Operation {operation!r} cannot be spooled as a replayable command (R3-8); "
                    "use enqueue_heartbeat for historical-only observation recording",
                    details={"operation": operation, "rule": "R3-8"},
                )
            if fence_token < self._fence:
                raise Conflict(
                    ErrorCode.VERSION_CONFLICT,
                    "Spooled item rejected by newer fence token",
                    details={"item_fence": fence_token, "active_fence": self._fence},
                )
            if fence_token > self._fence:
                self.advance_fence(fence_token)

            now = _require_aware_utc(self._clock.now())
            ts = _require_aware_utc(recorded_at if recorded_at is not None else now)
            self.purge_expired(now=now)

            seq = self._next_seq
            resolved_id = item_id or uuid4().hex
            raw = _serialize_entry(
                seq=seq,
                item_id=resolved_id,
                kind=kind,
                operation=operation,
                fence_token=fence_token,
                recorded_at=ts,
                payload=payload,
            )
            size = len(raw)
            if size > self._max_bytes:
                raise ValidationFailed(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    f"Spool item ({size} bytes) exceeds max spool capacity ({self._max_bytes} bytes)",
                    details={"size_bytes": size, "max_bytes": self._max_bytes},
                )

            existing = self._entries_with_paths()
            used = sum(entry.size_bytes for _, entry in existing)
            for path, entry in existing:
                if used + size <= self._max_bytes:
                    break
                try:
                    path.unlink()
                except OSError:
                    continue
                else:
                    used -= entry.size_bytes
                    self._evicted_total += 1
            if used + size > self._max_bytes:
                raise BackendUnavailable(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    "Unable to evict spooled entries to satisfy max spool capacity",
                    details={"used_bytes": used, "item_bytes": size, "max_bytes": self._max_bytes},
                )

            self._next_seq = seq + 1
            target = self._root / f"{_ENTRY_PREFIX}{seq:020d}-{resolved_id}{_ENTRY_SUFFIX}"
            atomic_write(target, raw, mode=0o600)
            return SpoolEntry(
                seq=seq,
                item_id=resolved_id,
                kind=kind,
                operation=operation,
                fence_token=fence_token,
                recorded_at=ts,
                payload=payload,
                size_bytes=size,
            )

    def replay(
        self,
        *,
        active_fence: int,
        dispatch_command: Callable[[SpoolEntry], None] | None = None,
        record_observation: Callable[[HistoricalObservation], None],
    ) -> ReplayReport:
        """Drain the spool in FIFO order under R3-8 invariants.

        - Entries older than ``ttl`` (24h) are dropped without replay.
        - Entries with ``fence_token < active_fence`` are superseded/rejected without replay.
        - Heartbeat observations are passed ONLY to ``record_observation`` with their ORIGINAL
          ``recorded_at`` timestamp; ``dispatch_command`` is NEVER called for heartbeats or for
          ``execution.renew_lease`` / ``workspace.record_worker_heartbeat``.
        - If no command dispatcher is supplied, only historical observations are replayed.
        - On transient ``BackendUnavailable`` during command dispatch, replay stops immediately so
          remaining entries preserve strict FIFO order.
        """
        with self._lock:
            if active_fence > self._fence:
                self.advance_fence(active_fence)
            effective_fence = max(self._fence, active_fence)
            now = _require_aware_utc(self._clock.now())

            replayed_commands = 0
            observations: list[HistoricalObservation] = []
            rejected_stale_fence = 0
            expired_dropped = 0
            evicted_fifo = self._evicted_total
            self._evicted_total = 0

            for path, entry in self._entries_with_paths():
                if now - entry.recorded_at > self._ttl:
                    with suppress(OSError):
                        path.unlink()
                    expired_dropped += 1
                    continue

                if entry.fence_token < effective_fence:
                    with suppress(OSError):
                        path.unlink()
                    rejected_stale_fence += 1
                    continue

                if (
                    entry.kind is SpoolItemKind.HEARTBEAT_OBSERVATION
                    or entry.operation == "workspace.record_worker_heartbeat"
                ):
                    obs = HistoricalObservation(
                        item_id=entry.item_id,
                        fence_token=entry.fence_token,
                        observed_at=entry.recorded_at,
                        replayed_at=now,
                        payload=entry.payload,
                    )
                    record_observation(obs)
                    observations.append(obs)
                    with suppress(OSError):
                        path.unlink()
                    continue

                if dispatch_command is None or entry.operation in FORBIDDEN_REPLAY_OPERATIONS:
                    # Defense in depth: never dispatch host/offer/lease mutating commands from a spool.
                    with suppress(OSError):
                        path.unlink()
                    rejected_stale_fence += 1
                    continue

                try:
                    dispatch_command(entry)
                except BackendUnavailable:
                    break
                replayed_commands += 1
                with suppress(OSError):
                    path.unlink()

            return ReplayReport(
                replayed_commands=replayed_commands,
                recorded_observations=tuple(observations),
                rejected_stale_fence=rejected_stale_fence,
                expired_dropped=expired_dropped,
                evicted_fifo=evicted_fifo,
            )
