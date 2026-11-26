"""A visa admits the compiled progressive selection of one published revision."""

from dataclasses import replace
from typing import Any, cast

import pytest

from contracts.execution.harness import _publish_revision
from contracts.execution.seed_helpers import seed_attempt, seed_output, seed_stage
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.roles import Role
from skm.modules.access.ports import MembershipRepository
from skm.modules.execution.domain.attempt import (
    AttemptEndReason,
    AttemptState,
    record_output,
    transition_attempt,
)
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.domain.task import TaskStatus, accept
from skm.modules.execution.generated.commands import (
    ApproveRevision,
    CancelRun,
    CarryForwardResult,
    StartRun,
    StartRunSelectionVariant1,
    ValidateForExecution,
    ValidateForExecutionSelectionVariant1,
)
from skm.modules.execution.generated.queries import GetReadinessReport
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    BundleRepository,
    EnvironmentRepository,
    ReadinessRepository,
    RunRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning
from skm.modules.planning.domain.specification import to_document

from ._support import _shared_side as _shared_side
from ._support import side as side

_MODE = "progressive_per_phase"


def _with_next_phase(side: Any, *, predecessor: bool = False, detailed: bool = False) -> Any:
    with side.uow(readonly=True) as uow:
        current = planning.get_plan_ref(uow, side.plan1).current_revision_id
        assert current is not None
        spec = planning.get_revision_specification(uow, current)
    doc = to_document(spec)
    phases = cast("list[JsonObject]", doc["phases"])
    if not any(phase["key"] == "P9" for phase in phases):
        phases.append(
            {
                "key": "P9",
                "title": "Next phase",
                "goal": "Deliver the next increment.",
                "design_state": "detailed" if detailed else "skeleton",
                "contract": {"consumes": ["artifact"], "produces": ["next artifact"]},
                "deliverables": ["next artifact"],
                "depends_on": [],
            }
        )
    if detailed:
        cast("list[JsonObject]", doc["items"]).append(
            {
                "key": "P9.1",
                "phase": "P9",
                "title": "Next item",
                "summary": "Deliver more work.",
                "why": "Complete the next increment.",
                "work_kind": "docs",
                "scope": {"include": ["repo:docs/**"], "exclude": []},
                "guidance_md": "Write the next artifact.",
                "deliverables": ["next artifact"],
                "review": {"mode": "required", "independence": "separate_session"},
            }
        )
        cast("list[JsonObject]", doc.setdefault("criteria", [])).append(
            {
                "key": "AC99",
                "owner": "P9.1",
                "statement": "The next artifact is present.",
                "verification_mode": "review",
            }
        )
    if predecessor:
        phases[0]["depends_on"] = ["P9"]
    return _publish_revision(
        side.app,
        side.client,
        side.owner,
        side.clock,
        side.plan1,
        {key: doc[key] for key in ("phases", "items", "criteria") if key in doc},
        "current",
    )


def _preview(side: Any, revision: Any, *, phases: tuple[str, ...] = (), keys: tuple[str, ...] = ()) -> Any:
    return side.client.dispatch(
        ValidateForExecution(
            side.plan1,
            revision,
            mode=_MODE,
            selection=ValidateForExecutionSelectionVariant1(phases=phases, task_keys=keys),
        )
    )


def test_unselected_skeleton_is_allowed_but_selected_and_required_skeletons_are_refused(side: Any) -> None:
    revision = _with_next_phase(side)
    full = side.client.dispatch(ValidateForExecution(side.plan1, revision))
    assert full.status == "not_ready"
    valid = _preview(side, revision, phases=("P1",))
    assert valid.status in {"ready", "ready_with_advisories"}
    current = side.client.ask(GetReadinessReport(report_id=valid.report_id))
    assert current.effective_status == valid.status
    with side.uow(readonly=True) as uow:
        saved = uow.repo(ReadinessRepository).get(valid.report_id)
        assert saved.scope.phase_keys == ("P1",)
        assert saved.scope.kind == "selection"
        assert saved.start_request == {
            "mode": _MODE,
            "overrides": {},
            "selection": {"phases": ["P1"], "task_keys": []},
        }

    for report in (
        _preview(side, revision, phases=("P9",)),
        _preview(side, _with_next_phase(side, predecessor=True), phases=("P1",)),
    ):
        assert report.status == "not_ready"
        assert "PHASE_SKELETON" in {f["code"] for f in report.findings}
        with pytest.raises(SkmError) as caught:
            side.client.dispatch(ApproveRevision(side.plan1, report.report_id, "blocked"))
        assert caught.value.code is ErrorCode.READINESS_REQUIRED


def test_item_selection_checks_its_own_phase_and_requires_a_nonempty_selection(side: Any) -> None:
    with side.uow(readonly=True) as uow:
        doc = to_document(planning.get_revision_specification(uow, side.rev2))
    cast("list[JsonObject]", doc["phases"])[0]["design_state"] = "skeleton"
    revision = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan1, {"phases": doc["phases"]}, "current"
    )
    blocked = _preview(side, revision, keys=("P1.1/U1",))
    assert blocked.status == "not_ready"
    assert "PHASE_SKELETON" in {f["code"] for f in blocked.findings}
    with pytest.raises(SkmError) as caught:
        _preview(side, revision)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_visa_is_human_scoped_and_binds_report_selection_and_revision(side: Any) -> None:
    revision = _with_next_phase(side)
    report = _preview(side, revision, phases=("P1",))
    approve = ApproveRevision(side.plan1, report.report_id, "Reviewed the selected increment")
    for role in (Role.VIEWER, Role.MEMBER, Role.MAINTAINER):
        with side.uow() as uow:
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(side.ws), side.viewer.principal_id, role, None, side.clock.now())
            )
            uow.commit()
        if role is Role.MAINTAINER:
            signed = side.viewer_client.dispatch(approve)
        else:
            with pytest.raises(SkmError) as caught:
                side.viewer_client.dispatch(approve)
            assert caught.value.code is ErrorCode.FORBIDDEN

    start = StartRun(
        side.plan1,
        revision,
        None,
        {},
        "Start checked increment",
        selection=StartRunSelectionVariant1(phases=("P1",)),
        mode=_MODE,
        visa_id=signed.visa_id,
    )
    for bad in (
        replace(start, visa_id=None, readiness_report_id=report.report_id),
        replace(start, revision_id=side.rev2),
        replace(start, selection=StartRunSelectionVariant1(task_keys=("P1.1/U1",))),
        replace(start, mode="full"),
    ):
        with pytest.raises(SkmError) as caught:
            side.client.dispatch(bad)
        assert caught.value.code is ErrorCode.READINESS_REQUIRED

    result = side.client.dispatch(start)
    with side.uow(readonly=True) as uow:
        stored = uow.repo(ReadinessRepository).get_visa(signed.visa_id)
        assert stored.selection == {"phases": ["P1"], "task_keys": []}
        assert stored.signed_by == side.viewer.principal_id
        run = uow.repo(RunRepository).get(result.run_id)
        assert run.readiness_report_id == stored.readiness_report_id
        selection = uow.repo(BundleRepository).get(run.id).selection
        assert selection is not None
        assert selection.phases == ("P1",)
        assert all(key.startswith("P1") for key in selection.compiled_keys)


def _start_increment(side: Any, revision: Any, *keys: str) -> Any:
    report = _preview(side, revision, keys=keys)
    visa = side.client.dispatch(ApproveRevision(side.plan1, report.report_id, "Approve the increment"))
    return side.client.dispatch(
        StartRun(
            side.plan1,
            revision,
            None,
            {},
            "Start increment",
            selection=StartRunSelectionVariant1(task_keys=keys),
            mode=_MODE,
            visa_id=visa.visa_id,
        )
    ).run_id


def _seed_attempt(side: Any, run_id: Any, *, accepted: bool) -> Any:
    with side.uow() as uow:
        tasks = uow.repo(TaskRepository)
        task = next(t for t in tasks.list_for_run(run_id) if t.display_key == "P1.1/U1")
        attempt = seed_attempt(side, uow, run_id, task.id)
        uow.repo(EnvironmentRepository).upsert(
            ExecutionEnvironment(
                side.new_id(),
                attempt.id,
                side.host1,
                EnvironmentKind.GIT_WORKTREE,
                (BaselineEntry("repo", side.repo_id, "1" * 40, "1" * 40, None),),
                attempt_branch(attempt.id),
                f"/test/{attempt.id}",
                EnvironmentState.READY,
                side.clock.now(),
                None,
                None,
            )
        )
        active = replace(
            task,
            status=TaskStatus.INTEGRATING if accepted else TaskStatus.ASSIGNED,
            current_attempt_id=attempt.id,
            attempt_count=1,
            blocking_reason=None,
            row_version=task.row_version + 1,
        )
        tasks.save(active, expected_version=task.row_version)
        if accepted:
            output = seed_output(side, uow, attempt)
            current = record_output(attempt, output, previous=None)
            attempts = uow.repo(AttemptRepository)
            attempts.save(current, expected_version=attempts.version(attempt.id))
            tasks.save(
                accept(active, rule="T19", attempt=current, output=output),
                expected_version=active.row_version,
            )
            attempts.save(
                transition_attempt(
                    current,
                    AttemptState.COMPLETED,
                    now=side.clock.now(),
                    end_reason=AttemptEndReason.ACCEPTED,
                ),
                expected_version=attempts.version(attempt.id),
            )
        else:
            seed_stage(
                side,
                uow,
                attempt,
                stage_id="prepare",
                stage_type="prepare_environment",
                state=StageState.COMPLETED,
            )
        uow.commit()
    return task.id


def test_expansion_carries_compatible_prepared_task_into_new_revision_and_run(side: Any) -> None:
    source_run = _start_increment(side, side.rev2, "P1.1/U1")
    source = _seed_attempt(side, source_run, accepted=True)
    side.client.dispatch(CancelRun(source_run, "Close initial increment"))
    with side.uow() as uow:
        accepted = uow.repo(TaskRepository).get(source)
        assert accepted.accepted_attempt_id is not None
        environments = uow.repo(EnvironmentRepository)
        original = environments.for_attempt(accepted.accepted_attempt_id)
        assert original is not None
        assert environments.mark_removed((original.id,), side.host1, side.clock.now()) == 1
        uow.commit()
    revision = _with_next_phase(side, detailed=True)
    target_run = _start_increment(side, revision, "P1.1/U1", "P9#gate")
    target = _seed_attempt(side, target_run, accepted=False)
    command = CarryForwardResult(source, target, "Carry the compatible accepted result forward")
    with pytest.raises(SkmError) as denied:
        side.viewer_client.dispatch(command)
    assert denied.value.code is ErrorCode.FORBIDDEN
    result = side.client.dispatch(command)
    with side.uow(readonly=True) as uow:
        assert uow.repo(RunRepository).get(source_run).revision_id == side.rev2
        assert uow.repo(RunRepository).get(target_run).revision_id == revision
        assert uow.repo(TaskRepository).get(target).status is TaskStatus.ACCEPTED
        (row,) = uow.repo(AcceptanceRepository).carry_forwards_for_run(target_run)
        assert row.id == result.carry_forward_id
        assert row.compatibility_inputs["schema_version"] == 1
        assert row.compatibility_inputs["source"] == row.compatibility_inputs["target"]


def test_visa_rechecks_signer_even_when_caller_can_start_and_readiness_is_optional(side: Any) -> None:
    from ._support import context, set_setting

    set_setting(side, "execution.readiness.required", False)
    with side.uow(readonly=True) as uow:
        assert context(side, uow).config.get("execution.readiness.required") is False
    scope = ScopeId(side.ws)
    membership = Membership(scope, side.viewer.principal_id, Role.MAINTAINER, None, side.clock.now())
    with side.uow() as uow:
        uow.repo(MembershipRepository).upsert(membership)
        uow.commit()
    report = _preview(side, side.rev2, phases=("P1",))
    visa = side.viewer_client.dispatch(ApproveRevision(side.plan1, report.report_id, "Approved selection"))
    start = StartRun(
        side.plan1,
        side.rev2,
        None,
        {},
        "Run approved selection",
        selection=StartRunSelectionVariant1(phases=("P1",)),
        mode=_MODE,
        visa_id=visa.visa_id,
    )
    caller = side.restricted_client(["run.start"], owner_token=True)
    with pytest.raises(SkmError) as missing:
        caller.dispatch(replace(start, visa_id=None, readiness_report_id=report.report_id))
    assert missing.value.code is ErrorCode.READINESS_REQUIRED
    different = _preview(side, side.rev2, phases=("P1",))
    with pytest.raises(SkmError) as mismatched:
        caller.dispatch(replace(start, readiness_report_id=different.report_id))
    assert mismatched.value.code is ErrorCode.READINESS_REQUIRED
    caller.dispatch(start)
    with side.uow() as uow:
        uow.repo(MembershipRepository).upsert(replace(membership, role=Role.MEMBER))
        uow.commit()
    with pytest.raises(SkmError, match="signer") as revoked:
        side.client.dispatch(start)
    assert revoked.value.code is ErrorCode.FORBIDDEN


def test_optional_full_mode_visa_expires_at_its_deadline(side: Any) -> None:
    from datetime import timedelta

    from ._support import set_setting

    set_setting(side, "execution.readiness.required", False)
    set_setting(side, "execution.readiness.max_age_seconds", 60)
    report = side.client.dispatch(ValidateForExecution(side.plan1, side.rev2))
    visa = side.client.dispatch(ApproveRevision(side.plan1, report.report_id, "Approve full run"))
    side.clock.advance(timedelta(seconds=60))
    with pytest.raises(SkmError, match="visa") as expired:
        side.client.dispatch(StartRun(side.plan1, side.rev2, None, {}, "Expired", visa_id=visa.visa_id))
    assert expired.value.code is ErrorCode.READINESS_REQUIRED


def test_visa_rechecks_linked_design_brief_evidence(side: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from skm.modules.planning.generated.commands import DesignPlan, DesignPlanResearchReferencesItem

    evidence = DesignPlanResearchReferencesItem("design:requirements", "sha256:" + "a" * 64)
    brief = side.client.dispatch(DesignPlan(side.plan1, "Deliver", research_references=(evidence,)))
    revision = _publish_revision(
        side.app,
        side.client,
        side.owner,
        side.clock,
        side.plan1,
        {"design_brief_id": str(brief.design_brief_id)},
        "current",
    )
    report = _preview(side, revision, phases=("P1",))
    visa = side.client.dispatch(ApproveRevision(side.plan1, report.report_id, "Reviewed evidence"))
    with side.uow(readonly=True) as uow:
        saved = planning.get_design_brief(uow, side.plan1, brief.design_brief_id)
    changed = replace(saved.research_references[0], content_digest="sha256:" + "b" * 64)
    monkeypatch.setattr(
        planning, "get_design_brief", lambda *_: replace(saved, research_references=(changed,))
    )
    with pytest.raises(SkmError) as stale:
        side.client.dispatch(
            StartRun(
                side.plan1,
                revision,
                None,
                {},
                "Stale design",
                mode=_MODE,
                selection=StartRunSelectionVariant1(phases=("P1",)),
                visa_id=visa.visa_id,
            )
        )
    assert stale.value.details["stale_parts"] == ["materials"]


def test_required_design_visa_gates_ordinary_run_with_readiness_disabled(side: Any) -> None:
    from skm.modules.planning.generated.commands import DesignPlan

    from ._support import set_setting

    set_setting(side, "execution.readiness.required", False)
    brief = side.client.dispatch(DesignPlan(side.plan1, "Deliver", visa_policy="required"))
    revision = _publish_revision(
        side.app,
        side.client,
        side.owner,
        side.clock,
        side.plan1,
        {"design_brief_id": str(brief.design_brief_id)},
        "current",
    )
    report = side.client.dispatch(ValidateForExecution(side.plan1, revision))
    start = StartRun(side.plan1, revision, None, {}, "Run linked revision")
    for report_id in (None, report.report_id):
        with pytest.raises(SkmError, match="visa") as denied:
            side.client.dispatch(replace(start, readiness_report_id=report_id))
        assert denied.value.code is ErrorCode.READINESS_REQUIRED
    visa = side.client.dispatch(ApproveRevision(side.plan1, report.report_id, "Approve full run"))
    assert side.client.dispatch(replace(start, visa_id=visa.visa_id)).run_id
