"""Byte-bound terminal and handoff delivery receipts for Task plans."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from task import journal, plan_layout, plan_lint


class DeliveryError(ValueError):
    """A typed refusal to declare a Task delivery complete."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


TERMINAL_ITEM_STATUSES = frozenset((
    "🟢 Done", "🟠 Done with deviations", "🔴 Blocked", "⛔ Skipped by decision",
))
TERMINAL_PHASE_STATUSES = frozenset((
    "🟢 Done", "🟠 Done with deviations", "⛔ Skipped by decision",
))
_ITEM_RE = re.compile(r"^(P[0-9]+)\.[0-9]+$")
_PHASE_RE = re.compile(r"^P[0-9]+$")
_STATUS_BY_RESULT = {
    "closed-green": "🟢 Done",
    "closed-deviations": "🟠 Done with deviations",
    "blocked": "🔴 Blocked",
    "escalated": "🔴 Blocked",
}


def file_digest(path) -> str:
    try:
        value = Path(path).read_bytes()
    except OSError as exc:
        raise DeliveryError("DELIVERY_CARRIER_MISSING", f"носитель не читается: {path}") from exc
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _handoff(plan_dir: Path) -> dict:
    path = plan_dir / "handoff.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", f"handoff.md не читается: {exc}") from exc
    start = next((index for index, line in enumerate(lines)
                  if line.strip().startswith("**Next:**")), None)
    if start is None:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "в handoff.md нет **Next:**")
    next_exact = lines[start].split("**Next:**", 1)[1].strip()
    if not next_exact:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "Next пуст")
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].strip().startswith("**Done:**")), len(lines))
    recommendation = "\n".join(lines[start:end]).strip()
    if not recommendation:
        raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", "recommendation пуста")

    route = {"batch": None, "model": None, "thinking": None, "context": None, "command": None}
    rows = []
    for line in lines[start:end]:
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if cells and not all(set(cell) <= {":", "-"} for cell in cells):
            rows.append(cells)
    keyed = {row[0]: row[1] for row in rows if len(row) == 2}
    route.update({
        "batch": keyed.get("Batch"),
        "model": keyed.get("Model"),
        "thinking": keyed.get("Thinking"),
        "context": keyed.get("Context"),
        "command": keyed.get("Команда"),
    })
    for index, row in enumerate(rows[:-1]):
        if row == ["Model", "Thinking", "Context", "Суть", "Команда"]:
            values = rows[index + 1]
            if len(values) == 5:
                route.update(dict(zip(("model", "thinking", "context", "rationale", "command"), values)))
            break

    def field(name):
        prefix = f"**{name}:**"
        return next((line.split(prefix, 1)[1].strip() for line in lines
                     if line.strip().startswith(prefix)), None)

    return {
        "next_exact": next_exact,
        "recommendation": recommendation,
        "route": route,
        "rationale": {"remaining": field("Remaining"), "open_risks": field("Open risks")},
        "digest": file_digest(path),
    }


def _item_status(plan_dir: Path, item_id: str) -> tuple[str, Path]:
    phase_id = item_id.split(".", 1)[0]
    layout = plan_layout.layout_version(plan_dir)
    phase_path = plan_layout.phase_path(plan_dir, phase_id)
    diagnostics = plan_lint.Diagnostics()
    phase = plan_lint.parse_phase_md(phase_path, phase_id, diagnostics, layout=layout)
    occurrences = phase["items"].get(item_id) if phase else None
    if not occurrences:
        raise DeliveryError("DELIVERY_STATE_INVALID", f"item {item_id} не найден")
    if diagnostics.errors:
        raise DeliveryError("DELIVERY_STATE_INVALID", diagnostics.errors[0])
    status = occurrences[0]["fields"].get("Status", (None, None))[0]
    state_path = (plan_layout.carrier_path(plan_dir, "item-state", item_id=item_id)
                  if layout == "v2" else phase_path)
    return status, state_path


def _terminal_journal(plan_dir: Path, subject: str) -> dict:
    path = plan_layout.carrier_path(plan_dir, "journal")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DeliveryError("TERMINAL_JOURNAL_MISSING", f"journal не читается: {exc}") from exc
    candidates = []
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
            journal.validate_entry(event)
        except (json.JSONDecodeError, journal.JournalValidationError):
            continue
        subject_matches = event.get("item_id") == subject
        if subject == "archive":
            subject_matches = event.get("item_id") == "archive" and event.get("command") == "plan-close"
        if subject_matches and event.get("result") in journal.TERMINAL_CLOSE_RESULTS:
            candidates.append((line_number, raw, event))
    if not candidates:
        raise DeliveryError("TERMINAL_JOURNAL_MISSING", f"для {subject} нет terminal journal event")
    line_number, raw, event = candidates[-1]
    if not event.get("run_id"):
        raise DeliveryError("TERMINAL_RUN_ID_MISSING", f"journal.jsonl:{line_number} не несёт run_id")
    return {
        "line": line_number,
        "sha256": "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "run_id": event["run_id"],
        "result": event["result"],
    }


def _git_commit(plan_dir: Path) -> str | None:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=plan_dir, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else None


def _closure_digest(plan_dir: Path, phase_id: str) -> str | None:
    candidates = (plan_dir / "closure" / f"{phase_id}.json",
                  plan_dir / "phases" / phase_id / f"{phase_id}.closed.md")
    return next((file_digest(path) for path in candidates if path.is_file()), None)


def _base_receipt(plan_dir: Path, subject: str, *, schema_version: str, status: str,
                  state_digest: str | None, closure_digest: str | None,
                  terminal: dict | None) -> dict:
    handoff = _handoff(plan_dir)
    return {
        "schema_version": schema_version,
        "plan_id": plan_dir.name,
        "subject": subject,
        "status": status,
        "next_exact": handoff["next_exact"],
        "recommendation": handoff["recommendation"],
        "route": handoff["route"],
        "rationale": handoff["rationale"],
        "commit_sha": _git_commit(plan_dir),
        "journal": terminal,
        "digests": {
            "plan": file_digest(plan_dir / "plan.md"),
            "handoff": handoff["digest"],
            "state": state_digest,
            "closure": closure_digest,
        },
    }


def build_handoff_receipt(plan_dir, subject: str) -> dict:
    plan_dir = Path(plan_dir)
    return _base_receipt(
        plan_dir, subject,
        schema_version="handoff-recommendation-receipt/v1",
        status="handoff-persisted", state_digest=None, closure_digest=None, terminal=None,
    )


def build_terminal_receipt(plan_dir, subject: str) -> dict:
    plan_dir = Path(plan_dir)
    if _ITEM_RE.fullmatch(subject):
        status, state_path = _item_status(plan_dir, subject)
        if status not in TERMINAL_ITEM_STATUSES:
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", f"{subject}: {status}")
        terminal = _terminal_journal(plan_dir, subject)
        if _STATUS_BY_RESULT.get(terminal["result"]) != status:
            raise DeliveryError("STALE_TERMINAL_RECEIPT", "journal result не совпадает с item state")
        phase_id = subject.split(".", 1)[0]
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status=status,
            state_digest=file_digest(state_path), closure_digest=_closure_digest(plan_dir, phase_id),
            terminal=terminal,
        )
    if _PHASE_RE.fullmatch(subject):
        status = plan_layout.phase_statuses(plan_dir).get(subject)
        if status not in TERMINAL_PHASE_STATUSES:
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", f"{subject}: {status}")
        terminal = _terminal_journal(plan_dir, subject)
        if _STATUS_BY_RESULT.get(terminal["result"]) != status:
            raise DeliveryError("STALE_TERMINAL_RECEIPT", "journal result не совпадает с phase state")
        phase_path = plan_layout.phase_path(plan_dir, subject)
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status=status,
            state_digest=file_digest(phase_path), closure_digest=_closure_digest(plan_dir, subject),
            terminal=terminal,
        )
    if subject == "archive":
        if plan_dir.parent.name != "archive":
            raise DeliveryError("FINAL_BEFORE_TERMINAL_FORBIDDEN", "план ещё не в archive")
        terminal = _terminal_journal(plan_dir, subject)
        return _base_receipt(
            plan_dir, subject, schema_version="terminal-delivery-receipt/v1", status="archived",
            state_digest=None, closure_digest=None, terminal=terminal,
        )
    raise DeliveryError("DELIVERY_SUBJECT_INVALID", "subject должен быть Pn.m, Pn или archive")


def verify_receipt(plan_dir, receipt: dict) -> bool:
    if not isinstance(receipt, dict):
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "receipt не object")
    schema = receipt.get("schema_version")
    subject = receipt.get("subject")
    if schema == "terminal-delivery-receipt/v1":
        current = build_terminal_receipt(plan_dir, subject)
    elif schema == "handoff-recommendation-receipt/v1":
        current = build_handoff_receipt(plan_dir, subject)
    else:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "неизвестная схема receipt")
    for field in ("next_exact", "recommendation"):
        if receipt.get(field) != current[field]:
            raise DeliveryError("HANDOFF_RECOMMENDATION_MISSING", f"{field} не совпадает с handoff.md")
    if receipt != current:
        raise DeliveryError("STALE_TERMINAL_RECEIPT", "receipt digests/state устарели")
    return True


def write_receipt(path, receipt: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path
