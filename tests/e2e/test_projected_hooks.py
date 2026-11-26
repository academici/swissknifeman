"""Installed native renderers use the verified private hook daemon on PostgreSQL."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from e2e.test_instance_profiles import _Databases
from e2e.test_instance_profiles import databases as databases
from e2e.test_p04_workspace import Sandbox, _installed_cli
from fixtures.hooks.subprocess.harness import (
    HOOK,
    TARGETS,
    Invocation,
    claude_on_path,
    commands,
    installed_daemon,
    native_payload,
    runtime_environment,
)
from skm.bootstrap.hook import hook_context
from skm.kernel.ids import ProjectId
from skm.modules.integrations.host.hook_state import HookState
from skm.modules.integrations.host.observe import resolve_checkout_for_mount
from support.git_repo import init_git_repo

pytestmark = [pytest.mark.e2e, pytest.mark.pg]

NATIVE_FILES = {
    "claude_code": ".claude/settings.json",
    "codex": ".codex/hooks.json",
    "cursor": ".cursor/hooks.json",
    "grok": ".grok/hooks/skm.json",
}

HOOK_PERMISSIONS = (
    "workspace.read",
    "project.read",
    "checkout.read_locator",
    "integration.read",
    "policy.read",
    "run.read",
    "inbox.read",
    "lesson.read",
)


def install_hook_token(
    environment: Mapping[str, str], root: Path, token_path: Path, workspace_id: str
) -> None:
    token_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    arguments = tuple(
        argument for permission in HOOK_PERMISSIONS for argument in ("--permission", permission)
    )
    result = _installed_cli(
        environment,
        root,
        "token",
        "create",
        "native-test",
        "--scope",
        f"workspace:{workspace_id}",
        "--expires-in",
        "1h",
        "--save",
        str(token_path),
        *arguments,
    )
    assert result["saved_to"] == str(token_path)


@dataclass(frozen=True)
class _NativeCheckout:
    box: Sandbox
    project: str
    checkout: Path
    bootstrap: Path


def _native_checkout(tmp_path: Path, databases: _Databases) -> _NativeCheckout:
    root = tmp_path / "local"
    root.mkdir()
    box = Sandbox(root, databases.projects[0], databases.machine_env)
    env = box.env()
    _installed_cli(env, root, "init")
    _installed_cli(env, root, "host", "register", "native-a03")
    project = _installed_cli(env, root, "project", "create", "native", "--workspace", "personal")
    _installed_cli(env, root, "use", "personal/native")
    repo = init_git_repo(tmp_path / "native-checkout")
    repo.commit_file("README.md", "native test\n", message="Initial commit")
    repo.add_remote("origin", "https://repo.example/team/native.git")
    _installed_cli(env, repo.path, "repo", "bind", "--register", "--write-marker", "--yes")
    install_hook_token(env, repo.path, box.state_dir / "secrets/hook.token", project["workspace_id"])
    _installed_cli(
        env,
        repo.path,
        "config",
        "set",
        "integrations.hooks.mode",
        '{"git_guardrails":"strict","command_log":"warn","session_start":"warn"}',
        "--scope",
        f"project:{project['project_id']}",
    )
    bootstrap = box.root / "config/skm/bootstrap.toml"
    return _NativeCheckout(box, project["project_id"], repo.path, bootstrap)


def assert_native(result: subprocess.CompletedProcess[str], target: str, *, denied: bool) -> None:
    assert result.returncode == (2 if denied and target in {"codex", "grok"} else 0), result.stderr
    if target == "claude_code" and denied:
        assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    elif target == "cursor":
        if result.stdout:
            assert json.loads(result.stdout)["permission"] == ("deny" if denied else "allow"), result.stdout
        else:
            assert not denied
    else:
        assert result.stdout == ""


def test_projected_native_registration(tmp_path: Path, databases: _Databases, record_property: Any) -> None:
    native = _native_checkout(tmp_path, databases)
    env = native.box.env()
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(HOOK.parent) + os.pathsep + env["PATH"]
    with runtime_environment(env) as environment:
        claude_on_path(environment)
        for target in TARGETS:
            _installed_cli(
                env,
                native.checkout,
                "integrations",
                "apply",
                "--project",
                native.project,
                "--target",
                target,
                "--yes",
            )
            registrations = commands(json.loads((native.checkout / NATIVE_FILES[target]).read_text()))
            _assert_native_projection(native.checkout, target)
            if target == "claude_code":
                _assert_live_checkout(native, environment)
            guard = _invocation(native, target, registrations, environment, command="git reset --hard")
            safe = _invocation(native, target, registrations, environment)
            with installed_daemon(environment, cwd=native.checkout, bootstrap=native.bootstrap):
                denied, _ = guard.execute()
                assert_native(denied, target, denied=True)
                assert "Unsafe Git operation" in denied.stdout + denied.stderr
                assert "HOOK_BACKEND_UNAVAILABLE" not in denied.stdout + denied.stderr
                allowed, live_ms = safe.execute()
                assert_native(allowed, target, denied=False)
                assert "HOOK_BACKEND_UNAVAILABLE" not in allowed.stderr
                assert any(
                    native.box.state_dir.glob(f"hook-profiles/*/*/*/hooks/{native.project}-{target}.json")
                )
                record_property(target + "_native_round_trip_ms", round(live_ms, 3))
            _assert_unavailable(safe, target)
            _assert_deadlines(native, safe, target, live_ms)
        _assert_no_ambient_operator_fallback(native, safe, environment)


def _assert_native_projection(root: Path, target: str) -> None:
    if target == "claude_code":
        mcp = json.loads((root / ".mcp.json").read_text())["mcpServers"]
        perms = json.loads((root / ".claude/settings.json").read_text())["permissions"]
        assert set(perms) >= {"allow", "ask", "deny"}
    elif target == "cursor":
        mcp = json.loads((root / ".cursor/mcp.json").read_text())["mcpServers"]
        perms = json.loads((root / ".cursor/permissions.json").read_text())
        assert set(perms) >= {"terminalAllowlist", "mcpAllowlist"}
    else:
        config = tomllib.loads((root / f".{target}/config.toml").read_text())
        mcp = config["mcp_servers"]
        if target == "codex":
            assert config["sandbox_mode"] in {"read-only", "workspace-write"}
        else:
            assert isinstance(config["permission"]["deny"], list)
    assert mcp["skm"]["command"] == "skm"


def _assert_live_checkout(native: _NativeCheckout, environment: dict[str, str]) -> None:
    with hook_context(environment, str(native.bootstrap)) as context:
        location = resolve_checkout_for_mount(context, ProjectId(UUID(native.project)), "main")
        assert location.local_locator == str(native.checkout)
        context.gateways.get(HookState).checkout(
            location.local_locator,
            str(native.checkout),
            native.project,
            str(location.binding_id),
            str(location.repository_id),
            "main",
        )


def _invocation(
    native: _NativeCheckout,
    target: str,
    registrations: list[list[str]],
    environment: dict[str, str],
    *,
    command: str = "git status",
) -> Invocation:
    argv = next(
        argv for argv in registrations if argv[argv.index("--surface") + 1] == "lifecycle.git_guardrails"
    )
    assert argv[argv.index("--target") + 1] == target
    assert argv[argv.index("--project") + 1] == native.project
    return Invocation(
        argv, native_payload(target, argv[1], native.checkout, command), environment, native.checkout
    )


def _assert_unavailable(call: Invocation, target: str) -> float:
    result, elapsed = call.execute()
    assert_native(result, target, denied=True)
    assert "HOOK_BACKEND_UNAVAILABLE" in result.stdout + result.stderr
    return elapsed


def _assert_no_ambient_operator_fallback(
    native: _NativeCheckout, safe: Invocation, environment: dict[str, str]
) -> None:
    token_path = native.box.state_dir / "secrets/hook.token"
    hook_secret = token_path.read_bytes()
    owner = native.box.owner_token_file.read_text().strip()
    for explicitly_wide in (False, True):
        token_path.unlink(missing_ok=True)
        if explicitly_wide:
            token_path.write_text(owner)
            token_path.chmod(0o600)
        with installed_daemon(
            {**environment, "SKM_API_TOKEN": owner}, cwd=native.checkout, bootstrap=native.bootstrap
        ):
            result, _ = safe.execute()
            assert_native(result, "grok", denied=True)
            assert "HOOK_BACKEND_UNAVAILABLE" in result.stdout + result.stderr
            assert owner not in result.stdout + result.stderr
    token_path.write_bytes(hook_secret)


def _assert_deadlines(native: _NativeCheckout, safe: Invocation, target: str, live_ms: float) -> None:
    # The policy query waits on a real relation lock. Client exit precedes releasing the lock.
    durations: list[float] = []
    for timeout_ms in (350, 1000):
        with installed_daemon(safe.environ, cwd=native.checkout, bootstrap=native.bootstrap):
            result, _ = safe.execute()
            assert_native(result, target, denied=False)
            with psycopg.connect(native.box.dsn) as lock:
                lock.execute("LOCK TABLE skm_integrations.projections IN ACCESS EXCLUSIVE MODE")
                call = Invocation(
                    safe.argv,
                    safe.payload,
                    {**safe.environ, "SKM__INTEGRATIONS__HOOK__TIMEOUT_MS": str(timeout_ms)},
                    safe.cwd,
                )
                elapsed = _assert_unavailable(call, target)
                assert elapsed < live_ms + 1500 + timeout_ms, (target, elapsed)
                durations.append(elapsed)
                lock.rollback()
    assert durations[1] - durations[0] >= 400, (target, durations)
