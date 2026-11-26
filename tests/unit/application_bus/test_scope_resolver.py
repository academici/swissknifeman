"""``scope_resolver``: the stored resource names the scope the bus authorizes on (kernel §4.4).

An operation that carries only the id of a stored resource cannot name a scope in its request. The spec's
resolver reads the owner link in the operation's own unit of work and returns a ``ScopeRef``; the bus
authorizes on it, the handler gets it as ``ctx.scope``, an unknown resource fails closed on the instance
scope, and a denial on a resolved scope tells the caller nothing of the resource.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from fakes.app import Harness, build_harness
from fakes.demo_module import (
    ECHO,
    GET_ECHO,
    PERMISSIONS,
    SCHEMA_ROOT,
    Echo,
    GetEcho,
    GetEchoResult,
    manifest,
)
from skm.application_bus.ports import AuthzDecision
from skm.application_bus.registry import BusRegistry, BusRegistryError
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, NotFound
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef
from skm.platform.schema.registry import SchemaRegistry


class ScopedAuthorizer:
    """Allows a permission only on the listed scopes; the refusal carries ``reason_code``."""

    def __init__(self, allowed: set[Any], *, reason_code: str = "NO_MEMBERSHIP") -> None:
        self.allowed = allowed
        self.reason_code = reason_code
        self.calls: list[Any] = []

    def authorize(
        self, uow: UnitOfWork, actor: Actor, permission: str | None, chain: tuple[ScopeRecord, ...]
    ) -> AuthzDecision:
        self.calls.append(chain[-1].id)
        if permission is None or chain[-1].id in self.allowed:
            return AuthzDecision(allowed=True)
        return AuthzDecision(allowed=False, reason_code=self.reason_code)


def workspace_ref(h: Harness, *, other: bool = False) -> ScopeRef:
    workspace = h.seed.other_workspace_id if other else h.seed.workspace_id
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(workspace))


def resolving(resolver: Callable[[Any, UnitOfWork], Any], **changes: Any) -> Harness:
    spec = replace(GET_ECHO, scope_of=None, scope_resolver=resolver, **changes)
    return build_harness(manifests=(manifest(queries=(spec,)),))


def ask(h: Harness) -> Any:
    return h.bus.ask(GetEcho(workspace_id=h.seed.workspace_id), actor=h.actor, meta=h.meta())


def test_the_bus_authorizes_the_resolved_scope_and_binds_the_handler_to_it() -> None:
    seen: list[Any] = []

    def handler(query: GetEcho, ctx: Any, uow: UnitOfWork) -> GetEchoResult:
        seen.append((ctx.scope, uow))
        return GetEchoResult(texts=())

    h = resolving(lambda query, uow: workspace_ref(h, other=True), handler=handler)
    assert ask(h) == GetEchoResult(texts=())
    assert h.authorizer.calls[-1].scope_id == h.seed.other_workspace_id  # not the workspace the DTO names
    assert seen[0][0] == workspace_ref(h, other=True)


def test_the_resolver_and_the_handler_share_one_unit_of_work() -> None:
    units: list[UnitOfWork] = []

    def resolver(query: GetEcho, uow: UnitOfWork) -> ScopeRef:
        units.append(uow)
        return workspace_ref(h)

    def handler(query: GetEcho, ctx: Any, uow: UnitOfWork) -> GetEchoResult:
        units.append(uow)
        return GetEchoResult(texts=())

    h = resolving(resolver, handler=handler)
    ask(h)
    assert len(units) == 2
    assert units[0] is units[1]
    assert units[0].readonly is True
    assert h.backend.peak_active == 1


@pytest.mark.parametrize("unknown", ["none", "not_found"])
def test_an_unknown_resource_fails_closed_on_the_instance_scope(unknown: str) -> None:
    called: list[str] = []

    def resolver(query: GetEcho, uow: UnitOfWork) -> None:
        if unknown == "not_found":
            raise NotFound(ErrorCode.NOT_FOUND, "no such resource")

    def handler(query: GetEcho, ctx: Any, uow: UnitOfWork) -> GetEchoResult:
        called.append("handler")
        return GetEchoResult(texts=())

    h = resolving(resolver, handler=handler)
    h.authorizer.authorize = ScopedAuthorizer(set()).authorize
    with pytest.raises(Forbidden) as raised:
        ask(h)
    assert called == []  # nothing was read for the caller
    assert raised.value.details == {
        "permission": "demo.read",
        "scope": None,
        "reason_code": "ROLE_LACKS_PERMISSION",
    }
    (row,) = h.audit()
    assert row.decision == "denied"
    assert row.target["scope"] == {"kind": "instance", "id": str(h.seed.instance_id)}


def test_a_holder_of_the_instance_right_reaches_the_handler_for_an_unknown_resource() -> None:
    def handler(query: GetEcho, ctx: Any, uow: UnitOfWork) -> GetEchoResult:
        assert ctx.scope.kind is ScopeKind.INSTANCE
        raise NotFound(ErrorCode.NOT_FOUND, "no such resource")

    h = resolving(lambda query, uow: None, handler=handler)
    with pytest.raises(NotFound):
        ask(h)
    assert h.authorizer.calls[-1].scope_id == h.seed.instance_id


def test_a_denial_on_a_resolved_scope_names_neither_the_scope_nor_the_reason() -> None:
    h = resolving(lambda query, uow: workspace_ref(h, other=True))
    h.authorizer.authorize = ScopedAuthorizer({h.seed.workspace_id}, reason_code="NO_MEMBERSHIP").authorize
    with pytest.raises(Forbidden) as raised:
        ask(h)
    assert str(h.seed.other_workspace_id) not in repr(raised.value.details)
    assert str(h.seed.other_workspace_id) not in str(raised.value)
    assert raised.value.details == {
        "permission": "demo.read",
        "scope": None,
        "reason_code": "ROLE_LACKS_PERMISSION",
    }
    (row,) = h.audit()  # the audit row is server-side: it keeps the real scope and the real reason
    assert (row.decision, row.reason_code) == ("denied", "NO_MEMBERSHIP")
    assert row.target["scope"] == {"kind": "workspace", "id": str(h.seed.other_workspace_id)}


def test_a_scope_the_request_names_is_still_reported_as_before() -> None:
    h = build_harness()
    h.authorizer.deny_all()
    with pytest.raises(Forbidden) as raised:
        ask(h)
    assert raised.value.details["scope"] == str(h.seed.workspace_id)


def test_a_resolver_that_answers_anything_but_a_scope_is_a_defect_not_a_grant() -> None:
    h = resolving(lambda query, uow: "workspace")
    with pytest.raises(InternalError):
        ask(h)
    assert h.authorizer.calls == []


def test_a_resolver_failure_other_than_not_found_reaches_nobody() -> None:
    def resolver(query: GetEcho, uow: UnitOfWork) -> ScopeRef:
        raise RuntimeError("boom")

    h = resolving(resolver)
    with pytest.raises(InternalError) as raised:
        ask(h)
    assert "boom" not in str(raised.value)
    assert h.authorizer.calls == []


def test_a_command_resolves_authorizes_and_records_its_denial_like_a_query() -> None:
    spec = replace(ECHO, scope_of=None, scope_resolver=lambda cmd, uow: workspace_ref(h, other=True))
    h = build_harness(manifests=(manifest(commands=(spec,)),))
    h.authorizer.authorize = ScopedAuthorizer({h.seed.workspace_id}).authorize
    with pytest.raises(Forbidden) as raised:
        h.bus.dispatch(Echo(workspace_id=h.seed.workspace_id, text="x"), actor=h.actor, meta=h.meta())
    assert raised.value.details["scope"] is None
    assert h.events() == []  # the handler never ran
    (row,) = h.audit()
    assert row.target["scope"] == {"kind": "workspace", "id": str(h.seed.other_workspace_id)}


def test_a_command_replay_authorizes_the_resolved_scope_again() -> None:
    spec = replace(ECHO, scope_of=None, scope_resolver=lambda cmd, uow: workspace_ref(h))
    h = build_harness(manifests=(manifest(commands=(spec,)),))
    cmd = Echo(workspace_id=h.seed.workspace_id, text="x")
    first = h.bus.dispatch(cmd, actor=h.actor, meta=h.meta("key-1"))
    again = h.bus.dispatch(cmd, actor=h.actor, meta=h.meta("key-1"))
    assert first == again
    assert len(h.events()) == 1  # replayed from the receipt, the handler ran once
    assert [call.scope_id for call in h.authorizer.calls] == [h.seed.workspace_id] * 2


# --------------------------------------------------------------------------------------------- registry
def build(**changes: Any) -> BusRegistry:
    schemas = SchemaRegistry.load(SCHEMA_ROOT)
    spec = replace(GET_ECHO, **changes)
    return BusRegistry.build(
        (manifest(queries=(spec,)),),
        schemas=schemas,
        permission_catalog=PERMISSIONS,
        disabled_modules=frozenset(),
    )


def test_the_registry_accepts_a_resolver_in_place_of_a_scope_of() -> None:
    registry = build(scope_of=None, scope_resolver=lambda query, uow: None)
    assert registry.query_by_name("demo.get_echo").scope_resolver is not None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"scope_resolver": lambda query, uow: None}, "exclude each other"),
        ({"scope_of": None, "scope_resolver": "artifacts"}, "scope_resolver must be a callable"),
        ({"scope_of": None, "scope_resolver": lambda query: None}, "scope_resolver must be a callable"),
    ],
)
def test_the_registry_refuses_a_malformed_or_doubled_scope_source(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(BusRegistryError) as raised:
        build(**changes)
    assert message in str(raised.value)
