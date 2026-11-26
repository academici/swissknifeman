from pathlib import Path

import pytest

from skm.platform.process.environment import BASE_ALLOW, build_env


def test_allowlist_is_explicit_and_does_not_inherit_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_HOST", "host-secret")
    source = dict.fromkeys(BASE_ALLOW, "base") | {
        "LC_TIME": "C",
        "SECRET": "hidden",
        "CUSTOM": "yes",
        "AICORE_ROOT": "legacy",
        "SKM_EXT_TRUSTED": "1",
        "PYTHONPATH": "injection",
        "LD_PRELOAD": "injection",
        "CODEX_HOME": "personal",
    }
    before = source.copy()
    assert build_env(source) == dict.fromkeys(BASE_ALLOW, "base") | {"LC_TIME": "C"}
    assert build_env({}, allow=["SECRET_HOST"]) == {}
    assert build_env(source, allow=(name for name in ["CUSTOM"]))["CUSTOM"] == "yes"
    assert source == before


def test_extra_and_home_override_in_order(tmp_path: Path) -> None:
    extra = {"HOME": "extra", "TOKEN": "explicit"}
    assert build_env({"HOME": "original"}, extra=extra, home=tmp_path) == {
        "HOME": str(tmp_path),
        "TOKEN": "explicit",
    }
    assert extra == {"HOME": "extra", "TOKEN": "explicit"}


@pytest.mark.parametrize("extra", [{"": "x"}, {"A=B": "x"}, {"A\0B": "x"}, {"A": "secret\0"}])
def test_invalid_environment_is_refused_without_values_in_error(extra: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="environment") as caught:
        build_env({}, extra=extra)
    assert "secret" not in str(caught.value)
