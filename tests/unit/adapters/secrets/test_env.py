"""The environment adapter has an explicit, immutable source and safe failures."""

import json
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from skm.adapters.secrets.env import EnvSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.config.secrets import SecretRef

REF = SecretRef.parse("secret://env/SKM_TEST_SECRET")
TEXT = "synthetic-environment-secret-8346"


def test_only_explicit_environment_is_used(monkeypatch):
    monkeypatch.setenv(REF.path, "ambient-must-not-be-used")
    resolver = EnvSecretResolver({REF.path: TEXT})
    assert resolver.scheme == "env"
    assert resolver.resolve(REF) == TEXT
    with pytest.raises(ValidationFailed) as caught:
        EnvSecretResolver({}).resolve(REF)
    assert caught.value.code == ErrorCode.CONFIG_INVALID
    assert dict(caught.value.details) == {"ref": str(REF), "reason": "secret_unresolved"}
    assert "ambient-must-not-be-used" not in json.dumps(caught.value.to_problem())


def test_source_is_copied_and_not_exposed_by_repr():
    inputs = {REF.path: TEXT}
    resolver = EnvSecretResolver(inputs)
    inputs[REF.path] = "replacement-source"
    assert resolver.resolve(REF) == TEXT
    assert TEXT not in repr(resolver)
    with pytest.raises(FrozenInstanceError):
        cast(Any, resolver).scheme = "file"
    with pytest.raises(TypeError):
        cast(Any, resolver)._environ[REF.path] = "replacement-source"


@pytest.mark.parametrize("value", ["", "a", "with\nnewlines\n", " with whitespace "])
def test_environment_value_is_returned_verbatim(value):
    assert EnvSecretResolver({REF.path: value}).resolve(REF) == value


@pytest.mark.parametrize("ref", ["secret://file/SKM_TEST_SECRET", "secret://keyring/skm/test"])
def test_another_scheme_is_rejected_even_if_path_exists_in_environment(ref):
    parsed = SecretRef.parse(ref)
    with pytest.raises(ValidationFailed) as caught:
        EnvSecretResolver({parsed.path: TEXT}).resolve(parsed)
    assert dict(caught.value.details) == {"reason": "secret_ref_invalid"}
    assert TEXT not in json.dumps(caught.value.to_problem())
