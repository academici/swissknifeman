"""G14 (policy §4.5): every operation row by every built-in profile, from ``data/operation-matrix.json``.

The profile files must agree with the matrix, ``evaluate_operation`` must give the expected outcome with an
empty and with a fully granted task authority, and the classifier must produce every operation of the table.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from skm.modules.policy.domain.calls import FileDelete, FileRead, FileWrite, RunCommand, ToolCall
from skm.modules.policy.domain.classify import classify
from skm.modules.policy.domain.operations import (
    AccessCapability,
    OperationDecision,
    OperationHit,
    OperationName,
    StaticPathFacts,
    TaskAuthority,
    evaluate_operation,
    rule_from_decision,
)
from skm.modules.policy.domain.paths import PathRule, PathScope, ScopedPath, ScopeRoots
from skm.modules.policy.domain.profiles import BUILTIN_PROFILE_IDS, PolicyProfile
from skm.modules.policy.domain.shell_words import simple_commands
from skm.modules.policy.domain.tool_intent import RiskClass

MATRIX: Mapping[str, Any] = json.loads(
    Path(__file__).with_name("data").joinpath("operation-matrix.json").read_text()
)
WT = "/w/attempt/repo"
GRANTED = TaskAuthority(
    write_scope=None,
    delete_scope=(PathRule(PathScope.WORKTREE, "**"),),
    operations=frozenset(OperationName),
    capabilities=frozenset(AccessCapability),
)
EMPTY = TaskAuthority(write_scope=None, delete_scope=(), operations=frozenset(), capabilities=frozenset())
CELLS = [(operation, profile) for operation in MATRIX["operations"] for profile in BUILTIN_PROFILE_IDS]

# one call per operation of §4.5 (authority: write scope src/** where the row needs it)
SAMPLES: dict[OperationName, ToolCall] = {
    OperationName.MODIFY_WRITE_SET: FileWrite(f"{WT}/src/new.py"),
    OperationName.MODIFY_OUTSIDE_WRITE_SET: FileWrite(f"{WT}/docs/x.md"),
    OperationName.DELETE_TRACKED: FileDelete(f"{WT}/src/app.py"),
    OperationName.DELETE_OWN_UNTRACKED: FileDelete(f"{WT}/build/out.o"),
    OperationName.DELETE_FOREIGN_UNTRACKED: FileDelete(f"{WT}/notes.txt"),
    OperationName.MODIFY_GIT_DIR: FileWrite(f"{WT}/.git/config"),
    OperationName.GIT_DISCARD: RunCommand("git reset --hard HEAD~1", WT),
    OperationName.GIT_PUSH: RunCommand("git push origin main", WT),
    OperationName.GIT_FORCE_PUSH: RunCommand("git push --force origin main", WT),
    OperationName.FORGE_WRITE: RunCommand("gh pr create --title t --body b", WT),
    OperationName.RELEASE_PUBLISH: RunCommand("twine upload dist/pkg.whl", WT),
    OperationName.SECRETS_ACCESS: FileRead("/home/dev/.ssh/id_rsa"),
    OperationName.DOCKER_SOCKET: RunCommand("docker ps", WT),
    OperationName.EXTERNAL_SERVICES: RunCommand("psql -h db.internal", WT),
}


def outcome(rule_profile: PolicyProfile, operation: OperationName, authority: TaskAuthority) -> str:
    hit = OperationHit(operation, "subject", "test", ScopedPath(PathScope.WORKTREE, "main", "src/app.py"))
    result = evaluate_operation(rule_profile.permissions.operations[operation], hit, authority)
    if result.outcome == "deny":
        return f"deny:{result.code}"
    if result.outcome == "allow" and result.warn:
        return "warn"
    return result.outcome


def test_matrix_covers_every_operation_and_profile() -> None:
    assert set(MATRIX["operations"]) == {item.value for item in OperationName}
    for row in MATRIX["operations"].values():
        assert set(row) == set(BUILTIN_PROFILE_IDS)
    assert set(MATRIX["network"]) == set(BUILTIN_PROFILE_IDS)


@pytest.mark.parametrize(("operation", "profile"), CELLS)
def test_profile_file_row_matches_matrix(
    profiles: Mapping[str, PolicyProfile], operation: str, profile: str
) -> None:
    cell = MATRIX["operations"][operation][profile]
    capability = cell.get("capability")
    expected = rule_from_decision(
        OperationDecision(cell["decision"]),
        capability=None if capability is None else AccessCapability(capability),
        risk=None if "risk" not in cell else RiskClass(cell["risk"]),
    )
    assert profiles[profile].permissions.operations[OperationName(operation)] == expected


@pytest.mark.parametrize(("operation", "profile"), CELLS)
def test_operation_outcome_with_empty_and_granted_authority(
    profiles: Mapping[str, PolicyProfile], operation: str, profile: str
) -> None:
    cell = MATRIX["operations"][operation][profile]
    name = OperationName(operation)
    assert outcome(profiles[profile], name, EMPTY) == cell["empty"]
    assert outcome(profiles[profile], name, GRANTED) == cell["granted"]


@pytest.mark.parametrize("profile", BUILTIN_PROFILE_IDS)
def test_network_row(profiles: Mapping[str, PolicyProfile], profile: str) -> None:
    assert profiles[profile].permissions.network.mode.value == MATRIX["network"][profile]


@pytest.mark.parametrize("operation", list(OperationName))
def test_every_operation_of_the_table_is_classified(
    roots: ScopeRoots, facts: StaticPathFacts, operation: OperationName
) -> None:
    call = SAMPLES[operation]
    authority = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**"),), (), frozenset(), frozenset())
    words = simple_commands(call.command) if isinstance(call, RunCommand) else None
    found = classify(call, roots=roots, facts=facts, authority=authority, words=words)
    assert operation in {hit.operation for hit in found.hits}


def test_delete_tracked_task_authority_is_limited_to_the_delete_scope(
    profiles: Mapping[str, PolicyProfile],
) -> None:
    rule = profiles["workspace-contained"].permissions.operations[OperationName.DELETE_TRACKED]
    scoped = TaskAuthority(None, (PathRule(PathScope.WORKTREE, "build/**"),), frozenset(), frozenset())
    inside = OperationHit(
        OperationName.DELETE_TRACKED, "x", "K4", ScopedPath(PathScope.WORKTREE, "main", "build/a.o")
    )
    outside = OperationHit(
        OperationName.DELETE_TRACKED, "x", "K4", ScopedPath(PathScope.WORKTREE, "main", "src/app.py")
    )
    assert evaluate_operation(rule, inside, scoped).outcome == "allow"
    assert evaluate_operation(rule, outside, scoped).code == "requires_task_authority"
