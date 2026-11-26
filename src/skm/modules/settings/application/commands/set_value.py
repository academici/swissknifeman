"""``settings.set_value`` (settings §A.7.1); ``write_value`` is shared with ``settings.unset_value`` (§A.7.2).

Order: target scope, entry read for update, farther resolution, domain rules R1-R13/R16 (first violation),
R15 no-op (nothing written, no history, event or generation), the new entry steps, R14 on the candidate
config of the target, then the conditional write, one generation, history and events.
"""

from typing import cast

from skm.application_bus.context import CommandContext
from skm.application_bus.registry import CommandSpec
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.preview import chain_kind
from skm.modules.settings.application.rights import BASE_PERMISSION, write_permissions
from skm.modules.settings.application.scopes import bus_scope_of
from skm.modules.settings.application.write_flow import (
    WriteSession,
    candidate_problems,
    effective_view,
    entry_view,
    raise_problems,
)
from skm.modules.settings.domain.entry import ConfigEntry, EntryOp
from skm.modules.settings.domain.write_rules import check_write
from skm.modules.settings.generated.commands import SetValue, UnsetValue
from skm.modules.settings.generated.results import SetValueResult
from skm.modules.settings.generated.views import EffectiveKeyView, EntryView

__all__ = ["SPEC", "handle", "write_value"]


def permissions_of(cmd: SetValue) -> tuple[str, ...]:
    return write_permissions(cmd.scope.level, (cmd.key,), lock_change=cmd.locked is not None)


def write_value(
    cmd: SetValue | UnsetValue,
    ctx: CommandContext,
    uow: UnitOfWork,
    *,
    op: EntryOp,
    value: JsonValue | None,
    locked: bool | None,
) -> tuple[EntryView, bool, int, EffectiveKeyView]:
    """``(entry, changed, generation, effective)`` of a set, append or unset of one key."""
    session = WriteSession(ctx, uow, cmd.scope, reason=cmd.reason)
    key, target = cmd.key, session.target
    existing = session.entries.find(target.scope.id, key, for_update=True)
    request = session.request(
        key,
        action="write",
        op=op,
        value=value,
        locked=locked,
        expected_row_version=cmd.expected_row_version,
        confirmed=cmd.confirmed,
    )
    check_write(request, session.context(request, existing))  # R1-R13, R16
    spec = session.registry.spec(key)
    kind = chain_kind(target.ref.level, spec)
    wanted = locked if locked is not None else existing is not None and existing.locked
    write = session.build(key, existing, op=op, value=value, locked=wanted)
    if write is None:  # R15: the entry already holds this op, value and lock flag
        current = session.candidate({}, keys=(key,))[kind]
        entry = cast("ConfigEntry", existing)
        return (
            entry_view(entry, target.label, spec),
            False,
            session.counter.current(),
            effective_view(current.resolution(key), spec),
        )
    candidate = session.candidate({key: write.after})[kind]
    raise_problems(candidate_problems(candidate, (key,)))  # R14
    generation = session.persist((write,))
    session.record_changed((write,), generation)
    after = cast("ConfigEntry", write.after)
    return (
        entry_view(after, target.label, spec),
        True,
        generation,
        effective_view(candidate.resolution(key), spec),
    )


def handle(cmd: SetValue, ctx: CommandContext, uow: UnitOfWork) -> SetValueResult:
    op = EntryOp.APPEND if cmd.mode == "append" else EntryOp.SET
    entry, changed, generation, effective = write_value(
        cmd, ctx, uow, op=op, value=cmd.value, locked=cmd.locked
    )
    return SetValueResult(entry=entry, changed=changed, generation=generation, effective=effective)


SPEC = CommandSpec(
    name="settings.set_value",
    dto=SetValue,
    result=SetValueResult,
    permission=BASE_PERMISSION,
    scope_of=bus_scope_of(lambda cmd: cmd.scope),
    handler=handle,
    permissions_of=permissions_of,
)
