"""Doctor's executable lookup sees the PATH native clients give their hook commands."""

import dataclasses
from pathlib import Path

from skm.adapters.host_commands.subprocess_runner import SubprocessHostCommandRunner
from skm.bootstrap.hook_subscriptions import with_subscription_gateways
from skm.kernel.gateways import GatewayTable
from skm.modules.integrations.ports import HostCommandRunner


def _hook_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "user bin"
    bin_dir.mkdir()
    hook = bin_dir / "skm-hook-probe"
    hook.write_text("#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    return bin_dir


def _which(runner: SubprocessHostCommandRunner, tmp_path: Path, env: dict[str, str]) -> int | None:
    return runner.run(
        ("which", "--", "skm-hook-probe"), cwd=tmp_path, env=env, stdin=b"", timeout_ms=5000
    ).exit_code


def test_lookup_without_path_uses_the_session_path(tmp_path: Path) -> None:
    bin_dir = _hook_dir(tmp_path)
    # Before: an empty env searched no user directory, so uv/pipx installs were always "not resolvable".
    assert _which(SubprocessHostCommandRunner(), tmp_path, {}) != 0
    session = SubprocessHostCommandRunner.for_session({"PATH": f"relative/bin:{bin_dir}:/usr/bin:/bin"})
    assert _which(session, tmp_path, {}) == 0
    assert _which(session, tmp_path, {"PATH": "/nonexistent"}) != 0  # an explicit PATH still wins


def test_relative_session_entries_are_never_searched(tmp_path: Path) -> None:
    _hook_dir(tmp_path)
    runner = SubprocessHostCommandRunner.for_session({"PATH": "user bin:/usr/bin:/bin"})
    assert _which(runner, tmp_path, {}) != 0


@dataclasses.dataclass(frozen=True)
class _Ctx:
    gateways: GatewayTable


def test_subscription_gateways_bind_the_session_path(tmp_path: Path) -> None:
    bin_dir = _hook_dir(tmp_path)
    ctx = with_subscription_gateways(
        _Ctx(GatewayTable({}, "host_gateway")), tmp_path, {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    )
    runner = ctx.gateways.get(HostCommandRunner)
    assert isinstance(runner, SubprocessHostCommandRunner)
    assert _which(runner, tmp_path, {}) == 0
