"""Stdio and HTTP authoring steps for the ENCH4 process acceptance test."""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from select import select
from subprocess import Popen  # noqa: TID251 -- typed pipe endpoints for the MCP test
from typing import Any, Literal
from uuid import UUID

import pytest

from contracts.execution._client_execution import manual_check
from contracts.planning._authoring_support import BASE_GUIDE, BASE_TEXT, EDITED_TEXT, NEW_GUIDE, REKEYED, A, B
from contracts.planning.test_client_planning import preview, publication
from e2e.test_m1_config_on_postgres import Sandbox, rows
from integration.artifacts.test_upload_flow import add_file_dto, dispatch_new
from integration.runtimes.test_codex_argv import _make_request
from skm.adapters.runtimes._cli_session.binding import launch_verification_digest
from skm.adapters.runtimes.codex.launch import build_launch_plan
from skm.application_bus.client import SkmClient
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import FileVersionId, HostId, ProjectId, WorkspaceId
from skm.kernel.isolation import IsolationProfile
from skm.modules.access import public as access
from skm.modules.artifacts import public as artifacts
from skm.modules.planning import public as planning
from skm.modules.runtimes import public as runtimes
from skm.platform.system_clock import SystemClock
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient, InjectedFault
from support.service_runner import Instance

AUTHORED_CHECK = "Verify authored output"
PUBLISHED_EVENT = "urn:skm:planning:event:plan-revision-published:v1"


def verify_barrier_runtime(
    owner: SkmClient,
    box: Sandbox,
    host: UUID,
    worker: Popen[str],
    worker_env: dict[str, str],
    executable: Path,
    *,
    worker_python: str = sys.executable,
) -> None:
    def installed() -> list[tuple[Any, ...]]:
        assert worker.poll() is None, (box.root / "worker.log").read_text()
        return rows(
            box.dsn,
            "SELECT observation, snapshot->'offers' "
            "FROM skm_runtimes.worker_model_offer_snapshots AS snapshots "
            "JOIN skm_workspace.workers AS workers ON workers.id = snapshots.worker_id "
            "CROSS JOIN LATERAL jsonb_array_elements(snapshot->'installations') AS observation "
            "WHERE workers.host_id = %s AND observation->>'runtime_id' = 'codex' "
            "AND observation->>'version' = '0.165.0'",
            host,
        )

    ((observation, offers),) = Instance.wait_until(
        installed, timeout=30, description="worker Codex installation and model offer snapshot"
    )
    assert {"gpt-6-sol", "gpt-6-astra"} <= {
        item["model_id"] for item in offers if item["runtime_id"] == "codex" and item["effort"] == "high"
    }
    assert "binary_locator" not in observation
    details = observation["details"]
    binary_path = str(executable.resolve(strict=True))
    canary_dir = box.root / "verification-canary"
    socket_path = str(canary_dir / "stage.sock")
    stage_server = runtimes.McpServerSpec(
        "skm", (worker_python, "-m", "skm.entrypoints.cli.main", "mcp"), {"SKM_STAGE_SOCKET": socket_path}, ()
    )
    request = _make_request(
        canary_dir, mcp_servers=(stage_server,), extra_env={"SKM_STAGE_SOCKET": socket_path}
    )
    request = replace(request, stage_tool_socket=socket_path, env_allowlist=())
    launch = build_launch_plan(
        request,
        binary_path=binary_path,
        step_dir=canary_dir / "step",
        ownership=runtimes.ProcessOwnership(request.process_owner, "pgroup_best_effort", "canary"),
        host_environ=worker_env,
        user_home=box.home,
    )
    os_name, kernel = details["os_kernel"].split(":", 1)
    context = runtimes.VerificationContext(
        host_id=HostId(host),
        binary_sha256=details["binary_sha256"],
        os=os_name,
        kernel=kernel,
        adapter_version=details["adapter_version"],
        isolation_profile=IsolationProfile.WORKTREE,
        launch_config_digest=launch_verification_digest(launch.command.as_wrapped(), binary_path),
    )
    observations: tuple[tuple[str, Literal["native", "adapted"]], ...] = (
        ("config_isolation", "adapted"),
        ("workspace_binding", "native"),
        ("reliable_cancellation", "adapted"),
        ("permission_flags", "native"),
        ("sandbox_native", "native"),
    )
    verified_at = SystemClock().now().date()
    for capability, status in observations:
        dispatch_new(
            owner,
            runtimes.RecordCapabilityVerification(
                "codex", "0.165.0", capability, status, "fixture:ench4-barrier", "", verified_at, context
            ),
        )


@dataclass(frozen=True)
class Editor:
    principal_id: UUID
    token_id: UUID
    secret: str


def issue_editor(owner: SkmClient, ws: UUID, name: str) -> Editor:
    principal = dispatch_new(owner, access.CreatePrincipal.from_json({"kind": "human", "display_name": name}))
    dispatch_new(
        owner,
        access.GrantMembership.from_json(
            {"scope_id": str(ws), "principal_id": str(principal.principal_id), "role": "maintainer"}
        ),
    )
    token = owner.dispatch(access.CreateToken(name, principal.principal_id, ws))
    assert isinstance(token, access.CreateTokenResult)
    return Editor(principal.principal_id, token.token_id, token.secret)


def upload_guide(owner: SkmClient, ws: UUID, project: UUID, prior: Any = None) -> Any:
    guide = BASE_GUIDE if prior is None else NEW_GUIDE
    staged = owner.upload_blob(WorkspaceId(ws), [guide], size=len(guide), media_type="text/plain")
    if prior is None:
        return dispatch_new(owner, add_file_dto(WorkspaceId(ws), ProjectId(project), staged))
    return dispatch_new(
        owner,
        artifacts.AddFileVersion.from_json(
            {
                "file_id": str(prior.file_id),
                "expected_row_version": 2,
                "blob": {
                    "workspace_id": str(ws),
                    "staged_blob_id": str(staged.staged_blob_id),
                    "digest": staged.digest,
                    "size": staged.size,
                    "media_type": staged.media_type,
                },
                "original_filename": "guide-v2.txt",
                "declared_media_type": None,
                "source": {"kind": "upload"},
            }
        ),
    )


def baseline_revision(
    owner: SkmClient, project: UUID, version: UUID, *, output_path: str | None = None
) -> tuple[UUID, Any]:
    plan = dispatch_new(owner, planning.CreatePlan(project, "Concurrent authors")).plan_id
    draft = dispatch_new(owner, planning.OpenDraft(plan, base="empty"))
    saved = dispatch_new(
        owner,
        planning.SaveDraft(
            plan,
            draft.draft_id,
            draft.edit_version,
            merge_patch={
                "goal": "Keep the execution contract pinned across publications.",
                "phases": [
                    {"key": "P1", "title": "Author", "goal": "Pin inputs", "design_state": "detailed"}
                ],
                "items": [
                    {
                        "key": key,
                        "phase": "P1",
                        "title": f"Author {key}",
                        "summary": text,
                        "why": "Exercise independent drafts",
                        "scope": {"include": ["repo:src/**"], "exclude": []},
                        "change_hints": [{"mount": "repo", "pattern": output_path, "change": "modify"}]
                        if key == A and output_path is not None
                        else [],
                        "deliverables": ["Verified fixture"],
                        "guidance_md": "Keep the fixture self-contained.",
                        "route": {"runtime": "codex", "class": "implementation", "effort": "high"},
                        "review": {"mode": "self", "reason": "Synthetic fixture"},
                    }
                    for key, text in ((A, BASE_TEXT), (B, "Independent item"))
                ],
                "checks": [
                    manual_check(
                        key, "Verify original fixture", required=key == A and output_path is not None
                    )
                    for key in (A, B)
                ],
                "requirements": [
                    {
                        "key": "R1",
                        "statement": "Retain the structural owner",
                        "priority": "must",
                        "source": {"kind": "owner"},
                        "owners": [B],
                    }
                ],
                "materials": [
                    {
                        "key": "guide",
                        "title": "Authoring guide",
                        "kind": "file_version",
                        "role": "input",
                        "file_version_id": str(version),
                        "freshness": {"policy": "latest_at_publish"},
                        "required_for": ["execution"],
                        "applies_to": [A, B],
                    }
                ],
            },
        ),
    )
    return plan, dispatch_new(owner, publication(plan, saved, preview(owner, plan, saved)))


def mcp_tools(process: Popen[str]) -> Callable[..., dict[str, Any]]:
    stdin, stdout = process.stdin, process.stdout
    assert stdin is not None
    assert stdout is not None
    sequence = 0

    def rpc(method: str, params: dict[str, Any], *, notify: bool = False) -> Any:
        nonlocal sequence
        sequence += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            message["id"] = sequence
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()
        if notify:
            return None
        assert select([stdout], [], [], 15)[0], f"MCP timed out at {method}"
        line = stdout.readline()
        assert line, f"MCP closed stdout at {method} (exit={process.poll()})"
        reply = json.loads(line)
        assert reply["id"] == sequence, reply
        assert "result" in reply, reply
        return reply["result"]

    init = rpc(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "ench4", "version": "1"},
        },
    )
    assert init["protocolVersion"] == "2025-06-18"
    rpc("notifications/initialized", {}, notify=True)

    def call(tool: str, *, error: ErrorCode | None = None, **args: Any) -> dict[str, Any]:
        reply = rpc("tools/call", {"name": "skm_plan_" + tool, "arguments": args})
        content = json.loads(reply["content"][0]["text"])
        assert reply["isError"] is (error is not None), content
        if error is not None:
            assert content["error"]["code"] == error.value, content
        return content

    return call


def _source_reads(mcp: Callable[..., dict[str, Any]], source: dict[str, Any]) -> tuple[str, str]:
    first = mcp("entities", **source, kinds=["item"], limit=1)
    second = mcp("entities", **source, kinds=["item"], limit=1, after=first["next_cursor"])
    entity = mcp("entity", **source, entity=A)
    fragment = mcp("read_text", **source, target=A, pointer="/summary", max_bytes=9)
    tail = mcp("read_text", **source, target=A, pointer="/summary", offset_bytes=fragment["end_offset_bytes"])
    assert [first["items"][0]["display_key"], second["items"][0]["display_key"]] == [A, B]
    assert second.get("next_cursor") is None
    assert all(view["source"] == first["source"] for view in (second, entity, fragment, tail))
    assert first["source"]["draft_id"] == source["draft_id"]
    assert first["source"]["edit_version"] == source["expected_edit_version"]
    assert fragment["truncated"]
    assert tail.get("next_offset_bytes") is None
    assert fragment["text"] + tail["text"] == BASE_TEXT
    assert fragment["text_digest"] == tail["text_digest"]
    assert entity["entity_id"] == fragment["target_entity_id"] == first["items"][0]["entity_id"]
    return fragment["text_digest"], second["items"][0]["entity_id"]


def _replace_text(digest: str, text: str) -> dict[str, Any]:
    return {
        "op": "replace_text",
        "target": A,
        "pointer": "/summary",
        "expected_text_digest": digest,
        "old_text": BASE_TEXT,
        "new_text": text,
    }


def edit_drafts(
    first: SkmClient,
    second: SkmClient,
    mcp: Callable[..., dict[str, Any]],
    plan: UUID,
    baseline: UUID,
) -> Any:
    left = dispatch_new(first, planning.OpenDraft(plan, base="current"))
    right = mcp("draft_open", plan=str(plan), base="current", idempotency_key="ench4-open-right")
    assert str(left.draft_id) != right["draft_id"]
    assert str(left.base_revision_id) == right["base_revision_id"] == str(baseline)
    left_source = {"draft_id": left.draft_id, "expected_edit_version": left.edit_version}
    right_source = {
        "plan": str(plan),
        "draft_id": right["draft_id"],
        "expected_edit_version": right["edit_version"],
    }
    left_text: Any = first.ask(planning.ReadText(plan, A, "/summary", **left_source))
    digest, entity_b = _source_reads(mcp, right_source)
    assert left_text.text_digest == digest
    assert left_text.text == BASE_TEXT

    left = dispatch_new(
        first,
        planning.SaveDraft.from_json(
            {
                "plan_id": str(plan),
                "draft_id": str(left.draft_id),
                "expected_edit_version": left.edit_version,
                "changes": [
                    _replace_text(digest, "First editor wording"),
                    {
                        "op": "patch",
                        "target": A,
                        "merge_patch": {"route": {"class": "frontier"}, "depends_on": [B]},
                    },
                ],
            }
        ),
    )
    saved = mcp(
        "draft_save",
        **right_source,
        changes=[
            _replace_text(digest, EDITED_TEXT),
            {"op": "patch", "target": B, "merge_patch": {"depends_on": [A]}},
            {
                "op": "add",
                "kind": "check",
                "entity": manual_check(A, AUTHORED_CHECK, key="V2", required=True),
            },
            {"op": "rekey", "target": B, "new_key": REKEYED},
        ],
    )
    mcp("read_text", **right_source, target=A, pointer="/summary", error=ErrorCode.VERSION_CONFLICT)
    right = planning.SaveDraftResult.from_json(saved)
    candidates = preview(first, plan, left), preview(second, plan, right)
    assert all(candidate.publishable for candidate in candidates)
    published = dispatch_new(first, publication(plan, left, candidates[0]))
    with pytest.raises(SkmError) as rejected:
        dispatch_new(second, publication(plan, right, candidates[1]))
    assert rejected.value.code is ErrorCode.BASE_REVISION_CHANGED

    rebase = planning.RebaseDraft(plan, right.draft_id, right.edit_version, published.revision_id)
    before = second.ask(planning.GetDraft(plan, right.draft_id))
    with pytest.raises(SkmError) as conflict:
        dispatch_new(second, rebase)
    assert conflict.value.code is ErrorCode.REBASE_CONFLICTS
    assert second.ask(planning.GetDraft(plan, right.draft_id)) == before
    conflicts = conflict.value.details["conflicts"]
    assert isinstance(conflicts, list)
    (found,) = conflicts
    assert isinstance(found, dict)
    assert found["pointer"] == "/items/0/summary"
    resolved = dispatch_new(
        second,
        planning.RebaseDraft.from_json(
            {
                **rebase.to_json(),
                "resolutions": [{"conflict_id": found["conflict_id"], "keep": "yours"}],
            }
        ),
    )
    cyclic = preview(second, plan, resolved)
    assert not cyclic.publishable
    assert any("cycle" in f.code.lower() for f in cyclic.validation.findings)
    with pytest.raises(SkmError) as invalid:
        dispatch_new(second, publication(plan, resolved, cyclic))
    assert invalid.value.code is ErrorCode.PLAN_NOT_READY
    findings = invalid.value.details["findings"]
    assert isinstance(findings, list)
    assert any(isinstance(f, dict) and "cycle" in str(f["code"]).lower() for f in findings)
    head: Any = second.ask(planning.GetPlan(plan))
    history: Any = second.ask(planning.ListRevisions(plan))
    assert head.current_revision_id == published.revision_id
    assert len(history.items) == 2

    repaired = dispatch_new(
        second,
        planning.SaveDraft.from_json(
            {
                "plan_id": str(plan),
                "draft_id": str(resolved.draft_id),
                "expected_edit_version": resolved.edit_version,
                "changes": [{"op": "patch", "target": A, "merge_patch": {"depends_on": []}}],
            }
        ),
    )
    final: Any = second.ask(planning.GetDraft(plan, repaired.draft_id))
    a, b = final.document["items"]
    assert (b["key"], b["id"], b["depends_on"]) == (REKEYED, entity_b, [A])
    assert final.document["requirements"][0]["owners"] == [REKEYED]
    assert final.document["materials"][0]["applies_to"] == [A, REKEYED]
    assert a["summary"] == EDITED_TEXT
    assert a["route"]["class"] == "frontier"
    assert any(c["key"] == "V2" and c["required"] for c in final.document["checks"])
    return repaired


def publish_repaired(
    box: Sandbox,
    owner: SkmClient,
    second: SkmClient,
    token: Editor,
    connect: Callable[[str], SkmClient],
    ws: UUID,
    project: UUID,
    plan: UUID,
    draft: Any,
    material: Any,
) -> tuple[Any, Any]:
    stale = preview(second, plan, draft)
    assert stale.publishable
    assert stale.pinned_materials[0].file_version_id == material.file_version_id
    updated = upload_guide(owner, ws, project, material)
    with pytest.raises(SkmError) as changed:
        dispatch_new(second, publication(plan, draft, stale))
    assert changed.value.code is ErrorCode.VERSION_CONFLICT
    assert changed.value.details["reason"] == "candidate_changed"
    fresh = preview(second, plan, draft)
    assert fresh.publishable
    assert fresh.source == stale.source
    assert fresh.content_digest != stale.content_digest
    assert fresh.pinned_materials[0].file_version_id == updated.file_version_id
    assert fresh.pinned_materials[0].resolved_from == "latest_at_publish"
    version: Any = owner.ask(artifacts.GetFileVersion(updated.file_version_id))
    assert version.digest == "sha256:" + sha256(NEW_GUIDE).hexdigest()

    def publication_count() -> int:
        ((count,),) = rows(
            box.dsn,
            "SELECT count(*) FROM skm_core.domain_events WHERE stream_id = %s AND event_type = %s",
            plan,
            PUBLISHED_EVENT,
        )
        return count

    before = publication_count()
    assert before == 2
    command, key = publication(plan, draft, fresh), second.new_idempotency_key()
    fault = FaultPoint.CLIENT_AFTER_SERVER_COMMIT
    with pytest.raises(InjectedFault) as lost:
        FaultyClient(second, FaultPlan({fault: 1})).dispatch(command, idempotency_key=key)
    assert lost.value.point is fault
    assert publication_count() == before + 1
    latest: Any = owner.ask(planning.GetPlan(plan))
    committed: Any = owner.ask(planning.GetRevision(plan, revision_id=latest.current_revision_id))
    receipt: Any = second.dispatch(command, idempotency_key=key)
    assert (receipt.revision_id, receipt.content_digest) == (committed.revision_id, fresh.content_digest)
    assert receipt.content_digest == committed.content_digest
    with pytest.raises(SkmError) as reuse:
        second.dispatch(replace(command, expected_content_digest=stale.content_digest), idempotency_key=key)
    assert reuse.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
    history: Any = owner.ask(planning.ListRevisions(plan))
    assert len(history.items) == 3
    assert publication_count() == before + 1

    page_query = planning.ListEntities(plan, revision_id=receipt.revision_id, kinds=("item",), limit=1)
    page: Any = second.ask(page_query)
    assert page.next_cursor
    owner.dispatch(access.RevokeToken(token.token_id))
    with pytest.raises(SkmError) as denied_page:
        second.ask(replace(page_query, after=page.next_cursor))
    assert denied_page.value.code is ErrorCode.UNAUTHENTICATED
    with pytest.raises(SkmError) as revoked:
        second.dispatch(command, idempotency_key=key)
    assert revoked.value.code is ErrorCode.UNAUTHENTICATED
    restricted: Any = owner.dispatch(
        access.CreateToken(
            "Publisher without file.read", token.principal_id, ws, ("plan.read", "plan.publish")
        )
    )
    limited = connect(restricted.secret)
    assert limited.dispatch(command, idempotency_key=key) == receipt
    new_draft = dispatch_new(owner, planning.OpenDraft(plan, base="current"))
    with pytest.raises(SkmError) as lookup:
        limited.ask(artifacts.GetFileVersion(updated.file_version_id))
    assert lookup.value.code is ErrorCode.FORBIDDEN
    with (
        pytest.raises(SkmError) as content,
        limited.open_file_version_content(FileVersionId(updated.file_version_id)),
    ):
        pytest.fail("file content opened after losing file.read")
    assert content.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(SkmError) as denied:
        preview(limited, plan, new_draft)
    assert denied.value.code is ErrorCode.FORBIDDEN
    return receipt, updated
