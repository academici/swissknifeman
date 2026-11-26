from pathlib import Path
from types import SimpleNamespace

import pytest

from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot, provider_pool
from skm.adapters.sandbox.bubblewrap import BubblewrapSandbox
from skm.bootstrap.runtimes import build_provider_pool
from skm.kernel.errors import CapabilityUnavailable
from skm.platform.process.runner import run


@pytest.mark.parametrize("runtime_id", ["claude_code", "codex", "cursor", "grok", "antigravity"])
def test_strict_pool_rejects_cli_with_shared_credential_view(tmp_path: Path, runtime_id: str) -> None:
    root = tmp_path / "pool"
    slot = ProviderSlot(runtime_id, "account")
    pool = ProviderPoolManager(root, [slot], strict_isolated=True)
    assert pool.credential_isolation("account") == "unsupported"
    with pytest.raises(CapabilityUnavailable) as error:
        pool.acquire("account", "step", ttl_seconds=60)
    assert error.value.details["credential_isolation"] == "unsupported"
    assert not list(root.iterdir())
    with pytest.raises(ValueError, match="controls its own tool execution"):
        ProviderSlot(runtime_id, "same-account", host_dispatches_tools=True)


def test_strict_pool_requires_available_tool_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(BubblewrapSandbox, "available", lambda self: {"available": False})
    slot = ProviderSlot("host_client", "account", host_dispatches_tools=True)
    pool = build_provider_pool(tmp_path / "pool", [slot], strict_isolated=True)
    with pytest.raises(CapabilityUnavailable) as error:
        pool.acquire("account", "step", ttl_seconds=60)
    assert error.value.details["credential_isolation"] == "unsupported"


def test_strict_pool_checks_lease_from_another_manager(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    slot = ProviderSlot("codex", "account")
    lease = ProviderPoolManager(root, [slot]).acquire("account", "step", ttl_seconds=60)
    assert lease is not None
    strict = ProviderPoolManager(root, [slot], strict_isolated=True)
    with pytest.raises(CapabilityUnavailable) as error, strict.use(lease):
        pytest.fail("an unisolated lease reached the provider client")
    assert error.value.details["credential_isolation"] == "unsupported"


def test_tool_launcher_uses_separate_mounts_and_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pool"
    pool = build_provider_pool(root, [])
    worktree = tmp_path / "checkout"
    tool_home = tmp_path / "tool"

    def wrap(self, argv, *, worktree, step_tmp, protected, writable_worktree):
        assert worktree == tmp_path / "checkout"
        assert step_tmp == tool_home
        assert protected == (root,)
        assert not writable_worktree
        return ("/usr/bin/bwrap", "--", *argv)

    def run_tool(argv, *, cwd, env, timeout_seconds):
        assert argv == ("/usr/bin/bwrap", "--", "/bin/true")
        assert cwd == tmp_path
        assert set(env) == {"PATH", "HOME"}
        assert env["HOME"] == str(tool_home)
        assert timeout_seconds == 5
        return SimpleNamespace(exit_code=0)

    monkeypatch.setattr(BubblewrapSandbox, "filesystem_argv", wrap)
    monkeypatch.setattr(provider_pool, "run", run_tool)
    assert (
        pool.run_tool(("/bin/true",), worktree=worktree, tool_home=tool_home, timeout_seconds=5).exit_code
        == 0
    )
    for overlap in (root, root.parent, root / "account"):
        with pytest.raises(ValueError, match="overlaps the provider pool"):
            pool.run_tool(("/bin/true",), worktree=worktree, tool_home=overlap, timeout_seconds=5)


def test_child_tool_cannot_read_active_credential(tmp_path: Path) -> None:
    probe = BubblewrapSandbox().available()
    if probe["available"] is not True:
        pytest.skip(f"kernel tool boundary unavailable: {probe['reason']}")
    slot = ProviderSlot("host_client", "account", host_dispatches_tools=True)
    pool = build_provider_pool(tmp_path / "pool", [slot], strict_isolated=True)
    lease = pool.acquire("account", "step", ttl_seconds=60)
    assert lease is not None
    assert lease.credential_isolation == "supported"
    worktree, tool_home = tmp_path / "checkout", tmp_path / "tool"
    (worktree / ".git").mkdir(parents=True)
    tool_home.mkdir(mode=0o700)

    with pool.use(lease) as client_home:
        credential = client_home / "auth.json"
        credential.write_text("active-credential-canary", encoding="utf-8")
        credential.chmod(0o600)
        alias = worktree / "alias"
        alias.symlink_to(credential)
        trusted = run(("/bin/cat", str(credential)), cwd=client_home, env={}, timeout_seconds=5)
        assert trusted.exit_code == 0
        assert trusted.stdout == b"active-credential-canary"
        child = pool.run_tool(
            (
                "/bin/sh",
                "-eu",
                "-c",
                'test ! -r "$1" && test ! -r alias && test "$HOME" = "$TMPDIR" && echo tool-ran',
                "sh",
                str(credential),
            ),
            worktree=worktree,
            tool_home=tool_home,
            timeout_seconds=5,
        )
        assert child.exit_code == 0, child.stderr.decode()
        assert child.stdout == b"tool-ran\n"
