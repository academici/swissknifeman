"""Pure built-in hook decisions (integrations §5.5)."""

from __future__ import annotations

import fnmatch
import posixpath
import shlex
from dataclasses import dataclass
from enum import StrEnum

from .hook_events import HookEventKind, HookSurfaceId, NormalizedHookEvent


class HookMode(StrEnum):
    OFF = "off"
    WARN = "warn"
    STRICT = "strict"


class HookVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    CONTEXT = "context"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class HookDecision:
    verdict: HookVerdict
    surface: HookSurfaceId
    reason_code: str | None
    user_message: str | None
    agent_message: str | None
    additional_context: str | None


ENFORCEMENT = frozenset(
    {
        HookSurfaceId.GIT_GUARDRAILS,
        HookSurfaceId.SAFE_DIRS,
        HookSurfaceId.PLAN_GUARD,
        HookSurfaceId.PACK_GUARD,
        HookSurfaceId.CHANGELOG_GATE,
    }
)


@dataclass(frozen=True, slots=True)
class HookPolicyContext:
    root: str = "/"
    reserved_paths: tuple[str, ...] = (".skm/**",)
    managed_file_paths: frozenset[str] = frozenset()
    staged_paths: tuple[str, ...] = ()
    code_globs: tuple[str, ...] = ("**",)
    changelog_paths: tuple[str, ...] = ("CHANGELOG.md",)
    skip_marker: str = "[changelog-skip]"
    review_fresh: bool = False
    open_blockers: bool = False
    session_context: str = ""
    review_context: str = ""
    git_violation: bool = False
    git_reason: str = "GIT_GUARDRAILS"
    git_message: str = "Unsafe Git operation blocked by project policy."
    safe_verdict: str = "none"
    safe_reason: str | None = None
    safe_message: str | None = None
    managed_path: str | None = None
    changelog_required: bool = False
    commit_text: str | None = None


def commit_message(command: str) -> str | None:
    """Recognize shell words before interpreting Git, including adjacent quoted fragments."""
    words = _commit_words(command)
    if words is None:
        return None
    messages: list[str] = []
    remaining = iter(words)
    for word in remaining:
        if word in {"-m", "--message"}:
            messages.append(next(remaining, ""))
        elif word.startswith("--message="):
            messages.append(word.partition("=")[2])
        elif word.startswith("-m") and len(word) > 2:
            messages.append(word[2:])
    return "\n\n".join(messages)


def _commit_words(command: str, depth: int = 0) -> tuple[str, ...] | None:
    if depth > 6:
        return None
    try:
        lexer = shlex.shlex(command.replace("\\\n", ""), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return () if "git" in command and "commit" in command else None
    segment = 0
    for index, word in enumerate(words):
        if word in {";", "&&", "||", "|", "&", "(", ")"}:
            segment = index + 1
        if words[segment : segment + 1] in (["echo"], ["printf"]):
            continue
        if (
            word == "-c"
            and index + 1 < len(words)
            and posixpath.basename(words[segment]) in {"sh", "bash", "zsh"}
        ):
            nested = _commit_words(words[index + 1], depth + 1)
            if nested is not None:
                return nested
        if posixpath.basename(word) != "git":
            continue
        cursor = index + 1
        while cursor < len(words) and words[cursor].startswith("-"):
            cursor += (
                2
                if words[cursor] in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
                else 1
            )
        if cursor < len(words) and words[cursor] == "commit":
            end = next(
                (i for i in range(cursor + 1, len(words)) if words[i] in {";", "&&", "||", "|", "&"}),
                len(words),
            )
            return tuple(words[cursor + 1 : end])
    return None


_LARAVEL_DESTRUCTIVE = frozenset({"migrate:fresh", "migrate:refresh", "db:wipe"})
_SAFE_REASONS = {
    "HOOK_COMMAND_INVALID": "Unable to safely interpret the shell command.",
    "HOOK_PATH_INVALID": "Unable to verify the edit path in the bound checkout.",
    "ENV_FILE_PROTECTED": "The .env file is protected. Use .env.example for templates.",
    "LARAVEL_DB_GUARD": "Destructive Laravel database resets are blocked.",
}


def protected_env_path(path: str) -> bool:
    return any(
        part != ".env.example" and (part == ".env" or part.startswith(".env.")) for part in path.split("/")
    )


def safe_shell_words(command: str) -> tuple[str, ...]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    words = tuple(lexer)
    if not words or "\0" in command:
        raise ValueError("unparseable command")
    return words


def safe_dirs_violation(paths: tuple[str, ...], words: tuple[str, ...]) -> tuple[str, str] | None:
    if any(protected_env_path(path) for path in paths):
        code = "ENV_FILE_PROTECTED"
    elif any(posixpath.basename(word) == "artisan" for word in words) and _LARAVEL_DESTRUCTIVE.intersection(
        words
    ):
        code = "LARAVEL_DB_GUARD"
    else:
        return None
    return code, _SAFE_REASONS[code]


def failure_decision(
    surface: HookSurfaceId, mode: HookMode, reason: str, *, commit: bool = False, detail: str | None = None
) -> HookDecision:
    enforcement = surface in ENFORCEMENT or (
        surface is HookSurfaceId.REVIEW_GATE and commit and mode is HookMode.STRICT
    )
    # Without policy, enforcement always fails closed, including a cached mode=off.
    verdict = HookVerdict.DENY if enforcement else HookVerdict.NONE
    if surface is HookSurfaceId.REVIEW_GATE and commit and mode is HookMode.WARN:
        verdict = HookVerdict.CONTEXT
    message = f"skm hook: {reason}" if detail is None else f"skm hook: {reason} ({detail})"
    return HookDecision(
        verdict, surface, reason, message, message, message if verdict is HookVerdict.CONTEXT else None
    )


def evaluate_hook(  # noqa: PLR0911 - one rule per built-in surface
    event: NormalizedHookEvent, surface: HookSurfaceId, mode: HookMode, ctx: HookPolicyContext
) -> HookDecision:
    def decision(
        code: str | None = None,
        text: str | None = None,
        *,
        context: bool = False,
        strict: bool = False,
    ) -> HookDecision:
        verdict = HookVerdict.NONE
        if text:
            verdict = (
                HookVerdict.CONTEXT if context or (mode is HookMode.WARN and not strict) else HookVerdict.DENY
            )
        return HookDecision(
            verdict, surface, code, text, text, text if verdict is HookVerdict.CONTEXT else None
        )

    if mode is HookMode.OFF:
        return decision()
    command = event.command or ""
    shell = event.kind is HookEventKind.PRE_SHELL
    message = (ctx.commit_text if ctx.commit_text is not None else commit_message(command)) if shell else None
    if surface is HookSurfaceId.GIT_GUARDRAILS and shell:
        if ctx.git_violation:
            return decision(ctx.git_reason, ctx.git_message)
    elif surface is HookSurfaceId.SAFE_DIRS and (shell or event.kind is HookEventKind.PRE_TOOL):
        if ctx.safe_verdict == "deny":
            text = ctx.safe_message or _SAFE_REASONS.get(
                ctx.safe_reason or "", "Operation denied by project policy."
            )
            return decision(
                ctx.safe_reason, text, strict=ctx.safe_reason in {"HOOK_COMMAND_INVALID", "HOOK_PATH_INVALID"}
            )
        if ctx.safe_verdict == "ask":
            return HookDecision(
                HookVerdict.ASK,
                surface,
                None,
                "Command requires approval.",
                "Command requires approval.",
                None,
            )
    elif surface in {HookSurfaceId.PLAN_GUARD, HookSurfaceId.PACK_GUARD} and (
        shell or event.kind is HookEventKind.PRE_TOOL
    ):
        if ctx.managed_path:
            return decision("MANAGED_FILE", "Edit the source, then run skm integrations apply.")
    elif surface is HookSurfaceId.CHANGELOG_GATE and message is not None:
        changed = set(ctx.staged_paths)
        code = any(fnmatch.fnmatchcase(path, glob) for path in changed for glob in ctx.code_globs)
        if (
            code
            and not changed.intersection(ctx.changelog_paths)
            and ctx.skip_marker not in message
            and ctx.changelog_required
        ):
            return decision("CHANGELOG_REQUIRED", "Stage a changelog entry before committing.")
    elif surface is HookSurfaceId.REVIEW_GATE:
        if message is not None and (not ctx.review_fresh or ctx.open_blockers):
            return decision("REVIEW_RECEIPT_STALE", "Review receipt is missing, stale, or has open blockers.")
        if event.kind is HookEventKind.SUBAGENT_STOP:
            return decision(text=ctx.review_context[:2048], context=True)
    elif surface is HookSurfaceId.SESSION_CONTEXT and event.kind is HookEventKind.SESSION_START:
        return decision(text=ctx.session_context.encode()[:2048].decode(errors="ignore"), context=True)
    return decision()
