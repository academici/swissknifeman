"""Provider-neutral lease and reducer for Task terminal admission.

This module owns repository-side policy only.  A provider adapter supplies the
last response bytes and renders this verdict; it never infers plan terminality.
Runtime state is intentionally project-local and stores hashes, never messages.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from time import time
from typing import Callable


LEASE_SCHEMA = "terminal-admission-lease/v1"
EVENT_SCHEMA = "final-admission-event/v1"
_LIFECYCLES = frozenset(("active", "waiting-owner", "waiting-external", "released"))
_SHA256_LENGTH = 64
_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"


class AdmissionError(ValueError):
    """A stable local recovery diagnostic."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def validate_contracts() -> bool:
    """Keep runtime enums bound to the two committed schema carriers."""
    expected = (
        ("terminal-admission-lease-v1.schema.json", LEASE_SCHEMA, "lifecycle", sorted(_LIFECYCLES)),
        ("final-admission-event-v1.schema.json", EVENT_SCHEMA, None, None),
    )
    for filename, version, enum_key, enum in expected:
        try:
            schema = json.loads((_CONFIG_ROOT / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdmissionError("ADMISSION_SCHEMA_INVALID", filename) from exc
        if schema.get("schema_version") != version:
            raise AdmissionError("ADMISSION_SCHEMA_INVALID", f"{filename}: version")
        if enum_key and sorted(schema.get("properties", {}).get(enum_key, {}).get("enum", ())) != enum:
            raise AdmissionError("ADMISSION_SCHEMA_INVALID", f"{filename}: {enum_key}")
    return True


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now_iso(clock: Callable[[], float]) -> str:
    return datetime.fromtimestamp(clock(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalized_message(value: str) -> str:
    if not isinstance(value, str):
        raise AdmissionError("FINAL_MESSAGE_INVALID", "proposed message must be text")
    # Canonical output is machine-authored; CRLF normalisation is transport-only.
    return value.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True)
class Identity:
    plan_id: str
    subject: str
    command: str
    run_id: str
    task_session: str
    provider: str
    provider_session: str
    turn_id: str

    def validate(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in asdict(self).values()):
            raise AdmissionError("IDENTITY_INVALID", "all lease identities are required")

    def as_dict(self) -> dict[str, str]:
        self.validate()
        return asdict(self)

    def lease_key(self) -> dict[str, str]:
        """Return the stable run key; turn evidence remains event-local."""
        self.validate()
        return {
            "plan_id": self.plan_id,
            "subject": self.subject,
            "command": self.command,
            "run_id": self.run_id,
            "task_session": self.task_session,
            "provider": self.provider,
            "provider_session": self.provider_session,
        }


@dataclass(frozen=True)
class Lease:
    identity: Identity
    sequence: int
    progress_fingerprint: str
    continuity_sha256: str
    lifecycle: str
    issued_at: float
    refreshed_at: float
    expires_at: float
    schema_version: str = LEASE_SCHEMA

    def validate(self) -> None:
        self.identity.validate()
        if self.schema_version != LEASE_SCHEMA or self.lifecycle not in _LIFECYCLES:
            raise AdmissionError("LEASE_INVALID", "unsupported lease schema or lifecycle")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdmissionError("LEASE_INVALID", "sequence must be positive")
        if not isinstance(self.progress_fingerprint, str) or len(self.progress_fingerprint) != _SHA256_LENGTH:
            raise AdmissionError("LEASE_INVALID", "progress fingerprint must be sha256")
        if not isinstance(self.continuity_sha256, str) or len(self.continuity_sha256) != _SHA256_LENGTH:
            raise AdmissionError("LEASE_INVALID", "continuity identity must be sha256")
        if not all(isinstance(value, (int, float)) for value in (self.issued_at, self.refreshed_at, self.expires_at)):
            raise AdmissionError("LEASE_INVALID", "lease times must be numbers")
        if self.expires_at <= self.refreshed_at:
            raise AdmissionError("LEASE_INVALID", "lease expiry must follow refresh")

    def as_dict(self) -> dict:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "identity": self.identity.as_dict(),
            "sequence": self.sequence,
            "progress_fingerprint": self.progress_fingerprint,
            "continuity_sha256": self.continuity_sha256,
            "lifecycle": self.lifecycle,
            "issued_at": self.issued_at,
            "refreshed_at": self.refreshed_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "Lease":
        required = {"schema_version", "identity", "sequence", "progress_fingerprint",
                    "continuity_sha256", "lifecycle", "issued_at", "refreshed_at", "expires_at"}
        if not isinstance(value, dict) or set(value) != required or not isinstance(value.get("identity"), dict):
            raise AdmissionError("LEASE_INVALID", "lease shape is invalid")
        try:
            lease = cls(identity=Identity(**value["identity"]), **{key: value[key] for key in required - {"identity"}})
        except TypeError as exc:
            raise AdmissionError("LEASE_INVALID", "lease identity shape is invalid") from exc
        lease.validate()
        return lease


@dataclass(frozen=True)
class Verdict:
    final_allowed: bool
    reason: str
    continuation: str | None
    recovery: str | None
    sequence: int | None
    schema_version: str = EVENT_SCHEMA

    def as_dict(self) -> dict:
        return asdict(self)


class FileStore:
    """Atomic current lease + append-only JSONL evidence under one project-local root."""

    def __init__(self, directory: Path | str, *, clock: Callable[[], float] = time):
        self.directory = Path(directory)
        self.leases_dir = self.directory / "leases"
        self.events_path = self.directory / "events.jsonl"
        self.lock_path = self.directory / ".lock"
        self.clock = clock

    def path_for(self, identity: Identity) -> Path:
        """One lease per normalized provider session and Task run identity."""
        return self.leases_dir / f"{_sha(_canonical(identity.lease_key()))}.json"

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - supported targets are POSIX
                pass
            try:
                yield
            finally:
                try:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                except ImportError:  # pragma: no cover
                    pass

    def load(self, identity: Identity) -> Lease | None:
        path = self.path_for(identity)
        if not path.exists():
            return None
        try:
            lease = Lease.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, AdmissionError) as exc:
            raise AdmissionError("LEASE_INVALID", "current lease cannot be recovered; re-arm") from exc
        if lease.identity.lease_key() != identity.lease_key():
            raise AdmissionError("LEASE_AMBIGUOUS", "lease path identity mismatch; re-arm")
        return lease

    def replace(self, lease: Lease, *, expected_sequence: int | None, recover_invalid: bool = False) -> Lease:
        lease.validate()
        with self._locked():
            try:
                current = self.load(lease.identity)
            except AdmissionError:
                if not recover_invalid:
                    raise
                current = None
            observed = current.sequence if current is not None else None
            if observed != expected_sequence:
                raise AdmissionError("LEASE_SEQUENCE_CONFLICT", "concurrent lease update; resume and retry")
            target = self.path_for(lease.identity)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = _canonical(lease.as_dict()) + "\n"
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                                 prefix=".current.", suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        return lease

    def event(self, identity: Identity, verdict: Verdict, *, expected_message: str | None = None,
              observed_message: str | None = None, receipt: dict | None = None) -> None:
        event = {
            "schema_version": EVENT_SCHEMA,
            "ts": _now_iso(self.clock),
            "identity": identity.as_dict(),
            "final_allowed": verdict.final_allowed,
            "reason": verdict.reason,
            "continuation": verdict.continuation,
            "recovery": verdict.recovery,
            "sequence": verdict.sequence,
        }
        if expected_message is not None:
            event["expected_message_sha256"] = _sha(expected_message)
        if observed_message is not None:
            event["observed_message_sha256"] = _sha(observed_message)
        if receipt is not None:
            event["receipt_sha256"] = _sha(_canonical(receipt))
        with self._locked():
            with self.events_path.open("a", encoding="utf-8") as output:
                output.write(_canonical(event) + "\n")
                output.flush()
                os.fsync(output.fileno())


def _continuity_outcome(value: dict) -> str:
    from task import plan_continuity
    try:
        return plan_continuity.decision_from_dict(value).outcome
    except plan_continuity.ContinuityError as exc:
        raise AdmissionError("CONTINUITY_INVALID", "typed P1.3 continuity decision is required") from exc


def required_final_message(receipt: dict) -> str:
    """The sole canonical transcript fragment P4.1 may compare byte-for-byte."""
    from task import plan_delivery
    try:
        return plan_delivery.required_final_message(receipt)
    except plan_delivery.DeliveryError as exc:
        raise AdmissionError("STALE_TERMINAL_RECEIPT", str(exc)) from exc


def arm(store: FileStore, identity: Identity, continuity: dict, *, progress_fingerprint: str,
        ttl_seconds: int) -> Lease:
    validate_contracts()
    identity.validate()
    _continuity_outcome(continuity)
    if not isinstance(ttl_seconds, int) or ttl_seconds < 1:
        raise AdmissionError("LEASE_TTL_INVALID", "ttl_seconds must be a positive integer")
    now = store.clock()
    lease = Lease(identity=identity, sequence=1, progress_fingerprint=progress_fingerprint,
                  continuity_sha256=_sha(_canonical(continuity)), lifecycle="active",
                  issued_at=now, refreshed_at=now, expires_at=now + ttl_seconds)
    try:
        current = store.load(identity)
    except AdmissionError:
        current = None
    if current is not None and current.lifecycle in {"active", "waiting-owner", "waiting-external"} and now < current.expires_at:
        raise AdmissionError("LEASE_ALREADY_ACTIVE", "active lease must be refreshed or released")
    store.replace(lease, expected_sequence=current.sequence if current is not None else None,
                  recover_invalid=True)
    store.event(identity, Verdict(False, "LEASE_ARMED", "continue-root", None, lease.sequence))
    return lease


def refresh(store: FileStore, identity: Identity, *, expected_sequence: int, progress_fingerprint: str,
            continuity: dict, ttl_seconds: int) -> Lease:
    validate_contracts()
    _continuity_outcome(continuity)
    current = store.load(identity)
    if current is None or current.identity.lease_key() != identity.lease_key():
        raise AdmissionError("LEASE_NOT_APPLICABLE", "no matching lease; re-arm")
    if current.lifecycle == "released":
        raise AdmissionError("LEASE_RELEASED", "released lease requires re-arm")
    outcome = _continuity_outcome(continuity)
    if current.progress_fingerprint == progress_fingerprint and outcome not in {"waiting-owner", "waiting-external"}:
        raise AdmissionError("PROGRESS_UNCHANGED", "refresh requires material progress")
    now = store.clock()
    lifecycle = outcome if outcome in {"waiting-owner", "waiting-external"} else "active"
    lease = Lease(identity=identity, sequence=current.sequence + 1,
                  progress_fingerprint=progress_fingerprint, continuity_sha256=_sha(_canonical(continuity)),
                  lifecycle=lifecycle, issued_at=current.issued_at, refreshed_at=now,
                  expires_at=now + ttl_seconds)
    store.replace(lease, expected_sequence=expected_sequence)
    store.event(identity, Verdict(False, "LEASE_REFRESHED", lifecycle, None, lease.sequence))
    return lease


def release(store: FileStore, identity: Identity, *, expected_sequence: int, reason: str = "ABORTED") -> Lease:
    validate_contracts()
    current = store.load(identity)
    if current is None or current.identity.lease_key() != identity.lease_key():
        raise AdmissionError("LEASE_NOT_APPLICABLE", "no matching lease")
    now = store.clock()
    lease = Lease(identity=identity, sequence=current.sequence + 1,
                  progress_fingerprint=current.progress_fingerprint, continuity_sha256=current.continuity_sha256,
                  lifecycle="released", issued_at=current.issued_at, refreshed_at=now, expires_at=now + 1)
    store.replace(lease, expected_sequence=expected_sequence)
    store.event(identity, Verdict(False, reason, None, "re-arm", lease.sequence))
    return lease


def _verdict(store: FileStore, identity: Identity, verdict: Verdict, **event) -> Verdict:
    store.event(identity, verdict, **event)
    return verdict


def evaluate(store: FileStore, identity: Identity, continuity: dict, *, receipt_reader: Callable[[], dict],
             proposed_message: str) -> Verdict:
    """Return one total, non-provider-specific decision for a Stop attempt."""
    validate_contracts()
    identity.validate()
    try:
        lease = store.load(identity)
    except AdmissionError:
        return _verdict(store, identity, Verdict(False, "LEASE_INVALID", None, "re-arm", None),
                        observed_message=_normalized_message(proposed_message))
    if lease is None or lease.identity.lease_key() != identity.lease_key():
        return _verdict(store, identity, Verdict(False, "NOT_APPLICABLE", None, None, None))
    if lease.lifecycle == "released":
        return _verdict(store, identity, Verdict(False, "LEASE_RELEASED", None, "re-arm", lease.sequence))
    if store.clock() >= lease.expires_at:
        return _verdict(store, identity, Verdict(False, "LEASE_EXPIRED", None, "re-arm", lease.sequence))
    try:
        outcome = _continuity_outcome(continuity)
    except AdmissionError:
        return _verdict(store, identity, Verdict(False, "CONTINUITY_INVALID", None, "resume", lease.sequence))
    if _sha(_canonical(continuity)) != lease.continuity_sha256:
        return _verdict(store, identity, Verdict(False, "CONTINUITY_STALE", None, "refresh", lease.sequence))
    if outcome == "waiting-owner":
        return _verdict(store, identity, Verdict(False, "WAITING_OWNER", "waiting-owner", None, lease.sequence),
                        observed_message=_normalized_message(proposed_message))
    if outcome == "waiting-external":
        return _verdict(store, identity, Verdict(False, "WAITING_EXTERNAL", "waiting-external", None, lease.sequence),
                        observed_message=_normalized_message(proposed_message))
    # Chat completion of the admitted scope does not terminate the plan or
    # manufacture a fresh session. A cold-start boundary may deliver a handoff
    # only after the current subject has a valid terminal receipt as below.
    chat_boundary = (outcome == "cold-start-root" or (
        outcome == "continue-root" and continuity.get("reason") == "authorized-scope-complete"))
    if outcome != "terminal" and not chat_boundary:
        return _verdict(store, identity, Verdict(False, outcome.upper().replace("-", "_"), outcome, None, lease.sequence),
                        observed_message=_normalized_message(proposed_message))
    try:
        receipt = receipt_reader()
        expected = required_final_message(receipt)
        journal = receipt.get("journal", {})
        if (receipt.get("plan_id"), receipt.get("subject"), journal.get("run_id"), journal.get("command")) != (
                identity.plan_id, identity.subject, identity.run_id, identity.command):
            raise AdmissionError("STALE_TERMINAL_RECEIPT", "receipt identity does not match active lease")
    except AdmissionError as exc:
        return _verdict(store, identity, Verdict(False, exc.code, None, "re-arm", lease.sequence))
    except Exception:
        return _verdict(store, identity, Verdict(False, "STALE_TERMINAL_RECEIPT", None, "re-arm", lease.sequence))
    observed = _normalized_message(proposed_message)
    if observed != expected:
        return _verdict(store, identity, Verdict(False, "FINAL_MESSAGE_MISMATCH", "terminal-template", None, lease.sequence),
                        expected_message=expected, observed_message=observed, receipt=receipt)
    now = store.clock()
    released = Lease(identity=identity, sequence=lease.sequence + 1,
                     progress_fingerprint=lease.progress_fingerprint, continuity_sha256=lease.continuity_sha256,
                     lifecycle="released", issued_at=lease.issued_at, refreshed_at=now, expires_at=now + 1)
    try:
        store.replace(released, expected_sequence=lease.sequence)
    except AdmissionError:
        return _verdict(store, identity, Verdict(False, "LEASE_SEQUENCE_CONFLICT", None, "resume", lease.sequence))
    return _verdict(store, identity, Verdict(True, "FINAL_ALLOWED", None, None, released.sequence),
                    expected_message=expected, observed_message=observed, receipt=receipt)


def _identity(args) -> Identity:
    return Identity(plan_id=args.plan, subject=args.subject, command=args.command, run_id=args.run_id,
                    task_session=args.task_session, provider=args.provider,
                    provider_session=args.provider_session, turn_id=args.turn_id)


def _continuity(value: str) -> dict:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise AdmissionError("CONTINUITY_INVALID", "continuity-json must be JSON") from exc


def pre_final_open_runs(project_root: Path, provider_session: str) -> dict:
    """Inspect session-bound durable positions without requiring a proposed receipt.

    Only live project plan journals are inspected; archives and other projects are
    excluded. Observation events do not terminate a run. No product state is written.
    """
    from task import journal, plan_item_state, task_contract

    if not provider_session:
        raise AdmissionError("TERMINAL_ADMISSION_CONTEXT_INVALID", "нет provider session")
    observed = []
    worksets = []
    for path in sorted((Path(project_root) / "plans").glob("*/journal.jsonl")):
        rows = path.read_text(encoding="utf-8").splitlines()
        events = []
        for raw in rows:
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except ValueError:
                if provider_session in raw:
                    raise AdmissionError("TASK_FINAL_STATE_UNAVAILABLE", str(path))
                continue
            if isinstance(event, dict):
                events.append(event)
        subjects = {event.get("item_id") for event in events
                    if event.get("session_id") == provider_session
                    and re.fullmatch(r"P\d+\.\d+", str(event.get("item_id", "")))}
        for subject in sorted(subjects):
            history = [event for event in events if event.get("item_id") == subject]
            latest = plan_item_state.latest_execution_event(history)
            if latest is None or latest.get("session_id") != provider_session:
                continue
            try:
                journal.validate_entry(latest)
            except journal.JournalValidationError as exc:
                raise AdmissionError("TASK_FINAL_STATE_UNAVAILABLE", str(path)) from exc
            if latest.get("plan_id") != path.parent.name or not latest.get("run_id"):
                raise AdmissionError("TASK_FINAL_STATE_UNAVAILABLE", str(path))
            observed.append({"plan_id": path.parent.name, "item_id": subject,
                             "run_id": latest["run_id"], "state": latest["result"]})
        receipts = []
        for event in events:
            receipt = event.get("batch_receipt")
            if event.get("session_id") != provider_session or receipt is None:
                continue
            try:
                task_contract.validate_batch_receipt(receipt)
            except ValueError as exc:
                raise AdmissionError("TASK_FINAL_STATE_UNAVAILABLE", str(path)) from exc
            identity = (receipt["batch_id"], receipt["invocation_digest"])
            if identity not in {(row[0], row[1]) for row in receipts}:
                receipts.append((identity[0], identity[1], receipt))
        positions = {}
        subjects = {event.get("item_id") for event in events
                    if re.fullmatch(r"P\d+\.\d+", str(event.get("item_id", "")))}
        for subject in subjects:
            latest = plan_item_state.latest_execution_event(
                [event for event in events if event.get("item_id") == subject])
            if latest is not None:
                positions[subject] = latest
        for _batch_id, _digest, receipt in receipts:
            remaining = []
            boundary = None
            for member in receipt["membership"]:
                state = positions.get(member, {}).get("result")
                if state in {"closed-green", "closed-deviations"}:
                    continue
                if state in {"blocked", "escalated"}:
                    boundary = {"item_id": member, "state": state}
                    break
                remaining = receipt["membership"][receipt["membership"].index(member):]
                break
            worksets.append({"plan_id": path.parent.name, "batch_id": receipt["batch_id"],
                             "membership": receipt["membership"], "remaining": remaining,
                             "terminal_boundary": boundary})
    open_run = any(row["state"] == "in-progress" for row in observed)
    incomplete_workset = any(row["remaining"] and row["terminal_boundary"] is None
                             for row in worksets)
    # An unstarted remainder is reported, not forbidden: the final must name the exact
    # semantic Next. Only a run left open (in-progress) blocks the final.
    blocked = open_run
    verdict = {"final_allowed": not blocked,
               "reason": ("TASK_OPEN_RUN_FINAL_FORBIDDEN" if open_run else
                          "TASK_WORKSET_REMAINING" if incomplete_workset else
                          "NO_OPEN_SESSION_RUN"),
               "observed": observed, "worksets": worksets}
    if observed or worksets:
        store = FileStore(Path(project_root) / ".swissknifeman/terminal-admission")
        # Reuse the local admission journal; no response or user text is retained.
        with store._locked():
            with store.events_path.open("a", encoding="utf-8") as stream:
                stream.write(_canonical({"schema_version": "task-pre-final-open-run/v1",
                                         "session_id": provider_session, **verdict}) + "\n")
    return verdict


def _check_open_main(argv) -> int:
    parser = argparse.ArgumentParser(description="Session-bound Task pre-final check")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--provider-session", required=True)
    args = parser.parse_args(argv)
    try:
        value = pre_final_open_runs(args.project_root, args.provider_session)
    except (AdmissionError, OSError, UnicodeError) as exc:
        value = {"final_allowed": False,
                 "reason": exc.code if isinstance(exc, AdmissionError) else "TASK_FINAL_STATE_UNAVAILABLE"}
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value["final_allowed"] else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "check-open":
        return _check_open_main(argv[1:])
    parser = argparse.ArgumentParser(description="Lease-bound Task terminal admission")
    parser.add_argument("command", choices=("arm", "refresh", "check", "release"))
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--subject", required=True)
    # `plan-exec` is the legacy spelling of `plan-run`.
    parser.add_argument("--command", dest="task_command", required=True,
                        choices=("plan-run", "plan-exec", "plan-close", "plan-audit"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-session", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--provider-session", required=True)
    parser.add_argument("--turn-id", required=True)
    parser.add_argument("--continuity-json", required=True)
    parser.add_argument("--progress-fingerprint")
    parser.add_argument("--ttl-seconds", type=int, default=900)
    parser.add_argument("--expected-sequence", type=int)
    parser.add_argument("--message", default="")
    parser.add_argument("--plan-dir")
    args = parser.parse_args(argv)
    args.command, args.task_command = args.task_command, args.command
    store = FileStore(args.state_dir)
    try:
        identity = _identity(args)
        continuation = _continuity(args.continuity_json)
        if args.task_command == "arm":
            if args.progress_fingerprint is None:
                parser.error("arm requires --progress-fingerprint")
            value = arm(store, identity, continuation, progress_fingerprint=args.progress_fingerprint, ttl_seconds=args.ttl_seconds).as_dict()
        elif args.task_command == "refresh":
            if args.progress_fingerprint is None or args.expected_sequence is None:
                parser.error("refresh requires --progress-fingerprint and --expected-sequence")
            value = refresh(store, identity, expected_sequence=args.expected_sequence,
                            progress_fingerprint=args.progress_fingerprint, continuity=continuation,
                            ttl_seconds=args.ttl_seconds).as_dict()
        elif args.task_command == "release":
            if args.expected_sequence is None:
                parser.error("release requires --expected-sequence")
            value = release(store, identity, expected_sequence=args.expected_sequence).as_dict()
        else:
            from task import plan_delivery
            receipt_reader = (lambda: plan_delivery.build_terminal_receipt(args.plan_dir, args.subject)) if args.plan_dir else (
                lambda: (_ for _ in ()).throw(AdmissionError("STALE_TERMINAL_RECEIPT", "check needs --plan-dir for an applicable terminal lease")))
            value = evaluate(store, identity, continuation,
                             receipt_reader=receipt_reader,
                             proposed_message=args.message).as_dict()
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0
    except AdmissionError as exc:
        print(json.dumps({"final_allowed": False, "reason": exc.code, "recovery": "re-arm"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
