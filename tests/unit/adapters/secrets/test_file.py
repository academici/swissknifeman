"""Private file admission and descriptor-bound reads, using synthetic test secrets only."""

import json
import os
import traceback
from types import SimpleNamespace

import pytest

from skm.adapters.secrets.file import FileSecretResolver
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.platform.config.secrets import SecretRef, SecretResolvers
from skm.platform.logging.redaction import MASK, Redactor

TEXT = "synthetic-file-secret-6248"


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / "secret"
    path.write_text(TEXT + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def ref(path):
    return SecretRef.parse("secret://file/" + str(path))


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_private_owned_file_resolves_and_registers_before_use(secret_file, mode):
    secret_file.chmod(mode)
    redactor = Redactor(patterns=())
    resolvers = SecretResolvers([FileSecretResolver()], on_reveal=redactor.register_secret)
    assert resolvers.resolve(ref(secret_file)).reveal() == TEXT
    assert redactor.text(TEXT) == MASK


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o660, 0o666, 0o700, 0o1600, 0o2600, 0o4600])
def test_permissions_broader_than_0600_are_rejected_before_reading(secret_file, monkeypatch, mode):
    secret_file.chmod(mode)

    def forbidden_read(*args, **kwargs):
        pytest.fail("unsafe file content must not be read")

    monkeypatch.setattr("skm.adapters.secrets.file.open", forbidden_read, raising=False)
    with pytest.raises(ValidationFailed) as caught:
        FileSecretResolver().resolve(ref(secret_file))
    assert caught.value.code == ErrorCode.CONFIG_INVALID
    assert dict(caught.value.details) == {"ref": str(ref(secret_file)), "reason": "secret_file_permissions"}
    assert TEXT not in json.dumps(caught.value.to_problem())


def test_wrong_owner_is_rejected_before_content_is_read(secret_file, monkeypatch):
    original = os.fstat

    def wrong_owner(descriptor):
        metadata = original(descriptor)
        return SimpleNamespace(st_uid=os.geteuid() + 1, st_mode=metadata.st_mode)

    def forbidden_read(*args, **kwargs):
        pytest.fail("foreign-owned content must not be read")

    monkeypatch.setattr("skm.adapters.secrets.file.os.fstat", wrong_owner)
    monkeypatch.setattr("skm.adapters.secrets.file.open", forbidden_read, raising=False)
    with pytest.raises(ValidationFailed) as caught:
        FileSecretResolver().resolve(ref(secret_file))
    assert caught.value.details["reason"] == "secret_file_permissions"


@pytest.mark.parametrize("ending", ["", "\n", "\r\n", "\n\n"])
def test_trailing_newlines_are_removed_but_whitespace_is_preserved(secret_file, ending):
    secret_file.write_bytes((" " + TEXT + " \t" + ending).encode())
    assert FileSecretResolver().resolve(ref(secret_file)) == " " + TEXT + " \t"


def test_internal_line_endings_are_not_normalized(secret_file):
    content = TEXT + "\r\nsecond\rthird\nfourth"
    secret_file.write_bytes((content + "\r\n").encode())
    assert FileSecretResolver().resolve(ref(secret_file)) == content


def test_permission_failure_through_registry_does_not_register_or_fall_back(secret_file):
    secret_file.chmod(0o644)
    revealed = []
    resolvers = SecretResolvers([FileSecretResolver()], on_reveal=revealed.append)
    with pytest.raises(ValidationFailed) as caught:
        resolvers.resolve(ref(secret_file))
    assert caught.value.details["reason"] == "secret_file_permissions"
    assert caught.value.__context__ is None
    assert revealed == []


def test_embedded_nul_path_has_a_safe_backend_failure():
    with pytest.raises(BackendUnavailable) as caught:
        FileSecretResolver().resolve(SecretRef.parse("secret://file//synthetic\x00path"))
    assert caught.value.__context__ is None
    assert caught.value.code == ErrorCode.BACKEND_UNAVAILABLE


def test_tilde_is_expanded_at_file_adapter_boundary(secret_file, monkeypatch):
    monkeypatch.setenv("HOME", str(secret_file.parent))
    assert FileSecretResolver().resolve(SecretRef.parse("secret://file/~/secret")) == TEXT


def test_replacing_path_after_open_cannot_replace_admitted_descriptor(secret_file, monkeypatch):
    original_open = os.open
    replacement = secret_file.with_name("other")
    replacement.write_text("replacement-source", encoding="utf-8")
    replacement.chmod(0o666)

    def swap_after_open(path, flags):
        descriptor = original_open(path, flags)
        replacement.replace(path)
        return descriptor

    monkeypatch.setattr("skm.adapters.secrets.file.os.open", swap_after_open)
    assert FileSecretResolver().resolve(ref(secret_file)) == TEXT
    assert secret_file.read_text() == "replacement-source"


def test_symlink_uses_target_ownership_and_permissions(secret_file, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(secret_file)
    assert FileSecretResolver().resolve(ref(link)) == TEXT
    secret_file.chmod(0o644)
    with pytest.raises(ValidationFailed, match="private"):
        FileSecretResolver().resolve(ref(link))


@pytest.mark.parametrize("kind", ["missing", "directory", "fifo", "encoding"])
def test_unavailable_and_nonregular_sources_fail_safely(secret_file, tmp_path, kind):
    source = tmp_path / kind
    if kind == "directory":
        source.mkdir(mode=0o700)
    elif kind == "fifo":
        os.mkfifo(source, mode=0o600)
    elif kind == "encoding":
        source.write_bytes(b"\xff" + TEXT.encode())
        source.chmod(0o600)
    expected = ValidationFailed if kind in ("directory", "fifo") else BackendUnavailable
    with pytest.raises(expected) as caught:
        FileSecretResolver().resolve(ref(source))
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert TEXT not in "".join(traceback.format_exception(caught.value))
    assert TEXT not in json.dumps(caught.value.to_problem())


def test_read_failure_closes_descriptor_and_sanitizes_exception(secret_file, monkeypatch):
    descriptors = []
    original_open = os.open

    def record_open(path, flags):
        descriptor = original_open(path, flags)
        descriptors.append(descriptor)
        return descriptor

    def fail_read(*args, **kwargs):
        raise OSError(TEXT)

    monkeypatch.setattr("skm.adapters.secrets.file.os.open", record_open)
    monkeypatch.setattr("skm.adapters.secrets.file.open", fail_read, raising=False)
    with pytest.raises(BackendUnavailable) as caught:
        FileSecretResolver().resolve(ref(secret_file))
    assert caught.value.__context__ is None
    assert TEXT not in "".join(traceback.format_exception(caught.value))
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.fstat(descriptors[0])


def test_other_scheme_is_rejected_before_open(monkeypatch):
    def forbidden_open(*args, **kwargs):
        pytest.fail("another scheme must not perform file IO")

    monkeypatch.setattr("skm.adapters.secrets.file.os.open", forbidden_open)
    with pytest.raises(ValidationFailed) as caught:
        FileSecretResolver().resolve(SecretRef.parse("secret://env/SKM_TEST_SECRET"))
    assert caught.value.details["reason"] == "secret_ref_invalid"


@pytest.mark.parametrize("relative", ["token", "./token", "../token"])
@pytest.mark.parametrize("through_registry", [False, True])
@pytest.mark.parametrize("nested_cwd", [False, True])
@pytest.mark.parametrize("file_exists", [False, True])
def test_relative_paths_are_rejected_before_open_regardless_of_cwd(
    tmp_path, monkeypatch, relative, through_registry, nested_cwd, file_exists
):
    cwd = tmp_path / "checkout"
    if nested_cwd:
        cwd /= "nested"
    cwd.mkdir(parents=True)
    if file_exists:
        source = cwd / relative
        source.write_text(TEXT, encoding="utf-8")
        source.chmod(0o600)
    monkeypatch.chdir(cwd)
    opened = []
    revealed = []

    def forbidden_open(*args, **kwargs):
        opened.append(args)
        pytest.fail("relative references must be rejected before opening")

    adapter = FileSecretResolver()
    registry = SecretResolvers([adapter], on_reveal=revealed.append)
    resolve = registry.resolve if through_registry else adapter.resolve
    reference = ref(relative)
    monkeypatch.setattr("skm.adapters.secrets.file.os.open", forbidden_open)
    with pytest.raises(ValidationFailed) as caught:
        resolve(reference)
    assert caught.value.code == ErrorCode.CONFIG_INVALID
    assert caught.value.details["reason"] == "secret_ref_invalid"
    assert opened == revealed == []
