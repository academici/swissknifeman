"""Worker states and capabilities (workspace §4.3, §5.3)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, PrincipalId, WorkerId, WorkspaceId
from skm.modules.workspace.domain.host import HostArch, HostOs, HostPlatform
from skm.modules.workspace.domain.worker import (
    WORKER_TRANSITIONS,
    Worker,
    WorkerCapabilities,
    WorkerState,
    ensure_transition,
    ensure_unconfined_allowed,
    heartbeat,
    is_overdue,
    mark_offline,
    new_worker,
    set_state,
)

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)
PLATFORM = HostPlatform(HostOs.LINUX, HostArch.X86_64)


def caps(**changes: object) -> WorkerCapabilities:
    base = WorkerCapabilities(
        runtimes=("claude_code", "codex"),
        isolation_profiles=("worktree", "container"),
        max_concurrency=4,
        labels=("gpu", "team:core"),
        platform=PLATFORM,
        skm_version="2.0.0",
    )
    return replace(base, **changes)


def worker(state: WorkerState = WorkerState.OFFLINE, *, last: datetime | None = None) -> Worker:
    return Worker(
        id=WorkerId(UUID(int=1)),
        workspace_id=WorkspaceId(UUID(int=2)),
        host_id=HostId(UUID(int=3)),
        principal_id=PrincipalId(UUID(int=4)),
        display_name="w",
        capabilities=caps(),
        state=state,
        last_heartbeat_at=last,
        registered_at=T0,
        row_version=7,
    )


_ALLOWED = {
    (WorkerState.ONLINE, WorkerState.DRAINING),
    (WorkerState.ONLINE, WorkerState.OFFLINE),
    (WorkerState.ONLINE, WorkerState.RETIRED),
    (WorkerState.DRAINING, WorkerState.ONLINE),
    (WorkerState.DRAINING, WorkerState.OFFLINE),
    (WorkerState.DRAINING, WorkerState.RETIRED),
    (WorkerState.OFFLINE, WorkerState.ONLINE),
    (WorkerState.OFFLINE, WorkerState.DRAINING),
    (WorkerState.OFFLINE, WorkerState.RETIRED),
}


@pytest.mark.parametrize("source", list(WorkerState))
@pytest.mark.parametrize("target", list(WorkerState))
def test_transition_table(source: WorkerState, target: WorkerState) -> None:
    allowed = (source, target) in _ALLOWED
    assert (target in WORKER_TRANSITIONS[source]) is allowed
    if allowed:
        ensure_transition(source, target)
    else:
        with pytest.raises(PreconditionFailed) as err:
            ensure_transition(source, target)
        assert err.value.code is ErrorCode.INVALID_TRANSITION


def test_retired_is_terminal_for_every_command() -> None:
    retired = worker(WorkerState.RETIRED)
    for target in (WorkerState.ONLINE, WorkerState.DRAINING, WorkerState.OFFLINE):
        with pytest.raises(PreconditionFailed):
            set_state(retired, target)
    with pytest.raises(PreconditionFailed):
        heartbeat(retired, None, T1)
    assert set_state(retired, WorkerState.RETIRED) is retired


def test_set_state_bumps_the_version_and_same_state_is_a_no_op() -> None:
    online = worker(WorkerState.ONLINE)
    draining = set_state(online, WorkerState.DRAINING)
    assert (draining.state, draining.row_version) == (WorkerState.DRAINING, 8)
    assert set_state(draining, WorkerState.DRAINING) is draining


def test_heartbeat_brings_an_offline_worker_online() -> None:
    result = heartbeat(worker(WorkerState.OFFLINE), None, T1)
    assert (result.state, result.last_heartbeat_at, result.row_version) == (WorkerState.ONLINE, T1, 8)


@pytest.mark.parametrize("state", [WorkerState.ONLINE, WorkerState.DRAINING])
def test_heartbeat_keeps_online_and_draining(state: WorkerState) -> None:
    result = heartbeat(worker(state), None, T1)
    assert result.state is state
    assert result.last_heartbeat_at == T1


def test_heartbeat_updates_capabilities_only_when_given() -> None:
    newer = caps(max_concurrency=8)
    assert heartbeat(worker(), newer, T1).capabilities == newer
    assert heartbeat(worker(), None, T1).capabilities == caps()


def test_mark_offline_is_the_sweepers_transition() -> None:
    assert mark_offline(worker(WorkerState.ONLINE)).state is WorkerState.OFFLINE
    assert mark_offline(worker(WorkerState.DRAINING)).state is WorkerState.OFFLINE
    offline = worker(WorkerState.OFFLINE)
    assert mark_offline(offline) is offline
    retired = worker(WorkerState.RETIRED)
    assert mark_offline(retired) is retired


def test_is_overdue() -> None:
    limit = timedelta(seconds=120)
    live = worker(WorkerState.ONLINE, last=T0)
    assert not is_overdue(live, T0 + limit, limit)
    assert is_overdue(live, T0 + limit + timedelta(seconds=1), limit)
    assert is_overdue(replace(live, state=WorkerState.DRAINING), T0 + limit + timedelta(seconds=1), limit)
    assert is_overdue(worker(WorkerState.ONLINE, last=None), T0 + limit + timedelta(seconds=1), limit)
    for state in (WorkerState.OFFLINE, WorkerState.RETIRED):
        assert not is_overdue(worker(state, last=T0), T0 + timedelta(days=1), limit)


def test_new_worker_starts_offline_without_a_heartbeat() -> None:
    created = new_worker(
        worker_id=WorkerId(UUID(int=1)),
        workspace_id=WorkspaceId(UUID(int=2)),
        host_id=HostId(UUID(int=3)),
        principal_id=PrincipalId(UUID(int=4)),
        display_name="  builder ",
        capabilities=caps(),
        now=T0,
    )
    assert (created.state, created.last_heartbeat_at, created.row_version) == (WorkerState.OFFLINE, None, 1)
    assert created.display_name == "builder"


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_new_worker_display_name_bounds(name: str) -> None:
    with pytest.raises(ValidationFailed):
        new_worker(
            worker_id=WorkerId(UUID(int=1)),
            workspace_id=WorkspaceId(UUID(int=2)),
            host_id=HostId(UUID(int=3)),
            principal_id=PrincipalId(UUID(int=4)),
            display_name=name,
            capabilities=caps(),
            now=T0,
        )


# --- capabilities ---


def test_capabilities_accept_plugin_isolation_profiles() -> None:
    assert (
        caps(isolation_profiles=("worktree", "acme.sandbox:strict")).isolation_profiles[1]
        == "acme.sandbox:strict"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"runtimes": ("a",)},  # shorter than 2 characters
        {"runtimes": ("Codex",)},
        {"runtimes": ("codex", "codex")},
        {"runtimes": tuple(f"rt{i:02d}" for i in range(33))},
        {"isolation_profiles": ()},
        {"isolation_profiles": ("worktree", "worktree")},
        {"isolation_profiles": ("sandbox",)},  # neither built-in nor plugin_id:name
        {"isolation_profiles": ("workspace-contained",)},  # a policy profile, not an isolation profile
        {"max_concurrency": 0},
        {"max_concurrency": 65},
        {"max_concurrency": True},
        {"labels": ("Bad",)},
        {"labels": ("a", "a")},
        {"labels": tuple(f"l{i}" for i in range(33))},
        {"skm_version": "2.0"},
        {"skm_version": "v2.0.0"},
        {"skm_version": "2.0.0\n"},
    ],
)
def test_capabilities_reject(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationFailed) as err:
        caps(**changes)
    assert err.value.code is ErrorCode.SCHEMA_INVALID
    assert str(err.value.details["field"]).startswith("capabilities.")


def test_capability_boundaries_are_accepted() -> None:
    assert caps(max_concurrency=1).max_concurrency == 1
    assert caps(max_concurrency=64).max_concurrency == 64
    assert caps(runtimes=()).runtimes == ()
    assert caps(skm_version="2.0.0-rc.1").skm_version == "2.0.0-rc.1"


def test_unconfined_needs_the_host_to_allow_it() -> None:
    unconfined = caps(isolation_profiles=("none", "worktree"))
    ensure_unconfined_allowed(unconfined, allow_unconfined=True)
    ensure_unconfined_allowed(caps(), allow_unconfined=False)
    with pytest.raises(ValidationFailed) as err:
        ensure_unconfined_allowed(unconfined, allow_unconfined=False)
    assert err.value.details == {
        "field": "capabilities.isolation_profiles",
        "reason": "unconfined_not_allowed",
    }
