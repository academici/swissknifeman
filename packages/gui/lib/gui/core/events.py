"""EventHub: the frames of ``/v1/events`` (``stream/v1``) with a sequence, a replay ring and bounded subscriptions.

Every published frame gets the next ``seq`` of this backend process (from 1) and goes to a ring of
``events.ring_frames`` frames with its filter metadata (project, run, owner, type). A subscription with a cursor of
this epoch that is still in the ring gets the frames after it, then live ones, without gaps or duplicates; any other
cursor gets ``snapshot_required`` (``cursor_expired``). Each subscription has its own bounded queue: when it is full
the queue is dropped and replaced by ``snapshot_required`` (``overflow``), so ``publish`` never waits for a client.
``.progress`` events with the same type and subject within 250 ms replace each other in a queue. Everything runs in
the event loop thread; stdlib only.
"""
from __future__ import annotations

import asyncio
import collections
import fnmatch
import time
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Mapping, Optional, Set, Tuple

from ..storage.db import now

CONTRACT = "urn:swissknifeman:gui:stream:v1"
COALESCE_S = 0.25


@dataclass(frozen=True)
class Meta:
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    owner: Optional[str] = None
    type: str = ""


@dataclass
class _Entry:
    seq: int
    frame: Dict[str, Any]
    meta: Meta


def matches(filter_: Mapping[str, Any], meta: Meta) -> bool:
    """Every key of the filter must hold: exact membership for projects, runs and owners, shell patterns for types."""
    if "projects" in filter_ and meta.project_id not in filter_["projects"]:
        return False
    if "runs" in filter_ and meta.run_id not in filter_["runs"]:
        return False
    if "owners" in filter_ and meta.owner not in filter_["owners"]:
        return False
    if "types" in filter_ and not any(fnmatch.fnmatchcase(meta.type, pattern) for pattern in filter_["types"]):
        return False
    return True


class Subscription:
    """One subscription of one connection; ``get`` waits for the next frame (with ``sub`` set)."""

    def __init__(self, sub_id: str, filter_: Mapping[str, Any], limit: int, *, clock=time.monotonic) -> None:
        self.id = sub_id
        self.filter = dict(filter_)
        self.limit = limit
        self._clock = clock
        self._items: Deque[List[Dict[str, Any]]] = collections.deque()  # one-element holders, replaceable in place
        self._pending: Dict[Tuple[str, Optional[str]], Tuple[List[Dict[str, Any]], float]] = {}
        self._ready = asyncio.Event()
        self.closed = False

    def offer(self, frame: Dict[str, Any]) -> None:
        if self.closed:
            return
        key = None
        if frame["kind"] == "event" and str(frame["event"].get("type", "")).endswith(".progress"):
            key = (frame["event"]["type"], frame["event"].get("subject"))
            held = self._pending.get(key)
            if held is not None and self._clock() - held[1] <= COALESCE_S:
                held[0][0] = self._tag(frame)
                return
        if len(self._items) >= self.limit:
            self._items.clear()
            self._pending.clear()
            self._items.append([{"$schema": CONTRACT, "kind": "snapshot_required", "sub": self.id,
                                 "reason": "overflow"}])
            self._ready.set()
            return
        holder = [self._tag(frame)]
        self._items.append(holder)
        if key is not None:
            self._pending[key] = (holder, self._clock())
        self._ready.set()

    def _tag(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        return frame if frame["kind"] in ("heartbeat", "snapshot_required") else {**frame, "sub": self.id}

    def snapshot_required(self, reason: str) -> None:
        self._items.append([{"$schema": CONTRACT, "kind": "snapshot_required", "sub": self.id, "reason": reason}])
        self._ready.set()

    def pending(self) -> int:
        return len(self._items)

    def get_nowait(self) -> Optional[Dict[str, Any]]:
        if not self._items:
            return None
        holder = self._items.popleft()
        for key, (held, _at) in list(self._pending.items()):
            if held is holder:
                del self._pending[key]
        if not self._items:
            self._ready.clear()
        return holder[0]

    async def get(self) -> Dict[str, Any]:
        while True:
            frame = self.get_nowait()
            if frame is not None:
                return frame
            if self.closed:
                raise asyncio.CancelledError
            await self._ready.wait()

    def close(self) -> None:
        self.closed = True
        self._ready.set()


class EventHub:
    def __init__(self, epoch: str, *, ring_frames: int = 10000, queue_frames: int = 1000) -> None:
        self.epoch = epoch
        self.seq = 0
        self.ring: Deque[_Entry] = collections.deque(maxlen=ring_frames)
        self.queue_frames = queue_frames
        self.subscriptions: Set[Subscription] = set()
        self.listeners: Set[Subscription] = set()  # connection-level: heartbeats

    def publish(self, kind: str, body: Mapping[str, Any], meta: Meta) -> int:
        """Store and fan out one frame; returns its seq. Never waits."""
        self.seq += 1
        frame = {"$schema": CONTRACT, "kind": kind, "seq": self.seq, **body}
        self.ring.append(_Entry(self.seq, frame, meta))
        for subscription in list(self.subscriptions):
            if matches(subscription.filter, meta):
                subscription.offer(frame)
        return self.seq

    def publish_run(self, doc: Mapping[str, Any], frame_run: Mapping[str, Any]) -> int:
        meta = Meta(project_id=doc.get("context", {}).get("project_id"), run_id=doc["run_id"], owner=doc["owner"],
                    type="gui.run")
        return self.publish("run", {"run": dict(frame_run)}, meta)

    def publish_log(self, run: Mapping[str, Any], stream: str, chunk: int, text: str, truncated: bool) -> int:
        meta = Meta(project_id=run.get("context", {}).get("project_id"), run_id=run["run_id"], owner=run["owner"],
                    type="gui.log")
        return self.publish("log", {"run_id": run["run_id"], "stream": stream, "chunk": chunk, "text": text,
                                    "truncated": truncated}, meta)

    def publish_event(self, event: Mapping[str, Any], project_id: Optional[str]) -> int:
        source = str(event.get("source", ""))
        owner = source.rsplit(":", 1)[-1] if source else None
        return self.publish("event", {"event": dict(event)},
                            Meta(project_id=project_id, owner=owner, type=str(event.get("type", ""))))

    def heartbeat(self) -> int:
        self.seq += 1
        frame = {"$schema": CONTRACT, "kind": "heartbeat", "seq": self.seq, "at": now()}
        for listener in list(self.listeners):
            if listener.pending() < listener.limit:  # a connection that does not read just misses heartbeats
                listener.offer(frame)
        return self.seq

    def subscribe(self, sub_id: str, filter_: Mapping[str, Any], cursor: Optional[int],
                  epoch: Optional[str]) -> Subscription:
        """A live subscription; with a cursor of this epoch still in the ring, the frames after it come first."""
        subscription = Subscription(sub_id, filter_, self.queue_frames)
        if cursor is not None:
            oldest = self.ring[0].seq if self.ring else self.seq + 1
            if epoch != self.epoch or cursor < oldest - 1 or cursor > self.seq:
                subscription.snapshot_required("cursor_expired")
            else:
                for entry in self.ring:
                    if entry.seq > cursor and matches(subscription.filter, entry.meta):
                        subscription.offer(entry.frame)
        self.subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self.subscriptions.discard(subscription)
        subscription.close()

    def listen(self) -> Subscription:
        listener = Subscription("heartbeat", {}, 4)
        self.listeners.add(listener)
        return listener

    def unlisten(self, listener: Subscription) -> None:
        self.listeners.discard(listener)
        listener.close()
