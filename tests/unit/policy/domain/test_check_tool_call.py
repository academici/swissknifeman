"""policy §5.3: every step of ``check_tool_call``, the unattended rule, the ``evaluate_operation`` order."""

import pytest

from skm.modules.policy.domain.calls import (
    FileDelete,
    FileEdit,
    FileRead,
    FileWrite,
    McpCall,
    RunCommand,
    WebAccess,
)
from skm.modules.policy.domain.commands import CommandMode, CommandsLayer
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import (
    AccessCapability,
    OperationHit,
    OperationName,
    OperationRule,
    Requirement,
    TaskAuthority,
    evaluate_operation,
)
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope, ScopedPath, classify_path
from skm.modules.policy.domain.permission_set import PermissionLayer
from skm.modules.policy.domain.tool_call import DECISION_CODES, Allow, Ask, Deny, EnforcementMode
from unit.policy.domain.layout import HOME, ROOTS, WT

INTERACTIVE = EnforcementMode.INTERACTIVE
WC = "workspace-contained"
RO = "read-only"
TRUSTED = "trusted-full-access"


def sh(command: str) -> RunCommand:
    return RunCommand(command, WT)


def denied(decision: object, code: str, rule: str | None = None) -> bool:
    return isinstance(decision, Deny) and decision.code == code and (rule is None or decision.rule == rule)


def asked(decision: object, rule: str) -> bool:
    return isinstance(decision, Ask) and decision.rule == rule


def test_t0_tool_outside_every_list(decide) -> None:
    assert denied(decide(WC, McpCall("other", "x")), "tool_not_allowed", "mcp:other/x")
    assert decide(WC, McpCall("skm", "plan_get")) == Allow()
    layer = PermissionLayer("role", tools=frozenset({"fs.read"}))
    assert denied(decide(WC, FileWrite(f"{WT}/src/a.py"), layers=(layer,)), "tool_not_allowed")


@pytest.mark.parametrize("profile", [WC, RO, TRUSTED])
def test_p0_skm_state_is_protected_for_every_profile(decide, profile: str) -> None:
    assert denied(decide(profile, FileRead("/var/lib/skm/db"), mode=INTERACTIVE), "path_protected")
    # a symlink inside the worktree is judged by its target
    assert denied(decide(profile, FileRead(f"{WT}/state/db"), mode=INTERACTIVE), "path_protected")
    assert denied(decide(profile, sh("cat /var/lib/skm/secret.key"), mode=INTERACTIVE), "path_protected")


def test_p0_own_roots_under_a_protected_root_stay_usable(decide) -> None:
    # "/w" is protected, the attempt's own worktree below it is not
    assert decide(WC, FileRead(f"{WT}/src/app.py")) == Allow()


def test_only_step_tmp_is_writable_inside_step_state(decide) -> None:
    assert classify_path("/w/attempt/tmp/scratch", ROOTS).scope is PathScope.TMP
    assert decide(WC, FileWrite("/w/attempt/tmp/scratch")) == Allow()
    assert denied(decide(WC, FileWrite("/w/attempt/transcript.jsonl")), "path_protected")
    assert denied(decide(WC, FileWrite("/tmp/shared")), "path_outside_scope")  # noqa: S108 -- simulated path


def test_unattended_external_write_requires_an_intent_even_in_full_access(decide) -> None:
    assert denied(
        decide(TRUSTED, FileWrite("/outside/file"), mode=EnforcementMode.AGENT_UNATTENDED),
        "requires_intent",
        "fs_write_external",
    )


def test_f1_f2_read_scopes(decide) -> None:
    assert denied(decide(WC, FileRead("/etc/passwd")), "path_outside_scope")
    assert denied(decide(WC, FileRead(f"{HOME}/notes.md")), "path_denied")
    assert decide(WC, FileRead("/opt/cache/pkg.tar")) == Allow()
    assert decide(WC, FileRead("/w/attempt/materials/brief.md")) == Allow()


def test_f2_symlink_escape_is_judged_by_its_target(decide) -> None:
    assert denied(decide(WC, FileRead(f"{WT}/escape/passwd")), "path_outside_scope", "/etc/passwd")
    assert denied(decide(WC, FileWrite(f"{WT}/escape/hosts")), "path_outside_scope", "/etc/hosts")
    assert denied(decide(WC, sh("echo x > escape/hosts")), "path_outside_scope", "/etc/hosts")
    assert denied(decide(TRUSTED, FileWrite(f"{WT}/state/db"), mode=INTERACTIVE), "path_protected")


def test_f2_every_layer_of_the_conjunction_must_allow(decide) -> None:
    layer = PermissionLayer("task", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "src/**"),), ()))
    assert decide(WC, FileWrite(f"{WT}/src/a.py"), layers=(layer,)) == Allow()
    assert denied(decide(WC, FileWrite(f"{WT}/docs/a.md"), layers=(layer,)), "path_denied")
    forbidden = PermissionLayer(
        "task",
        fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "**"),), (PathRule(PathScope.WORKTREE, "*.lock"),)),
    )
    assert denied(decide(WC, FileEdit(f"{WT}/uv.lock"), layers=(forbidden,)), "path_denied")


def test_c1_commands_disabled(decide) -> None:
    layer = PermissionLayer("ceiling", commands=CommandsLayer(mode=CommandMode.NONE))
    assert denied(decide(WC, sh("ls"), layers=(layer,)), "commands_disabled")


def test_c2_unsupported_syntax_asks_and_keeps_deny_checks(decide) -> None:
    assert asked(decide(WC, sh("for f in *; do echo $f; done"), mode=INTERACTIVE), "unsupported_syntax")
    unattended = decide(WC, sh("for f in *; do echo $f; done"))
    assert denied(unattended, "approval_unavailable_unattended", "unsupported_syntax")
    assert denied(decide(WC, sh("for x in 1; do sudo ls; done"), mode=INTERACTIVE), "command_denied")


def test_c3_deny_patterns_on_visible_text_and_raw_text_of_carriers(decide) -> None:
    assert denied(decide(WC, sh("sudo ls")), "command_denied", "deny:0")
    assert decide(WC, sh("echo 'sudo is a word'")) == Allow(allowlisted=True)
    assert denied(decide(WC, sh("bash -c 'sudo ls'")), "command_denied", "deny:0")
    assert denied(decide(WC, sh("env -i A=1 sh -c 'mkfs /dev/sda'")), "command_denied")


@pytest.mark.parametrize(
    "command",
    [
        "'sudo' ls",
        "su'do' ls",
        "s\\udo ls",
        '"sudo" ls',
        "env 'sudo' ls",
        "sh -c \"'sudo' ls\"",
        "'mkfs' /dev/sda",
    ],
)
def test_c3_a_quoted_program_is_the_same_program(decide, command: str) -> None:
    assert denied(decide(WC, sh(command), mode=INTERACTIVE), "command_denied", "deny:0")


@pytest.mark.parametrize(
    "command", ["echo 'sudo'", "echo 'kill'", "printf '%s' 'mount'", "grep 'kill' src/app.py", "ls 'sudo'"]
)
def test_c3_c7_a_quoted_argument_stays_a_word(decide, command: str) -> None:
    assert isinstance(decide(WC, sh(command), mode=INTERACTIVE), Allow)


def test_c4_deletion_outside_the_write_scope(decide) -> None:
    assert denied(decide(WC, sh("rm -rf /etc/x")), "rm_outside_write_scope", "C4")
    assert denied(decide(WC, sh("/bin/rm -rf /etc/x")), "rm_outside_write_scope")
    assert decide(WC, sh("rm -rf build")) == Allow()
    assert denied(decide(RO, sh("rm build/out.o")), "rm_outside_write_scope")


def test_c4_writes_of_commands_pass_f2(decide) -> None:
    assert denied(decide(WC, sh("cp src/app.py /etc/app.py")), "path_outside_scope", "/etc/app.py")
    assert denied(decide(WC, sh("tee /w/attempt/materials/x < src/app.py")), "path_denied")


def test_o1_operations_in_hit_order(decide) -> None:
    assert denied(decide(WC, sh("git push origin main")), "requires_intent", "git_push")
    assert denied(decide(WC, sh("git status && git push --force")), "operation_denied", "git_force_push")
    assert denied(decide(WC, FileDelete(f"{WT}/src/app.py")), "requires_task_authority", "delete_tracked")
    assert denied(decide(WC, sh("docker ps")), "capability_not_granted", "docker_socket")
    granted = TaskAuthority(None, (), frozenset(), frozenset({AccessCapability.DOCKER_SOCKET}))
    assert decide(WC, sh("docker ps"), authority=granted) == Allow()


def test_o1_warnings_survive_as_allow_warnings(decide) -> None:
    scoped = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**"),), (), frozenset(), frozenset())
    for mode in EnforcementMode:
        decision = decide(WC, FileWrite(f"{WT}/docs/x.md"), authority=scoped, mode=mode)
        assert decision == Allow(warnings=("modify_outside_write_set",))


def test_n1_network(decide) -> None:
    assert decide(WC, sh("curl https://pypi.org/simple")) == Allow()
    assert denied(decide(WC, sh("curl https://example.com/")), "network_denied", "example.com")
    offline = PermissionLayer("ceiling", network=NetworkLayer(mode=NetworkMode.NONE))
    search = WebAccess("web.search", None, "x")
    assert denied(decide(WC, search, layers=(offline,), mode=INTERACTIVE), "network_denied")
    assert denied(decide(RO, search, mode=INTERACTIVE), "tool_not_allowed")
    assert decide(WC, search) == Allow()
    assert asked(decide(WC, sh("wget"), mode=INTERACTIVE), "network_unresolved")
    assert decide(TRUSTED, sh("curl https://example.com/"), mode=INTERACTIVE) == Allow()
    assert denied(decide(WC, WebAccess("web.fetch", "https://example.com/x", None)), "network_denied")


@pytest.mark.parametrize(
    "command",
    [
        "curl https://pypi.org/simple evil.example",
        "curl --url=https://evil.example https://pypi.org/simple",
        "curl -x evil.example:3128 https://pypi.org/simple",
        "https_proxy=http://evil.example:8080 curl https://pypi.org/simple",
    ],
)
def test_n1_one_allowed_url_does_not_hide_another_destination(decide, command: str) -> None:
    assert denied(decide(WC, sh(command)), "network_denied", "evil.example")


def test_n1_a_destination_moved_out_of_the_argv_is_unresolved(decide) -> None:
    resolved = decide(WC, sh("curl --resolve pypi.org:443:203.0.113.9 https://pypi.org/simple"))
    assert denied(resolved, "approval_unavailable_unattended", "network_unresolved")
    assert decide(WC, sh("curl -sSL -o out.html https://pypi.org/simple")) == Allow()


@pytest.mark.parametrize(
    "call",
    [
        RunCommand(f"ls | cd {WT}/build; rm -f out.o", "/"),
        RunCommand(f"true && cd {WT}/build; rm -f out.o", "/"),
        sh("env -C /etc /bin/rm -f passwd"),
        sh("env --chdir=/etc /bin/rm -f passwd"),
        sh("env -C /etc sh -c 'rm -f passwd'"),
    ],
)
def test_c4_a_deletion_in_another_directory_is_refused(decide, call: RunCommand) -> None:
    assert isinstance(decide(WC, call), Deny), call
    assert isinstance(decide(WC, call, mode=INTERACTIVE), (Deny, Ask)), call


def test_c4_a_repeated_wrapper_directory_is_not_stacked(decide) -> None:
    layer = PermissionLayer("task", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "build/**"),), ()))
    for command in ("env -C build -C . touch created.txt", "env --chdir=build --chdir=. touch created.txt"):
        assert denied(decide(WC, sh(command), layers=(layer,)), "path_denied"), command
    assert decide(WC, sh("env -C build env -C . touch created.txt"), layers=(layer,)) == Allow()
    # unquoted ``$D`` may split into ``.`` plus a shell: the later ``-C build`` must not hide it
    assert isinstance(decide(WC, sh("env -C $D -C build touch created.txt"), layers=(layer,)), (Deny, Ask))


def test_o1_abbreviated_git_discards_are_not_allowed(decide) -> None:
    for command in ("git reset --har", "git clean --for -d", "git reset --bogus"):
        assert isinstance(decide(WC, sh(command)), Deny), command
        assert isinstance(decide(TRUSTED, sh(command), mode=INTERACTIVE), (Ask, Deny)), command


def test_n1_remote_hosts_must_pass_every_host_list(decide) -> None:
    assert denied(decide(WC, sh("git fetch")), "network_denied", "github.com")
    layer = PermissionLayer("restriction", network=NetworkLayer(hosts=frozenset({"github.com"})))
    assert denied(decide(WC, sh("git fetch"), layers=(layer,)), "network_denied")
    both = PermissionLayer("p", network=NetworkLayer(hosts=frozenset({"github.com", "pypi.org"})))
    profile_hosts = PermissionLayer("q", network=NetworkLayer(hosts=frozenset({"github.com"})))
    assert denied(decide(WC, sh("git fetch"), layers=(both, profile_hosts)), "network_denied")


def test_c5_inline_interpreter_in_allowlist_mode(decide) -> None:
    assert asked(decide(RO, sh("python3 -c 'print(1)'"), mode=INTERACTIVE), "inline_interpreter")
    assert decide(WC, sh("python3 -c 'print(1)'")) == Allow()


def test_c7_ask_patterns(decide) -> None:
    assert asked(decide(WC, sh("systemctl restart nginx"), mode=INTERACTIVE), "ask:0")
    assert denied(decide(WC, sh("systemctl restart nginx")), "approval_unavailable_unattended", "ask:0")


def test_c8_allowlist_and_allowlisted_flag(decide) -> None:
    assert decide(RO, sh("ls -la src")) == Allow(allowlisted=True)
    assert asked(decide(RO, sh("./ls"), mode=INTERACTIVE), "not_allowlisted")
    # outside allowlist mode ``allowlisted`` is judged on the built-in read-only data
    assert decide(WC, sh("ls -la src")) == Allow(allowlisted=True)
    assert decide(WC, sh("make build")) == Allow(allowlisted=False)
    assert decide(WC, sh("ls -la src"), reference=False) == Allow(allowlisted=False)


def test_r_first_deny_wins_over_asks_and_warnings(decide) -> None:
    scoped = TaskAuthority((PathRule(PathScope.WORKTREE, "src/**"),), (), frozenset(), frozenset())
    decision = decide(
        WC, sh("echo x > docs/a.md; systemctl stop x; git push"), authority=scoped, mode=INTERACTIVE
    )
    assert denied(decision, "requires_intent")


def test_u_unattended_turns_every_ask_into_deny(decide) -> None:
    for call in (sh("git reset --hard"), sh("git push origin main"), FileDelete(f"{WT}/src/app.py")):
        interactive = decide(TRUSTED, call, mode=INTERACTIVE)
        unattended = decide(TRUSTED, call)
        assert isinstance(interactive, Ask)
        assert unattended == Deny("approval_unavailable_unattended", interactive.rule, interactive.reason)


def test_empty_write_scope_forbids_every_worktree_write(decide) -> None:
    nothing = TaskAuthority((), (), frozenset(), frozenset())
    assert denied(decide(WC, FileWrite(f"{WT}/src/app.py"), authority=nothing), "path_denied")
    assert denied(decide(WC, sh("touch src/new.py"), authority=nothing), "path_denied")
    assert decide(WC, FileWrite("/w/attempt/tmp/scratch"), authority=nothing) == Allow()


@pytest.mark.parametrize(
    "command",
    [
        "sudo -u build git push origin main",
        "env -i A=1 git push origin main",
        "timeout 5 git push origin main",
        "bash -c 'git push origin main'",
        "sh -c \"eval 'git push origin main'\"",
        "xargs git push origin main",
        "git -C sub push origin main",
        "git -c alias.p=push p origin main",
    ],
)
def test_wrappers_do_not_hide_a_push(decide, command: str) -> None:
    assert isinstance(decide(WC, sh(command)), Deny)


def test_decision_codes_are_the_closed_set() -> None:
    assert {
        "tool_not_allowed",
        "path_protected",
        "path_outside_scope",
        "path_denied",
        "commands_disabled",
        "command_denied",
        "rm_outside_write_scope",
        "operation_denied",
        "requires_intent",
        "requires_task_authority",
        "capability_not_granted",
        "network_denied",
        "approval_unavailable_unattended",
    } == DECISION_CODES


def test_evaluate_operation_strict_order() -> None:
    hit = OperationHit(OperationName.DELETE_TRACKED, "x", "K4", ScopedPath(PathScope.WORKTREE, "main", "a"))
    everything = TaskAuthority(None, (), frozenset(OperationName), frozenset(AccessCapability))
    nothing = TaskAuthority(None, (), frozenset(), frozenset())
    all_requirements = OperationRule(
        deny=True,
        requires=frozenset(Requirement),
        capabilities=frozenset({AccessCapability.SECRETS}),
        warn=True,
    )
    steps = [
        (all_requirements, everything, "operation_denied"),
        (OperationRule(requires=frozenset(Requirement)), everything, "requires_intent"),
        (
            OperationRule(
                requires=frozenset({Requirement.TASK_AUTHORITY, Requirement.ASK}),
                capabilities=frozenset({AccessCapability.SECRETS}),
            ),
            nothing,
            "requires_task_authority",
        ),
        (
            OperationRule(
                requires=frozenset({Requirement.ASK}), capabilities=frozenset({AccessCapability.SECRETS})
            ),
            nothing,
            "capability_not_granted",
        ),
    ]
    for rule, authority, code in steps:
        assert evaluate_operation(rule, hit, authority).code == code
    ask = evaluate_operation(OperationRule(requires=frozenset({Requirement.ASK}), warn=True), hit, everything)
    assert ask.outcome == "ask"
    warn = evaluate_operation(OperationRule(warn=True), hit, nothing)
    assert (warn.outcome, warn.warn) == ("allow", True)
    assert evaluate_operation(OperationRule(), hit, nothing).outcome == "allow"
