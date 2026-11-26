"""Surface and delivery helpers for the P13.Z acceptance tests."""

import argparse
import json
import tomllib
from base64 import b64encode
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest

from contracts.execution.harness import PEPPER
from contracts.extensions.harness import pack_payload
from fixtures.execution.harness import RecoverySide
from fixtures.execution.single_run import run_worker, single_run, successful_script
from integration.api.test_planning import ok, problem
from integration.artifacts.test_upload_flow import dispatch_new
from integration.mcp.test_protocol import call, content, exchange
from security.api.harness import TestClient
from skm.application_bus.host import HostContext
from skm.application_bus.ports import ConsumerReceipts, OutboxStore
from skm.application_bus.subscribers import DeliveryOutcome, DeliverySettings, deliver
from skm.bootstrap import hook
from skm.bootstrap.worker import run_vault_host
from skm.entrypoints.cli.main import Backend, main
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import CreateToken, CreateTokenResult
from skm.modules.context import public as context
from skm.modules.execution import public as execution
from skm.modules.execution.ports import StageRepository
from skm.modules.exports.domain.note import VaultNote
from skm.modules.exports.ports import VaultNoteRepository
from skm.modules.extensions.generated.commands import InstallPack
from skm.modules.extensions.generated.documents import PackPayload, PackPayloadFilesItem
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.knowledge import public as knowledge
from skm.modules.settings.public import SetValue
from skm.modules.workspace.public import BindCheckout, CreateProject
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.logging.logger import get_logger
from support.service_runner import Instance, ServiceRunner
from unit.execution.application._support import set_setting


def mcp_session(side: RecoverySide, secret: str) -> McpSession:
    actor = side.app.authenticate(secret)
    return McpSession.open(side.app.client(actor=actor, surface=Surface.MCP), project_id=side.proj)


def post(http: TestClient, path: str, body: JsonObject) -> Any:
    return http.post(path, json=body, headers={"Idempotency-Key": str(uuid4())})


def remember_body(body: str = "P13 check", **fields: Any) -> JsonObject:
    return {"kind": "fact", "body": body, "ttl_hours": 1, "source": "api", **fields}


def memory_path(side: RecoverySide) -> str:
    return f"/api/v1/projects/{side.proj}/memory"


def memory_ids(http: TestClient, path: str, query: str, **fields: str) -> set[str]:
    return {row["id"] for row in ok(http.get(path, params={"q": query, **fields}))["items"]}


def _memory_cli(side: RecoverySide, *args: str) -> Any:
    out, err = StringIO(), StringIO()
    backend = Backend(side.client, instance_id=side.app.instance_id)
    argv = ["memory", *args, "--project", str(side.proj), "--json"]
    env = {"HOME": str(side.root)}
    status = main(argv, stdout=out, stderr=err, environ=env, backend=lambda *_: backend)
    assert status == 0, err.getvalue()
    return json.loads(out.getvalue())["result"]


def exercise_memory(side: RecoverySide, http: TestClient, secret: str) -> None:
    path, session = memory_path(side), mcp_session(side, secret)
    cli_id = _memory_cli(side, "remember", "P13 parity CLI", "--ttl-hours", "1")["entry_id"]
    api_id = ok(post(http, path, remember_body("P13 parity API")), 201)["entry_id"]
    stored, found = exchange(
        session,
        [
            call("skm_memory_remember", {"key": "fact", "text": "P13 parity MCP"}),
            call("skm_memory_search", {"query": "parity"}),
        ],
    )
    assert not stored["result"]["isError"], content(stored)
    ids = {cli_id, api_id, content(stored)["entry_id"]}
    assert {row["entry_id"] for row in content(found)["items"]} == ids
    assert memory_ids(http, path, "parity") == ids
    assert {row["id"] for row in _memory_cli(side, "search", "parity")["items"]} == ids

    set_setting(side, "knowledge.memory.max_live_per_scope", 3)
    problem(post(http, path, remember_body("over capacity")), 409, "MEMORY_LIMIT_REACHED")
    limited = ok(http.get(path, params={"q": "parity", "limit": 1}))
    assert len(limited["items"]) == 1
    assert limited["truncated"]
    other_project = dispatch_new(side.client, CreateProject(side.ws, "other", "Other")).project_id
    assert not memory_ids(http, f"/api/v1/projects/{other_project}/memory", "parity")

    scope = {"level": "workspace", "scope_id": str(side.ws)}
    setting = SetValue.from_json({"scope": scope, "key": "knowledge.memory.namespaces", "value": ["team"]})
    dispatch_new(side.client, setting)
    shared = remember_body("P13 shared fact", scope={"kind": "namespace", "namespace": "team"})
    shared_id = ok(post(http, path, shared), 201)["entry_id"]
    assert not memory_ids(http, path, "shared")
    assert memory_ids(http, path, "shared", include_shared="true") == {shared_id}

    handoff = remember_body("P13 handoff", kind="active_handoff")
    old = ok(post(http, path, handoff), 201)["entry_id"]
    problem(post(http, path, handoff), 409, "VERSION_CONFLICT")
    next_handoff = {**handoff, "body": "P13 updated handoff", "expected_handoff_id": old}
    command = knowledge.Remember.from_json({**next_handoff, "project_id": str(side.proj)})
    result: Any = side.client.dispatch(command, idempotency_key="optional-handoff")
    assert result["superseded_id"] == old
    problem(post(http, path, next_handoff), 409, "VERSION_CONFLICT")
    assert memory_ids(http, path, "handoff") == {result["entry_id"]}
    assert side.client.dispatch(command, idempotency_key="optional-handoff") == result


def enable_executor_recall(side: RecoverySide) -> None:
    (pack,) = side.app.gateways.get(BuiltinPacks).payloads()
    profile_path = "agent-profiles/executor.toml"
    profile = next(file.content.decode() for file in pack.files if file.path == profile_path)
    overlay = pack_payload(
        "p13-recall",
        trust="operator",
        files={profile_path: profile.replace("memory_top_k = 0", "memory_top_k = 3")},
        extra_manifest=(
            '[[overrides]]\nkind = "agent_profile"\nkey = "executor"\n'
            'reason = "Exercise lesson recall in the P13 fake worker"\n'
        ),
    )
    files = tuple(PackPayloadFilesItem(file.path, b64encode(file.content).decode()) for file in overlay.files)
    command = InstallPack(PackPayload(overlay.manifest_text, files), "path:p13-recall", trust="operator")
    assert dispatch_new(side.client, command).status == "installed"
    # The worker startup also installs packaged core. Keep this overlay paired with its synthetic core.
    set_setting(side, "extensions.packs.versions", {"core": tomllib.loads(pack.manifest_text)["version"]})
    set_setting(side, "extensions.packs.enabled", ["p13-recall"])
    set_setting(side, "context.memory.enabled", True)


def task_lesson_refs(side: RecoverySide, case: Any) -> set[str]:
    with side.uow(readonly=True) as uow:
        entries = uow.repo(StageRepository).history(case.attempt.id).entries
        step = next(step for entry in entries for step in entry.steps if step.role.value == "executor")
        assert step.context_manifest_id is not None
        manifest = context.require_final(uow, step.context_manifest_id)
        assert manifest.owner_ref == f"step:{step.id}"
        return {
            block.source_ref
            for block in manifest.blocks
            if block.included and block.source_ref.startswith("knowledge:")
        }


def run_follow_up(side: RecoverySide) -> set[str]:
    follow_up = replace(side, root=side.root / "follow-up")
    follow_up.root.mkdir()
    case = single_run(follow_up)
    # The archive/restart trace owns its own run-note fixtures.
    set_setting(side, "exports.notes.run_finished", "off")
    with ServiceRunner(side):
        run_worker(follow_up, case, successful_script(follow_up, case.task.display_key))
        run = cast("execution.RunView", side.client.ask(execution.GetRun(case.run.id)))
        assert run.status == "succeeded"
        events = side.client.events(
            workspace_id=side.ws, after=0, types=frozenset({"urn:skm:execution:event:run-finished:v1"})
        )
        event = next(event for event in events if event.stream_id == case.run.id)

        def processed() -> bool:
            with side.uow(readonly=True) as uow:
                return uow.repo(ConsumerReceipts).seen("exports.run_finished_note", event.id)

        Instance.wait_until(processed, description="follow-up run-finished delivery")
    set_setting(side, "exports.notes.run_finished", "all")
    return task_lesson_refs(side, case)


def _activity_count(side: RecoverySide) -> int:
    assert side.dsn is not None
    # The optional activity repository is absent from the disabled composition.
    with psycopg.connect(side.dsn) as db:
        row = db.execute(
            "SELECT count(*) FROM skm_learning.activity_records WHERE project_id = %s", (side.proj,)
        ).fetchone()
    assert row is not None
    return cast("int", row[0])


def assert_session_end_admission(
    side: RecoverySide, checkout: Path, monkeypatch: pytest.MonkeyPatch, *, enabled: bool
) -> None:
    marker = checkout / ".skm/project.json"
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "schema": "urn:skm:workspace:checkout-marker:v1",
                "instance_id": str(side.app.instance_id),
                "workspace_id": str(side.ws),
                "project_id": str(side.proj),
                "repository_id": str(side.repo_id),
                "mount_name": "repo",
            }
        )
    )
    path = str(checkout)
    dispatch_new(
        side.client,
        BindCheckout(
            side.repo_id, side.host1, path, path, ("example.invalid/m3",), None, False, side.clock.now()
        ),
    )
    home = side.root / "hook-home"
    session = f"p13-{uuid4()}"
    transcript = home / ".claude/projects/checkout" / f"{session}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(
        json.dumps({"type": "assistant", "sessionId": session, "message": {"content": []}}) + "\n"
    )
    args = argparse.Namespace(
        target="claude_code", surface="lifecycle.run_report", event_name="SessionEnd", project=str(side.proj)
    )
    payload = {
        "cwd": path,
        "session_id": session,
        "reason": "logout",
        "transcript_path": str(transcript),
    }
    state = home / "state"
    queue = state / "hooks/learning"
    observations = state / "hooks/observations.jsonl"
    previous = observations.read_text().splitlines() if observations.exists() else []
    wakeups = []
    before = _activity_count(side)
    bootstrap = _session_hook_profile(side, home, state, session)
    env = {
        "HOME": str(home),
        "SKM_HOST_ID": str(side.host1),
        "SKM_STATE_DIR": str(state),
    }
    with monkeypatch.context() as patch:
        patch.setattr(hook, "_start_session_drain", lambda *_: wakeups.append(True))
        invocations = 1 if enabled else 2
        for _ in range(invocations):
            out, err = StringIO(), StringIO()
            assert hook.invoke(args, StringIO(json.dumps(payload)), out, err, env, str(bootstrap)) == 0
            assert (out.getvalue(), err.getvalue()) == ("", "")
        assert len(list(queue.glob("*.json"))) == int(enabled)
        assert len(wakeups) == int(enabled)
        hook._drain_sessions(env, str(bootstrap))
    added = observations.read_text().splitlines()[len(previous) :]
    assert [json.loads(line)["kind"] for line in added] == ["session_end"] * invocations
    assert not list(queue.glob("*.json"))
    assert _activity_count(side) - before == int(enabled)


def _session_hook_profile(side: RecoverySide, home: Path, state: Path, session: str) -> Path:
    secret_dir = state / "secrets"
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    pepper_file = secret_dir / "token-pepper"
    dsn_file = secret_dir / "database-url"
    pepper_file.write_bytes(PEPPER)
    pepper_file.chmod(0o600)
    assert side.dsn is not None
    dsn_file.write_text(side.dsn)
    dsn_file.chmod(0o600)
    token = side.client.dispatch(
        CreateToken(
            session,
            scope_id=side.ws,
            permissions=("project.read", "checkout.read_locator", "integration.read", "lesson.read"),
        )
    )
    assert isinstance(token, CreateTokenResult)
    token_file = secret_dir / "hook.token"
    token_file.write_text(token.secret)
    token_file.chmod(0o600)
    bootstrap = home / "bootstrap.toml"
    bootstrap.write_text(
        f'schema = "{BOOTSTRAP_URN}"\n'
        f'instance_id = "{side.app.instance_id}"\n'
        '[access]\nmode = "embedded"\n'
        f'[database]\nurl = "secret://file/{dsn_file}"\n'
        f'[secrets]\ntoken_pepper = "secret://file/{pepper_file}"\n'
    )
    return bootstrap


def assert_archive_redelivery(side: RecoverySide, note: VaultNote, ctx: HostContext, root: Path) -> None:
    destination = "exports.plan_archived_note"
    params = (note.event_id, destination)
    relay_id = "p13-redelivery"
    now = side.clock.now()
    receipt_count = "SELECT count(*) FROM skm_core.consumer_receipts WHERE event_id = %s AND consumer_id = %s"
    assert side.dsn is not None
    with side.uow(readonly=True) as uow:
        write_count = len(uow.repo(VaultNoteRepository).writes(note.id))
    file_count = len(list(root.rglob("*.md")))
    with psycopg.connect(side.dsn) as db:
        receipts = db.execute(receipt_count, params).fetchone()
        assert receipts == (1,)
        # Make the original committed destination due again while the background relay is stopped.
        reopened = db.execute(
            "UPDATE skm_core.outbox SET state = 'pending', delivered_at = NULL "
            "WHERE event_id = %s AND destination = %s AND state = 'delivered' RETURNING id",
            params,
        ).fetchone()
        assert reopened is not None
    with side.uow() as uow:
        (item,) = uow.repo(OutboxStore).claim(destination=destination, relay_id=relay_id, now=now, limit=1)
        assert (item.id, item.event_id) == (reopened[0], note.event_id)
        uow.commit()
    app = side.app
    assert (
        deliver(
            item,
            registry=app.bus._registry,
            uow_factory=app.uow_factory,
            config=app.config,
            delivery=DeliverySettings(max_attempts=3, backoff_seconds=1, backoff_max_seconds=2),
            clock=side.clock,
            ids=app.bus._ids,
            gateways=app.gateways,
            log=get_logger("tests.optional.redelivery"),
            relay_id=relay_id,
        )
        is DeliveryOutcome.SKIPPED_DUPLICATE
    )
    report = run_vault_host(ctx, "exports.host.push_vault_notes", {"workspace_id": str(side.ws)})
    assert report["created"] == report["verified_existing"] == []
    with side.uow(readonly=True) as uow:
        repo = uow.repo(VaultNoteRepository)
        current = repo.by_event(note.event_id, note.kind)
        assert current is not None
        assert current.id == note.id
        assert len(repo.writes(note.id)) == write_count
    with psycopg.connect(side.dsn) as db:
        assert db.execute(receipt_count, params).fetchone() == receipts
    assert len(list(root.rglob("*.md"))) == file_count
