"""policy §§5.11, 5.12, 13: proofs of representation, isolation grants, the view, ``is_subset``, the digest.

A consumer that can express only one path policy, one operation row or one host list either receives an
equivalent single form or a refusal (``CAPABILITY_UNAVAILABLE``); it never receives a wider one.
"""

from collections.abc import Mapping
from dataclasses import replace
from importlib import resources
from typing import cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.policy import public
from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.domain.calls import RunCommand, WebAccess
from skm.modules.policy.domain.network import NetworkLayer, NetworkMode
from skm.modules.policy.domain.operations import AccessCapability, OperationName, OperationRule, Requirement
from skm.modules.policy.domain.paths import PathPolicy, PathRule, PathScope
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow, narrow_all
from skm.modules.policy.domain.profiles import BUILTIN_PROFILE_IDS, PolicyProfile, parse_profile
from skm.modules.policy.domain.render import (
    isolation_grants,
    operation_document,
    representable_paths,
    view_document,
)
from skm.platform.config.sources.document import decode_document
from skm.platform.schema.registry import SchemaRegistry
from unit.policy.domain.layout import EMPTY, FACTS, HOME, ROOTS, WT

ALL = PathRule(PathScope.WORKTREE, "**")
SRC = PathRule(PathScope.WORKTREE, "src/**")
DOCS = PathRule(PathScope.WORKTREE, "docs/**")
PY = PathRule(PathScope.WORKTREE, "*.py")
READABLE = tuple(
    PathRule(scope, "**")
    for scope in (PathScope.WORKTREE, PathScope.MATERIALS, PathScope.TMP, PathScope.SAFE_DIR)
)


def perms(profile_id: str, *layers: PermissionLayer) -> PermissionSet:
    return narrow_all(builtin_profiles()[profile_id].permissions, layers)


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def test_representable_paths_by_prefix() -> None:
    merged = representable_paths(
        (PathPolicy((ALL,), (PathRule(PathScope.WORKTREE, "*.lock"),)), PathPolicy((SRC,), (DOCS,)))
    )
    assert merged == PathPolicy((SRC,), (PathRule(PathScope.WORKTREE, "*.lock"), DOCS))
    assert representable_paths(
        (PathPolicy((SRC,), ()), PathPolicy((PathRule(PathScope.WORKTREE, "src/a/**"),), ()))
    ) == (PathPolicy((PathRule(PathScope.WORKTREE, "src/a/**"),), ()))
    # a mount-bound rule is inside the same rule for any mount
    main_src = PathRule(PathScope.WORKTREE, "src/**", "main")
    assert representable_paths((PathPolicy((SRC,), ()), PathPolicy((main_src,), ()))) == PathPolicy(
        (main_src,), ()
    )


@pytest.mark.parametrize(
    "policies",
    [
        (PathPolicy((SRC,), ()), PathPolicy((DOCS,), ())),
        (PathPolicy((SRC,), ()), PathPolicy((PY,), ())),
        (
            PathPolicy((PathRule(PathScope.WORKTREE, "src/**", "main"),), ()),
            PathPolicy((PathRule(PathScope.WORKTREE, "src/**", "lib"),), ()),
        ),
        (PathPolicy((SRC, DOCS), ()), PathPolicy((SRC,), ()), PathPolicy((DOCS,), ())),
        (
            PathPolicy((PathRule(PathScope.ANY, "**"),), ()),
            PathPolicy((PathRule(PathScope.HOME, "x/**"),), ()),
        ),
        (),
    ],
)
def test_unprovable_conjunctions_are_refused(policies: tuple[PathPolicy, ...]) -> None:
    assert representable_paths(policies) is None


def test_isolation_grants_never_include_home_under_landlock() -> None:
    grants = isolation_grants(perms("workspace-contained"), ROOTS, "landlock")
    assert grants.rw_paths == (WT, "/w/attempt/tmp")
    assert grants.ro_paths == ("/w/attempt/materials", "/opt/cache")
    assert HOME not in grants.rw_paths + grants.ro_paths


def test_isolation_grants_of_a_narrowed_worktree() -> None:
    layer = PermissionLayer("task", fs_write=PathPolicy((SRC,), ()))
    grants = isolation_grants(perms("workspace-contained", layer), ROOTS, "container")
    # the task layer allows no tmp write, so tmp is not granted either
    assert grants.rw_paths == (f"{WT}/src",)
    assert WT in grants.ro_paths


def test_isolation_grants_refuse_a_profile_outside_the_permission_set() -> None:
    with pytest.raises(CapabilityUnavailable) as caught:
        isolation_grants(perms("workspace-contained"), ROOTS, "none")
    assert caught.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    nothing = perms("workspace-contained", PermissionLayer("l", allowed_isolation=frozenset()))
    for profile in ("none", "worktree", "landlock", "container"):
        with pytest.raises(CapabilityUnavailable):
            isolation_grants(nothing, ROOTS, profile)


def _refused(permissions: PermissionSet, profile: str = "container") -> dict[str, JsonValue]:
    with pytest.raises(CapabilityUnavailable) as caught:
        public.isolation_grants(permissions, ROOTS, profile)
    assert caught.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert caught.value.details["reason"] == "restriction_not_representable"
    return dict(caught.value.details)


@pytest.mark.parametrize(
    ("layer", "field"),
    [
        # a deny rule inside the writable worktree (task forbidden paths)
        (public.forbidden_paths_layer((("main", "secrets/**"),), source="task"), "fs_write"),
        (PermissionLayer("t", fs_write=PathPolicy((ALL, PathRule(PathScope.TMP, "**")), (PY,))), "fs_write"),
        # a deny rule inside a writable subdirectory
        (
            PermissionLayer("t", fs_write=PathPolicy((SRC,), (PathRule(PathScope.WORKTREE, "src/gen/**"),))),
            "fs_write",
        ),
        # a read deny inside a writable (hence readable) root
        (
            PermissionLayer("t", fs_read=PathPolicy((ALL,), (PathRule(PathScope.WORKTREE, "**/.env"),))),
            "fs_read",
        ),
        # a writable root that fs_read does not allow (tmp is not readable here)
        (PermissionLayer("t", fs_read=PathPolicy((ALL,), ())), "fs_read"),
        # a read deny inside a read-only root
        (
            PermissionLayer(
                "t", fs_read=PathPolicy(READABLE, (PathRule(PathScope.MATERIALS, "private/**"),))
            ),
            "fs_read",
        ),
    ],
)
def test_isolation_grants_refuse_a_deny_rule_a_directory_cannot_carry(
    layer: PermissionLayer, field: str
) -> None:
    assert _refused(perms("workspace-contained", layer))["field"] == field


def test_isolation_grants_keep_a_deny_rule_outside_every_granted_directory() -> None:
    layer = PermissionLayer("task", fs_write=PathPolicy((SRC,), (DOCS,)))
    grants = isolation_grants(perms("workspace-contained", layer), ROOTS, "container")
    assert grants.rw_paths == (f"{WT}/src",)


def test_isolation_grants_honour_explicit_empty_allows() -> None:
    nothing_written = perms("workspace-contained", PermissionLayer("t", fs_write=PathPolicy((), ())))
    grants = public.isolation_grants(nothing_written, ROOTS, "landlock")
    assert grants.rw_paths == ()
    assert WT in grants.ro_paths
    # read only the worktree and tmp: materials and safe dirs are not readable, so not granted
    worktree_only = PermissionLayer("t", fs_read=PathPolicy((ALL, PathRule(PathScope.TMP, "**")), ()))
    grants = public.isolation_grants(perms("workspace-contained", worktree_only), ROOTS, "landlock")
    assert grants.ro_paths == ()
    assert grants.rw_paths == (WT, "/w/attempt/tmp")
    nothing_read = perms("read-only", PermissionLayer("t", fs_read=PathPolicy((), ())))
    assert public.isolation_grants(nothing_read, ROOTS, "landlock") == public.IsolationGrants(
        "landlock", (), ()
    )


def test_isolation_grants_of_a_mount_bound_subdirectory_need_every_policy() -> None:
    main_src = PathRule(PathScope.WORKTREE, "src/**", "main")
    other = PermissionLayer("t", fs_write=PathPolicy((PathRule(PathScope.WORKTREE, "src/**", "lib"),), ()))
    assert isolation_grants(perms("workspace-contained", other), ROOTS, "container").rw_paths == ()
    own = PermissionLayer("t", fs_write=PathPolicy((main_src,), ()))
    assert isolation_grants(perms("workspace-contained", own), ROOTS, "container").rw_paths == (f"{WT}/src",)


def test_isolation_none_may_add_home() -> None:
    grants = isolation_grants(perms("trusted-full-access"), ROOTS, "none")
    assert HOME in grants.rw_paths


@pytest.mark.parametrize("profile_id", BUILTIN_PROFILE_IDS)
def test_operation_rows_render_back_to_themselves(
    profiles: Mapping[str, PolicyProfile], profile_id: str
) -> None:
    for name, rule in profiles[profile_id].permissions.operations.items():
        doc = operation_document(rule)
        reparsed = parse_profile(
            _profile_doc(profiles[profile_id])
            | {"operations": {**_rows(profiles[profile_id]), name.value: doc}}
        )
        assert reparsed.permissions.operations[name] == rule


@pytest.mark.parametrize(
    "rule",
    [
        OperationRule(
            requires=frozenset({Requirement.TASK_AUTHORITY}),
            capabilities=frozenset({AccessCapability.SECRETS}),
        ),
        OperationRule(capabilities=frozenset({AccessCapability.SECRETS, AccessCapability.DOCKER_SOCKET})),
        OperationRule(requires=frozenset({Requirement.TASK_AUTHORITY}), warn=True),
    ],
)
def test_an_unrepresentable_operation_is_a_capability_refusal(rule: OperationRule) -> None:
    with pytest.raises(CapabilityUnavailable) as caught:
        operation_document(rule)
    assert caught.value.details["reason"] == "permissions_not_representable"


def test_unrepresentable_conjunction_does_not_widen_the_view() -> None:
    layer = PermissionLayer(
        "role",
        operations={
            OperationName.DELETE_TRACKED: OperationRule(capabilities=frozenset({AccessCapability.SECRETS}))
        },
    )
    with pytest.raises(CapabilityUnavailable):
        view_document(perms("workspace-contained", layer))


@pytest.mark.parametrize("profile_id", BUILTIN_PROFILE_IDS)
def test_view_round_trip_keeps_the_digest(registry: SchemaRegistry, profile_id: str) -> None:
    original = perms(profile_id, PermissionLayer("task", fs_write=PathPolicy((SRC,), (DOCS,))))
    doc = view_document(original) | {"digest": public.permissions_digest(original)}
    assert registry.validate("urn:skm:policy:view:permission-set:v1", doc) == ()
    restored = public.permission_set_from_view(doc)
    assert public.permissions_digest(restored) == public.permissions_digest(original)


EMPTY_CONJUNCTIONS = (
    ("workspace-contained", NetworkLayer(hosts=frozenset())),
    ("workspace-contained", NetworkLayer(hosts=frozenset({"example.com"}))),
    ("workspace-contained", NetworkLayer(mode=NetworkMode.ALLOWLIST, hosts=frozenset())),
    ("trusted-full-access", NetworkLayer(mode=NetworkMode.ALLOWLIST)),
)


VIEW_V1 = "urn:skm:policy:view:permission-set:v1"
VIEW_V2 = "urn:skm:policy:view:permission-set:v2"


def view_of(permissions: PermissionSet) -> dict[str, JsonValue]:
    return view_document(permissions) | {"digest": public.permissions_digest(permissions)}


def decide_interactive(permissions: PermissionSet, call: public.ToolCall) -> public.ToolDecision:
    return public.check_tool_call(
        permissions, call, roots=ROOTS, facts=FACTS, authority=EMPTY, mode=public.EnforcementMode.INTERACTIVE
    )


@pytest.mark.parametrize(("profile_id", "layer"), EMPTY_CONJUNCTIONS)
def test_empty_host_conjunction_round_trips_through_the_view(
    registry: SchemaRegistry, profile_id: str, layer: NetworkLayer
) -> None:
    closed = perms(profile_id, PermissionLayer("ceiling", network=layer))
    assert closed.network.mode is NetworkMode.ALLOWLIST
    doc = view_of(closed)
    assert doc["network"] == {"mode": "allowlist", "hosts": []}
    assert registry.validate(VIEW_V2, doc) == ()
    assert registry.validate(VIEW_V1, doc) != ()  # the state is what the new major adds
    restored = public.permission_set_from_view(doc)
    assert restored.network.mode is NetworkMode.ALLOWLIST
    assert public.permissions_digest(restored) == doc["digest"]
    for call in (
        WebAccess("web.search", None, "query"),
        WebAccess("web.fetch", "https://example.com/x", None),
        WebAccess("web.fetch", "https://pypi.org/simple", None),
        RunCommand("wget", WT),
    ):
        assert decide_interactive(restored, call) == decide_interactive(closed, call), call


def test_an_allowlist_without_a_host_is_neither_none_nor_open() -> None:
    closed = perms("workspace-contained", PermissionLayer("ceiling", network=NetworkLayer(hosts=frozenset())))
    offline = perms(
        "workspace-contained", PermissionLayer("ceiling", network=NetworkLayer(mode=NetworkMode.NONE))
    )
    restored = public.permission_set_from_view(view_of(closed))
    search = WebAccess("web.search", None, "query")
    fetch = WebAccess("web.fetch", "https://pypi.org/simple", None)
    wget = RunCommand("wget", WT)
    assert decide_interactive(restored, search) == public.Allow()
    assert isinstance(decide_interactive(offline, search), public.Deny)
    assert isinstance(decide_interactive(restored, wget), public.Ask)
    assert isinstance(decide_interactive(offline, wget), public.Deny)
    assert isinstance(decide_interactive(restored, fetch), public.Deny)
    assert not restored.network.allows("pypi.org", 443)


@pytest.mark.parametrize(
    "network",
    [
        {"mode": "none", "hosts": ["pypi.org"]},
        {"mode": "any", "hosts": ["pypi.org"]},
        {"mode": "allowlist", "hosts": ["NOT A HOST"]},
        {"mode": "allowlist", "hosts": ["pypi.org", "pypi.org"]},
        {"mode": "allowlist"},
        {"hosts": []},
        {"mode": "everything", "hosts": []},
        {"mode": "allowlist", "hosts": [], "extra": True},
    ],
)
def test_the_view_refuses_any_other_network_form(registry: SchemaRegistry, network: JsonValue) -> None:
    doc = view_of(perms("workspace-contained")) | {"network": network}
    assert registry.validate(VIEW_V2, doc) != ()
    with pytest.raises(ValidationFailed):
        public.permission_set_from_view(doc)


def test_a_profile_still_states_no_host_as_mode_none(registry: SchemaRegistry) -> None:
    text = resources.files("skm.modules.policy").joinpath("profiles", "read-only.toml").read_text("utf-8")
    document = decode_document(text, "toml")
    urn = "urn:skm:policy:profile:v1"
    assert registry.validate(urn, document) == ()
    empty = document | {"network": {"mode": "allowlist", "hosts": []}}
    assert registry.validate(urn, empty) != ()
    with pytest.raises(ValidationFailed):
        parse_profile(empty)


@pytest.mark.parametrize("profile_id", BUILTIN_PROFILE_IDS)
def test_a_view_of_the_first_major_stays_a_view(registry: SchemaRegistry, profile_id: str) -> None:
    doc = view_of(
        perms(profile_id, PermissionLayer("c", network=NetworkLayer(hosts=frozenset({"pypi.org"}))))
    )
    assert registry.validate(VIEW_V1, doc) == ()
    assert registry.validate(VIEW_V2, doc) == ()
    assert public.permission_set_from_view(doc).network.mode is NetworkMode(
        cast("dict[str, JsonValue]", doc["network"])["mode"]
    )


@pytest.mark.parametrize(
    ("layer", "network"),
    [
        (
            NetworkLayer(hosts=frozenset({"pypi.org", "example.com"})),
            {"mode": "allowlist", "hosts": ["pypi.org"]},
        ),
        (NetworkLayer(mode=NetworkMode.NONE, hosts=frozenset()), {"mode": "none", "hosts": []}),
    ],
)
def test_a_representable_network_stays_in_the_view(
    layer: NetworkLayer, network: dict[str, JsonValue]
) -> None:
    assert (
        view_document(perms("workspace-contained", PermissionLayer("c", network=layer)))["network"] == network
    )


def test_digest_ignores_sources_and_set_order() -> None:
    a = perms("workspace-contained")
    b = narrow(a, PermissionLayer("another-source"))
    assert public.permissions_digest(a) == public.permissions_digest(b)
    assert public.permissions_digest(a).startswith("sha256:")
    assert public.permissions_digest(a) != public.permissions_digest(perms("read-only"))


def test_is_subset_accepts_a_narrower_request() -> None:
    request = {
        "profile_id": "workspace-contained",
        "fs": {"write": {"allow": [{"scope": "worktree", "pattern": "src/**"}]}},
        "network": {"mode": "allowlist", "hosts": ["pypi.org"]},
        "tools": {"allow": ["fs.read", "shell.run"]},
        "effects": {"allow": ["git_commit"], "need_approval": []},
        "operations": {
            "git_force_push": {"decision": "deny"},
            "modify_outside_write_set": {"decision": "deny"},
        },
        "allowed_isolation": ["container"],
    }
    assert public.is_subset(request, perms("workspace-contained")) == ()


@pytest.mark.parametrize(
    ("request_doc", "field"),
    [
        ({"network": {"mode": "any"}}, "network.mode"),
        ({"network": {"hosts": ["example.com"]}}, "network.hosts"),
        ({"network": {"hosts": ["*.org"]}}, "network.hosts"),
        ({"tools": {"allow": ["mcp:*"]}}, "tools"),
        ({"operations": {"git_force_push": {"decision": "allow"}}}, "operations.git_force_push"),
        ({"operations": {"git_push": {"decision": "ask"}}}, "operations.git_push"),
        ({"operations": {"secrets_access": {"decision": "allow"}}}, "operations.secrets_access"),
        ({"effects": {"allow": ["publish"]}}, "external_effects"),
        ({"effects": {"allow": ["git_push"], "need_approval": []}}, "effects_need_approval"),
        ({"allowed_isolation": ["none"]}, "allowed_isolation"),
        ({"fs": {"write": {"allow": [{"scope": "home", "pattern": "**"}]}}}, "fs_write"),
        (
            {"commands": {"mode": "denylist", "trust_inline_interpreters": True}},
            "commands.trust_inline_interpreters",
        ),
        ({"commands": {"mode": "denylist", "deny_patterns": []}}, "commands.deny_patterns"),
    ],
)
def test_is_subset_reports_every_widening(request_doc: dict[str, JsonValue], field: str) -> None:
    found = public.is_subset(request_doc, perms("workspace-contained"))
    assert field in {violation.field for violation in found}, found


def test_is_subset_accepts_a_view_document_as_ceiling() -> None:
    ceiling = perms("read-only")
    view = view_document(ceiling) | {"digest": public.permissions_digest(ceiling)}
    own: dict[str, JsonValue] = {**cast("dict[str, JsonValue]", view["commands"]), "subcommands": {}}
    ls: dict[str, JsonValue] = {"commands": {**own, "programs": ["ls"]}}
    make: dict[str, JsonValue] = {"commands": {**own, "programs": ["make"]}}
    assert public.is_subset(ls, view) == ()
    assert {v.field for v in public.is_subset(make, view)} == {"commands.allow"}
    # a request that omits the ceiling's deny patterns would run without them: widening
    bare = public.is_subset({"commands": {"mode": "allowlist", "programs": ["ls"]}}, view)
    assert "commands.deny_patterns" in {v.field for v in bare}


NAMES = r"(^|[^a-z])(kill|mount)(\s|$)"


@pytest.mark.parametrize(
    "own",
    [
        NAMES,
        r"(^|[^a-z])(mount|kill)(\s|$)",
        r"(^|[^a-z])(kill|mount|ssh)(\s|$)",
        r"(^|[^a-z])(kill|mount|ssh)",
    ],
)
def test_a_pattern_of_the_ceiling_is_kept_by_a_provably_wider_one(own: str) -> None:
    ceiling = _ceiling_with_ask(NAMES)
    assert public.is_subset({"commands": {"ask_patterns": [own]}}, ceiling) == ()


@pytest.mark.parametrize(
    "own",
    [
        r"(^|[^a-z])(kill)(\s|$)",  # a name is missing
        r"(^|[^a-zA-Z])(kill|mount)(\s|$)",  # another prefix
        r"(^|[^a-z])(kill|mount)$",  # another tail
        r"(^|[^a-z])(kill|mount)(\s)",  # a narrower tail
        r"(^|[^a-z])(kill|mount|x.*)(\s|$)",  # not a list of names
        r"x(^|[^a-z])(kill|mount)(\s|$)",  # a longer prefix
        r"((^|[^a-z])(kill|mount)(\s|$))?z",  # the names are not at the top level
    ],
)
def test_a_pattern_without_a_proof_is_still_dropped(own: str) -> None:
    found = public.is_subset({"commands": {"ask_patterns": [own]}}, _ceiling_with_ask(NAMES))
    assert [(v.field, v.reason, v.detail) for v in found] == [
        ("commands.ask_patterns", "drops_pattern", NAMES)
    ]


@pytest.mark.parametrize("limit", [r"[(kill|mount)]", r"\(kill|mount\)", r"(k.ll|mount)", r"(?:kill|mount)"])
def test_a_ceiling_pattern_of_another_shape_needs_its_exact_text(limit: str) -> None:
    ceiling = _ceiling_with_ask(limit)
    assert public.is_subset({"commands": {"ask_patterns": [limit]}}, ceiling) == ()
    found = public.is_subset({"commands": {"ask_patterns": [r"(kill|mount|ssh)"]}}, ceiling)
    assert {v.field for v in found} == {"commands.ask_patterns"}


def test_the_proof_covers_deny_patterns_too() -> None:
    ceiling = _ceiling(deny_patterns=(NAMES,))
    wider: dict[str, JsonValue] = {"commands": {"deny_patterns": [r"(^|[^a-z])(kill|mount|ssh)"]}}
    narrower: dict[str, JsonValue] = {"commands": {"deny_patterns": [r"(^|[^a-z])(kill)"]}}
    assert public.is_subset(wider, ceiling) == ()
    assert {v.field for v in public.is_subset(narrower, ceiling)} == {"commands.deny_patterns"}


def _ceiling_with_ask(pattern: str) -> PermissionSet:
    return _ceiling(ask_patterns=(pattern,))


def _ceiling(*, ask_patterns: tuple[str, ...] = (), deny_patterns: tuple[str, ...] = ()) -> PermissionSet:
    """The default profile whose commands carry only the given patterns."""
    base = builtin_profiles()["workspace-contained"].permissions
    commands = replace(
        base.commands,
        ask_patterns=ask_patterns,
        deny_patterns=deny_patterns,
        inline_interpreters=frozenset[str](),
    )
    return replace(base, commands=commands)


def test_permission_request_schema(registry: SchemaRegistry) -> None:
    urn = "urn:skm:policy:permission-request:v1"
    assert (
        registry.validate(urn, {"profile_id": "workspace-contained", "tools": {"allow": ["fs.read"]}}) == ()
    )
    assert registry.validate(urn, {"operations": {"bogus": {"decision": "deny"}}}) != ()
    assert registry.validate(urn, {"profile_id": "Bad Id"}) != ()


def _profile_doc(profile: PolicyProfile) -> dict[str, JsonValue]:
    text = resources.files("skm.modules.policy").joinpath("profiles", f"{profile.id}.toml").read_text("utf-8")
    return decode_document(text, "toml")


def _rows(profile: PolicyProfile) -> dict[str, JsonValue]:
    return {name.value: operation_document(rule) for name, rule in profile.permissions.operations.items()}
