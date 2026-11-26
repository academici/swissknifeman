"""Operation table rules, task authority and path facts (policy §§4.3, 5.3 ``evaluate_operation``).

A profile row becomes an ``OperationRule``; ``narrow_rule`` never yields a milder rule (deny OR, requirements
and capabilities union, warn OR, risk max). ``evaluate_operation`` applies the strict order of §5.3: deny,
intent, task authority, capabilities, ask, warn. Task authority only satisfies a ``task_authority`` row; no
authority lifts ``deny``.
"""

from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from .paths import PathRule, PathScope, ScopedPath
from .tool_intent import RiskClass

__all__ = [
    "INTERACTIVE_AUTHORITY_DELETE_SCOPE",
    "RISK_ORDER",
    "AccessCapability",
    "OperationDecision",
    "OperationHit",
    "OperationName",
    "OperationOutcome",
    "OperationRule",
    "PathFacts",
    "PathOrigin",
    "Requirement",
    "StaticPathFacts",
    "TaskAuthority",
    "evaluate_operation",
    "narrow_rule",
    "rule_from_decision",
]


class OperationName(StrEnum):
    MODIFY_WRITE_SET = "modify_write_set"
    MODIFY_OUTSIDE_WRITE_SET = "modify_outside_write_set"
    DELETE_TRACKED = "delete_tracked"
    DELETE_OWN_UNTRACKED = "delete_own_untracked"
    DELETE_FOREIGN_UNTRACKED = "delete_foreign_untracked"
    MODIFY_GIT_DIR = "modify_git_dir"
    GIT_DISCARD = "git_discard"
    GIT_PUSH = "git_push"
    GIT_FORCE_PUSH = "git_force_push"
    FORGE_WRITE = "forge_write"
    RELEASE_PUBLISH = "release_publish"
    SECRETS_ACCESS = "secrets_access"
    DOCKER_SOCKET = "docker_socket"
    EXTERNAL_SERVICES = "external_services"


class OperationDecision(StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    ASK = "ask"
    TASK_AUTHORITY = "task_authority"
    CAPABILITY = "capability"
    INTENT = "intent"
    DENY = "deny"


class Requirement(StrEnum):
    ASK = "ask"
    TASK_AUTHORITY = "task_authority"
    INTENT = "intent"


class AccessCapability(StrEnum):
    SECRETS = "secrets"
    DOCKER_SOCKET = "docker_socket"
    EXTERNAL_SERVICES = "external_services"


class PathOrigin(StrEnum):
    TRACKED = "tracked"
    OWN_UNTRACKED = "own_untracked"
    FOREIGN_UNTRACKED = "foreign_untracked"
    IGNORED = "ignored"
    ABSENT = "absent"
    GIT_INTERNAL = "git_internal"


RISK_ORDER: dict[RiskClass, int] = {
    RiskClass.LOW: 0,
    RiskClass.MEDIUM: 1,
    RiskClass.HIGH: 2,
    RiskClass.CRITICAL: 3,
}


@dataclass(frozen=True, slots=True)
class OperationRule:
    deny: bool = False
    requires: frozenset[Requirement] = frozenset()
    capabilities: frozenset[AccessCapability] = frozenset()
    warn: bool = False
    risk: RiskClass | None = None


def rule_from_decision(
    decision: OperationDecision, *, capability: AccessCapability | None = None, risk: RiskClass | None = None
) -> OperationRule:
    """One profile row (§4.3); ``capability`` is required exactly for the ``capability`` decision."""
    if (decision is OperationDecision.CAPABILITY) != (capability is not None):
        raise ValueError("capability is given exactly for the capability decision")
    rules = {
        OperationDecision.ALLOW: OperationRule(),
        OperationDecision.WARN: OperationRule(warn=True),
        OperationDecision.ASK: OperationRule(requires=frozenset({Requirement.ASK})),
        OperationDecision.TASK_AUTHORITY: OperationRule(requires=frozenset({Requirement.TASK_AUTHORITY})),
        OperationDecision.INTENT: OperationRule(requires=frozenset({Requirement.INTENT})),
        OperationDecision.DENY: OperationRule(deny=True),
    }
    base = OperationRule(capabilities=frozenset({capability})) if capability is not None else rules[decision]
    return OperationRule(base.deny, base.requires, base.capabilities, base.warn, risk)


def _max_risk(a: RiskClass | None, b: RiskClass | None) -> RiskClass | None:
    if a is None or b is None:
        return a if b is None else b
    return a if RISK_ORDER[a] >= RISK_ORDER[b] else b


def narrow_rule(a: OperationRule, b: OperationRule) -> OperationRule:
    """More conditions are never milder."""
    return OperationRule(
        deny=a.deny or b.deny,
        requires=a.requires | b.requires,
        capabilities=a.capabilities | b.capabilities,
        warn=a.warn or b.warn,
        risk=_max_risk(a.risk, b.risk),
    )


@dataclass(frozen=True, slots=True)
class TaskAuthority:
    write_scope: tuple[PathRule, ...] | None  # None: the task declared no write scope
    delete_scope: tuple[PathRule, ...]
    operations: frozenset[OperationName]
    capabilities: frozenset[AccessCapability]


# Interactive hooks: the human answers for their own checkout.
INTERACTIVE_AUTHORITY_DELETE_SCOPE = (PathRule(PathScope.WORKTREE, "**"),)


class PathFacts(Protocol):
    """Facts about checkout paths; ``adapters/git/path_facts.py`` on hosts, ``StaticPathFacts`` in tests."""

    def resolve(self, path: str, cwd: str) -> str: ...
    def origins(self, path: str) -> frozenset[PathOrigin]: ...
    def expand(self, pattern: str, cwd: str) -> tuple[str, ...] | None: ...


_UNKNOWN_ORIGINS = frozenset({PathOrigin.TRACKED, PathOrigin.FOREIGN_UNTRACKED})


@dataclass(frozen=True, slots=True)
class StaticPathFacts:
    """Observed facts as data (query §8 ``observed_origins``, tests); unknown paths fail closed."""

    origins_by_path: Mapping[str, frozenset[PathOrigin]] = field(
        default_factory=dict[str, frozenset[PathOrigin]]
    )
    links: Mapping[str, str] = field(default_factory=dict[str, str])  # symlink path → absolute target
    home: str | None = None
    max_glob_matches: int = 1000

    def resolve(self, path: str, cwd: str) -> str:
        if self.home is not None and (path == "~" or path.startswith("~/")):
            path = self.home + path[1:]
        joined = posixpath.normpath(posixpath.join(cwd or "/", path))
        for _ in range(40):
            for link, target in sorted(self.links.items(), key=lambda item: -len(item[0])):
                if joined == link or joined.startswith(link.rstrip("/") + "/"):
                    joined = posixpath.normpath(target + joined[len(link.rstrip("/")) :])
                    break
            else:
                return joined
        return joined

    def origins(self, path: str) -> frozenset[PathOrigin]:
        known = self.origins_by_path.get(path)
        if known is not None:
            return known
        below = [
            origins
            for name, origins in self.origins_by_path.items()
            if name.startswith(path.rstrip("/") + "/")
        ]
        if below:
            return frozenset[PathOrigin]().union(*below)
        return _UNKNOWN_ORIGINS

    def expand(self, pattern: str, cwd: str) -> tuple[str, ...] | None:
        absolute = posixpath.normpath(posixpath.join(cwd or "/", pattern))
        found = tuple(sorted(name for name in self.origins_by_path if fnmatch.fnmatchcase(name, absolute)))
        return None if len(found) > self.max_glob_matches else found


@dataclass(frozen=True, slots=True)
class OperationHit:
    operation: OperationName
    subject: str  # path, command or host the operation was found on
    detail: str  # the classifier row (K1..K14) and its evidence
    scoped: ScopedPath | None = None


@dataclass(frozen=True, slots=True)
class OperationOutcome:
    """``evaluate_operation`` result: ``allow`` (``warn`` set), ``ask`` or ``deny`` with its code."""

    outcome: str  # allow | ask | deny
    code: str = ""
    reason: str = ""
    warn: bool = False


def _in_delete_scope(hit: OperationHit, authority: TaskAuthority) -> bool:
    scoped = hit.scoped
    return scoped is not None and any(rule.matches(scoped) for rule in authority.delete_scope)


def evaluate_operation(rule: OperationRule, hit: OperationHit, authority: TaskAuthority) -> OperationOutcome:
    """The strict order of §5.3."""
    operation = hit.operation
    if rule.deny:
        return OperationOutcome("deny", "operation_denied", f"{operation} is denied by the profile")
    if Requirement.INTENT in rule.requires:
        return OperationOutcome("deny", "requires_intent", "external effect goes through a tool intent")
    if Requirement.TASK_AUTHORITY in rule.requires and not (
        operation in authority.operations
        or (operation is OperationName.DELETE_TRACKED and _in_delete_scope(hit, authority))
    ):
        return OperationOutcome("deny", "requires_task_authority", f"{operation} needs task authority")
    missing = rule.capabilities - authority.capabilities
    if missing:
        return OperationOutcome("deny", "capability_not_granted", ",".join(sorted(missing)))
    if Requirement.ASK in rule.requires:
        return OperationOutcome("ask", reason=f"{operation} asks the human")
    return OperationOutcome("allow", warn=rule.warn)
