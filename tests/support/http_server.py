"""Real ASGI server on a private ephemeral loopback listener."""

import socket
import subprocess
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from shutil import which
from threading import Event, Thread
from time import monotonic

import uvicorn
from starlette.types import ASGIApp

__all__ = ["loopback_certificate", "loopback_server"]


def loopback_certificate(directory: Path) -> tuple[Path, Path]:
    """Create private one-day TLS material for 127.0.0.1 in a test directory."""
    executable = which("openssl")
    if executable is None:
        raise RuntimeError("OpenSSL is required for the HTTPS fixture")
    directory.mkdir(mode=0o700)
    cert, key = directory / "server.crt", directory / "server.key"
    subprocess.run(
        [
            executable,
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-out",
            str(cert),
            "-keyout",
            str(key),
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    return cert, key


@contextmanager
def loopback_server(
    build_app: Callable[[str], ASGIApp], *, tls: tuple[Path, Path] | None = None, port: int = 0
) -> Generator[str]:
    stopped = Event()
    failures: list[BaseException] = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen()
        authority = f"127.0.0.1:{listener.getsockname()[1]}"
        config = uvicorn.Config(
            build_app(authority),
            host="127.0.0.1",
            port=0,
            log_config=None,
            access_log=False,
            lifespan="on",
            loop="asyncio",
            ws="none",
            timeout_graceful_shutdown=2,
            ssl_certfile=tls[0] if tls else None,
            ssl_keyfile=tls[1] if tls else None,
        )
        server = uvicorn.Server(config)

        def serve() -> None:
            try:
                server.run(sockets=[listener])
            except BaseException as error:  # noqa: BLE001 -- propagate server thread failure
                failures.append(error)
            finally:
                stopped.set()

        thread = Thread(target=serve, name="test-asgi-loopback", daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 10
            while not server.started:
                if stopped.wait(0.01) or monotonic() >= deadline:
                    raise RuntimeError("Loopback ASGI server did not start") from (
                        failures[0] if failures else None
                    )
            yield f"{'https' if tls else 'http'}://{authority}"
        finally:
            server.should_exit = True
            thread.join(timeout=6)
            if thread.is_alive():
                server.force_exit = True
                thread.join(timeout=3)
            if thread.is_alive():
                raise RuntimeError("Loopback ASGI server did not stop")
            if failures:
                raise RuntimeError("Loopback ASGI server failed") from failures[0]
