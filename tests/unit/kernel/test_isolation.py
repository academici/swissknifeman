"""Built-in and plugin isolation profile identifiers (00-conventions §4.0.3, D-REG-6)."""

import json
from pathlib import Path

import pytest

from skm.kernel.isolation import (
    ISOLATION_PLUGIN_PATTERN,
    IsolationProfile,
    is_builtin_isolation_profile,
    is_plugin_isolation_profile,
    parse_isolation_profile,
)

POLICY_SCHEMA = Path(__file__).resolve().parents[3] / "src/skm/schemas/policy/profile.v1.json"


def test_matches_the_policy_schema_definition() -> None:
    branches = json.loads(POLICY_SCHEMA.read_text(encoding="utf-8"))["$defs"]["isolation_profile"]["anyOf"]

    assert branches[0]["enum"] == [profile.value for profile in IsolationProfile]
    assert branches[1]["pattern"] == ISOLATION_PLUGIN_PATTERN


@pytest.mark.parametrize("text", ["none", "worktree", "landlock", "container"])
def test_builtin_profiles(text: str) -> None:
    assert is_builtin_isolation_profile(text)
    assert not is_plugin_isolation_profile(text)
    parsed = parse_isolation_profile(text)
    assert parsed == text
    assert isinstance(parsed, IsolationProfile)
    assert parsed.value == text


def test_isolation_profile_is_a_closed_enum() -> None:
    assert IsolationProfile("worktree").value == "worktree"
    assert [profile.value for profile in IsolationProfile] == ["none", "worktree", "landlock", "container"]
    for text in ("docker", "acme:firejail", "Worktree", ""):
        with pytest.raises(ValueError, match="is not a valid IsolationProfile"):
            IsolationProfile(text)


@pytest.mark.parametrize("text", ["acme:firejail", "my.plugin-1:strict_mode", "a:b"])
def test_plugin_profiles(text: str) -> None:
    assert is_plugin_isolation_profile(text)
    assert not is_builtin_isolation_profile(text)
    parsed = parse_isolation_profile(text)
    assert parsed == text
    assert not isinstance(parsed, IsolationProfile)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Worktree",
        "NONE",
        "docker",
        "acme:",
        ":firejail",
        "acme:fire jail",
        "Acme:firejail",
        "acme:fire.jail",
        "acme:one:two",
        "acme:firejail\n",
        " worktree",
        "worktree\n",
    ],
)
def test_rejected_profiles(text: str) -> None:
    with pytest.raises(ValueError, match="not an isolation profile"):
        parse_isolation_profile(text)


def test_non_str_is_rejected() -> None:
    with pytest.raises(TypeError):
        parse_isolation_profile(None)  # type: ignore[arg-type]
