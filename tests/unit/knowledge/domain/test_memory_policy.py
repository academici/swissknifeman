from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.knowledge.domain.events import MemoryForgotten, MemoryRemembered
from skm.modules.knowledge.domain.memory_entry import (
    MemoryEntry,
    MemoryEntryId,
    MemoryState,
    expire,
    forget,
    new_entry,
    supersede,
)
from skm.modules.knowledge.domain.memory_kind import REJECTED_JOURNAL_KINDS, MemoryKind
from skm.modules.knowledge.domain.memory_policy import (
    check_handoff_replacement,
    check_limits,
    is_live,
    rejection_reason,
    ttl_for,
    validate_memory_write,
)
from skm.modules.knowledge.domain.memory_scope import (
    MemoryScope,
    MemoryScopeKind,
    allowed_scopes,
    ensure_scope_allowed,
    recall_scopes,
    require_project_scope,
    scope_lock_key,
)
from skm.modules.knowledge.generated.settings import KnowledgeMemorySettings
from support.registries import schemas, settings_registry

_WORKSPACE = WorkspaceId(UUID(int=1))
_PROJECT = MemoryScope(MemoryScopeKind.PROJECT, ScopeId(UUID(int=2)), None, _WORKSPACE)
_GLOBAL = MemoryScope(MemoryScopeKind.GLOBAL, None, None, None)
_SETTINGS = KnowledgeMemorySettings.from_settings(
    {spec.key: spec.default for spec in settings_registry().keys(section="knowledge")}
)


def _entry(
    clock: FrozenClock, kind: MemoryKind = MemoryKind.FACT, *, requested_hours: float | None = None
) -> MemoryEntry:
    now = clock.now()
    return new_entry(
        entry_id=MemoryEntryId(UUID(int=3)),
        scope=_PROJECT,
        kind=kind,
        body="  The runner is offline.  ",
        created_at=now,
        expires_at=now + ttl_for(kind, requested_hours, _SETTINGS),
        created_by=PrincipalId(UUID(int=4)),
        writer="human",
        source="cli",
    )


@pytest.mark.parametrize("kind", sorted(REJECTED_JOURNAL_KINDS))
def test_journal_kinds_win_over_other_rejections(kind: str) -> None:
    assert rejection_reason(kind, "", max_chars=800) == "repository_journal"
    assert rejection_reason(kind, "# " + "a" * 801, max_chars=800) == "repository_journal"


@pytest.mark.parametrize(
    ("kind", "body", "reason"),
    [
        ("unknown", "", "unsupported_category"),
        ("unknown", "AD01", "unsupported_category"),
        ("fact", None, "empty"),
        ("fact", " \t\n" * 801, "empty"),
        ("fact", "x" * 801, "oversized"),
        ("fact", " " + "x" * 800, "oversized"),
        ("fact", "# " + "x" * 800, "oversized"),
        ("fact", "AD01 " + "x" * 800, "oversized"),
        ("fact", "  ```python", "repository_copy"),
        ("fact", "# Heading", "repository_copy"),
        ("fact", "## Heading", "repository_copy"),
        ("fact", ' {"status": true}', "repository_copy"),
        ("fact", " ad01 Keep previous decision", "repository_copy"),
        ("fact", "P09 designed changes", "repository_copy"),
        ("fact", "P7.2 closed-green after review", "repository_copy"),
        ("fact", "P7.2 closed green after review", "repository_copy"),
        ("fact", "P7.2 completed changes", "repository_copy"),
        ("fact", "P7.2 completedness", None),
        ("fact", "x" * 800, None),
        ("active_handoff", "AD01 Need to revisit the decision", None),
        ("active_handoff", "P09 designed changes", None),
        ("active_handoff", "# Heading", "repository_copy"),
        ("blocker", "Decision needed on CI rerun", None),
    ],
)
def test_rejection_order_and_repository_copy(kind: str, body: object, reason: str | None) -> None:
    assert rejection_reason(kind, body, max_chars=800) == reason


def test_validation_uses_canonical_error_and_configured_hint() -> None:
    validate_memory_write("fact", "A" * 50, max_chars=50)
    with pytest.raises(ValidationFailed) as error:
        validate_memory_write("fact", "A" * 51, max_chars=50)
    assert error.value.code is ErrorCode.SCHEMA_INVALID
    assert error.value.details == {
        "reason": "oversized",
        "hint": (
            "not durable memory; keep plans, decisions, progress and code/git facts in repository artifacts; "
            "use a short context/blocker/coordination or one active_handoff (max 50 chars)"
        ),
    }


@pytest.mark.parametrize("max_chars", [800, 2000])
def test_remember_body_respects_effective_limit(max_chars: int) -> None:
    settings = _SETTINGS if max_chars == 800 else replace(_SETTINGS, max_chars=max_chars)
    assert settings.max_chars == max_chars
    body = "x" * max_chars
    schemas().require_valid(
        "urn:skm:knowledge:command:remember:v1",
        {
            "project_id": str(_PROJECT.scope_id),
            "kind": "fact",
            "body": body,
            "ttl_hours": None,
            "source": "cli",
        },
    )
    validate_memory_write("fact", body, max_chars=settings.max_chars)
    with pytest.raises(ValidationFailed) as error:
        validate_memory_write("fact", body + "x", max_chars=settings.max_chars)
    assert error.value.code is ErrorCode.SCHEMA_INVALID
    assert error.value.details["reason"] == "oversized"


@pytest.mark.parametrize("requested", [0, False, True, -1, 73, float("nan"), float("inf"), -float("inf")])
def test_ttl_rejects_invalid_hours_before_probe_cap(requested: float) -> None:
    for kind in (MemoryKind.FACT, MemoryKind.HEALTH_PROBE):
        with pytest.raises(ValidationFailed) as error:
            ttl_for(kind, requested, _SETTINGS)
        assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_default_and_max_ttl_and_probe_cap() -> None:
    assert ttl_for(MemoryKind.FACT, None, _SETTINGS) == timedelta(hours=48)
    assert ttl_for(MemoryKind.FACT, 72, _SETTINGS) == timedelta(hours=72)
    assert ttl_for(MemoryKind.FACT, 1.5, _SETTINGS) == timedelta(minutes=90)
    assert ttl_for(MemoryKind.HEALTH_PROBE, None, _SETTINGS) == timedelta(seconds=300)
    assert ttl_for(MemoryKind.HEALTH_PROBE, 72, _SETTINGS) == timedelta(seconds=300)
    assert ttl_for(MemoryKind.HEALTH_PROBE, 0.05, _SETTINGS) == timedelta(seconds=180)
    narrowed = replace(_SETTINGS, max_ttl_hours=24, default_ttl_hours=12)
    assert ttl_for(MemoryKind.FACT, None, narrowed) == timedelta(hours=12)
    with pytest.raises(ValidationFailed):
        ttl_for(MemoryKind.HEALTH_PROBE, 25, narrowed)


@pytest.mark.parametrize("requested_hours", [None, 1e-12])
def test_health_probe_ttl_with_zero_cap(requested_hours: float | None) -> None:
    settings = replace(_SETTINGS, health_probe_ttl_seconds=0)
    assert ttl_for(MemoryKind.HEALTH_PROBE, requested_hours, settings) == timedelta(microseconds=1)


@pytest.mark.parametrize("kind", [MemoryKind.FACT, MemoryKind.HEALTH_PROBE])
def test_submicrosecond_ttl_produces_a_valid_expiry(kind: MemoryKind) -> None:
    entry = _entry(FrozenClock(), kind, requested_hours=1e-12)
    assert entry.expires_at - entry.created_at == timedelta(microseconds=1)


def test_live_at_default_ttl_boundary_without_renewal() -> None:
    clock = FrozenClock()
    entry = _entry(clock)
    expires_at = entry.expires_at
    assert entry.body == "The runner is offline."
    clock.advance(timedelta(hours=48, seconds=-1))
    assert is_live(entry, clock.now(), _SETTINGS)
    clock.advance(timedelta(seconds=1))
    assert not is_live(entry, clock.now(), _SETTINGS)
    assert entry.expires_at == expires_at
    assert entry.state is MemoryState.LIVE


def test_live_at_configured_max_ttl_and_future_skew_boundaries() -> None:
    clock = FrozenClock()
    entry = _entry(clock)
    narrowed = replace(_SETTINGS, max_ttl_hours=24, default_ttl_hours=24)
    assert is_live(entry, clock.now() + timedelta(hours=24, seconds=-1), narrowed)
    assert not is_live(entry, clock.now() + timedelta(hours=24), narrowed)
    threshold = clock.now() - timedelta(seconds=60)
    assert is_live(entry, threshold, _SETTINGS)
    assert not is_live(entry, threshold - timedelta(microseconds=1), _SETTINGS)
    with pytest.raises(ValidationFailed):
        is_live(entry, threshold.replace(tzinfo=None), _SETTINGS)


def test_health_probe_expires_at_300_seconds() -> None:
    clock = FrozenClock()
    entry = _entry(clock, MemoryKind.HEALTH_PROBE)
    clock.advance(timedelta(seconds=299))
    assert is_live(entry, clock.now(), _SETTINGS)
    clock.advance(timedelta(seconds=1))
    assert not is_live(entry, clock.now(), _SETTINGS)


def test_memory_entry_checks_body_timestamp_state_and_row_version() -> None:
    entry = _entry(FrozenClock())
    for updates in (
        {"created_at": entry.created_at.replace(tzinfo=None)},
        {"expires_at": entry.expires_at.replace(tzinfo=None)},
        {"expires_at": entry.created_at},
        {"expires_at": entry.created_at - timedelta(seconds=1)},
        {"body": ""},
        {"body": " untrimmed"},
        {"body": "x" * 2001},
        {"state": MemoryState.FORGOTTEN},
        {"state_changed_at": entry.created_at},
        {"row_version": 0},
    ):
        with pytest.raises(ValidationFailed) as error:
            replace(entry, **updates)
        assert error.value.code is ErrorCode.SCHEMA_INVALID
    assert len(replace(entry, body="x" * 2000).body) == 2000


@pytest.mark.parametrize(
    ("transition", "state"),
    [(expire, MemoryState.EXPIRED), (forget, MemoryState.FORGOTTEN), (supersede, MemoryState.SUPERSEDED)],
)
def test_terminal_memory_transitions_are_immutable_and_idempotent(
    transition: Callable[[MemoryEntry, datetime], MemoryEntry], state: MemoryState
) -> None:
    clock = FrozenClock()
    entry = _entry(clock)
    clock.set(entry.expires_at)
    changed = transition(entry, clock.now())
    assert changed == replace(entry, state=state, state_changed_at=clock.now(), row_version=2)
    assert entry.row_version == 1
    assert entry.state is MemoryState.LIVE
    assert not is_live(changed, entry.created_at, _SETTINGS)
    clock.advance(timedelta(seconds=1))
    assert transition(changed, clock.now()) is changed


def test_eighth_counted_entry_succeeds_and_handoff_and_probe_are_exempt() -> None:
    for kind in (MemoryKind.FACT, MemoryKind.BLOCKER, MemoryKind.CONTEXT, MemoryKind.COORDINATION):
        check_limits(7, kind, _SETTINGS)
        with pytest.raises(PreconditionFailed) as error:
            check_limits(8, kind, _SETTINGS)
        assert error.value.code is ErrorCode.MEMORY_LIMIT_REACHED
    check_limits(8, MemoryKind.HEALTH_PROBE, _SETTINGS)
    check_limits(8, MemoryKind.ACTIVE_HANDOFF, _SETTINGS)


def test_handoff_cas_reserves_persisted_live_row_even_after_ttl() -> None:
    clock = FrozenClock()
    handoff = _entry(clock, MemoryKind.ACTIVE_HANDOFF)
    clock.set(handoff.expires_at)
    assert not is_live(handoff, clock.now(), _SETTINGS)
    check_handoff_replacement(_PROJECT, MemoryKind.ACTIVE_HANDOFF, None, None)
    for incumbent, expected in ((handoff, None), (handoff, MemoryEntryId(UUID(int=99))), (None, handoff.id)):
        with pytest.raises(Conflict) as error:
            check_handoff_replacement(_PROJECT, MemoryKind.ACTIVE_HANDOFF, incumbent, expected)
        assert error.value.code is ErrorCode.VERSION_CONFLICT
        assert error.value.details == {"reason": "handoff_changed"}
    check_handoff_replacement(_PROJECT, MemoryKind.ACTIVE_HANDOFF, handoff, handoff.id)
    predecessor = supersede(handoff, clock.now())
    successor = replace(
        handoff,
        id=MemoryEntryId(UUID(int=5)),
        created_at=clock.now(),
        expires_at=clock.now() + timedelta(hours=48),
        supersedes_id=predecessor.id,
    )
    assert predecessor.state is MemoryState.SUPERSEDED
    assert successor.supersedes_id == handoff.id
    with pytest.raises(Conflict):
        check_handoff_replacement(_PROJECT, MemoryKind.ACTIVE_HANDOFF, successor, handoff.id)
    with pytest.raises(ValidationFailed):
        check_handoff_replacement(_PROJECT, MemoryKind.FACT, None, handoff.id)


@pytest.mark.parametrize("name", ["ab", "a" * 41, "a1-b"])
def test_valid_namespace_shape(name: str) -> None:
    assert MemoryScope(MemoryScopeKind.NAMESPACE, None, name, _WORKSPACE).namespace == name


@pytest.mark.parametrize("name", [None, "", "a", "a" * 42, "A1", "1a", "a_b", "a.b", "ab\n", "*"])
def test_namespace_shape_rejects_invalid_names(name: str | None) -> None:
    with pytest.raises(ValidationFailed) as error:
        MemoryScope(MemoryScopeKind.NAMESPACE, None, name, _WORKSPACE)
    assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_scope_shapes_reject_scope_fields_from_other_kinds() -> None:
    for scope, updates in (
        (_PROJECT, {"scope_id": None}),
        (_PROJECT, {"workspace_id": None}),
        (_PROJECT, {"namespace": "ops"}),
        (_GLOBAL, {"scope_id": _PROJECT.scope_id}),
        (_GLOBAL, {"workspace_id": _WORKSPACE}),
        (_GLOBAL, {"namespace": "ops"}),
        (MemoryScope(MemoryScopeKind.NAMESPACE, None, "ops", _WORKSPACE), {"scope_id": _PROJECT.scope_id}),
        (MemoryScope(MemoryScopeKind.NAMESPACE, None, "ops", _WORKSPACE), {"workspace_id": None}),
    ):
        with pytest.raises(ValidationFailed):
            replace(scope, **updates)


def test_sharing_requires_opt_in_and_a_bound_project() -> None:
    namespaces = ("team", "ops", "*", "ops")
    assert recall_scopes(_PROJECT, namespaces) == (_PROJECT,)
    scopes = recall_scopes(_PROJECT, namespaces, include_shared=True)
    assert (
        scopes
        == allowed_scopes(_PROJECT, namespaces)
        == (
            _PROJECT,
            _GLOBAL,
            MemoryScope(MemoryScopeKind.NAMESPACE, None, "ops", _WORKSPACE),
            MemoryScope(MemoryScopeKind.NAMESPACE, None, "team", _WORKSPACE),
        )
    )
    ensure_scope_allowed(_GLOBAL, scopes)
    for unauthorized in (
        replace(scopes[2], workspace_id=WorkspaceId(UUID(int=90))),
        replace(scopes[2], namespace="qa"),
    ):
        with pytest.raises(Forbidden) as error:
            ensure_scope_allowed(unauthorized, scopes)
        assert error.value.code is ErrorCode.FORBIDDEN
    for missing in (None, _GLOBAL):
        with pytest.raises(PreconditionFailed) as error:
            require_project_scope(missing)
        assert error.value.code is ErrorCode.MEMORY_SCOPE_REQUIRED
    with pytest.raises(PreconditionFailed):
        recall_scopes(None, namespaces, include_shared=True)


def test_allowed_scopes_ignores_unusable_namespace_names() -> None:
    namespaces = ["ops", "team_ops", "*"]
    assert allowed_scopes(_PROJECT, namespaces) == (
        _PROJECT,
        _GLOBAL,
        MemoryScope(MemoryScopeKind.NAMESPACE, None, "ops", _WORKSPACE),
    )


def test_scope_lock_key_matches_the_canonical_scope_tuple() -> None:
    assert scope_lock_key(_PROJECT) == 0x5FA80A497989B7E6
    scopes = (
        *allowed_scopes(_PROJECT, ("ops", "*")),
        replace(_PROJECT, workspace_id=WorkspaceId(UUID(int=9))),
    )
    keys = {scope_lock_key(scope) for scope in scopes}
    assert len(keys) == len(scopes)
    assert all(-(2**63) <= key < 2**63 for key in keys)


def test_memory_event_schemas_and_scope_streams_without_body() -> None:
    entry = _entry(FrozenClock())
    remembered = MemoryRemembered(entry.scope, entry.id, entry.kind, entry.expires_at)
    forgotten = MemoryForgotten(entry.scope, (entry.id,))
    assert remembered.stream_kind == forgotten.stream_kind == "memory"
    assert remembered.stream_id() == forgotten.stream_id() == _PROJECT.scope_id
    assert remembered.scope_workspace_id() == forgotten.scope_workspace_id() == _WORKSPACE
    for event in (remembered, forgotten):
        event.validate(schemas())
        assert "body" not in event.payload()
    assert forgotten.payload() == {"entry_ids": [str(entry.id)]}
    payload = remembered.payload()
    assert set(payload) == {"entry_id", "scope", "kind", "expires_at"}
    assert schemas().validate(remembered.event_type, {**payload, "body": entry.body})

    scopes = allowed_scopes(_PROJECT, ("*", "ops", "team"))
    ids = {replace(remembered, scope=scope).stream_id() for scope in scopes}
    same_name_other_workspace = replace(scopes[2], workspace_id=WorkspaceId(UUID(int=9)))
    assert len(ids) == len(scopes)
    assert replace(remembered, scope=same_name_other_workspace).stream_id() not in ids
    assert replace(remembered, scope=_GLOBAL).scope_workspace_id() is None
    assert replace(remembered, scope=scopes[2]).stream_id() == replace(forgotten, scope=scopes[2]).stream_id()


def test_memory_command_and_settings_schema_fixtures() -> None:
    remember_urn = "urn:skm:knowledge:command:remember:v1"
    request: JsonObject = {
        "project_id": str(_PROJECT.scope_id),
        "kind": "active_handoff",
        "body": "P09 designed changes",
        "source": "cli",
        "ttl_hours": 72,
    }
    schemas().require_valid(remember_urn, request)
    for invalid in (
        {"kind": "decision"},
        {"body": "x" * 2001},
        {"ttl_hours": 0},
        {"ttl_hours": 73},
        {"ttl_hours": True},
    ):
        assert schemas().validate(remember_urn, {**request, **invalid})

    settings_urn = "urn:skm:settings:knowledge:v1"
    memory = {
        "default_ttl_hours": 48,
        "max_ttl_hours": 48,
        "recall_shared_limit": 0,
        "namespaces": ["*", "ops"],
    }
    schemas().require_valid(settings_urn, {"memory": memory})
    for invalid in ({"max_ttl_hours": 73}, {"recall_shared_limit": -1}, {"namespaces": ["ops", "ops"]}):
        assert schemas().validate(settings_urn, {"memory": {**memory, **invalid}})
    validator = settings_registry().validator("knowledge.ttl_order")
    values: JsonObject = {"knowledge.memory.default_ttl_hours": 48, "knowledge.memory.max_ttl_hours": 48}
    assert validator(values) is None
    assert validator({**values, "knowledge.memory.max_ttl_hours": 47}) is not None
