import json
import tomllib
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.runtimes.test_client_home import _make_request
from skm.adapters.runtimes._cli_session.probe import CommandOutput
from skm.adapters.runtimes.claude_code import launch as claude
from skm.adapters.runtimes.claude_code.detect import ClaudeDetector
from skm.adapters.runtimes.codex import launch as codex
from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.request import SecretStr


@pytest.mark.parametrize("isolated", [True, False])
def test_claude_strips_all_ambient_anthropic_variables_even_if_allowlisted(
    tmp_path: Path, isolated: bool
) -> None:
    ambient = {
        "ANTHROPIC_API_KEY": "ambient-key",
        "ANTHROPIC_AUTH_TOKEN": "ambient-auth",
        "ANTHROPIC_BASE_URL": "https://wrong.invalid",
        "ANTHROPIC_FUTURE_OPTION": "ambient-option",
        "CLAUDE_CODE_OAUTH_TOKEN": "ambient-token",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_SECURESTORAGE_CONFIG_DIR": "/shared/store",
    }
    request, owner = _make_request(
        runtime_id="claude_code",
        workdir=tmp_path / "work",
        state_dir=tmp_path / "state",
        config_mode="isolated" if isolated else "inherit",
        env_allowlist=tuple(ambient),
        extra_env={"ANTHROPIC_API_KEY": "explicit-key"},
    )
    plan = claude.build_launch_plan(
        request,
        binary_path="/usr/bin/claude",
        step_dir=tmp_path / "step",
        ownership=owner,
        host_environ=ambient,
        copy_credentials=False,
    )
    assert plan.command.env["ANTHROPIC_API_KEY"] == "explicit-key"
    assert not (ambient.keys() - {"ANTHROPIC_API_KEY"}) & plan.command.env.keys()
    assert "explicit-key" not in repr(plan)


def test_claude_probes_also_strip_ambient_anthropic_variables(tmp_path: Path) -> None:
    ambient = {"ANTHROPIC_FUTURE_OPTION": "poison", "CLAUDE_CODE_OAUTH_TOKEN": "ambient-token"}
    binary = tmp_path / "claude"
    binary.touch(mode=0o700)
    probed_envs: list[Mapping[str, str]] = []

    def runner(argv: tuple[str, ...], *, env: Mapping[str, str], timeout_seconds: float) -> CommandOutput:
        probed_envs.append(env)
        return CommandOutput(0, "2.1.261" if argv[-1] == "--version" else "", "")

    ClaudeDetector(run_cmd=runner).probe(
        binary=str(binary),
        environ=ambient,
        env_allowlist=tuple(ambient),
        adapter_version="test",
        launch_config_digest="sha256:" + "a" * 64,
    )
    assert len(probed_envs) == 2
    assert all(not ambient.keys() & env.keys() for env in probed_envs)


def test_macos_claude_guard_requires_explicit_auth_and_accepts_setup_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(claude, "sys", SimpleNamespace(platform="darwin"))
    user_home = tmp_path / "user"
    (user_home / ".claude").mkdir(parents=True)
    (user_home / ".claude" / claude.CREDENTIAL_FILENAME).write_text("different-account", encoding="utf-8")
    ambient = {
        "HOME": str(user_home),
        "CLAUDE_CODE_OAUTH_TOKEN": "wrong-account-token",
        "CLAUDE_SECURESTORAGE_CONFIG_DIR": "",
    }
    request, owner = _make_request(
        runtime_id="claude_code",
        workdir=tmp_path / "work",
        state_dir=tmp_path / "state",
        env_allowlist=tuple(ambient),
        extra_env={"ANTHROPIC_BASE_URL": "https://wrong.invalid", "CLAUDE_SECURESTORAGE_CONFIG_DIR": ""},
    )
    with pytest.raises(CapabilityUnavailable) as error:
        claude.build_launch_plan(
            request,
            binary_path="/usr/bin/claude",
            step_dir=tmp_path / "step",
            ownership=owner,
            host_environ=ambient,
        )
    assert error.value.code is ErrorCode.RUNTIME_AUTH_EXPIRED
    assert error.value.details["reason"] == "macos_keychain_namespace"
    assert request.client_home is not None
    assert not Path(request.client_home).exists()

    setup_token = SecretStr("explicit-setup-token")
    plan = claude.build_launch_plan(
        request,
        binary_path="/usr/bin/claude",
        step_dir=tmp_path / "step",
        ownership=owner,
        host_environ=ambient,
        setup_token=setup_token,
    )
    assert plan.client_home is not None
    assert plan.command.env["CLAUDE_CONFIG_DIR"] == str(plan.client_home)
    assert plan.command.env["CLAUDE_CODE_OAUTH_TOKEN"] == setup_token.reveal()
    assert "CLAUDE_SECURESTORAGE_CONFIG_DIR" not in plan.command.env
    assert "ANTHROPIC_BASE_URL" not in plan.command.env
    assert not (plan.client_home / claude.CREDENTIAL_FILENAME).exists()
    assert setup_token.reveal() not in repr(plan)
    assert setup_token.reveal() not in plan.permissions.settings_path.read_text(encoding="utf-8")


def test_codex_uses_distinct_file_stores_for_leased_slots(tmp_path: Path) -> None:
    slots = [ProviderSlot("codex", "account-a"), ProviderSlot("codex", "account-b")]
    pool = ProviderPoolManager(tmp_path / "pool", slots)
    ambient_home = tmp_path / "ambient"
    ambient_home.mkdir()
    (ambient_home / codex.CREDENTIAL_FILENAME).write_text("ambient-account", encoding="utf-8")
    ambient = {"CODEX_HOME": str(ambient_home), "CODEX_HOME_USER": str(ambient_home)}

    for slot in slots:
        credentials = json.dumps({"account": slot.slot_id})
        request, owner = _make_request(
            runtime_id="codex",
            workdir=tmp_path / "work",
            state_dir=tmp_path / "state",
            env_allowlist=tuple(ambient),
            extra_env=ambient,
        )
        lease = pool.acquire(slot.slot_id, request.request_id, ttl_seconds=60)
        assert lease is not None
        assert lease.credential_isolation == "unsupported"
        with pool.use(lease) as home:
            credential = home / codex.CREDENTIAL_FILENAME
            credential.write_text(credentials, encoding="utf-8")
            plan = codex.build_launch_plan(
                lease.bind_request(request),
                binary_path="/usr/bin/codex",
                step_dir=tmp_path / slot.slot_id,
                ownership=owner,
                host_environ=ambient,
                copy_credentials=False,
            )
            assert plan.client_home == home
            assert plan.command.env["CODEX_HOME"] == plan.command.env["HOME"] == str(home)
            assert "CODEX_HOME_USER" not in plan.command.env
            assert credential.read_text(encoding="utf-8") == credentials
            assert credential.stat().st_mode & 0o777 == 0o600
            config = tomllib.loads(plan.permissions.config_path.read_text(encoding="utf-8"))
            assert config["cli_auth_credentials_store"] == "file"
        assert pool.release(lease)
    assert (ambient_home / codex.CREDENTIAL_FILENAME).read_text(encoding="utf-8") == "ambient-account"


def test_slot_switch_refuses_already_admitted_resume(tmp_path: Path) -> None:
    pool = ProviderPoolManager(tmp_path / "pool", [ProviderSlot("codex", "a"), ProviderSlot("codex", "b")])
    first = pool.acquire("a", "earlier-step", ttl_seconds=60)
    assert first is not None
    with pool.use(first):
        pin = pool.pin_session(first, "earlier-session")
    assert pool.release(first)

    request, _ = _make_request(
        runtime_id="codex",
        workdir=tmp_path / "work",
        state_dir=tmp_path / "state",
        session_policy="persistent",
        resume_session_ref=pin.session_ref,
    )
    resumed = pool.acquire("a", request.request_id, ttl_seconds=60)
    assert resumed is not None
    with pool.use(resumed):
        assert resumed.bind_request(request, previous=pin).resume_session_ref == pin.session_ref
    assert pool.release(resumed)

    switched = pool.acquire("b", request.request_id, ttl_seconds=60)
    assert switched is not None
    with pool.use(switched):
        with pytest.raises(ValueError, match="admit a fresh session"):
            switched.bind_request(request, previous=pin)
        fresh = replace(request, resume_session_ref=switched.resume_ref(pin))
        assert switched.bind_request(fresh).resume_session_ref is None
