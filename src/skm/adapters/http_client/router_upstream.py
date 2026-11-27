"""Credential-isolated upstream transport for the loopback router."""

from __future__ import annotations

import json
import os
import stat
from contextlib import asynccontextmanager
from copy import copy
from typing import TYPE_CHECKING, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Mapping
    from pathlib import Path
    from ssl import SSLContext

__all__ = ["RouterUpstream", "UpstreamError", "UpstreamResponse"]

_FORWARDED = frozenset({"anthropic-version", "anthropic-beta", "content-type", "accept"})
_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "retry-after",
        "request-id",
        "x-request-id",
        "openai-processing-ms",
    }
)


class UpstreamError(Exception):
    """A transport failed without exposing provider credentials or URLs."""


class UpstreamResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status = response.status_code
        self.headers = {
            name: value
            for name, value in response.headers.items()
            if name in _RESPONSE_HEADERS or name.startswith("anthropic-ratelimit-")
        }

    async def chunks(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._response.aiter_raw(chunk_size=None):
                if self._response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise UpstreamError("unexpected upstream content encoding")
                yield chunk
        except httpx.HTTPError:
            raise UpstreamError("upstream response was interrupted") from None


def _read_oauth_token(path: Path) -> str:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ValueError("OAuth token file must be a private regular file")
        value = stream.read(65_537)
    if len(value) > 65_536:
        raise ValueError("OAuth token file exceeds the limit")
    token: object = value.decode().strip()
    if token.startswith("{"):
        payload: object = json.loads(token)
        token = cast("dict[str, object]", payload).get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token or any(not 33 <= ord(char) <= 126 for char in token):
        raise ValueError("invalid OAuth access token")
    return token


class RouterUpstream:
    def __init__(
        self,
        base_url: str,
        *,
        credential: str | None,
        protocol: str,
        bridge_url: str | None,
        provider_routing: Mapping[str, bool],
        verify: SSLContext | bool = True,
        token_file: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if (credential is None) == (token_file is None):
            raise ValueError("upstream requires exactly one credential source")
        self._credential = credential if token_file is None else _read_oauth_token(token_file)
        self._token_file = token_file
        self.protocol = protocol
        self._anthropic_key = protocol == "anthropic" and token_file is None
        self._bridge_url = bridge_url
        self._routing = dict(provider_routing)
        self._verify = verify

    def prepare(self) -> RouterUpstream:
        """Snapshot an OAuth file per request so host-side rotations take effect."""
        if self._token_file is None:
            return self
        result = copy(self)
        try:
            result._credential = _read_oauth_token(self._token_file)
        except (OSError, ValueError, RecursionError):
            raise UpstreamError("upstream credentials are unavailable") from None
        return result

    @asynccontextmanager
    async def request(
        self,
        path: str,
        headers: Mapping[str, str],
        raw: bytes,
        body: dict[str, object],
    ) -> AsyncGenerator[UpstreamResponse]:
        outgoing = {key: value for key, value in headers.items() if key in _FORWARDED}
        outgoing.setdefault("content-type", "application/json")
        outgoing["accept-encoding"] = "identity"
        if self._anthropic_key:
            outgoing["x-api-key"] = cast("str", self._credential)
        else:
            outgoing["authorization"] = f"Bearer {self._credential}"
        base = self._base_url
        if base.endswith("/v1") and path.startswith("/v1/"):
            path = path[3:]
        # Enforce operator routing values even when the caller supplies a provider object.
        content = raw
        if self._routing:
            preferences = body.get("provider")
            routing = (
                {**cast("dict[str, object]", preferences), **self._routing}
                if isinstance(preferences, dict)
                else self._routing
            )
            content = json.dumps({**body, "provider": routing}).encode()
        try:
            async with (
                httpx.AsyncClient(
                    proxy=self._bridge_url,
                    verify=self._verify,
                    trust_env=False,
                    timeout=httpx.Timeout(60, connect=10),
                ) as client,
                client.stream("POST", base + path, headers=outgoing, content=content) as response,
            ):
                yield UpstreamResponse(response)
        except (httpx.HTTPError, httpx.InvalidURL):
            raise UpstreamError("upstream request failed") from None
