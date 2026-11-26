"""Unit tests for ``skm.modules.extensions.domain.override_rules`` (extensions §4.13)."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.override_rules import can_override
from skm.modules.extensions.domain.pack import PackTrust


def test_same_pack_update_is_not_an_override() -> None:
    decision = can_override(
        PackTrust.THIRD_PARTY,
        PackTrust.THIRD_PARTY,
        declared=frozenset(),
        kind=ResourceKind.SKILL,
        key="my-skill",
        same_pack=True,
    )
    assert decision.allowed is True
    assert decision.overrides is False


def test_undeclared_override_raises_conflict() -> None:
    with pytest.raises(Conflict) as exc_info:
        can_override(
            PackTrust.OPERATOR,
            PackTrust.BUILTIN,
            declared=frozenset(),
            kind=ResourceKind.PROMPT_BLOCK,
            key="shared/system",
        )
    assert exc_info.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert exc_info.value.details == {
        "kind": "prompt_block",
        "key": "shared/system",
        "owner_trust": "builtin",
    }


@pytest.mark.parametrize("owner_trust", [PackTrust.THIRD_PARTY, PackTrust.BUILTIN, PackTrust.OPERATOR])
def test_declared_override_with_sufficient_trust_succeeds(owner_trust: PackTrust) -> None:
    decision = can_override(
        PackTrust.OPERATOR,
        owner_trust,
        declared=frozenset({(ResourceKind.PROMPT_BLOCK, "shared/system")}),
        kind=ResourceKind.PROMPT_BLOCK,
        key="shared/system",
    )
    assert decision.allowed is True
    assert decision.overrides is True


def test_operator_overrides_builtin_when_declared_and_fails_when_undeclared() -> None:
    decision = can_override(
        PackTrust.OPERATOR,
        PackTrust.BUILTIN,
        declared=frozenset({(ResourceKind.PROMPT_BLOCK, "shared/system")}),
        kind=ResourceKind.PROMPT_BLOCK,
        key="shared/system",
    )
    assert decision.allowed is True
    assert decision.overrides is True
    assert decision.owner_trust is PackTrust.BUILTIN

    with pytest.raises(Conflict) as exc_info:
        can_override(
            PackTrust.OPERATOR,
            PackTrust.BUILTIN,
            declared=frozenset(),
            kind=ResourceKind.PROMPT_BLOCK,
            key="shared/system",
        )
    assert exc_info.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert exc_info.value.details["owner_trust"] == "builtin"


@pytest.mark.parametrize("owner_trust", [PackTrust.BUILTIN, PackTrust.OPERATOR])
def test_third_party_cannot_override_builtin_or_operator_even_when_declared(
    owner_trust: PackTrust,
) -> None:
    with pytest.raises(Conflict) as exc_info:
        can_override(
            PackTrust.THIRD_PARTY,
            owner_trust,
            declared=frozenset({(ResourceKind.SKILL, "review")}),
            kind=ResourceKind.SKILL,
            key="review",
        )
    assert exc_info.value.code is ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED
    assert exc_info.value.details["owner_trust"] == owner_trust.value
