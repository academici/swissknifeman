"""Evidence-admitted locale corpus validation and guarded mutation helpers.

The ledger is deliberately data-first: package-specific paths stay in its rows while this
module only enforces the common ownership, review, preimage and checkpoint invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


LEDGER_SCHEMA = "urn:swissknifeman:locale-corpus:v1"
BATCH_SCHEMA = "urn:swissknifeman:locale-corpus-batch:v1"
SOURCE_LOCALE = "en"
OVERLAY_LOCALE = "ru"
GENERATED_SEGMENTS = (".agents", ".claude", ".codex-plugin", ".claude-plugin")
EXTERNAL_PREFIXES = ("http://", "https://", "vendor/")


class CorpusError(ValueError):
    """A stable refusal that can be rendered by thin package validators."""


@dataclass(frozen=True)
class CorpusReport:
    errors: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_prefixed(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def load_ledger(path: Path) -> Mapping[str, Any]:
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusError("LOCALE_CORPUS_LEDGER_INVALID") from error
    if not isinstance(ledger, dict):
        raise CorpusError("LOCALE_CORPUS_LEDGER_INVALID")
    return ledger


def check_ledger(ledger: Mapping[str, Any], *, root: Path) -> CorpusReport:
    errors: list[str] = []
    if ledger.get("$schema") != LEDGER_SCHEMA or ledger.get("contract_version") != "1.0.0":
        errors.append("LOCALE_CORPUS_LEDGER_INVALID")
    if ledger.get("source_locale") != SOURCE_LOCALE or ledger.get("overlay_locales") != [OVERLAY_LOCALE]:
        errors.append("AUTHORING_SOURCE_NOT_ENGLISH")
    classes = ledger.get("carrier_classes")
    if not isinstance(classes, list) or len(classes) != len(set(classes)) or not all(isinstance(value, str) for value in classes):
        errors.append("LOCALE_CORPUS_CARRIER_CLASSES_INVALID")
        classes = []
    rows = ledger.get("rows")
    if not isinstance(rows, list):
        errors.append("LOCALE_CORPUS_ROWS_INVALID")
        rows = []
    seen_ids: set[str] = set()
    source_paths: set[str] = set()
    for row in rows:
        errors.extend(_check_row(row, root=root, carrier_classes=set(classes), seen_ids=seen_ids, source_paths=source_paths))
    return CorpusReport(tuple(sorted(set(errors))), tuple(rows))


def _check_row(
    row: object,
    *,
    root: Path,
    carrier_classes: set[str],
    seen_ids: set[str],
    source_paths: set[str],
) -> list[str]:
    if not isinstance(row, dict):
        return ["LOCALE_CORPUS_ROW_INVALID"]
    errors: list[str] = []
    row_id = row.get("id")
    source_path = row.get("source_path")
    if not isinstance(row_id, str) or not row_id or row_id in seen_ids:
        errors.append("LOCALE_CORPUS_ROW_ID_INVALID")
    else:
        seen_ids.add(row_id)
    if row.get("carrier_id") not in carrier_classes:
        errors.append("LOCALE_CORPUS_CARRIER_UNKNOWN")
    if not isinstance(row.get("owner"), str) or not row["owner"]:
        errors.append("LOCALE_CORPUS_OWNER_MISSING")
    if row.get("source_locale") != SOURCE_LOCALE:
        errors.append("AUTHORING_SOURCE_NOT_ENGLISH")
    if not isinstance(source_path, str) or not source_path or source_path in source_paths:
        errors.append("LOCALE_CORPUS_SOURCE_AMBIGUOUS")
    else:
        source_paths.add(source_path)
        errors.extend(_classify_path(source_path))
    if not _digest(row.get("source_preimage_sha256")):
        errors.append("LOCALE_CORPUS_PREIMAGE_MISSING")
    if not isinstance(row.get("immutable_tokens"), list) or not all(isinstance(token, str) and token for token in row["immutable_tokens"]):
        errors.append("LOCALE_CORPUS_TOKENS_INVALID")
    if row.get("status") not in {"planned", "admitted", "applied", "rolled-back"}:
        errors.append("LOCALE_CORPUS_STATUS_INVALID")
    if not isinstance(row.get("generated_owner"), (str, type(None))):
        errors.append("OVERLAY_GENERATED_EDIT_FORBIDDEN")
    errors.extend(_check_reviews(row))
    if not _rollback_complete(row.get("rollback")):
        errors.append("OVERLAY_ROLLBACK_INCOMPLETE")
    return errors


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(char in "0123456789abcdef" for char in value[7:])


def _classify_path(path: str) -> list[str]:
    normalized = path.replace("\\", "/")
    if normalized.startswith(EXTERNAL_PREFIXES):
        return ["LOCALE_CORPUS_EXTERNAL_UPSTREAM"]
    if any(segment in normalized.split("/") for segment in GENERATED_SEGMENTS):
        return ["OVERLAY_GENERATED_EDIT_FORBIDDEN"]
    if "/overrides/" in f"/{normalized}":
        return ["OVERLAY_OVERRIDE_ADOPTION_FORBIDDEN"]
    return []


def _check_reviews(row: Mapping[str, Any]) -> list[str]:
    reviews = row.get("reviews")
    author, renderer = row.get("author"), row.get("renderer")
    if not isinstance(author, str) or not isinstance(renderer, str) or not isinstance(reviews, list):
        return ["AUTHORING_REVIEW_MISSING"]
    roles = {review.get("locale"): review for review in reviews if isinstance(review, dict)}
    if set(roles) != {"en", "ru"}:
        return ["AUTHORING_REVIEW_MISSING"]
    errors: list[str] = []
    reviewers: set[str] = set()
    for review in roles.values():
        reviewer = review.get("reviewer")
        if review.get("outcome") != "pass" or not isinstance(reviewer, str) or not reviewer:
            errors.append("AUTHORING_REVIEW_MISSING")
        elif reviewer in {author, renderer} or reviewer in reviewers:
            errors.append("AUTHORING_SELF_REVIEW")
        reviewers.add(reviewer)
    return errors


def _rollback_complete(rollback: object) -> bool:
    return isinstance(rollback, dict) and isinstance(rollback.get("id"), str) and isinstance(rollback.get("backup"), str)


def inventory(ledger: Mapping[str, Any], *, root: Path) -> list[dict[str, str]]:
    """Return deterministic extension-aware candidates without changing the worktree."""
    rows = ledger.get("rows") if isinstance(ledger.get("rows"), list) else []
    known = {row.get("source_path") for row in rows if isinstance(row, dict)}
    candidates: list[dict[str, str]] = []
    for raw_root in ledger.get("inventory_roots", []):
        directory = root / raw_root
        if not isinstance(raw_root, str) or not directory.is_dir():
            continue
        for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file() and candidate.suffix in {".md", ".py", ".sh", ".json"}):
            relative = path.relative_to(root).as_posix()
            candidates.append({"path": relative, "classification": "admitted" if relative in known else "unadmitted"})
    return candidates


def verify_batch(batch: Mapping[str, Any], ledger: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate a bounded D39/D40 checkpoint and its resume cursor."""
    errors: list[str] = []
    if batch.get("$schema") != BATCH_SCHEMA:
        errors.append("LOCALE_BATCH_SCHEMA_INVALID")
    row_ids = batch.get("row_ids")
    if not isinstance(row_ids, list) or not row_ids or len(row_ids) != len(set(row_ids)):
        errors.append("LOCALE_BATCH_OVERLAP")
        row_ids = []
    if len(row_ids) > 25:
        errors.append("LOCALE_BATCH_CAP_EXCEEDED")
    rows = {row.get("id"): row for row in ledger.get("rows", []) if isinstance(row, dict)}
    ordered = [row.get("id") for row in ledger.get("rows", []) if isinstance(row, dict)]
    positions = [ordered.index(row_id) for row_id in row_ids if row_id in ordered]
    if len(positions) != len(row_ids) or positions != sorted(positions):
        errors.append("LOCALE_BATCH_OUT_OF_ORDER")
    cwds = {rows[row_id].get("cwd") for row_id in row_ids if row_id in rows}
    if len(cwds) != 1:
        errors.append("LOCALE_BATCH_CROSS_CWD")
    reviewer = batch.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("verdict") != "pass" or reviewer.get("reviewer") == batch.get("author"):
        errors.append("AUTHORING_SELF_REVIEW")
    if batch.get("review_round", 0) > 2:
        errors.append("LOCALE_BATCH_REVIEW_CAP_EXCEEDED")
    if not isinstance(batch.get("commits"), list) or not isinstance(batch.get("commands"), list) or not _rollback_complete(batch.get("rollback")):
        errors.append("LOCALE_BATCH_CHECKPOINT_INCOMPLETE")
    accepted = [row_id for row_id in ordered if rows[row_id].get("status") in {"admitted", "applied"}]
    expected = next((row_id for row_id in ordered if row_id not in accepted), None)
    if batch.get("resume_cursor") != expected:
        errors.append("LOCALE_BATCH_RESUME_SKIP")
    return tuple(sorted(set(errors)))


def apply_row(ledger: Mapping[str, Any], row_id: str, *, root: Path, checkpoint_dir: Path) -> Path:
    row = _row(ledger, row_id)
    _admitted_row_or_raise(row)
    target = root / row["source_path"]
    before = target.read_bytes()
    if sha256_prefixed(before) != row["source_preimage_sha256"]:
        raise CorpusError("LOCALE_CORPUS_PREIMAGE_CHANGED")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    backup = checkpoint_dir / f"{row_id}.preimage"
    backup.write_bytes(before)
    if sha256_prefixed(target.read_bytes()) != row["source_preimage_sha256"]:
        raise CorpusError("LOCALE_CORPUS_PREIMAGE_CHANGED")
    target.write_text(row["apply"]["text"], encoding="utf-8")
    return backup


def rollback_row(ledger: Mapping[str, Any], row_id: str, *, root: Path, checkpoint_dir: Path) -> None:
    row = _row(ledger, row_id)
    target = root / row["source_path"]
    backup = checkpoint_dir / f"{row_id}.preimage"
    if not backup.is_file() or not _rollback_complete(row.get("rollback")):
        raise CorpusError("OVERLAY_ROLLBACK_INCOMPLETE")
    target.write_bytes(backup.read_bytes())


def review_markdown(ledger: Mapping[str, Any]) -> str:
    rows = ledger.get("rows") if isinstance(ledger.get("rows"), list) else []
    lines = ["# Locale corpus review", "", "| ID | Owner | Source | Status |", "|:--|:--|:--|:--|"]
    for row in sorted((row for row in rows if isinstance(row, dict)), key=lambda value: str(value.get("id", ""))):
        lines.append(f"| {row.get('id', '')} | {row.get('owner', '')} | {row.get('source_path', '')} | {row.get('status', '')} |")
    return "\n".join(lines) + "\n"


def _row(ledger: Mapping[str, Any], row_id: str) -> Mapping[str, Any]:
    for row in ledger.get("rows", []):
        if isinstance(row, dict) and row.get("id") == row_id:
            return row
    raise CorpusError("LOCALE_CORPUS_ROW_UNKNOWN")


def _admitted_row_or_raise(row: Mapping[str, Any]) -> None:
    if row.get("status") != "admitted":
        raise CorpusError("LOCALE_CORPUS_ROW_NOT_ADMITTED")
    codes = _classify_path(str(row.get("source_path", "")))
    if codes:
        raise CorpusError(codes[0])
    if not isinstance(row.get("apply"), dict) or not isinstance(row["apply"].get("text"), str):
        raise CorpusError("LOCALE_CORPUS_APPLY_INVALID")
