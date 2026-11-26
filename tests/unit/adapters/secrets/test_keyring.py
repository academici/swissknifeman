import sys
from types import SimpleNamespace

import pytest

from skm.adapters.secrets.keyring import KeyringSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed
from skm.platform.config.secrets import SecretRef, SecretResolvers

REF = SecretRef.parse("secret://keyring/skm-team/cli-token")


def test_keyring_resolves_only_requested_entry(monkeypatch):
    seen = []
    registered = []

    def get_password(service, name):
        seen.append((service, name))
        return "private-password"

    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_password=get_password))
    secret = SecretResolvers((KeyringSecretResolver(),), on_reveal=registered.append).resolve(REF)
    assert seen == [("skm-team", "cli-token")]
    assert registered == [secret.reveal()] == ["private-password"]
    assert "private-password" not in repr(secret)


@pytest.mark.parametrize("failure", ["absent", "missing", "locked"])
@pytest.mark.parametrize("composed", [False, True])
def test_keyring_failure_is_typed_and_has_no_secret_cause(monkeypatch, failure, composed):
    def get_password(*_args):
        if failure == "locked":
            raise RuntimeError("private-password")
        return

    module = None if failure == "absent" else SimpleNamespace(get_password=get_password)
    monkeypatch.setitem(sys.modules, "keyring", module)
    expected = PreconditionFailed if failure == "missing" else CapabilityUnavailable
    keyring = KeyringSecretResolver()
    resolver = SecretResolvers((keyring,), on_reveal=lambda _: None) if composed else keyring
    with pytest.raises(expected) as caught:
        resolver.resolve(REF)
    assert caught.value.code == (
        ErrorCode.SECRET_UNAVAILABLE if failure == "missing" else ErrorCode.CAPABILITY_UNAVAILABLE
    )
    assert "private-password" not in str(caught.value.to_problem())
    assert caught.value.__context__ is None
