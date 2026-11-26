"""Gate workflow safety constraints."""

# The common acceptance fixtures model immutable records, never acceptance shortcuts.
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast

import pytest

from skm.kernel.errors import SkmError
from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.acceptance import (
    AcceptanceBasis,
    AcceptanceDecision,
    Accepted,
    NotAcceptable,
)
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.deviation import DeviationAcceptance
from skm.modules.execution.domain.external_effect import EffectKind, EffectState, ExternalEffect
from skm.modules.execution.domain.finding import FindingState, Severity
from skm.modules.execution.domain.gate_range import range_bounds
from skm.modules.execution.domain.gates import GateInputs, decide_gate, decide_plan_acceptance
from skm.modules.execution.domain.output import OutputSource
from skm.modules.execution.domain.readiness import canonical_digest
from skm.modules.execution.domain.review import ReviewClearance, Verdict
from skm.modules.execution.domain.stage_record import StageOutcomeKind as K
from skm.modules.execution.domain.task import (
    GATE_KINDS,
    PathPattern,
    ReviewMode,
    TaskKind,
    TaskOrigin,
    TaskStatus,
)
from skm.modules.execution.domain.workflow.actions import CreateFollowups, Done, Escalate, RunStage, WaitFor
from skm.modules.execution.domain.workflow.definition import (
    WORKFLOW_SCHEMA,
    gate_workflow_violations,
    parse_workflow,
)
from skm.modules.execution.domain.workflow.engine import decide_advance
from unit.execution.domain.test_acceptance import (
    NOW,
    RUN,
    TASK,
    WS,
    make_check,
    make_finding,
    make_output,
    make_review,
    make_task,
    uid,
    verdict,
)
from unit.execution.domain.test_advance_table import (
    QUICK,
    REVIEWED,
    e,
    make_state,
    triaged,
)


def workflow(role: str, kind: str) -> JsonValue:
    document: dict[str, Any] = {
        "schema": WORKFLOW_SCHEMA,
        "id": "gate-safety",
        "version": "1.0.0",
        "applies_to": ["code"],
        "stage": [
            {"id": "prepare", "type": "prepare_environment", "for_kinds": [kind]},
            {"id": "agent", "type": "agent_step", "role": role, "for_kinds": [kind]},
        ],
    }
    return cast("JsonValue", document)


@pytest.mark.parametrize("kind", sorted(GATE_KINDS))
def test_gate_rejects_writable_executor(kind: str) -> None:
    parsed, violations = parse_workflow(workflow("executor", kind))
    assert parsed is None
    assert any(v.reason == "gate_executor_forbidden" for v in violations)


def test_gate_allows_read_only_triage_and_work_allows_executor() -> None:
    for role, kind in (("triager", "phase_gate"), ("executor", "item")):
        parsed, violations = parse_workflow(workflow(role, kind))
        assert parsed is not None
        assert not violations


def gate_inputs(**changes: Any) -> GateInputs:
    task = make_task(kind=TaskKind.PHASE_GATE, declared_write_scope=(), review_mode=ReviewMode.WAIVED)
    member = make_task(
        id=uid(101),
        status=TaskStatus.ACCEPTED,
        accepted_attempt_id=uid(201),
        accepted_output_id=uid(301),
        display_key="P1.1",
    )
    output = replace(make_output(), source=OutputSource.RANGE, produced_by_step_id=None)
    return replace(GateInputs(task, (member,), output, (), {}, (), (), (), True), **changes)


def codes(result: Any) -> tuple[str, ...]:
    assert isinstance(result, NotAcceptable)
    return result.codes


def test_closed_gate_kinds_and_empty_scopes() -> None:
    assert {
        TaskKind.ITEM_GATE,
        TaskKind.PHASE_GATE,
        TaskKind.PLAN_ACCEPTANCE,
        TaskKind.GROUP_REVIEW,
        TaskKind.PLAN_AUDIT,
    } == GATE_KINDS
    with pytest.raises(SkmError):
        replace(gate_inputs().task, declared_write_scope=(PathPattern("app", "src/**"),))


@pytest.mark.parametrize(
    "status",
    [TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.SUPERSEDED, TaskStatus.SKIPPED],
)
def test_ga1_requires_terminal_members_and_recorded_skip(status: TaskStatus) -> None:
    inputs = gate_inputs()
    member = replace(inputs.members[0], status=status, accepted_attempt_id=None, accepted_output_id=None)
    assert "MEMBER_NOT_DONE" in codes(decide_gate(replace(inputs, members=(member,))))
    if status is TaskStatus.SKIPPED:
        assert isinstance(
            decide_gate(replace(inputs, members=(member,), skipped_with_decision=frozenset({member.id}))),
            Accepted,
        )


def test_ga2_missing_stale_and_latest_required_checks() -> None:
    inputs = gate_inputs()
    check = make_check()
    required = frozenset({check.check_spec_id})
    assert "REQUIRED_CHECK_NOT_PASSED" in codes(decide_gate(replace(inputs, required_checks=required)))
    for field in ("output_id", "attempt_id", "task_id", "run_id"):
        stale = replace(check, **{field: uid(999)})
        assert "REQUIRED_CHECK_NOT_PASSED" in codes(
            decide_gate(replace(inputs, checks=(stale,), required_checks=required))
        )
    red = replace(check, id=uid(502), state=CheckState.FAILED, round_no=2)
    assert "REQUIRED_CHECK_NOT_PASSED" in codes(decide_gate(replace(inputs, checks=(check, red))))
    assert isinstance(decide_gate(replace(inputs, checks=(check,))), Accepted)


@pytest.mark.parametrize(
    ("value", "expected"), [(None, "MANUAL_PENDING"), ("fail", "MANUAL_FAILED"), ("pass", None)]
)
def test_ga3_manual_verdicts(value: Any, expected: Any) -> None:
    check = make_check(kind=CheckKind.MANUAL, state=CheckState.PASSED)
    manual = {} if value is None else {check.id: verdict(value, check_id=check.id)}
    result = decide_gate(gate_inputs(checks=(check,), manual=manual))
    assert isinstance(result, Accepted) if expected is None else expected in codes(result)
    foreign = verdict("pass", check_id=uid(999))
    assert "MANUAL_PENDING" in codes(decide_gate(gate_inputs(checks=(check,), manual={check.id: foreign})))


@pytest.mark.parametrize("verdict_", [Verdict.GREEN, Verdict.ATTENTION, Verdict.RED])
def test_ga4_required_review_is_of_this_range(verdict_: Verdict) -> None:
    inputs = gate_inputs()
    inputs = replace(inputs, task=replace(inputs.task, review_mode=ReviewMode.REQUIRED))
    assert "REVIEW_MISSING" in codes(decide_gate(inputs))
    review = make_review(verdict_=verdict_, audit_scope="range")
    result = decide_gate(replace(inputs, reviews=(review,)))
    assert isinstance(result, Accepted) if verdict_ is Verdict.GREEN else "REVIEW_NOT_GREEN" in codes(result)
    stale = replace(review, output_id=uid(999))
    assert "REVIEW_MISSING" in codes(decide_gate(replace(inputs, reviews=(stale,))))
    if verdict_ is not Verdict.GREEN:
        assert isinstance(
            decide_gate(replace(inputs, reviews=(review,), clearance=ReviewClearance.CLEARED_BY_TRIAGE)),
            Accepted,
        )


@pytest.mark.parametrize("severity", [Severity.BLOCKER, Severity.MAJOR])
def test_ga5_confirmed_findings_require_closed_followups_or_own_deviation(severity: Severity) -> None:
    finding = make_finding(1, severity, FindingState.CONFIRMED)
    inputs = gate_inputs(findings=(finding,), reviews=(make_review(audit_scope="range"),))
    assert "BLOCKER_OPEN" in codes(decide_gate(inputs))
    followup = make_task(
        id=uid(120),
        kind=TaskKind.FOLLOWUP,
        spec_entity_id=None,
        origin=TaskOrigin(TASK, (finding.id,), "review_findings"),
        status=TaskStatus.ACCEPTED,
        accepted_attempt_id=uid(220),
    )
    assert isinstance(decide_gate(replace(inputs, followups=(followup,))), Accepted)
    waiver = DeviationAcceptance(uid(888), RUN, TASK, None, finding.id, "approved", uid(900), NOW, "finding")
    assert isinstance(decide_gate(replace(inputs, deviations=(waiver,))), Accepted)
    assert "BLOCKER_OPEN" in codes(
        decide_gate(replace(inputs, deviations=(replace(waiver, task_id=uid(999)),)))
    )


def test_ga6_live_policy_and_range_identity() -> None:
    assert "POLICY_DENIES" in codes(decide_gate(gate_inputs(policy_live_ok=False)))
    assert "OUTPUT_NOT_CURRENT" in codes(decide_gate(gate_inputs(output=make_output())))
    assert "OUTPUT_NOT_CURRENT" in codes(decide_gate(gate_inputs(output=None)))
    assert isinstance(decide_gate(gate_inputs(output=None, empty_allowed=True)), Accepted)


def coverage_case(clearance: ReviewClearance = ReviewClearance.SELF) -> tuple[Any, ...]:
    inputs = gate_inputs()
    inputs = replace(inputs, task=replace(inputs.task, kind=TaskKind.PLAN_ACCEPTANCE, spec_entity_id=None))
    owner = inputs.members[0]
    assert owner.accepted_attempt_id is not None
    spec = {
        "requirements": [{"key": "R1"}],
        "items": [{"key": "P1.1", "implements": ["R1"]}],
        "criteria": [{"id": str(uid(70)), "key": "C1", "owner": "P1.1", "checks": ["P1.1:V1"]}],
    }
    decision = AcceptanceDecision(
        uid(90),
        WS,
        RUN,
        owner.id,
        owner.accepted_attempt_id,
        owner.accepted_output_id,
        "accepted",
        uid(900),
        AcceptanceBasis.empty(clearance),
        NOW,
    )
    return inputs, spec, owner, decision


def test_pa1_pa2_block_missing_verification_and_advisory_preserves_gaps() -> None:
    inputs, spec, owner, decision = coverage_case()
    spec["requirements"].append({"key": "R2"})
    result, report = decide_plan_acceptance(inputs, spec, (inputs.task, owner), (decision,), "required")
    assert set(codes(result)) == {"CRITERION_UNVERIFIED", "REQUIREMENT_UNCOVERED"}
    assert report.counts == {"requirements": 2, "covered": 1, "criteria": 1, "verified": 0}
    result, advisory = decide_plan_acceptance(inputs, spec, (inputs.task, owner), (decision,), "advisory")
    assert isinstance(result, Accepted)
    assert advisory.diagnostics == ("COVERAGE_GAP",)
    assert result.basis.coverage_report == advisory.to_json()
    denied, _ = decide_plan_acceptance(
        replace(inputs, policy_live_ok=False), spec, (owner,), (decision,), "advisory"
    )
    assert "POLICY_DENIES" in codes(denied)


@pytest.mark.parametrize("evidence", ["check", "review", "deviation"])
def test_pa1_exact_accepted_output_evidence(evidence: str) -> None:
    inputs, spec, owner, decision = coverage_case()
    checks, deviations = (), ()
    if evidence == "check":
        check = make_check(
            task_id=owner.id, attempt_id=owner.accepted_attempt_id, output_id=owner.accepted_output_id
        )
        checks = (check,)
        decision = replace(decision, basis=replace(decision.basis, check_execution_ids=(check.id,)))
    elif evidence == "review":
        decision = replace(decision, basis=replace(decision.basis, clearance=ReviewClearance.GREEN))
    else:
        deviations = (
            DeviationAcceptance(
                uid(888), RUN, owner.id, uid(70), None, "approved", uid(900), NOW, "coverage"
            ),
        )
    result, report = decide_plan_acceptance(
        inputs, spec, (owner,), (decision,), "required", checks=checks, deviations=deviations
    )
    assert isinstance(result, Accepted)
    assert report.criteria[0].evidence == evidence
    missing = replace(owner, status=TaskStatus.READY, accepted_attempt_id=None, accepted_output_id=None)
    result, _ = decide_plan_acceptance(
        inputs, spec, (missing,), (decision,), "required", checks=checks, deviations=deviations
    )
    assert {"MEMBER_NOT_DONE", "CRITERION_UNVERIFIED", "REQUIREMENT_UNCOVERED"} <= set(codes(result))
    if checks:
        stale = replace(checks[0], output_id=uid(999))
        result, _ = decide_plan_acceptance(inputs, spec, (owner,), (decision,), "required", checks=(stale,))
        assert "CRITERION_UNVERIFIED" in codes(result)


def integration_effect(
    member: Any, output: Any, *, before: str = "a" * 40, after: str = "b" * 40, n: int = 1
) -> ExternalEffect:
    identity = uid(9000 + n)
    request = {
        "repository_id": str(output.manifest.mounts[0].repository_id),
        "target_branch": "integration",
        "before_sha": before,
        "after_sha": after,
        "tree_sha": output.manifest.mounts[0].tree_sha,
        "baseline_sha": "a" * 40,
        "output_ids": [str(output.id)],
        "output_digests": [output.manifest_digest],
        "commit_shas": [] if before == after else [after],
        "assignment_fencing_token": 1,
        "slot_fencing_token": n,
        "writer_epoch_sha": "d" * 40,
    }
    digest = canonical_digest({"effect_id": str(identity), "kind": "git_commit", "request": request})
    receipt = {
        k: request[k]
        for k in (
            "before_sha",
            "after_sha",
            "tree_sha",
            "target_branch",
            "output_ids",
            "commit_shas",
            "writer_epoch_sha",
        )
    }
    receipt.update(
        ref=after, request_digest=digest, receipt_ref=f"refs/skm/receipts/{n}", receipt_commit_sha="e" * 40
    )
    return ExternalEffect(
        identity,
        member.workspace_id,
        member.run_id,
        member.accepted_attempt_id,
        member.id,
        EffectKind.GIT_COMMIT,
        None,
        digest,
        cast("Any", request),
        EffectState.SUCCEEDED,
        cast("Any", receipt),
        NOW,
        NOW + timedelta(seconds=n),
    )


def range_case() -> tuple[Any, ...]:
    member = gate_inputs().members[0]
    output = replace(
        make_output(output_id=member.accepted_output_id),
        task_id=member.id,
        attempt_id=member.accepted_attempt_id,
    )
    return member, output, integration_effect(member, output)


def test_range_uses_receipts_and_noop_is_base_equals_head() -> None:
    member, output, effect = range_case()
    (bound,) = range_bounds((member,), (output,), (effect,))
    assert (bound.base, bound.head) == ("a" * 40, "b" * 40)
    assert bound.to_json()["effects"]
    noop = integration_effect(member, output, after="a" * 40)
    (bound,) = range_bounds((member,), (output,), (noop,))
    assert bound.base == bound.head == "a" * 40


@pytest.mark.parametrize("defect", ["missing", "unknown", "receipt", "digest", "output", "head"])
def test_range_never_guesses_missing_or_inconsistent_receipt(defect: str) -> None:
    member, output, effect = range_case()
    effects = (effect,)
    heads = None
    if defect == "missing":
        effects = ()
    elif defect == "unknown":
        effects = (replace(effect, state=EffectState.OUTCOME_UNKNOWN),)
    elif defect == "receipt":
        effects = (replace(effect, receipt=None),)
    elif defect == "digest":
        effects = (replace(effect, request_digest="sha256:" + "f" * 64),)
    elif defect == "output":
        output = replace(output, id=uid(999))
    else:
        heads = {str(output.manifest.mounts[0].repository_id): "f" * 40}
    with pytest.raises(SkmError) as exc:
        range_bounds((member,), (output,), effects, heads=heads)
    assert exc.value.code.value == "CHECKOUT_MISMATCH"


def test_range_chain_covers_intervening_receipts_and_rejects_gaps() -> None:
    member, output, first = range_case()
    second_member = replace(member, id=uid(102), accepted_attempt_id=uid(202), accepted_output_id=uid(302))
    second_output = replace(output, id=uid(302), task_id=uid(102), attempt_id=uid(202))
    second = integration_effect(second_member, second_output, before="b" * 40, after="f" * 40, n=2)
    (bound,) = range_bounds((member,), (output,), (second, first))
    assert bound.head == "f" * 40
    (bound,) = range_bounds((member,), (output,), (second, first), heads={bound.repository_id: "b" * 40})
    assert bound.head == "b" * 40
    gap = integration_effect(second_member, second_output, before="e" * 40, after="f" * 40, n=2)
    with pytest.raises(SkmError):
        range_bounds((member,), (output,), (first, gap))


@pytest.mark.parametrize(
    ("stage", "outcome", "row", "action_type"),
    [
        ("gate_prepare", K.SUCCESS, "A6", RunStage),
        ("gate_checks", K.CHECKS_FAILED, "D6g", CreateFollowups),
        ("review", K.VERDICT_GREEN, "F1", RunStage),
        ("phase_gate", K.ACCEPTED, "K11", Done),
        ("plan_acceptance", K.ACCEPTED, "K12", Done),
    ],
)
def test_engine_gate_transition_rows(stage: str, outcome: Any, row: str, action_type: Any) -> None:
    kind = TaskKind.PLAN_ACCEPTANCE if stage == "plan_acceptance" else TaskKind.PHASE_GATE
    stage_type = {
        "gate_prepare": "prepare_environment",
        "gate_checks": "run_checks",
        "review": "agent_review",
        "phase_gate": "phase_gate",
        "plan_acceptance": "plan_acceptance",
    }[stage]
    state = make_state(
        e(stage, outcome, stage_type=stage_type),
        kind=kind,
        checks=(make_check(state=CheckState.FAILED),) if outcome is K.CHECKS_FAILED else (),
    )
    decision = decide_advance(state, REVIEWED, state.effective_policy, NOW)
    assert decision.cause["advance_rule"] == row
    assert isinstance(decision.action, action_type)


def test_engine_e2_h1g_h6_and_k1_k2() -> None:
    manual = make_check(kind=CheckKind.MANUAL, state=CheckState.FAILED)
    state = make_state(
        e("gate_checks", K.MANUAL_PENDING),
        kind=TaskKind.PHASE_GATE,
        checks=(manual,),
        manual={manual.id: verdict("fail", check_id=manual.id)},
    )
    decision = decide_advance(state, REVIEWED, state.effective_policy, NOW)
    assert decision.cause["advance_rule"] == "E2"
    assert isinstance(decision.action, CreateFollowups)
    for findings, row in (((), "H6"), ((make_finding(1, Severity.MAJOR, FindingState.CONFIRMED),), "H1g")):
        state = triaged(*findings, kind=TaskKind.PHASE_GATE)
        decision = decide_advance(state, REVIEWED, state.effective_policy, NOW)
        assert decision.cause["advance_rule"] == row
    for code, row, action in (("MANUAL_PENDING", "K1", WaitFor), ("POLICY_DENIES", "K2", Escalate)):
        state = make_state(
            e("phase_gate", K.NOT_ACCEPTABLE, stage_type="phase_gate", out={"reasons": [{"code": code}]}),
            kind=TaskKind.PHASE_GATE,
            checks=(make_check(kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING),),
        )
        decision = decide_advance(state, REVIEWED, state.effective_policy, NOW)
        assert decision.cause["advance_rule"] == row
        assert isinstance(decision.action, action)


def test_r13_required_gates_cannot_be_silently_empty() -> None:
    inputs = gate_inputs()
    assert not gate_workflow_violations(QUICK, inputs.task, required_checks=False)
    for task, required in (
        (inputs.task, True),
        (replace(inputs.task, review_mode=ReviewMode.REQUIRED), False),
    ):
        defects = gate_workflow_violations(QUICK, task, required_checks=required)
        assert defects[0].reason == "GATE_UNSUPPORTED_BY_WORKFLOW"
    assert not gate_workflow_violations(REVIEWED, inputs.task, required_checks=True)
    state = make_state(e("prepare"), kind=TaskKind.PHASE_GATE, task={"review_mode": ReviewMode.WAIVED})
    decision = decide_advance(state, QUICK, state.effective_policy, NOW)
    assert isinstance(decision.action, Done)
    reasons = decision.cause["reason_codes"]
    assert isinstance(reasons, list)
    assert "GATE_EMPTY" in reasons


def test_host_object_proofs_check_candidate_tree_parents_and_ancestry() -> None:
    from skm.modules.execution.domain.gate_range import GitObject, verify_range_objects

    member, output, effect = range_case()
    bounds = range_bounds((member,), (output,), (effect,))
    objects = {"b" * 40: GitObject("c" * 40, ("a" * 40,))}
    verify_range_objects(bounds, objects)
    for invalid in (
        {},
        {"b" * 40: GitObject("d" * 40, ("a" * 40,))},
        {"b" * 40: GitObject("c" * 40, ("e" * 40,))},
    ):
        with pytest.raises(SkmError) as exc:
            verify_range_objects(bounds, invalid)
        assert exc.value.code.value == "CHECKOUT_MISMATCH"


def test_k12_coverage_followups_stop_at_round_limit() -> None:
    state = make_state(
        e(
            "plan_acceptance",
            K.NOT_ACCEPTABLE,
            stage_type="plan_acceptance",
            out={"reasons": [{"code": "CRITERION_UNVERIFIED"}]},
        ),
        kind=TaskKind.PLAN_ACCEPTANCE,
    )
    decision = decide_advance(state, REVIEWED, state.effective_policy, NOW)
    assert decision.cause["advance_rule"] == "K12"
    assert isinstance(decision.action, CreateFollowups)
    state = replace(state, task=replace(state.task, review_rounds=2))
    assert isinstance(decide_advance(state, REVIEWED, state.effective_policy, NOW).action, Escalate)


def test_compiler_gate_chain_has_no_orphan_or_cycle_and_failed_phase_holds_dependents() -> None:
    from skm.modules.execution.domain.task_graph import prerequisites, ready_task_ids
    from unit.execution.domain.test_task_compile import compile_

    compiled = compile_()
    tasks = list(compiled.tasks)
    kinds_seen = set()
    phase = next(t for t in tasks if t.kind is TaskKind.PHASE_GATE)
    held = {t.id for t in tasks if phase.id in prerequisites(t.id, compiled.edges)}
    assert held
    for _ in range(len(tasks)):
        ready = ready_task_ids(tasks, compiled.edges)
        if not ready:
            break
        selected = next(t for t in tasks if t.id == ready[0])
        if phase.status is not TaskStatus.ACCEPTED:
            assert not (held & set(ready))
        if selected.kind in GATE_KINDS:
            assert selected.declared_write_scope == ()
            kinds_seen.add(selected.kind)
        accepted = replace(selected, status=TaskStatus.ACCEPTED, blocking_reason=None)
        tasks = [accepted if t.id == selected.id else t for t in tasks]
        if selected.id == phase.id:
            phase = accepted
    assert all(t.status is TaskStatus.ACCEPTED for t in tasks)
    assert kinds_seen == {TaskKind.ITEM_GATE, TaskKind.PHASE_GATE, TaskKind.PLAN_ACCEPTANCE}


def test_r13_engine_refuses_required_gate_without_runners() -> None:
    state = make_state(e("prepare"), kind=TaskKind.PHASE_GATE)
    decision = decide_advance(state, QUICK, state.effective_policy, NOW)
    assert isinstance(decision.action, Escalate)
    reasons = decision.cause["reason_codes"]
    assert isinstance(reasons, list)
    assert "GATE_UNSUPPORTED_BY_WORKFLOW" in reasons
    state = replace(
        state, task=replace(state.task, review_mode=ReviewMode.WAIVED), gate={"required_checks": ["required"]}
    )
    assert isinstance(decide_advance(state, QUICK, state.effective_policy, NOW).action, Escalate)


def test_decide_gate_owner_signature() -> None:
    inputs = gate_inputs()
    assert isinstance(
        decide_gate(inputs.task, inputs.members, inputs.output, (), {}, (), (), (), True), Accepted
    )


@pytest.mark.parametrize("head", [None, "a" * 40, "b" * 40])
def test_noop_members_stay_empty_at_pinned_head_after_unrelated_integration(head: str | None) -> None:
    member, output, _ = range_case()
    noop = integration_effect(member, output, after="a" * 40)
    other = replace(member, id=uid(102), accepted_attempt_id=uid(202), accepted_output_id=uid(302))
    other_output = replace(output, id=uid(302), task_id=other.id, attempt_id=other.accepted_attempt_id)
    foreign = integration_effect(other, other_output, before="a" * 40, after="b" * 40, n=2)
    repo = str(output.manifest.mounts[0].repository_id)
    heads = None if head is None else {repo: head}
    (bound,) = range_bounds((member,), (output,), (foreign, noop), heads=heads)
    pinned = head or "b" * 40
    assert bound.base == bound.head == pinned
    assert noop in bound.effects
    assert (foreign in bound.effects) is (pinned == "b" * 40)
    if pinned == "b" * 40:
        (mixed,) = range_bounds((member, other), (output, other_output), (noop, foreign), heads=heads)
        assert (mixed.base, mixed.head) == ("a" * 40, "b" * 40)


def test_range_for_carried_member_requires_its_exact_source_receipt() -> None:
    source, output, effect = range_case()
    target = replace(source, id=uid(991), run_id=uid(992), accepted_attempt_id=None, accepted_output_id=None)
    with pytest.raises(SkmError, match="no accepted output proof"):
        range_bounds((target,), (output,), (effect,))
    (bound,) = range_bounds((target,), (output,), (effect,), carried_sources={target.id: source})
    assert bound.effects == (effect,)
    assert bound.head == "b" * 40
    with pytest.raises(SkmError, match="no unique immutable integration receipt"):
        range_bounds((target,), (output,), (), carried_sources={target.id: source})
