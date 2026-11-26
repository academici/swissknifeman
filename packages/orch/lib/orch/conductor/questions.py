"""Questions of an agent as saved decisions (D11): the spec the agent asked, its binding to the input it was asked on, and
the resolution someone gave.

A blocking question never keeps a process: the piece is ``blocked``, the run ends, and ``questions.json`` of the piece
holds the question. ``orch conduct answer`` writes a resolution into that file only; ``resume --retry`` merges it into the
state of the run and gives it to the executor, but only while the input is the one the question was asked on
(``binding.input_part_digest``, or the full ``input_digest`` for legacy records). ``default`` (a proposal) is not
``assumed`` (what the agent went on with) and not what a
timeout does: the conductor never answers on a timeout.

Entry of a question: ``id, revision, kind, text, [options, answer_schema, default], blocking, [assumed, risk], status,
binding{run,item,step,input_digest,[input_part_digest]}, asked_at, [resolution{value,by,at}, answer_schema_ignored]``
(records/v1 questions); an entry answered by an accepted decision also has ``question_key`` and ``question_digest``
(:func:`question_key`: the meaning of a question, never only its id). An answer is checked against ``answer_schema`` when that schema loads in the closed profile; else
it is taken and ``answer_schema_ignored`` says why.
``status`` is ``open`` (waits for an answer),
``answered`` (the resolution is not given to the executor yet), ``applied`` (the executor got it), ``assumed`` (not
blocking: the agent went on), ``denied`` (``questions = deny``) or ``stale`` (the input changed: the answer is not used,
the revision is one higher).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Optional

from aicore.util import schema, timefmt
from aicore.util.digest import sha256_hex
from aicore.util.redact import redact_text

from orch._types.records import Questions
from orch.conductor import records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.lease import questions_lock

FILE = "questions.json"
MODES = ("queue", "deny", "defaults", "advisor")
DEFAULT_WARN_S = 1800
_SPEC = ("id", "revision", "kind", "text", "options", "answer_schema", "default", "blocking", "assumed", "risk")


class QuestionsInvalid(Stop):
    """``QUESTIONS_INVALID``: ``questions.json`` of a piece is not JSON or does not match records/v1 questions. Nothing is
    written over it: an answer it may hold is never lost by a rewrite."""

    def __init__(self, message: str):
        super().__init__("QUESTIONS_INVALID", message)


class QuestionError(Exception):
    """``QUESTION_UNKNOWN`` / ``QUESTION_NOT_OPEN`` / ``ANSWER_INVALID``: an answer that cannot be taken."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _epoch(text: str) -> float:
    value = timefmt.epoch(text)
    if value is None:
        raise ValueError(f"not a timestamp: {text!r}")
    return int(value)


REUSABLE_KINDS = ("decision", "clarification")  # approval and credential are the owner's every time


def _meaning(item_ref: str, entry: dict) -> dict:
    """What a question means, apart from its id and revision: the piece, the kind, the text (whitespace collapsed; case
    and digits stay), the full definition of each option (by id) and the answer schema."""
    options = sorted(({key: value for key, value in option.items()} for option in entry.get("options") or []),
                     key=lambda option: option["id"])
    return {"item": item_ref, "kind": entry["kind"], "text": " ".join(str(entry["text"]).split()), "options": options,
            "answer_schema": entry.get("answer_schema")}


def question_digest(item_ref: str, entry: dict) -> str:
    """Full sha256 of the canonical JSON of the meaning of a question."""
    return sha256_hex(json.dumps(_meaning(item_ref, entry), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8"))


def question_key(item_ref: str, entry: dict) -> str:
    """``qk-`` and the first 16 hex characters of :func:`question_digest`: the same question of the same piece, asked
    again, has the same key; a changed number, option or schema is another question."""
    return "qk-" + question_digest(item_ref, entry)[:16]


def decision_text(entry: dict) -> str:
    """The text of the decision a resolution becomes in the plan: ``<id>: <label>`` for an option, the string itself, else
    the JSON of the value."""
    value = entry["resolution"]["value"]
    option = next((row for row in entry.get("options") or [] if row["id"] == value), None)
    if option is not None:
        return f"{option['id']}: {option['label']}" if option.get("label") else option["id"]
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def reusable_value(entry: dict, decision: str) -> tuple:
    """``(True, value)`` when the text of an accepted decision is an answer the question can take: the id of one of its
    options (alone or before ``: label``), or a text that passes ``answer_schema``; else ``(False, None)``."""
    options = [row["id"] for row in entry.get("options") or []]
    for name in sorted(options, key=len, reverse=True):
        if decision == name or decision.startswith(f"{name}: "):
            return True, name
    if options and entry["kind"] != "clarification":
        return False, None
    answer_schema = entry.get("answer_schema")
    if not answer_schema:
        return bool(decision.strip()), decision
    if _answer_schema_problem(answer_schema):
        return False, None
    try:
        probe = {"answer_schema": answer_schema}
        value = _checked_answer(probe, entry["id"], decision, text=True)
    except QuestionError:
        return False, None
    return True, value


def reusable(item_ref: str, entry: dict, decisions: list) -> tuple:
    """``(decision, value, None)`` for the accepted decision that answers ``entry`` again, else ``(None, None, reason)``:
    ``reason`` is ``None`` when no decision names this question, else ``key`` (the same meaning under another key),
    ``digest`` (the key matches, the meaning is not proven) or ``value`` (the answer does not fit this question)."""
    if entry["kind"] not in REUSABLE_KINDS:
        return None, None, None
    key, digest = question_key(item_ref, entry), question_digest(item_ref, entry)
    refused = None
    for decision in decisions:
        if decision.get("status") != "accepted" or not isinstance(decision.get("decision"), str):
            continue
        if decision.get("question_digest") == digest and decision.get("question_key") != key:
            refused = refused or "key"
        elif decision.get("question_key") == key:
            if decision.get("question_digest") != digest:
                refused = refused or "digest"
                continue
            fits, value = reusable_value(entry, decision["decision"])
            if fits:
                return decision, value, None
            refused = refused or "value"
    return None, None, refused


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


def resolve_default(entry: dict, now: str, authority: Optional[dict] = None) -> bool:
    """Answer a non-owner-only question with its default once, recording the caller's authority snapshot."""
    if entry.get("kind") in ("approval", "credential") or "default" not in entry or entry.get("auto_answered"):
        return False
    entry["resolution"] = {"value": entry["default"], "by": "policy", "at": now,
                           "authority": authority if authority is not None else {
                               "mode": "defaults", "gate": [], "code_categories": [], "confidence": None}}
    entry["status"] = "applied"
    entry["auto_answered"] = True
    return True


def apply(store: dict, digest: Optional[str], part_digest: str, now: str) -> tuple:
    """Hand the answers of ``store`` to the executor: ``(applied ids, stale ids)``.

    An ``answered`` entry bound to the current required part becomes ``applied`` (legacy records compare the full
    input digest); any other is ``stale``: its
    resolution moves to ``stale_resolution``, its revision goes up and the question is open again.
    """
    applied, stale = [], []
    for entry in store.values():
        if entry["status"] != "answered":
            continue
        key = entry["binding"].get("input_part_digest")
        fresh = (key == part_digest) if key else (entry["binding"].get("input_digest") == digest)
        if fresh:
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
        # An owner may answer while the conductor computes a policy decision outside the short file lock.
        # A persisted answer awaiting consumption wins over that still-unpublished decision.
        pending_answer = entry.get("status") == "open"
        if (mine and (mine["status"] == "open" or pending_answer) and entry.get("resolution")
                and entry["revision"] == mine["revision"] and entry.get("binding") == mine.get("binding")):
            mine["resolution"] = entry["resolution"]
            mine["status"] = "answered"
            if entry.get("answer_schema_ignored"):
                mine["answer_schema_ignored"] = entry["answer_schema_ignored"]
            if entry["resolution"].get("by") != "policy":
                # A person's answer must not be reopened as an already-used policy default.
                mine.pop("auto_answered", None)


def answers_text(store: dict) -> list:
    """The resolutions the executor must see: ``[{id, text, answer, by}]``, in the order of the questions."""
    return [{"id": entry["id"], "text": entry["text"], "answer": entry["resolution"]["value"],
             "by": entry["resolution"]["by"]} for entry in store.values()
            if entry["status"] == "applied" and entry.get("resolution")]


def path(item_directory: Path) -> Path:
    return Path(item_directory) / FILE


def read(item_directory: Path) -> Optional[Questions]:
    """``questions.json`` of the piece checked against records/v1 (``None`` when there is none); ``QuestionsInvalid``
    when it is not JSON or does not match, never a document read as empty."""
    try:
        return records.read(path(item_directory), "questions")
    except Stop as stop:
        raise QuestionsInvalid(stop.message) from None


def document(run: str, item: str, store: dict) -> dict:
    return {"run": run, "item": item, "questions": list(store.values())}


def write(item_directory: Path, run: str, item: str, store: dict) -> None:
    """Replace ``questions.json`` with ``store`` (the caller holds ``questions_lock``)."""
    records.write(path(item_directory), document(run, item, store), "questions")


def save(item_directory: Path, run: str, item: str, store: dict) -> None:
    """Merge a concurrent answer before replacing the question document. Lock order: this lock first, the run-store
    lock after it (the caller saves the state once this returns)."""
    with questions_lock(item_directory):
        merge_file(store, read(item_directory))
        write(item_directory, run, item, store)


def answer_file(item_directory: Path, question: str, *, item: Optional[str] = None, **kwargs) -> dict:
    """Answer ``question`` in ``questions.json`` of the item under its lock. An item without questions is refused before
    anything is written: a mistyped ``--item`` leaves no folder and no lock file behind."""
    if not path(item_directory).is_file():
        raise QuestionError("QUESTION_UNKNOWN", f"{item or Path(item_directory).name} has no questions in run "
                                                f"{Path(item_directory).parent.name}")
    with questions_lock(item_directory):
        doc = read(item_directory)
        if doc is None:
            raise QuestionError("QUESTION_UNKNOWN", f"no questions in {item_directory}")
        entry = answer(doc, question, **kwargs)
        records.write(path(item_directory), doc, "questions")
        return entry


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
        if options and entry["kind"] != "clarification" and not any(
            isinstance(text, str) and (text == opt or text.startswith(f"{opt}:") or text.startswith(f"{opt} "))
            for opt in options
        ):
            raise QuestionError("ANSWER_INVALID", f"{question} is answered by one of its options: {', '.join(options)}")
        if text and redact_text(text) != text:
            # an answer goes into questions.json and into the prompt of the executor (a provider): never a secret
            raise QuestionError("ANSWER_INVALID", f"the answer to {question} looks like a secret; a credential never goes "
                                "into a run: put it where the role reads it (an environment variable, a secret store) "
                                "and answer with its name")
        value = text
    if entry.get("answer_schema"):
        value = _checked_answer(entry, question, value, text=option is None)
    entry["resolution"] = {"value": value, "by": by, "at": now}
    return entry


_ANSWER_ID = "urn:answer"


def _answer_registry(answer_schema: dict) -> schema.Registry:
    return schema.Registry({_ANSWER_ID: answer_schema}, urn_prefix="urn:", kinds=(), version="v1")


def _answer_schema_problem(answer_schema: dict) -> Optional[str]:
    """Why ``answer_schema`` cannot be applied: it leaves the closed profile of the validator, refers outside itself, or
    a ``$ref`` does not resolve in the registry the answer is checked with (only ``#/$defs/<name>`` fragments do);
    ``None`` when it can."""
    try:
        schema._check_profile(answer_schema, "answer_schema", "", root=True)
    except schema.SchemaProfileError as error:
        return str(error)
    refs = sorted(set(schema._refs(answer_schema)))
    outside = [ref for ref in refs if not ref.startswith("#")]
    if outside:
        return f"answer_schema: $ref outside the schema: {', '.join(outside)}"
    registry = _answer_registry(answer_schema)
    for ref in refs:
        try:
            registry.resolve(ref, _ANSWER_ID)
        except schema.RefError as error:
            return f"answer_schema: $ref {ref!r} does not resolve: {error}"
    if _same_level_cycle(registry, answer_schema):
        return "answer_schema: a $ref cycle never reaches a check"
    return None


def _same_level_cycle(registry: schema.Registry, root: dict) -> bool:
    """Whether some node of the schema reaches itself through ``$ref``, ``oneOf`` and ``not`` alone: those check the same
    value again, so validation would never end (``{"$ref": "#"}``). Keywords that descend into the value end on their own."""
    def same_level(node: dict) -> list:
        found = [registry.resolve(node["$ref"], _ANSWER_ID)[0]] if isinstance(node.get("$ref"), str) else []
        found += [branch for branch in node.get("oneOf") or () if isinstance(branch, dict)]
        return found + ([node["not"]] if isinstance(node.get("not"), dict) else [])

    def deeper(node: dict) -> list:
        found = [child for keyword in ("properties", "patternProperties", "$defs")
                 for child in (node.get(keyword) or {}).values() if isinstance(child, dict)]
        return found + [node[keyword] for keyword in ("items", "propertyNames") if isinstance(node.get(keyword), dict)]

    def cycles(start: dict) -> bool:
        path, stack = set(), [(start, iter(same_level(start)))]
        path.add(id(start))
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                path.discard(id(node))
                stack.pop()
            elif id(child) in path:
                return True
            else:
                path.add(id(child))
                stack.append((child, iter(same_level(child))))
        return False

    seen, pending = set(), [root]
    while pending:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if cycles(node):
            return True
        pending += same_level(node) + deeper(node)
    return False


def _checked_answer(entry: dict, question: str, value, *, text: bool):
    """The value of an answer checked against the ``answer_schema`` of the question. A free text is JSON unless the schema
    asks for a string (``ANSWER_INVALID`` when it is not); a schema outside the closed profile is not applied: the answer
    is taken and ``answer_schema_ignored`` says why."""
    answer_schema = entry["answer_schema"]
    problem = _answer_schema_problem(answer_schema)
    if problem:
        entry["answer_schema_ignored"] = problem
        return value
    entry.pop("answer_schema_ignored", None)
    original = value
    types = answer_schema.get("type")
    types = [types] if isinstance(types, str) else types or []
    if text and value is not None and types != ["string"]:
        try:
            value = json.loads(value)
        except ValueError:
            if "string" not in types:
                raise QuestionError("ANSWER_INVALID", f"the answer to {question} must be JSON for its answer_schema "
                                    f"(type {'/'.join(types) or 'any'}): {value[:60]!r}") from None
    try:
        issues = schema.validate_node(_answer_registry(answer_schema), answer_schema, _ANSWER_ID, value)
    except RecursionError:  # a $ref cycle that consumes no part of the value (``{"$ref": "#"}``)
        entry["answer_schema_ignored"] = "answer_schema: a $ref cycle never reaches a check"
        return original
    if issues:
        raise QuestionError("ANSWER_INVALID", f"the answer to {question} does not match its answer_schema: "
                            + "; ".join(issue.message for issue in issues[:3]))
    return value


def listing(directory: Path, now: float, default_warn_s: int = DEFAULT_WARN_S, invalid: Optional[list] = None) -> list:
    """Open questions of the run in ``directory``: ``[{item, id, revision, text, age_s, overdue}]``. A ``questions.json``
    that is not valid is skipped with a ``QUESTIONS_INVALID`` line on stderr (and its message added to ``invalid``)."""
    rows = []
    for file in sorted(Path(directory).glob(f"*/{FILE}")):
        try:
            doc = read(file.parent)
        except QuestionsInvalid as error:
            print(f"QUESTIONS_INVALID: {error.message} (skipped)", file=sys.stderr)
            if invalid is not None:
                invalid.append(error.message)
            continue
        if doc is None:
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
    """``limits.question_warn_s`` of the piece (``options.json``); ``default`` when it is not there or not readable."""
    try:
        options = records.read(Path(item_directory) / "options.json", "item-options") or {}
    except (OSError, Stop):
        return default
    return int((((options.get("options") or {}).get("limits") or {}).get("question_warn_s", default)))
