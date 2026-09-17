"""Load provider skill-distribution channels from the monorepo SSOT catalog."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from .values import ProviderId


@dataclass(frozen=True)
class ConnectChannelSpec:
    mode: str
    target: str = ""
    marketplace: str = ""
    bundle: bool = False


@dataclass(frozen=True)
class VendorChannelSpec:
    path_param: str


@dataclass(frozen=True)
class DiscoverySpec:
    surface: str
    decision: str = ""
    note: str = ""


@dataclass(frozen=True)
class ProviderDistributionSpec:
    connect: ConnectChannelSpec | None = None
    vendor: VendorChannelSpec | None = None
    discovery: DiscoverySpec | None = None


@dataclass(frozen=True)
class DistributionCatalog:
    providers: Mapping[str, ProviderDistributionSpec]


def _parse_provider(raw: object) -> ProviderDistributionSpec:
    if not isinstance(raw, dict):
        raise ValueError("PDIST_PROVIDER_INVALID")
    connect = vendor = discovery = None
    if "connect" in raw:
        value = raw["connect"]
        if not isinstance(value, dict) or not isinstance(value.get("mode"), str):
            raise ValueError("PDIST_CONNECT_INVALID")
        connect = ConnectChannelSpec(
            mode=value["mode"],
            target=str(value.get("target") or ""),
            marketplace=str(value.get("marketplace") or ""),
            bundle=bool(value.get("bundle")),
        )
    if "vendor" in raw:
        value = raw["vendor"]
        if not isinstance(value, dict) or not isinstance(value.get("path_param"), str):
            raise ValueError("PDIST_VENDOR_INVALID")
        vendor = VendorChannelSpec(path_param=value["path_param"])
    if "discovery" in raw:
        value = raw["discovery"]
        if not isinstance(value, dict) or not isinstance(value.get("surface"), str):
            raise ValueError("PDIST_DISCOVERY_INVALID")
        discovery = DiscoverySpec(
            surface=value["surface"],
            decision=str(value.get("decision") or ""),
            note=str(value.get("note") or ""),
        )
    return ProviderDistributionSpec(connect=connect, vendor=vendor, discovery=discovery)


def load_distribution_catalog(path: Path | None = None) -> DistributionCatalog:
    """Read ``configs/provider-distribution.json`` from *path* or the repo default."""
    if path is None:
        from ..config_paths import shared_config_path
        path = shared_config_path("provider-distribution")
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"PDIST_CATALOG_UNREADABLE:{path}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0.0":
        raise ValueError("PDIST_CATALOG_SCHEMA_INVALID")
    providers_raw = payload.get("providers")
    if not isinstance(providers_raw, dict):
        raise ValueError("PDIST_CATALOG_PROVIDERS_INVALID")
    providers = {str(key): _parse_provider(value) for key, value in providers_raw.items()}
    return DistributionCatalog(providers=providers)


def provider_distribution(catalog: DistributionCatalog,
                          provider_id: ProviderId) -> ProviderDistributionSpec | None:
    return catalog.providers.get(provider_id.value)


def connect_channel(catalog: DistributionCatalog,
                    provider_id: ProviderId) -> ConnectChannelSpec | None:
    spec = provider_distribution(catalog, provider_id)
    return None if spec is None else spec.connect


def vendor_channel(catalog: DistributionCatalog,
                   provider_id: ProviderId) -> VendorChannelSpec | None:
    spec = provider_distribution(catalog, provider_id)
    return None if spec is None else spec.vendor
