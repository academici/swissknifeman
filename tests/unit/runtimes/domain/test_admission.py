"""Admission of an operation before a runtime is chosen (runtimes §4.11, §4.10).

The admission side of routing is checked through the real ``route`` over a real catalog, real effective
capabilities and installations (explicit-route undershoot, required resume, fallback re-admission), and
through ``route_role`` whose catalog/capability loaders are the only replaced pieces.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, SkmError
from skm.kernel.ids import HostId
from skm.kernel.json_types import JsonValue
from skm.modules.runtimes import public
from skm.modules.runtimes.domain import admission as admission_module
from skm.modules.runtimes.domain.admission import (
    ADMISSION_DEFAULTS,
    OPERATION_ROLES,
    Admission,
    AdmissionFacts,
    AdmissionPolicy,
    FixBriefFacts,
    Operation,
    OperationContext,
    PreviousRoute,
    ResumeAllowance,
    ResumePolicy,
    admission_allows_resume,
    admit,
    classify_operation,
    fix_within_bounds,
    operations_of_role,
    session_policy_for,
)
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoad,
    SelfLoadKind,
    StaticCapabilityCatalog,
    explain_self_loads,
)
from skm.modules.runtimes.domain.catalog import ModelCatalog, ModelEntry, ModelStatus, RuntimeCatalogEntry
from skm.modules.runtimes.domain.classes import MODEL_CLASS_ORDER, Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.routing import (
    HostRouting,
    RouteConfig,
    RouteDecision,
    RouteKey,
    RouteRejection,
    RouteRequest,
    route,
    route_needs,
    route_refusal,
)
from skm.modules.runtimes.ports import CapabilityCatalog, HostRuntimeRepository

ROOT = Path(__file__).resolve().parents[4]
ECO, IMP, TOP = ModelClass.ECONOMY, ModelClass.IMPLEMENTATION, ModelClass.FRONTIER
DIGEST = "sha256:" + "a" * 64
OLD_DIGEST = "sha256:" + "b" * 64
SESSION = "019a3c55-6d2e-7f00-9c11-2b3c4d5e6f70"
STEP = "0193a7c1-9e00-7c00-8000-2d3e4f5a6b7c"
OUTPUT = "0193a7c2-0000-7000-8000-000000000001"

CODEX = PreviousRoute(
    runtime_id="codex",
    model="gpt-6-sol",
    model_class=IMP,
    effort=Effort.HIGH,
    session_ref=SESSION,
    step_ref=STEP,
)
BRIEF = FixBriefFacts(items=2, unconfirmed=0, finding_paths=("src/app.py", "src/util.py"))


def facts(operation: Operation, role: RoleId = RoleId.EXECUTOR, **changes: object) -> AdmissionFacts:
    """Facts that satisfy every condition of the operation's table row."""
    base = AdmissionFacts(
        operation=operation,
        role=role,
        task_min_class=None,
        task_min_effort=None,
        started_by=CODEX,
        previous=CODEX,
        contract_digest=DIGEST,
        previous_contract_digest=DIGEST,
        fix_brief=BRIEF,
        previous_output_id=OUTPUT,
    )
    return dataclasses.replace(base, **changes)


def policy(**changes: object) -> AdmissionPolicy:
    return dataclasses.replace(ADMISSION_DEFAULTS, **changes)


def caps(
    runtime_id: str = "codex", resume: CapabilityStatus | None = CapabilityStatus.NATIVE
) -> RuntimeCapabilities:
    records = {}
    if resume is not None:
        records[Capability.SESSION_RESUME] = CapabilityRecord(
            capability=Capability.SESSION_RESUME,
            status=resume,
            evidence="fixture:codex/resume.jsonl",
            tested_runtime_version="1.0.0",
            limitations="",
            last_verified_at=date(2026, 10, 1),
        )
    return RuntimeCapabilities(
        runtime_id=runtime_id,
        adapter_version="1.0.0",
        records=records,
        self_loads=(),
        read_only_network=True,
        config_isolation=None,
    )


# --- classify_operation


@pytest.mark.parametrize(
    ("role", "stage_final", "expected"),
    [
        (RoleId.REVIEWER, False, Operation.REVIEW),
        (RoleId.REVIEWER, True, Operation.FINAL_CLOSE),
        (RoleId.TRIAGER, False, Operation.REVIEW),
        (RoleId.TRIAGER, True, Operation.REVIEW),
        (RoleId.RESEARCHER, False, Operation.RESEARCH),
        (RoleId.SCOUT, True, Operation.RESEARCH),
        (RoleId.ADVISOR, False, Operation.ADVICE),
        (RoleId.REGISTRAR, False, Operation.AUXILIARY),
    ],
)
def test_classify_non_executor_roles_ignore_executor_facts(
    role: RoleId, stage_final: bool, expected: Operation
) -> None:
    for flags in [(False, False, False), (True, True, True)]:
        ctx = OperationContext(role, stage_final, *flags)
        assert classify_operation(ctx) is expected


@pytest.mark.parametrize(
    ("has_fix_brief", "wip_present", "contract_changed", "expected"),
    [
        (False, False, False, Operation.NEW_IMPLEMENTATION),
        (False, True, False, Operation.CONTINUATION),
        (True, True, False, Operation.BOUNDED_FIX),  # a fix brief wins over WIP
        (True, True, True, Operation.SCOPE_CHANGE),  # a changed contract wins over everything
        (False, False, True, Operation.SCOPE_CHANGE),
        (True, False, False, Operation.BOUNDED_FIX),
    ],
)
def test_classify_executor_in_rule_order(
    has_fix_brief: bool, wip_present: bool, contract_changed: bool, expected: Operation
) -> None:
    ctx = OperationContext(RoleId.EXECUTOR, True, has_fix_brief, wip_present, contract_changed)
    assert classify_operation(ctx) is expected


def test_operations_of_role_is_the_roles_column_of_the_table() -> None:
    for role in RoleId:
        assert operations_of_role(role) == {op for op, roles in OPERATION_ROLES.items() if role in roles}
    assert set(OPERATION_ROLES) == set(Operation)


# --- admit: every row of the table

# (operation, role, min_class with task class frontier, task class applies, default resume)
TABLE = [
    (Operation.NEW_IMPLEMENTATION, RoleId.EXECUTOR, TOP, True, ResumePolicy.NEVER),
    (Operation.CONTINUATION, RoleId.EXECUTOR, TOP, True, ResumePolicy.PREFERRED),
    (Operation.BOUNDED_FIX, RoleId.EXECUTOR, TOP, True, ResumePolicy.PREFERRED),
    (Operation.SCOPE_CHANGE, RoleId.EXECUTOR, TOP, True, ResumePolicy.NEVER),
    (Operation.REVIEW, RoleId.REVIEWER, IMP, False, ResumePolicy.NEVER),
    (Operation.REVIEW, RoleId.TRIAGER, IMP, False, ResumePolicy.NEVER),
    (Operation.FINAL_CLOSE, RoleId.REVIEWER, TOP, True, ResumePolicy.NEVER),
    (Operation.RESEARCH, RoleId.RESEARCHER, ECO, False, ResumePolicy.NEVER),
    (Operation.RESEARCH, RoleId.SCOUT, ECO, False, ResumePolicy.NEVER),
    (Operation.ADVICE, RoleId.ADVISOR, IMP, False, ResumePolicy.NEVER),
    (Operation.AUXILIARY, RoleId.REGISTRAR, ECO, False, ResumePolicy.NEVER),
]


@pytest.mark.parametrize(("op", "role", "min_class", "task_applies", "resume"), TABLE)
def test_each_table_row_with_its_conditions_met(
    op: Operation, role: RoleId, min_class: ModelClass, task_applies: bool, resume: ResumePolicy
) -> None:
    got = admit(facts(op, role, task_min_class=TOP, task_min_effort=Effort.XHIGH), ADMISSION_DEFAULTS)
    assert (got.requested, got.operation, got.notes) == (op, op, ())
    assert got.min_class is min_class
    assert ("task" in got.class_sources) is task_applies
    assert got.min_effort is (Effort.XHIGH if task_applies else None)
    assert got.resume is resume
    assert got.prefer_route == (CODEX if resume is not ResumePolicy.NEVER else None)
    assert got.required_capabilities == frozenset()


@pytest.mark.parametrize(("op", "role", "min_class", "task_applies", "resume"), TABLE)
def test_each_table_row_default_floor_without_task_class(
    op: Operation, role: RoleId, min_class: ModelClass, task_applies: bool, resume: ResumePolicy
) -> None:
    got = admit(facts(op, role, started_by=dataclasses.replace(CODEX, model_class=ECO)), ADMISSION_DEFAULTS)
    assert got.min_class is ADMISSION_DEFAULTS.min_class[op]
    assert got.class_sources[0] == "op_default"


@pytest.mark.parametrize("op", [Operation.REVIEW, Operation.FINAL_CLOSE])
def test_review_and_final_close_without_output_are_refused(op: Operation) -> None:
    with pytest.raises(PreconditionFailed) as caught:
        admit(facts(op, RoleId.REVIEWER, previous_output_id=None), ADMISSION_DEFAULTS)
    assert caught.value.code is ErrorCode.ADMISSION_REFUSED
    assert caught.value.details["reason"] == "no_output"
    assert caught.value.details["operation"] == op.value


@pytest.mark.parametrize(
    ("op", "role"),
    [
        (Operation.RESEARCH, RoleId.EXECUTOR),  # an executor cannot buy the economy floor of research
        (Operation.AUXILIARY, RoleId.EXECUTOR),
        (Operation.REVIEW, RoleId.EXECUTOR),
        (Operation.NEW_IMPLEMENTATION, RoleId.REVIEWER),
        (Operation.FINAL_CLOSE, RoleId.TRIAGER),
        (Operation.ADVICE, RoleId.SCOUT),
    ],
)
def test_operation_of_another_role_is_refused(op: Operation, role: RoleId) -> None:
    with pytest.raises(PreconditionFailed) as caught:
        admit(facts(op, role), ADMISSION_DEFAULTS)
    assert caught.value.code is ErrorCode.ADMISSION_REFUSED
    assert caught.value.details["reason"] == "operation_not_for_role"


def test_routing_explain_example_admission() -> None:
    """``examples/runtimes/routing-explain.json``: continuation of codex/gpt-6-sol at implementation."""
    got = admit(
        facts(Operation.CONTINUATION, task_min_class=IMP, task_min_effort=Effort.HIGH), ADMISSION_DEFAULTS
    )
    assert got.class_sources == ("op_default", "task", "started_by")
    assert (got.min_class, got.min_effort, got.resume) == (IMP, Effort.HIGH, ResumePolicy.PREFERRED)
    assert got.prefer_route == CODEX
    assert (got.required_capabilities, got.notes) == (frozenset(), ())


# --- continuation is never cheaper (S-23)


def test_continuation_is_not_below_its_start() -> None:
    started = dataclasses.replace(CODEX, model_class=TOP)
    got = admit(facts(Operation.CONTINUATION, task_min_class=ECO, started_by=started), ADMISSION_DEFAULTS)
    assert got.min_class is TOP
    assert got.class_sources == ("started_by",)


def test_continuation_is_not_below_the_task_floor() -> None:
    started = dataclasses.replace(CODEX, model_class=ECO)
    got = admit(
        facts(Operation.CONTINUATION, task_min_class=TOP, task_min_effort=Effort.XHIGH, started_by=started),
        ADMISSION_DEFAULTS,
    )
    assert (got.min_class, got.min_effort, got.class_sources) == (TOP, Effort.XHIGH, ("task",))


def test_config_and_role_floors_raise_the_class() -> None:
    raised = policy(min_class={**ADMISSION_DEFAULTS.min_class, Operation.REVIEW: TOP})
    got = admit(facts(Operation.REVIEW, RoleId.TRIAGER), raised)
    assert (got.min_class, got.class_sources) == (TOP, ("config",))
    by_role = policy(role_min_class={RoleId.SCOUT: TOP})
    got = admit(facts(Operation.RESEARCH, RoleId.SCOUT), by_role)
    assert (got.min_class, got.class_sources) == (TOP, ("role_min",))
    both = policy(min_class={Operation.RESEARCH: TOP}, role_min_class={RoleId.SCOUT: TOP})
    assert admit(facts(Operation.RESEARCH, RoleId.SCOUT), both).class_sources == ("config", "role_min")


def test_policy_without_an_operation_uses_the_default_floor_and_resume() -> None:
    sparse = AdmissionPolicy(min_class={}, resume={}, bounded_fix_below_task_class=False, role_min_class={})
    got = admit(facts(Operation.CONTINUATION, started_by=dataclasses.replace(CODEX, model_class=ECO)), sparse)
    assert (got.min_class, got.resume) == (IMP, ResumePolicy.PREFERRED)


def test_policy_coerces_plain_strings_to_enums() -> None:
    loose = AdmissionPolicy(
        min_class={"review": "frontier"},  # type: ignore[dict-item] - config-shaped input
        resume={"continuation": "never"},  # type: ignore[dict-item]
        bounded_fix_below_task_class=False,
        role_min_class={"reviewer": "frontier"},  # type: ignore[dict-item]
    )
    assert loose.resume[Operation.CONTINUATION] is ResumePolicy.NEVER
    assert admit(facts(Operation.CONTINUATION), loose).prefer_route is None
    with pytest.raises(ValueError, match="sometimes"):
        AdmissionPolicy(
            min_class={},
            resume={"continuation": "sometimes"},  # pyright: ignore[reportArgumentType]
            bounded_fix_below_task_class=False,
            role_min_class={},
        )


# --- escalations


@pytest.mark.parametrize(
    ("op", "changes", "target", "code"),
    [
        (
            Operation.CONTINUATION,
            {"previous_contract_digest": OLD_DIGEST},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
        (Operation.CONTINUATION, {"started_by": None}, Operation.NEW_IMPLEMENTATION, "no_wip"),
        # WIP whose contract is unknown cannot prove the contract unchanged
        (
            Operation.CONTINUATION,
            {"previous_contract_digest": None},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
        (
            Operation.BOUNDED_FIX,
            {"previous_contract_digest": OLD_DIGEST},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
        (
            Operation.BOUNDED_FIX,
            {"fix_brief": dataclasses.replace(BRIEF, unconfirmed=1)},
            Operation.NEW_IMPLEMENTATION,
            "findings_unconfirmed",
        ),
        (Operation.BOUNDED_FIX, {"fix_brief": None}, Operation.NEW_IMPLEMENTATION, "no_fix_brief"),
        (
            Operation.BOUNDED_FIX,
            {"fix_brief": FixBriefFacts(items=0, unconfirmed=0, finding_paths=())},
            Operation.NEW_IMPLEMENTATION,
            "no_fix_brief",
        ),
        (
            Operation.BOUNDED_FIX,
            {"previous_output_id": None},
            Operation.NEW_IMPLEMENTATION,
            "no_previous_output",
        ),
        (
            Operation.BOUNDED_FIX,
            {"previous_contract_digest": None},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
        # a changed contract wins over the other unmet conditions of the row
        (
            Operation.BOUNDED_FIX,
            {"previous_contract_digest": OLD_DIGEST, "fix_brief": dataclasses.replace(BRIEF, unconfirmed=3)},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
        (
            Operation.CONTINUATION,
            {"previous_contract_digest": OLD_DIGEST, "started_by": None},
            Operation.SCOPE_CHANGE,
            "contract_changed",
        ),
    ],
)
def test_unmet_condition_escalates_once(
    op: Operation, changes: Mapping[str, object], target: Operation, code: str
) -> None:
    got = admit(facts(op, task_min_class=TOP, task_min_effort=Effort.HIGH, **changes), ADMISSION_DEFAULTS)  # pyright: ignore[reportArgumentType]
    assert (got.requested, got.operation) == (op, target)
    assert [(note.code, note.detail) for note in got.notes] == [
        (f"escalated:{code}", f"{op.value}→{target.value}")
    ]
    # the escalated rows apply the task class and never resume: the old session saw old work or contract
    assert (got.min_class, got.min_effort, got.resume, got.prefer_route) == (
        TOP,
        Effort.HIGH,
        ResumePolicy.NEVER,
        None,
    )
    assert "started_by" not in got.class_sources


def test_unconfirmed_bounded_fix_cannot_keep_its_cheaper_floor() -> None:
    cheap = policy(bounded_fix_below_task_class=True)
    unconfirmed = facts(
        Operation.BOUNDED_FIX, task_min_class=TOP, fix_brief=dataclasses.replace(BRIEF, unconfirmed=1)
    )
    got = admit(unconfirmed, cheap)
    assert (got.operation, got.min_class) == (Operation.NEW_IMPLEMENTATION, TOP)


def test_bounded_fix_below_task_class_only_when_allowed() -> None:
    task = facts(Operation.BOUNDED_FIX, task_min_class=TOP, task_min_effort=Effort.XHIGH)
    strict = admit(task, ADMISSION_DEFAULTS)
    assert (strict.min_class, strict.min_effort) == (TOP, Effort.XHIGH)
    cheap = admit(task, policy(bounded_fix_below_task_class=True))
    assert (cheap.min_class, cheap.min_effort, cheap.class_sources) == (IMP, None, ("op_default",))


# --- resume policy and the admission_allows_resume filter


def test_resume_required_requires_session_resume() -> None:
    required = policy(resume={**ADMISSION_DEFAULTS.resume, Operation.CONTINUATION: ResumePolicy.REQUIRED})
    got = admit(facts(Operation.CONTINUATION), required)
    assert got.resume is ResumePolicy.REQUIRED
    assert got.required_capabilities == {Capability.SESSION_RESUME}


def test_prefer_route_needs_a_previous_session() -> None:
    no_ref = dataclasses.replace(CODEX, session_ref=None)
    assert admit(facts(Operation.CONTINUATION, previous=no_ref), ADMISSION_DEFAULTS).prefer_route is None
    assert admit(facts(Operation.CONTINUATION, previous=None), ADMISSION_DEFAULTS).prefer_route is None


def admitted(resume: ResumePolicy, prefer: PreviousRoute | None = CODEX) -> Admission:
    got = admit(facts(Operation.CONTINUATION), policy(resume={Operation.CONTINUATION: resume}))
    return dataclasses.replace(got, prefer_route=prefer if resume is not ResumePolicy.NEVER else None)


def test_allowance_on_the_previous_route_with_resume() -> None:
    got = admission_allows_resume(admitted(ResumePolicy.PREFERRED), "codex", "gpt-6-sol", caps())
    assert got == ResumeAllowance(allowed=True, required=False, session_ref=SESSION, reason="allowed")
    adapted = caps(resume=CapabilityStatus.ADAPTED)
    assert admission_allows_resume(admitted(ResumePolicy.REQUIRED), "codex", "gpt-6-sol", adapted).allowed


@pytest.mark.parametrize(
    ("resume", "prefer", "runtime", "model", "status", "reason"),
    [
        (ResumePolicy.NEVER, CODEX, "codex", "gpt-6-sol", CapabilityStatus.NATIVE, "resume_disabled"),
        (ResumePolicy.PREFERRED, None, "codex", "gpt-6-sol", CapabilityStatus.NATIVE, "no_previous_session"),
        (ResumePolicy.PREFERRED, CODEX, "claude_code", "sonnet", CapabilityStatus.NATIVE, "route_changed"),
        (ResumePolicy.PREFERRED, CODEX, "codex", "gpt-6-mini", CapabilityStatus.NATIVE, "route_changed"),
        (
            ResumePolicy.PREFERRED,
            CODEX,
            "codex",
            "gpt-6-sol",
            CapabilityStatus.UNSUPPORTED,
            "resume_not_supported",
        ),
        # unverified resume does not pass, whatever degraded.allow says
        (
            ResumePolicy.PREFERRED,
            CODEX,
            "codex",
            "gpt-6-sol",
            CapabilityStatus.UNKNOWN,
            "resume_not_supported",
        ),
        (ResumePolicy.PREFERRED, CODEX, "codex", "gpt-6-sol", None, "resume_not_supported"),
        (
            ResumePolicy.REQUIRED,
            CODEX,
            "codex",
            "gpt-6-sol",
            CapabilityStatus.UNKNOWN,
            "resume_not_supported",
        ),
        (ResumePolicy.REQUIRED, None, "codex", "gpt-6-sol", CapabilityStatus.NATIVE, "no_previous_session"),
        (ResumePolicy.REQUIRED, CODEX, "claude_code", "sonnet", CapabilityStatus.NATIVE, "route_changed"),
    ],
)
def test_allowance_refusal_reasons(
    resume: ResumePolicy,
    prefer: PreviousRoute | None,
    runtime: str,
    model: str,
    status: CapabilityStatus | None,
    reason: str,
) -> None:
    got = admission_allows_resume(admitted(resume, prefer), runtime, model, caps(runtime, status))
    assert got == ResumeAllowance(
        allowed=False,
        required=resume is ResumePolicy.REQUIRED,
        session_ref=None,
        reason=reason,  # type: ignore[arg-type]
    )


def test_allowance_routing_explain_example_fallback_route() -> None:
    """The example's continuation fell back from codex to claude_code: resume is not allowed there."""
    got = admit(
        facts(Operation.CONTINUATION, task_min_class=IMP, task_min_effort=Effort.HIGH), ADMISSION_DEFAULTS
    )
    allowance = admission_allows_resume(got, "claude_code", "sonnet", caps("claude_code"))
    assert allowance == ResumeAllowance(
        allowed=False, required=False, session_ref=None, reason="route_changed"
    )


def test_allowance_rejects_foreign_capabilities_and_odd_resume_values() -> None:
    with pytest.raises(ValueError, match="capabilities of claude_code"):
        admission_allows_resume(admitted(ResumePolicy.PREFERRED), "codex", "gpt-6-sol", caps("claude_code"))
    odd = dataclasses.replace(admitted(ResumePolicy.PREFERRED), resume="never")
    assert admission_allows_resume(odd, "codex", "gpt-6-sol", caps()).reason == "resume_disabled"
    odd = dataclasses.replace(admitted(ResumePolicy.PREFERRED), resume="always")
    assert not admission_allows_resume(odd, "codex", "gpt-6-sol", caps()).allowed


def test_allowance_is_a_filter_not_a_session_decision() -> None:
    """RT-01: runtimes has no session decider; the allowance carries no session mode."""
    assert {field.name for field in dataclasses.fields(ResumeAllowance)} == {
        "allowed",
        "required",
        "session_ref",
        "reason",
    }
    assert not {"session", "session_mode", "session_plan"} & {
        f.name for f in dataclasses.fields(RouteDecision)
    }
    for name in ("plan_session", "SessionPlan", "decide_session", "Resume", "Fresh"):
        assert not hasattr(admission_module, name)
        assert not hasattr(public, name)
    # the same inputs give the same allowance: no hidden state, no previous-step outcome considered
    first = admission_allows_resume(admitted(ResumePolicy.PREFERRED), "codex", "gpt-6-sol", caps())
    assert admission_allows_resume(admitted(ResumePolicy.PREFERRED), "codex", "gpt-6-sol", caps()) == first


# --- session_policy_for


def test_session_policy_for_roles() -> None:
    assert session_policy_for(RoleId.EXECUTOR, ADMISSION_DEFAULTS, resume_mode="auto") == "persistent"
    for role in set(RoleId) - {RoleId.EXECUTOR}:
        assert session_policy_for(role, ADMISSION_DEFAULTS, resume_mode="auto") == "ephemeral", role
    for role in RoleId:
        assert session_policy_for(role, ADMISSION_DEFAULTS, resume_mode="never") == "ephemeral"


def test_session_policy_follows_the_resume_policy_of_the_roles_operations() -> None:
    never = policy(resume=dict.fromkeys(Operation, ResumePolicy.NEVER))
    assert session_policy_for(RoleId.EXECUTOR, never, resume_mode="auto") == "ephemeral"
    only_fix = policy(resume={Operation.CONTINUATION: "never", Operation.BOUNDED_FIX: "required"})
    assert session_policy_for(RoleId.EXECUTOR, only_fix, resume_mode="auto") == "persistent"
    reviewer = policy(resume={Operation.FINAL_CLOSE: ResumePolicy.PREFERRED})
    assert session_policy_for(RoleId.REVIEWER, reviewer, resume_mode="auto") == "persistent"
    assert session_policy_for(RoleId.TRIAGER, reviewer, resume_mode="auto") == "ephemeral"


# --- admission_policy (facade over runtimes.admission.*)


class Config:
    """The part of ``EffectiveConfig`` the facade reads."""

    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self.values = dict(values)

    def get(self, key: str) -> JsonValue | None:
        return self.values.get(key)


CATALOG_DEFAULTS: dict[str, JsonValue] = {
    **{
        f"runtimes.admission.{op.value}.min_class": ADMISSION_DEFAULTS.min_class[op].value for op in Operation
    },
    "runtimes.admission.continuation.resume": "preferred",
    "runtimes.admission.bounded_fix.resume": "preferred",
    "runtimes.admission.bounded_fix.below_task_class": False,
    "runtimes.role_min_class": {"reviewer": "implementation"},
    "runtimes.session.resume": "auto",
}


def admission_policy(**values: JsonValue) -> AdmissionPolicy:
    merged = {**CATALOG_DEFAULTS, **{key.replace("__", "."): value for key, value in values.items()}}
    return public.admission_policy(config=Config(merged))  # type: ignore[arg-type] - duck-typed config


def test_admission_policy_defaults() -> None:
    got = admission_policy()
    assert got.min_class == ADMISSION_DEFAULTS.min_class
    assert got.resume == ADMISSION_DEFAULTS.resume
    assert got.bounded_fix_below_task_class is False
    assert got.role_min_class == {RoleId.REVIEWER: IMP}
    assert public.admission_policy(config=Config({})) == dataclasses.replace(  # type: ignore[arg-type]
        ADMISSION_DEFAULTS, role_min_class={}
    )


def test_admission_policy_only_raises_floors() -> None:
    got = admission_policy(
        runtimes__admission__review__min_class="frontier", runtimes__admission__advice__min_class="economy"
    )
    assert got.min_class[Operation.REVIEW] is TOP
    assert got.min_class[Operation.ADVICE] is IMP  # below ADMISSION_DEFAULTS: the default floor stays


def test_admission_policy_resume_keys_and_session_never() -> None:
    got = admission_policy(runtimes__admission__continuation__resume="required")
    assert got.resume[Operation.CONTINUATION] is ResumePolicy.REQUIRED
    assert got.resume[Operation.BOUNDED_FIX] is ResumePolicy.PREFERRED
    never = admission_policy(
        runtimes__admission__continuation__resume="required", runtimes__session__resume="never"
    )
    assert set(never.resume.values()) == {ResumePolicy.NEVER}
    assert session_policy_for(RoleId.EXECUTOR, never, resume_mode="auto") == "ephemeral"


def test_admission_policy_bounded_fix_and_roles() -> None:
    got = admission_policy(
        runtimes__admission__bounded_fix__below_task_class=True,
        runtimes__role_min_class={"advisor": "frontier", "reviewer": "economy"},
    )
    assert got.bounded_fix_below_task_class is True
    assert got.role_min_class == {RoleId.ADVISOR: TOP, RoleId.REVIEWER: ECO}
    # a reviewer role floor below the operation floor never lowers the review floor
    assert admit(facts(Operation.REVIEW, RoleId.REVIEWER), got).min_class is IMP


# --- fix_within_bounds (port of grown_paths)

TEST_GLOBS = ("**/tests/**", "**/test_*.py")
EXTRA = ("CHANGELOG.md", "docs/**")


def bounds(changed: list[str], scope: tuple[str, ...] = ("src/", "tests/")) -> tuple[bool, tuple[str, ...]]:
    got = fix_within_bounds(changed, BRIEF.finding_paths, scope, EXTRA, TEST_GLOBS)
    return got.within, got.grown


def test_fix_inside_bounds() -> None:
    assert bounds([]) == (True, ())
    assert bounds(["src/app.py", "./src/util.py"]) == (True, ())
    assert bounds(["tests/unit/test_app.py", "src/pkg/tests/data.json", "src/test_helpers.py"]) == (True, ())
    assert bounds(["CHANGELOG.md", "docs/guide/admission.md"]) == (True, ())


def test_fix_grown_paths_are_sorted_and_unique() -> None:
    assert bounds(["src/other.py", "README.md", "src/app.py", "README.md"]) == (
        False,
        ("README.md", "src/other.py"),
    )


def test_fix_test_paths_must_be_inside_the_write_scope() -> None:
    assert bounds(["lib/tests/test_x.py"]) == (False, ("lib/tests/test_x.py",))
    assert bounds(["tests/test_x.py"], scope=("src/",)) == (False, ("tests/test_x.py",))
    # a single * stays in one directory; a plain entry names itself and everything under it
    assert bounds(["src/a/test_x.py"], scope=("src/*",)) == (False, ("src/a/test_x.py",))
    assert bounds(["src/a/test_x.py"], scope=("src/**",)) == (True, ())
    assert bounds(["src/a/test_x.py"], scope=("src",)) == (True, ())
    assert bounds(["srcx/test_x.py"], scope=("src",)) == (False, ("srcx/test_x.py",))


def test_fix_test_globs_semantics() -> None:
    assert bounds(["test_root.py"], scope=("**",)) == (True, ())
    assert bounds(["src/test_x.pyc", "src/tests_data/x.py"]) == (
        False,
        ("src/test_x.pyc", "src/tests_data/x.py"),
    )
    assert bounds(["docs"]) == (True, ())  # docs/** names the directory and its content
    assert bounds(["docsx/a.md", "pkg/docs/a.md"]) == (False, ("docsx/a.md", "pkg/docs/a.md"))


@pytest.mark.parametrize(
    ("extra", "child"),
    [
        ("CHANGELOG.md", "CHANGELOG.md/payload.py"),
        ("notes/release.txt", "notes/release.txt/payload.py"),
        ("docs", "docs/payload.py"),
        ("docs/", "docs/payload.py"),
    ],
)
def test_fix_plain_allowed_extra_names_only_itself(extra: str, child: str) -> None:
    """A plain allowed extra path is compared exactly (``grown_paths``); a child under it grew the fix."""
    allowed = (extra, "docs/**") if not extra.startswith("docs") else (extra,)
    itself = extra.rstrip("/")
    got = public.fix_within_bounds([itself, child], [], ["**"], allowed, TEST_GLOBS)
    assert got == public.FixBounds(within=False, grown=(child,))
    assert public.fix_within_bounds([itself], [], ["**"], allowed, TEST_GLOBS).within


def test_fix_glob_allowed_extra_reaches_below_and_write_scope_keeps_directories() -> None:
    got = public.fix_within_bounds(
        ["CHANGELOG.md", "docs/guide/a.md", "docs/payload.py"], [], ["src"], EXTRA, TEST_GLOBS
    )
    assert got == public.FixBounds(within=True, grown=())
    # the write scope still names a directory and everything under it
    assert public.fix_within_bounds(["src/a/test_x.py"], [], ["src"], EXTRA, TEST_GLOBS).within
    assert public.fix_within_bounds(["src/a/test_x.py"], [], ["src/"], EXTRA, TEST_GLOBS).within


@pytest.mark.parametrize(
    "path",
    [
        "../src/app.py",
        "src/../../etc/passwd",
        "/src/app.py",
        "~/src/app.py",
        "C:/src/app.py",
        "src\\app.py",
        "",
    ],
)
def test_fix_paths_outside_the_repository_are_never_within(path: str) -> None:
    assert bounds([path], scope=("**",)) == (False, (path,))
    assert not fix_within_bounds([path], [path], ["**"], ["**"], ["**"]).within


def settings_schema() -> dict[str, Any]:
    return json.loads((ROOT / "src/skm/schemas/settings/runtimes.v1.json").read_text())


def test_defaults_match_the_settings_catalog() -> None:
    """``ADMISSION_DEFAULTS`` and the legacy fix bounds are the catalog defaults of the settings."""
    schema = settings_schema()["properties"]
    section = schema["admission"]["properties"]
    for op in Operation:
        assert (
            section[op.value]["properties"]["min_class"]["default"] == ADMISSION_DEFAULTS.min_class[op].value
        )
        resume = section[op.value]["properties"].get("resume")
        if resume is not None:
            assert resume["default"] == ADMISSION_DEFAULTS.resume[op].value
    bounded = section["bounded_fix"]["properties"]
    assert bounded["below_task_class"]["default"] is ADMISSION_DEFAULTS.bounded_fix_below_task_class
    assert tuple(bounded["test_globs"]["default"]) == TEST_GLOBS
    assert tuple(bounded["allowed_extra_paths"]["default"]) == EXTRA
    for key, value in CATALOG_DEFAULTS.items():
        node = schema
        parts = key.removeprefix("runtimes.").split(".")
        for part in parts[:-1]:
            node = node[part]["properties"]
        assert node[parts[-1]]["default"] == value, key


# --- the admission side of route: requirements and refusal


def request(admission: Admission, **changes: object) -> RouteRequest:
    base = RouteRequest(
        role=RoleId.EXECUTOR,
        required_capabilities=frozenset({Capability.HEADLESS_EXECUTION}),
        optional_capabilities=frozenset({Capability.USAGE_REPORTING, Capability.SESSION_RESUME}),
        model_class=ECO,
        effort=Effort.LOW,
        explicit_runtime="codex",
        explicit_model="gpt-6-mini",
        host_id=None,
        admission=admission,
        config_mode="isolated",
        excluded_routes=frozenset(),
        network_read_only=False,
    )
    return dataclasses.replace(base, **changes)


def test_route_needs_raise_the_request_to_the_admission_floor() -> None:
    adm = admit(
        facts(Operation.BOUNDED_FIX, task_min_class=TOP, task_min_effort=Effort.HIGH),
        policy(resume={Operation.BOUNDED_FIX: ResumePolicy.REQUIRED}),
    )
    needs = route_needs(request(adm), config_isolation_required=True)
    assert (needs.model_class, needs.effort) == (TOP, Effort.HIGH)
    assert needs.required == {
        Capability.HEADLESS_EXECUTION,
        Capability.SESSION_RESUME,
        Capability.CONFIG_ISOLATION,
    }
    assert needs.optional == {Capability.USAGE_REPORTING}  # required wins over optional
    # the request can only be raised, never lowered by admission
    high = route_needs(request(adm, model_class=TOP, effort=Effort.XHIGH), config_isolation_required=True)
    assert (high.model_class, high.effort) == (TOP, Effort.XHIGH)


def test_route_needs_config_isolation_by_mode() -> None:
    adm = admit(facts(Operation.RESEARCH, RoleId.SCOUT), ADMISSION_DEFAULTS)
    wanted = route_needs(request(adm), config_isolation_required=False)
    assert Capability.CONFIG_ISOLATION in wanted.optional
    assert Capability.CONFIG_ISOLATION not in wanted.required
    inherit = route_needs(request(adm, config_mode="inherit"), config_isolation_required=True)
    assert Capability.CONFIG_ISOLATION not in inherit.required | inherit.optional
    assert (inherit.model_class, inherit.effort) == (ECO, Effort.LOW)  # min_effort None keeps the request


def rejection(reason: str, source: str = "plan_route", runtime: str = "codex") -> RouteRejection:
    return RouteRejection(runtime_id=runtime, model="gpt-6-mini", source=source, reason=reason, detail="d")


def test_bounded_fix_on_a_model_below_the_task_class_is_route_undershoot() -> None:
    adm = admit(facts(Operation.BOUNDED_FIX, task_min_class=TOP), ADMISSION_DEFAULTS)
    assert route_needs(request(adm), config_isolation_required=True).model_class is TOP
    error = route_refusal(request(adm), [rejection("class_too_low")])
    assert isinstance(error, CapabilityUnavailable)
    assert error.code is ErrorCode.ROUTE_UNDERSHOOT
    assert error.details["operation"] == "bounded_fix"
    assert error.details["rejected"] == [
        {
            "runtime_id": "codex",
            "model": "gpt-6-mini",
            "source": "plan_route",
            "reason": "class_too_low",
            "detail": "d",
        }
    ]


def test_route_refusal_codes() -> None:
    preferred = admit(facts(Operation.CONTINUATION), ADMISSION_DEFAULTS)
    required = admit(facts(Operation.CONTINUATION), policy(resume={Operation.CONTINUATION: "required"}))
    undershoot = [rejection("class_too_low"), rejection("effort_too_low", "role_routing", "claude_code")]
    assert route_refusal(request(preferred), undershoot).code is ErrorCode.ROUTE_UNDERSHOOT
    assert route_refusal(request(required), [rejection("class_too_low", "previous_route")]).code is (
        ErrorCode.ROUTE_UNDERSHOOT
    )
    mixed = [rejection("class_too_low"), rejection("not_installed", "preference")]
    assert route_refusal(request(preferred), mixed).code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert route_refusal(request(preferred), []).code is ErrorCode.CAPABILITY_UNAVAILABLE
    for rejected in ([rejection("capability_missing:session_resume", "previous_route")], []):
        error = route_refusal(request(required), rejected)
        assert isinstance(error, PreconditionFailed)
        assert error.code is ErrorCode.ADMISSION_REFUSED
        assert error.details["reason"] == "resume_required_unavailable"


# --- route: the real candidates and filters under admission (§4.10 steps 2-5)

CATALOG_DIGEST = "sha256:" + "7" * 64
HOST = HostId(UUID("0193a6f0-0100-7a00-8000-9a8b7c6d5e4f"))
OTHER_HOST = HostId(UUID("0193a6f0-0100-7a00-8000-000000000002"))


def entry(
    model: str,
    runtime: str,
    *classes: ModelClass,
    status: ModelStatus = ModelStatus.CONFIRMED,
    window: int = 200_000,
) -> ModelEntry:
    return ModelEntry(
        id=model,
        runtime_id=runtime,
        display_name=model,
        classes=frozenset(classes),
        suited_roles=frozenset(),
        context_window_tokens=window,
        max_output_tokens=None,
        pricing=None,
        patterns=(),
        status=status,
        verified_at=date(2026, 10, 1),
        source="test",
        notes="",
    )


def runtime_catalog(
    runtime: str, selectors: Mapping[ModelClass, str], *models: ModelEntry
) -> RuntimeCatalogEntry:
    return RuntimeCatalogEntry(
        runtime_id=runtime,
        class_selectors={cls: (model,) for cls, model in selectors.items()},
        effort_selectors={effort: effort.value for effort in Effort},
        models=models,
    )


# grok and cursor have no models in the catalog (as in examples/runtimes/routing-explain.json)
CATALOG = ModelCatalog(
    catalog_version="1.0.0",
    resource_version_ids=(),
    digest=CATALOG_DIGEST,
    runtimes={
        "codex": runtime_catalog(
            "codex",
            {ECO: "gpt-6-mini", IMP: "gpt-6-sol", TOP: "gpt-6-astra"},
            entry("gpt-6-mini", "codex", ECO, window=128_000),
            entry("gpt-6-sol", "codex", IMP),
            entry("gpt-6-astra", "codex", IMP, TOP, window=400_000),
            entry("gpt-5-old", "codex", IMP, status=ModelStatus.DEPRECATED),
        ),
        "claude_code": runtime_catalog(
            "claude_code",
            {ECO: "haiku", IMP: "sonnet", TOP: "opus"},
            entry("haiku", "claude_code", ECO),
            entry("sonnet", "claude_code", IMP),
            entry("opus", "claude_code", TOP),
        ),
    },
)


def self_load(
    kind: SelfLoadKind, suppressed_by: Literal["config_isolation", "never"] = "config_isolation"
) -> SelfLoad:
    return SelfLoad(
        kind=kind, locator=kind.value, files=(), when="start", suppressed_by=suppressed_by, note=""
    )


CLAUDE_LOADS = (
    self_load(SelfLoadKind.USER_CONFIG),
    self_load(SelfLoadKind.PROJECT_INSTRUCTIONS),
    self_load(SelfLoadKind.PROJECT_SETTINGS),
)
CODEX_LOADS = (
    self_load(SelfLoadKind.USER_CONFIG),
    self_load(SelfLoadKind.PROJECT_INSTRUCTIONS, "never"),
    self_load(SelfLoadKind.PROJECT_SETTINGS),
)


def full_caps(
    runtime_id: str,
    statuses: Mapping[Capability, CapabilityStatus | None] | None = None,
    *,
    loads: tuple[SelfLoad, ...] = (),
    read_only_network: bool = True,
) -> RuntimeCapabilities:
    """Every capability native unless ``statuses`` says otherwise; ``None`` leaves the record out."""
    wanted: dict[Capability, CapabilityStatus | None] = dict.fromkeys(Capability, CapabilityStatus.NATIVE)
    wanted.update(statuses or {})
    records = {
        cap: CapabilityRecord(
            capability=cap,
            status=status,
            evidence=f"fixture:{runtime_id}/{cap.value}",
            tested_runtime_version="1.0.0",
            limitations="",
            last_verified_at=date(2026, 10, 1),
        )
        for cap, status in wanted.items()
        if status is not None
    }
    return RuntimeCapabilities(
        runtime_id=runtime_id,
        adapter_version="1.0.0",
        records=records,
        self_loads=loads,
        read_only_network=read_only_network,
        config_isolation=None,
    )


CAPS: dict[str, RuntimeCapabilities] = {
    "codex": full_caps("codex", loads=CODEX_LOADS),
    "claude_code": full_caps("claude_code", loads=CLAUDE_LOADS),
    "grok": full_caps("grok", {Capability.CONFIG_ISOLATION: CapabilityStatus.UNSUPPORTED}),
    "cursor": full_caps("cursor"),
}
CFG = RouteConfig(
    allowed=frozenset({"claude_code", "codex", "grok", "cursor"}),
    preference=("claude_code", "codex"),
    role_routing={},
    degraded_allow=frozenset(),
)
FALLBACK: dict[str, JsonValue] = {
    "runtime": "codex",
    "model_class": "implementation",
    "fallback": [{"runtime": "grok"}, {"runtime": "claude_code"}],
}


def routed(
    req: RouteRequest,
    cfg: RouteConfig = CFG,
    caps_by_runtime: Mapping[str, RuntimeCapabilities] = CAPS,
    installs: Mapping[str, RuntimeInstallation] | None = None,
    registered: frozenset[str] | None = None,
) -> RouteDecision:
    known = frozenset(CAPS) if registered is None else registered
    return route(req, cfg, CATALOG, caps_by_runtime, installs or {}, known)


def refused(req: RouteRequest, cfg: RouteConfig = CFG, **inputs: Any) -> SkmError:
    with pytest.raises(SkmError) as caught:
        routed(req, cfg, **inputs)
    return caught.value


def listed(error: SkmError) -> list[tuple[str, str | None, str, str]]:
    rejected: list[dict[str, Any]] = error.details["rejected"]  # type: ignore[assignment]
    return [(item["runtime_id"], item["model"], item["source"], item["reason"]) for item in rejected]


def trail(decision: RouteDecision) -> list[tuple[str, str | None, str, str]]:
    return [(item.runtime_id, item.model, item.source, item.reason) for item in decision.rejected]


def unrouted(admission: Admission, **changes: object) -> RouteRequest:
    """A request without a plan route: role routing, fallback and preference decide."""
    return request(admission, explicit_runtime=None, explicit_model=None, **changes)


def test_explicit_plan_route_below_the_task_class_is_undershoot() -> None:
    adm = admit(facts(Operation.BOUNDED_FIX, task_min_class=TOP), ADMISSION_DEFAULTS)
    cfg = dataclasses.replace(
        CFG, role_routing={RoleId.EXECUTOR: {"runtime": "claude_code", "model": "opus"}}
    )
    error = refused(request(adm), cfg)
    assert isinstance(error, CapabilityUnavailable)
    assert error.code is ErrorCode.ROUTE_UNDERSHOOT
    assert error.details["operation"] == "bounded_fix"
    # the plan route is the only candidate besides the previous route: role routing is not consulted
    assert listed(error) == [
        ("codex", "gpt-6-sol", "previous_route", "class_too_low"),
        ("codex", "gpt-6-mini", "plan_route", "class_too_low"),
    ]
    decision = routed(request(adm, explicit_model="gpt-6-astra"), cfg)
    assert (decision.runtime_id, decision.model, decision.source) == ("codex", "gpt-6-astra", "plan_route")
    assert (decision.model_class, decision.operation) == (TOP, Operation.BOUNDED_FIX)
    assert trail(decision) == [("codex", "gpt-6-sol", "previous_route", "class_too_low")]
    assert decision.resume_allowance.reason == "route_changed"


def test_bounded_fix_below_task_class_allowed_resumes_the_pinned_route() -> None:
    adm = admit(facts(Operation.BOUNDED_FIX, task_min_class=TOP), policy(bounded_fix_below_task_class=True))
    decision = routed(request(adm, explicit_model="gpt-6-sol"))
    assert (decision.source, decision.model, decision.model_class) == ("previous_route", "gpt-6-sol", IMP)
    assert decision.resume_allowance == ResumeAllowance(True, False, SESSION, "allowed")


def test_explicit_plan_effort_below_the_floor_is_undershoot_and_other_routes_are_raised() -> None:
    adm = admit(
        facts(Operation.NEW_IMPLEMENTATION, task_min_class=IMP, task_min_effort=Effort.XHIGH),
        ADMISSION_DEFAULTS,
    )
    error = refused(request(adm, explicit_model="gpt-6-sol", effort=Effort.MEDIUM))
    assert error.code is ErrorCode.ROUTE_UNDERSHOOT
    assert listed(error) == [("codex", "gpt-6-sol", "plan_route", "effort_too_low")]
    pinned = routed(request(adm, explicit_model="gpt-6-sol", effort=Effort.XHIGH))
    assert (pinned.effort, pinned.effort_flag, pinned.rejected) == (Effort.XHIGH, "xhigh", ())
    raised = routed(unrouted(adm, effort=Effort.LOW))  # not a plan route: the request is raised, not refused
    assert (raised.runtime_id, raised.model, raised.source) == ("claude_code", "sonnet", "preference")
    assert (raised.model_class, raised.effort, raised.effort_flag) == (IMP, Effort.XHIGH, "xhigh")


def test_explicit_model_without_runtime_routes_to_the_runtime_that_knows_it() -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    decision = routed(request(adm, explicit_runtime=None, explicit_model="gpt-6-astra"))
    assert (decision.runtime_id, decision.model, decision.source) == ("codex", "gpt-6-astra", "plan_route")
    assert decision.model_class is IMP  # the lowest class of the model that reaches the floor


REQUIRED = policy(resume={Operation.CONTINUATION: ResumePolicy.REQUIRED})


def test_required_resume_routes_only_the_previous_route() -> None:
    adm = admit(facts(Operation.CONTINUATION), REQUIRED)
    decision = routed(request(adm))  # the plan route codex/gpt-6-mini is never a candidate
    assert (decision.runtime_id, decision.model, decision.source) == ("codex", "gpt-6-sol", "previous_route")
    assert decision.resume_allowance == ResumeAllowance(True, True, SESSION, "allowed")


@pytest.mark.parametrize(
    ("status", "degraded_allow"),
    [
        (CapabilityStatus.UNKNOWN, frozenset({Capability.SESSION_RESUME})),  # degraded.allow never waives it
        (CapabilityStatus.UNKNOWN, frozenset()),
        (None, frozenset({Capability.SESSION_RESUME})),
        (CapabilityStatus.UNSUPPORTED, frozenset()),
    ],
)
def test_required_resume_without_verified_session_resume_is_admission_refused(
    status: CapabilityStatus | None, degraded_allow: frozenset[Capability]
) -> None:
    adm = admit(facts(Operation.CONTINUATION), REQUIRED)
    caps_by_runtime = {**CAPS, "codex": full_caps("codex", {Capability.SESSION_RESUME: status})}
    error = refused(
        request(adm), dataclasses.replace(CFG, degraded_allow=degraded_allow), caps_by_runtime=caps_by_runtime
    )
    assert isinstance(error, PreconditionFailed)
    assert (error.code, error.details["reason"]) == (
        ErrorCode.ADMISSION_REFUSED,
        "resume_required_unavailable",
    )
    assert listed(error) == [("codex", "gpt-6-sol", "previous_route", "capability_missing:session_resume")]


@pytest.mark.parametrize(
    ("changes", "reasons"),
    [
        ({"previous": None}, []),  # no previous session: nothing to resume, no other candidate
        ({"previous": dataclasses.replace(CODEX, session_ref=None)}, []),
    ],
)
def test_required_resume_without_a_previous_session_is_admission_refused(
    changes: Mapping[str, object], reasons: list[str]
) -> None:
    adm = admit(facts(Operation.CONTINUATION, **changes), REQUIRED)  # pyright: ignore[reportArgumentType]
    error = refused(request(adm))
    assert error.code is ErrorCode.ADMISSION_REFUSED
    assert [reason for *_, reason in listed(error)] == reasons


def test_required_resume_of_an_excluded_route_is_admission_refused() -> None:
    adm = admit(facts(Operation.CONTINUATION), REQUIRED)
    error = refused(unrouted(adm, excluded_routes=frozenset({("codex", "gpt-6-sol")})))
    assert error.code is ErrorCode.ADMISSION_REFUSED
    assert listed(error) == [("codex", "gpt-6-sol", "previous_route", "excluded_by_retry")]


SCOUT = admit(facts(Operation.RESEARCH, RoleId.SCOUT), ADMISSION_DEFAULTS)  # economy floor, no previous route


@pytest.mark.parametrize("status", [CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED, None])
def test_an_unverified_required_capability_fails_closed(status: CapabilityStatus | None) -> None:
    claude = full_caps("claude_code", {Capability.HEADLESS_EXECUTION: status}, loads=CLAUDE_LOADS)
    caps_by_runtime = {**CAPS, "claude_code": claude}
    decision = routed(unrouted(SCOUT, role=RoleId.SCOUT), caps_by_runtime=caps_by_runtime)
    assert trail(decision) == [
        ("claude_code", "haiku", "preference", "capability_missing:headless_execution")
    ]
    assert "headless_execution is " + ("unknown" if status is None else status.value) in (
        decision.rejected[0].detail
    )
    assert (decision.runtime_id, decision.model, decision.degraded) == ("codex", "gpt-6-mini", frozenset())
    allowed = dataclasses.replace(CFG, degraded_allow=frozenset({Capability.HEADLESS_EXECUTION}))
    if status is CapabilityStatus.UNSUPPORTED:  # degraded.allow takes an unknown, never an unsupported
        assert routed(unrouted(SCOUT, role=RoleId.SCOUT), allowed, caps_by_runtime).runtime_id == "codex"
        return
    degraded = routed(unrouted(SCOUT, role=RoleId.SCOUT), allowed, caps_by_runtime)
    assert (degraded.runtime_id, degraded.rejected) == ("claude_code", ())
    assert degraded.degraded == {Capability.HEADLESS_EXECUTION}


def test_missing_optional_capabilities_are_degraded_not_refused() -> None:
    claude = full_caps(
        "claude_code",
        {Capability.USAGE_REPORTING: CapabilityStatus.UNSUPPORTED, Capability.SESSION_RESUME: None},
        loads=CLAUDE_LOADS,
    )
    decision = routed(unrouted(SCOUT, role=RoleId.SCOUT), caps_by_runtime={**CAPS, "claude_code": claude})
    assert decision.runtime_id == "claude_code"
    assert decision.degraded == {Capability.USAGE_REPORTING, Capability.SESSION_RESUME}


@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("status", [CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED])
def test_config_isolation_by_requirement_and_degraded_allow(required: bool, status: CapabilityStatus) -> None:
    # without worktree project settings: those are never admitted without proven isolation (below)
    claude = full_caps("claude_code", {Capability.CONFIG_ISOLATION: status}, loads=CLAUDE_LOADS[:2])
    caps_by_runtime = {**CAPS, "claude_code": claude}
    req = unrouted(SCOUT, role=RoleId.SCOUT)
    for allow in (frozenset(), frozenset({Capability.CONFIG_ISOLATION})):
        cfg = dataclasses.replace(CFG, config_isolation_required=required, degraded_allow=allow)
        decision = routed(req, cfg, caps_by_runtime)
        passes = not required or (status is CapabilityStatus.UNKNOWN and bool(allow))
        if not passes:
            assert trail(decision) == [
                ("claude_code", "haiku", "preference", "capability_missing:config_isolation")
            ]
            assert decision.runtime_id == "codex"
            continue
        assert (decision.runtime_id, decision.degraded) == ("claude_code", {Capability.CONFIG_ISOLATION})
        # without proven isolation nothing counts as suppressed in the explained self loads
        assert [(view.active, view.reason) for view in decision.self_loads] == [(True, "not_isolated")] * 2


UNPROVEN_ISOLATION = [
    # (config_mode, config_isolation status, runtimes.config_isolation.required, runtimes.degraded.allow)
    ("isolated", CapabilityStatus.UNKNOWN, True, frozenset({Capability.CONFIG_ISOLATION})),  # degraded.allow
    ("isolated", CapabilityStatus.UNKNOWN, False, frozenset()),  # config_isolation.required = false
    ("isolated", CapabilityStatus.UNSUPPORTED, False, frozenset({Capability.CONFIG_ISOLATION})),
    ("isolated", None, False, frozenset()),  # no record at all
    ("inherit", CapabilityStatus.UNKNOWN, True, frozenset()),  # inherit never requires config_isolation
    ("inherit", CapabilityStatus.UNKNOWN, False, frozenset({Capability.CONFIG_ISOLATION})),
    ("inherit", CapabilityStatus.UNSUPPORTED, True, frozenset({Capability.CONFIG_ISOLATION})),
    ("inherit", None, True, frozenset()),
]


@pytest.mark.parametrize(("mode", "status", "required", "allow"), UNPROVEN_ISOLATION)
def test_suppressible_project_settings_without_proven_isolation_are_refused(
    mode: Literal["isolated", "inherit"],
    status: CapabilityStatus | None,
    required: bool,
    allow: frozenset[Capability],
) -> None:
    """§4.3.1 rule 7: ``suppressed_by = "config_isolation"`` is a static claim; only an effective
    native/adapted ``config_isolation`` proves the worktree settings suppressed, in both modes and whatever
    the config says."""
    claude = full_caps("claude_code", {Capability.CONFIG_ISOLATION: status}, loads=CLAUDE_LOADS)
    cfg = dataclasses.replace(CFG, config_isolation_required=required, degraded_allow=allow)
    caps_by_runtime = {**CAPS, "claude_code": claude}
    decision = routed(unrouted(SCOUT, role=RoleId.SCOUT, config_mode=mode), cfg, caps_by_runtime)
    assert trail(decision) == [("claude_code", "haiku", "preference", "capability_missing:config_isolation")]
    assert decision.rejected[0].detail == "project_settings_not_suppressible"
    # the next preferred runtime proves its isolation: its worktree settings stay suppressed
    assert (decision.runtime_id, decision.source) == ("codex", "preference")
    assert ("project_settings", False, "untrusted_suppressed") in [
        (view.kind.value, view.active, view.reason) for view in decision.self_loads
    ]
    # the plan route on that runtime alone: nothing is routed (no trust is assumed without a policy input)
    error = refused(
        request(
            SCOUT, role=RoleId.SCOUT, explicit_runtime="claude_code", explicit_model="haiku", config_mode=mode
        ),
        cfg,
        caps_by_runtime=caps_by_runtime,
    )
    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert listed(error) == [("claude_code", "haiku", "plan_route", "capability_missing:config_isolation")]


@pytest.mark.parametrize("status", [CapabilityStatus.NATIVE, CapabilityStatus.ADAPTED])
@pytest.mark.parametrize("mode", ["isolated", "inherit"])
def test_suppressible_project_settings_with_verified_isolation_are_routed(
    mode: Literal["isolated", "inherit"], status: CapabilityStatus
) -> None:
    claude = full_caps("claude_code", {Capability.CONFIG_ISOLATION: status}, loads=CLAUDE_LOADS)
    cfg = dataclasses.replace(CFG, config_isolation_required=False)
    decision = routed(
        unrouted(SCOUT, role=RoleId.SCOUT, config_mode=mode), cfg, {**CAPS, "claude_code": claude}
    )
    assert (decision.runtime_id, decision.rejected, decision.degraded) == ("claude_code", (), frozenset())
    assert [(view.kind.value, view.active, view.reason) for view in decision.self_loads][-1] == (
        "project_settings",
        False,
        "untrusted_suppressed",
    )


def test_unproven_project_settings_isolation_falls_back_to_a_verified_runtime() -> None:
    claude = full_caps(
        "claude_code", {Capability.CONFIG_ISOLATION: CapabilityStatus.UNKNOWN}, loads=CLAUDE_LOADS
    )
    cfg = dataclasses.replace(
        CFG,
        degraded_allow=frozenset({Capability.CONFIG_ISOLATION}),
        role_routing={RoleId.SCOUT: {"runtime": "claude_code", "fallback": ["codex"]}},
    )
    decision = routed(
        unrouted(SCOUT, role=RoleId.SCOUT, config_mode="inherit"), cfg, {**CAPS, "claude_code": claude}
    )
    assert (decision.runtime_id, decision.model, decision.source) == ("codex", "gpt-6-mini", "role_fallback")
    assert trail(decision) == [
        ("claude_code", "haiku", "role_routing", "capability_missing:config_isolation")
    ]


@pytest.mark.parametrize("mode", ["isolated", "inherit"])
def test_unsuppressible_project_settings_are_refused_whatever_the_config(mode: str) -> None:
    codex = full_caps("codex", loads=(self_load(SelfLoadKind.PROJECT_SETTINGS, "never"),))
    cfg = dataclasses.replace(
        CFG, config_isolation_required=False, degraded_allow=frozenset({Capability.CONFIG_ISOLATION})
    )
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    error = refused(
        request(adm, explicit_model="gpt-6-sol", config_mode=mode),
        cfg,
        caps_by_runtime={**CAPS, "codex": codex},
    )
    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE
    rejected: list[dict[str, Any]] = error.details["rejected"]  # type: ignore[assignment]
    assert [(item["reason"], item["detail"]) for item in rejected] == [
        ("capability_missing:config_isolation", "project_settings_not_suppressible")
    ]


def test_fallback_skips_the_failed_route_like_the_routing_explain_example() -> None:
    """``examples/runtimes/routing-explain.json``: codex failed, grok cannot isolate, claude_code takes it."""
    adm = admit(
        facts(Operation.CONTINUATION, task_min_class=IMP, task_min_effort=Effort.HIGH), ADMISSION_DEFAULTS
    )
    cfg = dataclasses.replace(CFG, role_routing={RoleId.EXECUTOR: FALLBACK})
    decision = routed(unrouted(adm, excluded_routes=frozenset({("codex", "gpt-6-sol")})), cfg)
    assert (decision.runtime_id, decision.model, decision.source) == (
        "claude_code",
        "sonnet",
        "role_fallback",
    )
    assert (decision.model_class, decision.effort, decision.effort_flag) == (IMP, Effort.HIGH, "high")
    # role_routing codex/gpt-6-sol collapses into the previous route; grok has no model in the catalog
    assert trail(decision) == [
        ("codex", "gpt-6-sol", "previous_route", "excluded_by_retry"),
        ("grok", None, "role_fallback", "capability_missing:config_isolation"),
    ]
    assert decision.resume_allowance == ResumeAllowance(False, False, None, "route_changed")
    assert (decision.config_mode, decision.catalog_digest, decision.admission) == (
        "isolated",
        CATALOG_DIGEST,
        adm,
    )
    assert decision.self_loads == explain_self_loads(CAPS["claude_code"], "isolated")
    # without the failure the previous route is resumed
    resumed = routed(unrouted(adm), cfg)
    assert (resumed.source, resumed.rejected) == ("previous_route", ())
    assert resumed.resume_allowance == ResumeAllowance(True, False, SESSION, "allowed")


def test_fallback_reapplies_the_admission_floor() -> None:
    started = dataclasses.replace(CODEX, model_class=TOP)  # S-23: a continuation is never cheaper
    adm = admit(facts(Operation.CONTINUATION, started_by=started), ADMISSION_DEFAULTS)
    assert adm.min_class is TOP
    cfg = dataclasses.replace(CFG, role_routing={RoleId.EXECUTOR: FALLBACK})
    same_runtime = routed(unrouted(adm, excluded_routes=frozenset({("codex", "gpt-6-sol")})), cfg)
    assert (same_runtime.runtime_id, same_runtime.model, same_runtime.source) == (
        "codex",
        "gpt-6-astra",
        "role_routing",
    )
    whole_runtime = routed(unrouted(adm, excluded_routes=frozenset({("codex", None)})), cfg)
    assert (whole_runtime.runtime_id, whole_runtime.model, whole_runtime.model_class) == (
        "claude_code",
        "opus",
        TOP,
    )
    assert [reason for *_, reason in trail(whole_runtime)] == [
        "excluded_by_retry",
        "excluded_by_retry",
        "capability_missing:config_isolation",
    ]
    pinned = {**FALLBACK, "fallback": [{"runtime": "claude_code", "model": "sonnet"}]}
    error = refused(
        unrouted(adm, excluded_routes=frozenset({("codex", None)})),
        dataclasses.replace(CFG, role_routing={RoleId.EXECUTOR: pinned}),
    )
    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE  # mixed reasons: not an undershoot
    assert listed(error)[-1] == ("claude_code", "sonnet", "role_fallback", "class_too_low")


def test_candidate_order_and_role_routing_forms() -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    assert routed(unrouted(adm)).source == "preference"
    by_class = {RoleId.EXECUTOR: {"model_class": "frontier"}}  # no runtime: each preferred runtime
    decision = routed(unrouted(adm), dataclasses.replace(CFG, role_routing=by_class))
    assert (decision.runtime_id, decision.model, decision.source) == ("claude_code", "opus", "role_routing")
    as_text = {RoleId.EXECUTOR: {"runtime": "grok", "fallback": ["codex"]}}  # settings schema: plain ids
    decision = routed(unrouted(adm), dataclasses.replace(CFG, role_routing=as_text))
    assert (decision.runtime_id, decision.model, decision.source) == ("codex", "gpt-6-sol", "role_fallback")


def efforts(route_: Mapping[str, JsonValue], adm: Admission = SCOUT, **changes: object) -> RouteDecision:
    """The decision of a request without a plan route under ``runtimes.role_routing.<role> = route_``."""
    role = RoleId.SCOUT if adm is SCOUT else RoleId.EXECUTOR
    cfg = dataclasses.replace(CFG, role_routing={role: dict(route_)})
    return routed(unrouted(adm, role=role, **changes), cfg)


def test_role_route_effort_raises_the_decision_effort() -> None:
    """``runtimes.role_routing.<role>.effort`` (settings schema) is honored on the real route."""
    decision = efforts({"runtime": "codex", "effort": "xhigh"})
    assert (decision.runtime_id, decision.source) == ("codex", "role_routing")
    assert (decision.effort, decision.effort_flag) == (Effort.XHIGH, "xhigh")
    # a plain-id fallback (the schema form) keeps the effort of its entry
    fallback = efforts({"runtime": "grok", "effort": "high", "fallback": ["codex"]})
    assert (fallback.runtime_id, fallback.source, fallback.effort) == ("codex", "role_fallback", Effort.HIGH)
    # an object fallback item may name its own effort
    own = efforts(
        {"runtime": "grok", "effort": "high", "fallback": [{"runtime": "codex", "effort": "medium"}]}
    )
    assert (own.runtime_id, own.effort, own.effort_flag) == ("codex", Effort.MEDIUM, "medium")
    # preference candidates are not role routes: no declared effort
    assert routed(unrouted(SCOUT, role=RoleId.SCOUT)).effort is Effort.LOW


def test_role_route_effort_never_lowers_the_request_or_the_admission_floor() -> None:
    assert efforts({"runtime": "codex", "effort": "low"}, effort=Effort.HIGH).effort is Effort.HIGH
    adm = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_effort=Effort.XHIGH), ADMISSION_DEFAULTS)
    floor = efforts({"runtime": "codex", "effort": "low", "fallback": ["claude_code"]}, adm)
    assert (floor.runtime_id, floor.effort, floor.effort_flag) == ("codex", Effort.XHIGH, "xhigh")
    excluded = efforts(
        {"runtime": "codex", "effort": "medium", "fallback": ["claude_code"]},
        adm,
        excluded_routes=frozenset({("codex", None)}),
    )
    assert (excluded.runtime_id, excluded.source, excluded.effort) == (
        "claude_code",
        "role_fallback",
        Effort.XHIGH,
    )


def effort_refused(route_: Mapping[str, JsonValue], adm: Admission = SCOUT, **changes: object) -> SkmError:
    role = RoleId.SCOUT if adm is SCOUT else RoleId.EXECUTOR
    cfg = dataclasses.replace(CFG, role_routing={role: dict(route_)})
    return refused(unrouted(adm, role=role, **changes), cfg)


def unsupported(source: str, value: str) -> str:
    return f"{source} effort {value} is no runtime effort (highest xhigh); it is not lowered to one"


def test_role_route_effort_max_is_refused_never_met_by_xhigh() -> None:
    """The settings schema's ``"max"`` is above every ``Effort`` of §4.1: no route proves it, so the role
    route and every fallback that keeps it are ``effort_unsupported`` (fail closed), never routed at xhigh."""
    error = effort_refused({"runtime": "codex", "effort": "max"})
    assert isinstance(error, CapabilityUnavailable)
    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE  # not an undershoot: no floor was compared
    assert error.details["rejected"] == [
        {
            "runtime_id": "codex",
            "model": "gpt-6-mini",
            "source": "role_routing",
            "reason": "effort_unsupported",
            "detail": unsupported("role_routing", "max"),
        }
    ]
    # a raised request or admission floor does not turn max into xhigh either
    adm = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_effort=Effort.XHIGH), ADMISSION_DEFAULTS)
    floor = effort_refused({"runtime": "codex", "effort": "max"}, adm, effort=Effort.XHIGH)
    assert listed(floor) == [("codex", "gpt-6-sol", "role_routing", "effort_unsupported")]
    # a fallback that keeps the entry's max (plain id or object without effort) is refused as well
    kept = effort_refused(
        {"runtime": "codex", "effort": "max", "fallback": ["claude_code", {"runtime": "grok"}]}
    )
    assert listed(kept) == [
        ("codex", "gpt-6-mini", "role_routing", "effort_unsupported"),
        ("claude_code", "haiku", "role_fallback", "effort_unsupported"),
        ("grok", None, "role_fallback", "capability_missing:config_isolation"),
    ]
    assert kept.details["rejected"][1]["detail"] == unsupported("role_fallback", "max")  # type: ignore[index]
    # a fallback item's own max is refused; the preference list is no way around a configured role route
    own = effort_refused({"runtime": "grok", "fallback": [{"runtime": "codex", "effort": "max"}]})
    assert listed(own)[-1] == ("codex", "gpt-6-mini", "role_fallback", "effort_unsupported")
    # a fallback item with its own supported effort is routed at that effort, after the refused max
    routed_ = efforts(
        {"runtime": "codex", "effort": "max", "fallback": [{"runtime": "claude_code", "effort": "high"}]}
    )
    assert (routed_.runtime_id, routed_.source, routed_.effort, routed_.effort_flag) == (
        "claude_code",
        "role_fallback",
        Effort.HIGH,
        "high",
    )
    assert trail(routed_) == [("codex", "gpt-6-mini", "role_routing", "effort_unsupported")]


@pytest.mark.parametrize(("value", "shown"), [("turbo", "turbo"), ("", ""), ("XHIGH", "XHIGH"), (5, "5")])
def test_role_route_effort_outside_the_enum_is_refused(value: JsonValue, shown: str) -> None:
    error = effort_refused({"runtime": "codex", "effort": value})
    assert error.details["rejected"] == [
        {
            "runtime_id": "codex",
            "model": "gpt-6-mini",
            "source": "role_routing",
            "reason": "effort_unsupported",
            "detail": unsupported("role_routing", shown),
        }
    ]
    # an explicit null is no declared effort
    assert efforts({"runtime": "codex", "effort": None}).effort is Effort.LOW


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"allowed": frozenset({"claude_code"})}, "not_allowed"),
        ({"registered": frozenset({"claude_code"})}, "not_registered"),
        ({"caps_by_runtime": {"claude_code": CAPS["claude_code"]}}, "not_registered"),
        (
            {"caps_by_runtime": {**CAPS, "codex": full_caps("codex", read_only_network=False)}},
            "read_only_network_unsupported",
        ),
    ],
)
def test_runtime_gates(changes: Mapping[str, Any], reason: str) -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    inputs = dict(changes)
    cfg = dataclasses.replace(CFG, allowed=inputs.pop("allowed", CFG.allowed))
    error = refused(request(adm, explicit_model="gpt-6-sol", network_read_only=True), cfg, **inputs)
    assert listed(error) == [("codex", "gpt-6-sol", "plan_route", reason)]


def install(runtime: str, auth: AuthState = AuthState.OK, host: HostId = HOST) -> RuntimeInstallation:
    return RuntimeInstallation(
        host_id=host,
        runtime_id=runtime,
        version="1.2.3",
        binary_locator=None,
        auth_state=auth,
        detected_at=datetime(2026, 10, 1, tzinfo=UTC),
        details={},
    )


@pytest.mark.parametrize(
    ("installs", "reason"),
    [
        ({}, "not_installed"),
        ({"codex": install("codex", host=OTHER_HOST)}, "not_installed"),
        ({"codex": install("codex", AuthState.MISSING)}, "auth_missing"),
        ({"codex": install("codex", AuthState.EXPIRED)}, "auth_expired"),
        ({"codex": install("codex", AuthState.UNKNOWN)}, None),
        ({"codex": install("codex")}, None),
    ],
)
def test_installation_on_the_host(installs: Mapping[str, RuntimeInstallation], reason: str | None) -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    req = request(adm, explicit_model="gpt-6-sol", host_id=HOST)
    assert routed(dataclasses.replace(req, host_id=None)).runtime_id == "codex"  # readiness: no host check
    if reason is None:
        decision = routed(req, installs=installs)
        assert decision.runtime_id == "codex"
        unknown = installs["codex"].auth_state is AuthState.UNKNOWN
        assert decision.degraded_details == (("auth_unknown",) if unknown else ())  # accepted, never silently
        return
    assert listed(refused(req, installs=installs)) == [("codex", "gpt-6-sol", "plan_route", reason)]


def test_models_unknown_deprecated_and_missing() -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    refuse = dataclasses.replace(CFG, unknown_model="refuse")
    assert listed(refused(request(adm, explicit_model="gpt-9"), refuse))[0][3] == "model_unknown"
    # warn: an unknown model proves no class above the lowest, so it never reaches a raised floor
    error = refused(request(adm, explicit_model="gpt-9"))
    assert (error.code, listed(error)[0][3]) == (ErrorCode.ROUTE_UNDERSHOOT, "class_too_low")
    lowest = routed(request(SCOUT, role=RoleId.SCOUT, explicit_model="gpt-9"))
    assert (lowest.model, lowest.model_class) == ("gpt-9", ECO)
    assert listed(refused(request(adm, explicit_model="gpt-5-old")))[0][3] == "model_deprecated"
    missing = refused(request(adm, explicit_runtime="cursor", explicit_model=None))
    assert listed(missing) == [("cursor", None, "plan_route", "no_model_for_class")]


def test_unknown_model_and_auth_are_accepted_with_details_and_the_smallest_window() -> None:
    """§4.10 step 3 at ``unknown_model = "warn"``: ``model_unknown``/``auth_unknown`` details, the smallest
    window of the runtime's catalog models."""
    known = routed(request(SCOUT, role=RoleId.SCOUT, explicit_model="gpt-6-astra"))
    assert (known.context_window_tokens, known.degraded_details) == (400_000, ())
    unknown = routed(request(SCOUT, role=RoleId.SCOUT, explicit_model="gpt-9"))
    assert (unknown.context_window_tokens, unknown.degraded_details) == (128_000, ("model_unknown",))
    assert unknown.model_class is ECO  # the request's own lowest floor, not a class proved for gpt-9
    both = routed(
        request(SCOUT, role=RoleId.SCOUT, explicit_model="gpt-9", host_id=HOST),
        installs={"codex": install("codex", AuthState.UNKNOWN)},
    )
    assert both.degraded_details == ("auth_unknown", "model_unknown")
    # a raised class floor is never reached by an unknown model, with or without the details
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    assert listed(refused(request(adm, explicit_model="gpt-9")))[0][3] == "class_too_low"


def no_window(model: str, runtime: str) -> str:
    return (
        f"{model} is not in the catalog of {runtime}, which has no valid context window to bound it "
        "(unknown_model warn)"
    )


def with_codex_models(*models: ModelEntry) -> ModelCatalog:
    codex = dataclasses.replace(CATALOG.runtimes["codex"], models=models)
    return dataclasses.replace(CATALOG, runtimes={**CATALOG.runtimes, "codex": codex})


@pytest.mark.parametrize(
    ("models", "runtime"),
    [
        ((), "cursor"),  # no catalog entry for the runtime at all
        ((), "codex"),  # a catalog entry with no models
        ((entry("gpt-6-mini", "codex", ECO, window=999), entry("gpt-6-sol", "codex", IMP)), "codex"),
        ((entry("gpt-6-mini", "codex", ECO, window=0),), "codex"),
        ((entry("gpt-6-mini", "codex", ECO, window=True),), "codex"),  # a bool is no window
    ],
)
def test_unknown_model_without_a_valid_window_is_refused(
    models: tuple[ModelEntry, ...], runtime: str
) -> None:
    """At ``unknown_model = "warn"`` an unknown model is accepted only with a proved smallest window; without
    one (no catalog models, or any window below the schema minimum) it is ``model_unknown``, never a guess."""
    models_catalog = with_codex_models(*models)
    req = request(SCOUT, role=RoleId.SCOUT, explicit_runtime=runtime, explicit_model="gpt-9")
    with pytest.raises(CapabilityUnavailable) as caught:
        route(req, CFG, models_catalog, CAPS, {}, frozenset(CAPS))
    assert caught.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert caught.value.details["rejected"] == [
        {
            "runtime_id": runtime,
            "model": "gpt-9",
            "source": "plan_route",
            "reason": "model_unknown",
            "detail": no_window("gpt-9", runtime),
        }
    ]
    # the same runtime and catalog still route a known model with its own window
    if runtime == "codex" and models:
        known = route(
            dataclasses.replace(req, explicit_model="gpt-6-mini"),
            CFG,
            models_catalog,
            CAPS,
            {},
            frozenset(CAPS),
        )
        assert (known.model, known.context_window_tokens, known.degraded_details) == (
            "gpt-6-mini",
            models[0].context_window_tokens,
            (),
        )


def test_unknown_model_window_refusal_on_the_role_route_and_fallback() -> None:
    """The window rule holds on every candidate source: a role route with an unknown model on a runtime
    without catalog models is refused, and its fallback with a provable window is routed."""
    cfg = dataclasses.replace(
        CFG,
        role_routing={
            RoleId.SCOUT: {"runtime": "cursor", "model": "cursor-x", "fallback": [{"model": "gpt-9"}]}
        },
    )
    decision = routed(unrouted(SCOUT, role=RoleId.SCOUT), cfg)
    assert (decision.runtime_id, decision.model, decision.source) == ("claude_code", "gpt-9", "role_fallback")
    assert (decision.context_window_tokens, decision.degraded_details) == (200_000, ("model_unknown",))
    assert trail(decision) == [("cursor", "cursor-x", "role_routing", "model_unknown")]
    assert decision.rejected[0].detail == no_window("cursor-x", "cursor")
    # a raised class floor stays an undershoot: the window is never consulted for a class it cannot prove
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    error = refused(request(adm, explicit_runtime="cursor", explicit_model="cursor-x"))
    assert (error.code, listed(error)) == (
        ErrorCode.ROUTE_UNDERSHOOT,
        [("cursor", "cursor-x", "plan_route", "class_too_low")],
    )


def test_route_role_refuses_an_unknown_model_without_a_window_and_a_max_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The facade path of both fail-closed rules (settings schema values through ``route_role``)."""
    monkeypatch.setattr(public, "catalog", lambda uow, *, config, pins=None: CATALOG)
    monkeypatch.setattr(
        public, "capabilities", lambda uow, gateways, runtime_id, version=None: CAPS[runtime_id]
    )
    settings = {
        **ROUTE_SETTINGS,
        "runtimes.allowed": ["claude_code", "codex", "cursor"],
        "runtimes.role_routing": {
            "scout": {
                "runtime": "cursor",
                "model": "cursor-x",
                "fallback": [
                    {"runtime": "codex", "effort": "max"},
                    {"runtime": "claude_code", "effort": "high"},
                ],
            }
        },
    }
    uow: Any = Uow(Repository(()))
    gateways: Any = Gateways()
    req = unrouted(SCOUT, role=RoleId.SCOUT)
    decision = public.route_role(uow, gateways, req, config=Config(settings))  # type: ignore[arg-type]
    assert (decision.runtime_id, decision.model, decision.effort) == ("claude_code", "haiku", Effort.HIGH)
    assert decision.context_window_tokens == 200_000
    assert trail(decision) == [
        ("cursor", "cursor-x", "role_routing", "model_unknown"),
        ("codex", "gpt-6-mini", "role_fallback", "effort_unsupported"),
    ]
    fallback: list[JsonValue] = [{"runtime": "codex", "effort": "max"}]
    only_max = {
        **settings,
        "runtimes.role_routing": {"scout": {"runtime": "cursor", "model": "x", "fallback": fallback}},
    }
    with pytest.raises(CapabilityUnavailable) as caught:
        public.route_role(uow, gateways, req, config=Config(only_max))  # type: ignore[arg-type]
    assert listed(caught.value) == [
        ("cursor", "x", "role_routing", "model_unknown"),
        ("codex", "gpt-6-mini", "role_fallback", "effort_unsupported"),
    ]


def test_effort_flag_needs_effort_control() -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_effort=Effort.HIGH), ADMISSION_DEFAULTS)
    codex = full_caps("codex", {Capability.EFFORT_CONTROL: CapabilityStatus.UNKNOWN})
    decision = routed(
        request(adm, explicit_model="gpt-6-sol", effort=Effort.HIGH), caps_by_runtime={**CAPS, "codex": codex}
    )
    assert (decision.effort, decision.effort_flag) == (Effort.HIGH, "")


def test_route_is_deterministic_over_mapping_order() -> None:
    adm = admit(facts(Operation.CONTINUATION, task_min_class=IMP), ADMISSION_DEFAULTS)
    cfg = dataclasses.replace(CFG, role_routing={RoleId.EXECUTOR: FALLBACK})
    req = unrouted(adm, excluded_routes=frozenset({("codex", "gpt-6-sol")}), host_id=HOST)
    installs = {name: install(name) for name in CAPS}
    first = routed(req, cfg, CAPS, installs)
    again = routed(req, cfg, dict(reversed(CAPS.items())), dict(reversed(installs.items())))
    assert first == again


# --- route_role: the facade composes config, catalog, effective capabilities and installations


class Repository:
    def __init__(self, installs: tuple[RuntimeInstallation, ...]) -> None:
        self.installs = installs
        self.hosts: list[HostId] = []

    def list_for_host(self, host_id: HostId) -> tuple[RuntimeInstallation, ...]:
        self.hosts.append(host_id)
        return self.installs


class Uow:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def repo(self, port: type[object]) -> object:
        assert port is HostRuntimeRepository
        return self.repository


class Gateways:
    def __init__(self) -> None:
        self.static = StaticCapabilityCatalog(declarations=CAPS, rules={})

    def get(self, port: type[object]) -> object:
        assert port is CapabilityCatalog
        return self.static


ROUTE_SETTINGS: dict[str, JsonValue] = {
    "runtimes.allowed": ["claude_code", "codex", "grok"],
    "runtimes.preference": ["claude_code", "codex"],
    "runtimes.role_routing": {"executor": FALLBACK},
    "runtimes.degraded.allow": ["usage_reporting", "not_a_capability"],
    "runtimes.config_isolation.required": True,
    "runtimes.routing.unknown_model": "warn",
}


def test_route_role_routes_on_the_effective_capabilities_of_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    versions: dict[str, str | None] = {}

    def effective(
        uow: object, gateways: object, runtime_id: str, runtime_version: str | None = None
    ) -> object:
        versions[runtime_id] = runtime_version
        return CAPS[runtime_id]

    monkeypatch.setattr(public, "catalog", lambda uow, *, config, pins=None: CATALOG)
    monkeypatch.setattr(public, "capabilities", effective)
    host = HostRouting(frozenset(RouteKey("claude_code", "sonnet", effort) for effort in Effort))
    monkeypatch.setattr(public, "host_routing", lambda *args, **kwargs: host)
    repository = Repository((install("claude_code"), install("codex", host=OTHER_HOST)))
    adm = admit(facts(Operation.CONTINUATION, task_min_class=IMP), ADMISSION_DEFAULTS)
    req = unrouted(adm, excluded_routes=frozenset({("codex", "gpt-6-sol")}), host_id=HOST)
    decision = public.route_role(Uow(repository), Gateways(), req, config=Config(ROUTE_SETTINGS))  # type: ignore[arg-type]
    assert (decision.runtime_id, decision.model, decision.source) == (
        "claude_code",
        "sonnet",
        "role_fallback",
    )
    assert repository.hosts == [HOST]
    # only registered and allowed runtimes, each at the version installed on this host
    assert versions == {"claude_code": "1.2.3", "codex": None, "grok": None}
    expected = route(
        req,
        RouteConfig(
            allowed=frozenset({"claude_code", "codex", "grok"}),
            preference=("claude_code", "codex"),
            role_routing={RoleId.EXECUTOR: FALLBACK},
            degraded_allow=frozenset({Capability.USAGE_REPORTING}),
        ),
        CATALOG,
        {name: CAPS[name] for name in versions},
        {"claude_code": install("claude_code")},
        frozenset(CAPS),
        host=host,
    )
    assert decision == expected


def test_route_role_without_allowed_runtimes_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(public, "catalog", lambda uow, *, config, pins=None: CATALOG)
    monkeypatch.setattr(
        public, "capabilities", lambda uow, gateways, runtime_id, version=None: CAPS[runtime_id]
    )
    adm = admit(facts(Operation.NEW_IMPLEMENTATION), ADMISSION_DEFAULTS)
    with pytest.raises(CapabilityUnavailable) as caught:
        public.route_role(Uow(Repository(())), Gateways(), unrouted(adm), config=Config({}))  # type: ignore[arg-type]
    assert caught.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert [reason for *_, reason in listed(caught.value)] == []  # no preference: no candidate at all


# --- invariants over arbitrary facts

classes = st.sampled_from(list(ModelClass))
routes = st.builds(
    PreviousRoute,
    runtime_id=st.sampled_from(["codex", "claude_code"]),
    model=st.sampled_from(["gpt-6-sol", "sonnet"]),
    model_class=classes,
    effort=st.sampled_from(list(Effort)),
    session_ref=st.none() | st.just(SESSION),
    step_ref=st.just(STEP),
)
pairs = st.sampled_from([(op, role) for op, roles in OPERATION_ROLES.items() for role in sorted(roles)])


@given(
    pair=pairs,
    task=st.none() | classes,
    started_by=st.none() | routes,
    previous=st.none() | routes,
    previous_digest=st.sampled_from([None, DIGEST, OLD_DIGEST]),
    brief=st.none() | st.builds(FixBriefFacts, st.integers(0, 3), st.integers(0, 2), st.just(("src/a.py",))),
    output=st.none() | st.just(OUTPUT),
    below=st.booleans(),
    resume=st.sampled_from(list(ResumePolicy)),
    role_min=st.none() | classes,
)
def test_admission_never_lowers_a_floor(
    pair: tuple[Operation, RoleId],
    task: ModelClass | None,
    started_by: PreviousRoute | None,
    previous: PreviousRoute | None,
    previous_digest: str | None,
    brief: FixBriefFacts | None,
    output: str | None,
    below: bool,
    resume: ResumePolicy,
    role_min: ModelClass | None,
) -> None:
    op, role = pair
    pol = policy(
        resume=dict.fromkeys(Operation, resume),
        bounded_fix_below_task_class=below,
        role_min_class={} if role_min is None else {role: role_min},
    )
    given_facts = AdmissionFacts(
        op, role, task, Effort.HIGH, started_by, previous, DIGEST, previous_digest, brief, output
    )
    if op in (Operation.REVIEW, Operation.FINAL_CLOSE) and output is None:
        with pytest.raises(PreconditionFailed) as refused:
            admit(given_facts, pol)
        assert refused.value.code is ErrorCode.ADMISSION_REFUSED
        return
    got = admit(given_facts, pol)  # every other combination of facts is admitted, possibly escalated
    rank = MODEL_CLASS_ORDER.index
    assert rank(got.min_class) >= rank(ADMISSION_DEFAULTS.min_class[got.operation])
    assert rank(got.min_class) >= rank(ADMISSION_DEFAULTS.min_class[op])  # an escalation never cheapens
    if role_min is not None:
        assert rank(got.min_class) >= rank(role_min)
    if task is not None and op in (
        Operation.NEW_IMPLEMENTATION,
        Operation.SCOPE_CHANGE,
        Operation.CONTINUATION,
    ):
        assert rank(got.min_class) >= rank(task)
    if got.operation is Operation.CONTINUATION and started_by is not None:
        assert rank(got.min_class) >= rank(started_by.model_class)
    if got.operation is not op:
        assert op in (Operation.CONTINUATION, Operation.BOUNDED_FIX)
        assert got.operation in (Operation.SCOPE_CHANGE, Operation.NEW_IMPLEMENTATION)
        assert len(got.notes) == 1
        if task is not None:
            assert rank(got.min_class) >= rank(task)
    assert (got.required_capabilities == {Capability.SESSION_RESUME}) is (got.resume is ResumePolicy.REQUIRED)
    if got.resume is ResumePolicy.NEVER:
        assert got.prefer_route is None
    if got.prefer_route is not None:
        assert got.prefer_route == previous
        assert got.prefer_route.session_ref is not None


def test_host_substitution_reapplies_work_capability_independence_and_resume_gates() -> None:
    asked = RouteKey("codex", "gpt-6-sol", Effort.HIGH)
    selected = RouteKey("claude_code", "sonnet", Effort.HIGH)
    admission = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_class=IMP), ADMISSION_DEFAULTS)
    req = request(admission, explicit_model=asked.model_id, effort=asked.effort, host_id=HOST)
    host = HostRouting(frozenset({selected}), ((asked, selected),))
    installs = {"codex": install("codex"), "claude_code": install("claude_code")}

    decision = route(req, CFG, CATALOG, CAPS, installs, frozenset(CAPS), host=host)
    assert decision.requested_route == asked
    assert (decision.runtime_id, decision.model, decision.effort) == (
        selected.runtime_id,
        selected.model_id,
        selected.effort,
    )
    assert decision.source == "host_substitution"

    denied = dataclasses.replace(CFG, allowed=frozenset({"codex"}))
    with pytest.raises(CapabilityUnavailable) as refused_work:
        route(req, denied, CATALOG, CAPS, installs, frozenset(CAPS), host=host)
    assert "not_allowed" in {row[3] for row in listed(refused_work.value)}

    capped = full_caps("claude_code", {Capability.HEADLESS_EXECUTION: CapabilityStatus.UNSUPPORTED})
    caps = {**CAPS, "claude_code": capped}
    with pytest.raises(CapabilityUnavailable) as refused_capability:
        route(req, CFG, CATALOG, caps, installs, frozenset(CAPS), host=host)
    assert "capability_missing:headless_execution" in {row[3] for row in listed(refused_capability.value)}

    excluded = dataclasses.replace(req, executor_runtimes=frozenset({"claude_code"}))
    with pytest.raises(CapabilityUnavailable) as refused_independence:
        route(excluded, CFG, CATALOG, CAPS, installs, frozenset(CAPS), host=host)
    assert "review_independence" in {row[3] for row in listed(refused_independence.value)}

    required = dataclasses.replace(admission, prefer_route=CODEX, resume=ResumePolicy.REQUIRED)
    with pytest.raises(PreconditionFailed) as refused_resume:
        route(
            dataclasses.replace(req, admission=required),
            CFG,
            CATALOG,
            CAPS,
            installs,
            frozenset(CAPS),
            host=host,
        )
    assert refused_resume.value.code is ErrorCode.ADMISSION_REFUSED


def test_host_routing_keeps_fallbacks_with_the_same_model_and_different_effort() -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_class=IMP), ADMISSION_DEFAULTS)
    req = unrouted(adm, host_id=HOST, effort=Effort.HIGH)
    cfg = dataclasses.replace(
        CFG,
        role_routing={
            RoleId.EXECUTOR: {
                "runtime": "codex",
                "model": "gpt-6-sol",
                "effort": "high",
                "fallback": [{"runtime": "codex", "model": "gpt-6-sol", "effort": "xhigh"}],
            }
        },
    )
    host = HostRouting(frozenset({RouteKey("codex", "gpt-6-sol", Effort.XHIGH)}))
    decision = route(req, cfg, CATALOG, CAPS, {"codex": install("codex")}, frozenset(CAPS), host=host)
    assert decision.effort is Effort.XHIGH
    assert decision.source == "role_fallback"


def test_independent_review_skips_executor_family_on_a_different_runtime() -> None:
    adm = admit(facts(Operation.REVIEW, RoleId.REVIEWER), ADMISSION_DEFAULTS)
    req = dataclasses.replace(
        unrouted(adm, host_id=HOST, effort=Effort.HIGH),
        executor_runtimes=frozenset({"cursor"}),
        executor_families=frozenset({"gpt"}),
    )
    cfg = dataclasses.replace(CFG, preference=("codex", "claude_code"))
    host = HostRouting(
        frozenset(
            {RouteKey("codex", "gpt-6-sol", Effort.HIGH), RouteKey("claude_code", "sonnet", Effort.HIGH)}
        )
    )
    installs = {runtime: install(runtime) for runtime in cfg.preference}

    decision = route(req, cfg, CATALOG, CAPS, installs, frozenset(CAPS), host=host)

    assert (decision.runtime_id, decision.model) == ("claude_code", "sonnet")
    assert trail(decision) == [("codex", "gpt-6-sol", "preference", "review_independence")]


@pytest.mark.parametrize(
    ("model", "effort", "code", "reason"),
    [
        ("gpt-6-mini", None, ErrorCode.ROUTE_UNDERSHOOT, "class_too_low"),
        ("gpt-6-sol", "max", ErrorCode.CAPABILITY_UNAVAILABLE, "effort_unsupported"),
    ],
)
def test_host_offer_absence_preserves_model_and_effort_rejections(
    model: str, effort: str | None, code: ErrorCode, reason: str
) -> None:
    adm = admit(facts(Operation.NEW_IMPLEMENTATION, task_min_class=IMP), ADMISSION_DEFAULTS)
    role_route = {"runtime": "codex", "model": model}
    if effort is not None:
        role_route["effort"] = effort
    cfg = dataclasses.replace(CFG, preference=(), role_routing={RoleId.EXECUTOR: role_route})
    installs = {"codex": install("codex")}
    req = unrouted(adm, host_id=HOST)

    with pytest.raises(CapabilityUnavailable) as caught:
        route(req, cfg, CATALOG, CAPS, installs, frozenset(CAPS), host=HostRouting(frozenset()))

    assert caught.value.code is code
    assert listed(caught.value) == [("codex", model, "role_routing", reason)]
