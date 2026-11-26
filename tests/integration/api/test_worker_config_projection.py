"""The registered worker HTTP query projects only admitted project settings."""

from integration.api.test_settings_machine_ownership import seed_machine_entries
from integration.api.test_worker_protocol import (
    BASE,
    TestClient,
    checked,
    worker_api,
)
from integration.api.test_worker_protocol import (
    clean_test_database as clean_test_database,
)
from integration.api.test_worker_protocol import (
    exec_side as exec_side,
)
from integration.api.test_worker_protocol import (
    pg_session as pg_session,
)
from integration.api.test_worker_protocol import (
    test_database as test_database,
)
from integration.api.test_worker_protocol import (
    worker_side as worker_side,
)
from skm.kernel.ids import ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from unit.execution.application._support import set_setting


def test_registered_worker_host_config_excludes_machine_inputs(worker_side):
    side, worker_headers, _operator = worker_side
    set_setting(side, "worker.capacity", 3)
    set_setting(side, "runtimes.extra_env_allow", {"codex": ["OPENAI_API_KEY"]})
    with side.uow() as uow:
        seed_machine_entries(
            uow,
            ScopeRef(ScopeKind.INSTANCE, ScopeId(side.app.instance_id)),
            side.owner.principal_id,
            side.clock.now(),
            {
                "runtimes.binaries": {"codex": "/synthetic/machine/runtime"},
                "runtimes.credentials.copy": {"codex": True},
            },
        )
        uow.commit()

    with TestClient(worker_api(side), base_url=BASE) as client:
        snapshot = checked(client.get(f"/api/v1/worker/hosts/{side.host1}/config", headers=worker_headers))

    assert snapshot["values"]["worker.capacity"] == 3
    assert "codex" in snapshot["values"]["runtimes.allowed"]
    for key in ("runtimes.binaries", "runtimes.extra_env_allow", "runtimes.credentials.copy"):
        assert key not in snapshot["values"]
        assert key not in snapshot["invalid"]
