import multiprocessing
import os
import stat
import sys
from multiprocessing.connection import Connection
from pathlib import Path

import pytest

from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.adapters.runtimes.pool import shallow_home as homes
from skm.adapters.runtimes.pool.provider_pool import SlotRuntimeConfig
from skm.adapters.runtimes.pool.shallow_home import ShallowHome, fingerprint_credentials
from skm.bootstrap.provider_accounts import ProviderAccounts
from skm.bootstrap.runtimes import build_provider_pool
from skm.kernel.errors import ValidationFailed
from skm.platform.fs.atomic_write import atomic_write

_SLOT = ProviderSlot("codex", "account")
_OLD = b'{"token":"original"}'
_NEW = b'{"token":"rotated"}'


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_home_default_and_explicit_ssh_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host, home, wallet = (tmp_path / name for name in ("host", "session", "wallet"))
    (host / ".ssh").mkdir(parents=True)
    (host / ".claude.json").write_bytes(b'{"host":true}')
    monkeypatch.setattr(sys, "platform", "darwin")
    layout = ShallowHome(home, wallet, host)
    assert layout.symlink_host_files == ()
    layout.prepare("claude_code")
    assert not (home / ".ssh").exists()
    assert (home / ".claude.json").read_bytes() == b"{}\n"
    assert _mode(home) == _mode(wallet) == _mode(home / "Library") == 0o700
    assert _mode(home / ".claude.json") == 0o600
    ShallowHome(home, wallet, host, (".ssh",)).prepare("claude_code")
    assert (home / ".ssh").readlink() == host / ".ssh"
    layout.prepare("claude_code")
    assert not (home / ".ssh").is_symlink()
    with pytest.raises(ValidationFailed, match="invalid host file link"):
        ShallowHome(home, wallet, host, (".CODEX",)).prepare("claude_code")
    with pytest.raises(ValidationFailed, match="overlaps"):
        ShallowHome(home, wallet, host).prepare("claude_code", workdir=tmp_path / "SESSION")
    (host / "ssh-alias").symlink_to(host / ".ssh")
    with pytest.raises(ValidationFailed, match="explicit"):
        ShallowHome(home, wallet, host, ("ssh-alias",)).prepare("claude_code")


@pytest.mark.parametrize(
    "name", ["/root", "C:/root", "../other", "config/Library", "x/.codex-local", ".claude.json", ".gemini"]
)
def test_disallowed_host_paths_are_rejected(tmp_path: Path, name: str) -> None:
    layout = ShallowHome(tmp_path / "home", tmp_path / "wallet", tmp_path, (name,))
    with pytest.raises(ValidationFailed):
        layout.prepare("codex")
    assert not (tmp_path / "home").exists()


def test_paths_are_validated_before_chmod_or_mkdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "work"
    work.mkdir(mode=0o755)
    alias = tmp_path / "alias"
    alias.symlink_to(work, target_is_directory=True)
    root = tmp_path / "pool"
    root.mkdir(mode=0o755)

    with pytest.raises(ValidationFailed, match="symlink"):
        ShallowHome(alias / "home", tmp_path / "wallet").prepare("codex")
    with pytest.raises(ValidationFailed, match="overlaps"):
        ProviderPoolManager(
            root,
            [_SLOT],
            workdir=work,
            configs={
                "account": SlotRuntimeConfig(shallow_home=work),
            },
        )
    with monkeypatch.context() as patch:
        patch.setattr(os, "geteuid", lambda: root.stat().st_uid + 1)
        with pytest.raises(ValidationFailed, match="owned"):
            ProviderPoolManager(root, [_SLOT])
    assert _mode(root) == _mode(work) == 0o755
    assert not (work / "home").exists()


@pytest.mark.parametrize("field", ["shallow_home", "wallet_path"])
@pytest.mark.parametrize("explicit_workdir", [True, False])
def test_pool_factory_refuses_checkout_paths_before_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, explicit_workdir: bool
) -> None:
    root, work = tmp_path / "pool", tmp_path / "checkout"
    root.mkdir(mode=0o755)
    target = work / "credentials"
    target.mkdir(mode=0o755, parents=True)
    host = tmp_path / "host"
    registry = host / ".config/skm/provider-pool.toml"
    atomic_write(
        registry,
        (
            'schema_version = 2\n[slots.account]\nruntime_id = "codex"\ntransport = "cli_subprocess"\n'
            f'{field} = "{target}"\n'
        ).encode(),
        mode=0o600,
        private=True,
    )
    monkeypatch.setenv("HOME", str(host))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(registry.parent.parent))
    if not explicit_workdir:
        monkeypatch.chdir(work)
    with pytest.raises(ValidationFailed, match="overlaps"):
        build_provider_pool(root, workdir=work if explicit_workdir else None)

    assert _mode(root) == _mode(target) == 0o755
    assert not list(root.iterdir())
    assert not list(target.iterdir())


@pytest.mark.parametrize("field", ["shallow_home", "wallet_path"])
@pytest.mark.parametrize("via_accounts", [True, False], ids=["accounts", "manager"])
def test_pool_refuses_checkout_paths_with_implicit_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, via_accounts: bool
) -> None:
    root, checkout = tmp_path / "pool", tmp_path / "checkout"
    root.mkdir(mode=0o755)
    target = checkout / "credentials"
    target.mkdir(mode=0o755, parents=True)
    config = SlotRuntimeConfig(shallow_home=target)
    if field == "wallet_path":
        config = SlotRuntimeConfig(wallet_path=target)
    configs = {_SLOT.slot_id: config}
    monkeypatch.chdir(checkout)

    if via_accounts:
        accounts = ProviderAccounts((_SLOT,), None, configs, pool_root=root)
        with pytest.raises(ValidationFailed, match="overlaps"):
            accounts.pool()
    else:
        with pytest.raises(ValidationFailed, match="overlaps"):
            ProviderPoolManager(root, [_SLOT], configs=configs)

    assert _mode(root) == _mode(target) == 0o755
    assert not list(root.iterdir())
    assert not list(target.iterdir())


@pytest.mark.parametrize("nested", [False, True])
def test_conflicting_slot_paths_are_rejected_before_provisioning(tmp_path: Path, nested: bool) -> None:
    root = tmp_path / "pool"
    shared = tmp_path / "shared"
    other = ProviderSlot("claude_code", "other")
    with pytest.raises(ValidationFailed, match="overlap"):
        ProviderPoolManager(
            root,
            [_SLOT, other],
            configs={
                "account": SlotRuntimeConfig(wallet_path=shared),
                "other": SlotRuntimeConfig(shallow_home=shared / "nested" if nested else shared),
            },
        )
    assert not root.exists()
    assert not shared.exists()


def _refresh_worker(
    root: Path,
    wallet: Path,
    channel: Connection,
    update: bool,
) -> None:
    pool = ProviderPoolManager(root, [_SLOT], configs={"account": SlotRuntimeConfig(wallet_path=wallet)})
    lease = pool.acquire("account", "worker", ttl_seconds=30)
    assert lease is not None

    def refresh(home: Path) -> None:
        channel.send_bytes(b"entered")
        if update:
            assert channel.recv_bytes() == b"release"
            atomic_write(home / "auth.json", _NEW, mode=0o600, private=True)
        else:
            channel.send_bytes((home / "auth.json").read_bytes())

    channel.send_bytes(b"ready")
    try:
        pool.refresh(lease, refresh)
    finally:
        pool.release(lease)
        channel.close()


def test_two_processes_lock_the_authoritative_wallet(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    wallet = tmp_path / "wallet"
    atomic_write(wallet / "auth.json", _OLD, mode=0o600, private=True)
    first, first_child = context.Pipe()
    second, second_child = context.Pipe()
    writer = context.Process(target=_refresh_worker, args=(tmp_path / "pool1", wallet, first_child, True))
    reader = context.Process(target=_refresh_worker, args=(tmp_path / "pool2", wallet, second_child, False))

    def receive(channel: Connection) -> bytes:
        assert channel.poll(8)
        return channel.recv_bytes()

    writer.start()
    try:
        assert receive(first) == b"ready"
        assert receive(first) == b"entered"
        reader.start()
        assert receive(second) == b"ready"
        assert not second.poll(0.15)
        first.send_bytes(b"release")
        assert receive(second) == b"entered"
        assert receive(second) == _NEW
        writer.join(8)
        reader.join(8)
        assert (writer.exitcode, reader.exitcode) == (0, 0)
    finally:
        for process in (writer, reader):
            if process.is_alive():
                process.kill()
                process.join()
        for channel in (first, second, first_child, second_child):
            channel.close()
    assert (wallet / ".credentials.lock").is_file()


@pytest.mark.parametrize("partial", [False, True])
def test_wallet_recovery_and_no_secret_in_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    path = tmp_path / "wallet" / "auth.json"
    atomic_write(path, _OLD, mode=0o600, private=True)
    original = fingerprint_credentials(path)
    events: list[tuple[str, str]] = []

    def fail_second(target: Path, data: bytes, *, mode: int, private: bool) -> None:
        if target == path:
            if partial:
                target.write_bytes(b'{"token":')
            raise OSError("simulated lost write")
        atomic_write(target, data, mode=mode, private=private)

    with monkeypatch.context() as patch:
        patch.setattr(homes, "atomic_write", fail_second)
        with pytest.raises(OSError, match="simulated lost write"):
            homes.write_wallet_credentials(path, _NEW)
    if not partial:
        assert path.read_bytes() == _OLD
    backup = path.with_name("auth.json.prev")
    assert backup.read_bytes() == _OLD
    assert _mode(backup) == 0o600
    monkeypatch.setattr(
        homes._LOG,
        "warning",
        lambda event, *, credential: events.append((event, credential)),
    )
    assert homes.read_wallet_credentials(path) == _OLD
    assert events == ([("runtimes.provider_wallet_recovered", path.name)] if partial else [])
    assert fingerprint_credentials(path) == original
    homes.write_wallet_credentials(path, _NEW)
    assert fingerprint_credentials(path) != original


def test_read_only_wallet_and_bounded_nofollow_fingerprint(tmp_path: Path) -> None:
    pool = ProviderPoolManager(
        tmp_path / "pool",
        [_SLOT],
        configs={
            "account": SlotRuntimeConfig(write_back=False),
        },
    )
    wallet = tmp_path / "pool/codex/account/wallet/auth.json"
    atomic_write(wallet, _OLD, mode=0o600, private=True)
    lease = pool.acquire("account", "worker", ttl_seconds=30)
    assert lease is not None
    pool.refresh(lease, lambda home: atomic_write(home / "auth.json", _NEW, mode=0o600, private=True))
    assert wallet.read_bytes() == _OLD
    assert not wallet.with_name("auth.json.prev").exists()
    assert pool.refresh(lease, lambda home: (home / "auth.json").read_bytes()) == _OLD
    symlink = tmp_path / "symlink"
    symlink.symlink_to(wallet)
    assert fingerprint_credentials(symlink) is None
    huge_file = tmp_path / "huge"
    huge_file.write_bytes(b"x" * (1024 * 1024 + 1))
    assert fingerprint_credentials(huge_file) is None
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    assert fingerprint_credentials(fifo) is None


def test_empty_wallet_discards_session_credentials_before_use(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    pool = ProviderPoolManager(root, [_SLOT])
    lease = pool.acquire("account", "worker", ttl_seconds=30)
    assert lease is not None
    atomic_write(lease.client_home / "auth.json", _OLD, mode=0o600, private=True)

    with pool.use(lease) as home:
        assert not (home / "auth.json").exists()

    wallet = root / "codex/account/wallet"
    assert not (wallet / "auth.json").exists()
    assert not (wallet / "auth.json.prev").exists()


@pytest.mark.parametrize("via_refresh", [True, False])
@pytest.mark.parametrize("write_back", [True, False])
def test_credentials_rotated_before_failure_are_persisted_only_with_write_back(
    tmp_path: Path, via_refresh: bool, write_back: bool
) -> None:
    root = tmp_path / "pool"
    pool = ProviderPoolManager(root, [_SLOT], configs={"account": SlotRuntimeConfig(write_back=write_back)})
    wallet = root / "codex/account/wallet/auth.json"
    atomic_write(wallet, _OLD, mode=0o600, private=True)
    lease = pool.acquire("account", "worker", ttl_seconds=30)
    assert lease is not None

    def rotate_then_fail(home: Path) -> None:
        atomic_write(home / "auth.json", _NEW, mode=0o600, private=True)
        raise RuntimeError("client failed after rotation")

    if via_refresh:
        with pytest.raises(RuntimeError, match="client failed after rotation"):
            pool.refresh(lease, rotate_then_fail)
    else:
        with pytest.raises(RuntimeError, match="client failed after rotation"), pool.use(lease) as home:
            rotate_then_fail(home)

    expected = _NEW if write_back else _OLD
    assert wallet.read_bytes() == expected
    backup = wallet.with_name("auth.json.prev")
    if write_back:
        assert backup.read_bytes() == _OLD
    else:
        assert not backup.exists()
    assert pool.refresh(lease, lambda home: (home / "auth.json").read_bytes()) == expected
