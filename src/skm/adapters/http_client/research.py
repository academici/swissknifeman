"""Cancellable single-request transport for host research providers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from skm.kernel.cancel import CancelToken

__all__ = ["ResearchHttpTransport"]

_MAX_RESPONSE_BYTES = 2_000_000


async def _cancel_when_requested(cancel: CancelToken, request: asyncio.Task[bytes | None]) -> None:
    while not request.done():
        if cancel.cancelled:
            request.cancel()
            return
        await asyncio.sleep(0.05)


class ResearchHttpTransport:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def request(
        self,
        request: tuple[str, str, dict[str, Any]],
        *,
        cancel: CancelToken,
        timeout: float,
        allow_not_found: bool = False,
    ) -> bytes | None:
        cancel.raise_if_cancelled()
        try:
            return asyncio.run(self._exchange(request, cancel, timeout, allow_not_found))
        except httpx.TimeoutException:
            raise TimeoutError("Research provider timed out") from None
        except (httpx.HTTPError, httpx.InvalidURL):
            raise ValueError("Research provider request failed") from None

    async def _exchange(
        self,
        request: tuple[str, str, dict[str, Any]],
        cancel: CancelToken,
        timeout: float,
        allow_not_found: bool,
    ) -> bytes | None:
        async with asyncio.timeout(timeout):
            pending = asyncio.create_task(self._read(request, cancel, timeout, allow_not_found))
            watcher = asyncio.create_task(_cancel_when_requested(cancel, pending))
            try:
                return await pending
            except asyncio.CancelledError:
                cancel.raise_if_cancelled()
                raise
            finally:
                watcher.cancel()

    async def _read(
        self,
        request: tuple[str, str, dict[str, Any]],
        cancel: CancelToken,
        timeout: float,
        allow_not_found: bool,
    ) -> bytes | None:
        method, endpoint, options = request
        headers = {"Accept-Encoding": "identity", **options.get("headers", {})}
        async with (
            httpx.AsyncClient(
                transport=self._transport, trust_env=False, follow_redirects=False, timeout=timeout
            ) as client,
            client.stream(
                method, endpoint, headers=headers, params=options.get("params"), json=options.get("json")
            ) as response,
        ):
            if allow_not_found and response.status_code == 404:
                return None
            if response.status_code in (429, 503):
                raise TimeoutError("Research provider is temporarily unavailable")
            response.raise_for_status()
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("Research provider response is invalid")
            content = bytearray()
            async for chunk in response.aiter_raw():
                cancel.raise_if_cancelled()
                if len(content) + len(chunk) > _MAX_RESPONSE_BYTES:
                    raise ValueError("Research provider response is invalid")
                content.extend(chunk)
            return bytes(content)
