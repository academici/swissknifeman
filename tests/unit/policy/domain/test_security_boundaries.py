"""policy §§4.4, 5.1, 5.2a, 5.3, 5.3a (ench2): semantic laws on ``None``/empty layers, the default network
ceiling, the supported-shell gate, basename identity and warnings that never turn a deny into an allow."""

import shlex
from collections.abc import Mapping

import pytest

from skm.kernel.json_types import JsonValue
from skm.modules.policy.application.composition import compose_effective
from skm.modules.policy.domain.calls import FileWrite, McpCall, RunCommand, ToolCall, WebAccess
from skm.modules.policy.domain.commands import CommandRule, CommandsLayer
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import TaskAuthority
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope, ScopeRoots
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow
from skm.modules.policy.domain.shell_words import parse
from skm.modules.policy.domain.tool_call import (
    Allow,
    Ask,
    Deny,
    EnforcementMode,
    ToolDecision,
    check_tool_call,
)
from skm.modules.policy.domain.tool_intent import EffectKind
from unit.policy.domain.layout import EMPTY, FACTS, ROOTS, WT, CatalogConfig

INTERACTIVE = EnforcementMode.INTERACTIVE
UNATTENDED = EnforcementMode.AGENT_UNATTENDED


def effective(overrides: Mapping[str, JsonValue] | None = None) -> PermissionSet:
    return compose_effective(
        CatalogConfig(overrides or {}),
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )


def decide(
    perms: PermissionSet, call: ToolCall, *, mode: EnforcementMode = UNATTENDED, roots: ScopeRoots = ROOTS
) -> ToolDecision:
    return check_tool_call(perms, call, roots=roots, facts=FACTS, authority=EMPTY, mode=mode)


def code_of(decision: ToolDecision) -> str:
    return decision.code if isinstance(decision, Deny) else type(decision).__name__


def rule_of(decision: ToolDecision) -> str:
    return decision.rule if isinstance(decision, Deny) else type(decision).__name__


# --- None does not narrow, an explicit empty list allows nothing ---------------------------------------


def test_none_fields_do_not_narrow() -> None:
    base = effective()
    assert narrow(base, PermissionLayer("noop")) == PermissionSet(
        base.fs_read,
        base.fs_write,
        base.commands,
        base.network,
        base.tools,
        base.operations,
        base.external_effects,
        base.effects_need_approval,
        base.allowed_isolation,
        (*base.sources, "noop"),
    )


@pytest.mark.parametrize(
    ("layer", "call"),
    [
        (PermissionLayer("l", tools=frozenset()), McpCall("skm", "plan_get")),
        (PermissionLayer("l", fs_write=PathPolicy((), ())), FileWrite(f"{WT}/src/a.py")),
        (
            PermissionLayer("l", network=NetworkLayer(hosts=frozenset())),
            RunCommand("curl https://pypi.org/x", WT),
        ),
        (PermissionLayer("l", commands=CommandsLayer(allow=())), RunCommand("ls", WT)),
    ],
)
def test_an_explicit_empty_list_allows_nothing(layer: PermissionLayer, call: ToolCall) -> None:
    profile = compose_effective(
        CatalogConfig({"policy.ceiling.network_allowlist": ["pypi.org"]}),
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    assert isinstance(decide(profile, call), Allow)
    assert isinstance(decide(narrow(profile, layer), call), Deny)


def test_empty_effects_and_isolation() -> None:
    closed = narrow(
        effective(), PermissionLayer("l", external_effects=frozenset(), allowed_isolation=frozenset())
    )
    assert closed.external_effects == frozenset()
    assert closed.allowed_isolation == frozenset()  # no launch at all, not "none"


def test_incompatible_isolation_layers_leave_nothing() -> None:
    perms = narrow(
        narrow(effective(), PermissionLayer("a", allowed_isolation=frozenset({"worktree"}))),
        PermissionLayer("b", allowed_isolation=frozenset({"container"})),
    )
    assert perms.allowed_isolation == frozenset()


# --- network ceiling (FOUNDATION-04, K16) ---------------------------------------------------------------


def test_default_config_forbids_the_network() -> None:
    perms = effective()
    assert perms.network.mode is NetworkMode.ALLOWLIST
    for call in (
        RunCommand("curl https://pypi.org/simple", WT),
        RunCommand("pip install requests", WT),
        RunCommand("npm install", WT),
        WebAccess("web.fetch", "https://pypi.org/simple", None),
    ):
        decision = decide(perms, call)
        assert code_of(decision) == "network_denied", (call, decision)


def test_remote_hosts_do_not_lift_an_empty_ceiling() -> None:
    perms = effective()
    roots = ScopeRoots(
        ROOTS.worktrees,
        ROOTS.materials,
        ROOTS.tmp,
        ROOTS.home,
        (),
        ROOTS.protected,
        frozenset({"github.com"}),
    )
    for command in ("git fetch", "git pull", "git ls-remote", "gh pr view 1"):
        decision = decide(perms, RunCommand(command, WT), roots=roots)
        assert code_of(decision) == "network_denied", (command, decision)


def test_a_changed_project_remote_does_not_widen_the_ceiling() -> None:
    perms = effective({"policy.ceiling.network_allowlist": ["github.com"]})
    trusted = ScopeRoots(ROOTS.worktrees, None, None, None, (), (), frozenset({"github.com"}))
    moved = ScopeRoots(ROOTS.worktrees, None, None, None, (), (), frozenset({"evil.example"}))
    profile_hosts = narrow(
        perms, PermissionLayer("allow-github", network=NetworkLayer(hosts=frozenset({"github.com"})))
    )
    assert isinstance(decide(profile_hosts, RunCommand("git fetch", WT), roots=moved), Deny)
    # github.com is not among the profile's registry hosts either: every list must admit it
    assert isinstance(decide(profile_hosts, RunCommand("git fetch", WT), roots=trusted), Deny)


def test_network_any_only_through_the_ceiling() -> None:
    perms = effective({"policy.ceiling.network": "any"})
    # the profile keeps its allowlist; the ceiling's (empty) list still applies
    assert perms.network.mode is NetworkMode.ALLOWLIST
    assert isinstance(decide(perms, RunCommand("curl https://example.com/", WT)), Deny)


def test_explicit_allowlist_admits_only_listed_hosts() -> None:
    perms = effective({"policy.ceiling.network_allowlist": ["pypi.org", "files.pythonhosted.org"]})
    assert decide(perms, RunCommand("pip install requests", WT)) == Allow()
    assert isinstance(decide(perms, RunCommand("npm install", WT)), Deny)


# --- supported shell subset (§5.2a) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "cat <<EOF\nhello\nEOF",
        "f() { ls; }; f",
        "for f in *; do echo $f; done",
        "while true; do ls; done",
        "if true; then ls; fi",
        "case x in x) ls;; esac",
        "echo $(date)",
        "ls $DIR",
        "echo 'unbalanced",
        "echo $'ansi'",
    ],
)
def test_unsupported_syntax_asks_and_is_denied_unattended(command: str) -> None:
    perms = effective()
    interactive = decide(perms, RunCommand(command, WT), mode=INTERACTIVE)
    unattended = decide(perms, RunCommand(command, WT))
    assert isinstance(interactive, Ask | Deny), interactive
    assert isinstance(unattended, Deny), unattended
    if isinstance(interactive, Ask):
        assert interactive.rule == "unsupported_syntax"
        assert unattended == Deny("approval_unavailable_unattended", "unsupported_syntax", interactive.reason)


def test_depth_limit_is_unsupported() -> None:
    nested = "ls"
    for _ in range(8):
        nested = "eval " + shlex.quote(nested)
    assert parse("eval " + shlex.quote("eval ls")).supported
    assert not parse(nested).supported
    decision = decide(effective(), RunCommand(nested, WT))
    assert rule_of(decision) == "unsupported_syntax"


def test_legacy_keywords_do_not_bypass_the_structural_gate() -> None:
    perms = effective()
    for command in ("time ls", "! ls"):
        assert isinstance(decide(perms, RunCommand(command, WT), mode=INTERACTIVE), Allow)
    assert isinstance(decide(perms, RunCommand("if ls; then rm -rf /; fi", WT)), Deny)


# --- identity: a basename is a label, not proof ---------------------------------------------------------


@pytest.mark.parametrize("command", ["./ls", "bin/ls -la", "/opt/x/git status", "env ./ls"])
def test_a_path_head_is_never_auto_allowlisted(command: str) -> None:
    read_only = narrow(
        effective(),
        PermissionLayer(
            "role", commands=CommandsLayer(allow=(CommandRule("ls", None), CommandRule("git", None)))
        ),
    )
    decision = decide(read_only, RunCommand(command, WT), mode=INTERACTIVE)
    assert isinstance(decision, Ask | Deny), decision
    if isinstance(decision, Ask):
        assert decision.rule == "not_allowlisted"


def test_basename_classification_still_applies_to_path_heads() -> None:
    decision = decide(effective(), RunCommand("/usr/bin/git push --force origin main", WT))
    assert rule_of(decision) == "git_force_push"


# --- warnings -------------------------------------------------------------------------------------------


def test_a_warning_is_kept_and_never_turns_a_deny_into_an_allow() -> None:
    perms = effective()
    scoped = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**"),), (), frozenset(), frozenset())
    warned = check_tool_call(
        perms, FileWrite(f"{WT}/docs/a.md"), roots=ROOTS, facts=FACTS, authority=scoped, mode=UNATTENDED
    )
    assert warned == Allow(warnings=("modify_outside_write_set",))
    both = check_tool_call(
        perms,
        RunCommand("echo x > docs/a.md && git push origin main", WT),
        roots=ROOTS,
        facts=FACTS,
        authority=scoped,
        mode=INTERACTIVE,
    )
    assert code_of(both) == "requires_intent"


def test_effects_of_the_default_ceiling() -> None:
    perms = effective()
    assert perms.external_effects == {EffectKind.GIT_COMMIT}
    assert EffectKind.GIT_PUSH in perms.effects_need_approval
