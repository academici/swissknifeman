"""P13.Z phase gate over fresh PostgreSQL compositions and fake-runtime workers."""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import timedelta
from itertools import product
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from contracts.execution.harness import PEPPER
from e2e import test_http_execution, test_m3_execution
from e2e._optional_helpers import (
    assert_archive_redelivery,
    assert_session_end_admission,
    enable_executor_recall,
    exercise_memory,
    mcp_session,
    memory_ids,
    memory_path,
    post,
    remember_body,
    run_follow_up,
    task_lesson_refs,
)
from fixtures.execution.harness import SYSTEM, RecoverySide, recovery
from fixtures.execution.single_run import run_worker, single_run, successful_script
from integration.api.test_planning import ok, problem
from integration.artifacts.test_upload_flow import dispatch_new
from integration.exports.test_vault_notes import _config as vault_defaults
from integration.mcp.test_protocol import call, content, exchange, request
from security.api.harness import BASE, TestClient
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.application_bus.host import HostContext
from skm.background.vault_push import VaultConfig, VaultPush
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.composition_resources import token_authenticator
from skm.bootstrap.lifecycle import add_background_services
from skm.bootstrap.modules import MANIFESTS, select_modules
from skm.bootstrap.worker import build_worker_host, embedded_vault_client, run_vault_host
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.mcp.protocol import METHOD_NOT_FOUND
from skm.entrypoints.mcp.registry import TOOLS
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
from skm.modules.access import public as access
from skm.modules.execution import public as execution
from skm.modules.exports import public as exports
from skm.modules.exports.domain.note import NoteKind, VaultNote
from skm.modules.exports.ports import VaultFs, VaultNoteRepository
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.knowledge import public as knowledge
from skm.modules.learning import public as learning
from skm.modules.planning import public as planning
from skm.modules.runtimes.ports import CapabilityCatalog
from skm.modules.workspace.public import BindCheckout
from skm.platform.logging.logger import get_logger
from support.pg import clean_test_database, pg_session, table_counts, test_database
from support.service_runner import Instance, ServiceRunner
from unit.execution.application._support import set_setting

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = [pytest.mark.e2e, pytest.mark.pg]

_OPTIONAL = ("knowledge", "learning", "exports")
_ALL_ENABLED = (True, True, True)
_ALL_DISABLED = (False, False, False)
_SERVICES = {"knowledge": "memory_expirer", "learning": "learning_recompute", "exports": "janitor"}
_PUSH = "exports.host.push_vault_notes"
_ARCHIVED = "urn:skm:planning:event:plan-archived:v1"
_FINISHED = "urn:skm:execution:event:run-finished:v1"


def _configure(side: RecoverySide, flags: tuple[bool, bool, bool]) -> None:
    for module, enabled in zip(_OPTIONAL, flags, strict=True):
        set_setting(side, f"modules.{module}.enabled", enabled)


def _token(side: RecoverySide, name: str, *permissions: str) -> access.CreateTokenResult:
    command = access.CreateToken(name, permissions=permissions or None)
    return cast("access.CreateTokenResult", side.client.dispatch(command))


@contextmanager
def _boot(side: RecoverySide) -> Iterator[RecoverySide]:
    ports = (BuiltinPacks, TokenEstimator, access.TokenPepperSource, CapabilityCatalog)
    fakes = GatewayTable({port: side.app.gateways.entries[port] for port in ports}, "control_plane_gateway")
    overrides = CompositionOverrides(
        access.RbacAuthorizer(side.clock), StoredScopeChain(), clock=side.clock, gateways=fakes
    )
    app = build_app(
        side.boot, surface=Surface.CLI, environ={}, invocation={}, backend="postgres", overrides=overrides
    )
    with closing(app):
        authenticate = token_authenticator(app.uow_factory, PEPPER, Surface.API, app.bus._ids, side.clock)
        app = add_background_services(replace(app, authenticator=authenticate))
        yield replace(
            side,
            app=app,
            client=app.client(actor=side.owner, surface=Surface.CLI),
            system=app.client(actor=SYSTEM, surface=Surface.BACKGROUND),
        )


@contextmanager
def _http(side: RecoverySide, secret: str) -> Iterator[TestClient]:
    registry = side.app.bus._registry
    enabled = (m.id for m in MANIFESTS if m.id not in registry.disabled_modules())
    api = create_app(side.app, route_table=build_route_table(enabled), registry=registry, no_background=True)
    with TestClient(api, base_url=BASE, headers={"Authorization": f"Bearer {secret}"}) as http:
        yield http


def _module_calls(side: RecoverySide) -> dict[str, tuple[object, object, str, str, JsonObject, int]]:
    workspace = {"workspace_id": str(side.ws)}
    project = {"project_id": str(side.proj)}
    scope = f"/api/v1/workspaces/{side.ws}"
    memory = memory_path(side)
    notes = f"/api/v1/projects/{side.proj}/vault-notes"
    note, body = uuid4(), remember_body()
    recall = knowledge.SearchMemory.from_json(project)
    remember = knowledge.Remember.from_json(body | project)
    candidates = learning.ListCandidates.from_json(workspace)
    recompute = learning.RecomputeConfidence.from_json(workspace)
    requeue = exports.RequeueNote(side.proj, note, 1)
    list_url, recompute_url = f"{scope}/lesson-candidates", f"{scope}/learning/recompute"
    requeue_url, generation = f"{notes}/{note}/requeue", cast("JsonObject", {"expected_generation": 1})
    return {
        "knowledge": (recall, remember, memory, memory, body, 201),
        "learning": (candidates, recompute, list_url, recompute_url, {}, 200),
        "exports": (exports.ListVaultNotes(side.proj), requeue, notes, requeue_url, generation, 404),
    }


def _check_calls(side: RecoverySide, http: TestClient, disabled: frozenset[str]) -> None:
    for module, (query, command, get, post_path, body, status) in _module_calls(side).items():
        if module in disabled:
            for invoke, dto in ((side.client.ask, query), (side.client.dispatch, command)):
                with pytest.raises(SkmError) as failure:
                    invoke(dto)
                assert failure.value.code is ErrorCode.MODULE_DISABLED
            problem(http.get(get), 409, "MODULE_DISABLED")
            problem(post(http, post_path, body), 409, "MODULE_DISABLED")
        else:
            side.client.ask(query)
            ok(http.get(get))
            response = post(http, post_path, body)
            if status == 404:
                problem(response, status, "NOT_FOUND")
            else:
                ok(response, status)


def _check_wiring(side: RecoverySide, disabled: frozenset[str]) -> None:
    registry = side.app.bus._registry
    assert registry.disabled_modules() == disabled
    assert {
        spec.consumer_id for spec in registry.subscribers() if spec.consumer_id.split(".")[0] in _OPTIONAL
    } == {
        cast("Any", spec).consumer_id
        for manifest in MANIFESTS
        if manifest.optional and manifest.id not in disabled
        for spec in manifest.subscribers
    }
    for module, service in _SERVICES.items():
        assert (service in {item.name for item in side.app.services}) == (module not in disabled)
    worker = build_worker_host(
        side.app, replace(side.boot, host_id=side.host1), side.app.authenticate(side.secret), environ={}
    )
    with closing(worker):
        assert (_PUSH in worker.operations) == ("exports" not in disabled)
        services = [getattr(close, "__self__", None) for close in worker.owned_resources]
        assert any(isinstance(service, VaultPush) for service in services) == ("exports" not in disabled)


def _check_mcp(side: RecoverySide, secret: str, disabled: frozenset[str]) -> None:
    optional_tools = [tool for tool in TOOLS if tool.module in _OPTIONAL]
    assert {"skm_memory_remember", "skm_memory_search"} <= {tool.name for tool in optional_tools}
    assert {"skm_local_memory_record", "skm_local_memory_search", "skm_local_memory_summarize"} <= {
        tool.name for tool in optional_tools if tool.local_only
    }
    unavailable = [tool for tool in optional_tools if tool.local_only or tool.module in disabled]
    calls = [call(tool.name, {}, ident=index) for index, tool in enumerate(unavailable, start=2)]
    listing, *direct = exchange(mcp_session(side, secret), [request("tools/list"), *calls])
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert {"skm_plan_list", "skm_run_status"} <= names
    for tool in optional_tools:
        assert (tool.name in names) == (not tool.local_only and tool.module not in disabled)
    for tool, response in zip(unavailable, direct, strict=True):
        if tool.local_only:
            assert response["error"]["code"] == METHOD_NOT_FOUND
            assert "result" not in response
        else:
            assert response["result"]["isError"]
            assert content(response)["error"]["code"] == "MODULE_DISABLED"


@pytest.mark.parametrize("flags", list(product((False, True), repeat=3)))
def test_restart_enables_exactly_the_selected_optional_modules(
    recovery: RecoverySide, flags: tuple[bool, bool, bool]
) -> None:
    _configure(recovery, flags)
    token = _token(recovery, "P13 API and MCP")
    k, lrn, exp = flags
    effective = (k, k and lrn, exp)
    disabled = frozenset(module for module, active in zip(_OPTIONAL, effective, strict=True) if not active)
    requested_off = {module for module, active in zip(_OPTIONAL, flags, strict=True) if not active}
    diagnostics = select_modules(MANIFESTS, requested_off).diagnostics
    assert [(diag.code, diag.target) for diag in diagnostics] == (
        [(ErrorCode.MODULE_DISABLED, "modules.learning.enabled")] if not k and lrn else []
    )
    with _boot(recovery) as side, _http(side, token.secret) as http:
        _check_wiring(side, disabled)
        _check_calls(side, http, disabled)
        _check_mcp(side, token.secret, disabled)
        paths = ok(http.get("/api/v1/openapi.json"))["paths"]
        for route in build_route_table(_OPTIONAL).describe():
            verbs = paths.get(route.path.removeprefix("/api/v1"), {})
            expected = route.bus_name.split(".")[0] not in disabled
            assert (route.method.lower() in verbs) == expected


def _empty_optional_schemas(side: RecoverySide) -> None:
    assert side.dsn is not None
    with psycopg.connect(side.dsn) as db:
        for module in _OPTIONAL:
            counts = table_counts(db, f"skm_{module}")
            assert set(counts.values()) == {0}, counts


@pytest.mark.parametrize("transport", ["embedded", "http"])
def test_m3_with_all_optional_modules_disabled(
    recovery: RecoverySide, tmp_path: Path, transport: str
) -> None:
    _configure(recovery, _ALL_DISABLED)
    with _boot(recovery) as side:
        _empty_optional_schemas(side)
        if transport == "embedded":
            test_m3_execution.test_three_task_dag_reworks_reviews_integrates_and_rebuilds_history(side)
        else:
            test_http_execution.test_http_run_completes_with_a_worker_without_database_credentials(
                side, tmp_path
            )
        _empty_optional_schemas(side)


def _candidate(side: RecoverySide) -> Any:
    scope = {"workspace_id": str(side.ws)}
    query = learning.ListCandidates.from_json({**scope, "detector": "resolved_failure", "states": []})
    page: Any = side.client.ask(query)
    if not page["items"]:
        return None
    (candidate,) = page["items"]
    details = learning.GetCandidate.from_json({**scope, "candidate_id": candidate["candidate_id"]})
    return side.client.ask(details)


def _recompute(side: RecoverySide) -> Any:
    return dispatch_new(side.client, learning.RecomputeConfidence.from_json({"workspace_id": str(side.ws)}))


def _promote(side: RecoverySide) -> str:
    candidate = _candidate(side)
    assert (candidate["s_total"], candidate["n_total"], candidate["exposure_unknown_total"]) == (1, 1, 1)
    # Rework carries prior feedback. Add a separate, controlled observation with complete exposure.
    check = candidate["trigger"].removeprefix("check failure was followed by a pass: ")
    checks = [
        {"command": None, "origin": "check_execution", "ok": ok, "check_key": check} for ok in (False, True)
    ]
    attempt_id, task_id, run_id = (str(uuid4()) for _ in range(3))
    summary = {
        "schema": "urn:skm:learning:activity-summary:v1",
        "source_kind": "attempt",
        "source_key": attempt_id,
        "outcome": "success",
        "observed_at": side.clock.now().isoformat(),
        "exposure_coverage": "complete",
        "exposed_lesson_refs": [],
        "checks": checks,
    }
    ids = {"attempt_id": attempt_id, "task_id": task_id, "run_id": run_id}
    dto = learning.ExtractCandidates.from_json({"project_id": str(side.proj), "summary": summary, **ids})
    evidence: Any = side.system.dispatch(dto)
    assert evidence["signaled"] == [candidate["id"]]
    assert _recompute(side)["recomputed"] == 1
    candidate = _candidate(side)
    assert (candidate["s_total"], candidate["n_total"], candidate["independent_known_total"]) == (2, 2, 1)
    fields = {"workspace_id": str(side.ws), "candidate_id": candidate["id"]}
    review = {**fields, "verdict": "approve", "expected_row_version": candidate["row_version"]}
    assert dispatch_new(side.client, learning.ReviewCandidate.from_json(review))["review_id"]
    reviewed = _candidate(side)
    assert reviewed["reviews"][-1]["reviewer_kind"] == "human"
    fields.update(
        expected_row_version=reviewed["row_version"],
        override_low_confidence=True,
        override_reason="Human verified the failed and passing checks",
    )
    command = learning.PromoteCandidate.from_json(fields)
    lesson = dispatch_new(side.client, command)["lesson_id"]
    assert _candidate(side)["state"] == "promoted"
    dto = knowledge.GetLesson.from_json({"workspace_id": str(side.ws), "lesson_id": lesson})
    view: Any = side.client.ask(dto)
    assert view["confidence_tier"] in {"moderate", "strong", "core"}
    return lesson


def _archive(side: RecoverySide, title: str) -> UUID:
    plan_id = dispatch_new(side.client, planning.CreatePlan(side.proj, title)).plan_id
    dispatch_new(side.client, planning.ArchivePlan(plan_id))
    return plan_id


def _note(side: RecoverySide, source_id: UUID, kind: NoteKind) -> VaultNote | None:
    event_type = _ARCHIVED if kind is NoteKind.PLAN_ARCHIVED else _FINISHED
    events = side.client.events(workspace_id=side.ws, after=0, types=frozenset({event_type}))
    with side.uow(readonly=True) as uow:
        repo = uow.repo(VaultNoteRepository)
        return next((repo.by_event(event.id, kind) for event in events if event.stream_id == source_id), None)


def _await_note(side: RecoverySide, source: UUID, kind: NoteKind) -> VaultNote:
    return Instance.wait_until(lambda: _note(side, source, kind), description=f"{kind} vault note")


def _vault_context(side: RecoverySide, fs: LocalVaultFs, actor: Actor | None = None) -> HostContext:
    client = embedded_vault_client(side.app, actor or side.owner, Surface.CLI, side.host2)
    config = VaultConfig(vault_defaults(**{"exports.vault.path": str(fs.root)}), client.ask)
    return HostContext(
        client,
        GatewayTable({VaultFs: fs}, "host_gateway"),
        side.host2,
        config,
        get_logger("tests.optional.vault"),
        CancelSource().token,
    )


def _vault_push(ctx: HostContext, side: RecoverySide) -> JsonObject:
    return run_vault_host(ctx, _PUSH, {"workspace_id": str(side.ws)})


def _check_write(side: RecoverySide, note: VaultNote, ctx: HostContext, root: Path, vault_id: UUID) -> None:
    with side.uow(readonly=True) as uow:
        writes = uow.repo(VaultNoteRepository).writes(note.id)
    (receipt,) = (write for write in writes if write.generation == note.generation)
    assert (receipt.host_id, receipt.vault_id) == (ctx.host_id, vault_id)
    assert receipt.expected_digest == receipt.observed_digest == note.body_digest
    assert (root / receipt.relative_path).read_bytes() == note.body.encode("utf-8")


def _history(side: RecoverySide) -> dict[str, tuple[str, ...]]:
    snapshot = {}
    query = sql.SQL("SELECT to_jsonb(t)::text AS row FROM {} AS t")
    order = sql.SQL(" ORDER BY row")
    assert side.dsn is not None
    with psycopg.connect(side.dsn) as db:
        for module in _OPTIONAL:
            schema = f"skm_{module}"
            for table in table_counts(db, schema):
                rows = db.execute(query.format(sql.Identifier(schema, table)) + order)
                snapshot[f"{schema}.{table}"] = tuple(row[0] for row in rows)
        optional = sql.SQL(" WHERE split_part({}, '.', 1) = ANY(%s)")
        for table, field in (
            ("consumer_receipts", "consumer_id"),
            ("idempotency_receipts", "operation"),
            ("outbox", "destination"),
        ):
            stmt = query.format(sql.Identifier("skm_core", table)) + optional.format(sql.Identifier(field))
            snapshot[table] = tuple(row[0] for row in db.execute(stmt + order, (list(_OPTIONAL),)))
    return snapshot


def _fake_run(side: RecoverySide, case: Any) -> UUID:
    run_worker(side, case, successful_script(side, case.task.display_key, bad_check=True))
    assert cast("execution.RunView", side.client.ask(execution.GetRun(case.run.id))).status == "succeeded"
    return case.run.id


def test_enabled_flow_and_restart_preserve_only_existing_optional_work(  # noqa: PLR0915 - one persisted restart trace
    recovery: RecoverySide, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure(recovery, _ALL_ENABLED)
    # A small configured observation scale keeps context admission testable with bounded evidence.
    set_setting(recovery, "learning.confidence.volume_k", 0.5)
    set_setting(recovery, "knowledge.lessons.inject_min_confidence", 0.5)
    set_setting(recovery, "exports.notes.run_finished", "all")
    set_setting(recovery, "exports.notes.pending_ttl_days", 1)
    set_setting(recovery, "integrations.hook.cache_ttl_seconds", 600)
    set_setting(recovery, "integrations.hooks.mode", {"run_report": "warn"})
    token = _token(recovery, "P13 restart owner")
    with _boot(recovery) as enabled, _http(enabled, token.secret) as http:
        fs = LocalVaultFs(enabled.root / "vault", enabled.root)
        fs.root.mkdir()
        path = str(enabled.root / "writer-checkout")
        repo, host, now = enabled.repo_id, enabled.host2, enabled.clock.now()
        binding = BindCheckout(repo, host, path, path, ("example.invalid/m3",), None, False, now)
        dispatch_new(enabled.client, binding)
        ctx = _vault_context(enabled, fs)
        run_vault_host(ctx, "exports.host.locate_vault", {"bind_writer": str(ctx.host_id)})
        vault_id = fs.require_writer(ctx.host_id).vault_id
        case = single_run(enabled)
        with ServiceRunner(enabled):
            run_id = _fake_run(enabled, case)
            archive = _archive(enabled, "P13 enabled archive")
            run_note = _await_note(enabled, run_id, NoteKind.RUN_FINISHED)
            archive_note = _await_note(enabled, archive, NoteKind.PLAN_ARCHIVED)
            Instance.wait_until(lambda: _candidate(enabled), description="candidate from the fake run")
        lesson = _promote(enabled)
        enable_executor_recall(enabled)
        assert f"knowledge:{lesson}" in run_follow_up(enabled)
        exercise_memory(enabled, http, token.secret)
        assert len(cast("list[Any]", _vault_push(ctx, enabled)["created"])) == 2
        for note in (run_note, archive_note):
            _check_write(enabled, note, ctx, fs.root, vault_id)
        assert_archive_redelivery(enabled, archive_note, ctx, fs.root)
        hook_checkout = case.repository
        assert_session_end_admission(enabled, hook_checkout, monkeypatch, enabled=True)
        persisted = _history(enabled)
        _configure(recovery, _ALL_DISABLED)
        with _boot(recovery) as disabled, _http(disabled, token.secret) as off:
            _check_calls(disabled, off, frozenset(_OPTIONAL))
            assert_session_end_admission(disabled, hook_checkout, monkeypatch, enabled=False)
            offline = replace(disabled, root=disabled.root / "disabled-run")
            offline.root.mkdir()
            case = single_run(offline)
            with ServiceRunner(disabled):
                missed_run = _fake_run(offline, case)
            assert task_lesson_refs(disabled, case) == set()
            assert _history(disabled) == persisted
        _configure(recovery, _ALL_ENABLED)
        for note, hours in ((archive_note, 25), (run_note, 0)):
            dispatch_new(ctx.client, exports.RequeueNote(enabled.proj, note.id, note.generation))
            enabled.clock.advance(timedelta(hours=hours))
        pending = _archive(enabled, "P13 queued before disable")
        before = _history(enabled)

    # Learning is also unavailable when its required knowledge module is disabled.
    _configure(recovery, (False, True, False))
    with _boot(recovery) as disabled:
        assert _history(disabled) == before
        assert_session_end_admission(disabled, hook_checkout, monkeypatch, enabled=False)
        disabled_ctx = _vault_context(disabled, fs)
        with pytest.raises(SkmError) as refused:
            _vault_push(disabled_ctx, disabled)
        assert refused.value.code is ErrorCode.MODULE_DISABLED
        with ServiceRunner(disabled) as services:
            missed_archive = _archive(disabled, "P13 archived while disabled")
            Instance.wait_until(services.healthy, description="relay with optional destinations disabled")
        assert _history(disabled) == before

    recovery.clock.advance(timedelta(hours=2))
    _configure(recovery, _ALL_ENABLED)
    with _boot(recovery) as resumed, _http(resumed, token.secret) as http:
        assert _history(resumed) == before
        assert not memory_ids(http, memory_path(resumed), "handoff")
        assert len(memory_ids(http, memory_path(resumed), "parity")) == 1
        resumed_ctx = _vault_context(resumed, fs)
        with pytest.raises(SkmError, match="writer binding"):
            _vault_push(replace(resumed_ctx, host_id=resumed.host1), resumed)

        with ServiceRunner(resumed) as services:
            Instance.wait_until(services.healthy, description="resumed relay")
            pending_note = _await_note(resumed, pending, NoteKind.PLAN_ARCHIVED)
        assert _note(resumed, missed_run, NoteKind.RUN_FINISHED) is None
        assert _note(resumed, missed_archive, NoteKind.PLAN_ARCHIVED) is None
        assert _recompute(resumed)["recomputed"] >= 1
        current = _candidate(resumed)
        assert (current["s_total"], current["n_total"], current["lesson_id"]) == (2, 2, lesson)

        # A current credential without source read access cannot receive the pending run report.
        limited = _token(resumed, "P13 writer", "export.run", "plan.read", "config.read", "project.read")
        actor = resumed.app.authenticate(limited.secret)
        limited_ctx = _vault_context(resumed, fs, actor)
        limited_result = _vault_push(limited_ctx, resumed)
        assert {entry["note_id"] for entry in cast("list[Any]", limited_result["created"])} == {
            str(pending_note.id)
        }, limited_result
        pending_run = _await_note(resumed, run_id, NoteKind.RUN_FINISHED)
        assert pending_run.generation == run_note.generation + 1
        with resumed.uow(readonly=True) as uow:
            notes = uow.repo(VaultNoteRepository)
            for note in (run_note, archive_note):
                assert [receipt.generation for receipt in notes.writes(note.id)] == [1]
        report = _vault_push(resumed_ctx, resumed)
        assert {entry["note_id"] for entry in cast("list[Any]", report["verified_existing"])} == {
            str(run_note.id)
        }
        _check_write(resumed, pending_run, ctx, fs.root, vault_id)
        _check_write(resumed, pending_note, ctx, fs.root, vault_id)
        _check_write(resumed, archive_note, ctx, fs.root, vault_id)
        assert len(list(fs.root.rglob("*.md"))) == 3
        assert _vault_push(resumed_ctx, resumed)["created"] == []

        fields = {"workspace_id": str(resumed.ws), "lesson_id": lesson}
        dto = knowledge.GetLesson.from_json(fields)
        view: Any = resumed.client.ask(dto)
        assert view["state"] == "curated"
        fields.update(reason="Replaced by an updated procedure", expected_row_version=view["row_version"])
        dispatch_new(resumed.client, knowledge.DeprecateLesson.from_json(fields))
        assert cast("Any", resumed.client.ask(dto))["state"] == "deprecated"
        scope = ScopeRef(ScopeKind.PROJECT, ScopeId(resumed.proj))
        with resumed.uow(readonly=True) as uow:
            available = knowledge.list_lessons_for_context(uow, (scope,), limit=10)
        assert all(row["id"] != lesson for row in available)
