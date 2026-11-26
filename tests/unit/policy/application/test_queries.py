"""Policy queries through the bus (policy §8): effective, explain, profiles, check, list and get."""

from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.modules.access.public import Role
from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.domain.network import NetworkMode
from skm.modules.policy.generated import documents
from skm.modules.policy.generated.queries import (
    CheckToolCall,
    EffectivePermissions,
    ExplainPermissions,
    GetIntent,
    ListProfiles,
)
from skm.modules.policy.public import (
    effective_permissions,
    is_subset,
    permission_set_from_view,
    permissions_digest,
)
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.platform.config.generated.settings import EcosystemsSettings
from unit.policy.application.harness import World
from unit.policy.application.test_lifecycle import propose

ROOTS = documents.ScopeRoots(
    worktrees={"main": "/work/main"},
    materials=None,
    tmp="/tmp/attempt",  # noqa: S108 -- a path in a document, never opened
    home="/home/dev",
    safe_dirs=(),
    protected=("/state",),
    remote_hosts=(),
)


def check(world: World, call: Any, mode: Any = "agent_unattended", **fields: Any) -> Any:
    return world.ask(
        CheckToolCall(
            scope_id=world.scope_id, call=call, roots=ROOTS, observed_origins={}, mode=mode, **fields
        )
    )


# --------------------------------------------------------------------------------- effective / explain
def test_effective_permissions_carry_the_digest_of_the_canonical_form(world: World) -> None:
    result = world.ask(EffectivePermissions(scope_id=world.scope_id))
    permissions = result.permissions
    with world.uow() as uow:
        ctx = world.context(uow)
        composed = effective_permissions(
            uow,
            scope_chain=(),
            config=ctx.config,
            profile_id=None,
            role_layer=None,
            task_layer=None,
            allow_unconfined=False,
        )
    assert permissions.digest == permissions_digest(composed)  # the digest execution puts in the bundle
    assert permission_set_from_view(permissions).external_effects == composed.external_effects
    assert [item.value for item in permissions.external_effects] == sorted(
        item.value for item in composed.external_effects
    )
    assert "git_push" in {item.value for item in permissions.external_effects}
    assert permissions.sources[0].startswith("profile:workspace-contained")
    assert "ceiling" in permissions.sources
    assert result.authority.delete_scope == ()
    assert result.authority.write_scope is None


def network_decisions(world: World, **fields: Any) -> dict[str, tuple[str, str | None]]:
    """What ``check_tool_call`` decides through the bus; interactive: an unknown destination still asks."""
    calls = {
        "search": documents.ToolCallVariant7(tool="web.search", query="x"),
        "fetch": documents.ToolCallVariant6(tool="web.fetch", url="https://example.com/x"),
        "unknown": documents.ToolCallVariant5(tool="shell.run", command="wget", cwd="/work/main"),
    }
    found = {name: check(world, call, "interactive", **fields) for name, call in calls.items()}
    return {name: (decision.outcome, decision.code or decision.rule) for name, decision in found.items()}


NO_HOST_DECISIONS = {
    "search": ("allow", None),
    "fetch": ("deny", "network_denied"),
    "unknown": ("ask", "network_unresolved"),
}


def test_the_default_view_states_an_allowlist_without_a_host(world: World) -> None:
    # the catalog default: ``none`` would hide what the tool call decides, a refusal would hide the view
    result = world.ask(EffectivePermissions(scope_id=world.scope_id))
    network = result.permissions.network
    assert (network.mode.value, list(network.hosts)) == ("allowlist", [])
    assert network_decisions(world) == NO_HOST_DECISIONS
    explained = world.ask(ExplainPermissions(scope_id=world.scope_id))
    explained_network = next(item for item in explained.items if item.field == "network")
    assert explained_network.value == {"mode": "allowlist", "hosts": []}
    assert "ceiling" in explained_network.contributed_by


def test_the_default_view_restores_the_permissions_it_states(world: World) -> None:
    permissions = world.ask(EffectivePermissions(scope_id=world.scope_id)).permissions
    restored = permission_set_from_view(permissions)
    assert restored.network.mode is NetworkMode.ALLOWLIST
    assert not restored.network.allows("pypi.org", 443)
    assert permissions_digest(restored) == permissions.digest
    assert [item.field for item in is_subset({"network": {"hosts": ["pypi.org"]}}, permissions)] == [
        "network.hosts"
    ]
    assert [item.field for item in is_subset({"network": {"mode": "any"}}, permissions)] == ["network.mode"]
    assert is_subset({"network": {"mode": "none"}}, permissions) == ()


def test_hosts_that_do_not_intersect_are_an_allowlist_without_a_host(world: World) -> None:
    world.set_config("policy.ceiling.network_allowlist", ["pypi.org"])
    other: dict[str, Any] = {"task_layer": {"network": {"hosts": ["example.com"]}}}
    network = world.ask(EffectivePermissions(scope_id=world.scope_id, **other)).permissions.network
    assert (network.mode.value, list(network.hosts)) == ("allowlist", [])
    assert network_decisions(world, **other) == NO_HOST_DECISIONS


def test_a_ceiling_of_any_alone_keeps_the_allowlist_of_the_profile(world: World) -> None:
    # the mode takes the strictest value and the empty ceiling list still applies
    world.set_config("policy.ceiling.network", "any")
    network = world.ask(EffectivePermissions(scope_id=world.scope_id)).permissions.network
    assert (network.mode.value, list(network.hosts)) == ("allowlist", [])
    assert network_decisions(world) == NO_HOST_DECISIONS


def test_a_ceiling_without_network_is_shown_as_it_decides(world: World) -> None:
    world.set_config("policy.ceiling.network", "none")
    view = world.ask(EffectivePermissions(scope_id=world.scope_id)).permissions.network
    assert (view.mode.value, list(view.hosts)) == ("none", [])
    search = check(world, documents.ToolCallVariant7(tool="web.search", query="x"))
    assert (search.outcome, search.code) == ("deny", "network_denied")


def test_a_view_with_a_host_decides_like_the_tool_call(world: World) -> None:
    world.set_config("policy.ceiling.network_allowlist", ["pypi.org"])
    view = world.ask(EffectivePermissions(scope_id=world.scope_id)).permissions
    assert (view.network.mode.value, list(view.network.hosts)) == ("allowlist", ["pypi.org"])
    restored = permission_set_from_view(view)
    assert restored.network.allows("pypi.org", 443)
    assert not restored.network.allows("example.com", 443)
    search = check(world, documents.ToolCallVariant7(tool="web.search", query="x"))
    assert search.outcome == "allow"


def test_project_ecosystem_entries_cannot_widen_permissions(world: World) -> None:
    world.set_config("ecosystems.ids", ["python", "dart"])
    world.set_config("ecosystems.hosts", ["pypi.org", "pub.dev"])
    world.set_config("policy.ceiling.network_allowlist", ["pypi.org"])
    project = SetValueDefsScopeRef(level="project", scope_id=world.project_id)
    assert (
        check(world, documents.ToolCallVariant6(tool="web.fetch", url="https://pypi.org/")).outcome == "allow"
    )

    for key, wider, parent in (
        ("ecosystems.ids", ["python", "dart", "php"], ["python", "dart"]),
        ("ecosystems.hosts", ["pypi.org", "pub.dev", "repo.packagist.org"], ["pypi.org", "pub.dev"]),
    ):
        with pytest.raises(ValidationFailed) as caught:
            world.run(SetValue(scope=project, key=key, value=wider))
        assert caught.value.code is ErrorCode.CONFIG_NARROWING_VIOLATION
        assert caught.value.details["ceiling"] == parent

    world.run(SetValue(scope=project, key="ecosystems.ids", value=["dart"]))
    world.run(SetValue(scope=project, key="ecosystems.hosts", value=["pub.dev"]))
    with world.uow(readonly=True) as uow:
        ecosystems = world.context(uow).config.section(EcosystemsSettings)
    assert ecosystems.ids == ("dart",)
    assert ecosystems.hosts == ("pub.dev",)

    for call in (
        documents.ToolCallVariant5(tool="shell.run", command="dart pub get", cwd="/work/main"),
        documents.ToolCallVariant6(tool="web.fetch", url="https://pub.dev/"),
        documents.ToolCallVariant6(tool="web.fetch", url="https://repo.packagist.org/"),
    ):
        decision = check(world, call)
        assert (decision.outcome, decision.code) == ("deny", "network_denied")


def test_the_interactive_profile_and_delete_scope(world: World) -> None:
    result = world.ask(EffectivePermissions(scope_id=world.scope_id, interactive=True))
    assert [(rule.scope.value, rule.pattern) for rule in result.authority.delete_scope] == [
        ("worktree", "**")
    ]


def test_a_read_only_profile_is_narrower(world: World) -> None:
    result = world.ask(EffectivePermissions(scope_id=world.scope_id, profile_id="read-only"))
    assert result.permissions.operations["modify_write_set"].decision.value == "deny"


def test_the_full_access_profile_needs_the_host_flag(world: World) -> None:
    refused_error = None
    with pytest.raises(Forbidden) as caught:
        world.ask(EffectivePermissions(scope_id=world.scope_id, profile_id="trusted-full-access"))
    refused_error = caught.value
    assert refused_error.details["reason"] == "unconfined_not_allowed_on_host"


def test_explain_names_the_layer_that_narrowed_each_field(world: World) -> None:
    world.allow_effects("git_commit")
    result = world.ask(ExplainPermissions(scope_id=world.scope_id))
    fields = {item.field: item for item in result.items}
    assert set(fields) == {
        "fs_read",
        "fs_write",
        "commands",
        "network",
        "tools",
        "operations",
        "external_effects",
        "effects_need_approval",
        "allowed_isolation",
    }
    assert list(fields["external_effects"].value) == ["git_commit"]
    assert fields["external_effects"].contributed_by[0].startswith("profile:workspace-contained")
    assert "ceiling" in fields["external_effects"].contributed_by
    assert "ceiling" in fields["network"].contributed_by or "ceiling" in fields["commands"].contributed_by


def test_explain_includes_the_role_and_task_layers(world: World) -> None:
    task: Any = {"effects": {"allow": ["git_commit"]}}
    result = world.ask(ExplainPermissions(scope_id=world.scope_id, task_layer=task))
    item = next(item for item in result.items if item.field == "external_effects")
    assert item.contributed_by[-1] == "task"
    assert item.value == ["git_commit"]


# ------------------------------------------------------------------------------------------ profiles
def test_the_three_builtin_profiles_are_listed_with_their_host_flag(world: World) -> None:
    result = world.ask(ListProfiles())
    profiles = {item.id: item for item in result.profiles}
    assert set(profiles) == set(builtin_profiles())
    assert all(item.builtin for item in profiles.values())
    assert profiles["trusted-full-access"].requires_host_flag is True
    assert profiles["workspace-contained"].requires_host_flag is False
    assert "none" not in profiles["workspace-contained"].allowed_isolation


# ------------------------------------------------------------------------------------------ check_tool_call
def test_a_write_in_the_worktree_is_allowed_and_one_outside_is_denied(world: World) -> None:
    inside = check(world, documents.ToolCallVariant2(tool="fs.write", path="/work/main/src/a.py"))
    assert (inside.outcome, inside.code) == ("allow", None)
    outside = check(world, documents.ToolCallVariant2(tool="fs.write", path="/etc/passwd"))
    assert (outside.outcome, outside.code) == ("deny", "path_outside_scope")


def test_a_push_is_not_a_direct_action_of_an_agent(world: World) -> None:
    decision = check(
        world, documents.ToolCallVariant5(tool="shell.run", command="git push origin main", cwd="/work/main")
    )
    assert decision.outcome == "deny"
    assert decision.code in {
        "requires_intent",
        "command_denied",
        "operation_denied",
    }


def test_an_unobserved_path_is_not_assumed_to_be_ours_to_delete(world: World) -> None:
    decision = check(world, documents.ToolCallVariant4(tool="fs.delete", path="/work/main/unknown.txt"))
    assert decision.outcome == "deny"


def test_the_read_only_profile_refuses_writes(world: World) -> None:
    decision = check(
        world, documents.ToolCallVariant2(tool="fs.write", path="/work/main/a.py"), profile_id="read-only"
    )
    assert decision.outcome == "deny"


def test_interactive_mode_asks_where_unattended_denies(world: World) -> None:
    call = documents.ToolCallVariant5(
        tool="shell.run", command="git push --force origin main", cwd="/work/main"
    )
    unattended = check(world, call)
    interactive = check(world, call, mode="interactive", interactive=True)
    assert unattended.outcome == "deny"
    assert interactive.outcome in {"deny", "ask"}


# ------------------------------------------------------------------------------------------ get_intent
def test_get_intent_needs_policy_read_on_the_scope_of_the_intent(world: World) -> None:
    proposed = propose(world)
    world.person("watcher", {world.workspace_id: Role.VIEWER})
    world.person("stranger", {})
    assert world.ask(GetIntent(intent_id=proposed.intent_id), "watcher").args_digest == proposed.args_digest
    with pytest.raises(Forbidden) as caught:
        world.ask(GetIntent(intent_id=proposed.intent_id), "stranger")
    assert caught.value.code is ErrorCode.FORBIDDEN
