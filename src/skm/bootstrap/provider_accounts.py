"""Compose host-local account management and quota probes from the operator's registry."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from http.client import HTTPException
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import BaseHandler, ProxyHandler, Request

from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.adapters.runtimes import LocalProxyBridge, ProxyEndpoint, apply_proxy_env
from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.adapters.runtimes.pool.provider_pool import SlotModel, SlotRuntimeConfig, Transport
from skm.adapters.runtimes.pool.quota_prober import QuotaGroup, QuotaProber, QuotaReading, QuotaReply
from skm.adapters.runtimes.pool.shallow_home import validate_host_links
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, NotFound, ValidationFailed
from skm.platform.config.secrets import SecretRef
from skm.platform.process.argv_rules import check_argv
from skm.platform.process.environment import build_env

__all__ = ["ProviderAccounts", "execute_account", "load_provider_accounts"]

_COMMON = frozenset({"runtime_id", "transport", "tier", "egress_proxy", "models", "quota_urls"})
_TRANSPORT_FIELDS = {
    "cli_subprocess": {"wallet_path", "shallow_home", "symlink_host_files", "write_back", "worker_mode"},
    "http_api": {"provider", "base_url", "api_key_ref", "provider_routing"},
    "oauth_gateway": {"provider", "base_url", "token_file", "write_back"},
}


@dataclass(frozen=True, slots=True)
class ProviderAccounts:
    slots: tuple[ProviderSlot, ...]
    prober: QuotaProber | None
    _configs: Mapping[str, SlotRuntimeConfig] = field(
        default_factory=dict[str, SlotRuntimeConfig], repr=False
    )
    schema_version: int = 1
    pool_root: Path | None = None
    host_home: Path | None = None

    def probe(self) -> tuple[QuotaReading, ...]:
        if self.prober is None:
            return ()
        return tuple(reading for slot in self.slots for reading in self.prober.probe(slot))

    def get_slot(self, slot_id: str) -> ProviderSlot:
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        raise NotFound(ErrorCode.NOT_FOUND, "provider account slot does not exist")

    def config_for(self, slot_id: str) -> SlotRuntimeConfig:
        self.get_slot(slot_id)
        return self._configs.get(slot_id, SlotRuntimeConfig())

    def pool(self, *, workdir: Path | None = None, initialize: bool = True) -> ProviderPoolManager:
        if self.pool_root is None:
            raise ValueError("provider accounts have no pool root")
        return ProviderPoolManager(
            self.pool_root,
            self.slots,
            configs=self._configs,
            host_home=self.host_home,
            workdir=Path.cwd() if workdir is None else workdir,
            initialize=initialize,
        )


class _QuotaProxy(BaseHandler):
    """Force the quota request through its bridge, including redirects and hosts in ambient NO_PROXY."""

    def __init__(self, proxy_url: str) -> None:
        self._authority = urlsplit(proxy_url).netloc

    def https_request(self, request: Request) -> Request:
        request.set_proxy(self._authority, "http")
        return request


def _get_quota(fetcher: HttpUpstreamFetcher, url: str) -> QuotaReply | None:
    """Read a counter from a bounded HTTPS response. A remote payload cannot attest to execution."""
    try:
        payload: object = json.loads(fetcher.fetch(url, max_bytes=8192, timeout_seconds=5))
    except BackendUnavailable as exc:
        status = exc.details.get("status")
        if isinstance(exc.__cause__, HTTPError):
            status = exc.__cause__.code
        return QuotaReply(status) if type(status) is int else None
    except (HTTPException, ValueError, RecursionError):
        return None
    match payload:
        case {"remaining": int(remaining)} if type(remaining) is int:
            return QuotaReply(200, remaining)
        case _:
            return None


def _table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected a TOML table")
    return cast("dict[str, object]", value)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError("expected a non-empty string")
    return value


def _url(value: object) -> str:
    url = _string(value)
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or "#" in url
        or any(char.isspace() for char in url)
        or "\\" in parts.netloc
        or parts.port == 0
    ):
        raise ValueError("expected an HTTPS URL without userinfo or fragment")
    return url


def _path(config: Mapping[str, object], key: str, home: Path) -> Path | None:
    if key not in config:
        return None
    raw = _string(config[key])
    path = home / raw[2:] if raw.startswith("~/") else Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("expected absolute provider path or ~/")
    return path


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ValueError("expected a boolean")
    return value


def _models(value: object) -> tuple[SlotModel, ...]:
    if not isinstance(value, list):
        raise ValueError("expected a list of slot models")
    models: list[SlotModel] = []
    for item in cast("list[object]", value):
        entry = _table(item)
        if set(entry) != {"name", "is_compat"}:
            raise ValueError("invalid slot model")
        models.append(SlotModel(_string(entry["name"]), _boolean(entry["is_compat"])))
    if len({model.name for model in models}) != len(models):
        raise ValueError("duplicate slot model")
    return tuple(models)


def _cli_config(config: Mapping[str, object], home: Path, proxy: ProxyEndpoint | None) -> SlotRuntimeConfig:
    links = config.get("symlink_host_files", [])
    if not isinstance(links, list):
        raise ValueError("expected a list of shallow home links")
    names = tuple(map(_string, cast("list[object]", links)))
    validate_host_links(names)
    mode = config.get("worker_mode", "ephemeral")
    if mode not in ("ephemeral", "hot_pool"):
        raise ValueError("invalid provider worker mode")
    return SlotRuntimeConfig(
        proxy=proxy,
        wallet_path=_path(config, "wallet_path", home),
        shallow_home=_path(config, "shallow_home", home),
        symlink_host_files=names,
        write_back=_boolean(config.get("write_back", True)),
        worker_mode=mode,
    )


def _parse_slot(
    slot_id: str, config: dict[str, object], version: int, home: Path
) -> tuple[ProviderSlot, SlotRuntimeConfig]:
    runtime = _string(config.get("runtime_id"))
    if version == 1:
        if config.keys() - {"runtime_id", "quota_urls"}:
            raise ValueError("unexpected v1 slot configuration")
        return ProviderSlot(runtime, slot_id), SlotRuntimeConfig()

    transport = _string(config.get("transport"))
    if transport not in _TRANSPORT_FIELDS or config.keys() - (_COMMON | _TRANSPORT_FIELDS[transport]):
        raise ValueError("invalid provider slot transport or fields")
    tier = config.get("tier", 1)
    if type(tier) is not int or tier < 1:
        raise ValueError("invalid provider slot tier")
    proxy = ProxyEndpoint.parse(_string(config.get("egress_proxy", "direct")))
    slot = ProviderSlot(
        runtime,
        slot_id,
        tier=tier,
        transport=cast("Transport", transport),
        models=_models(config.get("models", [])),
        has_egress_proxy=proxy is not None,
        proxy_scheme=proxy.scheme if proxy is not None else None,
    )
    if transport == "cli_subprocess":
        return slot, _cli_config(config, home, proxy)

    provider = _string(config.get("provider"))
    base_url = _url(config.get("base_url"))
    if transport == "oauth_gateway":
        token_file = _path(config, "token_file", home)
        if token_file is None:
            raise ValueError("OAuth slot requires a token file")
        return slot, SlotRuntimeConfig(
            proxy=proxy,
            provider=provider,
            base_url=base_url,
            token_file=token_file,
            write_back=_boolean(config.get("write_back", True)),
        )
    api_key_ref = SecretRef.parse(_string(config.get("api_key_ref")))
    routing = _table(config.get("provider_routing", {}))
    if routing.keys() - {"allow_fallbacks", "zdr"}:
        raise ValueError("invalid downstream provider routing")
    return slot, SlotRuntimeConfig(
        proxy=proxy,
        provider=provider,
        base_url=base_url,
        api_key_ref=api_key_ref,
        provider_routing={key: _boolean(value) for key, value in routing.items()},
    )


def _quota_prober(
    group_models: Mapping[str, object],
    endpoints: Mapping[tuple[str, str], str],
    configs: Mapping[str, SlotRuntimeConfig],
    version: int,
) -> QuotaProber | None:
    groups: list[QuotaGroup] = []
    for name, model in group_models.items():
        if not isinstance(model, str):
            raise ValueError("expected a quota model selector")
        groups.append(QuotaGroup(name, model))
    if version == 2 and not endpoints:
        return None
    # The legacy registry had six fixed groups. V2 permits the groups configured for its slots.
    fetcher = HttpUpstreamFetcher() if version == 1 else HttpUpstreamFetcher(handlers=(ProxyHandler({}),))

    def fetch(slot: ProviderSlot, group: QuotaGroup) -> QuotaReply | None:
        url = endpoints.get((slot.slot_id, group.group_id))
        if url is None:
            return None
        endpoint = configs[slot.slot_id].proxy
        if endpoint is None:
            return _get_quota(fetcher, url)
        try:
            with LocalProxyBridge(endpoint) as bridge:
                url_for_bridge = bridge.url
                if url_for_bridge is None:
                    return None
                proxied = HttpUpstreamFetcher(handlers=(ProxyHandler({}), _QuotaProxy(url_for_bridge)))
                return _get_quota(proxied, url)
        except OSError:
            return None

    return QuotaProber(groups, fetch, required_groups=6 if version == 1 else None)


def load_provider_accounts(path: Path | None, environ: Mapping[str, str], home: Path) -> ProviderAccounts:
    """Read either registry version and keep all credential-bearing configuration host-local."""
    registry = path or Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "skm/provider-pool.toml"
    root = Path(environ.get("XDG_STATE_HOME") or home / ".local/state") / "skm/provider-pool"
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(registry, flags), "rb") as source:
            facts = os.fstat(source.fileno())
            if not stat.S_ISREG(facts.st_mode):
                raise ValueError("registry is not a regular file")
            document = tomllib.load(source)
    except FileNotFoundError:
        if path is None:
            return ProviderAccounts((), None, pool_root=root, host_home=home)
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "provider pool registry does not exist") from None
    except (OSError, ValueError, RecursionError):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "cannot read provider pool registry") from None
    try:
        version = document.get("schema_version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported provider pool registry version")
        group_models = _table(document.get("groups", {} if version == 2 else None))
        slots: list[ProviderSlot] = []
        configs: dict[str, SlotRuntimeConfig] = {}
        endpoints: dict[tuple[str, str], str] = {}
        for slot_id, entry in sorted(_table(document.get("slots", {})).items()):
            config = _table(entry)
            slot, private = _parse_slot(slot_id, config, version, home)
            if (
                private.proxy is not None
                and private.proxy.username is not None
                and (facts.st_uid != os.geteuid() or stat.S_IMODE(facts.st_mode) != 0o600)
            ):
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    "provider registry with proxy credentials requires owner-only mode 0600",
                )
            slots.append(slot)
            configs[slot_id] = private
            for group, url in _table(config.get("quota_urls", {})).items():
                if group not in group_models:
                    raise ValueError("invalid quota group")
                endpoints[slot_id, group] = _url(url)
        prober = _quota_prober(group_models, endpoints, configs, version)
    except ValueError:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "invalid provider pool registry") from None
    return ProviderAccounts(tuple(slots), prober, configs, version, root, home)


def execute_account(
    accounts: ProviderAccounts, slot_id: str, cwd: Path, argv: Sequence[str], environ: Mapping[str, str]
) -> int:
    """Run a trusted host command with the selected account lease, home and egress."""
    slot = accounts.get_slot(slot_id)
    if slot.transport != "cli_subprocess":
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "account exec requires a CLI slot")
    if not cwd.is_dir():
        raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "account exec workdir does not exist")
    try:
        command = check_argv(argv)
    except ValueError:
        raise ValidationFailed(ErrorCode.RUNTIME_INVALID_REQUEST, "invalid account exec command") from None
    pool = accounts.pool(workdir=cwd)
    lease = pool.acquire(slot_id, "accounts-exec", ttl_seconds=60)
    if lease is None:
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "provider account slot is busy")
    try:
        with pool.use(lease) as home:
            env = build_env(
                environ, allow=("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"), home=home
            )
            env.update(
                TMPDIR=str(home / "tmp"),
                XDG_CONFIG_HOME=str(home / ".config"),
                XDG_CACHE_HOME=str(home / ".cache"),
                XDG_DATA_HOME=str(home / ".local/share"),
                XDG_STATE_HOME=str(home / ".local/state"),
            )
            if slot.runtime_id == "claude_code":
                env["CLAUDE_CONFIG_DIR"] = str(home)
            if slot.runtime_id == "codex":
                env["CODEX_HOME"] = str(home)
            if slot.runtime_id == "gemini_cli":
                env.update(GEMINI_CLI_HOME=str(home), GEMINI_TELEMETRY_ENABLED="false")
                if key := environ.get("GEMINI_API_KEY"):
                    env["GEMINI_API_KEY"] = key
            proxy = accounts.config_for(slot_id).proxy
            if proxy is None:
                return _run_account(command, cwd, env)
            try:
                with LocalProxyBridge(proxy) as bridge:
                    apply_proxy_env(env, bridge)
                    return _run_account(command, cwd, env)
            except OSError:
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE, "egress bridge unavailable"
                ) from None
    finally:
        pool.release(lease)


def _run_account(command: tuple[str, ...], cwd: Path, env: Mapping[str, str]) -> int:
    try:
        # This operator command inherits the terminal's streams and foreground process group.
        with subprocess.Popen(command, cwd=cwd, env=env) as process:  # noqa: TID251
            try:
                status = process.wait()
            except BaseException:
                process.kill()
                process.wait()
                raise
    except OSError:
        raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "could not run account command") from None
    return status if status >= 0 else 128 - status
