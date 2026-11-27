"""Positive and negative facts for all 26 doctor check identifiers."""

from dataclasses import replace

import pytest

from skm.modules.integrations.domain.checks import (
    DoctorContext,
    claude,
    clients,
    projections,
    run_checks,
    summarize,
)
from skm.modules.integrations.domain.checks.context import effective_settings
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind
from skm.modules.integrations.domain.hook_subscriptions import parse_subscriptions
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.target import TargetId


def layer(name="project", data=None, **facts):
    return {"layer": name, "path": name + ".json", "exists": True, "valid": True, "data": data or {}, **facts}


BASE = DoctorContext(TargetId.CLAUDE_CODE)
CURSOR = DoctorContext(TargetId.CURSOR)
CODEX = DoctorContext(TargetId.CODEX)
SECRET = "sk-" + "sensitive0123456789" * 3
HOOK = {"hooks": [{"type": "command", "command": "skm-hook PreToolUse"}]}
SUBS, ERRORS = parse_subscriptions(
    {
        "audit": {
            "class": "enforcement",
            "kind": "command",
            "execution_location": "host",
            "event_types": ["client:pre_shell"],
            "target": {"argv": ["audit"], "cwd": "checkout"},
            "failure_policy": "deny",
        }
    },
    {},
)
assert not ERRORS
SUB = SUBS[0]
SUB_CONTEXT = replace(
    BASE,
    subscriptions=SUBS,
    supported_kinds=frozenset({HookEventKind.PRE_SHELL}),
    trusted={SUB.id: SUB.digest},
)


def changed(data, **kwargs):
    return replace(BASE, layers=(layer(data=data),), **kwargs)


CASES = [
    (claude.layer_json_valid, BASE, replace(BASE, layers=(layer(valid=False),)), "error"),
    (
        claude.noncanonical_keys,
        changed({"permissions": {"allow": []}}),
        changed({"alienKey": True, "permissions": {"alien": True}}),
        "warning",
    ),
    (
        claude.default_mode_conflict,
        changed({"permissions": {"defaultMode": "default"}}),
        replace(
            BASE,
            layers=(
                layer("user", {"permissions": {"defaultMode": "default"}}),
                layer("local", {"permissions": {"defaultMode": "acceptEdits"}}),
            ),
        ),
        "warning",
    ),
    (
        claude.profile_conformance,
        changed({"permissions": {"allow": []}}, expected={"permissions": {"allow": []}}),
        changed({"permissions": {"allow": []}}, expected={"permissions": {"allow": ["Read"]}}),
        "warning",
    ),
    (
        claude.hooks_resolvable,
        changed(
            {"hooks": {"PreToolUse": [HOOK]}},
            commands=frozenset({"skm-hook"}),
            known_hook_events=frozenset({"PreToolUse"}),
        ),
        changed({"hooks": {"Unknown": [HOOK]}}),
        "error",
    ),
    (
        claude.dead_allow_rules,
        changed({"permissions": {"allow": ["Bash(git status)"]}}),
        changed({"permissions": {"allow": ["Bash(git *)", "Bash(git status)"]}}),
        "info",
    ),
    (
        claude.allow_deny_overlap,
        changed({"permissions": {"allow": ["Read"], "deny": ["Write"]}}),
        changed({"permissions": {"allow": ["Read"], "deny": ["Read"]}}),
        "warning",
    ),
    (
        claude.additional_dirs_missing,
        changed({"permissions": {"additionalDirectories": ["lib"]}}, directories={"lib": True}),
        changed({"permissions": {"additionalDirectories": ["gone"]}}, directories={"gone": False}),
        "warning",
    ),
    (
        claude.secrets_in_env,
        changed({"env": {"COLOR": "blue", "TOKEN": "secret://env/TOKEN"}}),
        changed({"env": {"TOKEN": SECRET}}),
        "error",
    ),
    (
        claude.bypass_without_skip_dialog,
        changed(
            {"permissions": {"defaultMode": "bypassPermissions"}, "skipDangerousModePermissionPrompt": True}
        ),
        changed({"permissions": {"defaultMode": "bypassPermissions"}}),
        "warning",
    ),
    (
        claude.ask_rules_expected_empty,
        changed({"permissions": {"ask": []}}, expected={"permissions": {"ask": []}}),
        changed({"permissions": {"ask": ["Write"]}}, expected={"permissions": {"ask": []}}),
        "info",
    ),
    (
        claude.initial_mode_mismatch,
        BASE,
        replace(
            BASE,
            layers=(
                layer(data={"permissions": {"defaultMode": "acceptEdits"}}),
                layer("vscode", {"claudeCode.initialPermissionMode": "default"}),
            ),
        ),
        "warning",
    ),
    (
        claude.bypass_toggle_missing,
        BASE,
        changed({"permissions": {"defaultMode": "bypassPermissions"}}),
        "info",
    ),
    (
        clients.single_writer_overlap,
        CURSOR,
        replace(
            CURSOR,
            layers=(
                layer("hooks", {"hooks": {"preToolUse": [HOOK]}}, path=".cursor/hooks.json"),
                layer("claude_user", {"hooks": {"PreToolUse": [HOOK]}}),
            ),
        ),
        "warning",
    ),
    (
        clients.duplicate_hook_registrations,
        CURSOR,
        replace(
            CURSOR,
            layers=(layer("hooks", {"hooks": {"preToolUse": [HOOK, HOOK]}}, path=".cursor/hooks.json"),),
        ),
        "warning",
    ),
    (
        clients.compat_binding_notice,
        CURSOR,
        replace(CURSOR, layers=(layer("claude_local", {"hooks": {"PreToolUse": [HOOK]}}),)),
        "info",
    ),
    (clients.layers_readable, CODEX, replace(CODEX, layers=(layer(valid=False),)), "warning"),
    (
        clients.project_overrides_machine_key,
        CODEX,
        replace(CODEX, layers=(layer(data={"notify": ["notify"], "telemetry": {}}),)),
        "error",
    ),
    (
        clients.hooks_feature_disabled,
        replace(CODEX, layers=(layer(data={"features": {"hooks": True}}),)),
        replace(CODEX, layers=(layer(data={"features": {"hooks": False}}),)),
        "warning",
    ),
    (
        projections.local_settings_gitignored,
        replace(BASE, layers=(layer("local", gitignored=True),)),
        replace(BASE, layers=(layer("local", gitignored=False),)),
        "warning",
    ),
    (projections.projection_drift, BASE, replace(BASE, drift_paths=("CLAUDE.md",)), "warning"),
    (
        projections.marker_digest,
        replace(BASE, marker_files={"CLAUDE.md": render_block("skm.core", "ok")}),
        replace(BASE, marker_files={"CLAUDE.md": render_block("skm.core", "ok").replace(b"ok\n", b"bad\n")}),
        "warning",
    ),
    (
        projections.subscriptions_valid,
        SUB_CONTEXT,
        replace(SUB_CONTEXT, subscriptions=(replace(SUB, timeout_ms=999999),)),
        "error",
    ),
    (projections.checkout_marker, BASE, replace(BASE, checkout_marker="missing"), "warning"),
    (projections.checkout_marker, BASE, replace(BASE, checkout_marker="mismatch"), "warning"),
    (projections.subscriptions_untrusted, SUB_CONTEXT, replace(SUB_CONTEXT, trusted={}), "warning"),
    (
        projections.event_unsupported,
        SUB_CONTEXT,
        replace(SUB_CONTEXT, supported_kinds=frozenset()),
        "warning",
    ),
]


@pytest.mark.parametrize(
    ("check", "good", "bad", "level"), CASES, ids=lambda value: getattr(value, "__name__", None)
)
@pytest.mark.parametrize("negative", [False, True])
def test_every_check(check, good, bad, level, negative):
    results = tuple(check(bad if negative else good))
    assert results
    assert all(result.level == (level if negative else "ok") for result in results)
    assert all(result.target == (bad if negative else good).target for result in results)


def test_exactly_33_stable_ids_and_severity_aggregation():
    results = tuple(result for ctx in (BASE, CURSOR, CODEX) for result in run_checks(ctx).checks)
    assert len({result.check_id for result in results}) == 33
    report = summarize(results)
    assert report.status == "ok"
    assert report.counts["ok"] == len(results)
    for _, _, bad, _ in CASES:
        report = run_checks(bad)
        assert sum(report.counts.values()) == len(report.checks)
        assert report.status == next(
            level for level in ("error", "warning", "info", "ok") if report.counts[level]
        )


def test_precedence_is_semantic_even_for_unordered_observations():
    layers = (
        layer("local", {"permissions": {"defaultMode": "acceptEdits"}}),
        layer("user", {"permissions": {"defaultMode": "default", "deny": ["Write"]}}),
        layer("project", {"permissions": {"allow": ["Read"]}}),
    )
    effective = effective_settings(layers)
    assert effective["permissions"] == {"defaultMode": "acceptEdits", "allow": ["Read"], "deny": ["Write"]}
    managed = effective_settings((*layers, layer("managed", {"permissions": {"defaultMode": "default"}})))
    permissions = managed["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["defaultMode"] == "default"


def test_redaction_prevents_leaks_in_any_report_fact():
    report = run_checks(
        changed({"env": {"TOKEN": SECRET}, "permissions": {"allow": [SECRET], "deny": [SECRET]}})
    )
    assert SECRET not in repr(report)
    secret = next(result for result in report.checks if result.check_id == "claude.secrets_in_env")
    assert secret.path == "project.json"
    assert "TOKEN" in secret.detail


@pytest.mark.parametrize(
    "raw",
    [
        b"<!-- skm:begin bad -->\n",
        render_block("skm.core", "ok") * 2,
        render_block("skm.core", "ok").replace(b"\n", b"\r\n"),
    ],
)
def test_markers_validate_structure_and_normalize_crlf(raw):
    result = projections.marker_digest(replace(BASE, marker_files={"AGENTS.md": raw}))[0]
    assert result.level == ("ok" if b"\r\n" in raw else "warning")


def test_workflow_trust_is_info_disabled_hooks_do_not_warn_and_digests_are_exact():
    sub = replace(SUB, hook_class=HookClass.WORKFLOW)
    ctx = replace(SUB_CONTEXT, subscriptions=(sub,), trusted={sub.id: "wrong"})
    assert projections.subscriptions_untrusted(ctx)[0].level == "info"
    ctx = replace(ctx, subscriptions=(replace(sub, enabled=False),), supported_kinds=frozenset())
    assert projections.subscriptions_untrusted(ctx)[0].level == "ok"
    assert projections.event_unsupported(ctx)[0].level == "ok"


def test_malformed_subscription_and_wildcard_capability():
    _, violations = parse_subscriptions({"broken": {}}, {})
    assert (
        projections.subscriptions_valid(replace(BASE, subscription_violations=violations))[0].level == "error"
    )
    wildcard = replace(SUB, event_types=("client:*",))
    assert (
        projections.event_unsupported(replace(SUB_CONTEXT, subscriptions=(wildcard,)))[0].level == "warning"
    )


def test_project_subscription_facts_preserve_upstream_validation_and_host_trust():
    fact = {
        "id": "project-hook",
        "enabled": True,
        "execution_location": "host",
        "class": "enforcement",
        "event_types": ["client:pre_shell"],
        "digest": "sha256:" + "1" * 64,
        "valid": False,
    }
    ctx = replace(BASE, subscription_facts=(fact,))
    assert projections.subscriptions_valid(ctx)[0].level == "error"
    assert projections.subscriptions_untrusted(ctx)[0].level == "warning"
    assert projections.event_unsupported(ctx)[0].level == "warning"
    ctx = replace(
        ctx,
        subscription_facts=({**fact, "valid": True},),
        trusted={fact["id"]: fact["digest"]},
        supported_kinds=frozenset({HookEventKind.PRE_SHELL}),
    )
    assert projections.subscriptions_valid(ctx)[0].level == "ok"
    assert projections.subscriptions_untrusted(ctx)[0].level == "ok"
    assert projections.event_unsupported(ctx)[0].level == "ok"
