"""The write path shared by the settings commands (settings §A.7.1-A.7.6).

``WriteSession`` binds one command to its unit of work: the target scope, the registry of ``ctx.config``, a
``Preview`` of the target and the actor's ``Rights``, confirmed in this unit of work (the base right on
creation, the lock and key rights once the change is known). A command first decides everything (domain rules,
R14 on the candidate); only then ``persist`` writes the entries conditionally on the versions read, takes
**one** ``generation`` and appends the history of every step, so a refused command writes nothing and a
failure after the first write rolls the whole unit of work back. ``EntryWrite`` is one entry's change as
domain steps: a value change and a lock change of the same entry are two steps, two history records and
``row_version + 2``, saved in one conditional update.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, Self, cast

from skm.application_bus.context import CommandContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.domain.entry import (
    ConfigEntry,
    ConfigEntryId,
    EntryOp,
    change_entry,
    new_entry,
    same_value,
    set_lock,
)
from skm.modules.settings.domain.events import ConfigChanged, ConfigLocked, ConfigUnlocked, EntryChangeKind
from skm.modules.settings.domain.history import ChangeKind, history_record
from skm.modules.settings.domain.write_rules import (
    Problem,
    WriteAction,
    WriteContext,
    WriteRequest,
    required_permissions,
)
from skm.modules.settings.generated.views import (
    EffectiveKeyView,
    EffectiveKeyViewDefsLayerRef,
    EntryView,
    EntryViewDefsScopeRef,
)
from skm.modules.settings.ports import ConfigEntryRepository, ConfigGenerationCounter, ConfigHistoryRepository
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import MISSING, Chain, KeySpec, copy_json
from skm.platform.config.layers import Contribution, LayerRef
from skm.platform.config.merge import KeyResolution
from skm.platform.config.secrets import mask_secret_refs
from skm.platform.config.store import PackConfigSource

from .preview import Preview, RegistryChecks, chain_kind, contribution_of
from .project_keys import require_project_key
from .rights import Rights, base_permission
from .scopes import ScopeRefDto, Target, resolve_target_scope

__all__ = [
    "EntryWrite",
    "WriteSession",
    "candidate_problems",
    "effective_view",
    "entry_view",
    "layer_view",
    "raise_problems",
    "safe_value",
]

type Step = tuple[ChangeKind, ConfigEntry | None, ConfigEntry | None]


def safe_value(spec: KeySpec | None, value: JsonValue) -> JsonValue:
    """A plain JSON copy as results may show it (resolutions hold frozen values): SecretRef strings stay,
    rejected secret literals are masked."""
    plain = copy_json(value, "value")
    return plain if spec is None else mask_secret_refs(plain, spec.value_schema)


class _LayerRefView(Protocol):
    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Self: ...


def layer_view[T: _LayerRefView](view: type[T], ref: LayerRef | None) -> T | None:
    return None if ref is None else view.from_json(ref.to_json())


def entry_view(entry: ConfigEntry, label: str, spec: KeySpec | None = None) -> EntryView:
    level = entry.scope.kind.value
    return EntryView(
        entry_id=entry.id,
        scope=EntryViewDefsScopeRef(level=level, scope_id=entry.scope.id, label=label or None),
        key=entry.key,
        op=entry.op.value,
        locked=entry.locked,
        row_version=entry.row_version,
        updated_at=entry.updated_at,
        updated_by=entry.updated_by,
        value=None if entry.op is EntryOp.UNSET else safe_value(spec, entry.value),
        reason=entry.reason,
    )


def effective_view(resolution: KeyResolution, spec: KeySpec) -> EffectiveKeyView:
    present = resolution.value is not MISSING
    return EffectiveKeyView(
        key=resolution.key,
        present=present,
        value=safe_value(spec, cast("JsonValue", resolution.value)) if present else None,
        winner=layer_view(EffectiveKeyViewDefsLayerRef, resolution.winner),
        locked_by=layer_view(EffectiveKeyViewDefsLayerRef, resolution.locked_by),
    )


def candidate_problems(candidate: EffectiveConfig, keys: Sequence[str]) -> list[Problem]:
    """R14: changed keys the candidate holds invalid (a section validator, the merged value, a missing
    required value). Each validator is reported once."""
    problems: list[Problem] = []
    seen: set[str] = set()
    invalid = candidate.invalid_keys()
    for key in keys:
        found = invalid.get(key)
        if found is None:
            continue
        if found.validator is not None:
            if found.validator in seen:
                continue
            seen.add(found.validator)
            spec = candidate.registry.section(candidate.registry.spec(key).section)
            declared = next(item for item in spec.validators if item.id == found.validator)
            details: JsonObject = {
                "validator": found.validator,
                "keys": list(declared.keys),
                "message": found.message,
            }
            if found.blocked_by:
                details["blocked_by"] = list(found.blocked_by)
            code = (
                ErrorCode.SCHEMA_INVALID
                if found.validator == "exports.notes_ttl_order" and not found.blocked_by
                else ErrorCode.CONFIG_INVALID
            )
            problems.append(Problem("R14", code.value, found.message, key=key, details=details))
        else:
            details = {"key": key, "reason": found.reason}
            if found.issues:
                details["issues"] = list(cast("list[JsonValue]", list(found.issues)))
            problems.append(Problem("R14", "CONFIG_INVALID", found.message, key=key, details=details))
    return problems


def raise_problems(problems: Sequence[Problem]) -> None:
    """Raise the first R14 problem of a single write with its validation code."""
    if problems:
        first = problems[0]
        raise ValidationFailed(ErrorCode(first.code), first.message, details=dict(first.details))


def _changes_lock(request: WriteRequest, existing: ConfigEntry | None) -> bool:
    """Whether ``request`` sets or clears a lock or removes a locked entry (the cases of R13)."""
    if request.action in ("lock", "unlock"):
        return True
    if request.action == "remove":
        return existing is not None and existing.locked
    return request.locked is not None and request.locked != (existing is not None and existing.locked)


@dataclass(frozen=True, slots=True)
class EntryWrite:
    """One entry's change: ``before`` as read, ``after`` as saved (``None`` = removed), the domain steps."""

    key: str
    before: ConfigEntry | None
    after: ConfigEntry | None
    steps: tuple[Step, ...]

    @property
    def change(self) -> EntryChangeKind:
        if self.before is None:
            return "created"
        if self.after is None:
            return "removed"
        if self.after.op != self.before.op or not same_value(self.after.value, self.before.value):
            return "updated"
        return "lock_changed"

    @property
    def lock_step(self) -> ChangeKind | None:
        """``LOCKED``/``UNLOCKED`` when the stored entry's lock flag changes (a new locked entry locks);
        a removal has no lock event of its own."""
        if self.after is None:
            return None
        was = self.before is not None and self.before.locked
        if was == self.after.locked:
            return None
        return ChangeKind.LOCKED if self.after.locked else ChangeKind.UNLOCKED


class WriteSession:
    """One settings command inside its unit of work."""

    def __init__(
        self, ctx: CommandContext, uow: UnitOfWork, scope: ScopeRefDto | None, *, reason: str
    ) -> None:
        self.ctx = ctx
        self.uow = uow
        self.reason = reason
        self.target: Target = resolve_target_scope(uow, scope, ctx.scope_chain)
        self.rights = Rights(ctx, uow)
        self.rights.require(base_permission(self.target.scope.kind.value))  # before anything is read
        self.registry = ctx.config.registry
        self.preview = Preview(uow, self.registry, uow.repo(PackConfigSource), self.target.ref)
        self.entries = uow.repo(ConfigEntryRepository)
        self.history = uow.repo(ConfigHistoryRepository)
        self.counter = uow.repo(ConfigGenerationCounter)

    # ------------------------------------------------------------------ decisions
    def context(self, request: WriteRequest, existing: ConfigEntry | None) -> WriteContext:
        """The rule context of ``request``; ``granted`` holds the rights this change needs (base, lock, key
        right) that the actor holds, confirmed now that the stored entry is known, ``refused`` the reason of
        each decision that refused one of them."""
        spec = self.registry.find(request.key)
        if spec is None:
            return WriteContext(None, existing, None, frozenset())
        needed = required_permissions(
            self.target.scope.kind.value, spec, lock_change=_changes_lock(request, existing)
        )
        granted = self.rights.confirmed(needed)
        refused = self.rights.refusals(needed)
        if request.action != "write":
            return WriteContext(spec, existing, None, granted, refused=refused)
        return WriteContext(
            spec,
            existing,
            self.preview.farther(spec),
            granted,
            RegistryChecks(self.registry, spec),
            refused=refused,
        )

    def request(self, key: str, *, action: WriteAction, **fields: Any) -> WriteRequest:
        require_project_key(key)
        values: dict[str, Any] = {"op": None, "value": None, "locked": None, "expected_row_version": None}
        values.update(fields)
        return WriteRequest(scope=self.target.scope, key=key, action=action, **values)

    def candidate(
        self, writes: Mapping[str, ConfigEntry | None], *, keys: Sequence[str] = ()
    ) -> dict[Chain, EffectiveConfig]:
        """Candidates of the target per chain kind with ``writes`` applied (``None`` = entry removed), for
        the sections of ``writes`` and ``keys``."""
        by_kind: dict[Chain, dict[str, Contribution | None]] = {}
        for key, entry in writes.items():
            spec = self.registry.find(key)
            if spec is None:
                continue
            override = None if entry is None else contribution_of(self.target.ref, entry)
            by_kind.setdefault(chain_kind(self.target.ref.level, spec), {})[key] = override
        for key in keys:
            spec = self.registry.find(key)
            if spec is not None:
                by_kind.setdefault(chain_kind(self.target.ref.level, spec), {})
        return {
            kind: self.preview.candidate(kind, overrides, keys=[key for key in keys if key not in overrides])
            for kind, overrides in by_kind.items()
        }

    def build(
        self, key: str, existing: ConfigEntry | None, *, op: EntryOp, value: JsonValue | None, locked: bool
    ) -> EntryWrite | None:
        """The steps that turn ``existing`` into ``(op, value, locked)``; ``None`` when nothing changes."""
        actor, now = self.ctx.actor.principal_id, self.ctx.clock.now()
        if existing is None:
            created = new_entry(
                entry_id=ConfigEntryId(self.ctx.ids.new_id()),
                scope=self.target.scope,
                key=key,
                op=op,
                value=value,
                locked=locked,
                reason=self.reason,
                actor=actor,
                now=now,
            )
            return EntryWrite(key, None, created, ((ChangeKind.CREATED, None, created),))
        steps: list[Step] = []
        current = existing
        if existing.op != op or not same_value(existing.value, value):
            changed = change_entry(current, op=op, value=value, reason=self.reason, actor=actor, now=now)
            steps.append((ChangeKind.UPDATED, current, changed))
            current = changed
        if existing.locked != locked:
            kind = ChangeKind.LOCKED if locked else ChangeKind.UNLOCKED
            relocked = set_lock(current, locked=locked, reason=self.reason, actor=actor, now=now)
            steps.append((kind, current, relocked))
            current = relocked
        return EntryWrite(key, existing, current, tuple(steps)) if steps else None

    @staticmethod
    def removal(existing: ConfigEntry) -> EntryWrite:
        return EntryWrite(existing.key, existing, None, ((ChangeKind.REMOVED, existing, None),))

    # ------------------------------------------------------------------ the write
    def persist(self, writes: Sequence[EntryWrite]) -> int:
        """Write every entry conditionally on the version read, one generation, the history of each step."""
        for write in writes:
            if write.before is None:
                self.entries.add(cast("ConfigEntry", write.after))
            elif write.after is None:
                self.entries.remove(write.before.id, expected_version=write.before.row_version)
            else:
                self.entries.save(write.after, expected_version=write.before.row_version)
        generation = self.counter.increment()
        now = self.ctx.clock.now()
        for write in writes:
            for kind, before, after in write.steps:
                self.history.append(
                    history_record(
                        record_id=self.ctx.ids.new_id(),
                        before=before,
                        after=after,
                        kind=kind,
                        actor=self.ctx.actor.principal_id,
                        request_id=self.ctx.meta.request_id,
                        reason=self.reason,
                        generation=generation,
                        now=now,
                    )
                )
        return generation

    def record_changed(self, writes: Sequence[EntryWrite], generation: int) -> None:
        """``ConfigChanged`` for all writes, then ``ConfigLocked``/``ConfigUnlocked`` per lock step."""
        target = self.target
        self.uow.record(
            ConfigChanged(
                scope=target.scope,
                workspace_id=target.workspace_id,
                changes={write.key: write.change for write in writes},
                generation=generation,
            )
        )
        self.record_locks(writes, generation)

    def record_locks(self, writes: Sequence[EntryWrite], generation: int) -> None:
        target = self.target
        for write in sorted(writes, key=lambda item: item.key):
            kind = write.lock_step
            if kind is ChangeKind.LOCKED:
                self.uow.record(ConfigLocked(target.scope, target.workspace_id, write.key, generation))
            elif kind is ChangeKind.UNLOCKED:
                self.uow.record(ConfigUnlocked(target.scope, target.workspace_id, write.key, generation))
