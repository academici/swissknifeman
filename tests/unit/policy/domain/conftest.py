"""Shared fixtures of the policy domain tests: one attempt layout, observed path facts, built-in profiles."""

from collections.abc import Callable, Mapping

import pytest

from skm.modules.policy.application.composition import builtin_profiles
from skm.modules.policy.domain.calls import ToolCall
from skm.modules.policy.domain.operations import StaticPathFacts, TaskAuthority
from skm.modules.policy.domain.paths import ScopeRoots
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow_all
from skm.modules.policy.domain.profiles import PolicyProfile
from skm.modules.policy.domain.tool_call import EnforcementMode, ToolDecision, check_tool_call
from unit.policy.domain.layout import EMPTY, FACTS, ROOTS

type Decide = Callable[..., ToolDecision]


@pytest.fixture
def profiles() -> Mapping[str, PolicyProfile]:
    return builtin_profiles()


@pytest.fixture
def roots() -> ScopeRoots:
    return ROOTS


@pytest.fixture
def facts() -> StaticPathFacts:
    return FACTS


@pytest.fixture
def empty_authority() -> TaskAuthority:
    return EMPTY


@pytest.fixture
def perms() -> Callable[..., PermissionSet]:
    return perms_of


def perms_of(profile_id: str, *layers: PermissionLayer) -> PermissionSet:
    return narrow_all(builtin_profiles()[profile_id].permissions, layers)


@pytest.fixture
def decide() -> Decide:
    """``decide(profile_or_perms, call, authority=EMPTY, mode=unattended, layers=())``."""

    def run(
        profile: str | PermissionSet,
        call: ToolCall,
        *,
        authority: TaskAuthority = EMPTY,
        mode: EnforcementMode = EnforcementMode.AGENT_UNATTENDED,
        layers: tuple[PermissionLayer, ...] = (),
        reference: bool = True,
    ) -> ToolDecision:
        perms = perms_of(profile, *layers) if isinstance(profile, str) else narrow_all(profile, layers)
        commands = builtin_profiles()["read-only"].permissions.commands if reference else None
        return check_tool_call(
            perms, call, roots=ROOTS, facts=FACTS, authority=authority, mode=mode, reference=commands
        )

    return run
