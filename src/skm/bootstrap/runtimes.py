"""Built-in runtime adapter factories."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from skm.adapters.runtimes.antigravity.runtime import AntigravityRuntime
from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.adapters.runtimes.cursor.runtime import CursorRuntime
from skm.adapters.runtimes.gemini_cli.runtime import GeminiCliRuntime
from skm.adapters.runtimes.grok.runtime import GrokRuntime
from skm.adapters.runtimes.pool import ProviderPoolManager
from skm.adapters.sandbox.bubblewrap import BubblewrapSandbox
from skm.bootstrap.provider_accounts import load_provider_accounts
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.runtimes.ports import AgentRuntime
from skm.modules.runtimes.public import Effort
from skm.modules.settings.public import worker_identifiers
from skm.platform.config.secrets import SecretRef
from skm.platform.logging.redaction import Redactor
from skm.platform.process.environment import BASE_ALLOW

if TYPE_CHECKING:
    from collections.abc import Iterable

    from skm.adapters.runtimes.pool import ProviderSlot
    from skm.platform.machine import MachineStore

__all__ = [
    "MACHINE_SETTING_KEYS",
    "RUNTIME_FACTORIES",
    "WorkerRuntimeSettings",
    "build_provider_pool",
    "runtime_environment",
]

_RUNTIME_WORKER_OPTIONS = (
    "runtimes.binaries",
    "runtimes.credentials.copy",
    "runtimes.codex.allow_full_access",
    "runtimes.claude_code.allow_skip_permissions",
)
_GROK_ACCOUNT_HOME = "runtimes.grok.account_home"
MACHINE_SETTING_KEYS = (
    *_RUNTIME_WORKER_OPTIONS,
    "plugins.allowed",
    "runtimes.allowed",
    "runtimes.accounts",
    _GROK_ACCOUNT_HOME,
    "runtimes.models.allowed",
)
_ACCOUNT_ENV = {
    runtime.runtime_id: frozenset(runtime.sensitive_env_names)
    for runtime in (AntigravityRuntime, ClaudeCodeRuntime, CodexRuntime, GeminiCliRuntime)
}
_PROVIDER_ENV = frozenset[str]().union(*_ACCOUNT_ENV.values())
_WORKER_ENV = frozenset((*BASE_ALLOW, "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"))


def _invalid_worker_setting(key: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.CONFIG_INVALID, "Invalid machine worker setting", details={"key": key})


def _operator_map(value: JsonValue, key: str) -> JsonObject:
    if isinstance(value, dict):
        return value
    raise _invalid_worker_setting(key)


@dataclass(frozen=True, slots=True)
class WorkerRuntimeSettings:
    """Machine operator's runtime policy for a single worker host."""

    allowed: frozenset[str] = frozenset()
    plugins: tuple[str, ...] = ()
    options: JsonObject = field(default_factory=dict[str, JsonValue], repr=False)
    accounts: Mapping[str, Mapping[str, SecretRef]] = field(
        default_factory=dict[str, Mapping[str, SecretRef]], repr=False
    )
    models: Mapping[str, Mapping[str, frozenset[str]]] = field(
        default_factory=dict[str, Mapping[str, frozenset[str]]]
    )
    grok_account_home: Path | None = field(default=None, repr=False)

    @classmethod
    def read(cls, store: MachineStore) -> WorkerRuntimeSettings:
        installation = store.get_installation_id()
        if installation is None:
            raise _invalid_worker_setting("installation_id")

        def get(key: str) -> JsonValue:
            return store.get_operator_setting(installation, key)

        options: JsonObject = {
            key: value for key in _RUNTIME_WORKER_OPTIONS if (value := get(key)) is not None
        }
        cls._validate_options(options)
        allowed, plugins = get("runtimes.allowed"), get("plugins.allowed")
        if allowed is None:
            allowed = list[JsonValue](
                _operator_map(options.get("runtimes.binaries", {}), "runtimes.binaries")
            )
        return cls(
            allowed=frozenset(worker_identifiers(allowed, key="runtimes.allowed")),
            plugins=worker_identifiers(plugins if plugins is not None else [], key="plugins.allowed"),
            options=options,
            accounts=cls._read_accounts(get("runtimes.accounts")),
            models=cls._read_models(get("runtimes.models.allowed")),
            grok_account_home=cls._read_grok_account_home(get(_GROK_ACCOUNT_HOME)),
        )

    @classmethod
    def validate_setting(cls, key: str, value: JsonValue) -> None:
        """Validate a machine-owned key at the operator write boundary."""
        if key in _RUNTIME_WORKER_OPTIONS:
            cls._validate_options({key: value})
        elif key in {"runtimes.allowed", "plugins.allowed"}:
            worker_identifiers(value, key=key)
        elif key == "runtimes.accounts":
            cls._read_accounts(value)
        elif key == "runtimes.models.allowed":
            cls._read_models(value)
        elif key == _GROK_ACCOUNT_HOME:
            cls._read_grok_account_home(value)
        else:
            raise _invalid_worker_setting(key)

    @staticmethod
    def _validate_options(options: JsonObject) -> None:
        for key, value in options.items():
            if key == "runtimes.binaries":
                files = _operator_map(value, key)
                worker_identifiers(list(files), key="runtimes.allowed")
                if any(
                    not isinstance(binary, str) or not binary or "\0" in binary for binary in files.values()
                ):
                    raise _invalid_worker_setting(key)
            elif key == "runtimes.credentials.copy":
                flags = _operator_map(value, key)
                worker_identifiers(list(flags), key="runtimes.allowed")
                if any(type(copy) is not bool for copy in flags.values()):
                    raise _invalid_worker_setting(key)
            elif type(value) is not bool:
                raise _invalid_worker_setting(key)

    @staticmethod
    def _read_accounts(value: JsonValue) -> dict[str, dict[str, SecretRef]]:
        key = "runtimes.accounts"
        accounts: dict[str, dict[str, SecretRef]] = {}
        for runtime_id, raw in _operator_map(value if value is not None else {}, key).items():
            worker_identifiers([runtime_id], key="runtimes.allowed")
            refs: dict[str, SecretRef] = {}
            allowed = _ACCOUNT_ENV.get(runtime_id, frozenset[str]())
            for name, ref in _operator_map(raw, key).items():
                if name not in allowed or not isinstance(ref, str):
                    raise _invalid_worker_setting(key)
                try:
                    reference = SecretRef.parse(ref)
                except ValidationFailed:
                    raise _invalid_worker_setting(key) from None
                if reference.scheme == "env" and (
                    reference.path.startswith("SKM_") or reference.path in (_PROVIDER_ENV - allowed)
                ):
                    raise _invalid_worker_setting(key)
                refs[name] = reference
            accounts[runtime_id] = refs
        return accounts

    @staticmethod
    def _read_grok_account_home(value: JsonValue) -> Path | None:
        if value is None:
            return None
        if isinstance(value, str) and "\0" not in value:
            path = Path(value)
            if path.is_absolute() and path != Path(path.anchor) and ".." not in path.parts:
                return path
        raise _invalid_worker_setting(_GROK_ACCOUNT_HOME)

    @staticmethod
    def _read_models(value: JsonValue) -> dict[str, dict[str, frozenset[str]]]:
        if value is None:
            return {}
        key = "runtimes.models.allowed"
        valid_efforts = {effort.value for effort in Effort} | {"default"}
        models: dict[str, dict[str, frozenset[str]]] = {}
        for runtime_id, raw in _operator_map(value, key).items():
            worker_identifiers([runtime_id], key="runtimes.allowed")
            allowed: dict[str, frozenset[str]] = {}
            for model, efforts in _operator_map(raw, key).items():
                if (
                    not model
                    or not isinstance(efforts, list)
                    or any(not isinstance(effort, str) or effort not in valid_efforts for effort in efforts)
                ):
                    raise _invalid_worker_setting(key)
                allowed[model] = frozenset(cast("list[str]", efforts))
            models[runtime_id] = allowed
        return models

    def allows_model(self, runtime_id: str, model: str, effort: Effort | None) -> bool:
        if runtime_id not in self.allowed:
            return False
        return (effort or "default") in self.models.get(runtime_id, {}).get(model, ())

    def get(self, key: str) -> JsonValue:
        if key == "runtimes.allowed":
            return list[JsonValue](sorted(self.allowed))
        if key == "plugins.allowed":
            return list[JsonValue](self.plugins)
        if key in ("runtimes.codex", "runtimes.claude_code"):
            return {
                name.removeprefix(key + "."): value
                for name, value in self.options.items()
                if name.startswith(key + ".")
            }
        if key == "runtimes.credentials.copy":
            copies = cast("JsonObject", self.options.get(key, {}))
            return {"codex": False, "claude_code": False, **copies}
        return self.options.get(key)


def runtime_environment(environ: Mapping[str, str], redactor: Redactor) -> dict[str, str]:
    """Collect only the worker runtime's local process and TLS inputs."""
    return {
        name: value
        for name, value in environ.items()
        if (name in _WORKER_ENV or name.startswith("LC_")) and redactor.text(value) == value
    }


def build_provider_pool(
    root: Path, slots: Iterable[ProviderSlot] | None = None, *, strict_isolated: bool = False
) -> ProviderPoolManager:
    """Compose the pool with the host's separate mount namespace for tool dispatch."""
    if slots is None:
        slots = load_provider_accounts(None, os.environ, Path.home()).slots
    return ProviderPoolManager(root, slots, strict_isolated=strict_isolated, tool_sandbox=BubblewrapSandbox())


def _extract_config_mapping(config: object, key: str) -> Mapping[str, object]:
    getter = getattr(config, "get", None)
    value: object = None
    if callable(getter):
        value = getter(key)
    elif isinstance(config, Mapping):
        value = cast("Mapping[str, object]", config).get(key)
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


def _build_claude_code_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    if ctx is not None:
        config = getattr(ctx, "config", None)
        if config is not None:
            binaries = _extract_config_mapping(config, "runtimes.binaries")
            raw_bin = binaries.get("claude_code")
            if "binary" not in options and isinstance(raw_bin, str) and raw_bin:
                options["binary"] = raw_bin

            creds = _extract_config_mapping(config, "runtimes.credentials.copy")
            raw_copy = creds.get("claude_code")
            if "copy_credentials" not in options and isinstance(raw_copy, bool):
                options["copy_credentials"] = raw_copy

            claude_cfg = _extract_config_mapping(config, "runtimes.claude_code")
            raw_skip = claude_cfg.get("allow_skip_permissions")
            if "allow_skip_permissions" not in options and isinstance(raw_skip, bool):
                options["allow_skip_permissions"] = raw_skip

    if "environ" not in options:
        options["environ"] = dict(os.environ)
    return ClaudeCodeRuntime(**options)


def _build_codex_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    if ctx is not None:
        config = getattr(ctx, "config", None)
        if config is not None:
            binaries = _extract_config_mapping(config, "runtimes.binaries")
            raw_bin = binaries.get("codex")
            if "binary" not in options and isinstance(raw_bin, str) and raw_bin:
                options["binary"] = raw_bin

            creds = _extract_config_mapping(config, "runtimes.credentials.copy")
            raw_copy = creds.get("codex")
            if "copy_credentials" not in options and isinstance(raw_copy, bool):
                options["copy_credentials"] = raw_copy

            codex_cfg = _extract_config_mapping(config, "runtimes.codex")
            raw_full = codex_cfg.get("allow_full_access")
            if "allow_full_access" not in options and isinstance(raw_full, bool):
                options["allow_full_access"] = raw_full

    if "environ" not in options:
        options["environ"] = dict(os.environ)
    return CodexRuntime(**options)


def _build_grok_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    if ctx is not None:
        config = getattr(ctx, "config", None)
        if config is not None:
            binaries = _extract_config_mapping(config, "runtimes.binaries")
            raw_bin = binaries.get("grok")
            if "binary" not in options and isinstance(raw_bin, str) and raw_bin:
                options["binary"] = raw_bin

    if "environ" not in options:
        options["environ"] = dict(os.environ)
    return GrokRuntime(**options)


def _build_cursor_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    if ctx is not None:
        config = getattr(ctx, "config", None)
        if config is not None:
            binaries = _extract_config_mapping(config, "runtimes.binaries")
            raw_bin = binaries.get("cursor") or binaries.get("cursor-agent")
            if "binary" not in options and isinstance(raw_bin, str) and raw_bin:
                options["binary"] = raw_bin

    if "environ" not in options:
        options["environ"] = dict(os.environ)
    return CursorRuntime(**options)


def _build_antigravity_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    binaries = _extract_config_mapping(getattr(ctx, "config", None), "runtimes.binaries")
    binary = binaries.get("antigravity")
    if isinstance(binary, str) and binary:
        options.setdefault("binary", binary)
    options.setdefault("environ", dict(os.environ))
    return AntigravityRuntime(**options)


def _build_gemini_cli_runtime(ctx: object = None, /, **kwargs: Any) -> AgentRuntime:
    options = dict(kwargs)
    binaries = _extract_config_mapping(getattr(ctx, "config", None), "runtimes.binaries")
    binary = binaries.get("gemini_cli")
    if isinstance(binary, str) and binary:
        options.setdefault("binary", binary)
    options.setdefault("environ", dict(os.environ))
    return GeminiCliRuntime(**options)


RUNTIME_FACTORIES: Mapping[str, Callable[..., AgentRuntime]] = MappingProxyType(
    {
        "antigravity": _build_antigravity_runtime,
        "claude_code": _build_claude_code_runtime,
        "claude-code": _build_claude_code_runtime,
        "codex": _build_codex_runtime,
        "codex-cli": _build_codex_runtime,
        "cursor": _build_cursor_runtime,
        "cursor-agent": _build_cursor_runtime,
        "gemini_cli": _build_gemini_cli_runtime,
        "grok": _build_grok_runtime,
    }
)
