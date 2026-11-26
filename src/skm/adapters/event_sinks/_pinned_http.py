"""Bounded stdlib HTTP transport with per-attempt DNS admission and pinned TLS."""

from __future__ import annotations

import contextlib
import http.client
import ipaddress
import queue
import socket
import ssl
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

__all__ = ["HttpRefused", "PinnedHttpClient"]

type _Address = tuple[int, int, int, str, tuple[Any, ...]]


class HttpRefused(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    body: bytes
    retry_after: str | None


def _resolve(host: str, port: int, remaining: Callable[[], float]) -> Sequence[_Address]:
    result: queue.Queue[Sequence[_Address] | OSError] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError as exc:
            result.put(exc)

    threading.Thread(target=resolve, daemon=True).start()
    try:
        found = result.get(timeout=remaining())
    except queue.Empty:
        raise TimeoutError from None
    if isinstance(found, OSError):
        raise found
    if not found:
        raise socket.gaierror("no addresses")
    return found


def _admit(addresses: Sequence[_Address], *, secure: bool, allow_private_networks: bool) -> None:
    for _, _, _, _, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise HttpRefused("address_refused")
        if not allow_private_networks and not address.is_global:
            raise HttpRefused("address_refused")
        if not secure and not address.is_loopback:
            raise HttpRefused("scheme_refused")


class PinnedHttpClient:
    def post(
        self,
        url: str,
        *,
        body: bytes,
        headers: Mapping[str, str],
        timeout_ms: int,
        allow_private_networks: bool = False,
        allow_http_loopback: bool = False,
        max_response_bytes: int = 65536,
    ) -> _Response:
        deadline = time.monotonic() + timeout_ms / 1000

        def remaining() -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise TimeoutError
            return value

        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not host or parsed.username is not None or parsed.password is not None or parsed.fragment:
                raise HttpRefused("scheme_refused")
        except ValueError:
            raise HttpRefused("scheme_refused") from None
        if parsed.scheme not in {"http", "https"} or (parsed.scheme == "http" and not allow_http_loopback):
            raise HttpRefused("scheme_refused")
        addresses = _resolve(host, port, remaining)
        _admit(addresses, secure=parsed.scheme == "https", allow_private_networks=allow_private_networks)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        return self._exchange(
            host,
            port,
            addresses[0],
            secure=parsed.scheme == "https",
            path=path,
            body=body,
            headers=headers,
            remaining=remaining,
            deadline=deadline,
            max_response_bytes=max(0, max_response_bytes),
        )

    def _exchange(  # noqa: PLR0913 - explicit transport policy, already validated by post
        self,
        host: str,
        port: int,
        address: _Address,
        *,
        secure: bool,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        remaining: Callable[[], float],
        deadline: float,
        max_response_bytes: int,
    ) -> _Response:
        family, socktype, proto, _, sockaddr = address
        connection = http.client.HTTPConnection(host, port, timeout=remaining())
        sock = socket.socket(family, socktype, proto)
        watchdog: threading.Timer | None = None
        try:
            sock.settimeout(remaining())
            sock.connect(sockaddr)
            if secure:
                sock.settimeout(remaining())
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)

            def expire() -> None:
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)

            # Enforce a total deadline even against slow headers or a trickling body.
            watchdog = threading.Timer(remaining(), expire)
            watchdog.daemon = True
            watchdog.start()
            connection.sock = sock
            sock.settimeout(remaining())
            connection.request("POST", path, body=body, headers=dict(headers))
            sock.settimeout(remaining())
            response = connection.getresponse()
            chunks: list[bytes] = []
            size = 0
            while size < max_response_bytes and not response.isclosed():
                sock.settimeout(remaining())
                chunk = response.read1(min(8192, max_response_bytes - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            remaining()
            return _Response(response.status, b"".join(chunks), response.getheader("Retry-After"))
        except (OSError, http.client.HTTPException):
            if time.monotonic() >= deadline:
                raise TimeoutError from None
            raise
        finally:
            if watchdog is not None:
                watchdog.cancel()
            connection.close()
            sock.close()
