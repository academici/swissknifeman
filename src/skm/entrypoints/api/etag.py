"""HTTP entity tags for resource versions and content digests."""

import re

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for

__all__ = ["check_version", "encode_etag", "parse_if_match", "parse_if_none_match"]

_ETAG = re.compile(r'W/"v([1-9][0-9]*)"')
_STRONG_TAG = re.compile(r'"[\x21\x23-\x7e\x80-\xff]*"')


def encode_etag(version: int | str) -> str:
    if isinstance(version, str):
        tag = f'"{version}"'
        if _STRONG_TAG.fullmatch(tag) is None:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid resource digest")
        return tag
    if type(version) is not int or version < 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid resource version")
    return f'W/"v{version}"'


def parse_if_match(value: str | None, *, required: bool = True) -> int | None:
    if value is None:
        if required:
            raise error_for(
                ErrorCode.PRECONDITION_REQUIRED, "If-Match is required", details={"header": "If-Match"}
            )
        return None
    matched = _ETAG.fullmatch(value)
    if matched is None or len(matched[1]) > 19:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid If-Match")
    return int(matched[1])


def parse_if_none_match(value: str | None) -> str | None:
    if value is not None and value != "*" and not (_ETAG.fullmatch(value) or _STRONG_TAG.fullmatch(value)):
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid If-None-Match")
    return value


def check_version(expected: int, actual: int | None) -> None:
    if expected != actual:
        raise error_for(
            ErrorCode.VERSION_CONFLICT,
            "Resource version changed",
            details={
                "expected": expected,
                "actual": actual,
            },
        )
