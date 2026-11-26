"""P07.09: real CLI main and embedded App, including denied and stale execution requests."""

from __future__ import annotations

import json
from dataclasses import replace
from io import StringIO
from typing import Any
from uuid import UUID

import pytest

from contracts.execution.seed_helpers import seed_bundle, seed_run
from e2e.cli._worker_production import ProductionWorker
from e2e.cli._worker_production import production_worker as production_worker
from e2e.test_m1_config_on_postgres import scratch as scratch
from skm.application_bus.client import SkmClient
from skm.entrypoints.cli.main import Backend, main
from skm.modules.execution.domain.run import RunKind, RunStatus
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.generated.queries import GetRun
from skm.modules.execution.ports import TaskRepository
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import carry_case, decision_case, manual_case, seeded
from unit.execution.application._support import side as side


def invoke(
    side: Any, *args: str, client: Any = None, host: Any = None, human: bool = False
) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    attached: SkmClient = client if client is not None else side.client

    class DiagnosedClient:
        def __init__(self) -> None:
            self.dispatch = attached.dispatch
            self.ask_with_meta = attached.ask_with_meta
            self.events = attached.events
            self.upload_blob = attached.upload_blob
            self.open_file_version_content = attached.open_file_version_content
            self.new_idempotency_key = attached.new_idempotency_key

        def ask(self, query: object) -> object:
            try:
                return attached.ask(query)
            except Exception as error:
                if error.__cause__ is not None:
                    import traceback

                    err.write("".join(traceback.format_exception(error)))
                raise

    backend = Backend(DiagnosedClient(), host_factory=host, instance_id=side.app.instance_id)
    code = main(
        [*([] if human else ["--json"]), *args],
        environ={"HOME": "/nonexistent", "SKM_WORKSPACE": str(side.ws), "SKM_PROJECT": str(side.proj)},
        stdout=out,
        stderr=err,
        backend=lambda *_: backend,
    )
    return code, out.getvalue(), err.getvalue()


def result(side: Any, *args: str, **kwargs: Any) -> Any:
    code, out, err = invoke(side, *args, **kwargs)
    assert code == 0, f"CLI exit {code}\nstdout: {out}\nstderr: {err}"
    envelope = json.loads(out)
    assert envelope["schema"] == "urn:skm:cli:envelope:v1"
    assert envelope["ok"]
    return envelope["result"]


def test_readiness_start_selection_inspection_and_controls(side: Any) -> None:
    ready = result(side, "run", "readiness", str(side.plan1), "--revision", str(side.rev2))
    assert ready["status"] in {"ready", "ready_with_advisories"}
    started = result(
        side,
        "run",
        "start",
        str(side.plan1),
        "--revision",
        str(side.rev2),
        "--tasks",
        "P1.1/U1",
        "--phase",
        "P1",
        "--stop-after",
        "P1.1/U1",
        "--set",
        "budgets.run.max_usd=12",
        "--reason",
        "selection exercise",
    )
    rid = started["run_id"]
    view = result(side, "run", "show", rid, "--tasks", "--graph")
    assert view["selection"]
    assert "pause_source" in view
    assert "stop_code" in view
    assert "blocking_reasons" in view
    assert "health" in view
    assert result(side, "run", "list", "--project", str(side.proj), "--plan", str(side.plan1), "--all")[
        "items"
    ]
    for verb in ("budget", "health", "timeline", "tasks"):
        assert result(side, "run", verb, rid) is not None
    with side.uow(readonly=True) as uow:
        task = uow.repo(TaskRepository).list_for_run(UUID(rid))[0]
    assert result(side, "run", "task", task.display_key, "--run", rid)["task_id"] == str(task.id)
    assert result(side, "run", "pause", rid, "--reason", "owner pause")["status"] == "paused"
    assert result(side, "run", "show", rid)["pause_source"] == "owner"
    assert result(side, "run", "resume", rid)["status"] in {"running", "ready"}
    assert result(side, "run", "cancel", rid, "--yes", "--reason", "done")["status"] == "cancelled"
    assert invoke(side, "run", "show", rid)[0] == 6


@pytest.mark.parametrize(
    ("flag", "key"), [("--tasks", "missing"), ("--phase", "missing"), ("--stop-after", "missing")]
)
def test_unknown_selection_is_not_found(side: Any, flag: str, key: str) -> None:
    code, out, _ = invoke(side, "run", "start", str(side.plan1), "--revision", str(side.rev2), flag, key)
    assert code == 1
    assert json.loads(out)["error"]["code"] == "NOT_FOUND"


def test_start_uses_same_workflow_and_overrides_for_readiness(side: Any) -> None:
    view = result(
        side,
        "run",
        "start",
        str(side.plan1),
        "--revision",
        str(side.rev2),
        "--workflow",
        "reviewed-development",
        "--set",
        "execution.parallel.max_units=2",
    )
    assert view["task_count"] > 0


def test_reconfigure_explicit_and_handshake_cas_never_retry(side: Any) -> None:
    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)
    before = side.client.ask(GetRun(run.id))
    applied = result(
        side, "run", "reconfigure", str(run.id), "execution.parallel.max_units=2", "--reason", "drained"
    )
    assert applied
    code, out, _ = invoke(
        side,
        "run",
        "reconfigure",
        str(run.id),
        "execution.parallel.max_units=3",
        "--if-version",
        str(before.row_version),
        "--reason",
        "stale CAS",
    )
    assert code == 6
    assert json.loads(out)["error"]["code"] == "VERSION_CONFLICT"
    current = side.client.ask(GetRun(run.id))
    assert current.row_version > before.row_version
    code, _, err = invoke(
        side,
        "run",
        "reconfigure",
        str(run.id),
        "execution.parallel.max_units=3",
        "--if-version",
        str(before.row_version),
        human=True,
    )
    assert code == 6
    assert "VERSION_CONFLICT" in err
    assert "pause" in err
    assert "drain" in err


def test_usage_not_ready_and_skip_readiness_codes(side: Any) -> None:
    assert invoke(side, "run", "reconfigure", str(side.new_id()))[0] == 2
    assert invoke(side, "worker", "start", "--capacity", "0")[0] == 2
    code, out, _ = invoke(side, "run", "readiness", str(side.plan1), "--revision", str(side.rev1))
    assert code == 1
    assert json.loads(out)["result"]["status"] == "not_ready"
    code, out, _ = invoke(
        side, "run", "start", str(side.plan1), "--revision", str(side.rev2), "--skip-readiness"
    )
    assert code == 6
    assert json.loads(out)["error"]["code"] == "READINESS_REQUIRED"


def test_inbox_answer_show_and_scope_denial(side: Any) -> None:
    run, _, _, request = decision_case(side)
    entries = result(side, "inbox", "list", "--run", str(run.id), "--kind", "question")
    assert any(row["request_id"] == str(request.id) for row in entries["items"])
    shown = result(side, "inbox", "show", str(request.id), "--run", str(run.id))
    assert shown["revision"] == request.revision
    code, out, _ = invoke(
        side, "inbox", "answer", str(request.id), "--run", str(run.id), "--option", "unknown"
    )
    assert code == 1
    assert not json.loads(out)["ok"]
    answered = result(side, "inbox", "answer", str(request.id), "--run", str(run.id), "--option", "continue")
    assert answered
    code, out, _ = invoke(side, "inbox", "answer", str(request.id), "--run", str(run.id), "--answer", "again")
    assert code == 6
    assert json.loads(out)["error"]["code"] == "INVALID_TRANSITION"
    restricted = side.restricted_client(["run.read"], scope_id=run.id)
    assert (
        invoke(side, "inbox", "list", "--run", str(run.id), "--kind", "question", client=restricted)[0] == 5
    )


def test_manual_verdict_deviation_and_carry_forward(side: Any) -> None:
    _, _, _, check = manual_case(side)
    assert result(side, "inbox", "verdict", str(check.id), "pass", "--comment", "verified")
    _, task, _, _ = decision_case(side, code="NOT_ACCEPTABLE")
    assert result(side, "run", "deviation", "accept", str(task.id), "--reason", "owner accepts")
    _, source, _, target, _ = carry_case(side)
    assert result(
        side,
        "run",
        "carry-forward",
        "--from",
        str(source.id),
        "--to",
        str(target.id),
        "--reason",
        "compatible",
    )


def test_skip_restart_and_real_authority_rejections(side: Any) -> None:
    run, task, _ = seeded(side, task_status=TaskStatus.FAILED)
    assert result(side, "run", "restart", str(task.id), "--yes", "--reason", "try again")
    _, other, _ = seeded(side, task_status=TaskStatus.READY)
    assert result(side, "run", "skip", str(other.id), "--reason", "owner scope decision")
    denied = side.restricted_client(["run.read"], scope_id=run.id)
    assert invoke(side, "run", "pause", str(run.id), client=denied)[0] == 5
    assert invoke(side, "run", "cancel", str(run.id))[0] == 1


def test_locator_redacted_by_real_permissions_and_step_context(side: Any) -> None:
    from contracts.execution.seed_helpers import seed_stage, seed_step
    from skm.modules.execution.domain.environment import (
        EnvironmentKind,
        EnvironmentState,
        ExecutionEnvironment,
        attempt_branch,
    )
    from skm.modules.execution.ports import EnvironmentRepository

    run, _, attempt = seeded(side)
    manifest = side.make_final_manifest()
    locator = "/private/checkout/locator"
    with side.uow() as uow:
        uow.repo(EnvironmentRepository).upsert(
            ExecutionEnvironment(
                side.new_id(),
                attempt.id,
                side.host1,
                EnvironmentKind.GIT_WORKTREE,
                (),
                attempt_branch(attempt.id),
                locator,
                EnvironmentState.READY,
                side.clock.now(),
                None,
                None,
            )
        )
        stage = seed_stage(side, uow, attempt)
        step = seed_step(side, uow, attempt, stage, manifest_id=manifest)
        uow.commit()
    restricted = side.restricted_client(["run.read"], scope_id=run.id, owner_token=True)
    hidden = result(side, "run", "attempt", str(attempt.id), client=restricted)
    assert locator not in json.dumps(hidden)
    assert "local_locator" not in json.dumps(hidden)
    visible = result(side, "run", "attempt", str(attempt.id))
    assert locator in json.dumps(visible)
    assert result(side, "run", "step", str(step.id))
    assert result(side, "run", "step-context", str(step.id), "--project", str(side.proj), "--blocks")
    assert result(
        side, "run", "step-context", str(step.id), "--project", str(side.proj), "--diff", str(step.id)
    )
    assert result(side, "run", "logs", str(attempt.id))
    assert invoke(side, "run", "logs", str(attempt.id), "--step", str(side.new_id()), "--transcript")[0] == 1


@pytest.mark.parametrize("section", ["execution", "budgets", "worker"])
def test_settings_explain_registered_sections(side: Any, section: str) -> None:
    view = result(side, "config", "explain", "--scope", "project:" + str(side.proj), "--section", section)
    assert view


def test_worker_once_uses_real_claim_protocol(
    side: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(100 * 1024**3, 10 * 1024**3, 90 * 1024**3),
    )
    from skm.application_bus.host import HostContext
    from skm.bootstrap.host_services import build_worker_services
    from skm.kernel.cancel import CancelSource
    from skm.kernel.gateways import GatewayTable
    from skm.kernel.scopes import ScopeKind, ScopeRef
    from skm.modules.execution.host.context import WorkerServices
    from skm.modules.execution.host.stages.registry import StageRegistry
    from skm.platform.config.store import ConfigStore, ScopeTree

    services = build_worker_services(
        tmp_path, stages=StageRegistry(()), context_inputs=None, resolve=lambda _: None
    )
    with side.uow(readonly=True) as uow:
        config = side.app.config.effective_host(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.HOST, side.host1)
        )
    host = HostContext(
        side.worker1_client,
        GatewayTable({WorkerServices: services}, "host_gateway"),
        side.host1,
        config,
        object(),
        CancelSource().token,
    )
    code, out, err = invoke(
        side, "worker", "start", "--once", "--capacity", "3", "--worker", str(side.worker1), host=lambda: host
    )
    assert code == 4, f"CLI exit {code}\nstdout: {out}\nstderr: {err}"
    assert json.loads(out)["outcome"]["code"] == "NOTHING_TO_CLAIM"
    bad_host = replace(host, client=side.client)
    assert (
        invoke(side, "worker", "start", "--once", "--worker", str(side.worker1), host=lambda: bad_host)[0]
        == 5
    )

    from skm.adapters.runtimes._cli_session.identity import claim_marker
    from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership

    unit_id = side.new_id()
    owner = ProcessOwner(
        side.host1,
        side.worker1,
        side.new_id(),
        side.new_id(),
        "git_effect",
        unit_id,
        "uncertain-launch-fixture",
        str(tmp_path / "identities"),
    )
    ownership = ProcessOwnership(owner, "pgroup_best_effort", f"pgroup:{unit_id}")
    marker = claim_marker(tmp_path / "identities", ownership)
    code, out, err = invoke(
        side, "worker", "start", "--once", "--worker", str(side.worker1), host=lambda: host
    )
    assert code == 6, f"CLI exit {code}\n{out}\n{err}"
    assert json.loads(out)["result"]["slots"][0]["reason"] == "cleanup_unconfirmed"
    assert json.loads(marker.read_text())["launching"] is True


@pytest.mark.pg
def test_production_worker_once_and_token_rotation(production_worker: ProductionWorker) -> None:
    worker = production_worker
    worker.expire_soon()
    for _ in range(2):
        code, out, err = worker.invoke("--once", "--capacity", "3")
        assert code == 4, out + err
        assert json.loads(out)["outcome"]["code"] == "NOTHING_TO_CLAIM"
        assert worker.secret not in out + err
        assert worker.token_path.read_text().strip() not in out + err
    worker.assert_rotated()


@pytest.mark.pg
def test_production_worker_sigterm_cancels_capacity_slots(production_worker: ProductionWorker) -> None:
    code, envelope, err = production_worker.stop_with_sigterm()
    assert code == 0, err
    slots = envelope["result"]["slots"]
    assert len(slots) == 2
    assert all(item["outcome"] == "stopped" and item["assignments"] == 0 for item in slots)


@pytest.mark.parametrize(
    ("default", "interactive"), [("workspace-contained", "read-only"), ("read-only", "workspace-contained")]
)
def test_policy_check_selects_interactive_profile(side: Any, default: str, interactive: str) -> None:
    from unit.execution.application._support import set_setting

    set_setting(side, "policy.default_profile", default)
    set_setting(side, "policy.interactive.profile", interactive)
    roots = json.dumps(
        {
            "worktrees": {"repo": "/owned/worktree"},
            "materials": None,
            "tmp": None,
            "home": None,
            "safe_dirs": [],
            "protected": [],
            "remote_hosts": [],
        }
    )
    args = (
        "policy",
        "check",
        '{"tool":"web.search","query":"example"}',
        "--scope",
        "project:" + str(side.proj),
        "--roots",
        roots,
    )
    expected = {"read-only": "deny", "workspace-contained": "allow"}
    assert result(side, *args)["outcome"] == expected[interactive]
    assert result(side, *args, "--mode", "agent_unattended")["outcome"] == expected[default]
    assert result(side, *args, "--profile", "workspace-contained")["outcome"] == "allow"


def test_inbox_lists_approvals_for_project_owned_run(side: Any) -> None:
    with side.uow() as uow:
        run = seed_run(side, uow, kind=RunKind.ADHOC, inline_spec_file_version_id=side.fv1)
        seed_bundle(side, uow, run.id)
        uow.commit()

    entries = result(side, "inbox", "list", "--run", str(run.id), "--kind", "approval")
    assert entries["approvals"] == []


def test_inbox_policy_approval_denial_and_preflight(side: Any) -> None:
    from skm.modules.policy.generated.commands import EffectKind, ProposeIntent
    from unit.execution.application._support import set_setting
    from unit.policy.application.harness import push_args

    set_setting(
        side, "policy.ceiling.external_effects", ["git_commit", "git_push", "pr_create", "message", "publish"]
    )
    run, _, _ = seeded(side)
    scope = "run:" + str(run.id)
    first = side.client.dispatch(
        ProposeIntent(run.id, scope, EffectKind.GIT_PUSH, push_args(), "owner request")
    )
    assert first.state == "proposed"
    code, out, _ = invoke(side, "inbox", "approve", str(first.intent_id), "--digest", "sha256:" + "0" * 64)
    assert code == 5
    assert json.loads(out)["error"]["code"] == "APPROVAL_MISMATCH"
    entries = result(side, "inbox", "list", "--run", str(run.id), "--kind", "approval", "--all")
    assert any(item["intent_id"] == str(first.intent_id) for item in entries["approvals"])
    assert result(
        side,
        "inbox",
        "approve",
        str(first.intent_id),
        "--expires-in",
        "30m",
        "--single-use",
        "--reason",
        "exact arguments",
    )
    second = side.client.dispatch(
        ProposeIntent(run.id, scope, EffectKind.GIT_PUSH, push_args(after_sha="d" * 40), "second request")
    )
    assert result(side, "inbox", "deny", str(second.intent_id), "--reason", "declined")
    assert result(side, "policy", "show", "--scope", scope)
    roots = {
        "worktrees": {"repo": "/owned/worktree"},
        "materials": None,
        "tmp": None,
        "home": None,
        "safe_dirs": [],
        "protected": [],
        "remote_hosts": [],
    }
    assert result(
        side,
        "policy",
        "check",
        '{"tool":"fs.read","path":"/owned/worktree/src/a.py"}',
        "--scope",
        scope,
        "--roots",
        json.dumps(roots),
    )
    assert invoke(side, "policy", "check", "broken-json", "--scope", scope, "--roots", "{}")[0] == 1


def test_reconfigure_handshake_detects_concurrent_real_write(side: Any) -> None:
    from skm.modules.execution.generated.commands import ReconfigureRun

    run, _, _ = seeded(side, run_status=RunStatus.PAUSED)

    class RacingClient:
        def __init__(self) -> None:
            self.writes = 0
            self.raced = False

        def __getattr__(self, name: str) -> Any:
            return getattr(side.client, name)

        def ask(self, query: Any) -> Any:
            value = side.client.ask(query)
            if isinstance(query, GetRun) and not self.raced:
                self.raced = True
                result(
                    side,
                    "run",
                    "reconfigure",
                    str(run.id),
                    "execution.parallel.max_units=1",
                    "--if-version",
                    str(value.row_version),
                    "--reason",
                    "concurrent writer",
                )
            return value

        def dispatch(self, command: Any, **kwargs: Any) -> Any:
            if isinstance(command, ReconfigureRun):
                self.writes += 1
            return side.client.dispatch(command, **kwargs)

    client = RacingClient()
    code, out, _ = invoke(
        side, "run", "reconfigure", str(run.id), "execution.parallel.max_units=3", client=client
    )
    assert code == 6
    assert json.loads(out)["error"]["code"] == "VERSION_CONFLICT"
    assert client.writes == 1


def test_selection_compiles_unaccepted_ancestors_via_cli(side: Any) -> None:
    from copy import deepcopy

    from contracts.execution.harness import _publish_revision
    from skm.modules.planning import public as planning
    from skm.modules.planning.domain.specification import to_document

    with side.uow(readonly=True) as uow:
        doc = to_document(planning.get_revision_specification(uow, side.rev2))
    units = doc["units"]
    assert isinstance(units, list)
    assert units
    first = units[0]
    assert isinstance(first, dict)
    child = deepcopy(first)
    child.update(id=str(side.new_id()), key="P1.1/U2", title="Dependent unit", depends_on=["P1.1/U1"])
    revision = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan1, {"units": [*units, child]}, "current"
    )
    started = result(side, "run", "start", str(side.plan1), "--revision", str(revision), "--tasks", "P1.1/U2")
    view = result(side, "run", "show", started["run_id"])
    assert view["selection"]["task_keys"] == ["P1.1/U2"]
    assert "P1.1/U1" in view["selection"]["compiled_keys"]
    assert "P1.1/U2" in view["selection"]["compiled_keys"]
    assert "@plan_acceptance" not in view["selection"]["compiled_keys"]


def test_semantic_audit_and_visa_cli(side: Any) -> None:
    from unit.execution.application._support import set_setting

    set_setting(side, "execution.readiness.semantic_audit_allowed", True)
    plan = str(side.plan1)
    request = (plan, "--revision", str(side.rev2), "--phase", "P1", "--mode", "progressive_per_phase")
    ready = result(side, "run", "readiness", *request, "--semantic-audit")
    audit = ready["audit_run_id"]
    visa = result(side, "plan", "approve", plan, ready["report_id"], "--reason", "Reviewed first phase")
    code, out, _ = invoke(side, "run", "start", *request, "--visa-id", visa["visa_id"])
    assert code != 0
    assert json.loads(out)["error"]["code"] == "READINESS_REQUIRED"
    result(side, "run", "cancel", audit, "--yes", "--reason", "Close advisory audit")
    started = result(side, "run", "start", *request, "--visa-id", visa["visa_id"])
    view = result(side, "run", "show", started["run_id"])
    assert view["selection"]["phases"] == ["P1"]
