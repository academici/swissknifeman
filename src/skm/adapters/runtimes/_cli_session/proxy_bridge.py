"""An HTTP egress bridge that keeps upstream proxy authentication in the host process."""

from __future__ import annotations

import base64
import ipaddress
import re
import select
import socket
import socketserver
import ssl
import threading
from contextlib import ExitStack, suppress
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, cast, override
from urllib.parse import unquote, urlsplit

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.policy.domain.network import host_matches

if TYPE_CHECKING:
    from types import TracebackType

__all__ = ["LocalProxyBridge", "ProxyEndpoint"]

_DEFAULT_PORTS = {"http": 80, "https": 443, "socks5": 1080, "socks5h": 1080}
_TIMEOUT = 30
_HEADER_LIMIT = 64 * 1024
_BUFFER_SIZE = 64 * 1024
_HTTP_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_BRIDGE_PORTS: set[int] = set()
_BRIDGE_PORTS_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    scheme: str
    host: str
    port: int
    username: str | None = field(default=None, repr=False)
    password: str = field(default="", repr=False)

    @classmethod
    def parse(cls, url: str) -> ProxyEndpoint | None:
        if url == "direct":
            return None
        try:
            if any(char.isspace() or ord(char) < 32 for char in url):
                raise ValueError
            parts = urlsplit(url)
            scheme = parts.scheme
            host = parts.hostname
            if (
                scheme not in _DEFAULT_PORTS
                or not host
                or "%" in host
                or "\\" in parts.netloc
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
                or parts.port == 0
            ):
                raise ValueError
            username = None if parts.username is None else unquote(parts.username, errors="strict")
            password = unquote(parts.password or "", errors="strict")
            if username is not None and (not username or (":" in username and scheme in {"http", "https"})):
                raise ValueError
            if (
                scheme.startswith("socks")
                and username is not None
                and not (0 < len(username.encode()) <= 255 and 0 < len(password.encode()) <= 255)
            ):
                raise ValueError
            # urlsplit splits userinfo at the final @. Decode escaped and literal @ identically.
            return cls(scheme, host, parts.port or _DEFAULT_PORTS[scheme], username, password)
        except ValueError:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "invalid provider egress proxy") from None

    def http_authorization(self) -> bytes:
        if self.username is None:
            return b""
        credentials = base64.b64encode(f"{self.username}:{self.password}".encode())
        return b"Proxy-Authorization: Basic " + credentials + b"\r\n"


def _recv_exact(peer: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = peer.recv(size - len(data))
        if not chunk:
            raise OSError("proxy peer closed")
        data.extend(chunk)
    return bytes(data)


def _authority(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _is_bridge_target(host: str, port: int) -> bool:
    with _BRIDGE_PORTS_LOCK:
        if port not in _BRIDGE_PORTS:
            return False
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def _dial(host: str, port: int) -> socket.socket:
    for family, kind, protocol, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
        if _is_bridge_target(str(address[0]), port):
            continue
        peer = socket.socket(family, kind, protocol)
        try:
            peer.settimeout(_TIMEOUT)
            peer.connect(address)
        except OSError:
            peer.close()
        else:
            return peer
    raise OSError("egress connection failed")


def _socks_connect(peer: socket.socket, endpoint: ProxyEndpoint, host: str, port: int) -> None:
    method = 0 if endpoint.username is None else 2
    peer.sendall(bytes((5, 1, method)))
    if _recv_exact(peer, 2) != bytes((5, method)):
        raise OSError("SOCKS authentication method refused")
    if endpoint.username is not None:
        user, password = endpoint.username.encode(), endpoint.password.encode()
        peer.sendall(b"\x01" + bytes((len(user),)) + user + bytes((len(password),)) + password)
        if _recv_exact(peer, 2) != b"\x01\x00":
            raise OSError("SOCKS authentication refused")

    address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
    if endpoint.scheme == "socks5":
        info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        resolved = str(info[0][4][0])
        if _is_bridge_target(resolved, port):
            raise OSError("local egress loop")
        address = ipaddress.ip_address(resolved)
    else:
        with suppress(ValueError):
            address = ipaddress.ip_address(host)
    if address is None:
        name = host.encode("idna")
        if len(name) > 255:
            raise OSError("SOCKS destination name too long")
        target = b"\x03" + bytes((len(name),)) + name
    else:
        target = bytes((1 if address.version == 4 else 4,)) + address.packed

    peer.sendall(b"\x05\x01\x00" + target + port.to_bytes(2, "big"))
    version, status, reserved, addr_type = _recv_exact(peer, 4)
    if (version, status, reserved) != (5, 0, 0) or addr_type not in (1, 3, 4):
        raise OSError("SOCKS destination refused")
    addr_length = _recv_exact(peer, 1)[0] if addr_type == 3 else {1: 4, 4: 16}[addr_type]
    _recv_exact(peer, addr_length + 2)


def _http_connect(peer: socket.socket, endpoint: ProxyEndpoint, host: str, port: int) -> None:
    authority = _authority(host, port).encode("ascii")
    peer.sendall(
        b"CONNECT "
        + authority
        + b" HTTP/1.1\r\nHost: "
        + authority
        + b"\r\n"
        + endpoint.http_authorization()
        + b"\r\n"
    )
    # Read exactly the header so immediate tunnel data is preserved.
    headers = bytearray()
    while len(headers) < _HEADER_LIMIT and not headers.endswith(b"\r\n\r\n"):
        headers.extend(_recv_exact(peer, 1))
    status = bytes(headers).split(b" ", 2)
    if not headers.endswith(b"\r\n\r\n") or len(status) < 3 or status[1] != b"200":
        raise OSError("upstream proxy refused CONNECT")


def _dial_target(
    stack: ExitStack, endpoint: ProxyEndpoint | None, host: str, port: int, *, connect: bool
) -> socket.socket:
    if _is_bridge_target(host, port):
        raise OSError("local egress loop")
    if endpoint is None:
        return stack.enter_context(_dial(host, port))
    peer = stack.enter_context(_dial(endpoint.host, endpoint.port))
    if endpoint.scheme == "https":
        peer = stack.enter_context(
            ssl.create_default_context().wrap_socket(peer, server_hostname=endpoint.host)
        )
    if endpoint.scheme.startswith("socks"):
        _socks_connect(peer, endpoint, host, port)
    elif connect:
        _http_connect(peer, endpoint, host, port)
    return peer


def _relay(client: socket.socket, peer: socket.socket, *, http: bool) -> None:
    if http:
        while data := peer.recv(_BUFFER_SIZE):
            client.sendall(data)
        return
    sources = [client, peer]
    while sources:
        pending = peer in sources and isinstance(peer, ssl.SSLSocket) and peer.pending()
        ready = [peer] if pending else select.select(sources, [], [], _TIMEOUT)[0]
        if not ready:
            return
        for source in ready:
            dest = peer if source is client else client
            data = source.recv(_BUFFER_SIZE)
            if data:
                dest.sendall(data)
            else:
                sources.remove(source)
                # A TLS half-close would also shut down the read side of the proxy connection.
                if not isinstance(dest, ssl.SSLSocket):
                    with suppress(OSError):
                        dest.shutdown(socket.SHUT_WR)


@dataclass(frozen=True, slots=True)
class _Request:
    method: bytes
    host: str
    port: int
    path: str
    headers: dict[bytes, bytes]
    length: int


def _destination(method: bytes, target: str) -> tuple[str, int, str]:
    connect = method == b"CONNECT"
    parts = urlsplit("//" + target if connect else target)
    if (
        not parts.hostname
        or parts.username is not None
        or "#" in target
        or "\\" in target
        or "%" in parts.hostname
        or parts.port == 0
        or (connect and (not parts.port or parts.path or "?" in target))
        or (not connect and parts.scheme != "http")
    ):
        raise ValueError("invalid proxy destination")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.hostname, parts.port or 80, path


class _BridgeHandler(socketserver.StreamRequestHandler):
    rbufsize = 0

    def _read_request(self) -> _Request:
        line = self.rfile.readline(_HEADER_LIMIT + 1)
        if not line.endswith(b"\r\n") or len(line) > _HEADER_LIMIT:
            raise ValueError("invalid proxy request line")
        method, raw_target, version = line[:-2].split(b" ")
        if not _HTTP_TOKEN.fullmatch(method) or version not in (b"HTTP/1.0", b"HTTP/1.1"):
            raise ValueError("invalid proxy request line")
        if any(char <= 32 or char >= 127 for char in raw_target):
            raise ValueError("invalid proxy target")
        target = raw_target.decode("ascii")
        host, port, path = _destination(method, target)
        headers: dict[bytes, bytes] = {}
        remaining = _HEADER_LIMIT - len(line)
        while True:
            line = self.rfile.readline(remaining + 1)
            remaining -= len(line)
            if remaining < 0 or not line.endswith(b"\r\n"):
                raise ValueError("invalid proxy request headers")
            if line == b"\r\n":
                break
            key, _, value = line[:-2].partition(b":")
            key = key.lower()
            if not _HTTP_TOKEN.fullmatch(key) or key in headers or any(ch < 32 and ch != 9 for ch in value):
                raise ValueError("invalid proxy request headers")
            headers[key] = value.strip(b" \t")
        size = headers.get(b"content-length", b"0")
        if b"transfer-encoding" in headers or not size.isdigit() or len(size) > 18:
            raise ValueError("unsupported proxy request framing")
        length = int(size)
        if method == b"CONNECT" and length:
            raise ValueError("unexpected CONNECT request body")
        return _Request(method, host, port, path, headers, length)

    def _reply(self, status: HTTPStatus) -> None:
        self.request.sendall(f"HTTP/1.1 {status.value} {status.phrase}\r\n\r\n".encode("ascii"))

    def _forward_http(self, request: _Request, peer: socket.socket, endpoint: ProxyEndpoint | None) -> None:
        http_proxy = endpoint if endpoint is not None and endpoint.scheme in {"http", "https"} else None
        authority = _authority(request.host, request.port)
        target = request.path if http_proxy is None else f"http://{authority}{request.path}"
        headers = bytearray(request.method + b" " + target.encode("ascii") + b" HTTP/1.1\r\n")
        headers.extend(f"Host: {authority}\r\n".encode("ascii"))
        headers.extend(b"Connection: close\r\n")
        if request.length:
            headers.extend(f"Content-Length: {request.length}\r\n".encode("ascii"))
        nominated = set(request.headers.get(b"connection", b"").lower().replace(b" ", b"").split(b","))
        drop = {
            b"host",
            b"content-length",
            b"connection",
            b"keep-alive",
            b"expect",
            b"te",
            b"proxy-authorization",
            b"proxy-authenticate",
            b"proxy-connection",
            b"trailer",
            b"upgrade",
        }
        for key, value in request.headers.items():
            if key not in (drop | nominated):
                headers.extend(key + b": " + value + b"\r\n")
        if http_proxy is not None:
            headers.extend(http_proxy.http_authorization())
        peer.sendall(headers + b"\r\n")
        remaining = request.length
        if remaining and request.headers.get(b"expect", b"").lower() == b"100-continue":
            self._reply(HTTPStatus.CONTINUE)
        while remaining:
            data = _recv_exact(self.request, min(remaining, _BUFFER_SIZE))
            peer.sendall(data)
            remaining -= len(data)

    @override
    def handle(self) -> None:
        server = cast("_BridgeServer", self.server)
        self.request.settimeout(_TIMEOUT)
        try:
            request = self._read_request()
        except ValueError:
            self._reply(HTTPStatus.BAD_REQUEST)
            return
        allowed = server.allowed_hosts
        if allowed is not None and not any(
            host_matches(item, request.host, request.port) for item in allowed
        ):
            self._reply(HTTPStatus.FORBIDDEN)
            return

        connect = request.method == b"CONNECT"
        endpoint = server.endpoint
        with ExitStack() as stack:
            try:
                peer = _dial_target(stack, endpoint, request.host, request.port, connect=connect)
                if not server.track(peer):
                    return
                stack.callback(server.untrack, peer)
            except (OSError, ValueError):
                self._reply(HTTPStatus.BAD_GATEWAY)
                return
            if connect:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            else:
                self._forward_http(request, peer, endpoint)
            _relay(self.request, peer, http=not connect)


class _BridgeServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, endpoint: ProxyEndpoint | None, allowed_hosts: frozenset[str] | None) -> None:
        self.endpoint = endpoint
        self.allowed_hosts = allowed_hosts
        self.clients: set[socket.socket] = set()
        self.clients_lock = threading.Lock()
        self.closing = False
        super().__init__(("127.0.0.1", 0), _BridgeHandler)

    def track(self, peer: socket.socket) -> bool:
        with self.clients_lock:
            if self.closing:
                return False
            self.clients.add(peer)
            return True

    def untrack(self, peer: socket.socket) -> None:
        with self.clients_lock:
            self.clients.discard(peer)

    @override
    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.track(request):
            super().process_request(request, client_address)
        else:
            super().shutdown_request(request)

    @override
    def shutdown_request(self, request: socket.socket) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.untrack(request)
        super().shutdown_request(request)

    @override
    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        # socketserver's default prints a traceback that can contain upstream inputs.
        pass

    def close_clients(self) -> None:
        with self.clients_lock:
            self.closing = True
            for client in self.clients:
                with suppress(OSError):
                    client.shutdown(socket.SHUT_RDWR)


class LocalProxyBridge:
    """Scope a synchronous loopback listener to a single launch or host probe."""

    def __init__(
        self, upstream: ProxyEndpoint | None, *, allowed_hosts: frozenset[str] | None = None
    ) -> None:
        self._endpoint = upstream
        self._allowed_hosts = allowed_hosts
        self._server: _BridgeServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def allowed_hosts(self) -> frozenset[str] | None:
        return self._allowed_hosts

    @property
    def url(self) -> str | None:
        return None if self._server is None else f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> LocalProxyBridge:
        if self._server is not None:
            raise RuntimeError("egress bridge already started")
        server = _BridgeServer(self._endpoint, self.allowed_hosts)
        port = server.server_address[1]
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="skm-egress", daemon=True
        )
        with _BRIDGE_PORTS_LOCK:
            _BRIDGE_PORTS.add(port)
        try:
            thread.start()
        except BaseException:
            with _BRIDGE_PORTS_LOCK:
                server.server_close()
                _BRIDGE_PORTS.discard(port)
            raise
        self._server, self._thread = server, thread
        return self

    def close(self) -> None:
        server, thread = self._server, self._thread
        if server is None or thread is None:
            return
        self._server = self._thread = None
        server.shutdown()
        server.close_clients()
        with _BRIDGE_PORTS_LOCK:
            server.server_close()
            _BRIDGE_PORTS.discard(server.server_address[1])
        thread.join()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.close()
