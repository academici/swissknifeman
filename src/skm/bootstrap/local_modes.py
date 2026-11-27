"""Compose host-local CLI operations without a control-plane client."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from skm.adapters.git.host_inputs import GitCheckoutReader
from skm.adapters.host_commands.local_gate import LocalUserSchemaValidator, SubprocessGateRunner
from skm.bootstrap.provider_accounts import load_provider_accounts
from skm.bootstrap.runtimes import RUNTIME_FACTORIES, runtime_environment
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.isolation import IsolationProfile
from skm.modules.context.host.pack_context import (
    DEFAULT_MAX_BYTES,
    PACK_MOUNT,
    PackContextRequest,
    PackContextResult,
    pack_context,
)
from skm.modules.context.ports import CheckoutReader
from skm.modules.execution.host.local_modes import (
    AskRequest,
    DeliberateRequest,
    DeliberateResult,
    DoRequest,
    LocalAnswer,
    local_deliberate,
    local_do,
)
from skm.modules.execution.host.local_modes import local_ask as _local_ask
from skm.modules.execution.ports import (
    GateCommandRunner,
    LocalRuntimePool,
    UserSchemaValidator,
)
from skm.modules.runtimes.domain.request import CommandRules, NetworkRules, PathRule, PathRules, ResultFormat
from skm.modules.runtimes.public import (
    AgentRequest,
    Capability,
    PermissionGrant,
    ProcessOwner,
    RoleId,
    RuntimeLimits,
)
from skm.platform.schema.user_schema import load_user_json_schema

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from skm.adapters.runtimes.pool import ProviderSlot, SlotLease
    from skm.modules.runtimes.public import AgentRuntime, RuntimeResult
    from skm.platform.logging.redaction import Redactor

__all__ = [
    "DEFAULT_MAX_BYTES",
    "AskRequest",
    "DeliberateRequest",
    "DeliberateResult",
    "DoRequest",
    "LocalAnswer",
    "LocalModeOptions",
    "PackContextRequest",
    "local_ask",
    "local_deliberate",
    "local_do",
    "pack_local_context",
    "runtime_gateways",
]

_CREDENTIAL_COPY_OPTIONS = frozenset({"codex", "claude_code"})
_PROXY_RUNTIMES = frozenset({"codex", "claude_code", "gemini_cli", "antigravity"})
_LIMITS = RuntimeLimits(600, 120, None, None, 2 * 1024 * 1024)


@dataclass(frozen=True, slots=True)
class LocalModeOptions:
    cwd: Path
    registry: Path | None
    model: str | None


@dataclass(frozen=True, slots=True)
class _ProviderSession:
    slot_id: str
    runtime: AgentRuntime
    state: Path
    cwd: Path
    client_home: Path
    model: str
    proxy: bool

    @property
    def config_mode(self) -> Literal["isolated"]:
        return "isolated"

    @property
    def supports_resume(self) -> bool:
        return self.runtime.capabilities().supports(Capability.SESSION_RESUME)

    def run(
        self,
        prompt: str,
        *,
        read_only: bool,
        session_policy: Literal["ephemeral", "persistent"] = "ephemeral",
        resume_session_ref: str | None = None,
    ) -> RuntimeResult:
        step_id = uuid4()
        owner = ProcessOwner(
            uuid4(), uuid4(), uuid4(), uuid4(), "step", step_id, token_hex(24), str(self.state / "identities")
        )
        paths = PathRules((PathRule(str(self.cwd), "**"),), ())
        request = AgentRequest(
            request_id=str(step_id),
            runtime_id=self.runtime.runtime_id,
            model=self.model,
            effort=None,
            role=RoleId.EXECUTOR,
            rendered_prompt=prompt,
            prompt_digest=f"sha256:{sha256(prompt.encode()).hexdigest()}",
            result_format=ResultFormat.TEXT,
            result_schema_urn=None,
            workdir=str(self.cwd),
            permissions=PermissionGrant(
                paths,
                PathRules((), ()) if read_only else paths,
                CommandRules("none", (), (), ()),
                NetworkRules("any" if self.proxy else "none", ()),
                frozenset(),
                frozenset(),
            ),
            isolation_profile=IsolationProfile.LANDLOCK,
            process_owner=owner,
            config_mode=self.config_mode,
            client_home=str(self.client_home),
            resume_session_ref=resume_session_ref,
            session_policy=session_policy,
            env_allowlist=(),
            extra_env={},
            secret_env={},
            mcp_servers=(),
            limits=_LIMITS,
            labels={},
        )
        handle = self.runtime.start(request)
        try:
            for _ in self.runtime.events(handle):
                pass
            return self.runtime.result(handle)
        except BaseException:
            self.runtime.cancel(handle, grace_seconds=5)
            raise


class _ProviderRuntimePool:
    def __init__(
        self, options: LocalModeOptions, environ: Mapping[str, str], home: Path, redactor: Redactor
    ) -> None:
        self._accounts = load_provider_accounts(options.registry, environ, home)
        self._pool = self._accounts.pool(workdir=options.cwd)
        self._cwd = options.cwd
        self._model = options.model
        self._env = runtime_environment(environ, redactor)

    def _choose_model(self, slot: ProviderSlot) -> str | None:
        if self._model is not None:
            return self._model if not slot.models or any(m.name == self._model for m in slot.models) else None
        return next((model.name for model in slot.models if not model.is_compat), None)

    def _acquire(self, slot_id: str | None) -> tuple[SlotLease, str]:
        candidates = (
            (self._accounts.get_slot(slot_id),)
            if slot_id is not None
            else sorted(self._accounts.slots, key=lambda slot: (slot.tier, slot.slot_id))
        )
        for slot in candidates:
            if slot.transport != "cli_subprocess" or slot.runtime_id not in RUNTIME_FACTORIES:
                continue
            model = self._choose_model(slot)
            if model is None:
                continue
            lease = self._pool.acquire_ranked((slot,), str(uuid4()), ttl_seconds=60, model=model)
            if lease is not None:
                return lease, model
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "no available CLI provider slot for the model. Select a configured slot and model",
        )

    @contextmanager
    def open(self, slot_id: str | None) -> Generator[LocalRuntimePool.Session[RuntimeResult]]:
        lease, model = self._acquire(slot_id)
        slot = lease.slot
        try:
            config = self._accounts.config_for(slot.slot_id)
            if config.proxy is not None and slot.runtime_id not in _PROXY_RUNTIMES:
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE, "runtime cannot use the slot proxy"
                )
            with (
                self._pool.use(lease) as home,
                TemporaryDirectory(prefix="local-mode-", dir=self._accounts.pool_root) as directory,
            ):
                state = Path(directory)
                options: dict[str, object] = {"environ": self._env}
                if slot.runtime_id != "cursor":
                    options["state_dir"] = state
                if slot.runtime_id in _CREDENTIAL_COPY_OPTIONS:
                    options["copy_credentials"] = False
                if config.proxy is not None:
                    options["egress_proxy"] = config.proxy
                if slot.runtime_id == "grok":
                    options["account_home"] = home
                runtime = RUNTIME_FACTORIES[slot.runtime_id](**options)
                yield _ProviderSession(
                    slot.slot_id, runtime, state, self._cwd, home, model, config.proxy is not None
                )
        finally:
            self._pool.release(lease)


def _checkout(cwd: Path) -> Path:
    try:
        root = cwd.resolve(strict=True)
        if root.is_dir():
            return root
    except (OSError, ValueError, RuntimeError):
        pass
    raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "checkout root is not an accessible directory")


def runtime_gateways(
    options: LocalModeOptions, environ: Mapping[str, str], home: Path, redactor: Redactor
) -> GatewayTable:
    options = LocalModeOptions(_checkout(options.cwd), options.registry, options.model)
    return GatewayTable(
        {
            LocalRuntimePool: _ProviderRuntimePool(options, environ, home, redactor),
            UserSchemaValidator: LocalUserSchemaValidator(),
            GateCommandRunner: SubprocessGateRunner(environ),
        },
        "host_gateway",
    )


def pack_local_context(root: Path, request: PackContextRequest) -> PackContextResult:
    reader = GitCheckoutReader({PACK_MOUNT: _checkout(root)})
    return pack_context(GatewayTable({CheckoutReader: reader}, "host_gateway"), request)


def local_ask(gateways: GatewayTable, request: AskRequest) -> LocalAnswer:
    if request.schema is not None:
        try:
            schema = load_user_json_schema(request.schema)
        except ValueError as error:
            return LocalAnswer(request.slot, error=str(error))
        except RecursionError:
            return LocalAnswer(request.slot, error="user JSON Schema is too deeply nested")
        request = replace(request, schema_json=json.dumps(schema, ensure_ascii=True))
    return _local_ask(gateways, request)
