"""The runtime records of the conductor (``schemas/records/v1``): the documents a run keeps on disk, checked against their
schema when they are written and when they are read.

Each kind has one tag carrier (``TAGS``): ``$schema`` with ``urn:swissknifeman:orch:records:<kind>:v1``, or ``schema``
with the short tag already published for the five short kinds (``SHORT_TAGS``: review-verdict, provider-gates,
observer-report, prompt-diff, conformance-report). A document read back carries the tag of its kind (v1),
no tag at all (v0: written before records/v1; ``migrate_v0`` adds the carrier in memory, the file is not rewritten), or
something else (another value, the carrier of another kind, both carriers): ``unknown or conflicting record tag``.

Errors are stops of the run: bytes that are not JSON are ``STATE_CORRUPT``; a document that does not match its schema is
``RUN_INVALID`` (run), ``STATE_INVALID`` (state), ``QUESTIONS_INVALID`` (questions) or ``RECORD_INVALID`` (any other
kind), with the path, the JSON pointer and the message of the first three problems.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from aicore.util import docio, schema

from orch.conductor.domain.stop import Stop

# orch.settings imports the questions of the conductor, which write through this module: the root is computed here
CONTRACT_DIR = Path(__file__).resolve().parents[3] / "schemas" / "records" / "v1"
URN_PREFIX = "urn:swissknifeman:orch:records:"
KINDS = ("agent-request", "agent-result", "agent-usage", "conformance-report", "item-options", "item-routes", "lease",
         "observer-report", "process", "prompt-diff", "provider-gates", "questions", "review-strategy", "review-verdict",
         "risk", "run", "state")
# The five short kinds keep the tag they already publish, in the field ``schema``.
SHORT_TAGS = {
    "review-verdict": "orch-conductor-review-verdict/v1",
    "provider-gates": "provider-gates/v1",
    "observer-report": "orch-conductor-observer/v1",
    "prompt-diff": "prompt-diff/v1",
    "conformance-report": "orch-conformance/v1",
}
# kind -> (carrier, value)
TAGS = {kind: ("schema", SHORT_TAGS[kind]) if kind in SHORT_TAGS else ("$schema", f"{URN_PREFIX}{kind}:v1")
        for kind in KINDS}
CARRIERS = ("$schema", "schema")
CODES = {"run": "RUN_INVALID", "state": "STATE_INVALID", "questions": "QUESTIONS_INVALID"}
HINT = "settle or release the items of this run, or start a new run"
# A report or command output the conductor builds itself that does not match its schema is a defect, not a run to settle
WRITER_HINT = "the conductor built a document outside its contract; report this defect"
TAG_CONFLICT = "unknown or conflicting record tag"
# Keys renamed since the documents of v0 were written: kind -> {old: new}. Filled only from facts; none so far.
_V0_RENAMES: dict = {}
_REGISTRY: list = []


class _TagConflict(Exception):
    def __init__(self, carrier: str):
        super().__init__(carrier)
        self.carrier = carrier


def registry() -> schema.Registry:
    if not _REGISTRY:
        found, kinds = schema.load_contract_set(CONTRACT_DIR)
        if tuple(kinds) != KINDS:
            raise schema.SchemaProfileError(f"records/v1 holds {kinds}, expected {list(KINDS)}")
        _REGISTRY.append(found)
    return _REGISTRY[0]


def code(kind: str) -> str:
    """The reason code of an invalid document of ``kind``."""
    return CODES.get(kind, "RECORD_INVALID")


def _known(kind: str) -> None:
    if kind not in KINDS:
        raise schema.SchemaProfileError(f"unknown records kind: {kind!r}")


def tag_state(kind: str, doc: Any) -> str:
    """``v1`` (the carrier of ``kind`` with its value, and not the other carrier), ``v0`` (no carrier at all; also a
    document that is not an object) or ``conflict``."""
    carrier, value = TAGS[kind]
    if not isinstance(doc, dict) or not any(name in doc for name in CARRIERS):
        return "v0"
    other = next(name for name in CARRIERS if name != carrier)
    return "v1" if doc.get(carrier) == value and other not in doc else "conflict"


def migrate_v0(kind: str, doc: Any) -> Any:
    """A copy of a v0 document of ``kind`` in the shape of v1: the carrier of its kind (short kinds get ``schema``,
    never ``$schema``) and the renamed keys of ``_V0_RENAMES``. Not an object: returned as it is (the schema says why)."""
    if not isinstance(doc, dict):
        return doc
    carrier, value = TAGS[kind]
    found = {carrier: value, **doc}
    for old, new in _V0_RENAMES.get(kind, {}).items():
        if old in found and new not in found:
            found[new] = found.pop(old)
    if kind == "item-options" and isinstance(found.get("options"), dict):
        found["options"] = options_layer(found["options"])  # v0 kept the merged skills map
    return found


def options_layer(options: dict) -> dict:
    """The effective options of a piece as the run-options document ``options.json`` keeps: the merged ``skills`` map
    (role -> names) becomes the run-options list ``[{role, names}]``, so the record is a layer that gives the same
    options again. Anything else is kept as it is."""
    skills = options.get("skills")
    if not isinstance(skills, dict):
        return options
    return {**options, "skills": [{"role": role, "names": list(names)} for role, names in sorted(skills.items())]}


def options_effective(options: dict) -> dict:
    """The effective options of a piece from its ``options.json`` (``options_layer`` undone: ``skills`` by role)."""
    skills = options.get("skills")
    if not isinstance(skills, list):
        return options
    return {**options, "skills": {entry["role"]: list(entry["names"]) for entry in skills if isinstance(entry, dict)}}


def stamp(kind: str, doc: Any) -> Any:
    """``doc`` with the carrier of ``kind``: the document itself when it has it, else a shallow copy that adds it (the
    caller's object is not changed: a dict of routes must not grow a ``$schema`` role)."""
    if tag_state(kind, doc) == "v1" or not isinstance(doc, dict):
        return doc
    if tag_state(kind, doc) == "conflict":
        raise _TagConflict(next(name for name in CARRIERS if name in doc))
    return migrate_v0(kind, doc)


def _migrator(kind: str):
    def migrate(doc: Any) -> Any:
        state = tag_state(kind, doc)
        if state == "conflict":
            raise _TagConflict(next(name for name in CARRIERS if name in doc))
        return migrate_v0(kind, doc) if state == "v0" else doc
    return migrate


def problems(doc: object, kind: str) -> list[str]:
    """Violations of ``records/v1`` ``kind`` by ``doc`` as ``pointer: message`` lines (empty when valid); the tag is
    read as ``read`` reads it (a v0 document is checked after ``migrate_v0``)."""
    _known(kind)
    try:
        found = _migrator(kind)(doc)
    except _TagConflict as conflict:
        return [f"/{conflict.carrier}: {TAG_CONFLICT}"]
    return [issue.message for issue in schema.validate(found, kind, registry())]


def _invalid(kind: str, path, lines: list, hint: str = HINT) -> Stop:
    return Stop(code(kind), f"{path}: {'; '.join(lines[:3])}; {hint}")


def check(doc: Any, kind: str, where, *, hint: str = HINT) -> Any:
    """``doc`` of ``kind`` as ``read`` gives it back (a v0 one after ``migrate_v0``, a v1 one itself), for a document
    the caller parsed or built itself (a file it opens its own way, a report it prints); ``<KIND CODE>`` naming
    ``where``, the pointers and ``hint`` when it does not match."""
    _known(kind)
    try:
        found = _migrator(kind)(doc)
    except _TagConflict as conflict:
        raise _invalid(kind, where, [f"/{conflict.carrier}: {TAG_CONFLICT}"], hint) from None
    issues = schema.validate(found, kind, registry())
    if issues:
        raise _invalid(kind, where, [issue.message for issue in issues], hint)
    return found


def read(path: Path, kind: str) -> Optional[dict]:
    """The document of ``kind`` at ``path`` checked against its schema (a v0 one after ``migrate_v0``, in memory only);
    ``None`` when there is none. ``STATE_CORRUPT`` for bytes that are not JSON, ``<KIND CODE>`` for a mismatch."""
    _known(kind)
    try:
        return docio.read_document(path, kind=kind, registry=registry(), migrate=_migrator(kind))
    except docio.DocumentCorrupt as error:
        raise Stop("STATE_CORRUPT", f"{path} is not JSON ({error.error}): restore it from the run's progress.jsonl or "
                   "remove the run folder and start again") from None
    except docio.DocumentInvalid as error:
        raise _invalid(kind, path, [str(getattr(issue, "message", issue)) for issue in error.issues]) from None
    except _TagConflict as conflict:
        raise _invalid(kind, path, [f"/{conflict.carrier}: {TAG_CONFLICT}"]) from None


def write(path: Path, doc: Any, kind: str) -> Path:
    """Write ``doc`` as a v1 document of ``kind`` (its carrier added when missing), checked first and replaced
    crash-safely (``0600``); an invalid document stops with the code of its kind and leaves the file as it was."""
    _known(kind)
    try:
        docio.write_document(path, stamp(kind, doc), kind=kind, registry=registry(), mode=0o600)
    except docio.DocumentInvalid as error:
        raise _invalid(kind, path, [str(getattr(issue, "message", issue)) for issue in error.issues]) from None
    except _TagConflict as conflict:
        raise _invalid(kind, path, [f"/{conflict.carrier}: {TAG_CONFLICT}"]) from None
    return Path(path)
