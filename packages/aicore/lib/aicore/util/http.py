"""Shared stdlib-only urllib HTTP client for the monorepo.

Moved from maind.http for JSON GET/POST and health-check probes.
"""
import json
import urllib.error
import urllib.request


class HTTPUnauthorizedError(RuntimeError):
    """HTTP 401: the server is alive but the request is unauthorized.

    It remains a ``RuntimeError`` subclass for backward compatibility.
    """


def _request(url, *, method, data=None, headers=None, timeout):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HTTPUnauthorizedError(f"HTTP 401 from {url}") from e
        raise RuntimeError(f"HTTP {e.code} from {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"no connection with {url}: {getattr(e, 'reason', e)}") from e


def http_get_json(url: str, *, timeout: float = 5, headers=None):
    """Return decoded JSON from GET; network failures raise ``RuntimeError``."""
    body = _request(url, method="GET", headers=headers, timeout=timeout)
    return json.loads(body or "null")


def http_post_json(url: str, payload, *, timeout: float = 10, headers=None):
    """POST JSON and return decoded JSON; an empty response yields ``{}``."""
    data = json.dumps(payload).encode("utf-8")
    merged = {"Content-Type": "application/json", **(headers or {})}
    body = _request(url, method="POST", data=data, headers=merged, timeout=timeout)
    return json.loads(body) if body.strip() else {}


def ping(url: str, *, timeout: float = 3, headers=None) -> bool:
    """Return whether an HTTP server responds, including 4xx and 401 responses."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="GET", headers=headers or {}),
                               timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False
