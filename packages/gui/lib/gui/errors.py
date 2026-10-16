"""Error codes of the gui control plane: the one registry of code -> (class, HTTP status).

The classes are the enum of ``api-error/v1``; docs/api.md lists every code with its class, status and whether the
same request may succeed later unchanged (``RETRYABLE``).
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

CLASSES = ("invalid", "unauthorized", "forbidden", "not_found", "conflict", "locked", "incompatible", "unavailable",
           "timeout", "limit", "internal")

CODES: Dict[str, Tuple[str, int]] = {
    # Local API: authentication and transport.
    "AUTH_REQUIRED": ("unauthorized", 401),
    "AUTH_INVALID": ("unauthorized", 401),
    "HOST_REJECTED": ("forbidden", 403),
    "ORIGIN_REJECTED": ("forbidden", 403),
    "PROTOCOL_INCOMPATIBLE": ("incompatible", 409),
    "PAYLOAD_TOO_LARGE": ("limit", 413),
    # Requests and handlers.
    "NOT_FOUND": ("not_found", 404),
    "INPUT_INVALID": ("invalid", 422),
    "OUTPUT_INVALID": ("internal", 502),
    "PATH_ESCAPE": ("forbidden", 403),
    "PERMISSION_DENIED": ("forbidden", 403),
    "CONFIRMATION_REQUIRED": ("forbidden", 428),
    "CONCURRENCY_LIMIT": ("limit", 429),
    "RUN_NOT_CANCELLABLE": ("conflict", 409),
    "HANDLER_FAILED": ("unavailable", 502),
    "HANDLER_TIMEOUT": ("timeout", 504),
    "PLUGIN_UNAVAILABLE": ("unavailable", 503),
    "PLUGIN_QUARANTINED": ("unavailable", 503),
    # Configuration writes.
    "CONFIG_REVISION_CONFLICT": ("conflict", 409),
    "CONFIG_LOCKED": ("locked", 423),
    "CONFIG_LAYER_FORBIDDEN": ("forbidden", 403),
    "PREVIEW_STALE": ("conflict", 409),
    # Contribution resolver and catalog sources (docs/contribution.md).
    "CONTRIB_INVALID": ("invalid", 422),
    "CONTRIB_UNREADABLE": ("invalid", 422),
    "CONTRIB_OWNER_MISMATCH": ("invalid", 422),
    "CONTRIB_ID_PREFIX": ("invalid", 422),
    "CONTRIB_CONFLICT": ("conflict", 409),
    "CONTRIB_INCOMPATIBLE": ("incompatible", 409),
    "CONTRIB_HANDLER_MISSING": ("invalid", 422),
    "CONTRIB_PATH_ESCAPE": ("forbidden", 403),
    "CONTRIB_REF_UNKNOWN": ("invalid", 422),
    "CONTRIB_INPUT_UNKNOWN": ("invalid", 422),
    "CONTRIB_CAPABILITY_RESERVED": ("forbidden", 403),
    "CATALOG_SOURCE_UNAVAILABLE": ("unavailable", 503),
    # Backend host: third-party packages and the state database.
    "GUI_DEPS_UNAVAILABLE": ("unavailable", 503),
    "STATE_INCOMPATIBLE": ("internal", 500),
    # Anything unexpected; the message never carries a trace.
    "INTERNAL": ("internal", 500),
}

# Transient failures: the same request may succeed later. A quarantined plugin or a too large body does not heal.
RETRYABLE = frozenset({"CONCURRENCY_LIMIT", "HANDLER_FAILED", "HANDLER_TIMEOUT", "PLUGIN_UNAVAILABLE",
                       "CONFIG_LOCKED", "CATALOG_SOURCE_UNAVAILABLE",
                       "GUI_DEPS_UNAVAILABLE"})


def error_class(code: str) -> str:
    return CODES[code][0]


def http_status(code: str) -> int:
    return CODES[code][1]


def retryable(code: str) -> bool:
    if code not in CODES:
        raise KeyError(code)
    return code in RETRYABLE


class GuiError(Exception):
    """A failure with a registered ``code``; ``str()`` is ``<code>: <message>``. The message must be safe to show."""

    def __init__(self, code: str, message: str, *, details: Optional[Mapping[str, object]] = None,
                 issues: Optional[List[Mapping[str, str]]] = None) -> None:
        if code not in CODES:
            raise ValueError(f"unregistered gui error code {code!r}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.issues = [dict(issue) for issue in issues or ()]

    def envelope(self, correlation_id: str) -> dict:
        """The ``api-error/v1`` document of this error."""
        error: dict = {"code": self.code, "class": error_class(self.code), "message": self.message,
                       "retryable": retryable(self.code), "correlation_id": correlation_id}
        if self.details:
            error["details"] = self.details
        if self.issues:
            error["issues"] = self.issues
        return {"$schema": "urn:swissknifeman:gui:api-error:v1", "error": error}
