"""Owner-gated, digest-bound migration of a sealed Task execution journal.

Ordinary journal writes remain append-only.  This module exists only for a historical
row that cannot be made schema-valid by a compensating append.  A migration keeps the
complete source bytes, applies an allow-listed set of JSON additions/replacements, and
writes a digest-bound receipt before the repaired journal becomes authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from task import journal, plan_decisions, terminal_policy


SCHEMA_VERSION = "journal-migration/v1"
RECEIPT_SCHEMA_VERSION = "journal-migration-receipt/v1"
_ROOT_FIELDS = frozenset((
    "schema_version", "migration_id", "plan_id", "owner_decision", "actor", "reason",
    "source_sha256", "target_sha256", "preimage_path", "changes",
))
_CHANGE_FIELDS = frozenset(("line", "before_sha256", "after_sha256", "operations"))
_ADD_FIELDS = frozenset(("op", "path", "value"))
_REPLACE_FIELDS = frozenset(("op", "path", "before", "value"))
_MIGRATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VALIDATION_EVIDENCE_RE = re.compile(
    r"^/decision/terminal_evidence/validation/(0|[1-9][0-9]*)/evidence_ids$")
_TERMINAL_SCALAR_PATHS = frozenset((
    "/decision/terminal_evidence/spec_sha256",
    "/decision/terminal_evidence/repair_exhausted",
))
_LEGACY_DECISION_ADDITIONS = {
    "/decision/signal_class": "authority",
    "/decision/scope_class": "item",
    "/decision/recovered": False,
    "/decision/terminal": False,
}
_LEGACY_ENUM_REPLACEMENTS = {
    "/command": frozenset((("owner-decision", "plan-design"),)),
    "/result": frozenset((
        ("decision-accepted", "no-op"),
        ("in-progress", "no-op"),
    )),
}
_NEUTRAL_ROOT_VALUES = {
    "/session_id": None,
    "/run_id": None,
    "/friction": [],
    "/cost_usd": None,
    "/num_turns": None,
    "/duration_ms": None,
}


class JournalMigrationError(ValueError):
    """The manifest or live journal does not satisfy the migration contract."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_line(entry: dict) -> bytes:
    return (json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _require_exact_fields(value, expected, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(expected):
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise JournalMigrationError(
            f"{label}: ожидались поля {sorted(expected)}, получено {actual}")


def _require_sha(value, *, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise JournalMigrationError(f"{label}: ожидается lowercase SHA-256")


def _decision_is_accepted(plan_dir: Path, decision_id: str) -> bool:
    try:
        decisions = plan_decisions.load_decisions(plan_dir)
    except plan_decisions.DecisionError as exc:
        raise JournalMigrationError(f"owner_decision: каталог решений невалиден: {exc}") from exc
    return any(row.identifier == decision_id and row.status == "accepted" for row in decisions)


def _decode_pointer(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise JournalMigrationError(f"operation.path: невалидный JSON pointer {path!r}")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/"))


def _parent_and_key(document: dict, path: str):
    parts = _decode_pointer(path)
    if not parts:
        raise JournalMigrationError("operation.path: корень journal event изменять нельзя")
    current = document
    for part in parts[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise JournalMigrationError(f"operation.path: parent отсутствует для {path}")
    key = parts[-1]
    if isinstance(current, list):
        if not key.isdigit() or int(key) >= len(current):
            raise JournalMigrationError(f"operation.path: индекс вне списка для {path}")
        key = int(key)
    elif not isinstance(current, dict):
        raise JournalMigrationError(f"operation.path: parent не container для {path}")
    return current, key


def _allowed_operation(operation: dict) -> None:
    op = operation.get("op")
    expected = _ADD_FIELDS if op == "add" else _REPLACE_FIELDS if op == "replace" else None
    if expected is None:
        raise JournalMigrationError("operation.op: допустимы только add/replace")
    _require_exact_fields(operation, expected, label="operation")
    path = operation["path"]

    if path == "/friction":
        if op == "add" and operation["value"] == []:
            return
        before = operation.get("before")
        if (op != "replace" or operation["value"] != ["deviation"]
                or not isinstance(before, list) or not before
                or any(not isinstance(item, str) or not item for item in before)):
            raise JournalMigrationError(
                "/friction: допускается только replace непустого legacy string[] на ['deviation']")
        return
    if path in _NEUTRAL_ROOT_VALUES:
        if op != "add" or operation["value"] != _NEUTRAL_ROOT_VALUES[path]:
            raise JournalMigrationError(
                f"{path}: допускается только additive neutral backfill {_NEUTRAL_ROOT_VALUES[path]!r}")
        return
    if path in _LEGACY_DECISION_ADDITIONS:
        if op != "add" or operation["value"] != _LEGACY_DECISION_ADDITIONS[path]:
            raise JournalMigrationError(
                f"{path}: допускается только additive legacy decision backfill")
        return
    if path in _LEGACY_ENUM_REPLACEMENTS:
        pair = (operation.get("before"), operation["value"])
        if op != "replace" or pair not in _LEGACY_ENUM_REPLACEMENTS[path]:
            raise JournalMigrationError(
                f"{path}: legacy enum transition не входит в migration allow-list")
        return
    if path == "/decision":
        if op != "add" or not isinstance(operation["value"], dict):
            raise JournalMigrationError("/decision: допускается только additive object recovery")
        return
    if path in _TERMINAL_SCALAR_PATHS:
        if path.endswith("/repair_exhausted") and (op != "add" or operation["value"] is not None):
            raise JournalMigrationError(
                "/decision/terminal_evidence/repair_exhausted: допускается только add null")
        if path.endswith("/spec_sha256"):
            _require_sha(operation["value"], label=path)
        return
    if _VALIDATION_EVIDENCE_RE.fullmatch(path):
        value = operation["value"]
        if (op != "add" or not isinstance(value, list) or not value
                or len(value) != len(set(value))
                or any(not isinstance(item, str) or not item for item in value)):
            raise JournalMigrationError(f"{path}: допускается только add непустого unique string[]")
        return
    raise JournalMigrationError(f"operation.path: путь не входит в migration allow-list: {path}")


def _apply_operation(entry: dict, operation: dict) -> None:
    _allowed_operation(operation)
    parent, key = _parent_and_key(entry, operation["path"])
    exists = key < len(parent) if isinstance(parent, list) else key in parent
    if operation["op"] == "add":
        if exists:
            raise JournalMigrationError(f"add target уже существует: {operation['path']}")
    else:
        if not exists:
            raise JournalMigrationError(f"replace target отсутствует: {operation['path']}")
        current = parent[key]
        if current != operation["before"]:
            raise JournalMigrationError(
                f"replace precondition не совпадает для {operation['path']}")
        if (operation["path"] == "/result"
                and operation["before"] == "in-progress"
                and (entry.get("session_id") is not None or entry.get("run_id") is not None)):
            raise JournalMigrationError(
                "/result: сброс допустим только для orphan in-progress без session_id/run_id")
    parent[key] = operation["value"]


def _validate_manifest(plan_dir: Path, manifest_path: Path, manifest: dict) -> None:
    _require_exact_fields(manifest, _ROOT_FIELDS, label="manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise JournalMigrationError(f"schema_version: ожидается {SCHEMA_VERSION}")
    migration_id = manifest["migration_id"]
    if not isinstance(migration_id, str) or not _MIGRATION_ID_RE.fullmatch(migration_id):
        raise JournalMigrationError("migration_id: допускаются lowercase a-z, 0-9, dot, dash, underscore")
    if manifest["plan_id"] != plan_dir.name:
        raise JournalMigrationError("plan_id: не совпадает с canonical plan directory")
    for field in ("owner_decision", "actor", "reason"):
        if not isinstance(manifest[field], str) or not manifest[field]:
            raise JournalMigrationError(f"{field}: ожидается непустая строка")
    if not _decision_is_accepted(plan_dir, manifest["owner_decision"]):
        raise JournalMigrationError("owner_decision: нет accepted D# в decisions/")
    for field in ("source_sha256", "target_sha256"):
        _require_sha(manifest[field], label=field)

    expected_dir = plan_dir / "journal-migrations" / migration_id
    expected_manifest = expected_dir / "manifest.json"
    expected_preimage = expected_dir / "journal.preimage.jsonl"
    try:
        actual_manifest = manifest_path.resolve(strict=True)
    except OSError as exc:
        raise JournalMigrationError(f"manifest не читается: {exc}") from exc
    if actual_manifest != expected_manifest.resolve(strict=False):
        raise JournalMigrationError(f"manifest обязан находиться в {expected_manifest}")
    if manifest["preimage_path"] != expected_preimage.relative_to(plan_dir).as_posix():
        raise JournalMigrationError("preimage_path: не совпадает с canonical migration path")

    changes = manifest["changes"]
    if not isinstance(changes, list) or not changes:
        raise JournalMigrationError("changes: ожидается непустой список")
    lines = []
    for index, change in enumerate(changes):
        _require_exact_fields(change, _CHANGE_FIELDS, label=f"changes[{index}]")
        line = change["line"]
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise JournalMigrationError(f"changes[{index}].line: ожидается int >= 1")
        lines.append(line)
        _require_sha(change["before_sha256"], label=f"changes[{index}].before_sha256")
        _require_sha(change["after_sha256"], label=f"changes[{index}].after_sha256")
        operations = change["operations"]
        if not isinstance(operations, list) or not operations:
            raise JournalMigrationError(f"changes[{index}].operations: ожидается непустой список")
        for operation in operations:
            _allowed_operation(operation)
    if lines != sorted(lines) or len(lines) != len(set(lines)):
        raise JournalMigrationError("changes.line: строки должны быть unique и строго возрастающими")


def render_target(plan_dir, manifest_path) -> tuple[bytes, bytes, dict]:
    """Validate the manifest and return ``(source_bytes, target_bytes, manifest)``."""
    plan_dir = Path(plan_dir)
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalMigrationError(f"manifest не читается как UTF-8 JSON: {exc}") from exc
    _validate_manifest(plan_dir, manifest_path, manifest)

    journal_path = plan_dir / journal.FILENAME
    try:
        source = journal_path.read_bytes()
    except OSError as exc:
        raise JournalMigrationError(f"journal не читается: {exc}") from exc
    if _sha256(source) == manifest["target_sha256"]:
        preimage = plan_dir / manifest["preimage_path"]
        if not preimage.is_file() or _sha256(preimage.read_bytes()) != manifest["source_sha256"]:
            raise JournalMigrationError("already-applied journal не имеет валидного sealed preimage")
        return preimage.read_bytes(), source, manifest
    if _sha256(source) != manifest["source_sha256"]:
        raise JournalMigrationError("source_sha256: live journal не совпадает с manifest")
    if not source.endswith(b"\n") or b"\r\n" in source:
        raise JournalMigrationError("journal: миграция требует LF и terminal newline")

    lines = source.splitlines(keepends=True)
    for change in manifest["changes"]:
        index = change["line"] - 1
        if index >= len(lines):
            raise JournalMigrationError(f"line {change['line']}: отсутствует в journal")
        raw = lines[index][:-1]
        if _sha256(raw) != change["before_sha256"]:
            raise JournalMigrationError(f"line {change['line']}: before_sha256 не совпадает")
        try:
            entry = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JournalMigrationError(f"line {change['line']}: невалидный UTF-8 JSON") from exc
        if not isinstance(entry, dict):
            raise JournalMigrationError(f"line {change['line']}: event обязан быть object")
        for operation in change["operations"]:
            _apply_operation(entry, operation)
        if entry.get("plan_id") != plan_dir.name:
            raise JournalMigrationError(f"line {change['line']}: plan_id изменён/невалиден")
        try:
            journal.validate_entry(entry)
            terminal_policy.validate_entry(entry, plan_dir=None)
        except (journal.JournalValidationError, terminal_policy.TerminalPolicyError) as exc:
            raise JournalMigrationError(f"line {change['line']}: итоговая запись невалидна: {exc}") from exc
        after = _canonical_line(entry)
        if _sha256(after[:-1]) != change["after_sha256"]:
            raise JournalMigrationError(f"line {change['line']}: after_sha256 не совпадает")
        lines[index] = after

    target = b"".join(lines)
    if _sha256(target) != manifest["target_sha256"]:
        raise JournalMigrationError("target_sha256: rendered journal не совпадает с manifest")
    return source, target, manifest


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    except BaseException:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass
        raise


def apply(plan_dir, manifest_path) -> dict:
    """Apply one exact migration, preserving source bytes and returning its receipt."""
    plan_dir = Path(plan_dir)
    manifest_path = Path(manifest_path)
    source, target, manifest = render_target(plan_dir, manifest_path)
    journal_path = plan_dir / journal.FILENAME
    preimage_path = plan_dir / manifest["preimage_path"]
    receipt_path = preimage_path.parent / "receipt.json"

    if preimage_path.exists():
        if preimage_path.read_bytes() != source:
            raise JournalMigrationError("preimage уже существует с другими bytes")
    else:
        _atomic_write(preimage_path, source)

    if journal_path.read_bytes() != target:
        if _sha256(journal_path.read_bytes()) != manifest["source_sha256"]:
            raise JournalMigrationError("journal изменился после render; миграция отменена")
        _atomic_write(journal_path, target)

    manifest_sha256 = _sha256(manifest_path.read_bytes())
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "migration_id": manifest["migration_id"],
        "plan_id": manifest["plan_id"],
        "owner_decision": manifest["owner_decision"],
        "manifest_sha256": manifest_sha256,
        "source_sha256": manifest["source_sha256"],
        "target_sha256": manifest["target_sha256"],
        "source_bytes": len(source),
        "target_bytes": len(target),
        "changed_lines": [change["line"] for change in manifest["changes"]],
        "preimage_path": manifest["preimage_path"],
    }
    receipt_bytes = (json.dumps(
        receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if receipt_path.exists() and receipt_path.read_bytes() != receipt_bytes:
        raise JournalMigrationError("receipt уже существует с другим содержимым")
    if not receipt_path.exists():
        _atomic_write(receipt_path, receipt_bytes)
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="task.journal_migration",
        description="Owner-gated digest-bound migration sealed journal rows",
    )
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--check", action="store_true", help="validate/render without writes")
    args = parser.parse_args(argv)
    try:
        if args.check:
            source, target, manifest = render_target(args.plan_dir, args.manifest)
            result = {
                "migration_id": manifest["migration_id"],
                "source_sha256": _sha256(source),
                "target_sha256": _sha256(target),
                "changed_lines": [change["line"] for change in manifest["changes"]],
                "status": "valid",
            }
        else:
            result = apply(args.plan_dir, args.manifest)
    except JournalMigrationError as exc:
        print(f"ERROR: journal migration отклонена: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
