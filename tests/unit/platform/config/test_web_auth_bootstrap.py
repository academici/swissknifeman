"""Pre-database [web_auth] bootstrap configuration tests (ADR 0010 addendum, I-10.1b)."""

import json
from pathlib import Path

import pytest

from skm.kernel.errors import ValidationFailed
from skm.platform.config.bootstrap import WebAuthConfig, load_bootstrap

ROOT = Path(__file__).resolve().parents[4]
INSTANCE_A = "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11"
INSTANCE_B = "0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c22"


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_single_instance_web_auth_defaults_and_custom_values(tmp_path: Path) -> None:
    default_file = _write(
        tmp_path / "default.toml",
        f"""
schema = "urn:skm:config:bootstrap:v1"
instance_id = "{INSTANCE_A}"

[access]
mode = "embedded"

[database]
url = "secret://env/SKM_DATABASE_URL"
""",
    )
    cfg = load_bootstrap(default_file, {}, tmp_path)
    assert cfg.web_auth == WebAuthConfig()
    assert cfg.web_auth.mode == "admin_login"
    assert cfg.web_auth.forwarded_allow_ips == ()
    assert cfg.web_auth.session_ttl_seconds == 43_200
    assert cfg.web_auth.cookie_samesite == "lax"
    assert cfg.web_auth.login_rate_limit_max == 10
    assert cfg.web_auth.login_rate_limit_window_seconds == 60

    custom_file = _write(
        tmp_path / "custom.toml",
        f"""
schema = "urn:skm:config:bootstrap:v1"
instance_id = "{INSTANCE_A}"

[access]
mode = "embedded"

[database]
url = "secret://env/SKM_DATABASE_URL"

[web_auth]
mode = "admin_login"
forwarded_allow_ips = ["127.0.0.1", "::1", "10.0.0.0/8"]
session_ttl_seconds = 3600
cookie_samesite = "strict"
login_rate_limit_max = 5
login_rate_limit_window_seconds = 30
""",
    )
    custom = load_bootstrap(custom_file, {}, tmp_path)
    assert custom.web_auth == WebAuthConfig(
        mode="admin_login",
        forwarded_allow_ips=("127.0.0.1", "::1", "10.0.0.0/8"),
        session_ttl_seconds=3600,
        cookie_samesite="strict",
        login_rate_limit_max=5,
        login_rate_limit_window_seconds=30,
    )


def test_named_profiles_support_root_inheritance_and_per_profile_override(tmp_path: Path) -> None:
    profiles_file = _write(
        tmp_path / "profiles.toml",
        f"""
schema = "urn:skm:config:bootstrap:v1"
default_instance = "local"

[web_auth]
mode = "admin_login"
cookie_samesite = "strict"
forwarded_allow_ips = ["127.0.0.1"]

[instances.local]
instance_id = "{INSTANCE_A}"
[instances.local.access]
mode = "embedded"
[instances.local.database]
url = "secret://env/SKM_DATABASE_URL"
[instances.local.web_auth]
mode = "none"
session_ttl_seconds = 900

[instances.prod]
instance_id = "{INSTANCE_B}"
[instances.prod.access]
mode = "embedded"
[instances.prod.database]
url = "secret://env/SKM_DATABASE_URL"
""",
    )
    local_cfg = load_bootstrap(profiles_file, {}, tmp_path, instance="local")
    assert local_cfg.web_auth.mode == "none"
    assert local_cfg.web_auth.cookie_samesite == "strict"
    assert local_cfg.web_auth.session_ttl_seconds == 900
    assert local_cfg.web_auth.forwarded_allow_ips == ("127.0.0.1",)

    prod_cfg = load_bootstrap(profiles_file, {}, tmp_path, instance="prod")
    assert prod_cfg.web_auth.mode == "admin_login"
    assert prod_cfg.web_auth.cookie_samesite == "strict"
    assert prod_cfg.web_auth.session_ttl_seconds == 43_200


def test_skm_web_auth_mode_env_override_applies_to_single_profile_and_env_only(tmp_path: Path) -> None:
    single = _write(
        tmp_path / "single.toml",
        f"""
schema = "urn:skm:config:bootstrap:v1"
instance_id = "{INSTANCE_A}"

[access]
mode = "embedded"

[database]
url = "secret://env/SKM_DATABASE_URL"

[web_auth]
mode = "admin_login"
""",
    )
    overridden = load_bootstrap(single, {"SKM_WEB_AUTH_MODE": "none"}, tmp_path)
    assert overridden.web_auth.mode == "none"

    env_only = load_bootstrap(
        None,
        {"SKM_DATABASE_URL": "postgresql://user:pass@127.0.0.1/skm", "SKM_WEB_AUTH_MODE": "none"},
        tmp_path,
    )
    assert env_only.web_auth.mode == "none"

    with pytest.raises(ValidationFailed) as invalid:
        load_bootstrap(single, {"SKM_WEB_AUTH_MODE": "invalid_mode"}, tmp_path)
    assert invalid.value.code == "CONFIG_INVALID"


@pytest.mark.parametrize(
    "web_auth_block",
    [
        'mode = "bogus"',
        'cookie_samesite = "none"',
        "session_ttl_seconds = 60",
        "login_rate_limit_max = 0",
        "login_rate_limit_window_seconds = 0",
        'forwarded_allow_ips = ["*"]',
        'forwarded_allow_ips = ["not-an-ip"]',
        'forwarded_allow_ips = ["127.0.0.1", "127.0.0.1"]',
        "unknown_key = true",
    ],
)
def test_web_auth_schema_rejects_invalid_values(tmp_path: Path, web_auth_block: str) -> None:
    path = _write(
        tmp_path / "bad.toml",
        f"""
schema = "urn:skm:config:bootstrap:v1"
instance_id = "{INSTANCE_A}"

[access]
mode = "embedded"

[database]
url = "secret://env/SKM_DATABASE_URL"

[web_auth]
{web_auth_block}
""",
    )
    with pytest.raises(ValidationFailed) as caught:
        load_bootstrap(path, {}, tmp_path)
    assert caught.value.code == "CONFIG_INVALID"


def test_web_auth_is_not_duplicated_in_api_settings_and_documented_in_adr_0010() -> None:
    api_schema = json.loads((ROOT / "src/skm/schemas/settings/api.v1.json").read_text(encoding="utf-8"))
    assert "web_auth" not in api_schema["properties"]
    assert "web_auth" not in json.dumps(api_schema)
    adr = (ROOT / "docs/adr/0010-one-config-engine.md").read_text(encoding="utf-8")
    assert "[web_auth]" in adr
    assert "SKM_WEB_AUTH_MODE" in adr
    assert "api.v1.json" in adr
