"""Strict local ``supervisor-run-v1`` event store.

The JSONL journal is the recovery authority.  Snapshots and owner queues are
derived, replaceable views and never participate in repair or replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

try:  # The contract deliberately has no Windows portability claim.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on unsupported hosts
    fcntl = None


EVENT_SCHEMA = "supervisor-run-event-v1"
ZERO_HASH = "0" * 64
RECORD_KEYS = frozenset((
    "schema_version", "seq", "prev_hash", "record_hash", "ts", "run_id",
    "slice_id", "attempt", "event", "state_before", "state_after",
    "idempotency_key", "input_hashes", "evidence", "redaction",
))
RECOVERY_INSPECTION_KEYS = frozenset((
    "preimage_hash", "postimage_hash", "observed_hash", "partial", "backup", "orphan_verified",
    "external_call_count",
))


class StoreRefusal(ValueError):
    """A named contract refusal; callers must not turn it into a best effort."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class InjectedFailure(RuntimeError):
    """Deterministic crash-cut probe used only by the local fault tests."""


def recovery_decision(inspection: dict) -> dict:
    """Classify a freshly observed side-effect boundary without guessing a rerun.

    The caller supplies hashes of the declared pre/postimages, an observed hash,
    backup verification for a recognized partial state, a verified orphan-death
    observation, and the external counter for this idempotency key.  Any absent,
    widened, or contradictory value is deliberately the third-state path.
    """
    if not isinstance(inspection, dict) or set(inspection) != RECOVERY_INSPECTION_KEYS:
        raise StoreRefusal("POSTIMAGE_THIRD_STATE", "inspection shape")
    preimage, postimage, observed = (inspection["preimage_hash"], inspection["postimage_hash"],
                                     inspection["observed_hash"])
    if any(not isinstance(value, str) or len(value) != 64 for value in (preimage, postimage, observed)):
        raise StoreRefusal("POSTIMAGE_THIRD_STATE", "image hash")
    if not isinstance(inspection["partial"], bool) or not isinstance(inspection["orphan_verified"], bool):
        raise StoreRefusal("POSTIMAGE_THIRD_STATE", "boolean evidence")
    if not isinstance(inspection["external_call_count"], int) or inspection["external_call_count"] not in (0, 1):
        raise StoreRefusal("POSTIMAGE_THIRD_STATE", "external counter")
    if inspection["orphan_verified"] is not True:
        return {"observed": "third", "reason": "ORPHAN_IDENTITY_AMBIGUOUS", "retry": False}
    if inspection["partial"]:
        backup = inspection["backup"]
        if backup == "missing":
            return {"observed": "third", "reason": "BACKUP_MISSING", "retry": False}
        if backup == "hash_mismatch":
            return {"observed": "third", "reason": "BACKUP_HASH_MISMATCH", "retry": False}
        if backup == "verified" and inspection["external_call_count"] == 1:
            return {"observed": "partial", "reason": "whole_slice_rollback", "retry": True}
        return {"observed": "third", "reason": "PARTIAL_UNRECOGNIZED", "retry": False}
    if inspection["backup"] is not None:
        raise StoreRefusal("POSTIMAGE_THIRD_STATE", "backup outside partial")
    if observed == preimage and inspection["external_call_count"] == 0:
        return {"observed": "preimage", "reason": "exact_no_effect", "retry": True}
    if observed == postimage and inspection["external_call_count"] == 1:
        return {"observed": "postimage", "reason": "validate_without_rerun", "retry": False}
    return {"observed": "third", "reason": "POSTIMAGE_THIRD_STATE", "retry": False}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def record_hash(record: dict) -> str:
    unsigned = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def _safe_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value in (".", "..") or "/" in value or "\\" in value:
        raise StoreRefusal("RUN_IDENTITY_MISMATCH", f"invalid {label}")
    return value


def _regular(path: Path, *, missing_ok: bool = False) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or os.lstat(path).st_nlink != 1:
        raise StoreRefusal("RUN_IDENTITY_MISMATCH", f"unsafe path: {path.name}")


def _directory(path: Path) -> None:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as exc:
        raise StoreRefusal("RUN_IDENTITY_MISMATCH", f"missing directory: {path}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise StoreRefusal("RUN_IDENTITY_MISMATCH", f"unsafe directory: {path}")


def _directory_fsync(directory: Path) -> dict:
    """Observe directory durability support without promoting it to a guarantee."""
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        return {"directory_fsync": "unsupported", "reason": type(exc).__name__}
    return {"directory_fsync": "observed", "reason": None}


@dataclass
class WriterLock:
    store: "RunStore"
    handle: object
    nonce: str

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.close()
            data = self.store.lock_path.read_bytes()
            metadata = json.loads(data.decode("utf-8"))
            if metadata.get("nonce") != self.nonce:
                raise StoreRefusal("LOCK_IDENTITY_AMBIGUOUS")
            self.store.lock_path.unlink()
            _directory_fsync(self.store.run_dir)
        finally:
            self.handle = None

    def __enter__(self) -> "WriterLock":
        return self

    def __exit__(self, *_ignored: object) -> None:
        self.release()


class RunStore:
    """One explicit run directory with strict append/replay semantics."""

    def __init__(self, run_dir: str | Path, *, rules: dict, states: set[str], events: set[str]) -> None:
        self.run_dir = Path(run_dir)
        self.rules = rules
        self.states = set(states)
        self.events = set(events)
        self.run_path = self.run_dir / "run.json"
        self.events_path = self.run_dir / "events.jsonl"
        self.snapshot_path = self.run_dir / "snapshot.json"
        self.queue_path = self.run_dir / "owner-queue.json"
        self.lock_path = self.run_dir / "writer.lock"

    @classmethod
    def create(cls, runs_root: str | Path, run_id: str, identity: dict, *, rules: dict,
               states: set[str], events: set[str]) -> "RunStore":
        root = Path(runs_root)
        _directory(root)
        _safe_name(run_id, "run_id")
        if not isinstance(identity, dict) or identity.get("run_id") != run_id:
            raise StoreRefusal("RUN_IDENTITY_MISMATCH", "run_id")
        run_dir = root / run_id
        if run_dir.exists():
            raise StoreRefusal("RUN_IDENTITY_MISMATCH", "run already exists")
        run_dir.mkdir(mode=0o700)
        _directory(run_dir)
        store = cls(run_dir, rules=rules, states=states, events=events)
        required = {"schema_version", "contract_version", "run_id", "repository_root_hash",
                    "base_commit", "plan_id", "plan_hash", "mandate_hash", "acceptance_hash",
                    "created_at", "redaction_policy_hash"}
        if set(identity) != required or any(not isinstance(identity[key], str) or not identity[key]
                                            for key in required):
            raise StoreRefusal("INPUT_HASH_MISSING")
        store._atomic_json(store.run_path, identity)
        return store

    @classmethod
    def open(cls, run_dir: str | Path, *, rules: dict, states: set[str], events: set[str]) -> "RunStore":
        store = cls(run_dir, rules=rules, states=states, events=events)
        _directory(store.run_dir)
        _regular(store.run_path)
        identity = store.identity()
        if identity.get("run_id") != store.run_dir.name:
            raise StoreRefusal("RUN_IDENTITY_MISMATCH")
        return store

    def _assert_layout(self) -> None:
        _directory(self.run_dir)
        for path in (self.run_path, self.events_path, self.snapshot_path, self.queue_path, self.lock_path):
            _regular(path, missing_ok=True)

    def identity(self) -> dict:
        self._assert_layout()
        try:
            identity = json.loads(self.run_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StoreRefusal("RUN_IDENTITY_MISMATCH") from exc
        if not isinstance(identity, dict):
            raise StoreRefusal("RUN_IDENTITY_MISMATCH")
        return identity

    def acquire_writer(self) -> WriterLock:
        self._assert_layout()
        if fcntl is None:
            raise StoreRefusal("LOCK_IDENTITY_AMBIGUOUS", "POSIX flock unavailable")
        if self.lock_path.exists():
            try:
                metadata = json.loads(self.lock_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise StoreRefusal("LOCK_IDENTITY_AMBIGUOUS") from exc
            if not isinstance(metadata, dict) or metadata.get("run_id") != self.run_dir.name:
                raise StoreRefusal("LOCK_IDENTITY_AMBIGUOUS")
            raise StoreRefusal("LOCK_HELD")
        nonce = secrets.token_hex(16)
        metadata = {"run_id": self.run_dir.name, "pid": os.getpid(), "nonce": nonce}
        try:
            fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            handle = os.fdopen(fd, "wb", buffering=0)
            handle.write(canonical_bytes(metadata))
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except FileExistsError as exc:
            raise StoreRefusal("LOCK_HELD") from exc
        except OSError as exc:
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StoreRefusal("LOCK_HELD") from exc
        return WriterLock(self, handle, nonce)

    def _cut(self, fault_at: str | None, stage: str) -> None:
        if fault_at == stage:
            raise InjectedFailure(stage)

    def _atomic_json(self, target: Path, value: object, *, fault_at: str | None = None) -> dict:
        self._assert_layout()
        temp = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
        try:
            self._cut(fault_at, "temp_write")
            with open(temp, "xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(canonical_bytes(value) + b"\n")
                self._cut(fault_at, "temp_flush")
                stream.flush()
                self._cut(fault_at, "temp_fsync")
                os.fsync(stream.fileno())
            self._cut(fault_at, "replace")
            os.replace(temp, target)
            self._cut(fault_at, "directory_fsync")
            return _directory_fsync(self.run_dir)
        finally:
            temp.unlink(missing_ok=True)

    def _record_from(self, payload: dict, replay: dict) -> dict:
        required = {"ts", "run_id", "slice_id", "attempt", "event", "state_before",
                    "state_after", "idempotency_key", "input_hashes", "evidence", "redaction"}
        if set(payload) != required or payload.get("run_id") != self.run_dir.name:
            raise StoreRefusal("RUN_IDENTITY_MISMATCH")
        record = {"schema_version": EVENT_SCHEMA, "seq": replay["seq"] + 1,
                  "prev_hash": replay["tail_hash"], **payload, "record_hash": ""}
        self._validate_record(record, replay, duplicate_index=replay["duplicate_index"])
        record["record_hash"] = record_hash(record)
        return record

    def _validate_record(self, record: dict, replay: dict, *, duplicate_index: dict) -> None:
        if set(record) != RECORD_KEYS:
            raise StoreRefusal("UNKNOWN_RECORD_KEY")
        if record["schema_version"] != EVENT_SCHEMA:
            raise StoreRefusal("UNKNOWN_SCHEMA_VERSION")
        if not isinstance(record["seq"], int):
            raise StoreRefusal("SEQUENCE_GAP")
        if record["seq"] != replay["seq"] + 1:
            if record["seq"] == replay["seq"] + 2:
                raise StoreRefusal("REORDERED_RECORD")
            raise StoreRefusal("SEQUENCE_GAP")
        if record["prev_hash"] != replay["tail_hash"]:
            raise StoreRefusal("CHAIN_MISMATCH")
        if record["event"] not in self.events:
            raise StoreRefusal("UNKNOWN_EVENT")
        if record["state_before"] not in self.states or record["state_after"] not in self.states:
            raise StoreRefusal("UNKNOWN_STATE")
        if replay["state"] is not None and record["state_before"] != replay["state"]:
            raise StoreRefusal("ILLEGAL_TRANSITION")
        key = record["idempotency_key"]
        if record["event"] == "append_observation" and key not in replay["intents"]:
            raise StoreRefusal("OBSERVATION_WITHOUT_INTENT")
        expected = self.rules.get(record["state_before"], {}).get("on", {}).get(record["event"])
        if expected != record["state_after"]:
            raise StoreRefusal(self.rules.get(record["state_before"], {}).get("otherwise", "ILLEGAL_TRANSITION"))
        if key is not None:
            if not isinstance(key, str) or not key:
                raise StoreRefusal("IDEMPOTENCY_COLLISION")
            owner = (record["run_id"], record["slice_id"], record["attempt"])
            prior = replay["owners"].get(key)
            if prior is not None and prior != owner:
                raise StoreRefusal("IDEMPOTENCY_COLLISION")
            duplicate_key = (key, record["event"])
            unsigned = {name: value for name, value in record.items() if name not in {"seq", "prev_hash", "record_hash"}}
            prior_payload = duplicate_index.get(duplicate_key)
            if prior_payload is not None:
                raise StoreRefusal("DUPLICATE_EVENT" if prior_payload == unsigned else "IDEMPOTENCY_COLLISION")

    def replay(self) -> dict:
        self._assert_layout()
        identity = self.identity()
        try:
            raw = self.events_path.read_bytes()
        except FileNotFoundError:
            raw = b""
        except OSError as exc:
            raise StoreRefusal("TRUNCATED_RECORD") from exc
        if raw and not raw.endswith(b"\n"):
            raise StoreRefusal("TRUNCATED_RECORD")
        result = {"seq": 0, "tail_hash": ZERO_HASH, "state": None, "records": [],
                  "intents": set(), "owners": {}, "duplicate_index": {}, "record_hashes": set()}
        try:
            lines = raw.splitlines(keepends=True)
            for raw_line in lines:
                if not raw_line.endswith(b"\n") or raw_line == b"\n":
                    raise StoreRefusal("TRUNCATED_RECORD")
                try:
                    record = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise StoreRefusal("TRUNCATED_RECORD") from exc
                if not isinstance(record, dict):
                    raise StoreRefusal("UNKNOWN_RECORD_KEY")
                if record.get("record_hash") in result["record_hashes"]:
                    raise StoreRefusal("DUPLICATE_EVENT")
                self._validate_record(record, result, duplicate_index=result["duplicate_index"])
                if record_hash(record) != record.get("record_hash"):
                    raise StoreRefusal("HASH_MISMATCH")
                key = record["idempotency_key"]
                if key is not None:
                    result["owners"][key] = (record["run_id"], record["slice_id"], record["attempt"])
                    result["duplicate_index"][(key, record["event"])] = {
                        name: value for name, value in record.items() if name not in {"seq", "prev_hash", "record_hash"}}
                if record["event"] == "append_intent":
                    result["intents"].add(key)
                result["seq"], result["tail_hash"], result["state"] = record["seq"], record["record_hash"], record["state_after"]
                result["records"].append(record)
                result["record_hashes"].add(record["record_hash"])
        except StoreRefusal:
            raise
        if identity.get("run_id") != self.run_dir.name:
            raise StoreRefusal("RUN_IDENTITY_MISMATCH")
        return result

    def append_event(self, payload: dict, *, fault_at: str | None = None) -> dict:
        """Append under an existing writer lock, then reopen and verify the tail."""
        self._assert_layout()
        if not self.lock_path.exists():
            raise StoreRefusal("LOCK_HELD", "writer lock required")
        replay = self.replay()
        record = self._record_from(payload, replay)
        self._cut(fault_at, "append_write")
        with open(self.events_path, "ab", buffering=0) as stream:
            stream.write(canonical_bytes(record) + b"\n")
            self._cut(fault_at, "append_flush")
            stream.flush()
            self._cut(fault_at, "append_fsync")
            os.fsync(stream.fileno())
        self._cut(fault_at, "append_reopen")
        verified = self.replay()
        self._cut(fault_at, "append_verify")
        if verified["tail_hash"] != record["record_hash"] or verified["seq"] != record["seq"]:
            raise StoreRefusal("HASH_MISMATCH")
        return record

    def rebuild_snapshot(self, *, fault_at: str | None = None) -> dict:
        replay = self.replay()
        snapshot = {"schema_version": "supervisor-run-snapshot-v1", "run_id": self.run_dir.name,
                    "seq": replay["seq"], "tail_hash": replay["tail_hash"], "state": replay["state"]}
        capability = self._atomic_json(self.snapshot_path, snapshot, fault_at=fault_at)
        owner_queue = {"schema_version": "supervisor-owner-queue-v1", "run_id": self.run_dir.name,
                       "entries": []}
        self._atomic_json(self.queue_path, owner_queue, fault_at=fault_at)
        return {"snapshot": snapshot, "capability": capability}
