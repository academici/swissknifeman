"""Coordinate account slots across workers that share a trusted local pool directory."""

from __future__ import annotations

import json
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast
from uuid import uuid4

from skm.adapters.runtimes._cli_session.launch import ensure_private_dir
from skm.adapters.runtimes.pool.rate_limit import RateLimitAction, RateLimitDecision
from skm.adapters.runtimes.pool.shallow_home import ShallowHome, paths_overlap, validate_directory
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed, ValidationFailed
from skm.modules.runtimes.domain.ids import is_runtime_id
from skm.platform.fs.atomic_write import assert_safe_replace_target, atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.process.runner import run
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping, Sequence

    from skm.adapters.runtimes._cli_session.proxy_bridge import ProxyEndpoint
    from skm.kernel.clock import Clock
    from skm.kernel.json_types import JsonObject
    from skm.modules.runtimes.domain.request import AgentRequest
    from skm.platform.config.secrets import SecretRef
    from skm.platform.process.runner import ProcessResult

__all__ = ["ProviderPoolManager", "ProviderSlot", "SessionPin", "SlotLease", "SlotModel", "SlotRuntimeConfig"]

type CredentialIsolation = Literal["supported", "unsupported"]
type Transport = Literal["cli_subprocess", "http_api", "oauth_gateway"]

_SLOT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_CLI_RUNTIMES = frozenset({"antigravity", "claude_code", "codex", "cursor", "gemini_cli", "grok"})


class _ToolSandbox(Protocol):
    """Trusted host backend with a private filesystem and no ambient tool credentials."""

    def available(self) -> JsonObject: ...

    def filesystem_argv(
        self,
        argv: Sequence[str],
        *,
        worktree: Path,
        step_tmp: Path,
        protected: Sequence[Path],
        writable_worktree: bool,
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class SlotModel:
    name: str
    is_compat: bool = False


@dataclass(frozen=True, slots=True)
class SlotRuntimeConfig:
    """Host-only configuration. Public serializers receive ProviderSlot instead."""

    proxy: ProxyEndpoint | None = field(default=None, repr=False)
    wallet_path: Path | None = None
    shallow_home: Path | None = None
    symlink_host_files: tuple[str, ...] = ()
    write_back: bool = True
    worker_mode: Literal["ephemeral", "hot_pool"] = "ephemeral"
    provider: str | None = None
    base_url: str | None = field(default=None, repr=False)
    api_key_ref: SecretRef | None = field(default=None, repr=False)
    token_file: Path | None = field(default=None, repr=False)
    provider_routing: Mapping[str, bool] = field(default_factory=dict[str, bool])


@dataclass(frozen=True, slots=True)
class ProviderSlot:
    """Host-registered account. Host dispatch requires a trusted client with no internal tool execution."""

    runtime_id: str
    slot_id: str
    host_dispatches_tools: bool = False
    tier: int = 1
    transport: Transport = "cli_subprocess"
    models: tuple[SlotModel, ...] = ()
    has_egress_proxy: bool = False
    proxy_scheme: str | None = None

    def __post_init__(self) -> None:
        if not is_runtime_id(self.runtime_id) or not _SLOT_ID.fullmatch(self.slot_id):
            raise ValueError("invalid provider runtime or slot ID")
        if self.host_dispatches_tools and self.runtime_id in _CLI_RUNTIMES:
            raise ValueError("the stock provider CLI controls its own tool execution")


@dataclass(frozen=True, slots=True)
class SessionPin:
    """Account identity stored by the host alongside the provider session reference."""

    slot: ProviderSlot
    client_home: Path
    session_ref: str


@dataclass(frozen=True, slots=True)
class SlotLease:
    slot: ProviderSlot
    owner_id: str
    client_home: Path
    expires_at: datetime
    credential_isolation: CredentialIsolation
    lease_id: str = field(repr=False)

    def resume_ref(self, previous: SessionPin | None, *, required: bool = False) -> str | None:
        """Filter an otherwise admitted resume. An unknown pin or a slot switch requires a fresh session."""
        if previous is not None and ((previous.slot, previous.client_home) == (self.slot, self.client_home)):
            return previous.session_ref
        if required:
            raise PreconditionFailed(
                ErrorCode.ADMISSION_REFUSED,
                "the resume requires the original provider slot",
                details={"reason": "resume_required_unavailable", "fresh_reason": "ROUTE_CHANGED"},
            )
        return None

    def bind_request(self, request: AgentRequest, *, previous: SessionPin | None = None) -> AgentRequest:
        """Bind an admitted step to this account home while the pool holds `use`.

        The caller provisions the slot's credentials and disables host credential copying on the CLI adapter.
        """
        if (request.runtime_id, request.request_id) != (self.slot.runtime_id, self.owner_id):
            raise ValueError("provider slot lease belongs to another step or runtime")
        if request.config_mode != "isolated":
            raise ValueError("provider slots require an isolated client home")
        if request.resume_session_ref is not None and request.resume_session_ref != self.resume_ref(previous):
            raise ValueError("admit a fresh session before moving to another provider slot")
        if paths_overlap(self.client_home, Path(request.workdir).resolve()):
            raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "provider home overlaps the workdir")
        return replace(request, client_home=str(self.client_home))


def _read_lease(path: Path) -> tuple[str, datetime] | None:
    try:
        document: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    match document:
        case [str(token), str(expires)]:
            return token, datetime.fromisoformat(expires)
        case _:
            raise ValueError("invalid provider lease record")


class ProviderPoolManager:
    """Lease accounts and mediate tools on a single host.

    The pool directory is private, on a local filesystem, and shared by all pool callers on the host.
    Register each account exactly once under a stable slot ID. Hold `use` through the trusted client's
    full credential use, including process cleanup. An in-flight use or refresh keeps the slot locked
    even if its lease expires. An expired idle lease is reclaimable and its token cannot release a successor.
    """

    def __init__(  # noqa: PLR0913 - host bindings and optional slot layout
        self,
        root: Path,
        slots: Iterable[ProviderSlot],
        *,
        strict_isolated: bool = False,
        clock: Clock | None = None,
        tool_sandbox: _ToolSandbox | None = None,
        configs: Mapping[str, SlotRuntimeConfig] | None = None,
        host_home: Path | None = None,
        workdir: Path | None = None,
        initialize: bool = True,
    ) -> None:
        self._slots: dict[str, ProviderSlot] = {}
        for slot in slots:
            if slot.slot_id in self._slots:
                raise ValueError(f"duplicate provider slot: {slot.slot_id}")
            self._slots[slot.slot_id] = slot
        self._root = validate_directory(root)
        self._workdir = (Path.cwd() if workdir is None else workdir).resolve()
        if paths_overlap(self._root, self._workdir):
            raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "provider pool overlaps the workdir")
        self._homes: dict[str, ShallowHome] = {}
        paths: list[Path] = []
        for slot in self._slots.values():
            config = (configs or {}).get(slot.slot_id, SlotRuntimeConfig())
            directory = self._directory(slot)
            home = ShallowHome(
                session_home=(config.shallow_home or directory / "client").absolute(),
                wallet=(config.wallet_path or directory / "wallet").absolute(),
                host_home=host_home,
                symlink_host_files=config.symlink_host_files,
                write_back=config.write_back,
            )
            for target, default in ((home.session_home, "client"), (home.wallet, "wallet")):
                if paths_overlap(target, self._root) and target != directory / default:
                    raise ValidationFailed(
                        ErrorCode.RUNTIME_INVALID_REQUEST, "configured provider directory overlaps the pool"
                    )
            paths.extend((home.session_home, home.wallet))
            self._homes[slot.slot_id] = home
        if len(set(paths)) != len(paths):
            raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "provider slot directories overlap")
        for home in self._homes.values():
            home.validate(
                workdir=self._workdir,
                reserved=tuple(path for path in paths if path not in (home.session_home, home.wallet)),
            )
        for slot in self._slots.values():
            validate_directory(self._directory(slot), owned_from=self._root)
        if initialize:
            ensure_private_dir(self._root)
        self._strict_isolated = strict_isolated
        self._clock = clock if clock is not None else SystemClock()
        self._sandbox = tool_sandbox

    def credential_isolation(self, slot_id: str) -> CredentialIsolation:
        slot = self._slots[slot_id]
        if (
            slot.host_dispatches_tools
            and self._sandbox is not None
            and self._sandbox.available()["available"] is True
        ):
            return "supported"
        return "unsupported"

    def _directory(self, slot: ProviderSlot) -> Path:
        return self._root / slot.runtime_id / slot.slot_id

    def _slot_dir(self, slot: ProviderSlot) -> Path:
        directory = validate_directory(self._directory(slot), owned_from=self._root)
        for path in (self._root, directory.parent, directory):
            ensure_private_dir(path)
        return directory

    def active_slots(self) -> tuple[ProviderSlot, ...]:
        """Read the unexpired lease records without exposing lease owners or tokens."""
        now = self._clock.now()
        active: list[ProviderSlot] = []
        for slot in self._slots.values():
            directory = validate_directory(self._directory(slot), owned_from=self._root)
            current = _read_lease(directory / "lease.json")
            if current is not None and (current[1] > now or self._slot_in_use(directory)):
                active.append(slot)
        return tuple(active)

    @staticmethod
    def _slot_in_use(directory: Path) -> bool:
        lock = FileLock(directory / "slot.lock", create=False, readonly=True)
        try:
            if not lock.acquire():
                return True
        except FileNotFoundError:
            return False
        except RuntimeError:
            # FileLock refuses a second acquisition by the thread already holding the lease.
            return True
        lock.release()
        return False

    def _check_isolation(self, slot: ProviderSlot) -> CredentialIsolation:
        isolation = self.credential_isolation(slot.slot_id)
        if self._strict_isolated and isolation == "unsupported":
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "provider slot has no proven credential isolation",
                details={"runtime_id": slot.runtime_id, "credential_isolation": isolation},
            )
        return isolation

    def acquire(self, slot_id: str, owner_id: str, *, ttl_seconds: float) -> SlotLease | None:
        """Return a new lease, or None while the slot is busy."""
        if not owner_id or not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("a lease needs an owner and a finite, positive TTL")
        slot = self._slots[slot_id]
        isolation = self._check_isolation(slot)
        home = self._homes[slot_id]
        home.validate(workdir=self._workdir)
        directory = self._slot_dir(slot)
        lock = FileLock(directory / "slot.lock")
        if not lock.acquire():
            return None
        try:
            now = self._clock.now()
            path = directory / "lease.json"
            current = _read_lease(path)
            if current is not None and current[1] > now:
                return None
            lease = SlotLease(
                slot,
                owner_id,
                ensure_private_dir(home.session_home),
                now + timedelta(seconds=ttl_seconds),
                isolation,
                uuid4().hex,
            )
            record = json.dumps([lease.lease_id, lease.expires_at.isoformat()])
            atomic_write(path, record.encode("utf-8"), private=True)
            return lease
        finally:
            lock.release()

    def acquire_ranked(
        self, slots: Iterable[ProviderSlot], owner_id: str, *, ttl_seconds: float, model: str | None = None
    ) -> SlotLease | None:
        """Lease the highest-ranked available slot outside its cooling period for this model."""
        if model is None:
            return self._acquire_ranked(slots, owner_id, ttl_seconds)
        with FileLock(self._root / "rotation.lock").hold(timeout_seconds=None):
            _, cooldowns = self._read_rotation()
            now = self._clock.now()
            blocked = frozenset(
                slot_id
                for slot_id, models in cooldowns.items()
                if model in models and datetime.fromisoformat(models[model]) > now
            )
            return self._acquire_ranked(slots, owner_id, ttl_seconds, blocked=blocked)

    def _acquire_ranked(
        self,
        slots: Iterable[ProviderSlot],
        owner_id: str,
        ttl_seconds: float,
        *,
        blocked: frozenset[str] = frozenset(),
    ) -> SlotLease | None:
        for slot in slots:
            if self._slots.get(slot.slot_id) != slot:
                raise ValueError("ranked slot belongs to another pool")
            if slot.slot_id in blocked:
                continue
            lease = self.acquire(slot.slot_id, owner_id, ttl_seconds=ttl_seconds)
            if lease is not None:
                return lease
        return None

    def _read_rotation(self) -> tuple[int, dict[str, dict[str, str]]]:
        try:
            generation, cooldowns = json.loads((self._root / "rotation.json").read_bytes())
        except FileNotFoundError:
            return 0, {}
        return cast("int", generation), cast("dict[str, dict[str, str]]", cooldowns)

    @property
    def route_generation(self) -> int:
        with FileLock(self._root / "rotation.lock").hold(timeout_seconds=None):
            return self._read_rotation()[0]

    def handle_rate_limit(
        self,
        slot_id: str,
        model: str,
        decision: RateLimitDecision,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RateLimitDecision:
        """Publish one cooldown per failing route and wait outside the shared rotation lock."""
        if slot_id not in self._slots or not model:
            raise ValueError("rate limit route needs a registered slot and model")
        decision = self._apply_cooldown(slot_id, model, decision)
        if decision.action is RateLimitAction.WAIT_SAME_SLOT:
            sleep(decision.wait_s)
            decision = self._apply_cooldown(slot_id, model, decision)
        return decision

    def _apply_cooldown(self, slot_id: str, model: str, decision: RateLimitDecision) -> RateLimitDecision:
        with FileLock(self._root / "rotation.lock").hold(timeout_seconds=None):
            generation, cooldowns = self._read_rotation()
            now = self._clock.now()
            existing = cooldowns.get(slot_id, {}).get(model)
            if existing is not None and (until := datetime.fromisoformat(existing)) > now:
                return replace(decision, action=RateLimitAction.ROTATE_SLOT, wait_s=0, cooldown_until=until)
            if decision.action is RateLimitAction.ROTATE_SLOT:
                until = decision.cooldown_until
                if until is None or until <= now:
                    until = now + timedelta(seconds=60)
                cooldowns = {
                    slot: {
                        name: expiry
                        for name, expiry in models.items()
                        if datetime.fromisoformat(expiry) > now
                    }
                    for slot, models in cooldowns.items()
                }
                cooldowns.setdefault(slot_id, {})[model] = until.isoformat()
                record = json.dumps([generation + 1, cooldowns]).encode()
                atomic_write(self._root / "rotation.json", record, mode=0o600, private=True)
                return replace(decision, cooldown_until=until)
        return decision

    def release(self, lease: SlotLease) -> bool:
        """Release the current lease after in-flight use completes. Stale releases have no effect."""
        path = self._lease_path(lease)
        with FileLock(path.with_name("slot.lock")).hold(timeout_seconds=None):
            current = _read_lease(path)
            if current is None or current[0] != lease.lease_id:
                return False
            path.unlink()
            return True

    def _lease_path(self, lease: SlotLease) -> Path:
        slot = self._slots.get(lease.slot.slot_id)
        if slot is None or slot != lease.slot or lease.client_home != self._homes[slot.slot_id].session_home:
            raise ValueError("lease belongs to another provider pool")
        return validate_directory(self._directory(slot), owned_from=self._root) / "lease.json"

    @contextmanager
    def use(self, lease: SlotLease) -> Generator[Path]:
        """Lend the trusted provider client its private home while the lease is current."""
        path = self._lease_path(lease)
        if self._strict_isolated:
            self._check_isolation(lease.slot)
        with FileLock(path.with_name("slot.lock")).hold(timeout_seconds=None):
            current = _read_lease(path)
            if current is None or current[0] != lease.lease_id or current[1] <= self._clock.now():
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "provider slot lease is no longer active",
                    details={"reason": "provider_slot_lease_inactive"},
                )
            home = self._homes[lease.slot.slot_id]
            home.prepare(lease.slot.runtime_id, workdir=self._workdir)
            wallet_lock = home.wallet.resolve(strict=True) / ".credentials.lock"
            assert_safe_replace_target(wallet_lock)
            with FileLock(wallet_lock).hold(timeout_seconds=None):
                original = home.stage(lease.slot.runtime_id)
                try:
                    yield lease.client_home
                finally:
                    home.persist(lease.slot.runtime_id, original)

    def pin_session(self, lease: SlotLease, session_ref: str) -> SessionPin:
        """Record a provider session's slot while holding `use` for that lease."""
        if not session_ref:
            raise ValueError("a session pin needs a provider session reference")
        self._lease_path(lease)
        return SessionPin(lease.slot, lease.client_home, session_ref)

    def refresh[T](self, lease: SlotLease, refresh_credentials: Callable[[Path], T]) -> T:
        """Serialize a credential refresh with other refreshes and client use of this slot."""
        with self.use(lease) as client_home:
            return refresh_credentials(client_home)

    def run_tool(
        self,
        argv: Sequence[str],
        *,
        worktree: Path,
        tool_home: Path,
        timeout_seconds: float,
        writable_worktree: bool = False,
    ) -> ProcessResult:
        """Run a host-dispatched tool in a separate filesystem view without provider credentials."""
        if self._sandbox is None:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "host-dispatched tools require a credential-isolating sandbox",
                details={"credential_isolation": "unsupported"},
            )
        protected = (
            self._root,
            *(
                path
                for home in self._homes.values()
                for path in (home.wallet, home.session_home)
                if not path.is_relative_to(self._root)
            ),
        )
        for grant in (worktree.resolve(), tool_home.resolve()):
            if any(paths_overlap(grant, path) for path in protected):
                raise ValueError("tool filesystem grant overlaps the provider pool")
        command = self._sandbox.filesystem_argv(
            argv,
            worktree=worktree,
            step_tmp=tool_home,
            protected=protected,
            writable_worktree=writable_worktree,
        )
        return run(
            command,
            cwd=self._root.parent,
            env={"PATH": os.defpath, "HOME": str(tool_home)},
            timeout_seconds=timeout_seconds,
        )
