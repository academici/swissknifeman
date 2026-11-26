"""Admission of an operation before a runtime is chosen (runtimes §4.11; G6, S-23, S-24).

Admission decides **which requirements** a route of this operation of this task has; ``route`` (§4.10)
looks for a candidate under them. Every fact comes from execution (``OperationContext``/``AdmissionFacts``),
never from what a model claims about its own work. Admission does not decide the session:
``admission_allows_resume`` is a pure filter whose result execution passes to ``decide_session``
(execution §5.16, the only resume decider, RT-01).

Port and generalization of ``orch/conductor/policies/routing.py`` ``correction_refusal``, ``grown_paths`` and
``route_minimum``; closed provider literals of the donor are not carried over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed

from .capability import Capability
from .classes import MODEL_CLASS_ORDER, Effort, ModelClass, RoleId

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from skm.modules.runtimes.domain.capability import RuntimeCapabilities
    from skm.modules.runtimes.domain.ids import Digest, ModelId, RuntimeId, SessionRef

__all__ = [
    "ADMISSION_DEFAULTS",
    "OPERATION_ROLES",
    "Admission",
    "AdmissionFacts",
    "AdmissionNote",
    "AdmissionPolicy",
    "FixBounds",
    "FixBriefFacts",
    "Operation",
    "OperationContext",
    "PreviousRoute",
    "ResumeAllowance",
    "ResumePolicy",
    "admission_allows_resume",
    "admit",
    "classify_operation",
    "fix_within_bounds",
    "operations_of_role",
    "session_policy_for",
]


class Operation(StrEnum):
    NEW_IMPLEMENTATION = "new_implementation"
    CONTINUATION = "continuation"
    BOUNDED_FIX = "bounded_fix"
    SCOPE_CHANGE = "scope_change"
    REVIEW = "review"
    FINAL_CLOSE = "final_close"
    RESEARCH = "research"
    ADVICE = "advice"
    AUXILIARY = "auxiliary"


class ResumePolicy(StrEnum):
    NEVER = "never"
    PREFERRED = "preferred"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class OperationContext:
    role: RoleId
    stage_final: bool
    has_fix_brief: bool
    wip_present: bool
    contract_changed: bool


@dataclass(frozen=True, slots=True)
class PreviousRoute:
    runtime_id: RuntimeId
    model: ModelId
    model_class: ModelClass
    effort: Effort
    session_ref: SessionRef | None
    step_ref: str


@dataclass(frozen=True, slots=True)
class FixBriefFacts:
    items: int
    unconfirmed: int
    finding_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdmissionFacts:
    operation: Operation
    role: RoleId
    task_min_class: ModelClass | None
    task_min_effort: Effort | None
    started_by: PreviousRoute | None
    previous: PreviousRoute | None
    contract_digest: Digest
    previous_contract_digest: Digest | None
    fix_brief: FixBriefFacts | None
    previous_output_id: str | None


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """``ADMISSION_DEFAULTS`` narrowed by ``runtimes.admission.*``; a missing operation uses the default."""

    min_class: Mapping[Operation, ModelClass]
    resume: Mapping[Operation, ResumePolicy]
    bounded_fix_below_task_class: bool
    role_min_class: Mapping[RoleId, ModelClass]

    def __post_init__(self) -> None:
        # Coerce to the enums: a plain "never" must not slip past an identity check of ResumePolicy.NEVER.
        min_class = {Operation(op): ModelClass(cls) for op, cls in self.min_class.items()}
        resume = {Operation(op): ResumePolicy(value) for op, value in self.resume.items()}
        role_min = {RoleId(role): ModelClass(cls) for role, cls in self.role_min_class.items()}
        object.__setattr__(self, "min_class", MappingProxyType(min_class))
        object.__setattr__(self, "resume", MappingProxyType(resume))
        object.__setattr__(self, "role_min_class", MappingProxyType(role_min))


@dataclass(frozen=True, slots=True)
class AdmissionNote:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class Admission:
    requested: Operation
    operation: Operation
    min_class: ModelClass
    min_effort: Effort | None
    class_sources: tuple[str, ...]
    required_capabilities: frozenset[Capability]
    resume: ResumePolicy
    prefer_route: PreviousRoute | None
    notes: tuple[AdmissionNote, ...]


@dataclass(frozen=True, slots=True)
class FixBounds:
    within: bool
    grown: tuple[str, ...]


# The operation table of §4.11: roles, default floor and whether the task's route class applies.
OPERATION_ROLES: Mapping[Operation, frozenset[RoleId]] = MappingProxyType(
    {
        Operation.NEW_IMPLEMENTATION: frozenset({RoleId.EXECUTOR}),
        Operation.CONTINUATION: frozenset({RoleId.EXECUTOR}),
        Operation.BOUNDED_FIX: frozenset({RoleId.EXECUTOR}),
        Operation.SCOPE_CHANGE: frozenset({RoleId.EXECUTOR}),
        Operation.REVIEW: frozenset({RoleId.REVIEWER, RoleId.TRIAGER}),
        Operation.FINAL_CLOSE: frozenset({RoleId.REVIEWER}),
        Operation.RESEARCH: frozenset({RoleId.RESEARCHER, RoleId.SCOUT}),
        Operation.ADVICE: frozenset({RoleId.ADVISOR}),
        Operation.AUXILIARY: frozenset({RoleId.REGISTRAR}),
    }
)

_TASK_CLASS_APPLIES = frozenset(
    {
        Operation.NEW_IMPLEMENTATION,
        Operation.CONTINUATION,
        Operation.BOUNDED_FIX,  # unless bounded_fix_below_task_class
        Operation.SCOPE_CHANGE,
        Operation.FINAL_CLOSE,
    }
)

_NEEDS_OUTPUT = frozenset({Operation.REVIEW, Operation.FINAL_CLOSE})

ADMISSION_DEFAULTS = AdmissionPolicy(
    min_class={
        Operation.NEW_IMPLEMENTATION: ModelClass.IMPLEMENTATION,
        Operation.CONTINUATION: ModelClass.IMPLEMENTATION,
        Operation.BOUNDED_FIX: ModelClass.IMPLEMENTATION,
        Operation.SCOPE_CHANGE: ModelClass.IMPLEMENTATION,
        Operation.REVIEW: ModelClass.IMPLEMENTATION,
        Operation.FINAL_CLOSE: ModelClass.IMPLEMENTATION,
        Operation.RESEARCH: ModelClass.ECONOMY,
        Operation.ADVICE: ModelClass.IMPLEMENTATION,
        Operation.AUXILIARY: ModelClass.ECONOMY,
    },
    resume={
        Operation.NEW_IMPLEMENTATION: ResumePolicy.NEVER,
        Operation.CONTINUATION: ResumePolicy.PREFERRED,
        Operation.BOUNDED_FIX: ResumePolicy.PREFERRED,
        Operation.SCOPE_CHANGE: ResumePolicy.NEVER,  # the old session saw the old contract
        Operation.REVIEW: ResumePolicy.NEVER,
        Operation.FINAL_CLOSE: ResumePolicy.NEVER,
        Operation.RESEARCH: ResumePolicy.NEVER,
        Operation.ADVICE: ResumePolicy.NEVER,
        Operation.AUXILIARY: ResumePolicy.NEVER,
    },
    bounded_fix_below_task_class=False,
    role_min_class={},
)


_ROLE_OPERATION: Mapping[RoleId, Operation] = MappingProxyType(
    {
        RoleId.TRIAGER: Operation.REVIEW,
        RoleId.RESEARCHER: Operation.RESEARCH,
        RoleId.SCOUT: Operation.RESEARCH,
        RoleId.ADVISOR: Operation.ADVICE,
        RoleId.REGISTRAR: Operation.AUXILIARY,
    }
)


def classify_operation(ctx: OperationContext) -> Operation:
    """Rule 1 of §4.11, in order; the inputs are execution facts, not model statements."""
    role = RoleId(ctx.role)
    if role is RoleId.REVIEWER:
        return Operation.FINAL_CLOSE if ctx.stage_final else Operation.REVIEW
    if role is not RoleId.EXECUTOR:
        return _ROLE_OPERATION[role]
    if ctx.contract_changed:
        return Operation.SCOPE_CHANGE
    if ctx.has_fix_brief:
        return Operation.BOUNDED_FIX
    if ctx.wip_present:
        return Operation.CONTINUATION
    return Operation.NEW_IMPLEMENTATION


def operations_of_role(role: RoleId) -> frozenset[Operation]:
    """Every operation ``classify_operation`` can give the role (the "Роли" column of the table)."""
    return frozenset(
        classify_operation(OperationContext(role, *flags)) for flags in product((False, True), repeat=4)
    )


def _refused(facts: AdmissionFacts, reason: str, message: str) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.ADMISSION_REFUSED,
        message,
        details={"role": facts.role.value, "operation": facts.operation.value, "reason": reason},
    )


def _contract_changed(facts: AdmissionFacts) -> bool:
    previous = facts.previous_contract_digest
    return previous is not None and previous != facts.contract_digest


def _escalation(facts: AdmissionFacts) -> tuple[Operation, str] | None:
    """The first unmet condition of the operation's table row, as ``(target, condition)``.

    The conditions are checked in the order of the row; a changed contract always wins, because it makes the
    old work (WIP, output, findings) a basis for another contract. A prior work whose contract digest is
    unknown cannot prove that the contract is unchanged and escalates like a changed one (fail closed).
    """
    if facts.operation not in (Operation.CONTINUATION, Operation.BOUNDED_FIX):
        return None
    if _contract_changed(facts):
        return Operation.SCOPE_CHANGE, "contract_changed"
    if facts.operation is Operation.CONTINUATION:
        unmet = None if facts.started_by is not None else "no_wip"
    else:
        brief = facts.fix_brief
        if brief is None or brief.items <= 0:
            unmet = "no_fix_brief"
        elif brief.unconfirmed != 0:
            unmet = "findings_unconfirmed"
        elif facts.previous_output_id is None:
            unmet = "no_previous_output"
        else:
            unmet = None
    if unmet is not None:
        return Operation.NEW_IMPLEMENTATION, unmet
    if facts.previous_contract_digest is None:
        return Operation.SCOPE_CHANGE, "contract_changed"
    return None


def _task_class_applies(op: Operation, policy: AdmissionPolicy) -> bool:
    if op is Operation.BOUNDED_FIX:
        return not policy.bounded_fix_below_task_class
    return op in _TASK_CLASS_APPLIES


def _max_class(classes: Iterable[ModelClass]) -> ModelClass:
    return max(classes, key=MODEL_CLASS_ORDER.index)


def admit(facts: AdmissionFacts, policy: AdmissionPolicy) -> Admission:
    """Rule 2 of §4.11: escalate once by the table, then raise the floor; refusal is ``ADMISSION_REFUSED``."""
    requested = facts.operation
    if facts.role not in OPERATION_ROLES[requested]:
        raise _refused(
            facts,
            "operation_not_for_role",
            f"operation {requested.value} is not admitted for role {facts.role.value}",
        )
    if requested in _NEEDS_OUTPUT and facts.previous_output_id is None:
        raise _refused(facts, "no_output", f"{requested.value} needs an output of the attempt to review")
    notes: list[AdmissionNote] = []
    op = requested
    escalation = _escalation(facts)
    if escalation is not None:  # the target rows have no conditions: an escalation never repeats
        op, condition = escalation
        notes.append(AdmissionNote(f"escalated:{condition}", f"{requested.value}→{op.value}"))

    configured = policy.min_class.get(op, ADMISSION_DEFAULTS.min_class[op])
    floors: list[tuple[str, ModelClass]] = [
        ("op_default" if configured == ADMISSION_DEFAULTS.min_class[op] else "config", configured)
    ]
    task_applies = _task_class_applies(op, policy)
    if task_applies and facts.task_min_class is not None:
        floors.append(("task", facts.task_min_class))
    if op is Operation.CONTINUATION and facts.started_by is not None:
        floors.append(("started_by", facts.started_by.model_class))  # S-23: never cheaper than its start
    role_min = policy.role_min_class.get(facts.role)
    if role_min is not None:
        floors.append(("role_min", role_min))
    min_class = _max_class(cls for _, cls in floors)

    resume = policy.resume.get(op, ADMISSION_DEFAULTS.resume[op])
    previous = facts.previous
    prefer_route = (
        previous
        if resume is not ResumePolicy.NEVER and previous is not None and previous.session_ref is not None
        else None
    )
    return Admission(
        requested=requested,
        operation=op,
        min_class=min_class,
        min_effort=facts.task_min_effort if task_applies else None,
        class_sources=tuple(source for source, cls in floors if cls == min_class),
        required_capabilities=(
            frozenset({Capability.SESSION_RESUME}) if resume is ResumePolicy.REQUIRED else frozenset()
        ),
        resume=resume,
        prefer_route=prefer_route,
        notes=tuple(notes),
    )


@dataclass(frozen=True, slots=True)
class ResumeAllowance:
    allowed: bool
    required: bool
    session_ref: SessionRef | None
    reason: Literal[
        "allowed", "resume_disabled", "no_previous_session", "route_changed", "resume_not_supported"
    ]


def admission_allows_resume(
    admission: Admission, runtime_id: RuntimeId, model: ModelId, caps: RuntimeCapabilities
) -> ResumeAllowance:
    """Rule 3 of §4.11: may the chosen route resume at all? A filter, not the session decision.

    ``caps`` are the effective capabilities of ``runtime_id``: an ``unknown`` ``session_resume`` (unverified)
    never allows a resume, whatever ``runtimes.degraded.allow`` says.
    """
    if caps.runtime_id != runtime_id:
        raise ValueError(f"capabilities of {caps.runtime_id} given for route {runtime_id}")
    required = admission.resume == ResumePolicy.REQUIRED
    prefer = admission.prefer_route
    reason: Literal["resume_disabled", "no_previous_session", "route_changed", "resume_not_supported"]
    if admission.resume != ResumePolicy.PREFERRED and not required:  # never, or not a resume policy at all
        reason = "resume_disabled"
    elif prefer is None or prefer.session_ref is None:
        reason = "no_previous_session"
    elif (prefer.runtime_id, prefer.model) != (runtime_id, model):
        reason = "route_changed"
    elif not caps.supports(Capability.SESSION_RESUME):
        reason = "resume_not_supported"
    else:
        return ResumeAllowance(
            allowed=True, required=required, session_ref=prefer.session_ref, reason="allowed"
        )
    return ResumeAllowance(allowed=False, required=required, session_ref=None, reason=reason)


def session_policy_for(
    role: RoleId, policy: AdmissionPolicy, *, resume_mode: Literal["auto", "never"]
) -> Literal["ephemeral", "persistent"]:
    """Rule 3a of §4.11: keep the client session only when a next step of the role may resume it."""
    if resume_mode != "auto":
        return "ephemeral"
    resumable = any(
        policy.resume.get(op, ADMISSION_DEFAULTS.resume[op]) is not ResumePolicy.NEVER
        for op in operations_of_role(role)
    )
    return "persistent" if resumable else "ephemeral"


_DRIVE = re.compile(r"[A-Za-z]:")


def _normal(path: str) -> str | None:
    """A repository-relative POSIX path without ``.``/``..`` segments; anything else is ``None``."""
    if not path or path.startswith(("/", "~")) or _DRIVE.match(path) or "\\" in path or "\x00" in path:
        return None
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _segments_match(parts: Sequence[str], pattern: Sequence[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_segments_match(parts[index:], rest) for index in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _segments_match(parts[1:], rest)


def _matches(path: str, pattern: str) -> bool:
    """``*``/``?``/``[..]`` stay inside one segment, ``**`` spans any number of them; a plain path or a
    trailing ``/`` names the path itself and everything under it."""
    directory = pattern.endswith("/")
    normal = _normal(pattern)
    if normal is None:
        return False
    if directory or not any(char in normal for char in "*?["):
        return path == normal or path.startswith(normal + "/")
    return _segments_match(path.split("/"), normal.split("/"))


def _extra_matches(path: str, pattern: str) -> bool:
    """An allowed extra path: a plain entry names exactly that path (``grown_paths`` compares
    ``path == "CHANGELOG.md"``); only an explicit glob such as ``docs/**`` reaches below it."""
    normal = _normal(pattern)
    if normal is None:
        return False
    if not any(char in normal for char in "*?["):
        return path == normal
    return _segments_match(path.split("/"), normal.split("/"))


def fix_within_bounds(
    changed: Sequence[str],
    finding_paths: Sequence[str],
    write_scope: Sequence[str],
    allowed_extra: Sequence[str],
    test_globs: Sequence[str],
) -> FixBounds:
    """Rule 5 of §4.11 (port of ``grown_paths``): did a bounded fix stay inside its validated fix brief?

    A path is allowed when it is a finding path, a test path inside the write scope, or an allowed extra path
    (a plain extra entry matches only itself, a glob extra entry its matches). A path that is not
    repository-relative (absolute, ``..``) is never allowed. ``grown`` is sorted.
    """
    findings = {normal for normal in map(_normal, finding_paths) if normal is not None}
    grown: set[str] = set()
    for raw in changed:
        path = _normal(raw)
        allowed = path is not None and (
            path in findings
            or (
                any(_matches(path, glob) for glob in test_globs)
                and any(_matches(path, scope) for scope in write_scope)
            )
            or any(_extra_matches(path, extra) for extra in allowed_extra)
        )
        if not allowed:
            grown.add(raw)
    return FixBounds(within=not grown, grown=tuple(sorted(grown)))
