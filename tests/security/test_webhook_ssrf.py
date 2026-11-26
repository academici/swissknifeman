"""Real HTTP transport admission, pinning, signatures and bounded response regressions."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

import pytest

from skm.adapters.event_sinks._pinned_http import HttpRefused, PinnedHttpClient
from skm.adapters.event_sinks.webhook import WebhookSink
from skm.adapters.event_sinks.webhook_signing import sign, verify
from skm.kernel.events import EventEnvelope
from skm.platform.jsonc.canonical import canonical_bytes


@contextlib.contextmanager
def _server(
    status: int = 200, response: bytes = b"ok", retry_after: str | None = None, chunk_delay: float = 0
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append({"body": body, "headers": self.headers, "path": self.path})
            self.send_response(status)
            self.send_header("Content-Length", str(len(response)))
            if 300 <= status < 400:
                self.send_header("Location", "http://169.254.169.254/metadata")
            if retry_after:
                self.send_header("Retry-After", retry_after)
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                if chunk_delay:
                    for byte in response:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(chunk_delay)
                else:
                    self.wfile.write(response)

        @override
        def log_message(self, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/hook", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _fixture() -> tuple[bytes, str, EventEnvelope]:
    raw = (
        Path(__file__).resolve().parents[2]
        / "tests/fixtures/corpus/examples/integrations/hooks/webhook-request.http"
    ).read_bytes()
    head, body = raw.split(b"\n\n", 1)
    import json

    signature = next(
        line.split(b": ", 1)[1].decode() for line in head.splitlines() if line.startswith(b"SKM-Signature:")
    )
    body = body.rstrip(b"\n")
    return body, signature, EventEnvelope.from_json(json.loads(body)["event"])


def test_hmac_exact_fixture_rotation_and_replay() -> None:
    body, header, _ = _fixture()
    assert verify(body, header, secret="example-secret-do-not-use", now=1793023343)
    rotated = sign(body, secrets=["new", "example-secret-do-not-use"], timestamp=1793023343)
    assert verify(body, rotated, secret="new", now=1793023343 + 300)
    assert verify(body, rotated, secret="example-secret-do-not-use", now=1793023343)
    assert not verify(body + b"\n", rotated, secret="new", now=1793023343)
    assert not verify(body, rotated, secret="new", now=1793023343 + 301)
    for malformed in ("", "t=bad,v1=abc", "t=1,t=2,v1=a", "t=1,v1=é", "t=1,broken"):
        assert not verify(body, malformed, secret="new", now=1)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "100.64.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "ff02::1",
        "0.0.0.0",
        "::ffff:127.0.0.1",
    ],
)
def test_every_dns_address_is_guarded(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (family, socket.SOCK_STREAM, 6, "", (address, 443)),
        ],
    )
    with pytest.raises(HttpRefused, match="address_refused"):
        PinnedHttpClient().post("https://hooks.example.test/hook", body=b"{}", headers={}, timeout_ms=1000)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com/hook",
        "https://user:pass@example.com",
        "https://example.com/#fragment",
    ],
)
def test_url_scheme_and_credentials_refused(url: str) -> None:
    with pytest.raises(HttpRefused, match="scheme_refused"):
        PinnedHttpClient().post(url, body=b"", headers={}, timeout_ms=1000)


def test_loopback_requires_both_permissions_and_response_is_bounded() -> None:
    with _server(response=b"x" * 100_000) as (url, requests):
        with pytest.raises(HttpRefused, match="scheme_refused"):
            PinnedHttpClient().post(url, body=b"", headers={}, timeout_ms=1000)
        with pytest.raises(HttpRefused, match="address_refused"):
            PinnedHttpClient().post(url, body=b"", headers={}, timeout_ms=1000, allow_http_loopback=True)
        response = PinnedHttpClient().post(
            url,
            body=b"abc",
            headers={},
            timeout_ms=1000,
            allow_http_loopback=True,
            allow_private_networks=True,
            max_response_bytes=4096,
        )
        assert len(response.body) == 4096
        assert requests[0]["body"] == b"abc"


@pytest.mark.parametrize("address", ["169.254.169.254", "fe80::1", "224.0.0.1", "0.0.0.0"])
def test_private_override_never_allows_metadata_or_multicast(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
    )
    with pytest.raises(HttpRefused, match="address_refused"):
        PinnedHttpClient().post(
            "https://example.test", body=b"", headers={}, timeout_ms=1000, allow_private_networks=True
        )


def test_dns_is_repeated_and_connection_uses_the_checked_numeric_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = socket.getaddrinfo
    calls: list[str] = []
    with _server() as (url, _):
        port = int(url.split(":")[2].split("/")[0])

        def resolve(host: str, _port: int, **_kw: Any) -> list:
            calls.append(host)
            assert host == "hooks.example.test"
            return original("127.0.0.1", port, type=socket.SOCK_STREAM)

        monkeypatch.setattr(socket, "getaddrinfo", resolve)
        for _ in range(2):
            result = PinnedHttpClient().post(
                f"http://hooks.example.test:{port}/hook",
                body=b"{}",
                headers={},
                timeout_ms=1000,
                allow_http_loopback=True,
                allow_private_networks=True,
            )
            assert result.status == 200
    assert calls == ["hooks.example.test", "hooks.example.test"]


@pytest.mark.parametrize(
    ("status", "ok", "retryable", "reason"),
    [
        (204, True, False, None),
        (302, False, False, "redirect_refused"),
        (410, False, False, "gone"),
        (429, False, True, "http_429"),
        (503, False, True, "http_503"),
        (501, False, False, "http_501"),
    ],
)
def test_sink_real_http_signed_exact_bytes_and_classification(
    status: int, ok: bool, retryable: bool, reason: str | None
) -> None:
    import json
    from datetime import UTC, datetime

    from fakes.clock import FrozenClock

    _, _, envelope = _fixture()
    clock = FrozenClock(datetime(2026, 10, 25, 14, 2, 23, 880000, tzinfo=UTC))
    with _server(status, b"x" * 4096, "2") as (url, requests):
        sink = WebhookSink(
            http=PinnedHttpClient(),
            settings={"allow_private_networks": True, "allow_http_loopback": True},
            clock=clock,
            version="2.0.0",
        )
        result = sink.deliver(
            envelope,
            {
                "url": url,
                "secret": "new",
                "previous_secret": "old",
                "delivery_id": "019a4c10-3c4d-7e5f-8061-7b8c9d0e1f2a",
                "subscription_id": "ci-notify",
                "attempt": 2,
                "timeout_ms": 1000,
            },
        )
        assert (result.ok, result.retryable, result.reason) == (ok, retryable, reason)
        assert result.retry_after_ms == (2000 if retryable else None)
        assert len(result.response_excerpt or "") == (0 if status == 204 else 2048)
        assert len(requests) == 1
        request = requests[0]
        assert request["body"] == canonical_bytes(json.loads(request["body"]))
        assert json.loads(request["body"])["attempt"] == 2
        for key in ("new", "old"):
            assert verify(
                request["body"],
                request["headers"]["SKM-Signature"],
                secret=key,
                now=int(clock.now().timestamp()),
            )


def test_total_timeout_bounds_a_trickling_response() -> None:
    with _server(response=b"x" * 100, chunk_delay=0.02) as (url, _requests):
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            PinnedHttpClient().post(
                url,
                body=b"{}",
                headers={},
                timeout_ms=100,
                allow_http_loopback=True,
                allow_private_networks=True,
            )
        assert time.monotonic() - started < 1
