"""Compose host-local account inspection and read-only quota probes from the operator's registry."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.parse import urlsplit

from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.adapters.runtimes.pool import ProviderSlot
from skm.adapters.runtimes.pool.quota_prober import QuotaGroup, QuotaProber, QuotaReading, QuotaReply
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed

__all__ = ["ProviderAccounts", "load_provider_accounts"]


@dataclass(frozen=True, slots=True)
class ProviderAccounts:
    slots: tuple[ProviderSlot, ...]
    prober: QuotaProber | None

    def probe(self) -> tuple[QuotaReading, ...]:
        if self.prober is None:
            return ()
        return tuple(reading for slot in self.slots for reading in self.prober.probe(slot))


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


def load_provider_accounts(path: Path | None, environ: Mapping[str, str], home: Path) -> ProviderAccounts:
    """Use the explicit registry or the host's XDG skm/provider-pool.toml."""
    registry = path or Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "skm/provider-pool.toml"
    try:
        with registry.open("rb") as source:
            document = tomllib.load(source)
    except FileNotFoundError:
        if path is None:
            return ProviderAccounts((), None)
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "provider pool registry does not exist") from None
    except (OSError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "cannot read provider pool registry") from exc
    try:
        groups: list[QuotaGroup] = []
        group_models = _table(document.get("groups"))
        for name, model in group_models.items():
            if not isinstance(model, str):
                raise ValueError("expected a model selector")
            groups.append(QuotaGroup(name, model))
        slots: list[ProviderSlot] = []
        endpoints: dict[tuple[ProviderSlot, str], str] = {}
        for slot_id, entry in sorted(_table(document.get("slots", {})).items()):
            config = _table(entry)
            runtime = config.get("runtime_id")
            if not isinstance(runtime, str):
                raise ValueError("missing runtime ID")
            slot = ProviderSlot(runtime, slot_id)
            slots.append(slot)
            for group, url in _table(config.get("quota_urls", {})).items():
                if group not in group_models or not isinstance(url, str):
                    raise ValueError("invalid quota URL mapping")
                parts = urlsplit(url)
                if (
                    parts.scheme != "https"
                    or not parts.hostname
                    or parts.username is not None
                    or parts.fragment
                ):
                    raise ValueError("expected a quota HTTPS URL without userinfo or fragment")
                endpoints[slot, group] = url

        fetcher = HttpUpstreamFetcher()

        def fetch(slot: ProviderSlot, group: QuotaGroup) -> QuotaReply | None:
            url = endpoints.get((slot, group.group_id))
            return None if url is None else _get_quota(fetcher, url)

        prober = QuotaProber(groups, fetch)
    except ValueError as exc:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "invalid provider pool registry") from exc
    return ProviderAccounts(tuple(slots), prober)
