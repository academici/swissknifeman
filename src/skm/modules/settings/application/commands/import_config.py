"""``settings.import_config`` (settings §A.7.6): a whole document of entries of one scope, all or nothing.

Before anything is written the handler collects **every** problem: parse problems of the document
(unknown keys, conflicting operations, a foreign ``schema``), the domain rules of each change
(``collect_write_problems``, R1-R13/R16) and R14 on the candidate of the target with all valid changes
applied. ``expected_entries_digest`` is a CAS over all entries of the scope (``entries_digest``). The result
shows the entry changes, the ``effective_diff`` of the affected sections and the digest the entries have
after the import (predicted for a dry run). A dry run writes nothing; with problems nothing is written either
(``CONFIG_INVALID`` with every problem; raised from a ``Forbidden`` when a right is missing, so the bus audits
the denial); otherwise every change is written in this unit of work with **one**
generation, the history of each step and one ``ConfigChanged`` (plus a lock event per lock change). A
document equal to the stored entries (export → import) writes nothing and keeps the generation.

Absent document keys leave their entries alone in ``merge`` mode and are removed in ``replace`` mode;
``unset`` stores the reset to the default, which is different from removing the entry.
"""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.project_keys import MACHINE_ONLY_KEYS, project_keys, require_project_key
from skm.modules.settings.application.rights import BASE_PERMISSION, write_permissions
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.application.write_flow import (
    EntryWrite,
    WriteSession,
    candidate_problems,
    safe_value,
)
from skm.modules.settings.domain.digest import entries_digest
from skm.modules.settings.domain.entry import KEY_PATTERN, ConfigEntry, EntryOp, same_value
from skm.modules.settings.domain.import_plan import ChangeType, EntryChange, EntryState, plan_import
from skm.modules.settings.domain.write_rules import Problem, collect_write_problems
from skm.modules.settings.generated.commands import ImportConfig
from skm.modules.settings.generated.results import (
    ImportConfigResult,
    ImportConfigResultChangesItem,
    ImportConfigResultEffectiveDiffItem,
    ImportConfigResultProblemsItem,
)
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import MISSING, Chain
from skm.platform.config.sources.document import ConfigDocument, decode_document, parse_document

__all__ = ["DOCUMENT_MAX_BYTES", "SPEC", "handle"]

DOCUMENT_MAX_BYTES = 1048576
_SPECIAL = frozenset({"schema", "unset", "lock", "append"})


def _document_size(cmd: ImportConfig) -> int:
    """Bytes of the document: UTF-8 of a TOML/JSON string, compact UTF-8 JSON of an object (§A.7.6)."""
    if isinstance(cmd.document, str):
        return len(cmd.document.encode("utf-8", errors="surrogatepass"))
    return len(json.dumps(cmd.document, separators=(",", ":"), ensure_ascii=False, default=str).encode())


def _document_names(cmd: ImportConfig) -> tuple[set[str], bool]:
    """Every dotted path the document mentions (a superset of its keys) and whether it locks keys; an
    oversized document is not parsed (the handler refuses it)."""
    if _document_size(cmd) > DOCUMENT_MAX_BYTES:
        return set(), False
    try:
        data = decode_document(cast("str | Mapping[str, object]", cmd.document), cmd.format)
    except (ValueError, TypeError, RecursionError):
        return set(), False
    names: set[str] = set()
    pending: list[tuple[str, JsonValue]] = [
        (name, value) for name, value in data.items() if name not in _SPECIAL
    ]
    while pending:
        path, value = pending.pop()
        names.add(path)
        if isinstance(value, dict):
            pending.extend((f"{path}.{name}", item) for name, item in value.items())
    for field in ("unset", "lock"):
        listed = data.get(field)
        if isinstance(listed, list):
            names.update(item for item in listed if isinstance(item, str))
    append = data.get("append")
    if isinstance(append, dict):
        names.update(append)
    locks = data.get("lock")
    return names, isinstance(locks, list) and bool(locks)


def permissions_of(cmd: ImportConfig) -> tuple[str, ...]:
    names, locks = _document_names(cmd)
    return write_permissions(cmd.scope.level, sorted(names), lock_change=locks)


def _state_json(state: EntryState | None, session: WriteSession, key: str) -> JsonValue:
    if state is None:
        return None
    op, value, locked = state
    document: JsonObject = {"op": op.value, "locked": locked}
    if op is not EntryOp.UNSET:
        document["value"] = safe_value(session.registry.find(key), value)
    return document


def _problem_item(problem: Problem) -> ImportConfigResultProblemsItem:
    key = problem.key if problem.key is not None and KEY_PATTERN.fullmatch(problem.key) else None
    return ImportConfigResultProblemsItem(
        code=problem.code, message=problem.message, key=key, pointer=problem.pointer
    )


def _denial(problems: list[Problem]) -> Forbidden | None:
    """The first right the import lacks (R13/R16) as the ``Forbidden`` its ``CONFIG_INVALID`` is raised from:
    the bus audits it as denied; any other problem is a validation failure only."""
    denied = next((item for item in problems if item.code == ErrorCode.FORBIDDEN.value), None)
    if denied is None:
        return None
    return Forbidden(ErrorCode.FORBIDDEN, denied.message, details=dict(denied.details))


def _parse(cmd: ImportConfig, session: WriteSession) -> tuple[ConfigDocument, list[Problem]]:
    """The parsed document and its parse problems (§B.11.4); a document over 1 MiB (UTF-8 bytes of a string,
    compact JSON of an object) is refused in a dry run and an apply alike."""
    size = _document_size(cmd)
    if size > DOCUMENT_MAX_BYTES:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"the document takes {size} bytes, at most {DOCUMENT_MAX_BYTES}",
            details={"reason": "document_too_large"},
        )
    document = parse_document(cast("str | Mapping[str, object]", cmd.document), cmd.format, session.registry)
    for key in (*document.entries, *sorted(document.locks), *(problem.key for problem in document.problems)):
        require_project_key(key)
    problems = [
        Problem("document", item.code, f"{item.message}: {item.reason}", key=item.key or None)
        for item in document.problems
    ]
    return document, problems


def _decide(
    session: WriteSession, change: EntryChange, existing: ConfigEntry | None, confirmed: bool
) -> tuple[list[Problem], EntryWrite | None]:
    """Rule problems of one planned change, else its entry write."""
    key = change.key
    if change.change is ChangeType.REMOVED:
        request = session.request(key, action="remove", confirmed=confirmed)
        problems = collect_write_problems(request, session.context(request, existing))
        return list(problems), None if problems else session.removal(cast("ConfigEntry", existing))
    op, value, locked = cast("EntryState", change.after)
    if change.change is ChangeType.LOCK_CHANGED:
        request = session.request(key, action="lock" if locked else "unlock", confirmed=confirmed)
        context = session.context(request, existing)
    else:
        request = session.request(key, action="write", op=op, value=value, locked=locked, confirmed=confirmed)
        context = session.context(request, existing)
    problems = collect_write_problems(request, context)
    if problems:
        return list(problems), None
    return [], session.build(key, existing, op=op, value=value, locked=locked)


def _effective_diff(
    session: WriteSession, before: Mapping[Chain, EffectiveConfig], after: Mapping[Chain, EffectiveConfig]
) -> list[ImportConfigResultEffectiveDiffItem]:
    items: dict[str, ImportConfigResultEffectiveDiffItem] = {}
    for kind, candidate in after.items():
        current = before.get(kind)
        for key in candidate.resolved_keys():
            if key in MACHINE_ONLY_KEYS:
                continue
            new = candidate.resolution(key).value
            old = (
                MISSING
                if current is None or key not in current.resolved_keys()
                else current.resolution(key).value
            )
            if (old is MISSING) == (new is MISSING) and (
                old is MISSING or same_value(cast("JsonValue", old), cast("JsonValue", new))
            ):
                continue
            spec = session.registry.find(key)
            items[key] = ImportConfigResultEffectiveDiffItem(
                key=key,
                before=None if old is MISSING else safe_value(spec, cast("JsonValue", old)),
                after=None if new is MISSING else safe_value(spec, cast("JsonValue", new)),
            )
    return [items[key] for key in sorted(items)]


def handle(cmd: ImportConfig, ctx: CommandContext, uow: UnitOfWork) -> ImportConfigResult:
    session = WriteSession(ctx, uow, cmd.scope, reason=cmd.reason)
    target = session.target
    document, problems = _parse(cmd, session)
    current = project_keys(session.entries.entries_of_scope(target.scope.id, for_update=True))
    digest_before = entries_digest(current)
    expected = cmd.expected_entries_digest
    if expected is not None and expected != digest_before:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "the entries of the scope changed since the expected digest",
            details={"expected": expected, "actual": digest_before},
        )
    plan = plan_import(current, document, mode=cmd.mode)
    writes: list[EntryWrite] = []
    for change in plan.effective:
        found, write = _decide(session, change, current.get(change.key), cmd.confirmed)
        problems.extend(found)
        if write is not None:
            writes.append(write)
    overrides = {write.key: write.after for write in writes}
    keys = [change.key for change in plan.effective]
    before = session.candidate({}, keys=keys)
    after = session.candidate(overrides, keys=keys)
    for candidate in after.values():  # R14
        resolved = set(candidate.resolved_keys())
        problems.extend(candidate_problems(candidate, [key for key in overrides if key in resolved]))
    predicted = {key: entry for key, entry in current.items() if key not in overrides}
    predicted.update({key: entry for key, entry in overrides.items() if entry is not None})
    preview = ImportConfigResult(
        dry_run=cmd.dry_run,
        applied=False,
        changes=tuple(
            ImportConfigResultChangesItem(
                key=change.key,
                change=change.change.value,
                before=_state_json(change.before, session, change.key),
                after=_state_json(change.after, session, change.key),
            )
            for change in plan.changes
        ),
        effective_diff=tuple(_effective_diff(session, before, after)),
        problems=tuple(_problem_item(problem) for problem in problems),
        entries_digest_before=digest_before,
        entries_digest_after=entries_digest(predicted),
        generation=None,
    )
    if cmd.dry_run:
        return preview
    if problems:
        code = (
            ErrorCode.SCHEMA_INVALID
            if all(
                item.code == ErrorCode.SCHEMA_INVALID.value
                and item.details.get("validator") == "exports.notes_ttl_order"
                for item in problems
            )
            else ErrorCode.CONFIG_INVALID
        )
        raise ValidationFailed(
            code,
            f"the document has {len(problems)} problem(s); nothing was written",
            details={"problems": [{**_problem_item(item).to_json(), "rule": item.rule} for item in problems]},
        ) from _denial(problems)
    if not writes:  # the document equals the stored entries: nothing to write
        generation = session.counter.current()
    else:
        generation = session.persist(writes)
        session.record_changed(writes, generation)
    digest_after = entries_digest(project_keys(session.entries.entries_of_scope(target.scope.id)))
    return replace(preview, applied=True, entries_digest_after=digest_after, generation=generation)


SPEC = CommandSpec(
    name="settings.import_config",
    dto=ImportConfig,
    result=ImportConfigResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
