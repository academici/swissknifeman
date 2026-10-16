"""Observe native Codex app-server messages without storing prompt/content bytes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time


class Observer:
    def __init__(self, directory, *, clock=time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.Lock()
        self.requests = {}
        self.turns = {}
        self.tools = {}

    def _record(self, value):
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
            stream.flush()
        temporary = self.directory / "status.json.tmp"
        temporary.write_text(json.dumps(list(self.requests.values()), sort_keys=True) + "\n")
        temporary.replace(self.directory / "status.json")

    def observe(self, direction: str, message: dict) -> None:
        with self.lock:
            method = message.get("method")
            params = message.get("params", {})
            request_id = message.get("id")
            now = self.clock()
            if direction == "client" and method == "turn/start":
                self.requests[request_id] = {"schema_version": "provider-request-lifecycle/v1",
                    "request_id": request_id, "thread_id": params["threadId"], "turn_id": None,
                    "phase": "submitted", "submitted_at": now, "updated_at": now,
                    "source": "codex-app-server", "observer_pid": os.getpid()}
                self._record(self.requests[request_id])
                return
            if direction != "server":
                return
            if request_id in self.requests and method is None:
                row = self.requests[request_id]
                if "error" in message:
                    row.update(phase="failed", updated_at=now)
                else:
                    turn = message.get("result", {}).get("turn", {})
                    if turn.get("id"):
                        row["turn_id"] = turn["id"]
                        self.turns[(row["thread_id"], turn["id"])] = request_id
                    row.update(updated_at=now, acknowledged_at=now)
                self._record(row)
                return
            thread = params.get("threadId")
            turn = params.get("turn", {})
            turn_id = params.get("turnId") or turn.get("id")
            key = (thread, turn_id)
            rid = self.turns.get(key)
            if rid is None and method == "turn/started":
                # Notifications may arrive before the response. Correlate only
                # an unambiguous pending start in this thread.
                candidates = [rid for rid, row in self.requests.items()
                              if row["thread_id"] == thread and row["turn_id"] is None]
                if len(candidates) == 1:
                    rid = candidates[0]
                    self.turns[key] = rid
                    self.requests[rid]["turn_id"] = turn_id
            if rid is None:
                return
            row = self.requests[rid]
            if row["phase"] in {"completed", "interrupted", "failed"}:
                return
            item = params.get("item", {})
            tools = self.tools.setdefault(key, set())
            if method == "turn/completed":
                phase = {"completed": "completed", "interrupted": "interrupted", "failed": "failed"}.get(
                    turn.get("status"), "unknown")
            elif method == "item/started" and item.get("type") in {
                    "commandExecution", "mcpToolCall", "dynamicToolCall", "fileChange", "webSearch"}:
                tools.add(item["id"])
                phase = "waiting-tool"
            elif method == "item/completed":
                tools.discard(item.get("id"))
                phase = "waiting-tool" if tools else "streaming"
            elif method == "turn/started":
                phase = "submitted"
            elif isinstance(method, str) and method.startswith("item/"):
                phase = "waiting-tool" if tools else "streaming"
            else:
                return
            row.update(phase=phase, updated_at=now)
            self._record({**row, "event": method})

    def disconnect(self, *, exit_code=None):
        with self.lock:
            for row in self.requests.values():
                if row["phase"] not in {"completed", "interrupted", "failed"}:
                    row.update(phase="unknown", updated_at=self.clock(), transport_exit_code=exit_code)
                    self._record({**row, "event": "observer/disconnected"})


def status(directory, *, stale_after: float = 60, now=None) -> list[dict]:
    path = Path(directory) / "status.json"
    rows = json.loads(path.read_text()) if path.exists() else []
    now = time.time() if now is None else now
    result = []
    for row in rows:
        stale = now - row["updated_at"] > stale_after and row["phase"] not in {"completed", "interrupted", "failed"}
        result.append({**row, "observation_stale": stale,
                       "current_state": "unknown" if stale else row["phase"]})
    return result
