"""``Bus.ask`` / ``ask_with_meta`` and ``EmbeddedClient`` reads over the memory UoW."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest

from fakes.app import Harness, build_harness, request_id
from fakes.demo_module import GET_ECHO, Echo, Echoed, GetEcho, GetEchoResult, manifest
from skm.application_bus.client import QueryMeta
from skm.application_bus.ports import AuditLog, AuditRecord, EventReader
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, InternalError, NotFound, SkmError, ValidationFailed
from skm.kernel.json_types import JsonObject

SECRET = "hunter2-quartz-lantern"


def query(h: Harness, *, other: bool = False) -> GetEcho:
    return GetEcho(workspace_id=h.seed.other_workspace_id if other else h.seed.workspace_id)


def say(h: Harness, text: str = "hello") -> None:
    h.client.dispatch(Echo(workspace_id=h.seed.workspace_id, text=text))


def with_query(**changes: Any) -> Harness:
    return build_harness(manifests=(manifest(queries=(replace(GET_ECHO, **changes),)),))


# ---------------------------------------------------------------- reads leave no trace


def test_ask_returns_the_result_and_commits_nothing() -> None:
    h = build_harness()
    before = h.backend.committed
    assert h.bus.ask(query(h), actor=h.actor, meta=h.meta()) == GetEchoResult(texts=())
    assert h.backend.committed is before  # a read never replaces the committed state
    assert h.audit() == []
    assert h.backend.committed.core.idempotency == {}
    assert h.backend.peak_active == 1
    assert h.backend.active == 0
    assert h.authorizer.calls[-1].readonly is True


# ---------------------------------------------------------------- events_cursor


def test_events_cursor_is_the_workspace_head_in_the_same_snapshot() -> None:
    h = build_harness()
    _, empty = h.bus.ask_with_meta(query(h), actor=h.actor, meta=h.meta())
    assert empty == QueryMeta(events_cursor=0)
    say(h, "one")
    say(h, "two")
    _, after = h.bus.ask_with_meta(query(h), actor=h.actor, meta=h.meta())
    assert after.events_cursor == 2
    _, other = h.bus.ask_with_meta(query(h, other=True), actor=h.actor, meta=h.meta())
    assert other.events_cursor == 0  # another workspace has its own feed


def test_instance_scoped_query_has_no_cursor() -> None:
    h = with_query(scope_of=None)
    say(h)
    _, meta = h.bus.ask_with_meta(query(h), actor=h.actor, meta=h.meta())
    assert meta.events_cursor is None


def test_embedded_client_reads_data_then_follows_events_from_the_cursor() -> None:
    h = build_harness()
    say(h, "one")
    result, meta = h.client.ask_with_meta(query(h))
    assert result == GetEchoResult(texts=())
    assert meta.events_cursor == 1
    assert h.client.ask(query(h)) == result
    say(h, "two")
    say(h, "three")
    followed = list(h.client.events(workspace_id=h.seed.workspace_id, after=meta.events_cursor or 0))
    assert [e.payload["text"] for e in followed] == ["two", "three"]
    assert [e.workspace_seq for e in followed] == [2, 3]
    only_other_type = list(
        h.client.events(
            workspace_id=h.seed.workspace_id, after=0, types=frozenset({"urn:skm:demo:event:other:v1"})
        )
    )
    assert only_other_type == []
    assert list(h.client.events(workspace_id=h.seed.workspace_id, after=3, wait_seconds=0.05)) == []


# ---------------------------------------------------------------- authorization and denied audit


def test_denied_query_audits_in_a_separate_unit_of_work() -> None:
    h = build_harness()
    h.authorizer.deny_all()
    with pytest.raises(Forbidden) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value.details["permission"] == "demo.read"
    (audit,) = h.audit()
    assert (audit.decision, audit.action, audit.reason_code) == (
        "denied",
        "demo.get_echo",
        "ROLE_LACKS_PERMISSION",
    )
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


def test_kind_refusal_of_a_query_is_audited_without_a_unit_of_work_for_the_decision() -> None:
    h = with_query(allowed_kinds=frozenset({PrincipalKind.WORKER}))
    with pytest.raises(Forbidden) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value.details["reason_code"] == "KIND_NOT_ALLOWED"
    assert h.authorizer.calls == []
    assert h.audit()[0].decision == "denied"


def denying(error: SkmError) -> Callable[..., GetEchoResult]:
    """A query handler that reads protected state and then finds a missing right (``error``)."""

    def handler(q: GetEcho, ctx: Any, uow: Any) -> GetEchoResult:
        uow.repo(EventReader).head_workspace_seq(q.workspace_id)  # the protected state is read first
        raise error

    return handler


def test_a_denial_the_query_handler_finds_is_audited_after_the_readonly_unit_of_work() -> None:
    original = Forbidden(ErrorCode.FORBIDDEN, "reading a locked entry", details={"permission": "config.lock"})
    h = with_query(handler=denying(original))
    say(h, SECRET)
    allowed_before = h.audit()
    with pytest.raises(Forbidden) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta(request=request_id(7)))
    assert raised.value is original  # the handler's own error, details unchanged
    assert raised.value.code is ErrorCode.FORBIDDEN
    assert raised.value.details == {"permission": "config.lock"}
    (audit,) = h.audit()[len(allowed_before) :]  # exactly one new row, and it is the denial
    assert (audit.decision, audit.action, audit.request_id) == ("denied", "demo.get_echo", request_id(7))
    assert audit.reason_code == "ROLE_LACKS_PERMISSION"
    assert audit.actor_id == h.actor.principal_id
    assert audit.workspace_id == h.seed.workspace_id
    assert audit.target == {
        "scope": {"kind": "workspace", "id": str(h.seed.workspace_id)},
        "permission": "config.lock",
    }
    assert [a.decision for a in h.audit()].count("allowed") == len(allowed_before)  # no allowed audit
    assert len(h.events()) == 1  # nothing but the denied audit was written
    assert h.backend.committed.core.idempotency == {}
    assert SECRET not in repr((audit, raised.value.to_problem()))
    assert h.backend.peak_active == 1  # the audit UoW opened after the readonly UoW was closed
    assert h.backend.active == 0


def test_an_error_raised_from_a_denial_in_a_query_keeps_its_contract_and_is_audited() -> None:
    cause = Forbidden(
        ErrorCode.FORBIDDEN,
        "reading the key requires hook.manage",
        details={"permission": "hook.manage", "reason_code": "TOKEN_NARROWED"},
    )
    problems: JsonObject = {"problems": [{"code": "FORBIDDEN", "rule": "R16"}]}
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, "the document has 1 problem(s)", details=problems)
    error.__cause__ = cause
    h = with_query(handler=denying(error))
    with pytest.raises(ValidationFailed) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert (raised.value.code, raised.value.details) == (ErrorCode.CONFIG_INVALID, problems)
    assert raised.value.__cause__ is cause
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "TOKEN_NARROWED")
    assert audit.target["permission"] == "hook.manage"
    assert h.backend.peak_active == 1


def test_a_query_handler_denial_without_a_reason_is_not_reauthorized_for_one() -> None:
    original = Forbidden(ErrorCode.FORBIDDEN, "reading a locked entry", details={"permission": "config.lock"})
    h = with_query(handler=denying(original))
    h.authorizer.allowed = {"demo.read"}
    h.authorizer.reason_code = "NO_MEMBERSHIP"  # what a later decision would say; it proves nothing
    with pytest.raises(Forbidden) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value is original
    assert raised.value.details == {"permission": "config.lock"}
    (audit,) = h.audit()
    # the bus fallback, not a proven role gap: the original decision's reason is not conveyed (an open gap)
    assert (audit.decision, audit.reason_code) == ("denied", "ROLE_LACKS_PERMISSION")
    assert [(call.permission, call.readonly) for call in h.authorizer.calls] == [("demo.read", True)]
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


def test_a_query_denial_deeper_in_the_explicit_cause_chain_is_audited() -> None:
    denial = Forbidden(
        ErrorCode.FORBIDDEN, "denied", details={"permission": "hook.manage", "reason_code": "TOKEN_SCOPE"}
    )
    middle = NotFound(ErrorCode.NOT_FOUND, "hidden")
    middle.__cause__ = denial
    error = ValidationFailed(ErrorCode.CONFIG_INVALID, "the document has 1 problem(s)")
    error.__cause__ = middle
    h = with_query(handler=denying(error))
    h.authorizer.allowed = {"demo.read"}
    h.authorizer.reason_code = "TOKEN_NARROWED"  # a later decision would differ; the reported one is kept
    with pytest.raises(ValidationFailed) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert raised.value.__cause__ is middle
    (audit,) = h.audit()
    assert (audit.decision, audit.reason_code) == ("denied", "TOKEN_SCOPE")
    assert [call.permission for call in h.authorizer.calls] == ["demo.read"]
    assert audit.target["permission"] == "hook.manage"


def test_a_cyclic_cause_chain_of_a_query_error_is_no_denial() -> None:
    first = ValidationFailed(ErrorCode.CONFIG_INVALID, "first")
    second = NotFound(ErrorCode.NOT_FOUND, "second")
    first.__cause__, second.__cause__ = second, first
    h = with_query(handler=denying(first))
    with pytest.raises(ValidationFailed) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value is first
    assert h.audit() == []


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
def test_other_query_handler_errors_are_not_denials(error: SkmError) -> None:
    h = with_query(handler=denying(error))
    with pytest.raises(type(error)) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value is error
    assert h.audit() == []  # no denied audit for a validation, lookup or version failure
    assert h.backend.peak_active == 1


class _FailingAudit:
    def append(self, record: AuditRecord) -> None:
        raise RuntimeError("audit storage is down")


@pytest.mark.parametrize("handler_denial", [True, False])
def test_a_failing_denied_audit_of_a_query_fails_closed(handler_denial: bool) -> None:
    denial = Forbidden(ErrorCode.FORBIDDEN, "reading a locked entry", details={"permission": "config.lock"})
    h = with_query(handler=denying(denial)) if handler_denial else build_harness()
    if not handler_denial:
        h.authorizer.deny_all()
    h.backend.factories = {**h.backend.factories, AuditLog: lambda state: _FailingAudit()}
    with pytest.raises(InternalError) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value.code is ErrorCode.INTERNAL_ERROR  # neither a result nor an unaudited FORBIDDEN
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert h.audit() == []
    assert h.backend.peak_active == 1
    assert h.backend.active == 0


def test_unknown_scope_is_not_found() -> None:
    h = build_harness()
    with pytest.raises(NotFound):
        h.bus.ask(GetEcho(workspace_id=uuid4()), actor=h.actor, meta=h.meta())
    assert h.audit() == []


# ---------------------------------------------------------------- readonly and results


def test_query_handler_cannot_record_events_or_write_repositories() -> None:
    def record(q: GetEcho, ctx: Any, uow: Any) -> GetEchoResult:
        uow.record(Echoed(workspace_id=q.workspace_id, text="forbidden"))  # type: ignore[arg-type]
        return GetEchoResult(texts=())

    def write(q: GetEcho, ctx: Any, uow: Any) -> GetEchoResult:
        uow.repo(AuditLog).append(
            AuditRecord(
                id=uuid4(),
                workspace_id=None,
                actor_id=ctx.actor.principal_id,
                action="x",
                target={},
                decision="allowed",
                reason_code=None,
                request_id=ctx.meta.request_id,
                recorded_at=ctx.meta.received_at,
            )
        )
        return GetEchoResult(texts=())

    for handler in (record, write):
        h = with_query(handler=handler)
        with pytest.raises(InternalError) as raised:
            h.bus.ask(query(h), actor=h.actor, meta=h.meta())
        assert isinstance(raised.value.__cause__, RuntimeError)
        assert h.events() == []
        assert h.audit() == []


def test_invalid_query_result_is_internal_error() -> None:
    class Bad:
        def to_json(self) -> dict[str, Any]:
            return {"texts": "not-a-list"}

    h = with_query(handler=lambda q, ctx, uow: Bad())
    with pytest.raises(InternalError) as raised:
        h.bus.ask(query(h), actor=h.actor, meta=h.meta())
    assert raised.value.code is ErrorCode.INTERNAL_ERROR
    assert raised.value.details == {"operation": "demo.get_echo"}
