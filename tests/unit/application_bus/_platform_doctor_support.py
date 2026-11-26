"""``platform.doctor`` handler, registration and composition (kernel-platform §5.6, settings §A.14).

The memory composition runs with an authorizer that grants ``config.read`` per (principal, scope) only, not
allow-all and not SYSTEM. Spy repositories log every inventory and config read with the identity of the UoW
working copy, so the tests prove that authorization comes first, in the same read-only UoW, and that a denied
actor reads nothing. Registered checks run only in ``App.doctor.collect`` (host-side, outside every unit of
work); the query reads their recorded reports and the restart observation through the ``DoctorRunner``
gateway: the default composition adapter (``DoctorCheckCollector`` and this process's loader), or a fake
runner for the error paths. Synthetic callbacks only; no network.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from fakes.app import FakeScopeChain
from skm.adapters.memory.config_store import increment_config_generation, write_config_entry
from skm.adapters.memory.core.scopes import MemoryScopeRegistry
from skm.adapters.memory.core.state import MemoryBackendState
from skm.application_bus.context import QueryContext
from skm.application_bus.platform.doctor import (
    RESTART_PENDING,
    handle,
)
from skm.application_bus.ports import (
    AuthzDecision,
    CurrentProcessObservation,
    DoctorRunner,
    RegisteredCheckReport,
)
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.generated.documents import CheckResult
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef, ScopeRegistry
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.keys import Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import ConfigStore, ScopeTree, StoredContribution
from skm.platform.generated.queries import Doctor
from skm.platform.generated.results import DoctorResult
from skm.platform.logging.logger import get_logger
from skm.platform.system_clock import SystemClock

OWNER = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")), PrincipalKind.HUMAN, "owner")
STRANGER = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b2")), PrincipalKind.HUMAN, "stranger")
INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
WORKSPACE = ScopeId(UUID("01900000-0000-7000-8000-000000000002"))
PROJECT = ScopeId(UUID("01900000-0000-7000-8000-000000000003"))
PLAN = ScopeId(UUID("01900000-0000-7000-8000-000000000004"))
RUN = ScopeId(UUID("01900000-0000-7000-8000-000000000005"))
HOST = ScopeId(UUID("01900000-0000-7000-8000-000000000006"))
SECRET = "Hunter2-Quartz-Lantern!"
RESULT_URN = "urn:skm:platform:result:doctor:v1"


class StateProbe:
    """Pseudo port: ``uow.repo(StateProbe)`` is the working copy of that unit of work."""


@dataclass
class ScopedAuthorizer:
    """Allows exactly the (principal, permission, scope id) grants; logs the UoW of every decision."""

    grants: frozenset[tuple[UUID, str, UUID]]
    log: list[tuple[Any, ...]]

    def authorize(
        self, uow: UnitOfWork, actor: Actor, permission: str, chain: tuple[ScopeRecord, ...]
    ) -> AuthzDecision:
        state = uow.repo(StateProbe)
        self.log.append(("authorize", id(state), uow.readonly, getattr(uow, "isolation", None)))
        if (actor.principal_id, permission, chain[-1].id) in self.grants:
            return AuthzDecision(allowed=True)
        return AuthzDecision(allowed=False, reason_code="NO_MEMBERSHIP")


class SpyScopes:
    def __init__(self, state: MemoryBackendState, log: list[tuple[Any, ...]]) -> None:
        self._inner = MemoryScopeRegistry(state)
        self._state = state
        self._log = log

    def list_scopes(self, *, after: ScopeId | None = None, limit: int = 100) -> tuple[ScopeRecord, ...]:
        page = self._inner.list_scopes(after=after, limit=limit)
        self._log.append(("list_scopes", id(self._state), limit, len(page)))
        return page

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class SpyStore:
    def __init__(self, state: MemoryBackendState, log: list[tuple[Any, ...]]) -> None:
        from skm.adapters.memory.config_store import MemoryConfigStore

        self._inner = MemoryConfigStore(state)
        self._state = state
        self._log = log

    def generation(self) -> int:
        self._log.append(("config", id(self._state)))
        return self._inner.generation()

    def entries_for(self, scope_ids: Any) -> Any:
        self._log.append(("config", id(self._state)))
        return self._inner.entries_for(scope_ids)

    def pending_writes(self) -> bool:
        return self._inner.pending_writes()


@dataclass
class FakeRunner:
    """A ``DoctorRunner`` whose observation, catalog and recorded reports are given; it records every call."""

    result: object = None
    error: Exception | None = None
    ids: object = frozenset[str]()
    recorded: object = ()
    reports_error: Exception | None = None
    calls: list[tuple[object, object]] = field(default_factory=list[tuple[object, object]])
    asked: list[frozenset[str] | None] = field(default_factory=list[frozenset[str] | None])

    def observe(self, store: ConfigStore, scopes: ScopeTree) -> CurrentProcessObservation:
        self.calls.append((store, scopes))
        if self.error is not None:
            raise self.error
        return self.result  # type: ignore[return-value]

    def check_ids(self) -> frozenset[str]:
        if isinstance(self.ids, Exception):
            raise self.ids
        return self.ids  # type: ignore[return-value]

    def reports(self, only: frozenset[str] | None) -> tuple[RegisteredCheckReport, ...]:
        self.asked.append(only)
        if self.reports_error is not None:
            raise self.reports_error
        return self.recorded  # type: ignore[return-value]


def meta() -> RequestMeta:
    return RequestMeta("req_" + uuid4().hex[:26], Surface.CLI, None, SystemClock().now())


def make_app(
    tmp_path: Path,
    *,
    grants: frozenset[tuple[UUID, str, UUID]] | None = None,
    observer: object | None = None,
) -> tuple[App, list[tuple[Any, ...]]]:
    log: list[tuple[Any, ...]] = []
    authorizer = ScopedAuthorizer(
        grants if grants is not None else frozenset({(OWNER.principal_id, "config.read", INSTANCE)}), log
    )
    app = build_app(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=authorizer,
            scopes=FakeScopeChain(),
            repositories={
                StateProbe: lambda state: state,
                ScopeRegistry: lambda state: SpyScopes(state, log),
                ConfigStore: lambda state: SpyStore(state, log),
            },
            gateways=(
                None if observer is None else GatewayTable({DoctorRunner: observer}, "control_plane_gateway")
            ),
        ),
    )
    return app, log


def seed(app: App, *, full: bool = True) -> None:
    with app.uow_factory(meta()) as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        if full:
            ws = WorkspaceId(WORKSPACE)
            scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws)
            scopes.create(PROJECT, ScopeKind.PROJECT, parent=WORKSPACE, workspace_id=ws)
            scopes.create(PLAN, ScopeKind.PLAN, parent=PROJECT, workspace_id=ws)
            scopes.create(RUN, ScopeKind.RUN, parent=PLAN, workspace_id=ws)
            scopes.create(HOST, ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
        uow.commit()


def write(app: App, scope_id: UUID, key: str, value: object) -> None:
    with app.uow_factory(meta()) as uow:
        state = cast("MemoryBackendState", uow.repo(StateProbe))
        entry = StoredContribution(uuid4(), key, "set", cast("JsonValue", value), False, 1)
        write_config_entry(state, scope_id, entry)
        increment_config_generation(state)
        uow.commit()


def start_process(app: App, host: UUID | None = None, level: Level = Level.HOST) -> None:
    with app.uow_factory(meta(), readonly=True) as uow:
        target = None if host is None else ConfigScopeRef(level, host)
        app.config.start_process(uow.repo(ConfigStore), uow.repo(ScopeTree), target)


def ask(app: App, query: Doctor | None = None, actor: Actor = OWNER) -> DoctorResult:
    result = app.client(actor=actor, surface=Surface.CLI).ask(query or Doctor())
    assert isinstance(result, DoctorResult)
    return result


def detail(check: CheckResult) -> dict[str, Any]:
    return json.loads(check.details.detail)


def restart(result: DoctorResult) -> list[CheckResult]:
    return [check for check in result.checks if check.id == RESTART_PENDING]


def run_handler(app: App, query: Doctor, gateways: Any, *, chain_of: UUID = INSTANCE) -> DoctorResult:
    """The handler without the bus, in one read-only UoW, for the gateway error paths."""
    with app.uow_factory(meta(), readonly=True, isolation=Isolation.REPEATABLE_READ) as uow:
        chain = uow.repo(ScopeRegistry).ancestors(ScopeId(chain_of))
        effective = app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
        ctx = QueryContext(
            actor=OWNER,
            meta=meta(),
            scope=ScopeRef(chain[-1].kind, chain[-1].id),
            scope_chain=chain,
            clock=SystemClock(),
            config=effective,
            log=get_logger("modules.platform"),
            gateways=gateways,
        )
        return handle(query, ctx, uow)


def with_observer(result: object = None, error: Exception | None = None) -> tuple[FakeRunner, GatewayTable]:
    observer = FakeRunner(result=result, error=error)
    return observer, GatewayTable({DoctorRunner: observer}, "control_plane_gateway")


class NoGateways:
    def get(self, port: type[Any]) -> Any:
        raise AssertionError("an absent gateway must not be requested")

    def has(self, port: type[object]) -> bool:
        return False


def _observation(**changes: Any) -> CurrentProcessObservation:
    values: dict[str, Any] = {
        "state": "observed",
        "instance_scope_id": INSTANCE,
        "host_target": None,
        "process_generation": 3,
        "pending": (),
    }
    values.update(changes)
    return CurrentProcessObservation(**values)
