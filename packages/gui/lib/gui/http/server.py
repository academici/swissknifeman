"""Run the app with uvicorn on a socket bound to ``127.0.0.1`` only (I9): no proxy headers, no server header,
no access log, WebSocket by ``wsproto``.

SIGINT/SIGTERM shut the server down gracefully (uvicorn's own handlers). uvicorn then raises the captured signal
again; :func:`serve` turns that into a normal return, so the caller still removes ``backend.json`` and releases the
instance lock.
"""
from __future__ import annotations

import signal
import socket
import threading

import uvicorn

from .app import create_app


class _Stopped(Exception):
    pass


def _stop(signum, frame):
    raise _Stopped(signum)


def bind(port: int) -> socket.socket:
    """A listening TCP socket on ``127.0.0.1:port`` (0: a free port). There is no other address."""
    return socket.create_server(("127.0.0.1", port), family=socket.AF_INET, backlog=128)


def serve(state, sock: socket.socket) -> None:
    config = uvicorn.Config(create_app(state), ws="wsproto", lifespan="on", log_config=None, access_log=False,
                            server_header=False, date_header=False, proxy_headers=False, forwarded_allow_ips="",
                            timeout_graceful_shutdown=10)
    main = threading.current_thread() is threading.main_thread()
    previous = signal.signal(signal.SIGTERM, _stop) if main else None
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except (_Stopped, KeyboardInterrupt):
        pass
    finally:
        if main:
            signal.signal(signal.SIGTERM, previous)
