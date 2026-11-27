from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock
from uuid import uuid4

import pytest

from fixtures.hooks.subprocess.harness import (
    TARGETS,
    cached_invocation,
    claude_on_path,
    memory_daemon,
    native_invocation,
    runtime_environment,
)
from integration.integrations.test_hooks import env, hook_env
from skm.adapters.git._checkout_marker import MARKER_FILENAME
from skm.bootstrap import instance_profiles
from skm.platform.config.secrets import SecretRef
from skm.platform.machine import MachineProfile, MachineStore
from skm.platform.storage.restore import MARKER, RECEIPT

if TYPE_CHECKING:
    from fixtures.hooks.subprocess.harness import Invocation

__all__ = ["env", "hook_env"]


def test_installed_loaders(installed_bin: Path, tmp_path: Path) -> None:
    cwd = tmp_path / "empty"
    cwd.mkdir()
    env = {"HOME": str(tmp_path / "home"), "PATH": str(installed_bin) + os.pathsep + os.defpath}
    assert subprocess.check_output(
        [installed_bin / "skm", "--version"], cwd=cwd, env=env, text=True
    ).strip() == version("skm")
    assert "usage: skm-hookd" in subprocess.check_output(
        [installed_bin / "skm-hookd", "--help"], cwd=cwd, env=env, text=True
    )
    probe = """
import json, py_compile, sys
from importlib.resources import files
from pathlib import Path
from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.bootstrap.local_postgres import compose_file
from skm.platform.schema.registry import SchemaRegistry

root = files("skm")
assert root.is_relative_to(Path(sys.prefix))
assert not any(Path(p, "skm").is_dir() and not Path(p).is_relative_to(sys.prefix) for p in sys.path)
assert compose_file() == root / "_deploy/compose.local.yaml"
packs = PackagedBuiltinPacks().payloads()
assert len(packs) == 30
snippet = next((root / "_resources/packs").glob("**/parametric-config/snippets/check.py"))
assert Path(py_compile.compile(str(snippet), doraise=True)).is_file()
assert PackagedBuiltinPacks().payloads() == packs
assert discover_migrations()
assert SchemaRegistry.load_default().get("urn:skm:kernel:error-catalog:v1")
assert json.loads((root / "entrypoints/api/openapi.json").read_bytes())["paths"]
assert (root / "_web/index.html").is_file()
"""
    subprocess.run([installed_bin / "python", "-I", "-c", probe], check=True, cwd=cwd, env=env)


def _installed_hook(
    installed_bin: Path, cwd: Path, invocation: Invocation, *, importtime: bool = False
) -> tuple[subprocess.CompletedProcess[str], float]:
    env = invocation.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONPROFILEIMPORTTIME", None)
    paths = [str(installed_bin), os.defpath]
    if runtime := env.get("XDG_RUNTIME_DIR"):
        paths.insert(0, str(Path(runtime) / "bin"))
    env["PATH"] = os.pathsep.join(paths)
    return replace(invocation, environ=env, cwd=cwd).execute(
        executable=installed_bin / "skm-hook", importtime=importtime
    )


@pytest.mark.perf
@pytest.mark.parametrize("env", ["memory"], indirect=True)
@pytest.mark.parametrize("target", TARGETS)
def test_installed_cached_hook_startup(
    installed_bin: Path, hook_env: Any, tmp_path: Path, target: str
) -> None:
    samples = []
    cwd = tmp_path / "empty"
    cwd.mkdir()
    for _ in range(20):
        cache = hook_env.state_dir / "hooks" / f"{hook_env.project_id}-{target}.json"
        cache.unlink(missing_ok=True)
        result, duration = _installed_hook(installed_bin, cwd, cached_invocation(hook_env, target))
        samples.append(duration)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ('{"permission": "allow"}' if target == "cursor" else "")
        assert "HOOK_BACKEND_UNAVAILABLE" not in result.stderr
    p95 = sorted(samples)[18]  # nearest-rank p95, as in the hook performance suite
    print(f"{target} installed skm-hook p95 = {p95:.3f} ms")
    assert p95 <= 150, samples


@pytest.mark.parametrize("env", ["memory"], indirect=True)
@pytest.mark.parametrize("target", TARGETS)
def test_installed_cached_hook_imports(
    installed_bin: Path, hook_env: Any, tmp_path: Path, target: str
) -> None:
    result, _ = _installed_hook(installed_bin, tmp_path, cached_invocation(hook_env, target), importtime=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ('{"permission": "allow"}' if target == "cursor" else "")
    assert "HOOK_BACKEND_UNAVAILABLE" not in result.stderr
    assert "import time:" in result.stderr
    assert "skm.adapters.git._checkout_marker" in result.stderr
    for module in (
        "skm.adapters.git.repo_inspect",
        "skm.application_bus.middleware",
        "skm.bootstrap.hookd",
        "skm.platform.schema.registry",
        "skm.platform.storage.backup",
        "skm.platform.storage.restore",
    ):
        assert module not in result.stderr


@pytest.mark.parametrize("env", ["memory"], indirect=True)
@pytest.mark.parametrize("target", TARGETS)
def test_installed_enforcement_uses_live_daemon(
    installed_bin: Path, hook_env: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    denied = native_invocation(hook_env, target, command="git reset --hard")
    allowed = native_invocation(hook_env, target)
    with runtime_environment(denied.environ) as environ:
        if target == "claude_code":
            claude_on_path(environ)
        with memory_daemon(environ, hook_env.ctx, monkeypatch):
            result, _ = _installed_hook(installed_bin, tmp_path, replace(denied, environ=environ))
            assert result.returncode == (2 if target in {"codex", "grok"} else 0)
            if target == "claude_code":
                assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
            elif target == "cursor":
                assert json.loads(result.stdout)["permission"] == "deny"
            assert "Unsafe Git operation" in result.stdout + result.stderr
            assert "HOOK_BACKEND_UNAVAILABLE" not in result.stdout + result.stderr
            result, _ = _installed_hook(
                installed_bin, tmp_path, replace(allowed, environ=environ), importtime=True
            )
    assert result.returncode == 0
    assert result.stdout.strip() == ('{"permission": "allow"}' if target == "cursor" else "")
    assert "HOOK_BACKEND_UNAVAILABLE" not in result.stderr
    assert "skm.adapters.git.hook_state" not in result.stderr
    assert "skm.bootstrap.composition" not in result.stderr


@pytest.mark.parametrize("env", ["memory"], indirect=True)
def test_installed_hook_rejects_symlinked_checkout_marker(
    installed_bin: Path, hook_env: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = native_invocation(hook_env, "codex")
    marker = hook_env.checkout_dir / MARKER_FILENAME
    outside = tmp_path / "project.json"

    with (
        runtime_environment(invocation.environ) as environ,
        memory_daemon(environ, hook_env.ctx, monkeypatch),
    ):
        invocation.environ = environ
        before, _ = _installed_hook(installed_bin, tmp_path, invocation)
        assert before.returncode == 0, before.stderr
        marker.rename(outside)
        marker.symlink_to(outside)

        result, _ = _installed_hook(installed_bin, tmp_path, invocation)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "HOOK_BACKEND_UNAVAILABLE" in result.stderr


@pytest.mark.parametrize("env", ["memory"], indirect=True)
@pytest.mark.parametrize("marker", [MARKER, RECEIPT])
@pytest.mark.parametrize("source_marker", [False, True], ids=["state-dir", "profile-dir"])
@pytest.mark.parametrize("access_mode", ["embedded", "http"])
def test_installed_hook_refuses_restored_profile(
    installed_bin: Path,
    hook_env: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
    source_marker: bool,
    access_mode: str,
) -> None:
    invocation = native_invocation(hook_env, "codex")
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    profile = profile_dir / "bootstrap.toml"
    identity = ""
    if access_mode == "http":
        invocation.environ.pop("SKM_DATABASE_URL")
        installation = uuid4()
        origin = "https://127.0.0.1:1"
        endpoint = f"{origin}/api/v1"
        credential = "secret://env/SKM_TEST_HUB_TOKEN"
        identity = f'installation_id = "{installation}"\n'
        connection = (
            f'[api]\nendpoint = "{endpoint}"\ncredential = "{credential}"\n'
            '[machine_database]\nurl = "secret://env/SKM_TEST_MACHINE_URL"\n'
            'migrator_url = "secret://env/SKM_TEST_MACHINE_MIGRATOR_URL"\n'
        )
        pin = MachineProfile(
            installation,
            "default",
            hook_env.app.instance_id,
            origin,
            endpoint,
            credential_ref=SecretRef.parse(credential),
            revision=uuid4(),
        )
        machine = Mock(spec_set=MachineStore)
        machine.get_profile.side_effect = lambda key, name: (
            pin if (key, name) == (installation, "default") else None
        )
        monkeypatch.setattr(instance_profiles, "open_machine_store", lambda *_args, **_kwargs: machine)
    else:
        connection = '[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
    profile.write_text(
        'schema = "urn:skm:config:bootstrap:v1"\n'
        f'instance_id = "{hook_env.app.instance_id}"\n'
        f"{identity}"
        f'[host]\nid = "{hook_env.ctx.host_id}"\n'
        f'[access]\nmode = "{access_mode}"\n' + connection
    )
    alias = tmp_path / "bootstrap.toml"
    alias.symlink_to(profile)

    with (
        runtime_environment(invocation.environ) as environ,
        memory_daemon(environ, hook_env.ctx, monkeypatch, bootstrap=alias),
    ):
        invocation.environ = environ
        before, _ = _installed_hook(installed_bin, tmp_path, invocation)
        assert before.returncode == 0, before.stderr
        root = profile_dir if source_marker else hook_env.state_dir
        (root / marker).symlink_to(root / "missing")
        result, _ = _installed_hook(installed_bin, tmp_path, invocation)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "HOOK_BACKEND_UNAVAILABLE" in result.stderr
