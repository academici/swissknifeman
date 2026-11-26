"""Bounded argv-only command execution in an isolated process group."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast, override

from skm.modules.integrations.domain.reports import CommandResult
from skm.modules.integrations.ports import HostCommandRunner

__all__ = ["LocalSubscriptionState", "SubprocessHostCommandRunner"]


class SubprocessHostCommandRunner(HostCommandRunner):
    def __init__(self, *, lookup_path: str | None = None) -> None:
        # Executable search path of the session the clients inherit; used only when ``env`` has no PATH.
        self._lookup_path = lookup_path

    @classmethod
    def for_session(cls, environ: Mapping[str, str]) -> SubprocessHostCommandRunner:
        """A runner whose lookups use the absolute PATH entries native clients inherit from ``environ``."""
        entries = [entry for entry in environ.get("PATH", "").split(os.pathsep) if os.path.isabs(entry)]
        return cls(lookup_path=os.pathsep.join(entries) or None)

    @override
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        stdin: bytes,
        timeout_ms: int,
        max_stdout: int = 65536,
        max_stderr: int = 8192,
    ) -> CommandResult:
        from skm.platform.process.runner import run

        started = time.monotonic()
        if (
            not argv
            or len(argv) > 64
            or sum(len(arg.encode()) for arg in argv) > 65536
            or len(stdin) > 1_048_576
            or max_stdout < 0
            or max_stderr < 0
        ):
            raise ValueError("command input exceeds limits")
        if timeout_ms <= 0:
            return CommandResult(None, b"", b"", 0, True)
        if self._lookup_path and "PATH" not in env:
            env = {**env, "PATH": self._lookup_path}
        try:
            # The platform runner owns the session/group, closes inherited fds and uses argv without a shell.
            result = run(
                argv,
                cwd=cwd,
                env=env,
                stdin=stdin,
                timeout_seconds=timeout_ms / 1000,
                max_stdout_bytes=min(max_stdout, 65536),
                max_stderr_bytes=min(max_stderr, 8192),
                grace_seconds=0,
            )
        except FileNotFoundError:
            return CommandResult(None, b"", b"not found", int((time.monotonic() - started) * 1000), False)
        except OSError:
            return CommandResult(None, b"", b"spawn failed", int((time.monotonic() - started) * 1000), False)
        return CommandResult(
            result.exit_code,
            result.stdout,
            result.stderr,
            int(result.duration_seconds * 1000),
            result.timed_out,
        )


class LocalSubscriptionState:
    """Private host state and scheduling IO for subscription operations, composed by bootstrap."""

    def __init__(
        self,
        state_dir: Path,
        *,
        environ: Mapping[str, str],
        request_factory: object,
        secrets: object,
        config_provider: Callable[[], object] | None = None,
        native_drain: bool = False,
    ) -> None:
        self._root = state_dir / "hooks"
        self._state_dir = state_dir
        self._environ = dict(environ)
        self._factory = request_factory
        self._secrets = secrets
        self._config_provider = config_provider
        self._native_drain = native_drain
        from skm.platform.system_clock import SystemClock
        from skm.platform.system_ids import Uuid7Generator

        self._clock = SystemClock()
        self._ids = Uuid7Generator(self._clock)

    def host_config(self) -> object | None:
        return None if self._config_provider is None else self._config_provider()

    def request(self, name: str, payload: dict[str, object]) -> object:

        return cast("Any", self._factory)(name, payload)

    def monotonic(self) -> float:
        return time.monotonic()

    def new_id(self) -> str:
        return str(self._ids.new_id())

    def now(self) -> datetime:
        return self._clock.now()

    def cwd(self, kind: str, checkout: str) -> Path:
        return self._state_dir if kind == "state_dir" else Path(checkout)

    def environment(self, allowed: Sequence[str], refs: Mapping[str, str]) -> dict[str, str]:

        names = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", *allowed}
        env = {
            key: self._environ[key]
            for key in names
            if key in self._environ and not key.upper().startswith("SKM_")
        }
        for key, ref in refs.items():
            if key.upper().startswith("SKM_") or ref.upper().startswith("SECRET://ENV/SKM_"):
                continue
            value = cast("Any", self._secrets).resolve(ref)
            env[key] = value.reveal() if hasattr(value, "reveal") else str(value)
        if len(env) > 128 or sum(len(key) + len(value) for key, value in env.items()) > 131072:
            raise ValueError("command environment exceeds limits")
        return env

    def parallel[T](self, actions: Sequence[Callable[[], T]], limit: int) -> list[T]:
        from concurrent.futures import ThreadPoolExecutor

        if not actions:
            return []
        with ThreadPoolExecutor(max_workers=min(max(1, limit), len(actions))) as pool:
            futures = [pool.submit(action) for action in actions]
            return [future.result() for future in futures]

    def _directory(self, path: Path) -> None:
        import stat

        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("subscription state directory must be private and owned")

    def audit(self, record: dict[str, object]) -> None:
        import json

        self._directory(self._root)
        # Only explicitly selected metadata; no process input/output or secret values.
        data = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        fd = os.open(
            self._root / "audit.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
        )
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def locked(self) -> Generator[bool]:
        import fcntl

        self._directory(self._root)
        fd = os.open(self._root / "spool.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                yield True
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def _mutation(self) -> Generator[None]:
        import fcntl

        self._directory(self._root)
        fd = os.open(self._root / "spool-mutation.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _entries(self) -> list[Path]:
        import stat

        spool = self._root / "spool"
        self._directory(spool)
        entries: list[Path] = []
        for directory in spool.iterdir():
            if directory.is_symlink() or not directory.is_dir():
                continue
            self._directory(directory)
            entries.extend(
                path
                for path in directory.iterdir()
                if path.suffix == ".json" and stat.S_ISREG(path.lstat().st_mode)
            )
        return sorted(entries, key=lambda path: path.name)

    def enqueue(self, document: dict[str, object], limit: int) -> None:
        import json

        from skm.platform.fs.atomic_write import atomic_write

        if limit <= 0:
            return
        with self._mutation():
            entries = self._entries()
            for path in entries[: max(0, len(entries) - limit + 1)]:
                path.unlink()
            subscription_id = str(cast("Any", document)["input"]["subscription_id"])
            if (
                not subscription_id
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for c in subscription_id)
                or subscription_id in {".", ".."}
            ):
                raise ValueError("invalid subscription id")
            directory = self._root / "spool" / subscription_id
            self._directory(directory)
            name = f"{self.new_id()}.json"
            atomic_write(directory / name, json.dumps(document).encode(), private=True)

    def pending(self) -> list[tuple[str, dict[str, Any]]]:
        import json

        with self._mutation():
            result: list[tuple[str, dict[str, Any]]] = []
            for path in self._entries():
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    raw = os.read(fd, 1_048_577)
                finally:
                    os.close(fd)
                try:
                    value = json.loads(raw) if len(raw) <= 1_048_576 else None
                except (ValueError, RecursionError):
                    value = None
                if not isinstance(value, dict):
                    path.unlink()
                    continue
                result.append((str(path.relative_to(self._root / "spool")), cast("dict[str, Any]", value)))
            return result

    def replace(self, key: str, document: dict[str, object] | None) -> None:
        import json

        from skm.platform.fs.atomic_write import atomic_write

        path = Path(key)
        if path.is_absolute() or len(path.parts) != 2 or any(part in {".", ".."} for part in path.parts):
            raise ValueError("invalid spool key")
        with self._mutation():
            destination = self._root / "spool" / path
            self._directory(destination.parent)
            if document is None:
                destination.unlink(missing_ok=True)
            else:
                atomic_write(destination, json.dumps(document).encode(), private=True)

    def start_drain(self, bootstrap_path: str | None) -> None:
        """Detach only after the hook response is flushed; the drainer owns its spool lock."""
        import subprocess
        import sys

        if not self.pending():
            return
        with self.locked() as acquired:
            if not acquired:
                return
        if self._native_drain:
            argv = [sys.executable, "-I", "-m", "skm.bootstrap.hook", "--subscriptions"]
            if bootstrap_path is not None:
                argv.append(bootstrap_path)
        else:
            argv = [sys.executable, "-m", "skm.entrypoints.cli.main"]
            if bootstrap_path is not None:
                argv.extend(("--bootstrap", bootstrap_path))
            argv.extend(("hooks", "drain"))
        # The daemon deliberately outlives this hook; the platform runner owns ordinary child lifetimes.
        subprocess.Popen(  # noqa: TID251 - specified detached drain, stdio never belongs to the client
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
            close_fds=True,
            env=self._environ,
        )
