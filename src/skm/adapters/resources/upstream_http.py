"""HTTP adapter for ``UpstreamFetcher`` (extensions §9).

Uses Python stdlib ``urllib.request`` under the ``resources`` adapter layer. Restricts requests to ``https://``
URLs, enforces explicit timeout and byte limits, and maps transport/HTTP/limit failures to
``BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, ...)``.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any, Final, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable
from skm.modules.extensions.ports import UpstreamFetcher

__all__ = ["HttpUpstreamFetcher"]

_DEFAULT_USER_AGENT: Final = "skm-upstream-fetcher/2.0"


def _validate_https_url(url: str) -> None:
    if not url or any(ch.isspace() for ch in url):
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "invalid upstream URL",
            details={"url": url, "reason": "invalid_url"},
        )
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "upstream URL must use https://",
            details={"url": url, "reason": "non_https_url"},
        )


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject any HTTP redirect whose target is not a valid ``https://`` URL."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        try:
            _validate_https_url(newurl)
        except BackendUnavailable:
            # The refused 3xx response is never handed back to the caller; release it here.
            fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpUpstreamFetcher(UpstreamFetcher):
    """Fetch upstream resource files over HTTPS with strict timeout and byte limits."""

    def __init__(
        self,
        *,
        urlopen: Callable[..., Any] | None = None,
        handlers: Sequence[urllib.request.BaseHandler] = (),
        user_agent: str = _DEFAULT_USER_AGENT,
    ) -> None:
        self._urlopen = urlopen
        self._handlers = tuple(handlers)
        self._user_agent = user_agent

    @override
    def fetch(self, url: str, *, max_bytes: int, timeout_seconds: int) -> bytes:
        _validate_https_url(url)
        if max_bytes <= 0:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "max_bytes must be positive",
                details={"url": url, "max_bytes": max_bytes, "reason": "invalid_max_bytes"},
            )
        if timeout_seconds <= 0:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "timeout_seconds must be positive",
                details={"url": url, "timeout_seconds": timeout_seconds, "reason": "invalid_timeout"},
            )

        request = urllib.request.Request(
            url,
            headers={"User-Agent": self._user_agent},
            method="GET",
        )
        opener = (
            self._urlopen
            if self._urlopen is not None
            else urllib.request.build_opener(_HttpsOnlyRedirectHandler(), *self._handlers).open
        )

        try:
            with opener(request, timeout=float(timeout_seconds)) as response:
                status = getattr(response, "status", 200)
                if isinstance(status, int) and not (200 <= status < 300):
                    raise BackendUnavailable(
                        ErrorCode.BACKEND_UNAVAILABLE,
                        f"upstream returned HTTP {status}",
                        details={"url": url, "status": status, "reason": "http_status"},
                    )

                headers = getattr(response, "headers", None)
                if headers is not None and hasattr(headers, "get"):
                    raw_len = headers.get("Content-Length")
                    if raw_len is not None:
                        try:
                            declared_len = int(raw_len)
                        except (TypeError, ValueError):
                            declared_len = -1
                        if declared_len > max_bytes:
                            raise BackendUnavailable(
                                ErrorCode.BACKEND_UNAVAILABLE,
                                f"upstream Content-Length ({declared_len}) exceeds max_bytes ({max_bytes})",
                                details={
                                    "url": url,
                                    "content_length": declared_len,
                                    "max_bytes": max_bytes,
                                    "reason": "max_bytes_exceeded",
                                },
                            )

                try:
                    data = response.read(max_bytes + 1)
                except TypeError:
                    data = response.read()
        except BackendUnavailable:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()  # An HTTPError owns the error response body.
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"failed to fetch upstream resource: {exc}",
                details={"url": url, "reason": "fetch_failed"},
            ) from exc

        if not isinstance(data, bytes):
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                "upstream response body is not bytes",
                details={"url": url, "reason": "invalid_response_body"},
            )
        if len(data) > max_bytes:
            raise BackendUnavailable(
                ErrorCode.BACKEND_UNAVAILABLE,
                f"upstream response exceeds max_bytes ({max_bytes})",
                details={"url": url, "max_bytes": max_bytes, "reason": "max_bytes_exceeded"},
            )
        return data
