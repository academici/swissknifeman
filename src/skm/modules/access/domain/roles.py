"""Roles and the role -> permission catalogue (access §4.3, spec/00 §5).

``ROLE_PERMISSIONS`` is a verbatim copy of the permission table; ``tests/unit/access/domain/test_roles.py``
parses the table and compares, so the data cannot drift. The restriction sets below are used by ``decide`` and
``can_grant``; they never grant anything by themselves.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from skm.kernel.scopes import ScopeKind

__all__ = [
    "ASSIGNMENT_TOKEN_DENIED",
    "HOST_MEMBER_PERMISSIONS",
    "HOST_WORKER_PERMISSIONS",
    "KNOWN_PERMISSIONS",
    "MEMBER_CONFIG_LEVELS",
    "NON_GRANTABLE_BY_TOKEN",
    "ROLE_PERMISSIONS",
    "ROLE_RANK",
    "SELF_PERMISSIONS",
    "SYSTEM_PERMISSIONS",
    "WORKER_SCOPE_KINDS",
    "Role",
    "role_permissions",
]


class Role(StrEnum):
    OWNER = "owner"
    MAINTAINER = "maintainer"
    MEMBER = "member"
    VIEWER = "viewer"
    WORKER = "worker"


ROLE_CLASSIFICATION_CEILINGS: Final[Mapping[Role, str]] = MappingProxyType(
    {
        Role.OWNER: "restricted",
        Role.MAINTAINER: "restricted",
        Role.MEMBER: "confidential",
        Role.VIEWER: "internal",
    }
)


_ROLE_RANK = {Role.OWNER: 50, Role.MAINTAINER: 40, Role.MEMBER: 30, Role.VIEWER: 20, Role.WORKER: 0}
_ROLE_PERMISSIONS = {
    Role.OWNER: frozenset(
        [
            "principal.manage",
            "membership.manage",
            "token.own",
            "token.any",
            "config.read",
            "config.write",
            "config.write_shared",
            "config.lock",
            "workspace.create",
            "workspace.read",
            "workspace.manage",
            "project.create",
            "project.read",
            "project.manage",
            "repo.manage",
            "host.manage",
            "checkout.bind",
            "checkout.read_locator",
            "worker.register",
            "file.read",
            "file.write",
            "ext.read",
            "ext.install",
            "policy.read",
            "intent.approve",
            "runtime.read",
            "runtime.manage",
            "plan.read",
            "plan.create",
            "plan.edit",
            "plan.publish",
            "plan.approve",
            "plan.archive",
            "context.assemble",
            "context.read",
            "context.research",
            "run.read",
            "run.start",
            "run.control",
            "inbox.read",
            "inbox.answer",
            "check.verdict",
            "deviation.accept",
            "integration.read",
            "integration.apply",
            "hook.manage",
            "memory.read",
            "memory.write",
            "lesson.read",
            "lesson.curate",
            "export.run",
            "admin.storage",
            "admin.events",
        ]
    ),
    Role.MAINTAINER: frozenset(
        [
            "membership.manage",
            "token.own",
            "token.any",
            "config.read",
            "config.write",
            "config.write_shared",
            "workspace.read",
            "workspace.manage",
            "project.create",
            "project.read",
            "project.manage",
            "repo.manage",
            "checkout.bind",
            "checkout.read_locator",
            "worker.register",
            "file.read",
            "file.write",
            "ext.read",
            "ext.install",
            "policy.read",
            "intent.approve",
            "runtime.read",
            "runtime.manage",
            "plan.read",
            "plan.create",
            "plan.edit",
            "plan.publish",
            "plan.approve",
            "plan.archive",
            "context.assemble",
            "context.read",
            "context.research",
            "run.read",
            "run.start",
            "run.control",
            "inbox.read",
            "inbox.answer",
            "check.verdict",
            "deviation.accept",
            "integration.read",
            "integration.apply",
            "hook.manage",
            "memory.read",
            "memory.write",
            "lesson.read",
            "lesson.curate",
            "export.run",
        ]
    ),
    Role.MEMBER: frozenset(
        [
            "token.own",
            "config.read",
            "config.write",
            "workspace.read",
            "project.read",
            "checkout.bind",
            "checkout.read_locator",
            "file.read",
            "file.write",
            "ext.read",
            "policy.read",
            "runtime.read",
            "plan.read",
            "plan.create",
            "plan.edit",
            "plan.publish",
            "context.assemble",
            "context.read",
            "context.research",
            "run.read",
            "run.start",
            "run.control",
            "inbox.read",
            "inbox.answer",
            "check.verdict",
            "integration.read",
            "integration.apply",
            "memory.read",
            "memory.write",
            "lesson.read",
            "export.run",
        ]
    ),
    Role.VIEWER: frozenset(
        [
            "token.own",
            "config.read",
            "workspace.read",
            "project.read",
            "file.read",
            "ext.read",
            "policy.read",
            "runtime.read",
            "plan.read",
            "context.read",
            "run.read",
            "inbox.read",
            "integration.read",
            "memory.read",
            "lesson.read",
        ]
    ),
    Role.WORKER: frozenset(
        [
            "token.own",
            "config.read",
            "workspace.read",
            "project.read",
            "checkout.read_locator",
            "file.read",
            "file.write",
            "ext.read",
            "policy.read",
            "runtime.read",
            "runtime.manage",
            "plan.read",
            "context.read",
            "context.research",
            "run.read",
            "worker.claim",
            "step.note",
            "memory.read",
            "memory.write",
            "lesson.read",
            "export.run",
        ]
    ),
}

ROLE_RANK: Final[Mapping[Role, int]] = MappingProxyType(_ROLE_RANK)
ROLE_PERMISSIONS: Final[Mapping[Role, frozenset[str]]] = MappingProxyType(_ROLE_PERMISSIONS)

# ``config.write`` obtained only through the ``member`` role applies to these target scope kinds (footnote 1).
MEMBER_CONFIG_LEVELS: Final = frozenset({ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN})
# The ``worker`` role acts only from workspace level down; a worker membership on the instance grants nothing.
WORKER_SCOPE_KINDS: Final = frozenset({ScopeKind.WORKSPACE, ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN})
# No role carries these; only the canonical SYSTEM_ACTOR holds them (spec/00 §4.0.2, access §13). access §4.3
# lists ``system.bootstrap`` only, but §13 and spec/00 give ``system.internal`` to the same single bearer.
SYSTEM_PERMISSIONS: Final = frozenset({"system.bootstrap", "system.internal"})
# A token created with explicit ``permissions`` cannot include these unless the creator owns the instance.
NON_GRANTABLE_BY_TOKEN: Final = (
    frozenset({"principal.manage", "membership.manage", "token.any", "config.lock"}) | SYSTEM_PERMISSIONS
)
# Owning one's own tokens needs no membership (§4.4 row 5c); the handler checks which token is owned.
SELF_PERMISSIONS: Final = frozenset({"token.own"})
# Worker principal registered on host H holds these on ``host:H`` without membership (§4.4 row 6a).
HOST_WORKER_PERMISSIONS: Final = frozenset(
    {"workspace.read", "config.read", "runtime.read", "runtime.manage", "worker.claim"}
)
# Human/service with a membership on any workspace read the shared hosts (§4.4 row 6b); never write.
HOST_MEMBER_PERMISSIONS: Final = frozenset({"workspace.read", "config.read", "runtime.read"})
# An assignment token never authorizes the worker protocol, even if its permissions list it (§4.4 row 5a).
ASSIGNMENT_TOKEN_DENIED: Final = frozenset({"worker.claim"})

# Every permission the domain can decide about; the registry ``access/permissions.py`` must equal it (tested).
KNOWN_PERMISSIONS: Final = frozenset[str]().union(
    *_ROLE_PERMISSIONS.values(), SELF_PERMISSIONS, SYSTEM_PERMISSIONS
)


def role_permissions(role: Role) -> frozenset[str]:
    return ROLE_PERMISSIONS[Role(role)]
