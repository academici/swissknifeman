"""Deterministic fix brief for a correction round (execution §4.13, §5.9; ``urn:skm:execution:fix-brief:v1``).

Only triaged findings enter (``confirmed``/``deferred`` with a ``fix_now`` triage decision), ordered by
severity, confidence and key; blockers first, then findings deferred by an earlier brief, then the rest.
Text fields are clipped head + tail with a marker that points into the full report; a red required check
contributes only the last ≤ 40 lines within ``max_inline_evidence_bytes`` and a reference to its full log,
so a 2 MB log never reaches the executor. A blocker is never left out, even beyond the limits
(``FIX_BRIEF_OVER``); other findings that do not fit are deferred. Any cut sets ``truncated``. The brief is
immutable and its digest covers the canonical document without the digest itself.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.finding import SEVERITY_RANK, FindingState, Severity

if TYPE_CHECKING:
    from skm.kernel.ids import AttemptId, FileVersionId, TaskId
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.ids import CheckExecutionId, FixBriefId, ReviewId

__all__ = [
    "DEFAULT_LIMITS",
    "FIELD_LIMITS",
    "SCHEMA_URN",
    "CheckLog",
    "FixBrief",
    "FixBriefCheck",
    "FixBriefItem",
    "TriageNote",
    "build_fix_brief",
    "fix_brief_to_json",
]

SCHEMA_URN: Final = "urn:skm:execution:fix-brief:v1"
DEFAULT_LIMITS: Final[Mapping[str, int]] = {
    "max_findings": 12,
    "max_finding_chars": 3000,
    "max_inline_evidence_bytes": 4000,
    "max_total_bytes": 24000,
}
FIELD_LIMITS: Final[Mapping[str, int]] = {"problem": 1200, "fix": 800, "observed": 600, "reproduction": 400}
_TAIL_LINES: Final = 40
_CONFIDENCE: Final = {"high": 0, "medium": 1, "low": 2}
_RED: Final = frozenset({CheckState.FAILED, CheckState.ERROR})


@dataclass(frozen=True, slots=True)
class FixBrief:
    id: FixBriefId
    task_id: TaskId
    attempt_id: AttemptId
    source_review_id: ReviewId | None
    source_check_round: int | None
    items: tuple[FixBriefItem, ...]
    truncated: bool
    full_report_file_version_id: FileVersionId
    limits: JsonObject
    digest: str
    checks: tuple[FixBriefCheck, ...] = ()
    deferred_finding_keys: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()  # not part of the document

    def __post_init__(self) -> None:
        if (self.source_review_id is None) == (self.source_check_round is None):
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "a fix brief has exactly one source: a review or a check round",
                details={"fix_brief_id": str(self.id)},
            )


@dataclass(frozen=True, slots=True)
class TriageNote:
    """The triage decision of one finding (role result ``triager``)."""

    decision: Literal["fix_now", "defer"]
    fix: str = ""
    observed: str = ""
    argv: tuple[str, ...] = ()
    exit_code: int | None = None


@dataclass(frozen=True, slots=True)
class CheckLog:
    """The full log of a red check: its text as read by the caller and the evidence file version."""

    text: str
    file_version_id: FileVersionId | None


@dataclass(frozen=True, slots=True)
class FixBriefCheck:
    check_key: str
    exit_code: int | None
    tail: str
    tail_bytes: int
    full_log_file_version_id: FileVersionId | None


def build_fix_brief(  # noqa: PLR0913 -- the identity of the immutable brief comes with its inputs
    findings: Sequence[Finding],
    checks: Sequence[CheckExecution],
    limits: JsonObject,
    *,
    brief_id: FixBriefId,
    task_id: TaskId,
    attempt_id: AttemptId,
    source_review_id: ReviewId | None,
    source_check_round: int | None,
    full_report_file_version_id: FileVersionId,
    triage: Mapping[str, TriageNote],
    logs: Mapping[CheckExecutionId, CheckLog] | None = None,
) -> FixBrief:
    """The brief of the logical ``findings`` (``triage`` by ``finding_key``) and the round's ``checks``."""
    caps = {name: _limit(limits, name, default) for name, default in DEFAULT_LIMITS.items()}
    ref = f"file_version:{full_report_file_version_id}"
    clipped = False
    red = sorted(
        (check for check in checks if check.required and check.state in _RED),
        key=lambda check: (check.check_key, str(check.id)),
    )
    brief_checks, clipped = _check_entries(red, logs or {}, caps["max_inline_evidence_bytes"])
    candidates = sorted(
        (f for f in findings if _triaged(f, triage)),
        key=lambda f: (
            0 if f.severity is Severity.BLOCKER else 1 if f.state is FindingState.DEFERRED else 2,
            *_order(f),
        ),
    )
    head: JsonObject = {
        "schema": SCHEMA_URN,
        "id": str(brief_id),
        "task_id": str(task_id),
        "attempt_id": str(attempt_id),
        "source_review_id": None if source_review_id is None else str(source_review_id),
        "source_check_round": source_check_round,
        "full_report_file_version_id": str(full_report_file_version_id),
    }

    def size(
        items: Sequence[FixBriefItem],
        deferred_keys: Sequence[str],
        entries: Sequence[FixBriefCheck] | None = None,
    ) -> int:
        """Bytes of the whole document, with ``truncated`` and a digest of its final length."""
        body = _document_body(caps, items, brief_checks if entries is None else entries, deferred_keys)
        # false is one byte longer than true: an uncut brief must fit too.
        return _size({**head, **body, "truncated": False, "digest": "sha256:" + "0" * 64})

    selected: list[FixBriefItem] = []
    deferred: list[str] = []
    diagnostics: list[str] = []
    optional: list[Finding] = []
    for finding in candidates:
        if finding.severity is Severity.BLOCKER:
            item, cut = _item(finding, triage[finding.finding_key], ref, caps["max_finding_chars"])
            selected.append(item)
            clipped = clipped or cut
        else:
            optional.append(finding)
    # Reserve blockers, every check identity/log reference and the deferred key list before tails.
    # Only blockers may exceed the document cap; check tails never consume that exception.
    optional_keys = [finding.finding_key for finding in optional]
    if size(selected, optional_keys) > caps["max_total_bytes"]:
        brief_checks, cut = _fit_checks(
            red,
            logs or {},
            caps["max_inline_evidence_bytes"],
            lambda entries: size(selected, optional_keys, entries) <= caps["max_total_bytes"],
        )
        clipped = clipped or cut
        if size([], optional_keys) > caps["max_total_bytes"]:
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                "fix brief metadata cannot fit max_total_bytes even without check tails",
                details={
                    "max_total_bytes": caps["max_total_bytes"],
                    "required_bytes": size([], optional_keys),
                },
            )
    for index, finding in enumerate(optional):
        item, cut = _item(finding, triage[finding.finding_key], ref, caps["max_finding_chars"])
        # upper bound: every later candidate may still be deferred and listed by key
        later = optional_keys[index + 1 :]
        trial = [*selected, item]
        within = (
            len(trial) <= caps["max_findings"] and size(trial, [*deferred, *later]) <= caps["max_total_bytes"]
        )
        if within:
            selected.append(item)
            clipped = clipped or cut
        else:
            deferred.append(finding.finding_key)
    blockers = sum(1 for item in selected if item.severity is Severity.BLOCKER)
    if blockers > caps["max_findings"] or size(selected, deferred) > caps["max_total_bytes"]:
        diagnostics.append("FIX_BRIEF_OVER")
    rank = {finding.finding_key: _order(finding) for finding in candidates}
    items = tuple(sorted(selected, key=lambda item: rank[item.finding_key]))
    truncated = clipped or bool(deferred)
    document: JsonObject = {
        **head,
        **_document_body(caps, list(items), brief_checks, deferred),
        "truncated": truncated,
    }
    return FixBrief(
        id=brief_id,
        task_id=task_id,
        attempt_id=attempt_id,
        source_review_id=source_review_id,
        source_check_round=source_check_round,
        items=items,
        truncated=truncated,
        full_report_file_version_id=full_report_file_version_id,
        limits=cast("JsonObject", dict(caps)),
        digest="sha256:" + hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest(),
        checks=tuple(brief_checks),
        deferred_finding_keys=tuple(deferred),
        diagnostics=tuple(diagnostics),
    )


@dataclass(frozen=True, slots=True)
class FixBriefItem:
    finding_key: str
    local_id: str
    severity: Severity
    category: str
    location: JsonObject
    problem: str
    fix: str
    observed: str
    reproduction: str


def fix_brief_to_json(brief: FixBrief) -> JsonObject:
    """The ``urn:skm:execution:fix-brief:v1`` document of ``brief`` (diagnostics are not part of it)."""
    caps = {name: _limit(brief.limits, name, default) for name, default in DEFAULT_LIMITS.items()}
    return {
        "schema": SCHEMA_URN,
        "id": str(brief.id),
        "task_id": str(brief.task_id),
        "attempt_id": str(brief.attempt_id),
        "source_review_id": None if brief.source_review_id is None else str(brief.source_review_id),
        "source_check_round": brief.source_check_round,
        **_document_body(caps, list(brief.items), list(brief.checks), list(brief.deferred_finding_keys)),
        "truncated": brief.truncated,
        "full_report_file_version_id": str(brief.full_report_file_version_id),
        "digest": brief.digest,
    }


# --- items ----------------------------------------------------------------------------------------------


def _triaged(finding: Finding, triage: Mapping[str, TriageNote]) -> bool:
    note = triage.get(finding.finding_key)
    return (
        note is not None
        and note.decision == "fix_now"
        and finding.state in {FindingState.CONFIRMED, FindingState.DEFERRED}
    )


def _order(finding: Finding) -> tuple[int, int, str]:
    return (-SEVERITY_RANK[finding.severity], _CONFIDENCE[finding.confidence], finding.finding_key)


def _item(finding: Finding, note: TriageNote, ref: str, max_chars: int) -> tuple[FixBriefItem, bool]:
    scenario = finding.failure_scenario.strip()
    message = finding.message.strip()
    problem = message if not scenario or scenario == message else f"{message} {scenario}"
    texts = {
        "problem": problem,
        "fix": note.fix,
        "observed": note.observed,
        "reproduction": _reproduction(finding, note),
    }
    full = f"{ref}#{finding.finding_key}"
    budgets = _field_budgets(texts, max_chars, full)
    cut = False
    fields: dict[str, str] = {}
    for name, text in texts.items():
        fields[name], was_cut = _clip(text, budgets[name], full)
        cut = cut or was_cut
    location = finding.location
    item = FixBriefItem(
        finding_key=finding.finding_key,
        local_id=finding.local_id,
        severity=finding.severity,
        category=finding.category,
        location={
            "mount": str(location.get("mount", "")),
            "path": str(location.get("path", "")),
            "line_start": _line(location.get("line_start")),
            "line_end": _line(location.get("line_end", location.get("line_start"))),
        },
        **fields,
    )
    return item, cut


def _reproduction(finding: Finding, note: TriageNote) -> str:
    if note.argv:
        exit_text = "" if note.exit_code is None else f"  (exit {note.exit_code})"
        return shlex.join(note.argv) + exit_text
    repro = finding.reproduction or {}
    argv = repro.get("argv")
    if not isinstance(argv, list) or not argv:
        return ""
    expected = repro.get("expected_exit")
    exit_text = f"  (expected exit {expected})" if isinstance(expected, int) else ""
    return shlex.join(str(part) for part in cast("list[JsonValue]", argv)) + exit_text


def _marker(cut: int, full: str) -> str:
    return f" … [clipped {cut} chars; full: {full}] "


def _field_budgets(texts: Mapping[str, str], max_chars: int, full: str) -> dict[str, int]:
    """Keep the usual proportions, borrowing space for intact markers at small item limits."""
    scale = min(1.0, max_chars / sum(FIELD_LIMITS.values()))
    minimum = {name: min(len(text), len(_marker(len(text), full)) + 2) for name, text in texts.items()}
    budgets = {name: max(int(cap * scale), minimum[name]) for name, cap in FIELD_LIMITS.items()}
    excess = max(0, sum(budgets.values()) - max_chars)
    for name in budgets:
        take = min(excess, budgets[name] - minimum[name])
        budgets[name] -= take
        excess -= take
    # Below supported config limits, omit whole fields rather than emit partial report references.
    for name in reversed(budgets):
        if excess > 0:
            excess -= budgets[name]
            budgets[name] = 0
    return budgets


def _clip(text: str, limit: int, full: str) -> tuple[str, bool]:
    """Head + marker + tail within ``limit`` characters; the marker names how much was cut and where."""
    if len(text) <= limit:
        return text, False
    room = limit
    for _ in range(4):  # the marker length depends on the number it reports; settles in two rounds
        marker = _marker(len(text) - room, full)
        room = max(0, limit - len(marker))
    marker = _marker(len(text) - room, full)
    if len(marker) > limit:
        return "", True
    room = max(0, limit - len(marker))
    head = room * 2 // 3
    tail = room - head
    return text[:head] + marker + (text[len(text) - tail :] if tail else ""), True


def _line(value: JsonValue | None) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


# --- checks ---------------------------------------------------------------------------------------------


def _check_entries(
    checks: Sequence[CheckExecution], logs: Mapping[CheckExecutionId, CheckLog], max_bytes: int
) -> tuple[list[FixBriefCheck], bool]:
    entries: list[FixBriefCheck] = []
    clipped = False
    for check in checks:
        entry, cut = _check_entry(check, logs.get(check.id), max_bytes)
        entries.append(entry)
        clipped = clipped or cut
    return entries, clipped


def _fit_checks(
    checks: Sequence[CheckExecution],
    logs: Mapping[CheckExecutionId, CheckLog],
    max_bytes: int,
    fits: Callable[[Sequence[FixBriefCheck]], bool],
) -> tuple[list[FixBriefCheck], bool]:
    """Fit a common tail budget, measured as serialized JSON (including escaping)."""
    best = _check_entries(checks, logs, 0)
    low, high = 1, max_bytes
    while low <= high:
        mid = (low + high) // 2
        candidate = _check_entries(checks, logs, mid)
        if fits(candidate[0]):
            best, low = candidate, mid + 1
        else:
            high = mid - 1
    return best


def _check_entry(check: CheckExecution, log: CheckLog | None, max_bytes: int) -> tuple[FixBriefCheck, bool]:
    text = check.summary if log is None else log.text
    file_version_id = None if log is None else log.file_version_id
    tail, cut = _tail(text, max_bytes, file_version_id)
    return (
        FixBriefCheck(
            check_key=check.check_key,
            exit_code=check.exit_code,
            tail=tail,
            tail_bytes=len(tail.encode("utf-8")),
            full_log_file_version_id=file_version_id,
        ),
        cut,
    )


def _tail(text: str, max_bytes: int, file_version_id: FileVersionId | None) -> tuple[str, bool]:
    """The last ≤ 40 lines within ``max_bytes`` UTF-8 bytes, marker included."""
    total = len(text.encode("utf-8"))
    lines = text.splitlines()
    kept = "\n".join(lines[-_TAIL_LINES:])
    if len(lines) <= _TAIL_LINES and total <= max_bytes:
        return text, False
    where = "" if file_version_id is None else f"; full: file_version:{file_version_id}"
    body = _last_bytes(kept, max_bytes)
    for _ in range(4):  # the marker reports the clipped bytes, so its own size settles in two rounds
        marker = f"… [clipped {total - len(body.encode('utf-8')):,} bytes{where}]\n".replace(",", " ")
        body = _last_bytes(kept, max(0, max_bytes - len(marker.encode("utf-8"))))
    marker = f"… [clipped {total - len(body.encode('utf-8')):,} bytes{where}]\n".replace(",", " ")
    if len(marker.encode("utf-8")) > max_bytes:
        return "", True  # log/whole-report references remain on the check and document
    return marker + body, True


def _last_bytes(text: str, limit: int) -> str:
    """The longest suffix of ``text`` within ``limit`` UTF-8 bytes, never splitting a character."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[len(data) - limit :].decode("utf-8", errors="ignore") if limit > 0 else ""


# --- document -------------------------------------------------------------------------------------------


def _document_body(
    caps: Mapping[str, int],
    items: Sequence[FixBriefItem],
    checks: Sequence[FixBriefCheck],
    deferred: Sequence[str],
) -> JsonObject:
    return {
        "limits": cast("JsonObject", dict(caps)),
        "items": [
            {
                "finding_key": item.finding_key,
                "local_id": item.local_id,
                "severity": item.severity.value,
                "category": item.category,
                "location": item.location,
                "problem": item.problem,
                "fix": item.fix,
                "observed": item.observed,
                "reproduction": item.reproduction,
            }
            for item in items
        ],
        "checks": [
            {
                "check_key": check.check_key,
                "exit_code": check.exit_code,
                "tail": check.tail,
                "tail_bytes": check.tail_bytes,
                "full_log_file_version_id": None
                if check.full_log_file_version_id is None
                else str(check.full_log_file_version_id),
            }
            for check in checks
        ],
        "deferred_finding_keys": list(deferred),
    }


def _size(body: JsonObject) -> int:
    return len(_canonical(body).encode("utf-8"))


def _canonical(document: JsonObject) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _limit(limits: Mapping[str, JsonValue], name: str, default: int) -> int:
    value = limits.get(name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default
