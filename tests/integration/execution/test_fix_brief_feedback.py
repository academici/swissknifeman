"""Fix-brief feedback: persisted brief → query bus → executor context, on memory and real PostgreSQL."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from contracts.context.harness import CHK_ID, UNIT_ID, default_work_policy
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_attempt, seed_output, seed_run, seed_task
from integration.artifacts.test_upload_flow import add_file_dto
from integration.worker.test_minimal_triage import (
    admitted_stage,
    checks,
    execute,
    fake_result,
    record,
    red_case,
    red_result,
    review,
)
from integration.worker.test_worker_loop import documents
from skm.adapters.memory.execution import fix_briefs as memory_briefs
from skm.adapters.postgres.execution import fix_briefs as postgres_briefs
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, ValidationFailed
from skm.kernel.ids import EntityId
from skm.modules.artifacts import public as artifacts
from skm.modules.context import public as ctx
from skm.modules.context.domain.blocks import canonical_json_digest
from skm.modules.execution.application.queries.get_fix_brief import FixBriefView, GetFixBrief
from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
from skm.modules.execution.domain.finding import (
    Finding,
    FindingState,
    Severity,
    finding_key,
    logical_findings,
)
from skm.modules.execution.domain.fix_brief import CheckLog, TriageNote, build_fix_brief, fix_brief_to_json
from skm.modules.execution.ports import CheckRepository, ReviewRepository
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.platform.jsonc.canonical import canonical_bytes
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from unit.execution.application._support import context


def _seed(side: Any) -> tuple[Any, Any, Any, Any]:
    with side.uow() as uow:
        run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        output = seed_output(side, uow, attempt)
        uow.commit()
    return run, task, attempt, output


def _finding(side: Any, n: int, severity: Severity = Severity.MAJOR) -> Finding:
    loc = {"mount": "repo", "path": f"src/component_{n}.py", "line_start": n}
    return Finding(
        side.new_id(),
        side.new_id(),
        f"F{n}",
        finding_key(loc, "logic", "failure", "problem"),
        severity,
        "high",
        "correctness",
        "logic",
        "problem " * 1000,
        "failure " * 1000,
        loc,
        None,
        side.new_id(),
        FindingState.CONFIRMED,
    )


def _brief(side: Any, task: Any, attempt: Any, findings: Any = (), checks: Any = (), **kw: Any) -> Any:
    return build_fix_brief(
        findings,
        checks,
        kw.pop("limits", {}),
        brief_id=kw.pop("brief_id", side.new_id()),
        task_id=task.id,
        attempt_id=attempt.id,
        source_review_id=None,
        source_check_round=1,
        full_report_file_version_id=side.fv1,
        triage={
            f.finding_key: TriageNote("fix_now", fix="fix " * 1000, observed="observed " * 500)
            for f in findings
        },
        **kw,
    )


def _draft(side: Any, run: Any, feedback: Any) -> Any:
    step_ref = str(side.new_id())
    with side.uow() as uow:
        req = ctx.ContextRequest(
            workspace_id=side.ws,
            project_id=side.proj,
            plan_id=side.plan1,
            revision_id=side.rev1,
            entity_id=UNIT_ID,
            project_slug="skm",
            purpose=ctx.StepPurpose("executor", "execute", step_ref, 1, 1),
            agent_profile_version_id=side.workflow_rv_id,
            runtime=ctx.RuntimeTarget(
                "codex_cli",
                "gpt-5",
                128000,
                frozenset(),
                frozenset(),
                (),
                "plan",
                "bounded_fix",
                "isolated",
                (),
                frozenset(),
                ("AGENTS.md",),
            ),
            permissions=ctx.PermissionsSummary(
                ("repo:src/**",), ("repo:**",), ("pytest",), (), "none", (), ()
            ),
            run=ctx.RunParams(str(run.id), "default", 1, 1, None, "none", "json", "en", ()),
            execution_blocks=ctx.ExecutionBlocks(
                default_work_policy(), (), feedback, None, None, (), None, (), ()
            ),
            resume=None,
            task_risk="medium",
            research_queries=(),
            pack_pins=None,
        )
        draft = ctx.assemble_draft(
            uow,
            side.app.gateways,
            req,
            config=context(side, uow, run).config,
            owner_ref=f"step:{step_ref}",
        )
        uow.commit()
    return draft


def _feedback(draft: Any) -> Any:
    blocks = [b for b in draft.blocks if b.block_type is ctx.BlockType.REVIEW_FEEDBACK]
    assert len(blocks) == 1
    return json.loads(blocks[0].content)


def _red_check(side: Any, run: Any, task: Any, attempt: Any, output: Any) -> CheckExecution:
    return CheckExecution(
        side.new_id(),
        side.ws,
        run.id,
        task.id,
        attempt.id,
        output.id,
        EntityId(UUID(CHK_ID)),
        "P1.1:V1",
        CheckKind.COMMAND,
        True,
        CheckState.FAILED,
        1,
        "FAILED",
        None,
        None,
        "sha256:" + "e" * 64,
        side.clock.now(),
        side.clock.now(),
        1,
    )


def test_two_megabyte_log_is_persisted_queried_and_bounded_in_executor_context(exec_side: Any) -> None:
    side = exec_side
    run, task, attempt, output = _seed(side)
    # UTF-8 boundaries and >40 lines exercise both independent tail caps.
    log = "PRIVATE-STDOUT-PREFIX\n" + ("ошибка 💥 " * 120 + "\n") * 2000
    assert len(log.encode()) > 2 * 1024 * 1024
    if side.kind == "postgres":
        with side.uow(readonly=True) as uow:
            side.clock.set(uow.connection.execute("SELECT clock_timestamp()").fetchone()[0])
    payload = log.encode()
    uploaded = side.client.upload_blob(side.ws, (payload,), size=len(payload), media_type="text/plain")
    log_id = side.client.dispatch(add_file_dto(side.ws, side.proj, uploaded)).file_version_id
    check = _red_check(side, run, task, attempt, output)
    brief = _brief(side, task, attempt, checks=(check,), logs={check.id: CheckLog(log, log_id)})
    assert (
        brief.digest
        == _brief(
            side, task, attempt, checks=(check,), logs={check.id: CheckLog(log, log_id)}, brief_id=brief.id
        ).digest
    )
    with side.uow() as uow:
        uow.repo(CheckRepository).add_many((check,))
        repo = uow.repo(ReviewRepository)
        if side.kind == "postgres":
            postgres_briefs.add_fix_brief(uow.connection, brief)
            assert postgres_briefs.get_fix_brief(uow.connection, brief.id) == repo.get_fix_brief(brief.id)
        else:
            memory_briefs.add_fix_brief(repo._backend, brief)
            assert memory_briefs.get_fix_brief(repo._backend, brief.id) == repo.get_fix_brief(brief.id)
        uow.commit()
    result = side.client.ask(GetFixBrief(brief.id))
    assert isinstance(result, FixBriefView)
    assert result.document == fix_brief_to_json(brief)
    assert FixBriefView.from_json(result.to_json()) == result
    assert GetFixBrief.from_json(GetFixBrief(brief.id).to_json()) == GetFixBrief(brief.id)
    assert result.full_report_file_version_id == brief.full_report_file_version_id
    with side.uow(readonly=True) as uow:
        assert artifacts.read_text_content(uow, log_id, max_bytes=len(payload) + 1) == log
        if side.kind == "postgres":
            row = uow.connection.execute(
                "SELECT document FROM skm_execution.fix_briefs WHERE id = %s", (brief.id,)
            ).fetchone()
            assert row[0] == result.document
    feedback = {
        "fix_brief": result.document,
        "stdout": log,
        "transcript": log,
        "messages": [log],
        "full_report_file_version_id": str(side.new_id()),
    }
    original = deepcopy(feedback)
    draft = _draft(side, run, feedback)
    received = _feedback(draft)
    assert feedback == original
    assert set(received) == {"fix_brief", "full_report_file_version_id"}
    assert received["full_report_file_version_id"] == str(brief.full_report_file_version_id)
    bounded = received["fix_brief"]
    assert bounded["truncated"] is True
    entry = bounded["checks"][0]
    assert 0 < len(entry["tail"].encode()) == entry["tail_bytes"] <= 4000
    assert len(entry["tail"].splitlines()) <= 40
    assert entry["full_log_file_version_id"] == str(log_id)
    assert "PRIVATE-STDOUT-PREFIX" not in str(draft)
    retry = _draft(side, run, {"schema_errors": [], "stdout": log})
    assert all(b.block_type is not ctx.BlockType.REVIEW_FEEDBACK for b in retry.blocks)
    assert "PRIVATE-STDOUT-PREFIX" not in str(retry)
    # Duplicate persistence cannot overwrite an immutable brief.
    with pytest.raises(SkmError), side.uow() as uow:
        uow.repo(ReviewRepository).add_fix_brief(brief)
    restricted = side.restricted_client(("run.read",), scope_id=side.proj2, owner_token=True)
    with pytest.raises(SkmError) as denied:
        restricted.ask(GetFixBrief(brief.id))
    assert denied.value.code in {ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND}
    with pytest.raises(SkmError) as missing:
        side.client.ask(GetFixBrief(side.new_id()))
    assert missing.value.code is ErrorCode.NOT_FOUND


def test_overflow_preserves_blockers_defers_findings_and_clips_fields(exec_side: Any) -> None:
    side = exec_side
    run, task, attempt, _ = _seed(side)
    findings = [_finding(side, n, Severity.BLOCKER if n < 3 else Severity.MAJOR) for n in range(1, 6)]
    brief = _brief(side, task, attempt, findings, limits={"max_findings": 1})
    assert brief.diagnostics == ("FIX_BRIEF_OVER",)
    assert {i.finding_key for i in brief.items} == {f.finding_key for f in findings[:2]}
    assert set(brief.deferred_finding_keys) == {f.finding_key for f in findings[2:]}
    with side.uow() as uow:
        uow.repo(ReviewRepository).add_fix_brief(brief)
        uow.commit()
    received = _feedback(_draft(side, run, {"fix_brief": side.client.ask(GetFixBrief(brief.id)).document}))
    doc = received["fix_brief"]
    assert doc["truncated"] is True
    assert doc["deferred_finding_keys"] == list(brief.deferred_finding_keys)
    for item in doc["items"]:
        for field, cap in {"problem": 1200, "fix": 800, "observed": 600, "reproduction": 400}.items():
            assert len(item[field]) <= cap
        assert sum(len(item[k]) for k in ("problem", "fix", "observed", "reproduction")) <= 3000
        assert f"file_version:{side.fv1}#{item['finding_key']}" in item["problem"]
    carried = [replace(f, state=FindingState.DEFERRED) for f in findings[2:]]
    next_brief = _brief(side, task, attempt, [*carried, _finding(side, 9)], limits={"max_findings": 1})
    assert next_brief.items[0].finding_key in brief.deferred_finding_keys


@pytest.mark.parametrize(
    "bad", ["stdout", "oversize", "lines", "tail_bytes", "digest", "deferred", "field", "clipped", "metadata"]
)
def test_unbounded_or_unvalidated_brief_cannot_enter_context(exec_side: Any, bad: str) -> None:
    run, task, attempt, _ = _seed(exec_side)
    doc: Any = fix_brief_to_json(_brief(exec_side, task, attempt, [_finding(exec_side, 1)]))
    doc["checks"] = [
        {
            "check_key": "red",
            "exit_code": 1,
            "tail": "failure",
            "tail_bytes": 7,
            "full_log_file_version_id": str(exec_side.fv1),
        }
    ]
    if bad == "stdout":
        doc["checks"][0]["stdout"] = "raw transcript"
    elif bad == "oversize":
        doc["checks"][0].update(tail="я" * 2100, tail_bytes=4200)
    elif bad == "lines":
        doc["checks"][0].update(tail="x\n" * 41, tail_bytes=82)
    elif bad == "tail_bytes":
        doc["checks"][0]["tail_bytes"] = 0
    elif bad == "deferred":
        doc.update(deferred_finding_keys=["fk-" + "a" * 16], truncated=False)
    elif bad == "field":
        doc["items"][0]["problem"] = "x" * 1201
    elif bad == "clipped":
        doc["truncated"] = False
    elif bad == "metadata":
        doc["items"][0]["severity"] = "blocker"
        doc["checks"][0]["check_key"] = "x" * 25000
    doc["digest"] = canonical_json_digest({k: v for k, v in doc.items() if k != "digest"})
    if bad == "digest":
        doc["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationFailed):
        _draft(exec_side, run, {"fix_brief": doc})


@pytest.mark.parametrize("severity", ["blocker", "minor"])
def test_real_role_rounds_keep_key_confirmation_and_one_logical_finding(
    exec_side: Any, tmp_path: Any, monkeypatch: Any, severity: str
) -> None:
    case = red_case(exec_side, tmp_path, monkeypatch)
    stage, step, _ = admitted_stage(case, "triager")
    payload = fake_result(case, tmp_path / "triage", monkeypatch, "triager", documents()["triager"])
    reply = record(case, stage, step, payload)
    assert record(case, stage, step, payload) == reply
    with exec_side.uow(readonly=True) as uow:
        first = uow.repo(ReviewRepository).findings_for_task(case.task.id)
        assert len(first) == 1
        assert first[0].state is FindingState.CONFIRMED
    fixed = execute(case, tmp_path / "execute-again", monkeypatch, "answer = 42\n")
    checks(case, fixed["next"])
    result = red_result()
    result["findings"][0].update(id="F99", severity=severity, confidence="low")
    result["findings"][0]["location"]["line_start"] = 91
    review(case, tmp_path / "review-again", monkeypatch, result)
    with exec_side.uow(readonly=True) as uow:
        repo = uow.repo(ReviewRepository)
        rows = repo.findings_for_task(case.task.id)
        reviews = repo.for_task(case.task.id)
        logical = logical_findings(rows, {r.id: r.round_no for r in reviews})
    assert len(rows) == 2
    assert len(logical) == 1
    latest = logical[0]
    assert latest.finding_key == first[0].finding_key
    assert latest.first_seen_review_id == first[0].first_seen_review_id
    assert latest.state is FindingState.CONFIRMED
    assert latest.severity.value == severity
    assert latest.local_id == "F99"
    assert latest.location["line_start"] == 91


def _resign(doc: Any) -> Any:
    doc["digest"] = canonical_json_digest({k: v for k, v in doc.items() if k != "digest"})
    return doc


@pytest.mark.parametrize("cap", [4500, 1500], ids=["blockers-fit", "blockers-over"])
def test_non_blockers_share_the_total_budget_with_blockers(exec_side: Any, cap: int) -> None:
    side = exec_side
    run, task, attempt, _ = _seed(side)
    findings = [_finding(side, 1, Severity.BLOCKER), _finding(side, 2)]
    doc: Any = fix_brief_to_json(_brief(side, task, attempt, findings))
    doc["limits"]["max_total_bytes"] = cap
    if cap == 1500:
        doc["items"][1].update(problem="small non-blocker", fix="", observed="", reproduction="")
    _resign(doc)
    assert len(canonical_bytes(doc)) > cap
    assert len(canonical_bytes({**doc, "items": doc["items"][1:]})) <= cap
    with pytest.raises(ValidationFailed):
        _draft(side, run, {"fix_brief": doc})
    # A blocker-only brief is admitted even when the blockers alone exceed the cap.
    blocker_only = _resign({**doc, "items": doc["items"][:1]})
    assert (len(canonical_bytes(blocker_only)) > cap) == (cap == 1500)
    assert _feedback(_draft(side, run, {"fix_brief": blocker_only}))["fix_brief"] == blocker_only
    # Exact canonical byte boundary includes blockers, metadata, checks and the digest.
    for _ in range(3):
        doc["limits"]["max_total_bytes"] = len(canonical_bytes(doc))
    _resign(doc)
    assert len(canonical_bytes(doc)) == doc["limits"]["max_total_bytes"]
    assert _feedback(_draft(side, run, {"fix_brief": doc}))["fix_brief"] == doc
    doc["limits"]["max_total_bytes"] -= 1
    with pytest.raises(ValidationFailed):
        _draft(side, run, {"fix_brief": _resign(doc)})


@pytest.mark.parametrize(
    ("key", "default"),
    [
        ("max_findings", 12),
        ("max_finding_chars", 3000),
        ("max_total_bytes", 24000),
        ("max_inline_evidence_bytes", 4000),
    ],
)
def test_document_cannot_raise_default_or_configured_limits(exec_side: Any, key: str, default: int) -> None:
    run, task, attempt, _ = _seed(exec_side)
    doc: Any = fix_brief_to_json(_brief(exec_side, task, attempt))
    doc["limits"][key] = default + 1
    with pytest.raises(ValidationFailed):
        _draft(exec_side, run, {"fix_brief": _resign(doc)})
    configured = exec_side.client.dispatch(
        SetValue(SetValueDefsScopeRef("plan", exec_side.plan1), f"execution.handoff.{key}", default // 2)
    )
    doc["limits"][key] = default
    with pytest.raises(ValidationFailed):
        _draft(exec_side, run, {"fix_brief": _resign(doc)})
    doc["limits"][key] = default // 2
    received = _feedback(_draft(exec_side, run, {"fix_brief": _resign(doc)}))
    assert received["fix_brief"] == doc
    exec_side.client.dispatch(
        SetValue(
            SetValueDefsScopeRef("plan", exec_side.plan1),
            f"execution.handoff.{key}",
            default * 2,
            expected_row_version=configured.entry.row_version,
        )
    )
    doc["limits"][key] = default + 1
    assert _feedback(_draft(exec_side, run, {"fix_brief": _resign(doc)}))["fix_brief"] == doc


@pytest.mark.parametrize("mutation", [None, "missing", "misplaced", "extra-line", "fake-marker"])
def test_builder_forty_content_lines_and_one_clip_marker(exec_side: Any, mutation: str | None) -> None:
    side = exec_side
    run, task, attempt, output = _seed(side)
    check = _red_check(side, run, task, attempt, output)
    brief = _brief(
        side,
        task,
        attempt,
        checks=(check,),
        logs={check.id: CheckLog("\n".join(f"line {n}" for n in range(100)), side.fv1)},
    )
    doc: Any = fix_brief_to_json(brief)
    entry = doc["checks"][0]
    lines = entry["tail"].splitlines()
    assert len(lines) == 41
    assert lines[0].startswith("… [clipped ")
    assert len(entry["tail"].encode()) <= 4000
    if mutation is None:
        assert _feedback(_draft(side, run, {"fix_brief": doc}))["fix_brief"] == doc
        return
    if mutation == "missing":
        lines[0] = "another content line"
    elif mutation == "misplaced":
        lines = [*lines[1:], lines[0]]
    elif mutation == "extra-line":
        lines.append("one content line too many")
    else:
        lines[0] = "… [clipped not-a-builder-marker]"
    entry.update(tail="\n".join(lines), tail_bytes=len("\n".join(lines).encode()))
    with pytest.raises(ValidationFailed):
        _draft(side, run, {"fix_brief": _resign(doc)})


@pytest.mark.parametrize("mutation", ["duplicate", "deferred-overlap", "severity-order"])
def test_finding_identity_and_severity_order_are_validated(exec_side: Any, mutation: str) -> None:
    side = exec_side
    run, task, attempt, _ = _seed(side)
    findings = [_finding(side, n, severity) for n, severity in enumerate(Severity, 1)]
    doc: Any = fix_brief_to_json(_brief(side, task, attempt, findings))
    assert [it["severity"] for it in doc["items"]] == ["blocker", "major", "minor", "nit"]
    assert _feedback(_draft(side, run, {"fix_brief": doc}))["fix_brief"] == doc
    if mutation == "duplicate":
        doc["items"][1]["finding_key"] = doc["items"][0]["finding_key"]
    elif mutation == "deferred-overlap":
        doc["deferred_finding_keys"] = [doc["items"][0]["finding_key"]]
        doc["truncated"] = True
    else:
        doc["items"] = list(reversed(doc["items"]))
    with pytest.raises(ValidationFailed):
        _draft(side, run, {"fix_brief": _resign(doc)})
