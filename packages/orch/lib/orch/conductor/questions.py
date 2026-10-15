"""Questions of an agent as saved decisions (D11): the spec the agent asked, its binding to the input it was asked on, and
the resolution someone gave.

A blocking question never keeps a process: the piece is ``blocked``, the run ends, and ``questions.json`` of the piece
holds the question. ``orch conduct answer`` writes a resolution into that file only; ``resume --retry`` merges it into the
state of the run and gives it to the executor, but only while the input is the one the question was asked on
(``binding.input_digest``). ``default`` (a proposal) is not ``assumed`` (what the agent went on with) and not what a
timeout does: the conductor never answers on a timeout.

Entry of a question: ``id, revision, kind, text, [options, answer_schema, default], blocking, [assumed, risk], status,
binding{run,item,step,input_digest}, asked_at, [resolution{value,by,at}]``. ``status`` is ``open`` (waits for an answer),
``answered`` (the resolution is not given to the executor yet), ``applied`` (the executor got it), ``assumed`` (not
blocking: the agent went on), ``denied`` (``questions = deny``) or ``stale`` (the input changed: the answer is not used,
the revision is one higher).
"""
from __future__ import annotations

import calendar
import json
from pathlib import Path
import time
from typing import Optional

FILE = "questions.json"
MODES = ("queue", "deny", "defaults")
DEFAULT_WARN_S = 1800
_SPEC = ("id", "revision", "kind", "text", "options", "answer_schema", "default", "blocking", "assumed", "risk")


class QuestionError(Exception):
    """``QUESTION_UNKNOWN`` / ``QUESTION_NOT_OPEN`` / ``ANSWER_INVALID``: an answer that cannot be taken."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _epoch(text: str) -> float:
    return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))


def record(store: dict, asked: list, binding: dict, now: str) -> list:
    """Put the questions of a report into ``store`` (id → entry); returns the entries that are new or asked again.

    A question that was answered and given to the executor stays as it is (a round that repeats the question does not
    undo the answer). A question that is still open, stale or denied is asked again: it takes the new binding and a
    revision not below its own.
    """
    changed = []
    for question in asked:
        known = store.get(question["id"])
        if known and known["status"] == "applied" and known.get("auto_answered") and known["binding"].get("step") != binding["step"]:
            # the executor asked it again after the policy answered it once: the policy does not answer twice, the
            # question waits for a person
            known["stale_resolution"] = known.pop("resolution")
            known["status"] = "open"
            known["binding"], known["asked_at"] = dict(binding), now
            changed.append(known)
            continue
        if (known and known["status"] != "stale" and known["binding"].get("step") == binding["step"]
                and known["revision"] >= question["revision"]):
            continue  # the same round again (a resume walks it): nothing new
        if known and known["status"] in ("applied", "answered") and known["revision"] >= question["revision"]:
            continue
        entry = {key: question[key] for key in _SPEC if key in question}
        entry["revision"] = max(question["revision"], known["revision"] if known else 1)
        entry["status"] = "open" if question["blocking"] else "assumed"
        entry["binding"] = dict(binding)
        entry["asked_at"] = now
        for kept in ("auto_answered", "stale_resolution"):
            if known and kept in known:
                entry[kept] = known[kept]
        store[question["id"]] = entry
        changed.append(entry)
    return changed


def blocking_open(store: dict, asked: list) -> list:
    """The questions of this report that still wait: blocking and without a resolution."""
    return [store[question["id"]] for question in asked
            if question["blocking"] and store[question["id"]]["status"] in ("open", "denied")]


def assumptions(store: dict) -> list:
    """One ``assumption`` issue per question the agent went on without an answer to (``blocking: false``)."""
    return [{"text": f"question {entry['id']}: {entry['text']} — assumed: {entry['assumed']}", "kind": "assumption",
             "impact": "the work went on with this value", "next": "check it, or answer and run the piece again",
             **({"severity": entry["risk"]} if entry.get("risk") in ("low", "medium", "high") else {})}
            for entry in store.values() if entry["status"] == "assumed"]


def resolve_default(entry: dict, now: str) -> bool:
    """Answer ``entry`` with its ``default`` by policy, once; ``False`` when it has none or was answered so before."""
    if "default" not in entry or entry.get("auto_answered"):
        return False
    entry["resolution"] = {"value": entry["default"], "by": "policy", "at": now}
    entry["status"] = "applied"
    entry["auto_answered"] = True
    return True


def apply(store: dict, digest: Optional[str], now: str) -> tuple:
    """Hand the answers of ``store`` to the executor: ``(applied ids, stale ids)``.

    An ``answered`` entry whose binding digest is the current one becomes ``applied``; any other is ``stale``: its
    resolution moves to ``stale_resolution``, its revision goes up and the question is open again.
    """
    applied, stale = [], []
    for entry in store.values():
        if entry["status"] != "answered":
            continue
        if entry["binding"].get("input_digest") == digest:
            entry["status"] = "applied"
            entry["applied_at"] = now
            applied.append(entry["id"])
        else:
            entry["stale_resolution"] = entry.pop("resolution")
            entry["revision"] += 1
            entry["status"] = "stale"
            stale.append(entry["id"])
    return applied, stale


def merge_file(store: dict, document: Optional[dict]) -> None:
    """Take the resolutions written into ``questions.json`` (by ``orch conduct answer``) into ``store``."""
    for entry in (document or {}).get("questions", []):
        mine = store.get(entry["id"])
        if (mine and mine["status"] == "open" and entry.get("resolution") and entry["revision"] == mine["revision"]):
            mine["resolution"] = entry["resolution"]
            mine["status"] = "answered"


def answers_text(store: dict) -> list:
    """The resolutions the executor must see: ``[{id, text, answer, by}]``, in the order of the questions."""
    return [{"id": entry["id"], "text": entry["text"], "answer": entry["resolution"]["value"],
             "by": entry["resolution"]["by"]} for entry in store.values()
            if entry["status"] == "applied" and entry.get("resolution")]


def path(item_directory: Path) -> Path:
    return Path(item_directory) / FILE


def read(item_directory: Path) -> Optional[dict]:
    try:
        return json.loads(path(item_directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def document(run: str, item: str, store: dict) -> dict:
    return {"run": run, "item": item, "questions": list(store.values())}


def answer(file_doc: dict, question: str, *, option: Optional[str] = None, text: Optional[str] = None, by: str,
           now: str) -> dict:
    """Write the resolution of ``question`` into the document of ``questions.json``; returns the entry."""
    entry = next((row for row in file_doc.get("questions", []) if row["id"] == question), None)
    if entry is None:
        raise QuestionError("QUESTION_UNKNOWN", f"no question {question} in {file_doc.get('item')}")
    if entry["status"] != "open":
        raise QuestionError("QUESTION_NOT_OPEN", f"question {question} is {entry['status']}, not open"
                            + (" (it was asked again after the input changed: answer its new revision after the run "
                               "asks it)" if entry["status"] == "stale" else ""))
    options = [row["id"] for row in entry.get("options") or []]
    if option is not None:
        if option not in options:
            raise QuestionError("ANSWER_INVALID", f"{option!r} is not an option of {question}: "
                                + (", ".join(options) or "it has no options"))
        value = option
    else:
        if options and entry["kind"] != "clarification":
            raise QuestionError("ANSWER_INVALID", f"{question} is answered by one of its options: {', '.join(options)}")
        value = text
    entry["resolution"] = {"value": value, "by": by, "at": now}
    return entry


def listing(directory: Path, now: float, default_warn_s: int = DEFAULT_WARN_S) -> list:
    """Open questions of the run in ``directory``: ``[{item, id, revision, text, age_s, overdue}]``."""
    rows = []
    for file in sorted(Path(directory).glob(f"*/{FILE}")):
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        warn = warn_seconds(file.parent, default_warn_s)
        for entry in doc.get("questions", []):
            if entry["status"] != "open":
                continue
            age = max(0, int(now - _epoch(entry["asked_at"])))
            answered = bool(entry.get("resolution"))  # it waits for resume, not for an answer
            rows.append({"item": doc.get("item"), "id": entry["id"], "revision": entry["revision"], "kind": entry["kind"],
                         "text": entry["text"], "answered": answered, "age_s": age,
                         "overdue": bool(warn) and age > warn and not answered})
    return rows


def warn_seconds(item_directory: Path, default: int = DEFAULT_WARN_S) -> int:
    try:
        options = json.loads((Path(item_directory) / "options.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return int((((options.get("options") or {}).get("limits") or {}).get("question_warn_s", default)))
