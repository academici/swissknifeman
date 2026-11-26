"""S9/S10 (mechanisms 08), policy §§4.4, 5.1, 15: no layer, authority or request widens permissions.

A run, role or task layer that names broader rights than the profile and ceiling gets nothing more; task
authority satisfies ``task_authority`` rows but never lifts ``deny``; a capability outside
``policy.access_capabilities.allowed`` has no effect; a serialized request that would widen the ceiling is
reported field by field. These are preflight decisions; process isolation remains a host responsibility.
"""

import re
from collections.abc import Mapping
from importlib import resources
from typing import cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, Forbidden
from skm.kernel.json_types import JsonValue
from skm.modules.policy import public
from skm.modules.policy.application.composition import (
    builtin_profiles,
    compose_effective,
    task_authority_from,
)
from skm.modules.policy.domain.calls import FileDelete, FileRead, FileWrite, RunCommand, ToolCall, WebAccess
from skm.modules.policy.domain.commands import CommandMode, CommandRule, CommandsLayer
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import (
    AccessCapability,
    OperationName,
    OperationRule,
    PathOrigin,
    StaticPathFacts,
    TaskAuthority,
)
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope, ScopeRoots
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet
from skm.modules.policy.domain.profiles import parse_layer
from skm.modules.policy.domain.render import view_document
from skm.modules.policy.domain.tool_call import Allow, Deny, EnforcementMode, ToolDecision
from skm.modules.policy.domain.tool_intent import EffectKind
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry

WT = "/srv/attempt/repo"
ROOTS = ScopeRoots(
    worktrees={"main": WT},
    materials="/srv/attempt/materials",
    tmp="/srv/attempt/tmp",
    home="/home/agent",
    safe_dirs=(),
    protected=("/var/lib/skm",),
    remote_hosts=frozenset({"github.com"}),
)
FACTS = StaticPathFacts(
    origins_by_path={
        f"{WT}/src/app.py": frozenset({PathOrigin.TRACKED}),
        f"{WT}/notes.txt": frozenset({PathOrigin.FOREIGN_UNTRACKED}),
    },
    home="/home/agent",
)
NO_AUTHORITY = TaskAuthority(None, (), frozenset(), frozenset())
FULL_AUTHORITY = TaskAuthority(
    write_scope=None,
    delete_scope=(PathRule(PathScope.WORKTREE, "**"),),
    operations=frozenset(OperationName),
    capabilities=frozenset(AccessCapability),
)
WIDE_LAYER: dict[str, JsonValue] = {
    "allowed_isolation": ["none", "worktree", "landlock", "container"],
    "fs": {
        "read": {"allow": [{"scope": "any", "pattern": "**"}, {"scope": "home", "pattern": "**"}]},
        "write": {"allow": [{"scope": "any", "pattern": "**"}, {"scope": "home", "pattern": "**"}]},
    },
    "commands": {"mode": "denylist", "deny_patterns": [], "trust_inline_interpreters": True},
    "network": {"mode": "any"},
    "tools": {
        "allow": [
            "fs.read",
            "fs.write",
            "fs.edit",
            "fs.delete",
            "shell.run",
            "web.fetch",
            "web.search",
            "mcp:*",
        ]
    },
    "effects": {"allow": ["git_commit", "git_push", "pr_create", "message", "publish"], "need_approval": []},
    "operations": {name.value: {"decision": "allow"} for name in OperationName},
}
PROBES: tuple[ToolCall, ...] = (
    FileRead("/etc/shadow"),
    FileRead("/home/agent/.ssh/id_ed25519"),
    FileWrite("/etc/hosts"),
    FileWrite(f"{WT}/.git/hooks/pre-commit"),
    FileDelete(f"{WT}/notes.txt"),
    RunCommand("git push --force origin main", WT),
    RunCommand("git push origin main", WT),
    RunCommand("sudo make install", WT),
    RunCommand("docker run --rm alpine", WT),
    RunCommand("psql -h prod-db", WT),
    RunCommand("curl https://example.com/", WT),
    RunCommand("gh pr create --title t --body b", WT),
    WebAccess("web.fetch", "https://example.com/", None),
)


class Config:
    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self.values = {
            "policy.default_profile": "workspace-contained",
            "policy.profiles": {},
            "policy.restrictions": [],
            "policy.ceiling.network": "allowlist",
            "policy.ceiling.network_allowlist": [],
            "policy.ceiling.shell": True,
            "policy.ceiling.external_effects": ["git_commit"],
            "policy.ceiling.isolation_profiles": ["worktree", "landlock", "container"],
            "policy.ceiling.commands_denylist": ["rm -rf /", "git push --force", "git reset --hard"],
            "policy.approval.required_for": ["git_push", "pr_create", "message", "publish"],
            "policy.access_capabilities.allowed": [],
            "policy.access_capabilities.granted": [],
            "policy.task_authority.operations": [],
            **values,
        }

    def get(self, key: str) -> JsonValue | None:
        return self.values.get(key)


def compose(
    config: Mapping[str, JsonValue] | None = None,
    *,
    role: PermissionLayer | None = None,
    task: PermissionLayer | None = None,
    profile_id: str | None = None,
    allow_unconfined: bool = False,
) -> PermissionSet:
    return compose_effective(
        Config(config or {}),
        profile_id=profile_id,
        role_layer=role,
        task_layer=task,
        allow_unconfined=allow_unconfined,
    )


def decide(perms: PermissionSet, call: ToolCall, authority: TaskAuthority = NO_AUTHORITY) -> ToolDecision:
    return public.check_tool_call(
        perms, call, roots=ROOTS, facts=FACTS, authority=authority, mode=EnforcementMode.AGENT_UNATTENDED
    )


def code_of(decision: ToolDecision) -> str:
    """The refusal code of a ``Deny``, else the decision type (an allow never passes for a refusal)."""
    return decision.code if isinstance(decision, Deny) else type(decision).__name__


def rule_of(decision: ToolDecision) -> str:
    return decision.rule if isinstance(decision, Deny) else type(decision).__name__


def wide(source: str) -> PermissionLayer:
    return parse_layer(WIDE_LAYER, source=source)


@pytest.mark.parametrize("level", ["role", "task", "restriction"])
@pytest.mark.parametrize("probe", PROBES, ids=repr)
def test_a_wider_layer_grants_nothing_more(level: str, probe: ToolCall) -> None:
    baseline = compose()
    if level == "restriction":
        widened = compose({"policy.restrictions": [WIDE_LAYER]})
    elif level == "role":
        widened = compose(role=wide("role:wide"))
    else:
        widened = compose(task=wide("task:wide"))
    before, after = decide(baseline, probe), decide(widened, probe)
    assert isinstance(before, Deny), (probe, before)
    assert isinstance(after, Deny), (probe, after)


def test_a_wider_layer_keeps_every_bound_of_the_set() -> None:
    baseline = compose()
    widened = compose(
        role=wide("role:wide"), task=wide("task:wide"), config={"policy.restrictions": [WIDE_LAYER]}
    )
    assert widened.allowed_isolation <= baseline.allowed_isolation
    assert "none" not in widened.allowed_isolation
    assert widened.external_effects <= baseline.external_effects == {EffectKind.GIT_COMMIT}
    assert widened.effects_need_approval >= baseline.effects_need_approval
    assert widened.network.mode is NetworkMode.ALLOWLIST
    assert widened.commands.mode is CommandMode.DENYLIST
    assert set(baseline.commands.deny_patterns) <= set(widened.commands.deny_patterns)
    assert widened.commands.trust_inline_interpreters is False
    for name in OperationName:
        rule, base = widened.operations[name], baseline.operations[name]
        assert rule.deny >= base.deny
        assert rule.requires >= base.requires
        assert rule.capabilities >= base.capabilities


def test_run_level_restriction_cannot_reopen_a_closed_ceiling() -> None:
    closed = compose(
        {"policy.ceiling.shell": False, "policy.restrictions": [{"commands": {"mode": "denylist"}}]}
    )
    decision = decide(closed, RunCommand("ls", WT))
    assert code_of(decision) in {"commands_disabled", "tool_not_allowed"}


@pytest.mark.parametrize(
    ("call", "operation"),
    [
        (RunCommand("git push -f origin main", WT), "git_force_push"),
        (FileDelete(f"{WT}/notes.txt"), "delete_foreign_untracked"),
        (FileWrite(f"{WT}/.git/config"), "modify_git_dir"),
        (RunCommand("git push origin main", WT), "git_push"),
    ],
)
def test_task_authority_never_lifts_a_deny_row(call: ToolCall, operation: str) -> None:
    decision = decide(compose(), call, FULL_AUTHORITY)
    assert rule_of(decision) == operation


def test_task_authority_satisfies_only_task_authority_rows() -> None:
    perms = compose()
    discard = RunCommand("git reset --soft HEAD~1 && git stash drop", WT)
    assert isinstance(decide(perms, discard), Deny)
    assert decide(perms, discard, FULL_AUTHORITY) == Allow()
    tracked = FileDelete(f"{WT}/src/app.py")
    in_scope = TaskAuthority(None, (PathRule(PathScope.WORKTREE, "src/**"),), frozenset(), frozenset())
    elsewhere = TaskAuthority(None, (PathRule(PathScope.WORKTREE, "docs/**"),), frozenset(), frozenset())
    assert decide(perms, tracked, in_scope) == Allow()
    assert isinstance(decide(perms, tracked, elsewhere), Deny)


def test_a_capability_outside_allowed_has_no_effect() -> None:
    granted_only = Config({"policy.access_capabilities.granted": ["docker_socket", "secrets"]})
    authority = task_authority_from(granted_only, write_scope=None)
    assert authority.capabilities == frozenset()
    decision = decide(compose(), RunCommand("docker ps", WT), authority)
    assert code_of(decision) == "capability_not_granted"
    both = Config(
        {
            "policy.access_capabilities.granted": ["docker_socket", "secrets"],
            "policy.access_capabilities.allowed": ["docker_socket"],
        }
    )
    allowed = task_authority_from(both, write_scope=None)
    assert allowed.capabilities == {AccessCapability.DOCKER_SOCKET}
    assert decide(compose(), RunCommand("docker ps", WT), allowed) == Allow()
    assert isinstance(decide(compose(), FileRead("/home/agent/.aws/credentials"), allowed), Deny)


def test_a_layer_cannot_turn_a_capability_row_into_allow() -> None:
    role = PermissionLayer("role:x", operations={OperationName.DOCKER_SOCKET: OperationRule()})
    decision = decide(compose(role=role), RunCommand("docker ps", WT))
    assert code_of(decision) == "capability_not_granted"


def test_a_layer_cannot_add_allowlisted_programs() -> None:
    readonly = compose(profile_id="read-only")
    role = PermissionLayer(
        "role:x", commands=CommandsLayer(allow=(CommandRule("make", None), CommandRule("ls", None)))
    )
    narrowed = compose(profile_id="read-only", role=role)
    assert {rule.program for rule in narrowed.commands.allow} == {"ls"}
    assert isinstance(decide(readonly, RunCommand("make", WT)), Deny)
    assert isinstance(decide(narrowed, RunCommand("make", WT)), Deny)


@pytest.mark.parametrize(
    "command", ["env -C build -C . touch created.txt", "env --chdir=build --chdir=. touch created.txt"]
)
def test_a_repeated_env_directory_does_not_widen_the_write_scope(command: str) -> None:
    # env keeps only the last ``-C`` of one invocation: ``created.txt`` lands in the worktree root
    perms = compose(
        task=PermissionLayer("task", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "build/**"),), ()))
    )
    assert code_of(decide(perms, RunCommand(command, WT))) == "path_denied"
    assert decide(perms, RunCommand("env -C build env -C . touch created.txt", WT)) == Allow()


def test_a_later_env_directory_does_not_hide_an_opaque_one() -> None:
    # D='. sh -c >created.txt': env runs the shell in the worktree root and ``-C build`` becomes its argument
    perms = compose(
        task=PermissionLayer("task", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "build/**"),), ()))
    )
    assert isinstance(decide(perms, RunCommand("env -C $D -C build touch created.txt", WT)), Deny)


def test_a_role_cannot_open_the_network() -> None:
    role = PermissionLayer("role:x", network=NetworkLayer(mode=NetworkMode.ANY, hosts=None))
    perms = compose({"policy.ceiling.network_allowlist": ["pypi.org"]}, role=role)
    assert isinstance(decide(perms, RunCommand("curl https://example.com/", WT)), Deny)
    assert decide(perms, RunCommand("curl https://pypi.org/simple", WT)) == Allow()


def test_trusted_profile_is_not_reachable_without_the_host_flag() -> None:
    with pytest.raises(Forbidden):
        compose({"policy.default_profile": "trusted-full-access"})
    with pytest.raises(Forbidden):
        compose(profile_id="trusted-full-access", role=wide("role:wide"))


def test_forbidden_paths_of_the_task_stay_forbidden_under_wider_layers() -> None:
    task = public.forbidden_paths_layer((("main", "secrets/**"),), source="task:P1")
    perms = compose(role=wide("role:wide"), task=task)
    decision = decide(perms, FileWrite(f"{WT}/secrets/key.txt"))
    assert code_of(decision) == "path_denied"


def test_isolation_grants_never_drop_a_forbidden_path_of_the_task() -> None:
    # a directory grant cannot carry ``deny secrets/**``: the profile is refused, the worktree never rw
    task = public.forbidden_paths_layer((("main", "secrets/**"),), source="task:P1")
    perms = compose(task=task)
    for profile in sorted(perms.allowed_isolation):
        with pytest.raises(CapabilityUnavailable) as caught:
            public.isolation_grants(perms, ROOTS, profile)
        assert caught.value.code is ErrorCode.SANDBOX_UNAVAILABLE
        assert caught.value.details["reason"] == "restriction_not_representable"
    assert WT in public.isolation_grants(compose(), ROOTS, "container").rw_paths
    # a role that allows only scope ``any`` grants no worktree root at all, neither rw nor ro
    widened = public.isolation_grants(compose(role=wide("role:wide"), task=task), ROOTS, "container")
    assert widened == public.IsolationGrants("container", (), ())


def test_is_subset_reports_a_widening_request() -> None:
    ceiling = compose()
    violations = public.is_subset(WIDE_LAYER, ceiling)
    fields = {violation.field for violation in violations}
    assert {
        "allowed_isolation",
        "fs_read",
        "fs_write",
        "network.mode",
        "tools",
        "external_effects",
        "commands.trust_inline_interpreters",
        "operations.git_force_push",
    } <= fields
    assert public.is_subset({"tools": {"allow": ["fs.read"]}}, ceiling) == ()


def read_only_request() -> dict[str, JsonValue]:
    """The built-in ``read-only`` profile as a serialized permission request."""
    text = resources.files("skm.modules.policy").joinpath("profiles", "read-only.toml").read_text("utf-8")
    profile = decode_document(text, "toml")
    identity = {"schema", "id", "version", "description", "requires_host_flag"}
    return {key: value for key, value in profile.items() if key not in identity}


WORKSPACE_ASK_PROGRAMS = (
    "crontab",
    "systemctl",
    "service",
    "launchctl",
    "iptables",
    "nft",
    "ufw",
    "mount",
    "umount",
    "kill",
    "pkill",
    "killall",
    "setfacl",
)


def test_the_read_only_profile_is_a_subset_of_workspace_contained() -> None:
    request = read_only_request()
    assert SchemaRegistry.load_default().validate("urn:skm:policy:permission-request:v1", request) == ()
    assert public.is_subset(request, builtin_profiles()["workspace-contained"].permissions) == ()


@pytest.mark.parametrize("program", WORKSPACE_ASK_PROGRAMS)
def test_read_only_without_an_ask_of_the_default_profile_is_widening(program: str) -> None:
    # negative example of the proof: the ask pattern of read-only is what keeps the program behind a question
    request = read_only_request()
    patterns = cast("dict[str, list[str]]", request["commands"])["ask_patterns"]
    without = re.sub(rf"\|{program}(?=[|)])", "", patterns[1])
    assert without != patterns[1]
    patterns[1] = without
    found = public.is_subset(request, builtin_profiles()["workspace-contained"].permissions)
    assert [(item.field, item.reason) for item in found] == [("commands.ask_patterns", "drops_pattern")]


@pytest.mark.parametrize("profile", ["read-only", "workspace-contained"])
@pytest.mark.parametrize("program", WORKSPACE_ASK_PROGRAMS)
@pytest.mark.parametrize(
    "template",
    ["{0} x", "env {0} x", "env -i {0} x", "env A=1 {0} x", "env '{0}' x", "'{0}' x", "sh -c \"'{0}' x\""],
)
def test_a_system_program_never_passes_either_profile(profile: str, program: str, template: str) -> None:
    perms = builtin_profiles()[profile].permissions
    call = RunCommand(template.format(program), WT)
    decision = public.check_tool_call(
        perms, call, roots=ROOTS, facts=FACTS, authority=NO_AUTHORITY, mode=EnforcementMode.INTERACTIVE
    )
    assert isinstance(decision, public.Ask), decision
    assert isinstance(decide(perms, call), Deny)


def test_a_view_that_admits_no_host_restores_no_authority() -> None:
    composed = compose()  # the catalog default: the ceiling lists no host
    fields = view_document(composed) | {"digest": public.permissions_digest(composed)}
    assert fields["network"] == {"mode": "allowlist", "hosts": []}
    assert SchemaRegistry.load_default().validate("urn:skm:policy:view:permission-set:v2", fields) == ()
    restored = public.permission_set_from_view(fields)
    for call in (
        WebAccess("web.fetch", "https://pypi.org/simple", None),
        WebAccess("web.fetch", "https://example.com/", None),
        RunCommand("curl https://pypi.org/simple", WT),
        RunCommand("git fetch", WT),
    ):
        assert code_of(decide(restored, call)) == "network_denied", call
    assert not restored.network.allows("pypi.org", 443)
    requests: tuple[tuple[dict[str, JsonValue], str], ...] = (
        ({"network": {"hosts": ["pypi.org"]}}, "network.hosts"),
        ({"network": {"mode": "allowlist", "hosts": ["*.org"]}}, "network.hosts"),
        ({"network": {"mode": "any"}}, "network.mode"),
    )
    for request, field in requests:
        assert [item.field for item in public.is_subset(request, fields)] == [field]


def test_is_subset_treats_an_unprovable_path_inclusion_as_widening() -> None:
    ceiling = compose(
        task=PermissionLayer("task", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "src/**"),), ()))
    )
    request: dict[str, JsonValue] = {"fs": {"write": {"allow": [{"scope": "worktree", "pattern": "*.py"}]}}}
    assert {violation.field for violation in public.is_subset(request, ceiling)} == {"fs_write"}
