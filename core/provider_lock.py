"""Fail-closed planning and explicit application for provider artifacts.

The module owns a versioned sidecar lock, not provider discovery or rendering.
Planning is pure and application accepts only a caller-provided root plus the
immutable plan it produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterable, Mapping

from .provider_artifact import (ArtifactProvenance, ArtifactRenderResult,
                                ArtifactSource, canonical_json_bytes, sha256_digest,
                                validate_target_path)
from .provider import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel
from .paths import is_within, is_within_lexical


LOCK_SCHEMA_VERSION = 1
LOCK_RELATIVE_PATH = ".swissknifeman/provider-artifacts.lock.json"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_BOOTSTRAP_DECISION_ID = "D104"
_BOOTSTRAP_EXISTING_TARGET = ".codex/hooks.json"
_BOOTSTRAP_PREIMAGE = "sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db"
_BOOTSTRAP_CREATED_TARGET = ".codex/hooks/lifecycle.py"
_BOOTSTRAP_EXISTING_ARTIFACT = "harness.codex.lifecycle.hooks"
_BOOTSTRAP_CREATED_ARTIFACT = "harness.codex.lifecycle.handler"


class DriftObservation(str, Enum):
    CLEAN = "clean"
    MISSING = "missing"
    STALE_SOURCE = "stale-source"
    MANAGED_DRIFT = "managed-drift"
    BOUNDARY_INVALID = "boundary-invalid"
    PROVENANCE_INVALID = "provenance-invalid"
    OWNERSHIP_CONFLICT = "ownership-conflict"
    UNSUPPORTED = "unsupported"


class ArtifactActionKind(str, Enum):
    NOOP = "noop"
    CREATE = "create"
    UPDATE = "update"
    REPAIR = "repair"
    REFUSE = "refuse"


@dataclass(frozen=True)
class BootstrapTransferAdmission:
    """The sole D104 exception that can transfer an unmanaged bootstrap preimage.

    The descriptor is caller supplied, but its values are checked against the
    closed D104 admission both while planning and immediately before each write.
    It does not alter ordinary artifact planning, update, or repair semantics.
    """

    decision_id: str
    existing_target_path: str
    existing_preimage_sha256: str
    created_target_path: str
    existing_artifact_id: str
    created_artifact_id: str
    require_absent_lock: bool = True

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) for value in (
                self.decision_id, self.existing_target_path,
                self.existing_preimage_sha256, self.created_target_path,
                self.existing_artifact_id, self.created_artifact_id)):
            raise TypeError("bootstrap transfer admission fields must be strings")
        validate_target_path(self.existing_target_path)
        validate_target_path(self.created_target_path)
        if not _DIGEST_RE.fullmatch(self.existing_preimage_sha256):
            raise ValueError("bootstrap transfer preimage must be a SHA-256 digest")
        if not _IDENTIFIER_RE.fullmatch(self.existing_artifact_id) or not _IDENTIFIER_RE.fullmatch(
                self.created_artifact_id):
            raise ValueError("bootstrap transfer artifact IDs are invalid")
        if self.existing_target_path == self.created_target_path:
            raise ValueError("bootstrap transfer targets must differ")
        if self.existing_artifact_id == self.created_artifact_id:
            raise ValueError("bootstrap transfer artifact IDs must differ")
        if self.require_absent_lock is not True:
            raise ValueError("bootstrap transfer requires an absent lock")


@dataclass(frozen=True)
class ArtifactLock:
    """Canonical v1 sidecar lock with exactly one record per artifact and target."""

    schema_version: int
    records: tuple[ArtifactProvenance, ...]

    def __post_init__(self) -> None:
        if self.schema_version != LOCK_SCHEMA_VERSION:
            raise ValueError("unsupported lock schema version")
        if not isinstance(self.records, tuple) or not all(isinstance(record, ArtifactProvenance)
                                                          for record in self.records):
            raise TypeError("records must be a tuple of ArtifactProvenance")
        ordered = tuple(sorted(self.records, key=lambda record: record.artifact_id))
        if len({record.artifact_id for record in ordered}) != len(ordered):
            raise ValueError("lock records must not repeat artifact IDs")
        if len({record.target_path for record in ordered}) != len(ordered):
            raise ValueError("lock records must not repeat target paths")
        object.__setattr__(self, "records", ordered)


@dataclass(frozen=True)
class ArtifactAction:
    """One deterministic no-write decision; bytes are applied only by ``apply_plan``."""

    artifact_id: str
    target_path: str
    observation: DriftObservation
    action: ArtifactActionKind
    expected: ArtifactRenderResult
    observed_hash: str | None
    diagnostic: str
    managed_block_codec: tuple[Callable[[bytes, tuple[str, ...]], bytes],
                               Callable[[bytes, bytes, tuple[str, ...]], bytes]] | None = None


@dataclass(frozen=True)
class ArtifactPlan:
    """A complete immutable plan, including the lock that successful apply writes."""

    actions: tuple[ArtifactAction, ...]
    next_lock: ArtifactLock | None
    lock_path: str = LOCK_RELATIVE_PATH
    bootstrap_transfer: BootstrapTransferAdmission | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple) or not all(isinstance(action, ArtifactAction)
                                                          for action in self.actions):
            raise TypeError("actions must be a tuple of ArtifactAction")
        ordered = tuple(sorted(self.actions, key=lambda action: (action.target_path, action.artifact_id)))
        if len({action.target_path for action in ordered}) != len(ordered):
            raise ValueError("actions must not repeat target paths")
        if self.next_lock is not None and not isinstance(self.next_lock, ArtifactLock):
            raise TypeError("next_lock must be ArtifactLock or None")
        if self.bootstrap_transfer is not None and not isinstance(
                self.bootstrap_transfer, BootstrapTransferAdmission):
            raise TypeError("bootstrap_transfer must be BootstrapTransferAdmission or None")
        validate_target_path(self.lock_path)
        object.__setattr__(self, "actions", ordered)


def artifact_dry_run(plan: ArtifactPlan) -> dict[str, object]:
    """Project one immutable plan for machine-readable no-write preview output.

    The returned value is derived only from ``plan``.  It deliberately neither
    reads a root nor calls ``apply_plan``; callers must pass this same plan to
    application if they later choose an explicit write operation.
    """
    return _plan_projection(plan, "dry-run")


def artifact_doctor(plan: ArtifactPlan) -> dict[str, object]:
    """Project one immutable plan into deterministic no-write doctor data."""
    return _plan_projection(plan, "doctor")


def render_artifact_projection(projection: dict[str, object]) -> str:
    """Render a stable Russian human view of a dry-run or doctor projection."""
    if not isinstance(projection, dict):
        raise TypeError("projection must be a dict")
    if set(projection) != {"actions", "exit_severity", "mode", "plan_id"}:
        raise ValueError("projection has an unsupported shape")
    mode = projection["mode"]
    severity = projection["exit_severity"]
    plan_id = projection["plan_id"]
    actions = projection["actions"]
    if mode not in {"dry-run", "doctor"} or severity not in {"green", "warning", "error"}:
        raise ValueError("projection has an unsupported value")
    if not isinstance(plan_id, str) or not isinstance(actions, list):
        raise ValueError("projection has an unsupported shape")
    lines = [f"Режим: {mode}", f"План: {plan_id}", f"Статус: {severity}"]
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("projection action has an unsupported shape")
        try:
            lines.append("- {artifact_id}: {observation} → {action} ({diagnostic})".format(**action))
        except (KeyError, TypeError) as error:
            raise ValueError("projection action has an unsupported shape") from error
    return "\n".join(lines) + "\n"


def serialize_lock(lock: ArtifactLock) -> bytes:
    """Return canonical JSON bytes for a supported lock; timestamps are forbidden."""
    if not isinstance(lock, ArtifactLock):
        raise TypeError("lock must be ArtifactLock")
    value = {"schema_version": lock.schema_version,
             "records": [_provenance_value(record) for record in lock.records]}
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8") + b"\n"


def _plan_projection(plan: ArtifactPlan, mode: str) -> dict[str, object]:
    if not isinstance(plan, ArtifactPlan):
        raise TypeError("plan must be ArtifactPlan")
    actions = [{
        "action": action.action.value,
        "artifact_id": action.artifact_id,
        "diagnostic": action.diagnostic,
        "observation": action.observation.value,
        "target_path": action.target_path,
    } for action in plan.actions]
    identity = {
        "actions": [{
            "action": action["action"], "artifact_id": action["artifact_id"],
            "diagnostic": action["diagnostic"], "observation": action["observation"],
            "target_path": action["target_path"],
        } for action in actions],
        "lock_path": plan.lock_path,
        "next_lock": sha256_digest(serialize_lock(plan.next_lock)) if plan.next_lock else None,
    }
    if any(action.action is ArtifactActionKind.REFUSE for action in plan.actions):
        severity = "error"
    elif any(action.action is not ArtifactActionKind.NOOP for action in plan.actions):
        severity = "warning"
    else:
        severity = "green"
    return {"mode": mode, "plan_id": sha256_digest(canonical_json_bytes(identity)),
            "exit_severity": severity, "actions": actions}


def parse_lock(raw: bytes) -> ArtifactLock:
    """Parse only the canonical v1 shape; malformed/newer locks fail closed."""
    if not isinstance(raw, bytes):
        raise TypeError("raw lock must be bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("corrupt lock") from error
    if not isinstance(value, dict) or set(value) != {"records", "schema_version"}:
        raise ValueError("corrupt lock")
    if value["schema_version"] != LOCK_SCHEMA_VERSION:
        raise ValueError("unsupported lock schema version")
    if not isinstance(value["records"], list):
        raise ValueError("corrupt lock")
    try:
        lock = ArtifactLock(LOCK_SCHEMA_VERSION, tuple(_provenance_from_value(item)
                                                       for item in value["records"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("corrupt lock") from error
    if serialize_lock(lock) != raw:
        raise ValueError("lock is not canonically serialized")
    return lock


def plan_artifact_lock(root: Path, expected: Iterable[ArtifactRenderResult], *,
                       lock_bytes: bytes | None, repair_artifact_ids: tuple[str, ...] = (),
                       unsupported_artifact_ids: tuple[str, ...] = (),
                       retain_unexpected_records: bool = False,
                       managed_block_codecs: Mapping[str, tuple[
                           Callable[[bytes, tuple[str, ...]], bytes],
                           Callable[[bytes, bytes, tuple[str, ...]], bytes]]] | None = None) -> ArtifactPlan:
    """Classify expected artifacts without changing disk, lock, backups, or root."""
    root = _root(root)
    results = tuple(sorted(_results(expected), key=lambda result: result.target.path))
    repairs = frozenset(repair_artifact_ids)
    unsupported = frozenset(unsupported_artifact_ids)
    codecs = _managed_block_codecs(managed_block_codecs, results)
    if not repairs.isdisjoint(unsupported):
        raise ValueError("repair and unsupported IDs must not overlap")
    lock, lock_problem = _read_lock(lock_bytes)
    records_by_id = {record.artifact_id: record for record in lock.records} if lock else {}
    records_by_target = {record.target_path: record for record in lock.records} if lock else {}
    actions = []
    for result in results:
        provenance = result.provenance
        target = root / provenance.target_path
        observation, action, observed_hash, diagnostic = _classify(
            target, result, records_by_id.get(provenance.artifact_id),
            records_by_target.get(provenance.target_path), lock_problem,
            provenance.artifact_id in repairs, provenance.artifact_id in unsupported, root,
            codecs.get(provenance.artifact_id))
        actions.append(ArtifactAction(provenance.artifact_id, provenance.target_path,
                                      observation, action, result, observed_hash, diagnostic,
                                      codecs.get(provenance.artifact_id)))
    expected_records = tuple(result.provenance for result in results)
    retained_records = ()
    if retain_unexpected_records and lock is not None:
        expected_ids = {record.artifact_id for record in expected_records}
        expected_targets = {record.target_path for record in expected_records}
        retained_records = tuple(record for record in lock.records
                                 if record.artifact_id not in expected_ids
                                 and record.target_path not in expected_targets)
    next_lock = None if any(action.action is ArtifactActionKind.REFUSE for action in actions) else ArtifactLock(
        LOCK_SCHEMA_VERSION, expected_records + retained_records)
    return ArtifactPlan(tuple(actions), next_lock)


def plan_bootstrap_transfer(root: Path, expected: Iterable[ArtifactRenderResult], *,
                            lock_bytes: bytes | None,
                            admission: BootstrapTransferAdmission) -> ArtifactPlan:
    """Plan the closed D104 bootstrap transfer without writing to ``root``.

    This is intentionally not an alternative to :func:`plan_artifact_lock`.
    Only the exact recorded D104 preimage, pair of target-relative paths and
    two artifact IDs can enter this one transaction.  Every other preimage or
    target remains an ordinary ownership conflict.
    """
    root = _root(root)
    results = tuple(sorted(_results(expected), key=lambda result: result.target.path))
    if not isinstance(admission, BootstrapTransferAdmission):
        raise TypeError("admission must be BootstrapTransferAdmission")
    error = _bootstrap_admission_error(admission, results, lock_bytes, root)
    if error is not None:
        return _refused_bootstrap_plan(results, admission, error)
    by_target = {result.target.path: result for result in results}
    existing = by_target[admission.existing_target_path]
    created = by_target[admission.created_target_path]
    actions = (
        ArtifactAction(existing.provenance.artifact_id, existing.target.path,
                       DriftObservation.OWNERSHIP_CONFLICT, ArtifactActionKind.UPDATE,
                       existing, sha256_digest((root / existing.target.path).read_bytes()),
                       "bootstrap-transfer-admitted"),
        ArtifactAction(created.provenance.artifact_id, created.target.path,
                       DriftObservation.MISSING, ArtifactActionKind.CREATE,
                       created, None, "bootstrap-transfer-admitted"),
    )
    return ArtifactPlan(actions, ArtifactLock(LOCK_SCHEMA_VERSION,
                                              tuple(result.provenance for result in results)),
                        bootstrap_transfer=admission)


def apply_plan(root: Path, plan: ArtifactPlan) -> ArtifactPlan:
    """Apply an already computed plan under one explicit root, or refuse without writes.

    Repair writes a recoverable ``.provider-artifact.bak`` pre-image beside its target.
    Precondition checks are repeated immediately before every write.
    """
    root = _root(root)
    if not isinstance(plan, ArtifactPlan):
        raise TypeError("plan must be ArtifactPlan")
    if plan.bootstrap_transfer is not None:
        return _apply_bootstrap_transfer(root, plan)
    if _is_bootstrap_transfer_shape(plan):
        raise ValueError("bootstrap transfer plan is missing admission")
    if plan.next_lock is None or any(action.action is ArtifactActionKind.REFUSE for action in plan.actions):
        raise ValueError("refusing plan cannot be applied")
    writable = tuple(action for action in plan.actions if action.action is not ArtifactActionKind.NOOP)
    if not writable:
        return plan
    for action in writable:
        target = _contained_target(root, action.target_path)
        current = _managed_hash(target, action.expected, action.managed_block_codec)
        if current != action.observed_hash:
            raise ValueError("target changed after planning")
    for action in writable:
        target = _contained_target(root, action.target_path)
        if action.action is ArtifactActionKind.REPAIR and target.exists():
            _atomic_write_bytes(target.with_name(target.name + ".provider-artifact.bak"),
                                target.read_bytes())
        _atomic_write_bytes(target, _replacement_bytes(target, action.expected,
                                                        action.managed_block_codec))
    _atomic_write_bytes(_contained_target(root, plan.lock_path), serialize_lock(plan.next_lock))
    return plan_artifact_lock(root, (action.expected for action in plan.actions),
                              lock_bytes=serialize_lock(plan.next_lock),
                              retain_unexpected_records=True,
                              managed_block_codecs={
                                  action.artifact_id: action.managed_block_codec
                                  for action in plan.actions if action.managed_block_codec is not None})


def _refused_bootstrap_plan(results: tuple[ArtifactRenderResult, ...],
                            admission: BootstrapTransferAdmission,
                            diagnostic: str) -> ArtifactPlan:
    actions = tuple(ArtifactAction(
        result.provenance.artifact_id, result.target.path,
        DriftObservation.OWNERSHIP_CONFLICT, ArtifactActionKind.REFUSE,
        result, None, diagnostic) for result in results)
    return ArtifactPlan(actions, None, bootstrap_transfer=admission)


def _bootstrap_admission_error(admission: BootstrapTransferAdmission,
                               results: tuple[ArtifactRenderResult, ...],
                               lock_bytes: bytes | None, root: Path) -> str | None:
    if (admission.decision_id != _BOOTSTRAP_DECISION_ID or
            admission.existing_target_path != _BOOTSTRAP_EXISTING_TARGET or
            admission.existing_preimage_sha256 != _BOOTSTRAP_PREIMAGE or
            admission.created_target_path != _BOOTSTRAP_CREATED_TARGET or
            admission.existing_artifact_id != _BOOTSTRAP_EXISTING_ARTIFACT or
            admission.created_artifact_id != _BOOTSTRAP_CREATED_ARTIFACT or
            admission.require_absent_lock is not True):
        return "bootstrap-admission-invalid"
    by_target = {result.target.path: result for result in results}
    if set(by_target) != {_BOOTSTRAP_EXISTING_TARGET, _BOOTSTRAP_CREATED_TARGET}:
        return "bootstrap-target-set-invalid"
    existing = by_target[_BOOTSTRAP_EXISTING_TARGET]
    created = by_target[_BOOTSTRAP_CREATED_TARGET]
    if (existing.provenance.artifact_id != _BOOTSTRAP_EXISTING_ARTIFACT or
            created.provenance.artifact_id != _BOOTSTRAP_CREATED_ARTIFACT or
            existing.provenance.managed_boundary != ("whole-file", ()) or
            created.provenance.managed_boundary != ("whole-file", ())):
        return "bootstrap-artifact-set-invalid"
    if lock_bytes is not None:
        return "bootstrap-lock-present"
    lock_path = _contained_target(root, LOCK_RELATIVE_PATH)
    existing_path = _contained_target(root, _BOOTSTRAP_EXISTING_TARGET)
    created_path = _contained_target(root, _BOOTSTRAP_CREATED_TARGET)
    backup_path = existing_path.with_name(existing_path.name +
                                          ".provider-artifact.bootstrap-transfer.bak")
    if lock_path.exists() or lock_path.is_symlink():
        return "bootstrap-lock-present"
    if not existing_path.is_file() or existing_path.is_symlink():
        return "bootstrap-preimage-missing"
    if sha256_digest(existing_path.read_bytes()) != _BOOTSTRAP_PREIMAGE:
        return "bootstrap-preimage-mismatch"
    if created_path.exists() or created_path.is_symlink():
        return "bootstrap-created-target-present"
    if backup_path.exists() or backup_path.is_symlink():
        return "bootstrap-backup-present"
    return None


def _apply_bootstrap_transfer(root: Path, plan: ArtifactPlan) -> ArtifactPlan:
    admission = plan.bootstrap_transfer
    if admission is None:  # pragma: no cover - dispatch guards this branch
        raise ValueError("bootstrap transfer admission is missing")
    if plan.lock_path != LOCK_RELATIVE_PATH:
        raise ValueError("bootstrap transfer lock path is invalid")
    results = tuple(sorted((action.expected for action in plan.actions),
                           key=lambda result: result.target.path))
    error = _bootstrap_admission_error(admission, results, None, root)
    if error is not None or plan.next_lock is None:
        raise ValueError(error or "bootstrap transfer plan is invalid")
    expected_lock = ArtifactLock(LOCK_SCHEMA_VERSION,
                                 tuple(result.provenance for result in results))
    if plan.next_lock != expected_lock or any(action.action is ArtifactActionKind.REFUSE
                                               for action in plan.actions):
        raise ValueError("bootstrap transfer plan is invalid")
    actions_by_target = {action.target_path: action for action in plan.actions}
    if (set(actions_by_target) != {_BOOTSTRAP_EXISTING_TARGET, _BOOTSTRAP_CREATED_TARGET} or
            actions_by_target[_BOOTSTRAP_EXISTING_TARGET].action is not ArtifactActionKind.UPDATE or
            actions_by_target[_BOOTSTRAP_CREATED_TARGET].action is not ArtifactActionKind.CREATE):
        raise ValueError("bootstrap transfer plan is invalid")
    by_target = {result.target.path: result for result in results}
    existing = by_target[_BOOTSTRAP_EXISTING_TARGET]
    created = by_target[_BOOTSTRAP_CREATED_TARGET]
    existing_path = _contained_target(root, _BOOTSTRAP_EXISTING_TARGET)
    created_path = _contained_target(root, _BOOTSTRAP_CREATED_TARGET)
    backup_path = existing_path.with_name(existing_path.name +
                                          ".provider-artifact.bootstrap-transfer.bak")
    lock_path = _contained_target(root, plan.lock_path)
    lock_value = serialize_lock(expected_lock)
    try:
        _bootstrap_write_state(root, admission, results, "backup")
        _atomic_write_bytes(backup_path, existing_path.read_bytes())
        _bootstrap_write_state(root, admission, results, "existing")
        _atomic_write_bytes(existing_path, existing.managed_bytes)
        _bootstrap_write_state(root, admission, results, "created")
        _atomic_write_bytes(created_path, created.managed_bytes)
        _bootstrap_write_state(root, admission, results, "lock")
        _atomic_write_bytes(lock_path, lock_value)
    except BaseException:
        _rollback_bootstrap_transfer(existing_path, created_path, backup_path, lock_path,
                                     existing.managed_bytes, created.managed_bytes, lock_value,
                                     admission.existing_preimage_sha256)
        raise
    return plan_artifact_lock(root, results, lock_bytes=lock_value)


def _is_bootstrap_transfer_shape(plan: ArtifactPlan) -> bool:
    """Recognize a reconstructed D104 transaction before ordinary dispatch."""
    actions_by_target = {action.target_path: action for action in plan.actions}
    if set(actions_by_target) != {_BOOTSTRAP_EXISTING_TARGET, _BOOTSTRAP_CREATED_TARGET}:
        return False
    existing = actions_by_target[_BOOTSTRAP_EXISTING_TARGET]
    created = actions_by_target[_BOOTSTRAP_CREATED_TARGET]
    return (existing.action is ArtifactActionKind.UPDATE and
            created.action is ArtifactActionKind.CREATE and
            existing.expected.provenance.artifact_id == _BOOTSTRAP_EXISTING_ARTIFACT and
            created.expected.provenance.artifact_id == _BOOTSTRAP_CREATED_ARTIFACT)


def _bootstrap_write_state(root: Path, admission: BootstrapTransferAdmission,
                           results: tuple[ArtifactRenderResult, ...], stage: str) -> None:
    error = _bootstrap_admission_error(admission, results, None, root)
    if stage == "backup":
        if error is not None:
            raise ValueError(error)
        return
    existing_path = _contained_target(root, _BOOTSTRAP_EXISTING_TARGET)
    created_path = _contained_target(root, _BOOTSTRAP_CREATED_TARGET)
    backup_path = existing_path.with_name(existing_path.name +
                                          ".provider-artifact.bootstrap-transfer.bak")
    lock_path = _contained_target(root, LOCK_RELATIVE_PATH)
    by_target = {result.target.path: result for result in results}
    existing = by_target[_BOOTSTRAP_EXISTING_TARGET]
    created = by_target[_BOOTSTRAP_CREATED_TARGET]
    if not backup_path.exists() or backup_path.is_symlink():
        raise ValueError("bootstrap backup changed after planning")
    if lock_path.exists() or lock_path.is_symlink():
        raise ValueError("bootstrap lock changed after planning")
    if stage == "existing":
        if backup_path.read_bytes() != existing_path.read_bytes():
            raise ValueError("bootstrap backup changed after planning")
        if sha256_digest(existing_path.read_bytes()) != admission.existing_preimage_sha256:
            raise ValueError("bootstrap preimage changed after planning")
        if created_path.exists() or created_path.is_symlink():
            raise ValueError("bootstrap created target changed after planning")
        return
    if sha256_digest(backup_path.read_bytes()) != admission.existing_preimage_sha256:
        raise ValueError("bootstrap backup changed after planning")
    if sha256_digest(existing_path.read_bytes()) != existing.provenance.rendered_hash:
        raise ValueError("bootstrap existing target changed after planning")
    if stage == "created":
        if created_path.exists() or created_path.is_symlink():
            raise ValueError("bootstrap created target changed after planning")
        return
    if stage == "lock" and sha256_digest(created_path.read_bytes()) == created.provenance.rendered_hash:
        return
    raise ValueError("bootstrap transaction changed after planning")


def _rollback_bootstrap_transfer(existing_path: Path, created_path: Path, backup_path: Path,
                                 lock_path: Path, existing_bytes: bytes, created_bytes: bytes,
                                 lock_bytes: bytes, preimage_hash: str) -> None:
    if lock_path.exists() and not lock_path.is_symlink() and lock_path.read_bytes() == lock_bytes:
        lock_path.unlink()
    if created_path.exists() and not created_path.is_symlink() and created_path.read_bytes() == created_bytes:
        created_path.unlink()
    if (backup_path.exists() and not backup_path.is_symlink() and
            sha256_digest(backup_path.read_bytes()) == preimage_hash and
            existing_path.exists() and not existing_path.is_symlink() and
            existing_path.read_bytes() == existing_bytes):
        _atomic_write_bytes(existing_path, backup_path.read_bytes())


def _classify(target: Path, result: ArtifactRenderResult, record: ArtifactProvenance | None,
              target_record: ArtifactProvenance | None, lock_problem: str | None,
              repair_requested: bool, unsupported: bool, root: Path,
              codec: tuple[Callable[[bytes, tuple[str, ...]], bytes],
                           Callable[[bytes, bytes, tuple[str, ...]], bytes]] | None) -> tuple[DriftObservation, ArtifactActionKind, str | None, str]:
    provenance = result.provenance
    if unsupported:
        return DriftObservation.UNSUPPORTED, ArtifactActionKind.REFUSE, None, "unsupported"
    if lock_problem:
        return DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE, None, lock_problem
    if not _safe_target(target, root):
        return DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE, None, "unsafe-target"
    if provenance.managed_boundary[0] == "managed-blocks":
        if codec is None:
            return DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE, None, "block-codec-not-supplied"
        if target.exists() and _managed_hash(target, result, codec) is None:
            return DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE, None, "block-extraction-invalid"
    if target_record is not None and target_record.artifact_id != provenance.artifact_id:
        return DriftObservation.OWNERSHIP_CONFLICT, ArtifactActionKind.REFUSE, None, "target-owned-by-other-artifact"
    if record is None:
        if target.exists() or target.is_symlink():
            return DriftObservation.OWNERSHIP_CONFLICT, ArtifactActionKind.REFUSE, _managed_hash(target, result, codec), "unmanaged-target"
        return DriftObservation.MISSING, ArtifactActionKind.CREATE, None, "missing"
    if not _matching_identity(record, provenance):
        return DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE, _managed_hash(target, result, codec), "record-identity-mismatch"
    if not target.exists():
        return DriftObservation.MISSING, ArtifactActionKind.CREATE, None, "missing"
    observed_hash = _managed_hash(target, result, codec)
    if observed_hash is None:
        return DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE, None, "block-extraction-invalid"
    if observed_hash != record.rendered_hash:
        if repair_requested:
            return DriftObservation.MANAGED_DRIFT, ArtifactActionKind.REPAIR, observed_hash, "explicit-repair"
        return DriftObservation.MANAGED_DRIFT, ArtifactActionKind.REFUSE, observed_hash, "repair-required"
    if record != provenance:
        if record.source_hash == provenance.source_hash:
            return DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE, observed_hash, "record-provenance-mismatch"
        return DriftObservation.STALE_SOURCE, ArtifactActionKind.UPDATE, observed_hash, "source-changed"
    return DriftObservation.CLEAN, ArtifactActionKind.NOOP, observed_hash, "clean"


def _read_lock(lock_bytes: bytes | None) -> tuple[ArtifactLock | None, str | None]:
    if lock_bytes is None:
        return ArtifactLock(LOCK_SCHEMA_VERSION, ()), None
    try:
        return parse_lock(lock_bytes), None
    except ValueError as error:
        return None, str(error)


def _results(expected: Iterable[ArtifactRenderResult]) -> tuple[ArtifactRenderResult, ...]:
    values = tuple(expected)
    if not values or not all(isinstance(value, ArtifactRenderResult) for value in values):
        raise ValueError("expected must be a non-empty iterable of ArtifactRenderResult")
    if len({value.provenance.artifact_id for value in values}) != len(values):
        raise ValueError("expected must not repeat artifact IDs")
    if len({value.target.path for value in values}) != len(values):
        raise ValueError("expected must not repeat target paths")
    return values


def _matching_identity(record: ArtifactProvenance, expected: ArtifactProvenance) -> bool:
    return (record.artifact_id == expected.artifact_id and record.target_path == expected.target_path
            and record.contract_version == expected.contract_version
            and record.managed_boundary == expected.managed_boundary)


def _managed_block_codecs(
        value: Mapping[str, tuple[Callable[[bytes, tuple[str, ...]], bytes],
                                  Callable[[bytes, bytes, tuple[str, ...]], bytes]]] | None,
        results: tuple[ArtifactRenderResult, ...]) -> dict[str, tuple[
            Callable[[bytes, tuple[str, ...]], bytes],
            Callable[[bytes, bytes, tuple[str, ...]], bytes]]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError("managed_block_codecs must be a mapping keyed by artifact ID")
    expected_ids = {result.provenance.artifact_id for result in results
                    if result.provenance.managed_boundary[0] == "managed-blocks"}
    if set(value) != expected_ids:
        raise ValueError("managed block codecs must exactly match managed-block artifacts")
    codecs = {}
    for artifact_id, pair in value.items():
        if (not isinstance(pair, tuple) or len(pair) != 2 or
                not callable(pair[0]) or not callable(pair[1])):
            raise TypeError("managed block codec must be an extract/replace callable pair")
        codecs[artifact_id] = pair
    return codecs


def _managed_hash(
        target: Path, result: ArtifactRenderResult,
        codec: tuple[Callable[[bytes, tuple[str, ...]], bytes],
                     Callable[[bytes, bytes, tuple[str, ...]], bytes]] | None) -> str | None:
    if not target.exists() or target.is_symlink():
        return None
    managed = _extract_managed_bytes(target.read_bytes(), result, codec)
    return sha256_digest(managed) if managed is not None else None


def _extract_managed_bytes(
        file_bytes: bytes, result: ArtifactRenderResult,
        codec: tuple[Callable[[bytes, tuple[str, ...]], bytes],
                     Callable[[bytes, bytes, tuple[str, ...]], bytes]] | None) -> bytes | None:
    if result.provenance.managed_boundary[0] == "whole-file":
        return file_bytes
    if codec is None:
        return None
    try:
        managed = codec[0](file_bytes, result.provenance.managed_boundary[1])
    except (TypeError, ValueError):
        return None
    return managed if isinstance(managed, bytes) else None


def _replacement_bytes(
        target: Path, result: ArtifactRenderResult,
        codec: tuple[Callable[[bytes, tuple[str, ...]], bytes],
                     Callable[[bytes, bytes, tuple[str, ...]], bytes]] | None) -> bytes:
    if result.provenance.managed_boundary[0] == "whole-file":
        return result.managed_bytes
    if codec is None:
        raise ValueError("managed block codec is required")
    original = target.read_bytes() if target.exists() else b""
    existing = _extract_managed_bytes(original, result, codec)
    if target.exists() and existing is None:
        raise ValueError("managed boundary is invalid")
    try:
        replacement = codec[1](original, result.managed_bytes,
                               result.provenance.managed_boundary[1])
    except (TypeError, ValueError) as error:
        raise ValueError("managed boundary replacement is invalid") from error
    if not isinstance(replacement, bytes):
        raise ValueError("managed boundary replacement is invalid")
    extracted = _extract_managed_bytes(replacement, result, codec)
    if extracted != result.managed_bytes:
        raise ValueError("managed boundary replacement is invalid")
    if target.exists():
        try:
            restored = codec[1](replacement, existing, result.provenance.managed_boundary[1])
        except (TypeError, ValueError) as error:
            raise ValueError("managed boundary replacement is invalid") from error
        if restored != original:
            raise ValueError("managed boundary replacement changed unmanaged bytes")
    return replacement


def _root(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("root must be Path")
    if not root.is_absolute():
        raise ValueError("root must be explicit and absolute")
    return root


def _safe_target(target: Path, root: Path) -> bool:
    return is_within_lexical(target, root) and (not target.exists() or not target.is_symlink())


def _contained_target(root: Path, relative: str) -> Path:
    target = root / validate_target_path(relative)
    if not _safe_target(target, root) or not is_within(target, root):
        raise ValueError("target escapes explicit root")
    return target


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _provenance_value(record: ArtifactProvenance) -> dict[str, object]:
    value = {"adapter_id": record.adapter_id, "adapter_version": record.adapter_version,
             "artifact_id": record.artifact_id,
             "canonical_sources": [{"hash": source.content_hash, "path": source.path,
                                    "source_id": source.source_id} for source in record.canonical_sources],
             "capability_requirements": [{"accepted_levels": [level.value for level in requirement.accepted_levels],
                                           "id": requirement.capability_id.value}
                                          for requirement in record.capability_requirements],
             "contract_version": record.contract_version,
             "managed_boundary": {"block_ids": list(record.managed_boundary[1]),
                                  "mode": record.managed_boundary[0]},
             "override_layers": [dict(layer) for layer in record.override_layers],
             "provider_id": record.provider_id.value, "rendered_hash": record.rendered_hash,
             "source_hash": record.source_hash, "target_path": record.target_path}
    if record.contract_version == "1.1.0":
        value["semantic_metadata"] = json.loads(canonical_json_bytes(
            dict(record.semantic_metadata)).decode("utf-8"))
    return value


def _provenance_from_value(value: object) -> ArtifactProvenance:
    if not isinstance(value, dict):
        raise ValueError("corrupt lock")
    required = {"adapter_id", "adapter_version", "artifact_id", "canonical_sources",
                "capability_requirements", "contract_version", "managed_boundary",
                "override_layers", "provider_id", "rendered_hash", "source_hash", "target_path"}
    version = value.get("contract_version")
    if version == "1.1.0":
        required.add("semantic_metadata")
    if (version not in {"1.0.0", "1.1.0"} or set(value) != required
            or not isinstance(value["canonical_sources"], list)
            or not isinstance(value["capability_requirements"], list)
            or (version == "1.1.0" and not isinstance(value["semantic_metadata"], dict))):
        raise ValueError("corrupt lock")
    if (not all(isinstance(value[field], str) for field in ("adapter_id", "adapter_version", "artifact_id", "target_path", "source_hash", "rendered_hash")) or
            not _IDENTIFIER_RE.fullmatch(value["adapter_id"]) or not _IDENTIFIER_RE.fullmatch(value["artifact_id"]) or
            not _SEMVER_RE.fullmatch(value["adapter_version"]) or not _DIGEST_RE.fullmatch(value["source_hash"]) or
            not _DIGEST_RE.fullmatch(value["rendered_hash"])):
        raise ValueError("corrupt lock")
    try:
        validate_target_path(value["target_path"])
    except ValueError as error:
        raise ValueError("corrupt lock") from error
    boundary = value["managed_boundary"]
    if not isinstance(boundary, dict) or set(boundary) != {"mode", "block_ids"} or not isinstance(boundary["block_ids"], list):
        raise ValueError("corrupt lock")
    sources = tuple(ArtifactSource(item["source_id"], item["path"], item["hash"])
                    for item in value["canonical_sources"] if isinstance(item, dict) and set(item) == {"source_id", "path", "hash"})
    if len(sources) != len(value["canonical_sources"]):
        raise ValueError("corrupt lock")
    requirements = tuple(CapabilityRequirement(CapabilityId(item["id"]),
                                                 tuple(SupportLevel(level) for level in item["accepted_levels"]))
                         for item in value["capability_requirements"]
                         if isinstance(item, dict) and set(item) == {"id", "accepted_levels"} and isinstance(item["accepted_levels"], list))
    if len(requirements) != len(value["capability_requirements"]) or not isinstance(value["override_layers"], list):
        raise ValueError("corrupt lock")
    overrides = tuple(tuple(sorted(layer.items())) for layer in value["override_layers"] if isinstance(layer, dict))
    if len(overrides) != len(value["override_layers"]):
        raise ValueError("corrupt lock")
    metadata = tuple(sorted(value.get("semantic_metadata", {}).items()))
    return ArtifactProvenance(value["contract_version"], value["artifact_id"], sources,
                              value["adapter_id"], value["adapter_version"], ProviderId(value["provider_id"]),
                              value["target_path"], value["source_hash"], value["rendered_hash"],
                              (boundary["mode"], tuple(boundary["block_ids"])), overrides, requirements,
                              metadata)
