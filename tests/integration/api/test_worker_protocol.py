"""Worker HTTP contract against the real memory and PostgreSQL application buses."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import timedelta
from threading import Event
from time import monotonic
from uuid import UUID

import pytest

from contracts.execution._worker_protocol_support import begin, claim, make_case, worker_claim
from contracts.execution.harness import PEPPER
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_lock_order import _owned_runtime, expire_now, sweep
from contracts.execution.test_step_notes import owned_agent
from fixtures.execution.protocol import add_budget
from integration.api.test_artifacts_routes import put_blob
from security.api.harness import BASE, TestClient
from skm import __version__
from skm.application_bus.ports import IdempotencyStore
from skm.bootstrap.host_services import decode_context_draft
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.access.ports import MembershipRepository
from skm.modules.artifacts.application.upload import bind_embedded_upload
from skm.modules.context import public as context
from skm.modules.context.domain.host_inputs import HostReadStatus
from skm.modules.execution.application import _stage_agent_helpers
from skm.modules.execution.domain.output import OutputMount, output_tree_digest
from skm.modules.execution.ports import (
    AssignmentRepository,
    DecisionRepository,
    EvidenceBindingRepository,
    OutputRepository,
    RunRepository,
    StageRepository,
    StepRepository,
)
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.catalog import ModelStatus
from skm.modules.runtimes.domain.catalog_records import (
    CanonicalModel,
    HostModelAvailability,
    ProviderModelOffering,
)
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.ports import HostModelAvailabilityRepository, ModelCatalogRepository
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.modules.workspace.generated.documents import WorkerCapabilities
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from support.seed import SEED
from unit.execution.application._integration_case import integrated_case, local_request

CLAIM_PATH = "/api/v1/worker/assignments/claim"
HEARTBEAT_PATH = "/api/v1/worker/heartbeat"
SLOT_PATH = "/api/v1/worker/integration-slots"
WORKER_CAPABILITIES = {
    "runtimes": ["codex_cli"],
    "isolation_profiles": ["landlock"],
    "max_concurrency": 4,
    "labels": ["linux"],
    "platform": {"os": "linux", "arch": "x86_64"},
    "skm_version": "2.0.0",
}


def bearer(secret):
    return {"Authorization": f"Bearer {secret}"}


def claim_body(side, **changes):
    return {
        "worker_id": str(side.worker1),
        "host_id": str(side.host1),
        "workspace_id": str(side.ws),
        "offer": {
            "capabilities": ["codex_cli"],
            "environment_kinds": ["git_worktree"],
            "isolation_profiles": ["landlock"],
            "labels": ["linux"],
        },
        **changes,
    }


def worker_api(side, **kwargs):
    def authenticate(secret):
        with side.uow(readonly=True) as uow:
            return access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    core = replace(side.app, authenticator=authenticate)
    bus = core.bus
    kwargs.setdefault("settings", {})
    modules = ("access", "settings", "workspace", "artifacts", "context", "execution")
    api = create_app(
        core,
        route_table=build_route_table(modules),
        registry=bus._registry,
        schema_check=lambda: None,
        no_background=True,
        **kwargs,
    )
    upload, _ = bind_embedded_upload(
        core.uow_factory,
        bus._authorizer,
        bus._scopes,
        core.config,
        core.gateways,
        bus._clock,
        bus._ids,
        bus.dispatch,
        bus.ask,
    )
    mount_blobs(api, upload)
    return api


@pytest.fixture
def worker_side(exec_side):
    if exec_side.dsn:
        # Staging uses the app clock; fenced evidence consumption uses database time.
        with exec_side.uow(readonly=True) as uow:
            exec_side.clock.set(uow.repo(RunRepository).now())
    registered = exec_side.client.dispatch(
        workspace.RegisterWorker(
            exec_side.ws, exec_side.host1, "HTTP worker", WorkerCapabilities.from_json(WORKER_CAPABILITIES)
        )
    )
    owner_token = exec_side.client.dispatch(
        access.CreateToken(name="HTTP operator", principal_id=None, scope_id=None, permissions=None)
    )
    with exec_side.uow(readonly=True) as uow:
        memberships = uow.repo(MembershipRepository)
        assert memberships.get(SEED.instance_id, registered.principal_id) is None
        assert memberships.get(exec_side.ws, registered.principal_id).role is access.Role.WORKER
        actor = access.authenticate_token(
            uow, registered.token_secret, pepper=PEPPER, now=exec_side.clock.now()
        )
    return (
        replace(
            exec_side,
            worker1=registered.worker_id,
            worker1_client=exec_side.app.client(actor=actor, surface=Surface.WORKER),
        ),
        bearer(registered.token_secret),
        bearer(owner_token.secret),
    )


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def problem(response, status, code):
    assert checked(response, status)["code"] == code


def post(client, path, body, key=None, **headers):
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(path, json=body, headers=headers)


def prepare_runtime(side, monkeypatch):
    # Stand in for host capability discovery. All worker commands and context verification are real.
    side.client.dispatch(
        settings.SetValue.from_json(
            {"scope": {"level": "instance"}, "key": "runtimes.allowed", "value": ["codex_cli"]}
        )
    )
    with side.uow() as uow:
        uow.repo(runtimes.HostRuntimeRepository).upsert(
            RuntimeInstallation(
                side.host1,
                "codex_cli",
                "1.0.0",
                "/fake/codex",
                AuthState.OK,
                side.clock.now(),
                {
                    "executable_sha256": "sha256:" + "a" * 64,
                    "verification_key": "sha256:" + "b" * 64,
                    "adapter_version": "1.0.0",
                },
            )
        )
        observed = side.clock.now()
        catalog = uow.repo(ModelCatalogRepository)
        catalog.add_model(CanonicalModel("gpt-5"))
        catalog.upsert_offering(
            ProviderModelOffering(
                "codex_cli",
                "gpt-5",
                "gpt-5",
                "Fixture model",
                128000,
                None,
                (),
                ModelStatus.CONFIRMED,
                observed.date(),
                "inventory",
                None,
            )
        )
        uow.repo(HostModelAvailabilityRepository).upsert(
            HostModelAvailability(
                side.host1,
                "codex_cli",
                "gpt-5",
                runtimes.Effort.HIGH,
                observed,
                observed + timedelta(minutes=5),
            )
        )
        uow.commit()

    def route(_uow, _gateways, request, *, config, pins, as_of):
        assert pins
        assert request.host_id == side.host1
        assert as_of >= observed
        return runtimes.RouteDecision(
            runtime_id="codex_cli",
            model="gpt-5",
            model_class=runtimes.ModelClass.IMPLEMENTATION,
            effort=runtimes.Effort.HIGH,
            effort_flag="high",
            source="role_routing",
            catalog_digest="sha256:" + "c" * 64,
            operation=request.admission.operation,
            admission=request.admission,
            resume_allowance=runtimes.ResumeAllowance(True, False, None, "allowed"),
            context_window_tokens=128000,
            config_mode="isolated",
            self_loads=(),
            degraded=frozenset(),
            rejected=(),
            degraded_details=(),
        )

    monkeypatch.setattr(_stage_agent_helpers, "route_role", route)


def prompt_wire(client, side, ready, claim):
    draft = decode_context_draft(ready["step"]["context"]["draft"])
    blocks = [
        context.HostBlock(
            request.request_id,
            HostReadStatus.SELF_LOADED if request.path == "AGENTS.md" else HostReadStatus.MISSING,
            request.path if request.path == "AGENTS.md" else None,
            None,
            None,
            None,
            None,
        )
        for request in draft.host_inputs
    ]
    facts = context.HostFacts(frozenset(), (), False, {"repo": "1" * 40})
    final = context.finalize(draft, blocks, facts, side.estimator)
    prompt = checked(
        put_blob(client, side.ws, final.rendered_prompt.encode(), "text/plain", "prompt-upload"), 201
    )
    return context.finalize_command(
        draft,
        final,
        blocks,
        facts,
        prompt_staged_blob=prompt,
        claim=context.ContextOwnerClaim(
            UUID(claim["assignment_id"]), UUID(claim["attempt_id"]), side.worker1, claim["fencing_token"]
        ),
        store_content=False,
        runtime_self_loaded=(),
    )


def empty_output(side):
    mount = OutputMount("repo", side.repo_id, "sha1", "1" * 40, "1" * 40, "3" * 40)
    return {
        "algorithm": "skm-output-v2",
        "mounts": [{**asdict(mount), "repository_id": str(mount.repository_id)}],
        "changed_paths": [],
        "outside_write_scope": [],
        "excluded_paths": [],
        "tree_digest": output_tree_digest((mount,), ()),
        "patch_file_version_id": None,
        "diff_stats": {"files": 0, "insertions": 0, "deletions": 0},
        "empty": True,
    }


def assert_secret_free(side, ready, secret):
    token = ready["step"]["runtime_token"]
    assert token["token_id"]
    assert secret not in json.dumps(ready)
    with side.uow(readonly=True) as uow:
        receipt = uow.repo(IdempotencyStore).get(
            side.ws, side.worker1_client._actor.principal_id, "execution.begin_stage", "begin"
        )
        assert receipt is not None
        assert receipt.result == ready
        if side.dsn:
            audit = uow.connection.execute(
                "SELECT * FROM skm_core.audit_records WHERE action=%s", ("execution.begin_stage",)
            ).fetchall()
        else:
            audit = [
                record
                for record in side.app.uow_factory._backend.committed.core.audit
                if record.action == "execution.begin_stage"
            ]
        assert audit
        assert secret not in str(audit)


@pytest.mark.parametrize("case", ["complete", "question", "expired-lease"])
def test_worker_claim_to_stage_result(worker_side, monkeypatch, case, caplog):
    side, headers, operator = worker_side
    prepare_runtime(side, monkeypatch)
    run, task, attempt, assignment = make_case(side, stage_id="execute", stage_type="agent_step", env=True)
    add_budget(side, run)
    secret = str(access.generate_secret(lambda count: b"S" * count))
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        checked(post(client, HEARTBEAT_PATH, {"worker_id": str(side.worker1), "capabilities": None}))
        claimed = checked(post(client, CLAIM_PATH, claim_body(side), "claim"))
        assert claimed["assignment_id"] == str(assignment.id)
        claim = worker_claim(side, claimed)
        assignment_path = f"/api/v1/worker/assignments/{assignment.id}"
        instruction = claimed["instruction"]
        begin_body = {
            "claim": claim,
            "stage_id": instruction["stage_id"],
            "round_no": instruction["round_no"],
            "input_digest": instruction["input_digest"],
            "runtime_token_secret": secret,
        }
        stage_path = f"{assignment_path}/stages"
        ready = checked(post(client, stage_path, begin_body, "begin"), 201)
        assert checked(post(client, stage_path, begin_body, "begin"), 201) == ready
        assert_secret_free(side, ready, secret)
        assert secret not in caplog.text
        stage_id, step_id = ready["stage_record_id"], ready["step"]["step_id"]
        result_path = f"{stage_path}/{stage_id}/result"
        handoff_body = {
            "claim": claim,
            "progress": {"phase": "runtime_started", "stage_record_id": stage_id, "step_id": step_id},
        }
        role_result = {
            "schema": "urn:skm:execution:role-result:executor:v1",
            "status": "done",
            "summary": "Completed",
            "changed_paths": [],
            "checks_run": [],
            "open_issues": [],
            "self_check": {"performed": True},
        }
        result_body = {
            "claim": claim,
            "outcome_kind": "success",
            "outcome": {"step_id": step_id, "role_result": role_result},
        }
        problem(post(client, result_path, result_body, "result"), 409, "CONTEXT_NOT_FINALIZED")
        problem(
            post(client, f"{assignment_path}/heartbeat", handoff_body, "handoff"),
            409,
            "CONTEXT_NOT_FINALIZED",
        )
        finalize = prompt_wire(client, side, ready, claim)
        finalize_path = f"/api/v1/context-manifests/{finalize['manifest_id']}/finalize"
        bad_key = post(client, finalize_path, finalize, "invalid")
        problem(bad_key, 422, "SCHEMA_INVALID")
        assert bad_key.json()["details"]["reason"] == "not_idempotent"
        stale = {**claim, "fencing_token": claim["fencing_token"] + 1}
        problem(post(client, finalize_path, {**finalize, "claim": stale}, **operator), 409, "LEASE_LOST")
        finalized = checked(post(client, finalize_path, finalize))
        assert finalized["state"] == "final"
        assert checked(post(client, finalize_path, finalize)) == finalized
        if case == "expired-lease":
            expire_now(side, assignment)
            problem(post(client, finalize_path, finalize), 409, "LEASE_LOST")
            return
        handoff = checked(post(client, f"{assignment_path}/heartbeat", handoff_body, "handoff"))
        assert "refusal" not in handoff
        sealed = checked(
            post(
                client,
                f"{assignment_path}/outputs",
                {
                    "claim": claim,
                    "stage_record_id": stage_id,
                    "step_id": step_id,
                    "source": "executor",
                    "manifest": empty_output(side),
                },
                "output",
            ),
            201,
        )
        runtime = bearer(secret)
        note_path = f"/api/v1/runs/{run.id}/steps/{step_id}/notes"
        if case == "question":
            _record_question(client, side, task, run.id, step_id, note_path, runtime)
        problem(post(client, CLAIM_PATH, claim_body(side), "runtime-claim", **runtime), 403, "FORBIDDEN")
        evidence = checked(
            put_blob(client, side.ws, json.dumps(role_result).encode(), "application/json", "evidence"), 201
        )
        result_body["outcome"]["output_id"] = sealed["output_id"]
        result_body["evidence"] = [
            {
                "staged_blob": evidence,
                "filename": "result.json",
                "media_type": "application/json",
                "owner": "step",
                "owner_id": step_id,
                "role": "raw_result",
            }
        ]
        result = checked(post(client, result_path, result_body, "result"))
        assert checked(post(client, result_path, result_body, "result")) == result
        _assert_terminal_state(side, attempt, task, step_id, sealed, case == "question")
        late_note = post(client, note_path, {"kind": "progress", "text": "late"}, "late", **runtime)
        problem(late_note, 401, "UNAUTHENTICATED")
        if case == "complete":
            assert result["next"]["kind"] == "run_stage"
            checked(
                post(
                    client,
                    f"{assignment_path}/release",
                    {
                        "claim": claim,
                        "reason": "retry_later",
                        "retain_environment": True,
                    },
                    "release",
                )
            )
            problem(post(client, finalize_path, finalize), 409, "LEASE_LOST")


def _record_question(client, side, task, run_id, step_id, note_path, runtime):
    body = {
        "kind": "question",
        "text": "Which design do you want?",
        "urgency": "blocking",
        "options": [{"id": "a", "text": "Design A"}, {"id": "b", "text": "Design B"}],
    }
    problem(
        post(client, note_path.replace(str(run_id), str(side.new_id())), body, "foreign-run", **runtime),
        403,
        "FORBIDDEN",
    )
    other_step = owned_agent(side)[5]
    for other_id in (side.new_id(), other_step.id):
        path = note_path.replace(step_id, str(other_id))
        problem(post(client, path, body, "foreign-step", **runtime), 404, "NOT_FOUND")
    note = checked(post(client, note_path, body, "note", **runtime), 201)
    assert checked(post(client, note_path, body, "note", **runtime), 201) == note
    with side.uow(readonly=True) as uow:
        assert [str(n.id) for n in uow.repo(StepRepository).notes_for_step(UUID(step_id))] == [
            note["note_id"]
        ]
        assert not uow.repo(DecisionRepository).open_for_task(task.id)


def _assert_terminal_state(side, attempt, task, step_id, sealed, question):
    with side.uow(readonly=True) as uow:
        history = uow.repo(StageRepository).history(attempt.id)
        assert len(history.entries) == 1
        output = uow.repo(OutputRepository).latest(attempt.id)
        assert output is not None
        assert str(output.id) == sealed["output_id"]
        assert output.seq == 1
        step = uow.repo(StepRepository).get(UUID(step_id))
        assert step.raw_result_file_version_id is not None
        bindings = uow.repo(EvidenceBindingRepository).for_owner("attempt", attempt.id)
        assert [str(v) for v, role in bindings if role.value == "raw_result"] == [
            str(step.raw_result_file_version_id)
        ]
        decisions = uow.repo(DecisionRepository).open_for_task(task.id)
        assert len(decisions) == int(question)


def test_worker_rejects_foreign_identity_and_stale_claim(worker_side):
    side, headers, _ = worker_side
    make_case(side)
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        problem(
            post(client, HEARTBEAT_PATH, {"worker_id": str(side.worker2), "capabilities": None}),
            403,
            "FORBIDDEN",
        )
        for key, value in (("worker_id", side.worker2), ("host_id", side.host2)):
            problem(post(client, CLAIM_PATH, claim_body(side, **{key: str(value)}), key), 403, "FORBIDDEN")
        denied = checked(
            post(client, CLAIM_PATH, claim_body(side, workspace_id=str(side.ws2)), "foreign-ws"), 403
        )
        assert denied["code"] == "FORBIDDEN"
        assert denied["details"]["reason_code"] == "TOKEN_SCOPE"
        claimed = checked(post(client, CLAIM_PATH, claim_body(side), "claim"))
        claim = worker_claim(side, claimed)
        path = f"/api/v1/worker/assignments/{claim['assignment_id']}/heartbeat"
        expired = {**claim, "fencing_token": claim["fencing_token"] + 1}
        problem(post(client, path, {"claim": expired}, "stale"), 409, "LEASE_LOST")
        problem(
            post(client, path, {"claim": {**claim, "assignment_id": str(side.new_id())}}, "collision"),
            422,
            "SCHEMA_INVALID",
        )


def test_worker_claim_requires_minimum_product_version(worker_side):
    side, headers, _ = worker_side
    make_case(side)
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        problem(
            post(client, CLAIM_PATH, claim_body(side, worker_version="0.0.9"), "old-version"),
            426,
            "CLIENT_TOO_OLD",
        )
        checked(post(client, CLAIM_PATH, claim_body(side, worker_version=__version__), "current-version"))


def test_integration_slot_waiting_and_delete_body(worker_side):
    side, headers, _ = worker_side
    make_case(side, env=True)
    make_case(side, env=True)
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        first = worker_claim(side, checked(post(client, CLAIM_PATH, claim_body(side), "claim-1")))
        second = worker_claim(side, checked(post(client, CLAIM_PATH, claim_body(side), "claim-2")))
        target = {"repository_id": str(side.repo_id), "target_branch": "main"}
        held = checked(post(client, SLOT_PATH, {**target, "claim": first}, "slot-1"), 201)
        waiting = checked(post(client, SLOT_PATH, {**target, "claim": second}, "slot-2"), 200)
        assert (waiting["outcome"], waiting["code"]) == ("waiting", "SLOT_BUSY")
        deleted = client.request(
            "DELETE",
            f"{SLOT_PATH}/{held['slot_id']}",
            json={"claim": first, "fencing_token": held["fencing_token"]},
            headers={"Idempotency-Key": "release-slot"},
        )
        assert checked(deleted)["released"] is True
        checked(post(client, SLOT_PATH, {**target, "claim": second}, "slot-2"), 201)


def test_empty_claim_waits_until_deadline(worker_side):
    side, headers, _ = worker_side
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        checked(post(client, HEARTBEAT_PATH, {"worker_id": str(side.worker1), "capabilities": None}))
        start = monotonic()
        empty = checked(post(client, CLAIM_PATH, claim_body(side, max_wait_seconds=1), "wait"))
        assert empty == {"outcome": "nothing_to_claim"}
        assert monotonic() - start >= 1


def test_report_attempt_failure(worker_side):
    side, headers, _ = worker_side
    make_case(side)
    claimed = claim(side)
    stage = begin(side, claimed)["stage_record_id"]
    body = {
        "claim": worker_claim(side, claimed),
        "stage_record_id": stage,
        "error_class": "transport",
        "detail": "lost connection",
        "worktree_dirty": False,
    }
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        path = f"/api/v1/worker/assignments/{claimed['assignment_id']}/failure"
        result = checked(post(client, path, body, "failure"))
        assert (result["next"]["kind"], result["next"]["mode"]) == ("run_stage", "retry")
        with side.uow(readonly=True) as uow:
            assert uow.repo(StageRepository).get(UUID(stage)).error_code == "RUNTIME_TRANSPORT"


def test_record_external_effect(worker_side):
    side, headers, _ = worker_side
    claimed, ready, _, _ = integrated_case(side)
    target, _, request, envelope = local_request(side, claimed, ready)
    body = {**envelope, "claim": worker_claim(side, claimed), "phase": "intended", "request": request}
    with TestClient(worker_api(side), base_url=BASE, headers=headers) as client:
        path = f"/api/v1/worker/assignments/{claimed['assignment_id']}/external-effects"
        effect = checked(post(client, path, body, "effect"), 201)
        assert (effect["effect_id"], effect["state"]) == (target["effect_id"], "intended")
        assert checked(post(client, path, body, "effect"), 201) == effect


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_admitted_step_note_loses_reissued_fence(worker_side, monkeypatch):
    side, headers, _ = worker_side
    run, _, attempt, assignment, _, proof = _owned_runtime(side)
    step_id = UUID(proof["unit_id"])
    secret = access.generate_secret(lambda n: b"N" * n)
    with side.uow() as uow:
        lease = uow.repo(AssignmentRepository).lease(assignment.id)
        access.issue_assignment_token(
            uow,
            worker=side.worker1_client._actor,
            secret=secret,
            run_scope_id=run.id,
            assignment_id=assignment.id,
            step_id=step_id,
            expires_at=lease.expires_at,
            permissions=frozenset({"step.note"}),
            pepper=PEPPER,
            now=side.clock.now(),
        )
        uow.commit()
    admitted, resume = Event(), Event()
    authorize = side.app.bus._authorizer.authorize

    def pause_admitted_note(uow, actor, permission, chain, *, basis=None):
        decision = authorize(uow, actor, permission, chain, basis=basis)
        if permission == "step.note" and decision.allowed:
            admitted.set()
            assert resume.wait(15)
        return decision

    monkeypatch.setattr(side.app.bus._authorizer, "authorize", pause_admitted_note)
    with (
        TestClient(worker_api(side), base_url=BASE, headers=headers) as client,
        ThreadPoolExecutor(1) as pool,
    ):
        path = f"/api/v1/runs/{run.id}/steps/{step_id}/notes"
        body = {"kind": "progress", "text": "finishing"}
        pending = pool.submit(post, client, path, body, "old-note", **bearer(secret))
        try:
            if not admitted.wait(10):
                response = pending.result(timeout=2)
                pytest.fail(
                    f"Step note did not reach policy admission: {response.status_code} {response.text}"
                )
            expire_now(side, assignment)
            assert sweep(side)["expired"] == 1
            fresh = checked(post(client, CLAIM_PATH, claim_body(side, reaped_steps=[proof]), "reclaim"))
            assert fresh["attempt_id"] == str(attempt.id)
            assert fresh["assignment_id"] != str(assignment.id)
            assert fresh["fencing_token"] > lease.fencing_token
        finally:
            resume.set()
        problem(pending.result(timeout=10), 409, "LEASE_LOST")
        problem(post(client, path, body, "after-revocation", **bearer(secret)), 401, "UNAUTHENTICATED")
        with side.uow(readonly=True) as uow:
            assert not uow.repo(StepRepository).notes_for_step(step_id)
