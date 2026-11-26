"""policy §§4.5, 5.1, 5.12: built-in profiles, ``parse_profile``/``parse_layer`` refusals and composition."""

import copy
from collections.abc import Mapping
from importlib import resources
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.modules.policy.application.composition import (
    builtin_profiles,
    ceiling_layer,
    compose_effective,
    denylist_pattern,
    forbidden_paths_layer,
    restriction_layers,
    task_authority_from,
)
from skm.modules.policy.domain.calls import FileDelete, FileEdit, FileWrite, RunCommand
from skm.modules.policy.domain.commands import CommandMode
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import AccessCapability, OperationName
from skm.modules.policy.domain.paths import PathRule, PathScope, ScopedPath
from skm.modules.policy.domain.profiles import BUILTIN_PROFILE_IDS, PolicyProfile, parse_layer, parse_profile
from skm.modules.policy.domain.tool_call import Deny
from skm.modules.policy.domain.tool_intent import EffectKind
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry
from unit.policy.domain.layout import WT, CatalogConfig

PROFILE_URN = "urn:skm:policy:profile:v1"


def document(profile_id: str) -> dict[str, Any]:
    text = resources.files("skm.modules.policy").joinpath("profiles", f"{profile_id}.toml").read_text("utf-8")
    return decode_document(text, "toml")


def refused(doc: Mapping[str, Any], *, layer: bool = False) -> ValidationFailed:
    with pytest.raises(ValidationFailed) as caught:
        parse_layer(doc, source="test") if layer else parse_profile(doc)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    return caught.value


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


@pytest.mark.parametrize("profile_id", BUILTIN_PROFILE_IDS)
def test_builtin_profiles_pass_the_schema_and_parse(registry: SchemaRegistry, profile_id: str) -> None:
    doc = document(profile_id)
    assert registry.validate(PROFILE_URN, doc) == ()
    profile = parse_profile(doc)
    assert profile.id == profile_id
    assert set(profile.permissions.operations) == set(OperationName)
    assert profile.permissions.sources == (f"profile:{profile_id}@{profile.version}",)


def test_read_only_forbids_every_write_and_deletion(decide) -> None:
    for call in (
        FileWrite(f"{WT}/src/new.py"),
        FileEdit(f"{WT}/src/app.py"),
        FileDelete(f"{WT}/build/out.o"),
        FileWrite("/w/attempt/tmp/x"),
        RunCommand("touch src/new.py", WT),
        RunCommand("rm build/out.o", WT),
        RunCommand("echo x >> README.md", WT),
    ):
        assert isinstance(decide("read-only", call), Deny), call
    profile = builtin_profiles()["read-only"].permissions
    assert profile.external_effects == frozenset()
    assert profile.network.mode is NetworkMode.NONE


def test_trusted_full_access_needs_the_host_flag() -> None:
    config = CatalogConfig()
    with pytest.raises(Forbidden) as caught:
        compose_effective(
            config, profile_id="trusted-full-access", role_layer=None, task_layer=None, allow_unconfined=False
        )
    assert caught.value.details["reason"] == "unconfined_not_allowed_on_host"
    opened = CatalogConfig({"policy.ceiling.isolation_profiles": ["none", "worktree"]})
    perms = compose_effective(
        opened, profile_id="trusted-full-access", role_layer=None, task_layer=None, allow_unconfined=True
    )
    assert perms.allowed_isolation == {"none", "worktree"}


def test_workspace_contained_never_allows_isolation_none(profiles: Mapping[str, PolicyProfile]) -> None:
    assert "none" not in profiles["workspace-contained"].permissions.allowed_isolation
    assert "none" not in profiles["read-only"].permissions.allowed_isolation
    assert builtin_profiles()["trusted-full-access"].requires_host_flag


def test_without_the_host_flag_none_leaves_every_profile() -> None:
    custom = document("workspace-contained") | {"id": "with-none", "allowed_isolation": ["none", "worktree"]}
    config = CatalogConfig(
        {"policy.profiles": {"with-none": custom}, "policy.ceiling.isolation_profiles": ["none", "worktree"]}
    )
    closed = compose_effective(
        config, profile_id="with-none", role_layer=None, task_layer=None, allow_unconfined=False
    )
    opened = compose_effective(
        config, profile_id="with-none", role_layer=None, task_layer=None, allow_unconfined=True
    )
    assert closed.allowed_isolation == {"worktree"}
    assert opened.allowed_isolation == {"none", "worktree"}


@pytest.mark.parametrize("operation", [item.value for item in OperationName])
def test_a_missing_operation_is_schema_invalid(registry: SchemaRegistry, operation: str) -> None:
    doc = document("workspace-contained")
    del doc["operations"][operation]
    assert registry.validate(PROFILE_URN, doc) != ()
    assert refused(doc).details["pointer"] == f"/operations/{operation}"


@pytest.mark.parametrize(
    ("change", "pointer"),
    [
        (lambda doc: doc.update(extra=1), "/extra"),
        (
            lambda doc: doc["operations"].update(modify_write_set={"decision": "maybe"}),
            "/operations/modify_write_set/decision",
        ),
        (
            lambda doc: doc["operations"].update(docker_socket={"decision": "capability"}),
            "/operations/docker_socket/capability",
        ),
        (lambda doc: doc["commands"].update(mode="sometimes"), "/commands/mode"),
        (lambda doc: doc["commands"]["deny_patterns"].append("(unclosed"), "/commands/deny_patterns/6"),
        (lambda doc: doc["commands"]["subcommands"].update(git=[]), "/commands/subcommands/git"),
        (lambda doc: doc["network"].update(hosts=[]), "/network/hosts"),
        (
            lambda doc: doc["fs"]["read"]["allow"].append({"scope": "worktree", "pattern": "../x"}),
            "/fs/read/allow/4/pattern",
        ),
        (
            lambda doc: doc["fs"]["read"]["allow"].append({"scope": "tmp", "pattern": "x", "mount": "main"}),
            "/fs/read/allow/4/mount",
        ),
        (lambda doc: doc.update(allowed_isolation=[]), "/allowed_isolation"),
        (lambda doc: doc.update(allowed_isolation=["firejail"]), "/allowed_isolation/0"),
        (lambda doc: doc["tools"]["allow"].append("shell.exec"), "/tools/allow/8"),
        (lambda doc: doc.update(schema="urn:skm:policy:profile:v2"), "/schema"),
    ],
)
def test_profile_defects_are_schema_invalid(registry: SchemaRegistry, change, pointer: str) -> None:
    doc = copy.deepcopy(document("workspace-contained"))
    change(doc)
    error = refused(doc)
    assert error.details["pointer"] == pointer
    assert registry.validate(PROFILE_URN, doc) != ()


def test_regex_error_reports_its_index() -> None:
    doc = copy.deepcopy(document("workspace-contained"))
    doc["commands"]["ask_patterns"] = ["ok", "[bad"]
    assert refused(doc).details["index"] == 1


def test_layer_semantics_of_absent_and_empty_fields() -> None:
    assert parse_layer({}, source="s") == parse_layer({}, source="s")
    nothing = parse_layer({}, source="s")
    assert (nothing.fs_read, nothing.commands, nothing.network, nothing.tools, nothing.allowed_isolation) == (
        None,
        None,
        None,
        None,
        None,
    )
    empty = parse_layer(
        {
            "tools": {"allow": []},
            "network": {"hosts": []},
            "allowed_isolation": [],
            "effects": {"allow": []},
            "commands": {"subcommands": {"git": []}},
        },
        source="s",
    )
    assert empty.tools == frozenset()
    assert empty.network == NetworkLayer(None, frozenset())
    assert empty.allowed_isolation == frozenset()
    assert empty.external_effects == frozenset()
    assert empty.commands is not None
    assert empty.commands.allow == ()
    deny_only = parse_layer(
        {"fs": {"write": {"deny": [{"scope": "worktree", "pattern": "*.lock"}]}}}, source="s"
    )
    assert deny_only.fs_write is not None
    assert not deny_only.fs_write.allows(ScopedPath(PathScope.WORKTREE, "main", "uv.lock"))
    assert deny_only.fs_write.allows(
        ScopedPath(PathScope.ANY, None, "etc/x")
    )  # a deny-only layer adds no allow limit


@pytest.mark.parametrize(
    "doc",
    [
        {"operations": {"unknown_operation": {"decision": "deny"}}},
        {"network": {"mode": "none", "hosts": ["pypi.org"]}},
        {"id": "x"},
        {"allowed_isolation": ["bogus"]},
    ],
)
def test_layer_defects_are_schema_invalid(registry: SchemaRegistry, doc: dict[str, Any]) -> None:
    refused(doc, layer=True)
    assert registry.validate("urn:skm:policy:permission-layer:v1", doc) != ()


def test_layer_schema_accepts_explicit_empty_restrictions(registry: SchemaRegistry) -> None:
    doc = {
        "network": {"mode": "allowlist", "hosts": []},
        "allowed_isolation": [],
        "commands": {"subcommands": {"git": []}},
    }
    assert registry.validate("urn:skm:policy:permission-layer:v1", doc) == ()


def test_custom_profile_cannot_shadow_a_builtin(registry: SchemaRegistry) -> None:
    doc = document("read-only")
    assert registry.validate("urn:skm:settings:policy:v1", {"profiles": {"read-only": doc}}) != ()
    assert (
        registry.validate("urn:skm:settings:policy:v1", {"profiles": {"my-ro": doc | {"id": "my-ro"}}}) == ()
    )
    config = CatalogConfig({"policy.profiles": {"read-only": doc}})
    with pytest.raises(ValidationFailed) as caught:
        compose_effective(config, profile_id=None, role_layer=None, task_layer=None, allow_unconfined=False)
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_unknown_profile_is_config_invalid() -> None:
    with pytest.raises(ValidationFailed) as caught:
        compose_effective(
            CatalogConfig(), profile_id="missing", role_layer=None, task_layer=None, allow_unconfined=False
        )
    assert (caught.value.code, caught.value.details["reason"]) == (
        ErrorCode.CONFIG_INVALID,
        "unknown_profile",
    )


def test_custom_profile_from_configuration() -> None:
    doc = document("read-only") | {"id": "audit"}
    perms = compose_effective(
        CatalogConfig({"policy.profiles": {"audit": doc}}),
        profile_id="audit",
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    assert perms.sources[0] == "profile:audit@1.0.0"


def test_interactive_profile_key() -> None:
    config = CatalogConfig({"policy.default_profile": "missing", "policy.interactive.profile": "read-only"})
    perms = compose_effective(
        config, profile_id=None, role_layer=None, task_layer=None, allow_unconfined=False, interactive=True
    )
    assert perms.sources[0].startswith("profile:read-only@")


def test_ceiling_layer_from_catalog_defaults() -> None:
    layer = ceiling_layer(CatalogConfig())
    assert layer.network is not None
    assert (layer.network.mode, layer.network.hosts) == (NetworkMode.ALLOWLIST, frozenset())
    assert layer.external_effects == {EffectKind.GIT_COMMIT}
    assert layer.effects_need_approval == {
        EffectKind.GIT_PUSH,
        EffectKind.PR_CREATE,
        EffectKind.MESSAGE,
        EffectKind.PUBLISH,
        EffectKind.FS_WRITE_EXTERNAL,
    }
    assert layer.allowed_isolation == {"worktree", "landlock", "container"}
    assert layer.commands is not None
    assert layer.commands.mode is None
    assert len(layer.commands.deny_patterns) == 3


def test_ceiling_shell_false_disables_commands_and_the_shell_tool() -> None:
    perms = compose_effective(
        CatalogConfig({"policy.ceiling.shell": False}),
        profile_id=None,
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    assert perms.commands.mode is CommandMode.NONE
    assert all("shell.run" not in tools for tools in perms.tools[1:])


def test_denylist_prefix_pattern() -> None:
    import re

    pattern = re.compile(denylist_pattern("git push --force"))
    assert pattern.search("git push --force origin")
    assert pattern.search("ls; git push --force")
    assert not pattern.search("git push --force-with-lease")
    assert not pattern.search("echo git push --force")


def test_restrictions_apply_in_order_with_sources() -> None:
    config = CatalogConfig(
        {"policy.restrictions": [{"tools": {"allow": ["fs.read"]}}, {"network": {"mode": "none"}}]}
    )
    layers = restriction_layers(config)
    assert [layer.source for layer in layers] == ["restriction:0", "restriction:1"]
    perms = compose_effective(
        config, profile_id=None, role_layer=None, task_layer=None, allow_unconfined=False
    )
    assert perms.network.mode is NetworkMode.NONE
    assert frozenset({"fs.read"}) in perms.tools
    assert perms.sources[1:] == ("ceiling", "restriction:0", "restriction:1")


def test_a_restriction_that_is_not_a_layer_is_refused() -> None:
    with pytest.raises(ValidationFailed):
        restriction_layers(CatalogConfig({"policy.restrictions": ["tools"]}))


def test_task_authority_capabilities_are_granted_and_allowed() -> None:
    config = CatalogConfig(
        {
            "policy.access_capabilities.allowed": ["secrets", "docker_socket"],
            "policy.access_capabilities.granted": ["docker_socket", "external_services"],
            "policy.task_authority.operations": ["git_discard"],
        }
    )
    authority = task_authority_from(config, write_scope=None)
    assert authority.capabilities == {AccessCapability.DOCKER_SOCKET}
    assert authority.operations == {OperationName.GIT_DISCARD}


def test_forbidden_paths_layer_denies_writes_only() -> None:
    layer = forbidden_paths_layer((("main", "secrets/**"), ("", "*.pem")), source="task:P1")
    assert layer.fs_read is None
    assert layer.fs_write is not None
    assert layer.fs_write.deny == (
        PathRule(PathScope.WORKTREE, "secrets/**", "main"),
        PathRule(PathScope.WORKTREE, "*.pem", None),
    )


def test_policy_profiles_are_not_extension_resources(registry: SchemaRegistry) -> None:
    defs = cast("Mapping[str, Any]", registry.get("urn:skm:extensions:defs:v1"))
    kinds = defs["$defs"]["resource_kind"]["enum"]
    assert "policy_profile" not in kinds
    assert "policy-profile" not in kinds
