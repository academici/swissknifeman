"""``policy.check_tool_call`` (policy §8): decide one tool call against the effective permissions of a scope.

The same pure ``check_tool_call`` the worker and the hook run, over the facts the caller observed
(``observed_origins``); a path without an observation is treated as ``{tracked, foreign_untracked}`` (fail
closed). The decision is advisory for the caller: the audit of decisions is a separate command.
"""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.application.commands import effective_for, layer_of
from skm.modules.policy.application.composition import builtin_profiles, task_authority_from
from skm.modules.policy.domain.calls import (
    FileDelete,
    FileEdit,
    FileRead,
    FileWrite,
    McpCall,
    RunCommand,
    ToolCall,
    WebAccess,
)
from skm.modules.policy.domain.operations import (
    INTERACTIVE_AUTHORITY_DELETE_SCOPE,
    PathOrigin,
    StaticPathFacts,
)
from skm.modules.policy.domain.paths import ScopeRoots
from skm.modules.policy.domain.tool_call import Allow, Ask, Deny, EnforcementMode, ToolDecision
from skm.modules.policy.domain.tool_call import check_tool_call as decide
from skm.modules.policy.generated import documents
from skm.modules.policy.generated.queries import CheckToolCall
from skm.modules.policy.generated.views import ToolDecisionView

__all__ = ["SPEC", "call_of", "handle", "roots_of", "view_of"]


def call_of(doc: documents.ToolCall) -> ToolCall:
    """The tool call document (``urn:skm:policy:tool-call:v1``) as the domain value."""
    match doc:
        case documents.ToolCallVariant1():
            return FileRead(doc.path)
        case documents.ToolCallVariant2():
            return FileWrite(doc.path)
        case documents.ToolCallVariant3():
            return FileEdit(doc.path)
        case documents.ToolCallVariant4():
            return FileDelete(doc.path)
        case documents.ToolCallVariant5():
            return RunCommand(doc.command, doc.cwd)
        case documents.ToolCallVariant6():
            return WebAccess("web.fetch", doc.url, None)
        case documents.ToolCallVariant7():
            return WebAccess("web.search", None, doc.query)
        case documents.ToolCallVariant8():
            return McpCall(doc.server, doc.tool)
    raise TypeError(f"unknown tool call document {type(doc).__name__}")


def roots_of(doc: documents.ScopeRoots) -> ScopeRoots:
    return ScopeRoots(
        worktrees=dict(doc.worktrees),
        materials=doc.materials,
        tmp=doc.tmp,
        home=doc.home,
        safe_dirs=tuple(doc.safe_dirs),
        protected=tuple(doc.protected),
        remote_hosts=frozenset(doc.remote_hosts),
    )


def view_of(decision: ToolDecision) -> ToolDecisionView:
    if isinstance(decision, Allow):
        return ToolDecisionView(
            outcome="warn" if decision.warnings else "allow",
            code=None,
            rule=None,
            reason="",
            warnings=tuple(decision.warnings),
            allowlisted=decision.allowlisted,
        )
    if isinstance(decision, Ask):
        return ToolDecisionView(
            outcome="ask",
            code=None,
            rule=decision.rule,
            reason=decision.reason,
            warnings=(),
            allowlisted=False,
        )
    assert isinstance(decision, Deny)  # noqa: S101 -- ToolDecision is Allow | Ask | Deny
    return ToolDecisionView(
        outcome="deny",
        code=decision.code,
        rule=decision.rule,
        reason=decision.reason,
        warnings=(),
        allowlisted=False,
    )


def handle(query: CheckToolCall, ctx: QueryContext, uow: UnitOfWork) -> ToolDecisionView:
    del uow  # the decision reads no repository
    perms = effective_for(
        ctx.config,
        profile_id=query.profile_id,
        role_layer=layer_of(query.role_layer, "role"),
        task_layer=layer_of(query.task_layer, "task"),
        interactive=query.interactive,
    )
    authority = task_authority_from(
        ctx.config,
        write_scope=None,
        delete_scope=INTERACTIVE_AUTHORITY_DELETE_SCOPE if query.interactive else (),
    )
    roots = roots_of(query.roots)
    facts = StaticPathFacts(
        origins_by_path={
            path: frozenset(PathOrigin(origin) for origin in origins)
            for path, origins in query.observed_origins.items()
        },
        home=roots.home,
    )
    decision = decide(
        perms,
        call_of(query.call),
        roots=roots,
        facts=facts,
        authority=authority,
        mode=EnforcementMode(query.mode),
        reference=builtin_profiles()["read-only"].permissions.commands,
    )
    return view_of(decision)


SPEC = QuerySpec(
    name="policy.check_tool_call",
    dto=CheckToolCall,
    result=ToolDecisionView,
    permission="policy.read",
    scope_of=lambda query: ScopeRef(ScopeKind.RUN, ScopeId(query.scope_id)),
    handler=handle,
)
