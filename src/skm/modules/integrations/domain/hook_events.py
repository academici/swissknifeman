"""P00 declarations; behavior is implemented by the owning leaf."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .target import TargetId


class HookSurfaceId(StrEnum):
    GIT_GUARDRAILS = "lifecycle.git_guardrails"
    SAFE_DIRS = "security.safe_dirs"
    PLAN_GUARD = "lifecycle.plan_guard"
    PACK_GUARD = "lifecycle.pack_guard"
    CHANGELOG_GATE = "lifecycle.changelog_gate"
    REVIEW_GATE = "lifecycle.review_gate"
    COMMAND_LOG = "lifecycle.command_log"
    SESSION_CONTEXT = "context.session_start"
    RUN_REPORT = "lifecycle.run_report"
    SUBSCRIPTIONS = "custom.subscriptions"


class HookClass(StrEnum):
    ENFORCEMENT = "enforcement"
    WORKFLOW = "workflow"
    OBSERVATION = "observation"


class HookEventKind(StrEnum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    USER_PROMPT = "user_prompt"
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    PRE_SHELL = "pre_shell"
    POST_SHELL = "post_shell"
    SUBAGENT_STOP = "subagent_stop"
    STOP = "stop"
    PERMISSION_REQUEST = "permission_request"


@dataclass(frozen=True, slots=True)
class NormalizedHookEvent:
    target: TargetId
    kind: HookEventKind
    session_id: str | None
    cwd: str
    tool_name: str | None
    command: str | None
    paths: tuple[str, ...]
    prompt: str | None
    stop_status: str | None
    raw_event_name: str
