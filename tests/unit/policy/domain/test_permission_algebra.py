"""policy §4.4: the narrowing table row by row, ``narrow_rule`` and the hypothesis laws (POLICY-01).

Laws are checked on the semantics of allowed actions (the decision of every call of a pool), never on the
order of ``sources`` or of diagnostic lists.
"""

from collections.abc import Callable, Sequence

from hypothesis import given, settings
from hypothesis import strategies as st

from skm.modules.policy.application.composition import builtin_profiles
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
from skm.modules.policy.domain.commands import CommandMode, CommandPolicy, CommandRule, CommandsLayer
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode, NetworkPolicy
from skm.modules.policy.domain.operations import (
    AccessCapability,
    OperationName,
    OperationRule,
    Requirement,
    TaskAuthority,
    narrow_rule,
)
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow, narrow_all
from skm.modules.policy.domain.tool_call import Allow, Ask, EnforcementMode, ToolDecision, check_tool_call
from skm.modules.policy.domain.tool_intent import EffectKind, RiskClass
from unit.policy.domain.layout import FACTS, ROOTS, WT

WORKTREE_ALL = PathRule(PathScope.WORKTREE, "**")
SRC = PathRule(PathScope.WORKTREE, "src/**")
TMP_ALL = PathRule(PathScope.TMP, "**")


def base() -> PermissionSet:
    return builtin_profiles()["workspace-contained"].permissions


def commands(mode: CommandMode, *rules: CommandRule) -> CommandPolicy:
    return CommandPolicy(mode, rules, ("d0",), ("a0",), frozenset({"python"}), True)


def with_commands(perms: PermissionSet, policy: CommandPolicy) -> PermissionSet:
    return narrow(
        PermissionSet(
            perms.fs_read,
            perms.fs_write,
            policy,
            perms.network,
            perms.tools,
            perms.operations,
            perms.external_effects,
            perms.effects_need_approval,
            perms.allowed_isolation,
            perms.sources,
        ),
        PermissionLayer("noop"),
    )


# --- the table of §4.4, row by row ------------------------------------------------------------------


def test_fs_lists_concatenate_without_duplicates_and_none_does_not_narrow() -> None:
    policy = PathPolicy((SRC,), ())
    once = narrow(base(), PermissionLayer("l", fs_read=policy, fs_write=policy))
    twice = narrow(once, PermissionLayer("l2", fs_read=policy, fs_write=policy))
    assert once.fs_read == (*base().fs_read, policy)
    assert twice.fs_write == once.fs_write
    assert narrow(base(), PermissionLayer("none")).fs_read == base().fs_read


def test_commands_mode_takes_the_strictest() -> None:
    perms = with_commands(base(), commands(CommandMode.DENYLIST))
    for layer_mode, expected in (
        (CommandMode.DENYLIST, CommandMode.DENYLIST),
        (CommandMode.ALLOWLIST, CommandMode.ALLOWLIST),
        (CommandMode.NONE, CommandMode.NONE),
    ):
        assert (
            narrow(perms, PermissionLayer("l", commands=CommandsLayer(mode=layer_mode))).commands.mode
            is expected
        )
    strict = with_commands(base(), commands(CommandMode.NONE))
    assert narrow(
        strict, PermissionLayer("l", commands=CommandsLayer(mode=CommandMode.DENYLIST))
    ).commands.mode is (CommandMode.NONE)


def test_commands_allow_intersects_by_program_and_subcommands() -> None:
    perms = with_commands(
        base(),
        commands(
            CommandMode.ALLOWLIST,
            CommandRule("git", frozenset({"status", "log"})),
            CommandRule("ls", None),
            CommandRule("gh", frozenset({"*:view"})),
            CommandRule("cat", None),
        ),
    )
    layer = CommandsLayer(
        allow=(
            CommandRule("git", frozenset({"log", "diff"})),
            CommandRule("ls", frozenset({"x"})),
            CommandRule("gh", frozenset({"pr:list"})),
            CommandRule("rg", None),
        )
    )
    result = narrow(perms, PermissionLayer("l", commands=layer)).commands
    assert result.mode is CommandMode.ALLOWLIST
    # S ∩ T; None ∩ S = S; empty intersection drops the program; a program on one side only is dropped
    assert result.allow == (CommandRule("git", frozenset({"log"})), CommandRule("ls", frozenset({"x"})))


def test_single_allowlist_keeps_its_allow() -> None:
    denylist = with_commands(base(), commands(CommandMode.DENYLIST))
    rules = (CommandRule("ls", None),)
    result = narrow(
        denylist, PermissionLayer("l", commands=CommandsLayer(mode=CommandMode.ALLOWLIST, allow=rules))
    )
    assert (result.commands.mode, result.commands.allow) == (CommandMode.ALLOWLIST, rules)


def test_empty_subcommands_remove_the_program() -> None:
    perms = with_commands(base(), commands(CommandMode.ALLOWLIST, CommandRule("git", None)))
    layer = CommandsLayer(allow=(CommandRule("git", frozenset()),))
    assert narrow(perms, PermissionLayer("l", commands=layer)).commands.allow == ()


def test_allowlist_after_none_still_intersects() -> None:
    perms = with_commands(base(), commands(CommandMode.ALLOWLIST, CommandRule("ls", None)))
    disabled = narrow(perms, PermissionLayer("ceiling", commands=CommandsLayer(mode=CommandMode.NONE)))
    later = narrow(disabled, PermissionLayer("l", commands=CommandsLayer(allow=(CommandRule("rm", None),))))
    assert later.commands.mode is CommandMode.NONE
    assert later.commands.allow == ()


def test_patterns_and_interpreters_accumulate_in_order_and_trust_is_and() -> None:
    perms = with_commands(base(), commands(CommandMode.DENYLIST))
    layer = CommandsLayer(
        deny_patterns=("d1", "d0"),
        ask_patterns=("a1",),
        inline_interpreters=frozenset({"node"}),
        trust_inline_interpreters=False,
    )
    result = narrow(perms, PermissionLayer("l", commands=layer)).commands
    assert result.deny_patterns == ("d0", "d1")
    assert result.ask_patterns == ("a0", "a1")
    assert result.inline_interpreters == {"python", "node"}
    assert result.trust_inline_interpreters is False
    trusted = narrow(perms, PermissionLayer("l", commands=CommandsLayer(trust_inline_interpreters=True)))
    assert trusted.commands.trust_inline_interpreters is True
    untouched = narrow(perms, PermissionLayer("l", commands=CommandsLayer()))
    assert untouched.commands.trust_inline_interpreters is True


def test_network_mode_strictest_and_hosts_appended() -> None:
    perms = base()
    assert perms.network.mode is NetworkMode.ALLOWLIST
    widened = narrow(perms, PermissionLayer("l", network=NetworkLayer(mode=NetworkMode.ANY)))
    assert widened.network.mode is NetworkMode.ALLOWLIST
    closed = narrow(perms, PermissionLayer("l", network=NetworkLayer(mode=NetworkMode.NONE)))
    assert closed.network.mode is NetworkMode.NONE
    listed = narrow(perms, PermissionLayer("l", network=NetworkLayer(hosts=frozenset({"pypi.org"}))))
    assert listed.network.hosts == (*perms.network.hosts, frozenset({"pypi.org"}))
    assert listed.network.allows("pypi.org", 443)
    assert not listed.network.allows("registry.npmjs.org", 443)


def test_a_host_list_without_mode_restricts_an_open_network() -> None:
    open_network = narrow(builtin_profiles()["trusted-full-access"].permissions, PermissionLayer("noop"))
    assert open_network.network.allows("example.com", 443)
    empty = narrow(open_network, PermissionLayer("l", network=NetworkLayer(hosts=frozenset())))
    assert empty.network.mode is NetworkMode.ALLOWLIST
    assert not empty.network.allows("example.com", 443)


def test_tools_conjunction() -> None:
    result = narrow(base(), PermissionLayer("l", tools=frozenset({"fs.read", "mcp:*"})))
    assert result.tools == (*base().tools, frozenset({"fs.read", "mcp:*"}))


def test_operations_narrow_per_key() -> None:
    layer = PermissionLayer(
        "l",
        operations={
            OperationName.MODIFY_WRITE_SET: OperationRule(warn=True),
            OperationName.GIT_FORCE_PUSH: OperationRule(),
        },
    )
    result = narrow(base(), layer)
    assert result.operations[OperationName.MODIFY_WRITE_SET] == OperationRule(warn=True)
    assert result.operations[OperationName.GIT_FORCE_PUSH].deny
    assert result.operations[OperationName.GIT_PUSH] == base().operations[OperationName.GIT_PUSH]


def test_effects_isolation_intersect_and_approval_unions() -> None:
    layer = PermissionLayer(
        "l",
        external_effects=frozenset({EffectKind.GIT_COMMIT, EffectKind.PUBLISH}),
        effects_need_approval=frozenset({EffectKind.GIT_COMMIT}),
        allowed_isolation=frozenset({"landlock", "none"}),
    )
    result = narrow(base(), layer)
    assert result.external_effects == {EffectKind.GIT_COMMIT}
    assert result.effects_need_approval == base().effects_need_approval | {EffectKind.GIT_COMMIT}
    assert result.allowed_isolation == {"landlock"}
    assert result.sources == (*base().sources, "l")


def test_empty_isolation_makes_every_launch_impossible() -> None:
    assert (
        narrow(base(), PermissionLayer("l", allowed_isolation=frozenset())).allowed_isolation == frozenset()
    )


# --- narrow_rule ---------------------------------------------------------------------------------------

rules = st.builds(
    OperationRule,
    deny=st.booleans(),
    requires=st.frozensets(st.sampled_from(list(Requirement))),
    capabilities=st.frozensets(st.sampled_from(list(AccessCapability))),
    warn=st.booleans(),
    risk=st.none() | st.sampled_from(list(RiskClass)),
)


def test_narrow_rule_never_milder() -> None:
    a = OperationRule(requires=frozenset({Requirement.ASK}), risk=RiskClass.LOW)
    b = OperationRule(
        deny=True, capabilities=frozenset({AccessCapability.SECRETS}), warn=True, risk=RiskClass.HIGH
    )
    assert narrow_rule(a, b) == OperationRule(
        deny=True,
        requires=frozenset({Requirement.ASK}),
        capabilities=frozenset({AccessCapability.SECRETS}),
        warn=True,
        risk=RiskClass.HIGH,
    )


@given(rules, rules, rules)
def test_narrow_rule_is_commutative_associative_idempotent(
    a: OperationRule, b: OperationRule, c: OperationRule
) -> None:
    assert narrow_rule(a, b) == narrow_rule(b, a)
    assert narrow_rule(narrow_rule(a, b), c) == narrow_rule(a, narrow_rule(b, c))
    assert narrow_rule(a, a) == a


# --- monotonicity and layer laws on the decision of a call pool -----------------------------------------

CALLS: tuple[ToolCall, ...] = (
    FileRead(f"{WT}/src/app.py"),
    FileRead("/etc/passwd"),
    FileRead("/home/dev/.ssh/id_rsa"),
    FileWrite(f"{WT}/src/new.py"),
    FileWrite(f"{WT}/docs/x.md"),
    FileWrite("/w/attempt/tmp/out.txt"),
    FileEdit(f"{WT}/.git/config"),
    FileDelete(f"{WT}/src/app.py"),
    FileDelete(f"{WT}/build/out.o"),
    FileDelete(f"{WT}/notes.txt"),
    RunCommand("ls -la src", WT),
    RunCommand("git status", WT),
    RunCommand("git push origin main", WT),
    RunCommand("git push --force origin main", WT),
    RunCommand("git reset --hard", WT),
    RunCommand("git fetch", WT),
    RunCommand("rm -rf build", WT),
    RunCommand("rm src/app.py", WT),
    RunCommand("echo hi > docs/out.md", WT),
    RunCommand("curl https://pypi.org/simple", WT),
    RunCommand("pip install requests", WT),
    RunCommand("python3 -c 'print(1)'", WT),
    RunCommand("make test", WT),
    RunCommand("docker ps", WT),
    RunCommand("psql -h db", WT),
    RunCommand("gh pr view 1", WT),
    RunCommand("systemctl status x", WT),
    RunCommand("for x in 1; do ls; done", WT),
    WebAccess("web.fetch", "https://pypi.org/simple", None),
    WebAccess("web.fetch", "https://example.com/", None),
    WebAccess("web.search", None, "query"),
    McpCall("skm", "plan_get"),
    McpCall("other", "tool"),
)
GRANTED = TaskAuthority(
    write_scope=(SRC,),
    delete_scope=(PathRule(PathScope.WORKTREE, "build/**"),),
    operations=frozenset({OperationName.GIT_DISCARD}),
    capabilities=frozenset({AccessCapability.SECRETS}),
)
EMPTY = TaskAuthority(write_scope=None, delete_scope=(), operations=frozenset(), capabilities=frozenset())

path_policies = st.builds(
    PathPolicy,
    allow=st.lists(
        st.sampled_from([WORKTREE_ALL, SRC, TMP_ALL, PathRule(PathScope.ANY, "etc/**")]), max_size=3
    ).map(tuple),
    deny=st.lists(st.sampled_from([PathRule(PathScope.WORKTREE, "docs/**"), SRC]), max_size=2).map(tuple),
)
command_layers = st.builds(
    CommandsLayer,
    mode=st.none() | st.sampled_from(list(CommandMode)),
    allow=st.none()
    | st.lists(
        st.sampled_from(
            [
                CommandRule("ls", None),
                CommandRule("git", frozenset({"status", "push"})),
                CommandRule("git", frozenset({"status"})),
                CommandRule("make", None),
                CommandRule("gh", frozenset({"*:view"})),
            ]
        ),
        max_size=3,
        unique_by=lambda rule: rule.program,
    ).map(tuple),
    deny_patterns=st.lists(st.sampled_from([r"\bmake\b", r"\bdocker\b"]), max_size=2, unique=True).map(tuple),
    ask_patterns=st.lists(st.sampled_from([r"\bls\b", r"\bgit\b"]), max_size=2, unique=True).map(tuple),
    inline_interpreters=st.frozensets(st.sampled_from(["python3", "node"])),
    trust_inline_interpreters=st.none() | st.booleans(),
)
network_layers = st.builds(
    NetworkLayer,
    mode=st.none() | st.sampled_from(list(NetworkMode)),
    hosts=st.none() | st.frozensets(st.sampled_from(["pypi.org", "*.org", "github.com", "example.com"])),
)
layers = st.builds(
    PermissionLayer,
    source=st.just("generated"),
    fs_read=st.none() | path_policies,
    fs_write=st.none() | path_policies,
    commands=st.none() | command_layers,
    network=st.none() | network_layers,
    tools=st.none()
    | st.frozensets(st.sampled_from(["fs.read", "fs.write", "shell.run", "web.fetch", "mcp:*"])),
    operations=st.none() | st.dictionaries(st.sampled_from(list(OperationName)), rules, max_size=4),
    external_effects=st.none() | st.frozensets(st.sampled_from(list(EffectKind))),
    effects_need_approval=st.none() | st.frozensets(st.sampled_from(list(EffectKind))),
    allowed_isolation=st.none()
    | st.frozensets(st.sampled_from(["none", "worktree", "landlock", "container"])),
)
profile_ids = st.sampled_from(["workspace-contained", "read-only", "trusted-full-access"])
authorities = st.sampled_from([EMPTY, GRANTED])
modes = st.sampled_from(list(EnforcementMode))


def rank(decision: ToolDecision) -> int:
    return 0 if isinstance(decision, Allow) else 1 if isinstance(decision, Ask) else 2


def kind(decision: ToolDecision) -> tuple[str, frozenset[str]]:
    warnings = frozenset(decision.warnings) if isinstance(decision, Allow) else frozenset[str]()
    return type(decision).__name__, warnings


def decide(
    perms: PermissionSet, call: ToolCall, authority: TaskAuthority, mode: EnforcementMode
) -> ToolDecision:
    return check_tool_call(perms, call, roots=ROOTS, facts=FACTS, authority=authority, mode=mode)


def semantics(
    perms: PermissionSet, authority: TaskAuthority, mode: EnforcementMode
) -> tuple[
    tuple[tuple[str, frozenset[str]], ...], frozenset[str], frozenset[EffectKind], frozenset[EffectKind]
]:
    decisions = tuple(kind(decide(perms, call, authority, mode)) for call in CALLS)
    return decisions, perms.allowed_isolation, perms.external_effects, perms.effects_need_approval


def fold(start: PermissionSet, sequence: Sequence[PermissionLayer]) -> PermissionSet:
    return narrow_all(start, tuple(sequence))


@settings(max_examples=60, deadline=None)
@given(profile_ids, layers, authorities, modes)
def test_narrowing_never_makes_a_decision_milder(
    profile: str, layer: PermissionLayer, authority: TaskAuthority, mode: EnforcementMode
) -> None:
    before = builtin_profiles()[profile].permissions
    after = narrow(before, layer)
    for call in CALLS:
        old, new = decide(before, call, authority, mode), decide(after, call, authority, mode)
        assert rank(new) >= rank(old), (call, old, new)
    assert after.allowed_isolation <= before.allowed_isolation
    assert after.external_effects <= before.external_effects
    assert after.effects_need_approval >= before.effects_need_approval


@settings(max_examples=40, deadline=None)
@given(profile_ids, layers, layers, authorities)
def test_layers_commute_and_are_idempotent(
    profile: str, first: PermissionLayer, second: PermissionLayer, authority: TaskAuthority
) -> None:
    start = builtin_profiles()[profile].permissions
    mode = EnforcementMode.INTERACTIVE
    forward = fold(start, (first, second))
    backward = fold(start, (second, first))
    assert semantics(forward, authority, mode) == semantics(backward, authority, mode)
    assert dict(forward.operations) == dict(backward.operations)  # every requirement survives a permutation
    once = fold(start, (first,))
    assert semantics(fold(start, (first, first)), authority, mode) == semantics(once, authority, mode)


@settings(max_examples=30, deadline=None)
@given(profile_ids, st.lists(layers, min_size=3, max_size=3))
def test_grouping_of_layers_does_not_matter(profile: str, three: list[PermissionLayer]) -> None:
    start = builtin_profiles()[profile].permissions
    mode = EnforcementMode.INTERACTIVE
    left = fold(fold(start, three[:2]), three[2:])
    right = fold(fold(start, three[:1]), three[1:])
    assert semantics(left, EMPTY, mode) == semantics(right, EMPTY, mode)


def test_monotonic_expectations_of_the_orch_authority_fixture() -> None:
    """Expectations of ``packages/orch/tests/test_authority_monotonic.py``: untrusted layers only tighten."""
    start = base()
    check: Callable[[PermissionSet, ToolCall], ToolDecision] = lambda perms, call: decide(  # noqa: E731
        perms, call, EMPTY, EnforcementMode.AGENT_UNATTENDED
    )
    widening = PermissionLayer(
        "role:executor",
        fs_write=PathPolicy((PathRule(PathScope.ANY, "**"),), ()),
        network=NetworkLayer(mode=NetworkMode.ANY),
        operations={name: OperationRule() for name in OperationName},
        external_effects=frozenset(EffectKind),
        allowed_isolation=frozenset({"none", "worktree", "landlock", "container"}),
    )
    narrowed = narrow(start, widening)
    for call in (
        FileWrite("/etc/hosts"),
        RunCommand("git push --force origin main", WT),
        WebAccess("web.fetch", "https://example.com/", None),
    ):
        assert rank(check(narrowed, call)) >= rank(check(start, call)) == 2
    assert "none" not in narrowed.allowed_isolation
    assert narrowed.external_effects == start.external_effects
    assert NetworkPolicy(NetworkMode.ALLOWLIST, ()).allows("pypi.org", 443) is False


def test_allowlist_mode_without_entries_commutes_and_stays_monotonic() -> None:
    start = base()
    cmd_mode_only = PermissionLayer("m", commands=CommandsLayer(mode=CommandMode.ALLOWLIST, allow=None))
    cmd_rules_only = PermissionLayer("r", commands=CommandsLayer(mode=None, allow=(CommandRule("ls", None),)))
    assert fold(start, (cmd_mode_only, cmd_rules_only)).commands.allow == ()
    assert fold(start, (cmd_rules_only, cmd_mode_only)).commands.allow == ()

    open_net = builtin_profiles()["trusted-full-access"].permissions
    net_mode_only = PermissionLayer("nm", network=NetworkLayer(mode=NetworkMode.ALLOWLIST, hosts=None))
    net_hosts_only = PermissionLayer("nh", network=NetworkLayer(mode=None, hosts=frozenset({"example.com"})))
    assert not fold(open_net, (net_mode_only, net_hosts_only)).network.allows("example.com", 443)
    assert not fold(open_net, (net_hosts_only, net_mode_only)).network.allows("example.com", 443)
