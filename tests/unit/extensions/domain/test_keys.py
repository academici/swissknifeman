"""Unit tests for ``skm.modules.extensions.domain.keys`` (extensions §4.1)."""

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.domain.keys import (
    LATEST,
    SemVer,
    VersionConstraint,
    is_digest,
    parse_pack_slug,
    parse_resource_key,
)


def test_parse_pack_slug_valid() -> None:
    assert parse_pack_slug("core") == "core"
    assert parse_pack_slug("my-pack-2") == "my-pack-2"
    assert parse_pack_slug("a" * 63) == "a" * 63


@pytest.mark.parametrize("bad_slug", ["", "a", "A-pack", "-bad", "bad_slug", "a" * 64, "pack/sub"])
def test_parse_pack_slug_invalid(bad_slug: str) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        parse_pack_slug(bad_slug)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "invalid_pack_slug"


def test_parse_resource_key_non_prompt_and_prompt() -> None:
    assert parse_resource_key("code-review", prompt_block=False) == "code-review"
    assert parse_resource_key("shared/system_prompt", prompt_block=True) == "shared/system_prompt"
    assert parse_resource_key("executor/task-contract", prompt_block=True) == "executor/task-contract"


@pytest.mark.parametrize(
    ("bad_key", "prompt_block"),
    [
        ("", False),
        ("a", False),
        ("has_underscore", False),
        ("shared/system", False),
        ("UpperCase", False),
        ("a" * 82, False),
        ("no-slash", True),
        ("too/many/slashes", True),
        ("/leading", True),
        ("trailing/", True),
    ],
)
def test_parse_resource_key_invalid(bad_key: str, prompt_block: bool) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        parse_resource_key(bad_key, prompt_block=prompt_block)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "invalid_resource_key"


def test_semver_parse_and_ordering() -> None:
    v1 = SemVer.parse("1.0.0-alpha.1")
    v2 = SemVer.parse("1.0.0-alpha.2")
    v3 = SemVer.parse("1.0.0-alpha.10")
    v4 = SemVer.parse("1.0.0-beta")
    v5 = SemVer.parse("1.0.0")
    v6 = SemVer.parse("1.2.0")
    v7 = SemVer.parse("2.0.0")

    ordered = [v1, v2, v3, v4, v5, v6, v7]
    rev = list(reversed(ordered))
    assert sorted(rev) == ordered
    assert v1 < v2 < v3 < v4 < v5 < v6 < v7
    assert v5 >= v4
    assert v7 > v6
    assert str(v1) == "1.0.0-alpha.1"
    assert str(v5) == "1.0.0"


@pytest.mark.parametrize("bad_ver", ["", "1.0", "01.0.0", "1.0.0-", "1.0.0-01", "1.0.0+build1", "v1.0.0"])
def test_semver_parse_invalid(bad_ver: str) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        SemVer.parse(bad_ver)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "invalid_semver"


def test_version_constraint_matching() -> None:
    latest = VersionConstraint.parse("latest")
    assert latest is LATEST
    assert str(latest) == "latest"
    assert latest.matches(SemVer.parse("0.0.1"))
    assert latest.matches(SemVer.parse("99.0.0"))

    c = VersionConstraint.parse(">=1.2.0,<2")
    assert c.matches(SemVer.parse("1.2.0"))
    assert c.matches(SemVer.parse("1.9.9"))
    assert not c.matches(SemVer.parse("1.1.9"))
    assert not c.matches(SemVer.parse("2.0.0"))

    exact = VersionConstraint.parse("1.2.3")
    assert exact.matches(SemVer.parse("1.2.3"))
    assert not exact.matches(SemVer.parse("1.2.4"))


@pytest.mark.parametrize("bad_constraint", ["", "^1.0.0", "~1.2.0", ">=1.0.0,", "invalid"])
def test_version_constraint_invalid(bad_constraint: str) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        VersionConstraint.parse(bad_constraint)
    assert exc_info.value.code is ErrorCode.SCHEMA_INVALID
    assert exc_info.value.details["reason"] == "invalid_version_constraint"


def test_is_digest() -> None:
    assert is_digest("sha256:" + "a" * 64)
    assert not is_digest("sha256:" + "A" * 64)
    assert not is_digest("sha256:short")
    assert not is_digest(123)
