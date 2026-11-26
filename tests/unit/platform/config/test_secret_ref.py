"""Only SecretRef's pure value contract; no secret is resolved by these operations."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.secrets import SecretRef


@pytest.mark.parametrize(
    "text", ["secret://env/SKM_TOKEN", "secret://file/~/.secrets/token", "secret://keyring/skm/user"]
)
def test_parse_string_round_trip(text):
    ref = SecretRef.parse(text)
    assert str(ref) == text
    assert SecretRef.parse(str(ref)) == ref
    assert not hasattr(ref, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, ref).path = "changed"


@pytest.mark.parametrize(
    "text",
    [
        "TOKEN_VALUE",
        "secret://env/lower",
        "secret://env/",
        "secret://file/a\nb",
        "secret://keyring/service",
        "secret://unknown/x",
        "secret://env/TOKEN\n",
        "secret://keyring/a/",
        "secret://env/" + "X" * 129,
    ],
)
def test_invalid_reference_never_enters_error_message(text):
    with pytest.raises(ValidationFailed) as caught:
        SecretRef.parse(text)
    assert caught.value.code == ErrorCode.CONFIG_INVALID
    assert dict(caught.value.details) == {"reason": "secret_ref_invalid"}
    assert text not in str(caught.value)


def test_direct_construction_also_enforces_value_contract():
    with pytest.raises(ValidationFailed):
        SecretRef("env", "invalid name")


def test_platform_and_generated_views_share_the_same_pure_value_type():
    from skm.kernel.generated._codec import SecretRef as GeneratedSecretRef
    from skm.kernel.generated._codec import convert

    assert SecretRef is GeneratedSecretRef
    text = "secret://env/SKM_TOKEN"
    value = convert(("secret", (), (), ()), text)
    assert type(value) is SecretRef
    assert convert(("secret", (), (), ()), value, encode=True) == text
