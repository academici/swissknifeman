"""The seven role result contracts (execution §5.7-§5.8, C3), declared as data.

Each role has exactly one concrete result schema ``urn:skm:execution:role-result:<role>:v1``, one semantic
result kind (the donor ``result_shape``; the ``kind`` of ``heal``/``drift``), the stage type that runs it and
the most its tools may do (the donor ``tools``). An invalid result is repaired deterministically and then
retried by the **same** role with its schema errors; there is no ``report_fixer`` role. Granted permissions
still come from the agent profile's policy profile and layer, which may only stay within these ceilings;
network access and research IO belong to policy and the host, not to a role contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.workflow.definition import StageType

__all__ = [
    "ROLE_CONTRACTS",
    "FilesystemAccess",
    "ResultKind",
    "RoleContract",
    "RoleTools",
    "ShellAccess",
    "WriteAuthority",
    "result_schema_urn",
    "role_for_result_schema",
]


class ResultKind(StrEnum):
    CONTEXT_MAP = "context-map"
    STAGE_REPORT = "stage-report"
    REVIEW_FINDINGS = "review-findings"
    TRIAGE_RESULT = "triage-result"
    ADVICE = "advice"
    RESEARCH_RESULT = "research-result"
    REGISTRATION_RECEIPT = "registration-receipt"


class FilesystemAccess(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"


class ShellAccess(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    FULL = "full"


class WriteAuthority(StrEnum):
    NONE = "none"
    CODE_SCOPE = "code_scope"


@dataclass(frozen=True, slots=True)
class RoleTools:
    filesystem: FilesystemAccess
    shell: ShellAccess


@dataclass(frozen=True, slots=True)
class RoleContract:
    role: RoleId
    result_schema_urn: str
    result_kind: ResultKind
    stage_type: StageType
    tools: RoleTools
    write_authority: WriteAuthority


def result_schema_urn(role: RoleId) -> str:
    return f"urn:skm:execution:role-result:{role.value}:v1"


_READER: Final = RoleTools(FilesystemAccess.READ, ShellAccess.READ_ONLY)
_ROWS: Final = (
    (RoleId.SCOUT, ResultKind.CONTEXT_MAP, StageType.AGENT_STEP, _READER),
    (
        RoleId.EXECUTOR,
        ResultKind.STAGE_REPORT,
        StageType.AGENT_STEP,
        RoleTools(FilesystemAccess.WRITE, ShellAccess.FULL),
    ),
    (RoleId.REVIEWER, ResultKind.REVIEW_FINDINGS, StageType.AGENT_REVIEW, _READER),
    # Triage reproductions run read-only on the worker (rule TR, §5.8), not in the role's shell.
    (RoleId.TRIAGER, ResultKind.TRIAGE_RESULT, StageType.AGENT_STEP, _READER),
    (RoleId.ADVISOR, ResultKind.ADVICE, StageType.ADVISOR_CONSULT, _READER),
    # Research batches are fetched by the host; the role reads them and proposes follow-up queries.
    (
        RoleId.RESEARCHER,
        ResultKind.RESEARCH_RESULT,
        StageType.AGENT_STEP,
        RoleTools(FilesystemAccess.READ, ShellAccess.NONE),
    ),
    # Deterministic commit-message template by default (profile llm = false); no tools at all.
    (
        RoleId.REGISTRAR,
        ResultKind.REGISTRATION_RECEIPT,
        StageType.AGENT_STEP,
        RoleTools(FilesystemAccess.NONE, ShellAccess.NONE),
    ),
)

ROLE_CONTRACTS: Final[Mapping[RoleId, RoleContract]] = {
    role: RoleContract(
        role=role,
        result_schema_urn=result_schema_urn(role),
        result_kind=kind,
        stage_type=stage_type,
        tools=tools,
        write_authority=(
            WriteAuthority.CODE_SCOPE if tools.filesystem is FilesystemAccess.WRITE else WriteAuthority.NONE
        ),
    )
    for role, kind, stage_type, tools in _ROWS
}

_BY_SCHEMA: Final = {contract.result_schema_urn: role for role, contract in ROLE_CONTRACTS.items()}


def role_for_result_schema(urn: str) -> RoleId | None:
    """The role whose result schema is ``urn``; ``None`` for any other URN (no role reads foreign schemas)."""
    return _BY_SCHEMA.get(urn)
