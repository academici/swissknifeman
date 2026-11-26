"""Repair of a role result's form and extraction of the result from a session (execution §5.8).

A role result is data for people and for the work source; its schema is there to catch a wrong *meaning*, not
a wrong form. Repeating a role costs a whole run of it, so every mismatch with exactly one honest reading
is mended here by rule and every mend is said (``notes``). There is no LLM report fixer (C3): what ``heal``
cannot mend goes to a repeat of the same role.

The law of the mend (I9): it keeps the meaning of a result or moves it toward caution, never away from it.
It never raises a status or a verdict, never drops an issue, finding, question or check row, never lowers a
severity, never turns an escalation or a blocker into another kind and never sets a deviation outcome to
``accepted`` by itself. A repeated check id (``checks_run[].id``) or finding id (``findings[].id``) is not
renamed: that result is not healable. ``semantics.drift`` holds a mend to the same law. Mending raw data is
*total*:
``heal`` returns a ``healed`` or a ``not_healable`` outcome for any JSON value and never raises.

The result shapes are JSON objects with a ``kind`` discriminator (``domain/contracts.py`` declares
them as JSON aliases):

* ``extract_result`` → ``{"kind": "extracted", "doc", "source"}`` | ``{"kind": "ambiguous", "candidates"}`` |
  ``{"kind": "missing"}``;
* ``heal`` → ``{"kind": "healed", "document", "notes"}`` | ``{"kind": "not_healable", "reason"}``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

from skm.modules.execution.domain.semantics import DEFAULT_DEVIATION_CLASS, NO_IMPACT, drift

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.execution.domain.contracts import Ambiguous, Extracted, HealOutcome, Missing, NotHealable

__all__ = [
    "MAX_SCHEMA_ERRORS",
    "NO_IMPACT",
    "NO_SUMMARY",
    "extract_result",
    "extraction_errors",
    "heal",
    "repair_form",
    "result_retry_allowed",
    "schema_error_hint",
    "schema_errors",
]

NO_SUMMARY: Final = "(the role gave no summary)"
NOT_DESCRIBED: Final = "(not described)"
MAX_SCHEMA_ERRORS: Final = 20
_MAX_MESSAGE: Final = 300
_MAX_EXPECTED: Final = 200
_SEVERE_ISSUE_TEXT: Final = 900

_CHECK_ID: Final = re.compile(r"V[0-9]+")
_FINDING_ID: Final = re.compile(r"F[0-9]{1,3}")
_BACKTICK_OPEN: Final = re.compile(r"^ {0,3}(`{3,})[ \t]*([^`\s]*)[^`]*$")
_TILDE_OPEN: Final = re.compile(r"^ {0,3}(~{3,})[ \t]*([^\s]*).*$")
_BACKTICK_CLOSE: Final = re.compile(r"^ {0,3}(`{3,})[ \t]*$")
_TILDE_CLOSE: Final = re.compile(r"^ {0,3}(~{3,})[ \t]*$")
# Info-string token, casefolded: empty, json, the seven role ids, the seven result kinds.
_FENCE_TAGS: Final = frozenset(
    {
        "",
        "json",
        "scout",
        "executor",
        "reviewer",
        "triager",
        "advisor",
        "researcher",
        "registrar",
        "context-map",
        "stage-report",
        "review-findings",
        "triage-result",
        "advice",
        "research-result",
        "registration-receipt",
    }
)
_WORD_BREAKS: Final = re.compile(r"[\s-]+")
_INTEGER: Final = re.compile(r"-?[0-9]+")

_STATUSES: Final = ("done", "done_with_deviations", "done_pending_checks", "blocked")
_VERDICTS: Final = ("green", "attention", "red")
_SEVERITIES: Final = ("blocker", "major", "minor", "nit")
_CONFIDENCES: Final = ("high", "medium", "low")
_ISSUE_KINDS: Final = ("escalation", "blocker", "pending", "deviation", "note", "assumption")
_DEVIATION_CLASSES: Final = (
    "write_set",
    "spec_mismatch",
    "test_env",
    "docs",
    "dependency",
    "environment",
    "other",
)
_DEVIATION_OUTCOMES: Final = ("accepted", "follow_up", "owner_decision")
_ISSUE_SEVERITIES: Final = ("low", "medium", "high", "critical")
_ESCALATION_CLASSES: Final = ("decision", "environment", "pre_existing_red", "scope", "authority")
_ISSUE_FIELDS: Final = (
    "text",
    "kind",
    "impact",
    "next",
    "class",
    "severity",
    "outcome",
    "auto_fixable",
    "evidence",
    "escalation_class",
)


# ---------------------------------------------------------------- extraction


def _object(text: str) -> JsonObject | None:
    """``text`` as one JSON object; ``None`` for anything else (not JSON, not an object, NaN, infinity)."""

    def refuse(constant: str) -> object:
        raise ValueError(constant)

    try:
        value: JsonValue = json.loads(text, parse_constant=refuse)
        json.dumps(value, allow_nan=False)  # 1e999 parses to infinity: not a JSON document
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _canonical(document: JsonValue) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fence_open(line: str) -> tuple[str, int, str] | None:
    """``(mark, width, tag)`` of a backtick or tilde opener, or ``None``."""
    for pattern in (_BACKTICK_OPEN, _TILDE_OPEN):
        opener = pattern.match(line)
        if opener is not None:
            mark = opener.group(1)
            return mark[0], len(mark), opener.group(2).casefold()
    return None


def _fence_closes(line: str, mark: str, width: int) -> bool:
    """True when ``line`` closes a fence of ``mark`` with a run at least ``width`` long.

    A backtick run never closes a tilde fence, and a tilde run never closes a backtick fence.
    """
    pattern = _BACKTICK_CLOSE if mark == "`" else _TILDE_CLOSE
    closer = pattern.match(line)
    return closer is not None and len(closer.group(1)) >= width


def _fenced_blocks(text: str) -> list[str]:
    """Bodies of closed backtick or tilde fences with an allowed info string, in order.

    The closing run uses the opener's character and is at least as long. The info-string token, casefolded,
    is empty, ``json``, a role id, or a result kind; any other language is ignored.
    """
    bodies: list[str] = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        opened = _fence_open(lines[index])
        index += 1
        if opened is None:
            continue
        mark, width, tag = opened
        body: list[str] = []
        closed = False
        while index < len(lines):
            line = lines[index]
            index += 1
            if _fence_closes(line, mark, width):
                closed = True
                break
            body.append(line)
        if closed and tag in _FENCE_TAGS:
            bodies.append("\n".join(body))
    return bodies


def _strip_leading_bom(text: str) -> str:
    """Strip surrounding whitespace and a leading U+FEFF.

    ``str.strip`` leaves the BOM, and ``json.loads`` rejects it.
    """
    stripped = text.strip()
    while stripped.startswith("\ufeff"):
        stripped = stripped.lstrip("\ufeff").strip()
    return stripped


def extract_result(structured: JsonObject | None, final_text: str) -> Extracted | Ambiguous | Missing:
    """The result document of a session, deterministically, from ``final_text`` only (never the transcript).

    1. the runtime's ``structured`` result; 2. the whole ``final_text`` (strip, drop a leading U+FEFF,
    CRLF → LF) as one JSON object; 3. backtick or tilde fences with an allowed info string whose body is
    one JSON object (a leading U+FEFF in the body is dropped). Equal blocks are one candidate. Several
    different candidates are ``ambiguous`` (no choice of "the last one"), none is ``missing``.
    """
    if structured is not None:
        return {"kind": "extracted", "doc": structured, "source": "structured"}
    text = _strip_leading_bom(final_text.replace("\r\n", "\n").replace("\r", "\n"))
    whole = _object(text)
    if whole is not None:
        return {"kind": "extracted", "doc": whole, "source": "final_text"}
    candidates: dict[str, JsonObject] = {}
    for body in _fenced_blocks(text):
        document = _object(_strip_leading_bom(body))
        if document is not None:
            candidates.setdefault(_canonical(document), document)
    if not candidates:
        return {"kind": "missing"}
    if len(candidates) > 1:
        return {"kind": "ambiguous", "candidates": list(candidates.values())}
    return {"kind": "extracted", "doc": next(iter(candidates.values())), "source": "fenced"}


def extraction_errors(outcome: Extracted | Ambiguous | Missing) -> list[JsonObject]:
    """``schema_errors`` of a result that could not be extracted (``result_invalid``); empty when it could."""
    kind = outcome.get("kind")
    if kind == "ambiguous":
        return [{"path": "", "message": "several different result documents", "expected": ""}]
    if kind == "missing":
        return [{"path": "", "message": "no result document", "expected": ""}]
    return []


# ---------------------------------------------------------------- schema errors


def _pointer(path: JsonValue) -> str:
    if isinstance(path, str):
        return path
    if isinstance(path, list):
        return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)
    return ""


def schema_errors(issues: Sequence[JsonObject]) -> list[JsonObject]:
    """At most 20 errors ``{path: JSON Pointer, message ≤ 300, expected ≤ 200}`` sorted by path."""
    rows: list[JsonObject] = []
    for issue in issues:
        if not isinstance(issue, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            continue
        expected = issue.get("expected")
        rows.append(
            {
                "path": _pointer(issue.get("path", issue.get("instance_path"))),
                "message": str(issue.get("message", ""))[:_MAX_MESSAGE],
                "expected": "" if expected is None else str(expected)[:_MAX_EXPECTED],
            }
        )
    rows.sort(key=lambda row: (str(row["path"]), str(row["message"])))
    return rows[:MAX_SCHEMA_ERRORS]


def schema_error_hint(issues: Sequence[JsonObject]) -> str:
    """The hint a repeated role gets: what the schema rejected, then to return the whole result."""
    shown = schema_errors(issues)
    parts: list[str] = []
    for row in shown:
        expected = f" (expected: {row['expected']})" if row["expected"] else ""
        parts.append(f"{row['path'] or '/'}: {row['message']}{expected}")
    omitted = len(issues) - len(shown)
    if omitted > 0:
        parts.append(f"… and {omitted} more errors")
    body = "; ".join(parts) if parts else "no details"
    return f"your previous result did not match the schema: {body}; return the whole result again"


def result_retry_allowed(retries_used: int, max_result_retries: int) -> bool:
    """Repeat the same role for a *form* that stays invalid: its own counter, apart from infra retries."""
    return retries_used < max_result_retries


# ---------------------------------------------------------------- heal helpers


class _Unhealable(Exception):  # internal control flow of heal, never leaves it
    pass


def _word(value: object, allowed: Sequence[str]) -> str | None:
    """``value`` matched to one of ``allowed`` ignoring case, spaces and dashes, else ``None``."""
    if not isinstance(value, str):
        return None
    key = _WORD_BREAKS.sub("_", value.strip()).lower()
    return next((option for option in allowed if option == key), None)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INTEGER.fullmatch(value.strip()):
        try:
            return int(value.strip())
        except ValueError:  # more digits than the interpreter converts: not a usable integer, not a crash
            return None
    return None


def _show(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _blank(value: object) -> bool:
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or (isinstance(value, (list, dict)) and not value)
    )


def _list(
    doc: Mapping[str, JsonValue], key: str, notes: list[str], *, scalars_to_text: bool = False
) -> list[JsonValue]:
    """``doc[key]`` read as a list. Fix of donor ``_list``: an object is a list of *one* (not its keys) and a
    number never reaches iteration.

    Missing → ``[]``; a string → a list of one (blank → ``[]``); an object → a list of one; a number or a
    bool → ``str`` in a list of strings, otherwise the value cannot be read as a list.
    """
    value = doc.get(key)
    if value is None:
        notes.append(f"{key} was missing; an empty list is assumed")
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        notes.append(f"{key} was one object; it is read as a list of one")
        return [value]
    if isinstance(value, str):
        notes.append(f"{key} was one string; it is read as a list of one")
        return [value] if value.strip() else []
    if scalars_to_text:
        notes.append(f"{key} was one {type(value).__name__}; it is read as a list of one text")
        return [str(value)]
    raise _Unhealable(f"{key} is not a list and cannot be read as one")


def _objects(items: Sequence[JsonValue], key: str) -> list[JsonObject]:
    rows: list[JsonObject] = []
    for item in items:
        if not isinstance(item, dict):
            raise _Unhealable(f"{key} holds an element that is not an object")
        rows.append(item)
    return rows


def _repeated_raw_id(rows: Sequence[JsonValue]) -> str | None:
    """The first string ``id`` repeated after strip, before a row is folded or renamed."""
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        value = raw.get("id")
        if not isinstance(value, str):
            continue
        name = value.strip()
        if name in seen:
            return name
        seen.add(name)
    return None


def _texts(items: Sequence[JsonValue], key: str, notes: list[str]) -> list[JsonValue]:
    rows: list[JsonValue] = []
    for item in items:
        if isinstance(item, str):
            rows.append(item)
        elif isinstance(item, (int, float)):  # bool is an int
            notes.append(f"{key}: {item!r} is not text; it is kept as text")
            rows.append(str(item))
        else:
            raise _Unhealable(f"{key} holds an element that is neither text nor a number")
    return rows


# ---------------------------------------------------------------- stage-report


def _evidence(issue: dict[str, JsonValue], folded: list[str]) -> None:
    value = issue["evidence"]
    if value == []:
        issue.pop("evidence")
        return
    rows = [value] if isinstance(value, str) else value
    if isinstance(rows, list) and rows and all(isinstance(row, str) and row.strip() for row in rows):
        issue["evidence"] = [row.strip() for row in rows if isinstance(row, str)]
    else:
        folded.append(f"evidence: {_show(issue.pop('evidence'))}")


def _issue_fields(issue: dict[str, JsonValue], notes: list[str]) -> None:
    """Class, severity, outcome, escalation class, auto_fixable, evidence normalized; deviation defaults.

    A word that matches no option is not guessed: it is folded into the text and the field is dropped. The
    deviation defaults are the cautious reading: ``other``, ``follow_up`` (a deviation is never accepted on
    the executor's silence) and an impact that says nobody stated it.
    """
    folded: list[str] = []
    for key, allowed in (
        ("class", _DEVIATION_CLASSES),
        ("severity", _ISSUE_SEVERITIES),
        ("outcome", _DEVIATION_OUTCOMES),
        ("escalation_class", _ESCALATION_CLASSES),
    ):
        if key not in issue:
            continue
        word = _word(issue[key], allowed)
        if word:
            issue[key] = word
        else:
            folded.append(f"{key}: {_show(issue.pop(key))}")
    if "auto_fixable" in issue and not isinstance(issue["auto_fixable"], bool):
        word = _word(issue["auto_fixable"], ("true", "false"))
        if word:
            issue["auto_fixable"] = word == "true"
        else:
            folded.append(f"auto_fixable: {_show(issue.pop('auto_fixable'))}")
    if "evidence" in issue:
        _evidence(issue, folded)
    if folded and isinstance(issue.get("text"), str):
        issue["text"] = f"{issue['text']} ({'; '.join(folded)})"
        names = ", ".join(entry.split(":")[0] for entry in folded)
        notes.append(f"open issue values {names} matched no option and were folded into its text")
    if issue.get("kind") != "deviation":
        return
    filled: list[str] = []
    for key, default in (("class", DEFAULT_DEVIATION_CLASS), ("outcome", "follow_up"), ("impact", NO_IMPACT)):
        if key not in issue:
            issue[key] = default
            filled.append(key)
    if filled:
        notes.append(
            f"a deviation lacked {', '.join(filled)}; the defaults are other, follow_up and '{NO_IMPACT}'"
        )


def _issue(raw: JsonValue, notes: list[str]) -> JsonObject:
    if isinstance(raw, str) and raw.strip():
        notes.append("an open issue was a plain string; it is kept as a note")
        return {"text": raw.strip(), "kind": "note"}
    if not isinstance(raw, dict):
        raise _Unhealable("open_issues holds an element that is neither an object nor text")
    issue: dict[str, JsonValue] = {key: value for key, value in raw.items() if key in _ISSUE_FIELDS}
    dropped = sorted(set(raw) - set(issue))
    if dropped:
        extra = "; ".join(f"{key}: {_show(raw[key])}" for key in dropped if not _blank(raw[key]))
        if extra and isinstance(issue.get("text"), str):
            issue["text"] = f"{issue['text']} ({extra})"
        notes.append(f"open issue keys {', '.join(dropped)} folded into its text")
    kind = _word(issue.get("kind"), _ISSUE_KINDS)
    if kind and kind != issue.get("kind"):
        issue["kind"] = kind
    for key in ("impact", "next"):
        value = issue.get(key)
        if key in issue and not (isinstance(value, str) and value.strip()):
            issue.pop(key)
    _issue_fields(issue, notes)
    return issue


def _check_row(raw: JsonValue, notes: list[str]) -> tuple[JsonObject | None, JsonObject | None]:
    """``(row, foreign)``: a ``checks_run`` row in one of its two shapes, or the row of a non-check."""
    if not isinstance(raw, dict):
        raise _Unhealable("checks_run holds an element that is not an object")
    if not _CHECK_ID.fullmatch(str(raw.get("id", ""))):
        return None, raw
    name = str(raw["id"])
    row: dict[str, JsonValue]
    if raw.get("cmd") or raw.get("command") or "exit" in raw:
        code = _int(raw.get("exit"))
        verdict = _word(raw.get("verdict"), ("pass", "fail"))
        if code is None and verdict is not None:
            code = 0 if verdict == "pass" else 1
        if code is None:
            raise _Unhealable(f"check {name} has no integer exit and no verdict")
        command = raw.get("cmd") or raw.get("command")
        if not command:
            notes.append(f"checks_run {name}: no command named")
        row = {"id": name, "cmd": command or "-", "exit": code}
    else:
        verdict = _word(raw.get("verdict"), ("pass", "fail"))
        if verdict is None:
            raise _Unhealable(f"check {name} has no result")
        row = {"id": name, "procedure": raw.get("procedure") or "-", "verdict": verdict}
    ignored = sorted(set(raw) - set(row) - {"command"})
    if ignored:
        notes.append(f"checks_run {name}: keys {', '.join(ignored)} dropped")
    return row, None


def _escalation(doc: Mapping[str, JsonValue], issues: list[JsonObject], notes: list[str]) -> None:
    """A blocked report names its gap: the blocker's words, else the summary (the owner decides)."""
    blocker = next((issue for issue in issues if issue.get("kind") == "blocker"), None)
    if blocker is not None:
        carried = {key: blocker[key] for key in ("impact", "next") if isinstance(blocker.get(key), str)}
        text = str(blocker.get("text") or doc["summary"])[:_SEVERE_ISSUE_TEXT]
        issues.append({**carried, "text": text, "kind": "escalation", "escalation_class": "decision"})
        notes.append(
            "a blocked report named its gap as a blocker; the blocker is kept and escalated to the owner"
        )
        return
    text = f"the executor reported blocked without naming the gap; its summary: {doc['summary']}"
    issues.append(
        {
            "text": text[:_SEVERE_ISSUE_TEXT],
            "kind": "escalation",
            "escalation_class": "decision",
            "next": "the owner reads the summary and the stream of the step",
        }
    )
    notes.append("a blocked report named no escalation; one is made from its summary")


def _status(value: object) -> str | None:
    """The stage-report status. The spelling ``blocker`` reads as ``blocked``.

    Issue kind ``blocker`` and finding severity ``blocker`` are not statuses and are not read here.
    """
    named = _word(value, _STATUSES)
    if named is not None:
        return named
    if _word(value, ("blocker",)) is not None:
        return "blocked"
    return None


def _stage_report(source: Mapping[str, JsonValue], notes: list[str]) -> JsonObject:
    doc: dict[str, JsonValue] = dict(source)
    status = _status(doc.get("status"))
    if status and status != doc.get("status"):
        doc["status"] = status
        notes.append(f"status was spelled {_show(source.get('status'))!r}; it is {status}")
    paths = _list(doc, "changed_paths", notes)
    unique: dict[str, JsonValue] = {}
    for path in paths:
        if not isinstance(path, (str, dict)):
            raise _Unhealable("changed_paths holds an element that is neither text nor an object")
        unique.setdefault(_canonical(path), path)
    if len(unique) != len(paths):
        notes.append("repeated changed_paths were collapsed in order of first appearance")
    doc["changed_paths"] = list(unique.values())
    doc["evidence"] = _texts(_list(doc, "evidence", notes, scalars_to_text=True), "evidence", notes)
    rows = _list(doc, "checks_run", notes)
    issues_in = _list(doc, "open_issues", notes)
    summary = doc.get("summary")
    if isinstance(summary, (int, float)):
        doc["summary"] = str(summary)
        notes.append("summary was not text; it is kept as text")
    elif summary is None or (isinstance(summary, str) and not summary.strip()):
        doc["summary"] = NO_SUMMARY
        notes.append("summary was empty")
    elif not isinstance(summary, str):
        raise _Unhealable("summary is neither text nor a number")
    issues = [_issue(raw, notes) for raw in issues_in]
    repeated_check = _repeated_raw_id(rows)
    if repeated_check is not None:
        raise _Unhealable(f"checks_run id {repeated_check} is duplicated")
    checks: list[JsonValue] = []
    foreign: list[JsonObject] = []
    seen_checks: set[str] = set()
    for raw in rows:
        row, other = _check_row(raw, notes)
        if other is not None:
            foreign.append(other)
        elif row is not None:
            name = str(row["id"])
            if name in seen_checks:
                raise _Unhealable(f"checks_run id {name} is duplicated")
            seen_checks.add(name)
            checks.append(row)
    if foreign:
        cmds = "; ".join(
            f"{_show(row.get('id'))}: {_show(row.get('cmd') or row.get('procedure') or '-')} -> "
            f"{_show(row.get('exit', row.get('verdict', '-')))}"
            for row in foreign
        )
        issues.append(
            {
                "text": f"commands the executor ran outside the acceptance checks: {cmds}"[
                    :_SEVERE_ISSUE_TEXT
                ],
                "kind": "note",
                "impact": "none",
                "next": "none",
            }
        )
    doc["checks_run"] = checks
    _consequences(doc, issues, notes)
    doc["open_issues"] = list(issues)
    return doc


def _consequences(doc: dict[str, JsonValue], issues: list[JsonObject], notes: list[str]) -> None:
    """Complete what a status names impossibly, on the cautious side (rules 7-10)."""
    kinds = {kind for issue in issues if isinstance(kind := issue.get("kind"), str)}
    status = doc.get("status")
    if status == "done_with_deviations" and "deviation" not in kinds:
        issues.append(
            {
                "text": "the executor reported done_with_deviations without naming the deviation",
                "kind": "deviation",
                "class": DEFAULT_DEVIATION_CLASS,
                "outcome": "follow_up",
                "impact": NO_IMPACT,
            }
        )
        notes.append("status done_with_deviations named no deviation issue; a follow-up deviation says so")
    if status == "done_pending_checks" and "pending" not in kinds:
        issues.append(
            {"text": "the executor named no pending check; the conductor checks decide", "kind": "pending"}
        )
        notes.append("status done_pending_checks named no pending issue; a pending issue says so")
    questions = doc.get("questions")
    asked = [questions] if isinstance(questions, dict) else questions if isinstance(questions, list) else []
    blocking_question = any(isinstance(q, dict) and q.get("blocking") is True for q in asked)
    if status != "blocked" and ("escalation" in kinds or blocking_question):
        doc["status"] = status = "blocked"
        notes.append(
            "an escalation was reported; the report is blocked for the owner"
            if "escalation" in kinds
            else "a blocking question was asked; the report is blocked for the owner"
        )
    if status == "blocked" and "escalation" not in kinds:
        _escalation(doc, issues, notes)


# ---------------------------------------------------------------- review-findings


def _fresh_id(taken: set[str]) -> str:
    for number in range(1, 1000):
        if f"F{number}" not in taken:
            return f"F{number}"
    raise _Unhealable("no free finding id F<n> remains")


def _finding(raw: JsonObject, seen: set[str], reserved: set[str], notes: list[str]) -> JsonObject:
    finding: dict[str, JsonValue] = dict(raw)
    local = finding.get("id")
    if isinstance(local, str) and _FINDING_ID.fullmatch(local):
        if local in seen:
            raise _Unhealable(f"finding id {local} is duplicated")
    else:
        fresh = _fresh_id(seen | reserved)
        notes.append(f"finding id {_show(local)!r} is not F<number>; it is {fresh}")
        finding["id"] = fresh
    seen.add(str(finding["id"]))
    for key, allowed in (("severity", _SEVERITIES), ("confidence", _CONFIDENCES)):
        word = _word(finding.get(key), allowed)
        if word:
            finding[key] = word
    if finding.get("confidence") not in _CONFIDENCES:
        finding["confidence"] = "medium"
        notes.append(f"finding {finding['id']} had no known confidence; medium is assumed")
    if _blank(finding.get("basis")):
        finding["basis"] = "correctness"
        notes.append(f"finding {finding['id']} had no basis; correctness is assumed")
    if "reproduction" in finding and _blank(finding["reproduction"]):
        finding.pop("reproduction")
    return finding


def _review(source: Mapping[str, JsonValue], notes: list[str]) -> JsonObject:
    doc: dict[str, JsonValue] = dict(source)
    verdict = _word(doc.get("verdict"), _VERDICTS)
    if verdict and verdict != doc.get("verdict"):
        doc["verdict"] = verdict
        notes.append(f"verdict was spelled {_show(source.get('verdict'))!r}; it is {verdict}")
    raws = _objects(_list(doc, "findings", notes), "findings")
    repeated_finding = _repeated_raw_id(raws)
    if repeated_finding is not None:
        raise _Unhealable(f"finding id {repeated_finding} is duplicated")
    reserved = {value for raw in raws if isinstance(value := raw.get("id"), str)}
    seen: set[str] = set()
    findings = [_finding(raw, seen, reserved, notes) for raw in raws]
    doc["findings"] = list(findings)
    severities = {value for finding in findings if isinstance(value := finding.get("severity"), str)}
    if doc.get("verdict") == "green" and severities & {"blocker", "major"}:
        doc["verdict"] = "red" if "blocker" in severities else "attention"
        notes.append(f"verdict green with a blocker or major finding; the findings win: {doc['verdict']}")
    return doc  # attention or red without findings is not mended into green: a repeat of the role says why


# ---------------------------------------------------------------- triage-result


def _triage_entry(key: str, raw: JsonObject, notes: list[str]) -> JsonObject:
    entry: dict[str, JsonValue] = dict(raw)
    repro = entry.get("reproduction")
    if isinstance(repro, dict):
        fixed: dict[str, JsonValue] = dict(repro)
        code = _int(fixed.get("exit"))
        if code is not None:
            fixed["exit"] = code
        if not fixed.get("observed"):
            fixed["observed"] = NOT_DESCRIBED
            notes.append(f"{key} {_show(entry.get('finding_id'))}: reproduction without an observation")
        entry["reproduction"] = fixed
    elif key == "rejected" and repro is None:
        entry.pop("reproduction", None)
    return entry


def _triage(source: Mapping[str, JsonValue], notes: list[str]) -> JsonObject:
    doc: dict[str, JsonValue] = dict(source)
    for key in ("confirmed", "rejected"):
        entries = _objects(_list(doc, key, notes), key)
        doc[key] = [_triage_entry(key, entry, notes) for entry in entries]
    return doc


_HEALERS: Final = {"stage-report": _stage_report, "review-findings": _review, "triage-result": _triage}


def heal(kind: str, doc: JsonValue) -> HealOutcome | NotHealable:
    """The result of ``kind`` with its form mended by the rules of §5.8, or why it cannot be mended.

    Total: any JSON value gives ``healed`` (with the document and a note per mend) or ``not_healable``
    (``result_invalid`` follows, with the schema errors of the *original* document). ``doc`` is not changed.
    """
    healer = _HEALERS.get(kind)
    if healer is None:
        return {"kind": "not_healable", "reason": f"no form repair for {kind!r}"}
    if not isinstance(doc, dict):
        return {"kind": "not_healable", "reason": "the result is not an object"}
    notes: list[str] = []
    try:
        document = healer(doc, notes)
    except _Unhealable as error:
        return {"kind": "not_healable", "reason": str(error)}
    except RecursionError:
        return {"kind": "not_healable", "reason": "the result is nested too deeply"}
    return {"kind": "healed", "document": document, "notes": list(notes)}


def repair_form(kind: str, raw: JsonObject) -> JsonObject:
    """Mend an invalid ``raw`` result and hold the mend to the law of meaning (host step 3, server step 5).

    ``{"kind": "repaired", "result", "repairs", "raw"}`` when the mend is possible and ``drift(raw, result)``
    is empty; ``{"kind": "semantic_drift", "code": "REPAIR_SEMANTIC_DRIFT", "drift", "raw"}`` when it is not
    (a defect of ``heal``, the outcome is ``result_invalid``); ``{"kind": "not_healable", "reason", "raw"}``
    otherwise. ``raw`` is returned untouched in every case: it is stored as the raw result of the step. The
    schema validation of ``result`` stays with the caller.
    """
    outcome = heal(kind, raw)
    if outcome["kind"] != "healed":
        return {"kind": "not_healable", "reason": outcome["reason"], "raw": raw}
    document = outcome["document"]
    if not isinstance(document, dict):
        return {"kind": "not_healable", "reason": "the mend did not produce an object", "raw": raw}
    changed = drift(kind, raw, document)
    if changed:
        return {"kind": "semantic_drift", "code": "REPAIR_SEMANTIC_DRIFT", "drift": list(changed), "raw": raw}
    return {"kind": "repaired", "result": document, "repairs": outcome["notes"], "raw": raw}
