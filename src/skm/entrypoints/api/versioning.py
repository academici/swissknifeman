"""HTTP API version and SemVer admission, before authentication."""

import re
from functools import lru_cache

from starlette.requests import Request

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

__all__ = ["API_VERSION", "check_version"]

API_VERSION = "1.0"
_VERSION = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


@lru_cache(maxsize=256)
def _version(value: str) -> tuple[tuple[int, int, int], tuple[str, ...]]:
    if len(value) > 256:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid client version")
    match = _VERSION.fullmatch(value)
    if match is None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid client version")
    prerelease = tuple((match[4] or "").split(".")) if match[4] else ()
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in prerelease):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid client version")
    return (int(match[1]), int(match[2]), int(match[3] or "0")), prerelease


def _older(client: str, minimum: str) -> bool:
    left, lp = _version(client)
    right, rp = _version(minimum)
    if left != right:
        return left < right
    if not lp or not rp:
        return bool(lp) and not rp
    for a, b in zip(lp, rp, strict=False):
        if a != b:
            if a.isdigit() and b.isdigit():
                return int(a) < int(b)
            if a.isdigit() != b.isdigit():
                return a.isdigit()
            return a < b
    return len(lp) < len(rp)


def check_version(request: Request, minimum: str) -> None:
    versions = request.headers.getlist("skm-client-version")
    if len(versions) > 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Repeated client version")
    if versions and _older(versions[0], minimum):
        raise error_for(
            ErrorCode.CLIENT_TOO_OLD,
            "Client version is too old",
            details={"client_version": versions[0], "min_version": minimum},
        )
