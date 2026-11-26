"""HTTPS transport and provider slug map for catalog sync.

Provider names stay here, in composition, so the runtimes application never names a vendor.
The transport wraps the resources HTTP adapter and returns text. The sync job receives it already built.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, override

from skm.adapters.resources.upstream_http import HttpUpstreamFetcher
from skm.modules.runtimes.public import CatalogTransport

__all__ = ["PROVIDER_RUNTIME", "HttpsCatalogTransport"]

_MAX_BYTES: Final = 8 * 1024 * 1024
_TIMEOUT_SECONDS: Final = 20

# Inventory provider slug -> runtime id that can launch it.
PROVIDER_RUNTIME: Final[Mapping[str, str]] = {
    "anthropic": "claude_code",
    "claude": "claude_code",
    "openai": "codex",
    "xai": "grok",
    "x-ai": "grok",
    "grok": "grok",
    "cursor": "cursor",
}


class HttpsCatalogTransport(CatalogTransport):
    """One HTTPS GET through ``HttpUpstreamFetcher``. Missing documents fail closed."""

    def __init__(self, fetcher: HttpUpstreamFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpUpstreamFetcher()

    @override
    def get_text(self, url: str) -> str:
        return self._fetcher.fetch(url, max_bytes=_MAX_BYTES, timeout_seconds=_TIMEOUT_SECONDS).decode(
            "utf-8"
        )
