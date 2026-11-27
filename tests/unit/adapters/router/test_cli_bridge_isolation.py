"""Verify that the CLI bridge owns per-client workers and temporary credentials."""

import json
import stat
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event, get_ident
from typing import Any

import pytest

from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.adapters.runtimes.pool.provider_pool import SlotRuntimeConfig
from skm.adapters.runtimes.router import cli_bridge
from skm.adapters.runtimes.router.cli_bridge import (
    CliBridge,
    CliRequest,
    ConversationBusy,
    InternalHop,
    WorkerHome,
)
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock


class FakeProcess:
    def __init__(
        self,
        argv: list[str],
        env: dict[str, str],
        cwd: Path,
        stdout: Callable[[bytes], None],
        answer: str,
        name: str,
        gate: Event | None,
    ) -> None:
        self.argv, self.env, self.cwd, self.stdout = argv, env, cwd, stdout
        self.answer, self.name, self.gate = answer, name, gate
        self.stopped = False
        self.turns = 0
        self.wrote = Event()

    def write_stdin(self, data: bytes) -> None:
        self.turns += 1
        self.wrote.set()
        assert json.loads(data)["type"] == "user"
        if self.gate is not None:
            assert self.gate.wait(4)
        result = self.name if self.answer == "@worker" else self.answer
        wire = json.dumps({"type": "result", "result": result}, ensure_ascii=False).encode() + b"\n"
        for offset in range(0, len(wire), 65_536):
            self.stdout(wire[offset : offset + 65_536])

    def terminate(self, *, grace_seconds: float) -> None:
        self.stopped = True

    def wait(self, timeout_seconds: float) -> int | None:
        return 0 if self.stopped else None


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    bridges: list[CliBridge] = []

    @contextmanager
    def home(slot: str, directory: Path, cwd: Path) -> Iterator[dict[str, str]]:
        yield {"HOME": str(directory)}

    def build(
        answer: str = "@worker",
        gate: Event | None = None,
        *,
        worker_home: WorkerHome = home,
        base_url: str | None = "http://127.0.0.1:8317",
        **kwargs: Any,
    ) -> tuple[CliBridge, list[FakeProcess]]:
        processes: list[FakeProcess] = []

        def spawn(
            argv: list[str], *, cwd: Path, env: dict[str, str], on_stdout: Callable[[bytes], None], **_: Any
        ) -> FakeProcess:
            if "--system-prompt-file" in argv:
                system = Path(argv[argv.index("--system-prompt-file") + 1])
                assert stat.S_IMODE(system.stat().st_mode) == 0o600
                assert system.read_text() == "system"
            process = FakeProcess(argv, env, cwd, on_stdout, answer, f"worker-{len(processes)}", gate)
            processes.append(process)
            return process

        monkeypatch.setattr(cli_bridge, "spawn", spawn)
        bridge = CliBridge(
            tmp_path,
            worker_home,
            InternalHop(),
            base_url=base_url,
            generation=1,
            allowed_cwds=kwargs.pop("allowed_cwds", {}),
            **kwargs,
        )
        bridges.append(bridge)
        return bridge, processes

    yield build
    for bridge in bridges:
        bridge.close()


def work(*, hot: bool = False) -> CliRequest:
    return CliRequest("client-a", "conversation", "slot", "model", "system", "user", hot=hot)


def test_ephemeral_uses_private_prompt_and_signed_bare_hop(cli: Any) -> None:
    bridge, processes = cli()
    assert bridge.run(work(), Event()).text == "worker-0"
    (process,) = processes
    assert "--bare" in process.argv
    assert "--no-session-persistence" in process.argv
    assert process.argv[process.argv.index("--tools") + 1] == ""
    assert process.env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8317"
    headers = process.env["ANTHROPIC_CUSTOM_HEADERS"]
    assert headers.startswith("X-SKM-Internal-Hop: 1\n")
    signature = headers.split(": ")[-1]
    assert bridge.hop.authenticate(process.env["ANTHROPIC_API_KEY"], "1", signature) is None
    assert process.stopped
    assert not Path(process.argv[process.argv.index("--system-prompt-file") + 1]).exists()


@pytest.mark.timeout(5)
def test_process_stdout_reassembles_a_long_result(cli: Any) -> None:
    answer = "x" * 70_000 + "é"
    bridge, _ = cli(answer=answer)
    assert bridge.run(work(), Event()).text == answer


def test_direct_cli_serializes_wallet_stage_and_write_back_with_provider_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = ProviderSlot("claude_code", "slot")
    root = tmp_path / "pool"
    pool = ProviderPoolManager(root, [slot])
    lease = pool.acquire(slot.slot_id, "accounts exec", ttl_seconds=60)
    assert lease is not None
    wallet = root / slot.runtime_id / slot.slot_id / "wallet"
    credentials = ".credentials.json"
    initial = b'{"token":"initial"}'
    fresh = b'{"token":"provider-rotation"}'
    with pool.use(lease) as home:
        atomic_write(home / credentials, initial, mode=0o600, private=True)

    provision = cli_bridge.worker_home({}, None, {slot.slot_id: (SlotRuntimeConfig(), root)}, {}, direct=True)
    blocked, staged, finish = Event(), Event(), Event()
    original_acquire = FileLock.acquire
    main_thread = get_ident()

    def observe_acquire(lock: FileLock, **kwargs: Any) -> bool:
        if get_ident() != main_thread and lock.path == wallet / ".credentials.lock":
            if original_acquire(lock):
                return True
            blocked.set()
        return original_acquire(lock, **kwargs)

    def direct_worker() -> None:
        directory = tmp_path / "worker"
        with provision(slot.slot_id, directory, directory) as env:
            isolated = Path(env["CLAUDE_CONFIG_DIR"]) / credentials
            assert isolated.read_bytes() == initial
            atomic_write(isolated, b'{"token":"router-rotation"}', mode=0o600, private=True)
            staged.set()
            assert finish.wait(5)

    monkeypatch.setattr(FileLock, "acquire", observe_acquire)
    with ThreadPoolExecutor(max_workers=1) as threads:
        try:
            with pool.use(lease):
                run = threads.submit(direct_worker)
                assert blocked.wait(2)
                assert not staged.is_set()
            assert staged.wait(2)
            blocked.clear()
            with pool.use(lease) as home:
                atomic_write(home / credentials, fresh, mode=0o600, private=True)
                finish.set()
                assert blocked.wait(2)
                assert not run.done()
            run.result(timeout=4)
        finally:
            finish.set()
    assert (wallet / credentials).read_bytes() == fresh


def test_direct_cli_waits_for_provider_pool_before_saving_credentials(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = ProviderSlot("claude_code", "slot")
    root = tmp_path / "pool"
    pool = ProviderPoolManager(root, [slot])
    lease = pool.acquire(slot.slot_id, "accounts exec", ttl_seconds=60)
    assert lease is not None
    wallet = root / slot.runtime_id / slot.slot_id / "wallet"
    credentials = ".credentials.json"
    initial = b'{"token":"initial"}'
    updated = b'{"token":"router-rotation"}'
    with pool.use(lease) as home:
        atomic_write(home / credentials, initial, mode=0o600, private=True)

    provision = cli_bridge.worker_home({}, None, {slot.slot_id: (SlotRuntimeConfig(), root)}, {}, direct=True)
    gate, saving = Event(), Event()
    bridge, processes = cli(gate=gate, worker_home=provision, base_url=None)
    original_acquire = FileLock.acquire

    def observe_acquire(lock: FileLock, **kwargs: Any) -> bool:
        if gate.is_set() and lock.path == wallet / ".credentials.lock":
            saving.set()
        return original_acquire(lock, **kwargs)

    monkeypatch.setattr(FileLock, "acquire", observe_acquire)
    with ThreadPoolExecutor(max_workers=1) as threads:
        run = threads.submit(bridge.run, work(), Event())
        try:
            for _ in range(100):
                if processes and processes[0].wrote.wait(0.01):
                    break
                gate.wait(0.01)
            (process,) = processes
            assert process.wrote.is_set()
            isolated = Path(process.env["CLAUDE_CONFIG_DIR"]) / credentials
            assert isolated.read_bytes() == initial
            with pool.use(lease):
                atomic_write(isolated, updated, mode=0o600, private=True)
                gate.set()
                assert saving.wait(2)
                with pytest.raises(TimeoutError):
                    run.result(timeout=3.5)
            assert run.result(timeout=4).text == "worker-0"
        finally:
            gate.set()

    assert (wallet / credentials).read_bytes() == updated
    assert (wallet / f"{credentials}.prev").read_bytes() == initial


def test_hot_pool_isolates_client_conversation_and_slot(cli: Any) -> None:
    bridge, processes = cli()
    first = work(hot=True)
    assert bridge.run(first, Event()).text == "worker-0"
    process = processes[0]
    headers = process.env["ANTHROPIC_CUSTOM_HEADERS"]
    assert (
        bridge.hop.authenticate(process.env["ANTHROPIC_API_KEY"], "1", headers.split(": ")[-1])
        == first.client_id
    )
    assert bridge.run(first, Event()).text == "worker-0"
    assert bridge.run(replace(first, client_id="client-b"), Event()).text == "worker-1"
    assert bridge.run(replace(first, conversation_id="different"), Event()).text == "worker-2"
    assert bridge.run(replace(first, slot_id="other"), Event()).text == "worker-3"
    assert [process.turns for process in processes] == [2, 1, 1, 1]
    assert all("--tools" in process.argv and "plan" in process.argv for process in processes)


def test_only_one_turn_can_run_and_tools_require_client_cwd_grant(cli: Any, tmp_path: Path) -> None:
    gate = Event()
    folder = tmp_path / "allowed"
    folder.mkdir()
    bridge, processes = cli(gate=gate, allowed_cwds={"client-a": (folder,)})
    first = replace(work(hot=True), cwd=folder)
    with pytest.raises(ValueError, match="grant"):
        bridge.run(replace(first, client_id="client-b"), Event())
    with pytest.raises(ValueError, match="grant"):
        bridge.run(replace(first, hot=False), Event())
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(bridge.run, first, Event())
        try:
            for _ in range(100):
                if processes and processes[0].wrote.wait(0.01):
                    break
                gate.wait(0.01)
            assert processes
            assert processes[0].wrote.is_set()
            with pytest.raises(ConversationBusy):
                bridge.run(first, Event())
        finally:
            gate.set()
        assert active.result(timeout=4).text == "worker-0"
    assert processes[0].cwd == folder
    assert "--tools" not in processes[0].argv


def test_structured_retries_refuse_and_lru_evicts(cli: Any) -> None:
    bridge, processes = cli(answer="invalid JSON", capacity=1)
    first = replace(work(hot=True), schema={"type": "integer"})
    assert bridge.run(first, Event()).refusal
    assert processes[0].turns == 4
    assert not processes[0].stopped
    bridge.run(replace(first, conversation_id="new"), Event())
    assert processes[0].stopped
    assert processes[1].turns == 4


def test_idle_hot_worker_expires(cli: Any) -> None:
    bridge, processes = cli(ttl=0.03)
    bridge.run(work(hot=True), Event())
    for _ in range(100):
        if processes[0].stopped:
            break
        Event().wait(0.01)
    assert processes[0].stopped
    assert bridge.run(work(hot=True), Event()).text == "worker-1"
