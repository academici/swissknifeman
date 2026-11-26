"""``Bus.dispatch`` over the memory UoW with the test-only ``demo.echo`` command.

Covers validation, denied audit, idempotency, handler errors, invalid results and the duplicate-receipt race.
The demo module exists only in ``tests/fakes``; no production registry contains it.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any, ClassVar, cast
from uuid import UUID

import pytest

from fakes.app import Harness, build_harness, request_id
from fakes.demo_module import (
    ECHO,
    ECHO_SECRET,
    Echo,
    EchoResult,
    EchoSecret,
    handle_echo,
    manifest,
)
from skm.adapters.memory.core.idempotency import MemoryIdempotencyStore
from skm.application_bus.middleware import request_digest
from skm.application_bus.ports import IdempotencyReceipt
from skm.application_bus.registry import IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    Conflict,
    Forbidden,
    InternalError,
    NotFound,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
)
from skm.kernel.generated._codec import json_copy
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.jsonc.digest import digest

SECRET = "hunter2-quartz-lantern"


def echo(h: Harness, text: str = "hello") -> Echo:
    return Echo(workspace_id=h.seed.workspace_id, text=text)


class Counting:
    """Handler wrapper that counts calls; the wrapped handler still records the event."""

    def __init__(self, inner: Callable[..., Any] = handle_echo) -> None:
        self.inner = inner
        self.calls = 0

    def __call__(self, cmd: Any, ctx: Any, uow: Any) -> Any:
        self.calls += 1
        return self.inner(cmd, ctx, uow)


def with_spec(spec: Any, **changes: Any) -> Harness:
    return build_harness(manifests=(manifest(commands=(replace(spec, **changes),)),))


def committed_nothing(h: Harness) -> bool:
    core = h.backend.committed.core
    return not (core.events or core.outbox or core.idempotency or core.audit)


# ---------------------------------------------------------------- happy path


def test_dispatch_commits_event_outbox_and_allowed_audit_together() -> None:
    h = build_harness()
    result = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert result == EchoResult(text="hello")
    (event,) = h.events()
    assert event.type == "urn:skm:demo:event:echoed:v1"
    assert event.workspace_seq == 1
    assert sorted(r.destination for r in h.backend.committed.core.outbox.values()) == [
        "demo.on_echoed",
        "sse",
    ]
    (audit,) = h.audit()
    assert (audit.decision, audit.action, audit.request_id) == ("allowed", "demo.echo", request_id())
    assert audit.workspace_id == h.seed.workspace_id
    assert audit.reason_code is None
    assert h.backend.peak_active == 1  # a request holds one unit of work at a time


def test_audit_can_be_switched_off_by_the_spec_or_the_config_key() -> None:
    no_audit = with_spec(ECHO, audit=False)
    no_audit.bus.dispatch(echo(no_audit), actor=no_audit.actor, meta=no_audit.meta())
    assert no_audit.audit() == []
    assert len(no_audit.events()) == 1
    quiet = build_harness(config={"access.audit.record_allowed": False})
    quiet.bus.dispatch(echo(quiet), actor=quiet.actor, meta=quiet.meta())
    assert quiet.audit() == []
    assert quiet.config.calls == 1


def test_module_disabled_command_is_a_precondition_failure() -> None:
    h = build_harness(disabled_modules=frozenset({"demo"}))
    with pytest.raises(PreconditionFailed) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value.code is ErrorCode.MODULE_DISABLED
    assert committed_nothing(h)


# ---------------------------------------------------------------- validation


def test_invalid_dto_is_refused_before_any_unit_of_work() -> None:
    h = build_harness()
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(echo(h, ""), actor=h.actor, meta=h.meta())
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert h.authorizer.calls == []
    assert committed_nothing(h)


def test_forbidden_mode_rejects_a_key_before_the_handler() -> None:
    counting = Counting()
    h = with_spec(ECHO, idempotency=IdempotencyMode.FORBIDDEN, handler=counting)
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("key-1"))
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert raised.value.details["reason"] == "not_idempotent"
    assert counting.calls == 0
    assert h.authorizer.calls == []
    assert committed_nothing(h)
    h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())  # without a key the command runs
    assert counting.calls == 1


def test_required_mode_needs_a_key_before_the_handler() -> None:
    counting = Counting()
    h = with_spec(ECHO, idempotency=IdempotencyMode.REQUIRED, handler=counting)
    with pytest.raises(ValidationFailed):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert counting.calls == 0
    assert committed_nothing(h)


# ---------------------------------------------------------------- authorization and denied audit


def test_denied_command_writes_denied_audit_in_a_separate_unit_of_work() -> None:
    counting = Counting()
    h = with_spec(ECHO, handler=counting)
    h.authorizer.deny_all()
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k"))
    assert raised.value.details["permission"] == "demo.echo"
    assert raised.value.details["reason_code"] == "ROLE_LACKS_PERMISSION"
    assert counting.calls == 0
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "ROLE_LACKS_PERMISSION")
    assert audit.target == {
        "scope": {"kind": "workspace", "id": str(h.seed.workspace_id)},
        "permission": "demo.echo",
    }
    assert h.backend.committed.core.idempotency == {}
    assert h.events() == []
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


def test_kind_refusal_happens_before_begin_and_is_audited() -> None:
    h = with_spec(ECHO, allowed_kinds=frozenset({PrincipalKind.SERVICE}))
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value.details["reason_code"] == "KIND_NOT_ALLOWED"
    assert h.authorizer.calls == []  # no unit of work was open for the decision
    assert h.audit()[0].reason_code == "KIND_NOT_ALLOWED"
    assert h.audit()[0].decision == "denied"


def test_receipt_hit_does_not_bypass_authorization() -> None:
    counting = Counting()
    h = with_spec(ECHO, handler=counting)
    first = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(1)))
    h.authorizer.deny_all()
    with pytest.raises(Forbidden):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert counting.calls == 1
    assert first == EchoResult(text="hello")
    assert [a.decision for a in h.audit()] == ["allowed", "denied"]
    assert len(h.authorizer.calls) == 2  # authorized again before the receipt was read


def denying(error: SkmError) -> Callable[..., EchoResult]:
    """A handler that writes first and then fails with ``error`` (as a settings handler finds a missing right
    after reading the stored entry)."""

    def handler(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)  # the event is recorded before the failure
        raise error

    return handler


def test_a_denial_the_handler_finds_is_audited_after_rollback_and_keeps_its_error() -> None:
    original = Forbidden(
        ErrorCode.FORBIDDEN, "removing a locked entry", details={"permission": "config.lock"}
    )
    h = with_spec(ECHO, handler=denying(original))
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(echo(h, SECRET), actor=h.actor, meta=h.meta("k1"))
    assert raised.value is original  # the handler's error, details unchanged
    assert raised.value.details == {"permission": "config.lock"}
    (audit,) = h.audit()
    assert (audit.decision, audit.action, audit.request_id) == ("denied", "demo.echo", request_id())
    assert audit.reason_code == "ROLE_LACKS_PERMISSION"
    assert audit.workspace_id == h.seed.workspace_id
    assert audit.target == {
        "scope": {"kind": "workspace", "id": str(h.seed.workspace_id)},
        "permission": "config.lock",
    }
    core = h.backend.committed.core
    assert h.events() == []  # the handler's writes were rolled back
    assert core.outbox == {}
    assert core.idempotency == {}
    assert SECRET not in repr((core.audit, raised.value.to_problem()))
    assert h.backend.peak_active == 1  # the audit UoW opened after the command UoW was closed
    assert h.backend.active == 0


def test_an_error_raised_from_a_denial_keeps_its_contract_and_is_audited() -> None:
    cause = Forbidden(
        ErrorCode.FORBIDDEN,
        "writing settings key requires hook.manage",
        details={"permission": "hook.manage", "reason_code": "TOKEN_NARROWED"},
    )
    problems: JsonObject = {"problems": [{"code": "FORBIDDEN", "rule": "R16"}]}
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, "the document has 1 problem(s)", details=problems)
    error.__cause__ = cause
    h = with_spec(ECHO, handler=denying(error))
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert (raised.value.code, raised.value.details) == (ErrorCode.CONFIG_INVALID, problems)
    assert raised.value.__cause__ is cause
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "TOKEN_NARROWED")
    assert audit.target["permission"] == "hook.manage"
    assert h.events() == []


def test_a_handler_denial_without_a_reason_is_not_reauthorized_for_one() -> None:
    original = Forbidden(
        ErrorCode.FORBIDDEN, "removing a locked entry", details={"permission": "config.lock"}
    )
    h = with_spec(ECHO, handler=denying(original))
    h.authorizer.allowed = {"demo.echo"}
    h.authorizer.reason_code = "NO_MEMBERSHIP"  # what a later decision would say; it proves nothing
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is original
    assert raised.value.details == {"permission": "config.lock"}  # the bus never adds the reason
    (audit,) = h.audit()
    # the bus fallback, not a proven role gap: the original decision's reason is not conveyed (an open gap)
    assert (audit.decision, audit.reason_code) == ("denied", "ROLE_LACKS_PERMISSION")
    assert audit.target["permission"] == "config.lock"
    assert [call.permission for call in h.authorizer.calls] == ["demo.echo"]
    assert h.events() == []
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


def test_a_reason_the_handler_reports_is_kept_and_the_authorizer_is_not_asked_again() -> None:
    original = Forbidden(
        ErrorCode.FORBIDDEN, "denied", details={"permission": "config.lock", "reason_code": "TOKEN_SCOPE"}
    )
    h = with_spec(ECHO, handler=denying(original))
    h.authorizer.reason_code = "TOKEN_NARROWED"
    h.authorizer.allowed = {"demo.echo"}
    with pytest.raises(Forbidden):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert h.audit()[0].reason_code == "TOKEN_SCOPE"
    assert [call.permission for call in h.authorizer.calls] == ["demo.echo"]


def test_a_handler_denial_naming_no_right_does_not_ask_the_authorizer_again() -> None:
    h = with_spec(ECHO, handler=denying(Forbidden(ErrorCode.FORBIDDEN, "not the owner")))
    with pytest.raises(Forbidden):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    (audit,) = h.audit()
    assert (audit.decision, audit.target["permission"]) == ("denied", "demo.echo")
    assert audit.reason_code == "ROLE_LACKS_PERMISSION"  # the bus fallback, not a proven role gap (open)
    assert [call.permission for call in h.authorizer.calls] == ["demo.echo"]


def test_a_reasonless_denial_never_reaches_an_authorizer_that_would_fail() -> None:
    original = Forbidden(ErrorCode.FORBIDDEN, "denied", details={"permission": "config.lock"})
    h = with_spec(ECHO, handler=denying(original))
    decide, lock_lookups = h.authorizer.authorize, []

    def authorize(uow: Any, actor: Any, permission: str, chain: Any) -> Any:
        if permission == "config.lock":
            lock_lookups.append(uow.readonly)
            raise RuntimeError("membership storage is down")
        return decide(uow, actor, permission, chain)

    h.authorizer.authorize = authorize
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is original
    assert lock_lookups == []
    assert [call.permission for call in h.authorizer.calls] == ["demo.echo"]
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "ROLE_LACKS_PERMISSION")
    assert h.events() == []
    assert h.backend.active == 0


def test_a_denial_deeper_in_the_explicit_cause_chain_is_audited() -> None:
    denial = Forbidden(
        ErrorCode.FORBIDDEN, "denied", details={"permission": "hook.manage", "reason_code": "TOKEN_SCOPE"}
    )
    middle = PreconditionFailed(ErrorCode.CONFIRMATION_REQUIRED, "wrapped")
    middle.__cause__ = denial
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, "the document has 1 problem(s)")
    error.__cause__ = middle
    h = with_spec(ECHO, handler=denying(error))
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert raised.value.__cause__ is middle
    assert middle.__cause__ is denial
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "TOKEN_SCOPE")
    assert audit.target["permission"] == "hook.manage"
    assert h.events() == []


def test_a_cyclic_cause_chain_ends_and_a_denial_in_it_is_found() -> None:
    first = ValidationFailed(ErrorCode.CONFIG_INVALID, "first")
    second = Conflict(ErrorCode.VERSION_CONFLICT, "second")
    first.__cause__, second.__cause__ = second, first
    h = with_spec(ECHO, handler=denying(first))
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is first
    assert committed_nothing(h)  # a cycle without a Forbidden is no denial
    denial = Forbidden(ErrorCode.FORBIDDEN, "denied", details={"permission": "config.lock"})
    looped = ValidationFailed(ErrorCode.CONFIG_INVALID, "looped")
    denial.__cause__, looped.__cause__ = looped, denial
    h = with_spec(ECHO, handler=denying(looped))
    with pytest.raises(ValidationFailed):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert [audit.decision for audit in h.audit()] == ["denied"]


def test_an_implicit_forbidden_context_is_not_a_denial() -> None:
    def handler(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)
        try:
            raise Forbidden(ErrorCode.FORBIDDEN, "probe", details={"permission": "config.lock"})
        except Forbidden:
            raise NotFound(ErrorCode.NOT_FOUND, "no entry") from None

    def handler_with_context(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)
        try:
            raise Forbidden(ErrorCode.FORBIDDEN, "probe", details={"permission": "config.lock"})
        except Forbidden:
            raise NotFound(ErrorCode.NOT_FOUND, "no entry")  # noqa: B904 - the implicit context under test

    for implicit in (handler, handler_with_context):
        h = with_spec(ECHO, handler=implicit)
        with pytest.raises(NotFound):
            h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
        assert committed_nothing(h)


@pytest.mark.parametrize(
    "error",
    [
        ValidationFailed(
            ErrorCode.CONFIG_INVALID, "bad value", details={"problems": [{"code": "FORBIDDEN"}]}
        ),
        NotFound(ErrorCode.NOT_FOUND, "no entry", details={"permission": "config.lock"}),
        Conflict(ErrorCode.VERSION_CONFLICT, "stale"),
    ],
)
def test_other_handler_errors_are_not_denials(error: SkmError) -> None:
    h = with_spec(ECHO, handler=denying(error))
    with pytest.raises(type(error)) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert committed_nothing(h)  # no denied audit for a validation, lookup or version failure


def test_a_handler_denial_stores_no_receipt_and_the_key_runs_again_once_allowed() -> None:
    calls: dict[str, int] = {}
    state = {"deny": True}

    def handler(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        calls["n"] = calls.get("n", 0) + 1
        result = handle_echo(cmd, ctx, uow)
        if state["deny"]:
            raise Forbidden(ErrorCode.FORBIDDEN, "denied", details={"permission": "config.lock"})
        return result

    h = with_spec(ECHO, handler=handler)
    with pytest.raises(Forbidden):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1"))
    assert h.backend.committed.core.idempotency == {}
    state["deny"] = False
    result = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert result == EchoResult(text="hello")
    assert calls["n"] == 2  # no receipt of the denied attempt was replayed
    assert [a.decision for a in h.audit()] == ["denied", "allowed"]
    assert len(h.events()) == 1


# ---------------------------------------------------------------- idempotency


def test_same_key_and_body_replays_the_receipt_without_the_handler() -> None:
    counting = Counting()
    h = with_spec(ECHO, handler=counting)
    first = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(1)))
    second = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert first == second == EchoResult(text="hello")
    assert counting.calls == 1
    assert len(h.events()) == 1
    assert len(h.audit()) == 1


def test_same_key_with_another_body_is_key_reused() -> None:
    h = build_harness()
    h.bus.dispatch(echo(h, "one"), actor=h.actor, meta=h.meta("k1"))
    with pytest.raises(Conflict) as raised:
        h.bus.dispatch(echo(h, "two"), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert len(h.events()) == 1


def test_expired_receipt_runs_the_handler_again() -> None:
    counting = Counting()
    h = build_harness(
        manifests=(manifest(commands=(replace(ECHO, handler=counting),)),), ttl=timedelta(hours=1)
    )
    h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1"))
    h.clock.advance(timedelta(hours=2))
    h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert counting.calls == 2
    assert len(h.events()) == 2


def test_secret_is_part_of_the_digest_and_never_stored_or_reported() -> None:
    h = build_harness(manifests=(manifest(commands=(ECHO_SECRET,)),))
    one = EchoSecret(workspace_id=h.seed.workspace_id, text="hello", secret=SECRET)
    h.bus.dispatch(one, actor=h.actor, meta=h.meta("k1"))
    assert h.bus.dispatch(one, actor=h.actor, meta=h.meta("k1", request=request_id(2))) == EchoResult(
        text="hello"
    )

    other = replace(one, secret=SECRET + "-changed")
    with pytest.raises(Conflict) as raised:
        h.bus.dispatch(other, actor=h.actor, meta=h.meta("k1", request=request_id(3)))
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert request_digest(ECHO_SECRET, one) != request_digest(ECHO_SECRET, other)

    core = h.backend.committed.core
    visible = repr(
        (core.idempotency, core.audit, core.events, core.outbox, raised.value.to_problem(), str(raised.value))
    )
    assert SECRET not in visible


@dataclass(frozen=True, slots=True)
class Budget:
    """Synthetic ``demo.echo`` DTO with a JSON number, like a settings budget of ``15.0``."""

    workspace_id: UUID
    text: str
    amount: JsonValue

    SCHEMA_URN: ClassVar[str] = Echo.SCHEMA_URN

    def to_json(self) -> JsonObject:
        return {"workspace_id": str(self.workspace_id), "text": self.text, "amount": self.amount}


@dataclass(frozen=True, slots=True)
class Limits:
    """Synthetic ``demo.echo`` DTO whose top-level float fields keep the insertion order of ``limits``."""

    workspace_id: UUID
    text: str
    limits: JsonObject

    SCHEMA_URN: ClassVar[str] = Echo.SCHEMA_URN

    def to_json(self) -> JsonObject:
        return {**self.limits, "workspace_id": str(self.workspace_id), "text": self.text}


class Raw:
    """Any validated JSON body for ``request_digest``."""

    def __init__(self, body: JsonObject) -> None:
        self.body = body

    def to_json(self) -> JsonObject:
        return self.body


def budget_harness(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[..., Any], dto: type[Any] = Budget
) -> Harness:
    """``Echo`` schema plus numeric extras; the ``Echo`` fields are validated by the real schema."""
    h = with_spec(ECHO, dto=dto, handler=handler)
    validate = h.schemas.require_valid

    def require_valid(urn: str, instance: object) -> None:
        if urn == Echo.SCHEMA_URN and isinstance(instance, dict):
            body = cast("dict[str, Any]", instance)
            if "amount" in body:
                assert type(body["amount"]) in (int, float)
            instance = {key: value for key, value in body.items() if key in ("workspace_id", "text")}
        validate(urn, instance)

    monkeypatch.setattr(h.schemas, "require_valid", require_valid)
    return h


def test_float_payload_reaches_the_handler_and_replays_by_its_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    counting = Counting()
    h = budget_harness(monkeypatch, counting)
    budget = Budget(workspace_id=h.seed.workspace_id, text="budget", amount=15.0)
    assert h.bus.dispatch(budget, actor=h.actor, meta=h.meta("k1")) == EchoResult(text="budget")
    replay = h.bus.dispatch(budget, actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert replay == EchoResult(text="budget")
    assert counting.calls == 1
    for n, amount in enumerate((15.5, 15), start=3):  # another float, the integer of the same value
        changed = replace(budget, amount=amount)
        with pytest.raises(Conflict) as raised:
            h.bus.dispatch(changed, actor=h.actor, meta=h.meta("k1", request=request_id(n)))
        assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert counting.calls == 1
    (receipt,) = h.backend.committed.core.idempotency.values()
    assert receipt.request_digest == request_digest(ECHO, budget)


def test_reordered_float_objects_replay_through_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    counting = Counting()
    h = budget_harness(monkeypatch, counting, Limits)
    ws = h.seed.workspace_id
    first = Limits(ws, "limits", {"cpu": 0.5, "pool": {"min": 0.25, "max": 2.5}, "ram": [1.5, 3]})
    reordered = Limits(ws, "limits", {"ram": [1.5, 3], "pool": {"max": 2.5, "min": 0.25}, "cpu": 0.5})
    assert list(first.to_json()) != list(reordered.to_json())
    assert h.bus.dispatch(first, actor=h.actor, meta=h.meta("k1")) == EchoResult(text="limits")
    replay = h.bus.dispatch(reordered, actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert replay == EchoResult(text="limits")
    assert counting.calls == 1
    changed = (
        {"ram": [3, 1.5], "pool": {"max": 2.5, "min": 0.25}, "cpu": 0.5},  # an array keeps its order
        {"ram": [1.5, 3], "pool": {"max": 0.25, "min": 2.5}, "cpu": 0.5},  # values swapped between keys
        {"ram": [1.5, 3], "pool": {"max": 2.5, "min": 0.25}, "cpu": "0.5"},  # a string is not the float
    )
    for n, limits in enumerate(changed, start=3):
        meta = h.meta("k1", request=request_id(n))
        with pytest.raises(Conflict) as raised:
            h.bus.dispatch(replace(first, limits=limits), actor=h.actor, meta=meta)
        assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert counting.calls == 1
    assert len(h.events()) == 1
    (receipt,) = h.backend.committed.core.idempotency.values()
    assert receipt.request_digest == request_digest(ECHO, first) == request_digest(ECHO, reordered)


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ({"a": 1.5, "b": 2.5, "c": 3}, {"c": 3, "b": 2.5, "a": 1.5}),  # top level
        ({"x": {"a": 1.5, "b": 2.5}}, {"x": {"b": 2.5, "a": 1.5}}),  # nested
        (  # sibling branches and objects inside arrays
            {"p": {"a": 1.5}, "q": [0.5, {"z": 2.5, "y": 3}], "r": -0.0},
            {"r": -0.0, "q": [0.5, {"y": 3, "z": 2.5}], "p": {"a": 1.5}},
        ),
    ],
)
def test_request_digest_ignores_object_key_order(one: JsonObject, other: JsonObject) -> None:
    assert one == other  # equal JSON, only the insertion order differs
    assert request_digest(ECHO, Raw(one)) == request_digest(ECHO, Raw(other))


def test_request_digest_lists_float_paths_in_canonical_order() -> None:
    body: JsonObject = {"b": 2.5, "a": {"y": [1, 0.5], "x": 1.5}}
    expected = digest(
        {
            "operation": "demo.echo",
            "dto": {"a": {"x": "1.5", "y": [1, "0.5"]}, "b": "2.5"},
            "floats": [["a", "x"], ["a", "y", 1], ["b"]],
        }
    )
    assert request_digest(ECHO, Raw(body)) == expected


def test_request_digest_keeps_reordered_kinds_apart() -> None:
    def d(body: JsonObject) -> str:
        return request_digest(ECHO, Raw(body))

    variants: tuple[JsonObject, ...] = (
        {"a": 1.5, "b": "2.5"},
        {"b": 2.5, "a": "1.5"},
        {"a": 1.0, "b": 1},
        {"b": 1.0, "a": 1},
        {"l": [1.5, 2.5]},
        {"l": [2.5, 1.5]},
        {"l": {"0": 1.5, "1": 2.5}},
        {"l": {"1": 1.5, "0": 2.5}},
    )
    assert len({d(body) for body in variants}) == len(variants)


def test_request_digest_keeps_floats_apart_from_strings_and_integers() -> None:
    def d(body: JsonObject) -> str:
        return request_digest(ECHO, Raw(body))

    assert d({"amount": 15.0}) == d({"amount": 15.0})
    variants: tuple[JsonObject, ...] = (
        {"amount": 15.0},
        {"amount": "15.0"},
        {"amount": 15},
        {"amount": 15.5},
        {"amount": -0.0},
        {"amount": 0.0},
        {"amount": "15.0", "floats": [["amount"]]},  # a DTO field cannot forge the float marker
        {"amount": [1.5]},
        {"amount": ["1.5"]},
        {"amount": {"0": 1.5}},
        {"amount": True},
        {"amount": 1},
    )
    assert len({d(body) for body in variants}) == len(variants)


def test_request_digest_without_floats_keeps_the_single_form() -> None:
    body: JsonObject = {"workspace_id": "w", "text": "hello", "n": 3, "tags": ["a"], "on": False}
    assert request_digest(ECHO, Raw(body)) == digest({"operation": "demo.echo", "dto": body})


@pytest.mark.parametrize("amount", [math.inf, -math.inf, math.nan])
def test_non_finite_number_is_schema_invalid_not_internal(amount: float) -> None:
    with pytest.raises(ValidationFailed) as raised:
        request_digest(ECHO, Raw({"budget": {"limits": [1.0, amount]}}))
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert raised.value.details == {"path": ["budget", "limits", 1]}


@dataclass(frozen=True, slots=True)
class Strict:
    """``demo.echo`` DTO encoded by the generated codec: a non-finite number raises ``ValueError``."""

    workspace_id: UUID
    text: str
    amount: Any

    SCHEMA_URN: ClassVar[str] = Echo.SCHEMA_URN

    def to_json(self) -> JsonObject:
        return json_copy({"workspace_id": str(self.workspace_id), "text": self.text, "amount": self.amount})


@pytest.mark.parametrize("amount", [math.nan, math.inf, -math.inf, [1.5, math.nan], {"x": math.inf}])
def test_a_dto_the_codec_cannot_encode_is_schema_invalid_before_any_unit_of_work(amount: Any) -> None:
    counting = Counting()
    h = with_spec(ECHO, dto=Strict, handler=counting)
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(Strict(h.seed.workspace_id, "x", amount), actor=h.actor, meta=h.meta("k1"))
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert raised.value.details == {"urn": Echo.SCHEMA_URN, "reason": "not_json"}
    assert "non-finite" not in str(raised.value)  # the codec text is not reported
    assert (counting.calls, h.authorizer.calls) == (0, [])
    assert committed_nothing(h)


@pytest.mark.parametrize("bad", ["\ud800", "\udfff", "x\ud83d", "\ude00y"])  # noqa: PT014
@pytest.mark.parametrize("where", ["text", "key", "nested_key", "nested_value"])
def test_unpaired_surrogate_is_schema_invalid_before_any_unit_of_work(
    monkeypatch: pytest.MonkeyPatch, where: str, bad: str
) -> None:
    counting = Counting()
    h = budget_harness(monkeypatch, counting, Limits)
    ws = h.seed.workspace_id
    text = f"{SECRET}{bad}" if where == "text" else "limits"
    limits: JsonObject = {
        "text": {},
        "key": {f"{SECRET}{bad}": 1},
        "nested_key": {"pool": [{f"{SECRET}{bad}": 1}]},
        "nested_value": {"pool": [{"name": f"{SECRET}{bad}"}]},
    }[where]
    with pytest.raises(ValidationFailed) as raised:
        h.bus.dispatch(Limits(ws, text, limits), actor=h.actor, meta=h.meta("k1"))
    assert raised.value.code is ErrorCode.SCHEMA_INVALID
    assert raised.value.details == {"command": "demo.echo", "reason": "invalid_unicode"}
    assert raised.value.__cause__ is None
    assert (counting.calls, h.authorizer.calls) == (0, [])
    assert committed_nothing(h)
    assert h.events() == []
    visible = repr((raised.value.to_problem(), str(raised.value), h.backend.committed.core.outbox))
    assert SECRET not in visible


def test_request_digest_rejects_an_unpaired_surrogate_without_echoing_it() -> None:
    bodies: tuple[JsonObject, ...] = (
        {"text": f"{SECRET}\ud800"},
        {f"{SECRET}\udc00": 1},
        {"a": [{"b": [f"{SECRET}\ud800"]}]},
    )
    for body in bodies:
        with pytest.raises(ValidationFailed) as raised:
            request_digest(ECHO, Raw(body))
        assert raised.value.code is ErrorCode.SCHEMA_INVALID
        assert raised.value.details == {"command": "demo.echo", "reason": "invalid_unicode"}
        assert SECRET not in repr((raised.value.to_problem(), str(raised.value)))


def test_valid_unicode_dispatches_and_replays_by_its_digest() -> None:
    counting = Counting()
    h = with_spec(ECHO, handler=counting)
    text = f"{SECRET} é é 😀 \U0010ffff 日本 �"
    assert h.bus.dispatch(echo(h, text), actor=h.actor, meta=h.meta("k1")) == EchoResult(text=text)
    replay = h.bus.dispatch(echo(h, text), actor=h.actor, meta=h.meta("k1", request=request_id(2)))
    assert replay == EchoResult(text=text)
    assert counting.calls == 1
    with pytest.raises(Conflict) as raised:  # NFC and NFD forms are different text and a different digest
        h.bus.dispatch(
            echo(h, text.replace("é", "é")), actor=h.actor, meta=h.meta("k1", request=request_id(3))
        )
    assert raised.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert counting.calls == 1
    (receipt,) = h.backend.committed.core.idempotency.values()
    assert receipt.request_digest == digest({"operation": "demo.echo", "dto": echo(h, text).to_json()})


def test_other_dto_encoding_failures_stay_internal() -> None:
    class Broken:
        SCHEMA_URN: ClassVar[str] = Echo.SCHEMA_URN

        def __init__(self, workspace_id: UUID) -> None:
            self.workspace_id = workspace_id

        def to_json(self) -> JsonObject:
            raise RuntimeError("codec defect")

    h = with_spec(ECHO, dto=Broken)
    with pytest.raises(InternalError) as raised:
        h.bus.dispatch(Broken(h.seed.workspace_id), actor=h.actor, meta=h.meta())
    assert raised.value.code is ErrorCode.INTERNAL_ERROR
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert committed_nothing(h)


def test_a_value_error_of_the_handler_stays_internal() -> None:
    def broken(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        raise ValueError("handler defect")

    h = with_spec(ECHO, handler=broken)
    with pytest.raises(InternalError):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert committed_nothing(h)


def test_non_finite_path_does_not_depend_on_key_order() -> None:
    bodies: tuple[JsonObject, ...] = ({"z": math.inf, "a": math.nan}, {"a": math.nan, "z": math.inf})
    for body in bodies:
        with pytest.raises(ValidationFailed) as raised:
            request_digest(ECHO, Raw(body))
        assert raised.value.details == {"path": ["a"]}


def test_duplicate_receipt_race_replays_the_winner_after_reauthorization() -> None:
    state = {"raced": False}

    def racing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        if not state["raced"]:
            state["raced"] = True
            now = h.clock.now()
            # The concurrent duplicate commits first. It runs on another connection, so it is written straight
            # into the committed state: a second unit of work cannot be open next to this one (adapters §2.2).
            MemoryIdempotencyStore(h.backend.committed).put(
                IdempotencyReceipt(
                    workspace_id=h.seed.workspace_id,
                    principal_id=h.seed.principal_id,
                    operation="demo.echo",
                    key="race",
                    request_digest=request_digest(ECHO, cmd),
                    result={"text": cmd.text},
                    created_at=now,
                    expires_at=now + timedelta(hours=1),
                )
            )
            raise Conflict(ErrorCode.ALREADY_EXISTS, "lost the receipt race")
        raise AssertionError("the loser must not run the handler twice")

    h = with_spec(ECHO, handler=racing)  # ``racing`` reads ``h`` when it runs, after this assignment
    result = h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("race"))
    assert result == EchoResult(text="hello")  # the winner's stored result
    assert h.events() == []  # the loser's attempt was rolled back
    assert [call.readonly for call in h.authorizer.calls] == [
        False,
        True,
    ]  # replay authorizes in a read-only UoW


def test_conflict_without_a_receipt_stays_the_original_conflict() -> None:
    def conflicting(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        raise Conflict(ErrorCode.ALREADY_EXISTS, "entity exists")

    h = with_spec(ECHO, handler=conflicting)
    with pytest.raises(Conflict) as raised:  # no receipt exists: the original conflict stands
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1"))
    assert raised.value.code is ErrorCode.ALREADY_EXISTS
    with pytest.raises(Conflict) as without_key:  # without a key there is no replay at all
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert without_key.value.code is ErrorCode.ALREADY_EXISTS
    assert h.authorizer.calls[-1].readonly is False  # no read-only replay UoW for a keyless command


# ---------------------------------------------------------------- handler errors and results


def test_unexpected_handler_error_is_internal_and_rolls_everything_back() -> None:
    def broken(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)  # the event is recorded first
        raise RuntimeError(f"private detail {cmd.text}")

    h = with_spec(ECHO, handler=broken)
    with pytest.raises(InternalError) as raised:
        h.bus.dispatch(echo(h, "zebra-lantern"), actor=h.actor, meta=h.meta("k1"))
    assert raised.value.code is ErrorCode.INTERNAL_ERROR
    assert raised.value.details == {"request_id": request_id()}
    assert "zebra-lantern" not in str(raised.value)
    assert "zebra-lantern" not in repr(raised.value.to_problem())
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert committed_nothing(h)


def test_domain_error_of_the_handler_keeps_its_code_and_commits_nothing() -> None:
    def missing(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        handle_echo(cmd, ctx, uow)
        raise NotFound(ErrorCode.NOT_FOUND, "no such thing", details={"kind": "thing"})

    h = with_spec(ECHO, handler=missing)
    with pytest.raises(NotFound):
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta())
    assert committed_nothing(h)


def test_invalid_result_is_internal_error_and_nothing_is_committed() -> None:
    class Bad:
        def to_json(self) -> dict[str, Any]:
            return {"unexpected": 1}

    def bad_result(cmd: Echo, ctx: Any, uow: Any) -> Any:
        handle_echo(cmd, ctx, uow)
        return Bad()

    h = with_spec(ECHO, handler=bad_result)
    with pytest.raises(InternalError) as raised:
        h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta("k1"))
    assert raised.value.details == {"operation": "demo.echo"}
    assert committed_nothing(h)


def test_noop_command_writes_no_event_and_no_outbox_row() -> None:
    def noop(cmd: Echo, ctx: Any, uow: Any) -> EchoResult:
        return EchoResult(text=cmd.text)

    h = with_spec(ECHO, handler=noop, audit=False)
    assert h.bus.dispatch(echo(h), actor=h.actor, meta=h.meta()) == EchoResult(text="hello")
    assert committed_nothing(h)


def test_embedded_client_builds_request_meta_and_new_keys() -> None:
    h = build_harness()
    key = h.client.new_idempotency_key()
    assert key.startswith("idem_")
    assert len(key) == 5 + 32
    assert h.client.dispatch(echo(h), idempotency_key=key) == EchoResult(text="hello")
    assert h.client.dispatch(echo(h), idempotency_key=key) == EchoResult(
        text="hello"
    )  # replay through the client
    (event,) = h.events()
    assert event.request_id is not None
    assert len(event.request_id) == 30
    assert event.request_id.startswith("req_")
    (audit, *_) = h.audit()
    assert audit.request_id == event.request_id
