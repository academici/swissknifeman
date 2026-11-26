"""Fit knowledge responses to a context budget using compact JSON and a receipt."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from skm.kernel.json_types import JsonObject, JsonValue

_HINT = "response truncated by context limit; narrow your request (query/depth/project)"


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


def estimate_tokens_json(text: str) -> int:
    return math.ceil(len(text) / 3.2)


def _compact(payload: JsonValue) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _largest_list(payload: JsonValue) -> tuple[str | None, list[JsonValue]] | None:
    if isinstance(payload, list) and payload:
        return None, payload
    if isinstance(payload, dict):
        lists = ((key, value) for key, value in payload.items() if isinstance(value, list) and value)
        return max(lists, key=lambda pair: len(_compact(pair[1])), default=None)
    return None


def truncate_largest_list(
    payload: JsonValue, limit_tokens: int = 10_000, *, is_error: bool = False
) -> JsonValue:
    if is_error or estimate_tokens_json(_compact(payload)) <= limit_tokens:
        return payload
    largest = _largest_list(payload)
    if largest is None:
        return payload
    key, items = largest
    if isinstance(payload, dict) and f"{key}_truncated" in payload:
        return payload

    def trimmed(count: int) -> JsonObject:
        receipt = TruncationReceipt(count, len(items)).to_json()
        if key is not None and isinstance(payload, dict):
            return {**payload, key: items[:count], f"{key}_truncated": receipt}
        return {"items": items[:count], **receipt}

    best = trimmed(0)
    if estimate_tokens_json(_compact(best)) > limit_tokens:
        return payload
    lo, hi = 1, len(items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = trimmed(mid)
        if estimate_tokens_json(_compact(candidate)) <= limit_tokens:
            best, lo = candidate, mid + 1
        else:
            hi = mid - 1
    return best
