"""An HTTP-started run completes with a remote worker and persisted PostgreSQL state."""

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from e2e.test_http_worker import _api, _run_remote, _Wire
from fixtures.execution.harness import RecoverySide, recovery
from fixtures.execution.single_run import single_run, successful_script
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.execution.ports import RunRepository, StageRepository
from support.client_transport import http_client
from support.http_server import loopback_server
from support.pg import clean_test_database, pg_session, test_database
from unit.execution.application._support import set_setting

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]

pytestmark = [pytest.mark.e2e, pytest.mark.pg]


def test_http_run_completes_with_a_worker_without_database_credentials(
    recovery: RecoverySide, tmp_path: Path
) -> None:
    side = recovery
    set_setting(side, "worker.disk_min_bytes", 0)
    owner: Any = side.client.dispatch(access.CreateToken("HTTP lifecycle owner"))
    wire = _Wire(tmp_path / "remote" / "state")
    wire.state.mkdir(mode=0o700, parents=True)
    with ExitStack() as stack:
        endpoint = stack.enter_context(loopback_server(_api(side, wire)))
        client = http_client(stack, endpoint, tmp_path, owner.secret, side.clock)
        remote_side = replace(side, client=client)
        case = single_run(remote_side)
        before: Any = client.ask(execution.GetRun(case.run.id))
        assert before.status == "running"
        script = successful_script(side, case.task.display_key)
        result = _run_remote(side, endpoint, wire, case=case, scenario_path=script)
        assert result.returncode == 0, result.stderr + result.stdout
        assert not wire.errors, wire.errors
        after: Any = client.ask(execution.GetRun(case.run.id))
        assert after.status == "succeeded", (after, result.stdout, result.stderr)
        assert after.bundle_digest == before.bundle_digest
        assert after.revision_no == before.revision_no

    assert any(path.endswith("/runs") and key for path, key, _ in wire.calls)
    assert any(path.endswith("/result") and key for path, key, _ in wire.calls)
    with side.uow(readonly=True) as uow:
        run = uow.repo(RunRepository).get(case.run.id)
        assert run.revision_id == case.run.revision_id
        assert run.status.value == "succeeded"
        history = uow.repo(StageRepository).history(case.attempt.id)
        assert len(history.of_stage("execute")) == 1
        assert history.of_stage("execute")[0].record.outcome_kind == "success"
