"""Token-budget fitting and session-local continuation of pinned authoring reads."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.logging.logger import get_logger
from skm.platform.tokens.heuristic import estimate_tokens

from .protocol import json_text

__all__ = [
    "AUTHORING_READS",
    "AuthoringReceipt",
    "AuthoringReceipts",
    "TruncationReceipt",
    "estimate_tokens",
    "fit",
]

_HINT: Final = (
    "response truncated by context limit; narrow the request (query/limit/entity) or page with `after`"
)
_LOG = get_logger("entrypoints.mcp")
AUTHORING_READS: Final = frozenset({"skm_plan_entities", "skm_plan_read_text"})
_MAX_RECEIPTS: Final = 128
_RECEIPT_FIELD: Final = "authoring_receipt"


@dataclass(frozen=True, slots=True)
class TruncationReceipt:
    returned_count: int
    total_count: int
    truncated: bool = True
    hint: str = _HINT

    def to_json(self) -> JsonObject:
        return {
            "truncated": self.truncated,
            "returned_count": self.returned_count,
            "total_count": self.total_count,
            "hint": self.hint,
        }


def _fits(payload: JsonValue, limit: int) -> bool:
    return estimate_tokens(json_text(payload)) <= limit


def _largest_list(payload: JsonValue) -> tuple[str | None, list[JsonValue]] | None:
    if isinstance(payload, list):
        return (None, payload) if payload else None
    if isinstance(payload, dict):
        candidates = (
            (key, value)
            for key, value in payload.items()
            if isinstance(value, list) and value and f"{key}_truncated" not in payload
        )
        return max(candidates, key=lambda pair: (estimate_tokens(json_text(pair[1])), pair[0]), default=None)
    return None


def _trim(
    payload: JsonValue, key: str | None, items: list[JsonValue], count: int
) -> tuple[JsonObject, TruncationReceipt]:
    receipt = TruncationReceipt(count, len(items))
    if key is not None and isinstance(payload, dict):
        return {**payload, key: items[:count], f"{key}_truncated": receipt.to_json()}, receipt
    return {"items": items[:count], **receipt.to_json()}, receipt


def fit(
    payload: JsonValue, limit: int, *, is_error: bool = False
) -> tuple[JsonValue, TruncationReceipt | None]:
    """Fit compact JSON by removing list items, recording each trimmed list."""
    if is_error or _fits(payload, limit):
        return payload, None
    candidate = payload
    while (largest := _largest_list(candidate)) is not None:
        key, items = largest
        empty, receipt = _trim(candidate, key, items, 0)
        if _fits(empty, limit):
            return _fit_prefix(candidate, key, items, limit, empty, receipt)
        candidate = empty
    _LOG.warning("mcp.response_over_budget")
    return payload, None


def _fit_prefix(
    payload: JsonValue,
    key: str | None,
    items: list[JsonValue],
    limit: int,
    best: JsonObject,
    receipt: TruncationReceipt,
) -> tuple[JsonObject, TruncationReceipt]:
    lo, hi = 1, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate, candidate_receipt = _trim(payload, key, items, mid)
        if _fits(candidate, limit):
            best, receipt = candidate, candidate_receipt
            lo = mid + 1
        else:
            hi = mid - 1
    return best, receipt


@dataclass(frozen=True, slots=True)
class AuthoringReceipt:
    """A server-owned continuation. Arguments include the original filters and an exact source."""

    tool: str
    arguments: JsonObject
    source: JsonObject
    skip: int = 0


def _pinned_arguments(arguments: JsonObject, source: JsonObject) -> JsonObject:
    pinned = {
        key: value
        for key, value in arguments.items()
        if key
        not in {
            "revision",
            "revision_id",
            "draft_id",
            "expected_edit_version",
        }
    }
    pinned["plan"] = source["plan_id"]
    if source["kind"] == "revision":
        pinned["revision_id"] = source["revision_id"]
    elif source["kind"] == "draft":
        pinned["draft_id"] = source["draft_id"]
        pinned["expected_edit_version"] = source["edit_version"]
    else:
        raise ValueError("authoring read returned an unknown source kind")
    return pinned


def _check_source() -> Conflict:
    return Conflict(ErrorCode.VERSION_CONFLICT, "The authoring read no longer matches its pinned source")


class AuthoringReceipts:
    """Keep bounded continuation metadata for one stdio connection, with no cached tool results."""

    def __init__(self) -> None:
        self._receipts: OrderedDict[str, AuthoringReceipt] = OrderedDict()

    def get(self, token: str) -> AuthoringReceipt:
        found = self._receipts.get(token)
        if found is None:
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "Unknown or expired authoring receipt")
        return deepcopy(found)

    def render(
        self,
        tool: str,
        arguments: JsonObject,
        payload: JsonValue,
        limit: int,
        *,
        resume: AuthoringReceipt | None = None,
    ) -> JsonValue:
        if tool not in AUTHORING_READS:
            fitted, receipt = fit(payload, limit)
            if (
                tool in {"skm_graph_neighbors", "skm_graph_path"}
                and receipt is None
                and not _fits(fitted, limit)
            ):
                raise ValidationFailed(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    "The graph response metadata cannot fit the token budget",
                    details={"tool": tool, "max_response_tokens": limit},
                )
            return fitted
        if not isinstance(payload, dict) or not isinstance(source := payload.get("source"), dict):
            raise ValueError("authoring read must return its source")
        if resume is not None and source != resume.source:
            raise _check_source()
        for argument, field in (
            ("revision_id", "revision_id"),
            ("draft_id", "draft_id"),
            ("expected_edit_version", "edit_version"),
        ):
            if argument in arguments and arguments[argument] != source.get(field):
                raise _check_source()
        skip = 0 if resume is None else resume.skip
        items = payload.get("items")
        if skip:
            if not isinstance(items, list) or skip >= len(items):
                raise _check_source()
            payload = {**payload, "items": items[skip:]}

        key = "next_cursor" if tool == "skm_plan_entities" else "next_offset_bytes"
        position = payload.get(key)
        if position is None and _fits(payload, limit):
            return payload

        token = uuid4().hex
        fitted, truncation = fit({**payload, _RECEIPT_FIELD: token}, limit)
        if (truncation is None and not _fits(fitted, limit)) or (
            truncation is not None and truncation.returned_count == 0
        ):
            raise ValidationFailed(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "The authoring response cannot fit with its continuation receipt",
                details={"tool": tool, "max_response_tokens": limit},
            )
        pinned = _pinned_arguments(arguments, source)
        if truncation is not None:
            receipt = AuthoringReceipt(tool, pinned, source, skip + truncation.returned_count)
        elif position is not None:
            pinned["after" if key == "next_cursor" else "offset_bytes"] = position
            receipt = AuthoringReceipt(tool, pinned, source)
        else:
            return payload
        self._receipts[token] = deepcopy(receipt)
        if len(self._receipts) > _MAX_RECEIPTS:
            self._receipts.popitem(last=False)
        return fitted
