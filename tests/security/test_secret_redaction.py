"""Secrets registered before spawn cannot reach private capture or public metadata."""

from __future__ import annotations

import dataclasses
import json
import threading
from pathlib import Path
from typing import Any, cast, override

import pytest

from contracts.execution.harness import ExecSide, ask, exec_side
from contracts.runtimes.conftest import FakeRunner, budget_for, build
from skm.adapters.runtimes._cli_session.transcript import TranscriptWriter
from skm.adapters.secrets.env import EnvSecretResolver
from skm.kernel.generated._codec import SecretRef
from skm.modules.runtimes.domain.observation import canonical_observation_bytes
from skm.platform.config.secrets import SecretResolvers
from skm.platform.fs.storage_budget import ReservationExceeded
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.schema.registry import SchemaRegistry
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


def test_secret_env_and_secretref_registered_before_spawn(tmp_path: Path) -> None:
    secret = "synthetic-super-private-token"
    reference = SecretRef.parse("secret://env/SKM_TOKEN")
    harness = build(
        tmp_path,
        stdout=(
            json.dumps({"type": "text_delta", "text": secret}).encode()
            + b"\n"
            + b'{"type":"fake_result","final_text":"done"}\n'
        ),
        stderr=(secret + "\n").encode(),
    )
    harness.writer.register_secret(secret)  # SecretResolvers.on_reveal callback before launch
    harness.writer.register_secret(str(reference))
    harness.session.command = dataclasses.replace(harness.command, env={"SKM_TOKEN": secret})

    class InspectRunner(FakeRunner):
        @override
        def spawn(self, command, **kwargs):
            assert secret not in " ".join(command.argv)
            assert harness.writer.redact(command.env["SKM_TOKEN"]) != secret
            return super().spawn(command, **kwargs)

    harness.session.runner = InspectRunner(harness.child)
    events = list(harness.session.run())
    result = harness.session.result()
    assert secret not in repr(events)
    assert secret not in harness.session.signals.stderr_tail
    for path in harness.writer.step_dir.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        assert secret.encode() not in path.read_bytes()
        assert not path.resolve().is_relative_to(harness.command.cwd)
    assert result.observation is not None
    encoded = canonical_observation_bytes(result.observation)
    for forbidden in (secret, "private prompt", "SKM_TOKEN", str(reference), str(harness.command.cwd)):
        assert forbidden.encode() not in encoded
    assert SchemaRegistry.load_default().validate(result.observation.schema, json.loads(encoded)) == ()


@pytest.mark.parametrize("sentinel", ["synthetic-capture-canary", 'synthetic"capture\\canary'])
def test_resolved_secret_is_redacted_in_decoded_transcript(tmp_path: Path, sentinel: str) -> None:
    def line(**fields: str) -> bytes:
        return json.dumps(fields).encode() + b"\n"

    message = f"before {sentinel} after"
    harness = build(
        tmp_path,
        stdout=(
            line(type="text_delta", text=message)
            + line(type="tool_requested", call_id="call-1", tool="read", args_preview=message)
            + line(type="fake_result", final_text="done")
        ),
        stderr=message.encode() + b"\n",
    )
    resolvers = SecretResolvers(
        [EnvSecretResolver({"SKM_TOKEN": sentinel})], on_reveal=harness.writer.register_secret
    )
    token = resolvers.resolve("secret://env/SKM_TOKEN")
    harness.session.command = dataclasses.replace(harness.command, env={"SKM_TOKEN": token.reveal()})

    events = list(harness.session.run())
    result = harness.session.result()
    assert result.outcome == "completed"
    assert sentinel not in repr(events)
    expected = f"before {MASK} after"
    assert (harness.writer.step_dir / "stream.stderr").read_text() == expected + "\n"
    transcript = (harness.writer.step_dir / "stream.jsonl").read_text().splitlines()
    delta, tool_call, final = (json.loads(entry) for entry in transcript)
    assert (delta["type"], tool_call["call_id"], final["final_text"]) == ("text_delta", "call-1", "done")
    assert delta["text"] == expected
    assert tool_call["args_preview"] == expected


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_secret_split_at_every_callback_boundary_is_redacted(tmp_path: Path, stream: str) -> None:
    secret = "synthetic-boundary-credential"
    harness = build(tmp_path)
    harness.writer.register_secret(secret)
    for byte in ("prefix " + secret + " suffix\n").encode():
        admitted, _ = harness.writer.write(stream, bytes((byte,)))
        assert admitted
    harness.writer.close()
    output = (
        harness.writer.step_dir / ("stream.jsonl" if stream == "stdout" else "stream.stderr")
    ).read_text()
    assert secret not in output
    assert "redacted" in output


def test_small_explicit_secret_and_partial_final_line_are_redacted(tmp_path: Path) -> None:
    harness = build(tmp_path)
    harness.writer.register_secret("short")
    harness.writer.write("stderr", b"sho")
    harness.writer.write("stderr", b"rt")
    harness.writer.close()
    assert "short" not in (harness.writer.step_dir / "stream.stderr").read_text()


@pytest.mark.parametrize("size", [50, 51])
def test_concurrent_streams_share_one_prewrite_ceiling(tmp_path: Path, size: int) -> None:
    harness = build(tmp_path)
    harness.writer.max_stream_bytes = 100
    barrier = threading.Barrier(3)

    def write(stream: str) -> None:
        barrier.wait()
        harness.writer.write(stream, b"x" * (size - 1) + b"\n")

    threads = [threading.Thread(target=write, args=(name,)) for name in ("stdout", "stderr")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)
        assert not thread.is_alive()
    harness.writer.close()
    assert harness.writer.exceeded == (size > 50)
    assert harness.writer.used == (size if size > 50 else 100)
    assert sum(path.stat().st_size for path in harness.writer.step_dir.iterdir()) == harness.writer.used
    assert harness.writer.bytes_dropped == (size if size > 50 else 0)


@pytest.mark.parametrize("secret", ["short", "a-much-longer-registered-secret"])
def test_pending_reservation_becomes_exact_redacted_file_size(tmp_path: Path, secret: str) -> None:
    harness = build(tmp_path)
    writer = harness.writer
    writer.register_secret(secret)
    raw = (secret + "\n").encode()
    expected = writer.redact(raw.decode()).encode()
    assert writer.write("stderr", raw[:-1])[0]
    assert writer.used == len(raw) - 1
    assert writer.write("stderr", b"\n")[0]
    writer.close()
    assert writer.used == len(expected)
    assert (writer.step_dir / "stream.stderr").read_bytes() == expected
    assert not writer.exceeded
    assert not writer.bytes_dropped


def test_disk_reserve_is_held_until_all_files_are_fsynced_and_closed(tmp_path: Path) -> None:
    harness = build(tmp_path)
    state = harness.writer.step_dir.parent.parent
    before = harness.budget.snapshot(state, min_free_bytes=0).reserved_bytes
    assert before >= harness.writer.max_stream_bytes
    harness.writer.write("stdout", b"record\n")
    assert harness.budget.snapshot(state, min_free_bytes=0).reserved_bytes == before
    harness.writer.close()
    assert harness.budget.snapshot(state, min_free_bytes=0).reserved_bytes == 0


def test_low_disk_refuses_before_any_runtime_spawn(tmp_path: Path) -> None:
    state = tmp_path / "state"
    budget = budget_for(state, free=100)
    with pytest.raises(Exception, match="storage budget unavailable"):
        budget.reserve(state, owner_id="synthetic-step", max_bytes=1024, min_free_bytes=100)
    assert not (state / "steps").exists()


def test_transcript_cannot_be_created_inside_worktree(tmp_path: Path) -> None:
    harness = build(tmp_path)
    with pytest.raises(ValueError, match="outside workdir"):
        TranscriptWriter(
            harness.command.cwd / "steps" / "unsafe",
            harness.writer.reservation,
            max_stream_bytes=1024,
            workdir=harness.command.cwd,
        )
    harness.writer.close()


def test_reservation_rejects_copy_before_writing_it(tmp_path: Path) -> None:
    budget = budget_for(tmp_path / "state")
    with budget.reserve(tmp_path, owner_id="writer", max_bytes=5, min_free_bytes=0) as reservation:
        target = reservation.open_file(tmp_path / "capture")
        target.write(b"12345")
        with pytest.raises(ReservationExceeded):
            target.write(b"6")
    assert (tmp_path / "capture").read_bytes() == b"12345"


@pytest.mark.parametrize("ascii_only", [False, True])
def test_transcript_masks_keys_nested_values_short_scalars_and_fragments(
    tmp_path: Path, ascii_only: bool
) -> None:
    harness = build(tmp_path)
    writer = harness.writer
    secret = 'š"\\canary'
    writer.register_secret(secret)
    writer.register_secret("19")
    record = {
        "safe": [{secret: secret, "path": f"read {secret}", "count": 19, "kept": 7}],
        "password": "unknown-credential",
    }
    line = json.dumps(record, ensure_ascii=ascii_only).encode()
    assert writer.write("stdout", line + b"\n")[0]
    escaped = json.dumps(secret, ensure_ascii=ascii_only)[1:-1]
    assert writer.write("stdout", (f'{{"key":"{escaped}","key":7}}\n').encode())[0]
    assert writer.write("stdout", f"broken {escaped}\n".encode())[0]
    assert writer.write("stdout", line)[0]
    assert writer.write("stderr", f"broken fragment {escaped}".encode())[0]
    writer.close()

    data = (writer.step_dir / "stream.jsonl").read_bytes()
    first, duplicate, malformed, final = data.splitlines(keepends=True)
    assert first.endswith(b"\n")
    assert not final.endswith(b"\n")
    expected = {
        "safe": [{MASK: MASK, "path": f"read {MASK}", "count": MASK, "kept": 7}],
        "password": MASK,
    }
    assert json.loads(first) == json.loads(final) == expected
    assert json.loads(duplicate) == {"key": 7}
    assert malformed.decode() == f"broken {MASK}\n"
    stderr = (writer.step_dir / "stream.stderr").read_bytes()
    assert stderr.decode() == f"broken fragment {MASK}"
    assert writer.used == len(data) + len(stderr)


def test_raw_json_number_is_masked_before_normalization_and_crlf_is_preserved(tmp_path: Path) -> None:
    writer = build(tmp_path).writer
    writer.register_secret("E+")
    writer.register_secret("-0")
    lines = b'{"count":1E+02,"kept":7}\r\n[-0,42]\n'
    expected = f'{{"count":"{MASK}","kept":7}}\r\n["{MASK}",42]\n'.encode()
    accepted, safe = writer.write("stdout", lines)
    assert accepted
    assert safe.encode() == expected
    writer.close()
    transcript = writer.step_dir / "stream.jsonl"
    assert transcript.read_bytes() == expected
    assert transcript.stat().st_size == writer.used == len(expected)


@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
def test_private_dto_and_runtime_error_do_not_widen_operational_logs(monkeypatch, fmt, detail) -> None:
    from io import StringIO
    from uuid import uuid4

    from security._security_helpers import canaries
    from skm.kernel.error_codes import ErrorCode
    from skm.kernel.errors import ValidationFailed
    from skm.platform.logging import setup
    from skm.platform.logging.envelope import bind
    from skm.platform.logging.logger import get_logger

    value = canaries()
    assert Redactor().text(value.document) == value.document
    stream = StringIO()
    run_id, correlation = str(uuid4()), str(uuid4())
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    setup.configure_logging(
        level="debug", detail=detail, fmt=fmt, stream=stream, redactor=value.redactor, host="local"
    )
    logger = get_logger("execution.worker")
    expl = ValidationFailed(ErrorCode.SCHEMA_INVALID, value.document, details={"raw": value.secret})
    with bind(run_id=run_id, correlation_id=correlation):
        logger.error(
            "stage.completed",
            exc=expl,
            stage="run_checks",
            passed=3,
            duration_ms=17,
            argv=["read", value.document],
            cwd=value.document,
            details={"nested": {"continuation": {"params": value.document}}},
            tool_output={"stdout": value.secret},
        )
        logger.info("config.resolved", generation=7, keys_count=3, digest="sha256:" + "a" * 64)
    rendered = stream.getvalue()
    assert value.document not in rendered
    assert value.secret not in rendered
    for expected in (run_id, correlation, "SCHEMA_INVALID", "17"):
        assert expected in rendered
    if detail == "debug":
        assert "sha256:" + "a" * 64 in rendered


def test_revision_and_runtime_metadata_keep_private_payload_behind_live_file_read(
    exec_side: ExecSide, tmp_path: Path
) -> None:
    from integration.mcp.test_tools import answer, authenticate
    from security._security_helpers import (
        OWNER_AUDIT_BODY,
        bearer,
        canaries,
        http_for,
        seed_private_run,
        token_for,
        web_metadata,
    )
    from skm.entrypoints.mcp.session import McpSession
    from skm.kernel.ports_uow import Surface
    from skm.modules.access.public import RevokeToken
    from skm.modules.execution import public as execution

    side = exec_side
    values = canaries()
    run = seed_private_run(side, tmp_path / "runtime", values)
    reader = token_for(side, scope_id=side.ws, permissions=("run.read", "project.read"))
    file_reader = token_for(side, scope_id=side.ws, permissions=("file.read",))
    foreign = token_for(side, scope_id=side.ws2, permissions=("file.read",))
    owner = token_for(side)
    path = f"/api/v1/runs/{run.run}"
    body_path = f"/api/v1/file-versions/{run.document_version}/content"
    outcome = ask(side.client, execution.GetRunHistory(run_id=run.run)).to_json()
    session = McpSession.open(
        side.app.client(actor=authenticate(side, reader.secret), surface=Surface.MCP), project_id=side.proj
    )
    mcp_history = answer(session, "run_history", {"run": str(run.run)})
    assert mcp_history == outcome
    with http_for(side, values.redactor) as api:
        history = api.get(path + "/history", headers=bearer(reader))
        meta = api.get(path, headers=bearer(reader))
        attempt = api.get(f"/api/v1/attempts/{run.attempt}", headers=bearer(reader))
        assert attempt.status_code == 200
        report = api.get(path + "/report.md", params={"variant": "summary"}, headers=bearer(owner))
        assert (history.status_code, meta.status_code, report.status_code) == (200, 200, 200)
        assert history.json() == outcome
        assert meta.json()["counts_by_status"]["ready"] == 1
        assert str(run.run) in report.text
        assert "Tasks 1" in report.text
        assert len(outcome["entries"]) == 7
        assert str(run.task) in history.text
        web = web_metadata(api, reader, run)
        for rendered in (history.text, meta.text, attempt.text, json.dumps(mcp_history), report.text, *web):
            assert values.document not in rendered
            assert values.secret not in rendered
            assert OWNER_AUDIT_BODY not in rendered

        captured = api.get(
            f"/api/v1/file-versions/{run.transcript_version}/content", headers=bearer(file_reader)
        )
        assert captured.status_code == 200
        assert values.secret not in captured.text
        assert MASK in captured.text
        allowed = api.get(body_path, headers=bearer(file_reader))
        assert (allowed.status_code, allowed.text) == (200, values.document)
        for denied in (
            api.get(body_path, headers=bearer(reader), params={"digest": run.digest}),
            api.get(body_path, headers=bearer(foreign)),
            api.get(f"/api/v1/file-versions/{run.task}/content", headers=bearer(reader)),
        ):
            assert denied.status_code in (403, 404)
            assert values.document not in denied.text
            assert "etag" not in denied.headers
        side.client.dispatch(RevokeToken(file_reader.token_id))
        revoked = api.get(
            body_path, headers={**bearer(file_reader), "If-None-Match": allowed.headers["etag"]}
        )
        assert revoked.status_code == 401
        assert values.document not in revoked.text


def test_explain_and_http_problem_use_safe_secret_projection(exec_side: ExecSide) -> None:
    from integration.integrations._hook_support import _webhook_cfg
    from security._security_helpers import REFERENCE, bearer, canaries, http_for, token_for
    from skm.modules.settings import public as settings

    side, values = exec_side, canaries()
    subscription = {"notify-chat": _webhook_cfg(enabled=False)}
    subscription["notify-chat"]["target"]["secret"] = REFERENCE
    scope = {"level": "workspace", "scope_id": str(side.ws)}
    side.client.dispatch(
        settings.SetValue.from_json(
            {
                "scope": scope,
                "key": "hooks.subscriptions",
                "value": subscription,
                "confirmed": True,
            }
        )
    )
    query = settings.ExplainConfig.from_json({"scope": scope, "keys": ["hooks.subscriptions"]})
    report = ask(side.client, query).to_json()
    assert report["keys"][0]["key"] == "hooks.subscriptions"
    assert report["keys"][0]["value"]["notify-chat"]["target"]["secret"] == REFERENCE
    assert values.secret not in json.dumps(report)
    from skm.platform.config.explain import render_explain_text

    assert values.secret not in render_explain_text(report)
    token = token_for(side)
    with http_for(side, values.redactor) as http:
        problem = http.get(
            "/api/v1/config/explain",
            params={"scope": "instance", "key": values.secret},
            headers=bearer(token),
        )
    assert problem.status_code == 422, problem.text
    assert problem.headers["content-type"] == "application/problem+json"
    assert problem.json()["code"] == "CONFIG_UNKNOWN_KEY", problem.text
    assert problem.json()["request_id"] == problem.headers["x-request-id"]
    assert values.secret not in problem.text
    assert MASK in problem.text


@pytest.mark.parametrize(("operation", "event_name"), [("cancel", "cancelled"), ("pause", "paused")])
def test_domain_events_and_audit_keep_safe_envelope_and_no_diagnostic_content(
    exec_side: ExecSide, operation: str, event_name: str
) -> None:
    from contracts.execution.seed_helpers import seed_bundle, seed_run
    from security._security_helpers import bearer, canaries, http_for, token_for
    from skm.application_bus.ports import EventReader

    side, values = exec_side, canaries()
    with side.uow() as uow:
        run = seed_run(side, uow)
        seed_bundle(side, uow, run.id)
        uow.commit()
    credential = token_for(side)
    path = f"/api/v1/runs/{run.id}"
    with http_for(side, values.redactor) as http:
        response = http.post(
            path + f"/{operation}",
            headers=bearer(credential),
            json={"reason": f"{values.document} {values.secret}"},
        )
        assert response.status_code == 200, response.text
        public = http.get(path + "/history", headers=bearer(credential))
        assert public.status_code == 200, public.text
        assert str(run.id) in public.text
        assert values.document not in public.text
        assert values.secret not in public.text
    with side.uow(readonly=True) as uow:
        events = uow.repo(EventReader).after_workspace_seq(side.ws, 0, types=None, limit=200)
    (event,) = [item for item in events if item.stream_id == run.id]
    assert event.correlation_id == response.headers["x-request-id"]
    assert event.stream_seq == 1
    assert event.type == f"urn:skm:execution:event:run-{event_name}:v1"
    assert event.payload["reason"] == f"RUN_{event_name.upper()}"

    if side.dsn is not None:
        import psycopg

        with psycopg.connect(side.dsn) as connection:
            audit = connection.execute(
                "SELECT action, target, decision FROM skm_core.audit_records WHERE request_id = %s",
                (response.headers["x-request-id"],),
            ).fetchall()
        assert len(audit) == 1
        assert audit[0][::2] == (f"execution.{operation}_run", "allowed")
        assert str(run.id) in json.dumps(audit)
        assert values.secret not in json.dumps(audit)
        assert values.document not in json.dumps(audit)
    persisted = json.dumps(event.to_json())
    assert (values.secret in persisted, values.document in persisted) == (False, False)


@pytest.mark.pg
@pytest.mark.parametrize("exec_side", ["postgres"], indirect=True)
def test_backup_manifest_preserves_inventory_without_captured_content(
    exec_side: ExecSide, tmp_path: Path
) -> None:
    from functools import partial

    from security._security_helpers import canaries, seed_private_run
    from skm.bootstrap._quarantine import _export
    from skm.platform.config.bootstrap import load_bootstrap
    from skm.platform.storage.backup import INVENTORY, MANIFEST, URN, create_backup

    side, values = exec_side, canaries()
    run = seed_private_run(side, tmp_path / "runtime", values)
    assert side.dsn is not None
    env = {"SKM_DATABASE_URL": side.dsn}
    config = load_bootstrap(None, env, tmp_path)
    output = tmp_path / "backup"
    backup = create_backup(output, config.blobs_root, partial(_export, side.dsn, env))
    assert backup["state"] == "complete"

    manifest = (output / MANIFEST).read_text()
    inventory = (output / INVENTORY).read_text()
    document = json.loads(manifest)
    side.app.schemas.require_valid(URN, document)
    assert document["database"]["table_rows"]["skm_core.domain_events"] > 0
    assert document["blobs"]["count"] >= 2
    assert run.digest in inventory
    for serialized in (manifest, inventory):
        assert values.secret not in serialized
        assert values.document not in serialized


def test_active_worker_file_grant_is_rechecked_for_private_canary(exec_side: ExecSide) -> None:
    from datetime import timedelta

    from contracts.execution.test_step_notes import owned_agent
    from integration.artifacts.test_upload_flow import add_file_dto
    from security._security_helpers import canaries, http_for
    from skm.modules.artifacts import public as artifacts
    from skm.modules.artifacts.domain.access_grant import GrantReason
    from skm.modules.artifacts.ports import BlobRepository, FileVersionRepository

    side, values = exec_side, canaries()
    _, _, _, claimed, _, _, runtime, _, credential = owned_agent(side)
    content = values.document.encode()
    staged = side.client.upload_blob(side.ws, [content], size=len(content), media_type="text/plain")
    added = cast("Any", side.client.dispatch(add_file_dto(side.ws, side.proj, staged)))
    version, principal, ref = added.file_version_id, runtime._actor.principal_id, claimed["assignment_id"]
    with side.uow() as uow:
        assert (
            artifacts.grant_access(
                uow,
                principal_id=principal,
                version_ids=(version,),
                reason=GrantReason.ASSIGNMENT,
                ref=ref,
                expires_at=side.clock.now() + timedelta(seconds=30),
                now=side.clock.now(),
                ids=side.ids,
            )
            == 1
        )
        blob_id = uow.repo(FileVersionRepository).get(version).blob_id
        digest = uow.repo(BlobRepository).get(blob_id).digest.value
        uow.commit()

    headers = {"Authorization": f"Bearer {credential}"}
    path = f"/api/v1/file-versions/{version}/content"
    with http_for(side, values.redactor) as http:
        ok = http.get(path, headers=headers)
        assert (ok.status_code, ok.text) == (200, values.document)
        with side.uow() as uow:
            assert (
                artifacts.revoke_grants(uow, reason=GrantReason.ASSIGNMENT, ref=ref, now=side.clock.now())
                >= 1
            )
            uow.commit()
        for direct in (path, f"/api/v1/file-versions/{blob_id}/content"):
            denied = http.get(
                direct, params={"digest": digest}, headers={**headers, "If-None-Match": ok.headers["etag"]}
            )
            assert denied.status_code in (403, 404)
            assert values.document not in denied.text
            assert "etag" not in denied.headers


def test_run_metric_dimensions_do_not_grow_with_correlation_or_untrusted_input(
    exec_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from security._security_helpers import check_run_metric_dimensions

    check_run_metric_dimensions(exec_side, tmp_path, monkeypatch)


def test_uppercase_correlation_header_matches_request_meta_and_structured_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from security._security_helpers import check_uppercase_correlation_header

    check_uppercase_correlation_header(monkeypatch)
