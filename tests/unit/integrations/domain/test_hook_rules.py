"""Pure hook mode and lifecycle decisions, independent of provider rendering."""

from dataclasses import replace

import pytest

from skm.modules.integrations.domain.hook_events import HookEventKind, HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import (
    HookMode,
    HookPolicyContext,
    HookVerdict,
    commit_message,
    evaluate_hook,
    failure_decision,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.policy.domain.changelog_gate import changelog_gate_verdict
from skm.modules.policy.domain.managed_guard import candidate_paths, managed_hit
from skm.modules.policy.public import GuardMode


def event(command: str = "git commit -m 'feat: thing'") -> NormalizedHookEvent:
    return NormalizedHookEvent(
        TargetId.CODEX, HookEventKind.PRE_SHELL, None, "/repo", "shell", command, (), None, None, "PreToolUse"
    )


@pytest.mark.parametrize("surface", list(HookSurfaceId))
def test_off_never_adds_a_decision(surface: HookSurfaceId) -> None:
    ctx = HookPolicyContext(git_violation=True, safe_verdict="deny", managed_path="/repo/.skm/x")
    assert evaluate_hook(event(), surface, HookMode.OFF, ctx).verdict is HookVerdict.NONE


@pytest.mark.parametrize(
    ("mode", "verdict"), [(HookMode.STRICT, HookVerdict.DENY), (HookMode.WARN, HookVerdict.CONTEXT)]
)
@pytest.mark.parametrize(
    ("surface", "ctx"),
    [
        (HookSurfaceId.GIT_GUARDRAILS, HookPolicyContext(git_violation=True)),
        (HookSurfaceId.SAFE_DIRS, HookPolicyContext(safe_verdict="deny")),
        (HookSurfaceId.PLAN_GUARD, HookPolicyContext(managed_path="/repo/.skm/state")),
        (HookSurfaceId.PACK_GUARD, HookPolicyContext(managed_path="/repo/generated.md")),
        (
            HookSurfaceId.CHANGELOG_GATE,
            HookPolicyContext(staged_paths=("src/app.py",), changelog_required=True),
        ),
        (HookSurfaceId.REVIEW_GATE, HookPolicyContext()),
    ],
)
def test_modes_preserve_enforcement(surface, ctx, mode, verdict) -> None:
    assert evaluate_hook(event(), surface, mode, ctx).verdict is verdict


@pytest.mark.parametrize(
    ("fresh", "blockers", "expected"),
    [(True, False, HookVerdict.NONE), (False, False, HookVerdict.DENY), (True, True, HookVerdict.DENY)],
)
def test_review_gate_checks_both_freshness_and_blockers(fresh, blockers, expected) -> None:
    result = evaluate_hook(
        event(),
        HookSurfaceId.REVIEW_GATE,
        HookMode.STRICT,
        HookPolicyContext(review_fresh=fresh, open_blockers=blockers),
    )
    assert result.verdict is expected
    if expected is HookVerdict.DENY:
        assert result.reason_code == "REVIEW_RECEIPT_STALE"


def test_context_is_bounded_by_bytes_and_observation_does_not_decide() -> None:
    start = replace(event(), kind=HookEventKind.SESSION_START)
    result = evaluate_hook(
        start, HookSurfaceId.SESSION_CONTEXT, HookMode.STRICT, HookPolicyContext(session_context="я" * 3000)
    )
    assert result.verdict is HookVerdict.CONTEXT
    assert len((result.additional_context or "").encode()) <= 2048
    for surface in (HookSurfaceId.COMMAND_LOG, HookSurfaceId.RUN_REPORT):
        assert (
            evaluate_hook(event(), surface, HookMode.STRICT, HookPolicyContext()).verdict is HookVerdict.NONE
        )


@pytest.mark.parametrize(
    "message", ["feat: new", "fix(api)!: corrected", "perf(core): fast", "refactor: shape"]
)
def test_release_commits_require_changelog(message: str) -> None:
    assert changelog_gate_verdict(message, mode=GuardMode.STRICT).decision == "deny"
    assert changelog_gate_verdict(message, mode=GuardMode.WARN).decision == "warn"
    assert changelog_gate_verdict(message, mode=GuardMode.OFF).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'feat: x'",
        "env A=b git -c color.ui=false commit --message='feat: x'",
        r"git commit -mfeat:\ x",
    ],
)
def test_commit_message_is_parsed_without_shell_eval(command: str) -> None:
    assert commit_message(command) == "feat: x"
    assert commit_message("echo 'git commit'") is None


@pytest.mark.parametrize(
    ("staged", "message"),
    [
        (("CHANGELOG.md", "src/a.py"), "feat: x"),
        (("src/a.py",), "feat: x [changelog-skip]"),
        (("docs/a.md",), "docs: x"),
    ],
)
def test_changelog_bypasses_only_explicit_conditions(staged, message) -> None:
    ctx = HookPolicyContext(staged_paths=staged, code_globs=("src/**",), changelog_required=True)
    result = evaluate_hook(
        event(f"git commit -m '{message}'"), HookSurfaceId.CHANGELOG_GATE, HookMode.STRICT, ctx
    )
    assert result.verdict is HookVerdict.NONE


def test_managed_candidates_include_recursive_inputs_and_patch_headers() -> None:
    payload = {
        "edits": [{"path": "../.skm/state"}],
        "patch": "*** Begin Patch\n*** Update File: generated.md\n+x",
    }
    assert "generated.md" in candidate_paths(payload)
    assert (
        managed_hit(payload, "/repo/sub", frozenset(), protected_dirs=("/repo/.skm",)) == "/repo/.skm/state"
    )
    assert (
        managed_hit(
            {"command": "echo x > generated.md"},
            "/repo",
            frozenset({"/repo/generated.md"}),
            protected_dirs=(),
        )
        == "/repo/generated.md"
    )
    assert managed_hit(".skm-other/x", "/repo", frozenset(), protected_dirs=("/repo/.skm",)) is None
    assert (
        managed_hit("echo x > .skm; echo done", "/repo", frozenset(), protected_dirs=("/repo/.skm",))
        == "/repo/.skm"
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (HookMode.STRICT, HookVerdict.DENY),
        (HookMode.WARN, HookVerdict.CONTEXT),
        (HookMode.OFF, HookVerdict.NONE),
    ],
)
def test_review_outage_respects_known_mode(mode: HookMode, expected: HookVerdict) -> None:
    decision = failure_decision(HookSurfaceId.REVIEW_GATE, mode, "HOOK_BACKEND_UNAVAILABLE", commit=True)
    assert decision.verdict is expected


@pytest.mark.parametrize(
    "command",
    [
        "'git' commit -m 'feat: x'",
        "g'i't commit -m 'feat: x'",
        "git c'om'mit -m 'feat: x'",
        "git com\\\nmit -m 'feat: x'",
    ],
)
def test_git_commit_recognition_uses_shell_words(command: str) -> None:
    assert commit_message(command) == "feat: x"
    assert (
        evaluate_hook(event(command), HookSurfaceId.REVIEW_GATE, HookMode.STRICT, HookPolicyContext()).verdict
        is HookVerdict.DENY
    )
