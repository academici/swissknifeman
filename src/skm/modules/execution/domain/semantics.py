"""What a role result means, apart from its form: the outcome of a result and the drift between two readings
(execution §5.7; port of ``conductor/domain/semantics.py``).

Repair may change the form of a result, never its meaning, and the meaning may only move toward caution.
``outcome_key`` reduces a document to the fields that carry the meaning; ``drift`` names what got better,
shrank or was lost between two documents. Both are pure and read *raw* documents too: a missing or odd
field is skipped, never an error, and an object where a list is expected is read as a list of one (the
same singleton rule as ``heal``, so a blocker written as ``open_issues: {...}`` is counted before and after).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, cast

from skm.modules.execution.domain.finding import place

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "DEFAULT_DEVIATION_CLASS",
    "ISSUE_COUNTS",
    "NO_IMPACT",
    "SEVERITY_RANK",
    "STATUS_RANK",
    "VERDICT_RANK",
    "drift",
    "outcome_key",
]

# More is more cautious: a repair may move a document up these orders, never down.
STATUS_RANK: Final = {"done": 0, "done_with_deviations": 1, "done_pending_checks": 2, "blocked": 3}
VERDICT_RANK: Final = {"green": 0, "attention": 1, "red": 2}
SEVERITY_RANK: Final = {"nit": 0, "minor": 1, "major": 2, "blocker": 3}
ISSUE_COUNTS: Final = ("escalation", "blocker", "pending", "deviation")
# What ``heal`` writes into a deviation that states nothing means the same as saying nothing: not identity.
NO_IMPACT: Final = "not stated by the executor"
DEFAULT_DEVIATION_CLASS: Final = "other"

_CHECK_ID: Final = re.compile(r"V[0-9]+")
_SEPARATORS: Final = re.compile(r"[\s-]+")
_BLANKS: Final = re.compile(r"\s+")
_PASS_FAIL: Final = {"pass": 0, "fail": 1}
_SUPPORTED: Final = ("stage-report", "review-findings", "triage-result")


def _name(rank: Mapping[str, int], value: object) -> str | None:
    """The key of ``rank`` that ``value`` spells (ignoring case, spaces and dashes), else ``None``."""
    if not isinstance(value, str):
        return None
    key = _SEPARATORS.sub("_", value.strip()).lower()
    return next((name for name in rank if name == key), None)


def _items(doc: Mapping[str, JsonValue], key: str) -> list[Mapping[str, JsonValue]]:
    """The object rows under ``key``; one object stands for a list of one."""
    value = doc.get(key)
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _words(value: object) -> str:
    """Identity text of a free-text field: blanks collapsed, case ignored; empty when it is not a string."""
    return _BLANKS.sub(" ", value).strip().casefold() if isinstance(value, str) else ""


def _place(location: object) -> str:
    """Normalized place of a finding: a location object is ``mount:path``, a bare string is its own path."""
    if isinstance(location, Mapping):
        fields = cast("Mapping[str, JsonValue]", location)
        path, mount = fields.get("path"), fields.get("mount")
        base = place(path) if isinstance(path, str) else "-"
        return f"{mount}:{base}" if isinstance(mount, str) and mount.strip() else base
    return place(location) if isinstance(location, str) else "-"


def _check_result(row: Mapping[str, JsonValue]) -> int | str:
    """The result of a check row (its ``exit`` or its manual ``verdict``) as one comparable value.

    ``pass`` and ``fail`` stand for exit 0 and 1; a value that spells nothing is kept as it was written.
    """
    value = row.get("exit") if "exit" in row else row.get("verdict")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?[0-9]+", text):
            try:
                return int(text)
            except ValueError:  # beyond the interpreter digit limit: kept as written, never a crash
                return text
        word = _name(_PASS_FAIL, text)
        return _PASS_FAIL[word] if word else text
    return repr(value)


def _key(*parts: str) -> str:
    return json.dumps(list(parts), ensure_ascii=False)


def _stage_report(doc: Mapping[str, JsonValue]) -> JsonObject:
    issues = _items(doc, "open_issues")
    counts = {
        name: sum(1 for issue in issues if _name({name: 0}, issue.get("kind")) == name)
        for name in ISSUE_COUNTS
    }
    deviations: dict[
        str, int
    ] = {}  # per content: how many are accepted; a deviation has no id, content is identity
    bare = 0
    for issue in issues:
        if _name({"deviation": 0}, issue.get("kind")) is None:
            continue
        accepted_here = 1 if _name({"accepted": 0}, issue.get("outcome")) else 0
        content = (
            _words(issue.get("text")),
            "" if _words(issue.get("impact")) == NO_IMPACT else _words(issue.get("impact")),
            "" if _words(issue.get("class")) == DEFAULT_DEVIATION_CLASS else _words(issue.get("class")),
        )
        if not any(content):  # nothing to tell it from another: only its place among such ones
            bare += 1
            content = (f"(no content) #{bare}", "", "")
        identity = _key(*content)
        deviations[identity] = deviations.get(identity, 0) + accepted_here
    questions = {
        str(row["id"]): row.get("blocking") is True for row in _items(doc, "questions") if "id" in row
    }
    checks: dict[str, list[int | str]] = {}
    for row in _items(doc, "checks_run"):
        if _CHECK_ID.fullmatch(str(row.get("id", ""))):
            checks.setdefault(str(row["id"]), []).append(_check_result(row))
    status = _name(STATUS_RANK, doc.get("status"))
    document = {
        "status": status,
        "status_rank": None if status is None else STATUS_RANK[status],
        "issue_counts": counts,
        "deviations_accepted": sum(deviations.values()),
        "deviation_accepted": deviations,
        "questions": questions,
        "check_rows": {name: sorted(rows, key=str) for name, rows in checks.items()},
    }
    return cast("JsonObject", document)


def _review(doc: Mapping[str, JsonValue]) -> JsonObject:
    places: dict[str, list[int]] = {}
    for row in _items(doc, "findings"):
        severity = _name(SEVERITY_RANK, row.get("severity"))
        identity = _key(_place(row.get("location")), _words(row.get("failure_scenario")))
        places.setdefault(identity, []).append(-1 if severity is None else SEVERITY_RANK[severity])
    verdict = _name(VERDICT_RANK, doc.get("verdict"))
    document = {
        "verdict": verdict,
        "verdict_rank": None if verdict is None else VERDICT_RANK[verdict],
        "findings": {name: sorted(ranks, reverse=True) for name, ranks in places.items()},
    }
    return cast("JsonObject", document)


def _triage_id(row: Mapping[str, JsonValue]) -> str | None:
    value = row.get("finding_id", row.get("finding"))
    return str(value) if value else None


def _triage(doc: Mapping[str, JsonValue]) -> JsonObject:
    sets = {
        key: sorted({found for row in _items(doc, key) if (found := _triage_id(row)) is not None})
        for key in ("confirmed", "rejected")
    }
    return cast("JsonObject", sets)


def outcome_key(kind: str, doc: JsonObject) -> JsonValue:
    """The fields of ``doc`` that carry its meaning, by kind; ``{}`` for an unsupported kind or a non-object.

    * ``stage-report``: the rank of the status; the counts of escalation, blocker, pending and deviation
      issues; how many deviations are accepted per content ``(text, impact, class)`` (one with no content
      is told apart only by its place among such ones; the values ``heal`` fills in for a deviation that
      stated none, the default impact and class ``other``, count as no content); the ``blocking`` flag
      of each question by id; the result of each ``V<n>`` check row.
    * ``review-findings``: the rank of the verdict and, per finding identity (normalized place and failure
      scenario, never the id or the severity: ids are renumbered and a repair may move severities), the
      severity ranks from the highest down.
    * ``triage-result``: the finding ids it confirmed and the ones it rejected.
    """
    if kind not in _SUPPORTED or not isinstance(doc, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        return {}
    if kind == "stage-report":
        return _stage_report(doc)
    if kind == "review-findings":
        return _review(doc)
    return _triage(doc)


def _stage_drift(old: Mapping[str, JsonValue], new: Mapping[str, JsonValue]) -> list[str]:
    found: list[str] = []
    old_rank, new_rank = old["status_rank"], new["status_rank"]
    if isinstance(old_rank, int) and (not isinstance(new_rank, int) or new_rank < old_rank):
        found.append(f"/status: {old['status']} -> {new['status']}")
    old_counts, new_counts = _as_map(old["issue_counts"]), _as_map(new["issue_counts"])
    found.extend(
        f"/open_issues: {name} {old_counts[name]} -> {new_counts[name]}"
        for name in ISSUE_COUNTS
        if _as_int(new_counts[name]) < _as_int(old_counts[name])
    )
    if _as_int(new["deviations_accepted"]) > _as_int(old["deviations_accepted"]):
        found.append(
            f"/open_issues: deviations accepted {old['deviations_accepted']} -> {new['deviations_accepted']}"
        )
    else:  # the total holds, but one deviation may be accepted while another turned into a follow-up
        before = _as_map(old["deviation_accepted"])
        for identity, count in _as_map(new["deviation_accepted"]).items():
            if _as_int(count) > _as_int(before.get(identity, 0)):
                text, impact, klass = json.loads(identity)
                found.append(
                    f"/open_issues: deviation accepted: {text or impact or klass or '(no text)'}"
                    f" (impact: {impact or '-'}, class: {klass or '-'})"
                )
    new_questions = _as_map(new["questions"])
    for name, blocking in _as_map(old["questions"]).items():
        if name not in new_questions:
            found.append(f"/questions: {name} lost")
        elif blocking and not new_questions[name]:
            found.append(f"/questions: {name} blocking true -> false")
    new_rows = _as_map(new["check_rows"])
    for name, rows in _as_map(old["check_rows"]).items():
        if name not in new_rows:
            found.append(f"/checks_run: {name} lost")
        elif new_rows[name] != rows:
            found.append(f"/checks_run: {name} result {_join(rows)} -> {_join(new_rows[name])}")
    return found


def _review_drift(old: Mapping[str, JsonValue], new: Mapping[str, JsonValue]) -> list[str]:
    found: list[str] = []
    old_rank, new_rank = old["verdict_rank"], new["verdict_rank"]
    if isinstance(old_rank, int) and (not isinstance(new_rank, int) or new_rank < old_rank):
        found.append(f"/verdict: {old['verdict']} -> {new['verdict']}")
    later_all = _as_map(new["findings"])
    for identity, ranks in _as_map(old["findings"]).items():
        before, later = _as_list(ranks), _as_list(later_all.get(identity, []))
        where = json.loads(identity)[0]
        if len(later) < len(before):
            found.append(f"finding lost at {where}")
            continue
        lowered = next((i for i, rank in enumerate(before) if _as_int(later[i]) < _as_int(rank)), None)
        if lowered is not None:
            was, now = _severity_name(before[lowered]), _severity_name(later[lowered])
            found.append(f"severity lowered at {where}: {was} -> {now}")
    return found


def _triage_drift(old: Mapping[str, JsonValue], new: Mapping[str, JsonValue]) -> list[str]:
    found: list[str] = []
    rejected, confirmed = _as_list(new["rejected"]), _as_list(new["confirmed"])
    for name in _as_list(old["confirmed"]):
        if name in rejected:
            found.append(f"finding {name} confirmed -> rejected")
        elif name not in confirmed:
            found.append(f"finding {name} confirmed -> lost")
    return found


def _as_map(value: JsonValue) -> Mapping[str, JsonValue]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _as_int(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _join(rows: JsonValue) -> str:
    return ", ".join(str(row) for row in _as_list(rows))


def _severity_name(rank: JsonValue) -> str:
    return next((name for name, number in SEVERITY_RANK.items() if number == rank), "?")


def drift(kind: str, before: JsonObject, after: JsonObject) -> tuple[str, ...]:
    """What got better, shrank or was lost from ``before`` to ``after`` (``/status: blocked -> done``).

    Empty when ``after`` means the same as ``before`` or is more cautious. A field ``before`` does not state
    (an unknown status) has nothing to compare and is not drift.
    """
    old, new = outcome_key(kind, before), outcome_key(kind, after)
    if not isinstance(old, Mapping) or not isinstance(new, Mapping) or not old:
        return ()
    if not new:
        return ("/: the document is no longer a readable result",)  # an unreadable after loses all of before
    if kind == "stage-report":
        return tuple(_stage_drift(old, new))
    if kind == "review-findings":
        return tuple(_review_drift(old, new))
    return tuple(_triage_drift(old, new))
