"""Optional explicit reviewer selection, independent of the plan storage format.

Derived from main's review_packet selector contract. Parsing chooses a route;
it neither starts a reviewer nor attests that the selected session ran.
"""
from __future__ import annotations

import re
import shlex

from planner import COMMAND_NAMESPACE

_REVIEW_ONLY_COMMANDS = frozenset(f"{COMMAND_NAMESPACE}:{name}" for name in ("review", "plan-audit"))
_REVIEW_COMMANDS = _REVIEW_ONLY_COMMANDS | frozenset(
    f"{COMMAND_NAMESPACE}:{name}" for name in ("plan-run", "dev", "design", "make-workflow"))
_SELECTOR = re.compile(r"^(claude-code|codex|cursor|grok|antigravity)/([A-Za-z0-9][A-Za-z0-9._:-]*)$")


class ReviewError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def reviewer(selector: str) -> dict:
    parts = (selector or "").strip().rstrip("/").split("/")
    match = _SELECTOR.fullmatch("/".join(parts[:2]))
    if not match:
        raise ReviewError("REVIEWER_REQUIRED", "use provider/model[/context][/effort], with an exact model ID")
    result = {"provider": match[1], "model": match[2]}
    for raw in parts[2:]:
        token = raw.lower()
        if token == "hight":
            token = "high"
        if token in {"low", "medium", "high", "xhigh"} and "effort" not in result:
            result["effort"] = token
        elif re.fullmatch(r"[1-9][0-9]*[km]?", token) and "context_tokens" not in result:
            count = int(token.rstrip("km")) * (1000 if token.endswith("k") else 1_000_000 if token.endswith("m") else 1)
            if count > 2**63 - 1:
                raise ReviewError("REVIEW_ROUTE_INVALID", "context window is too large")
            result["context_tokens"] = count
        else:
            raise ReviewError("REVIEW_ROUTE_INVALID", "use one context size (500k, 1m, 500000) and/or one effort (low, medium, high, xhigh)")
    return result


def canonical_selector(selector: str) -> str:
    selected = reviewer(selector)
    # Effort is its own durable axis; suffix and --effort spellings are equivalent.
    return (f"{selected['provider']}/{selected['model']}"
            + (f"/{selected['context_tokens']}" if "context_tokens" in selected else ""))


def selected_effort(selector: str, effort: str | None, *, default: str = "high") -> str:
    suffix = reviewer(selector).get("effort")
    explicit = ("high" if effort.lower() == "hight" else effort.lower()) if effort is not None else None
    if suffix and explicit and suffix != explicit:
        raise ReviewError("REVIEW_ROUTE_MISMATCH", "effort suffix conflicts with the explicit effort argument")
    value = explicit or suffix or default
    if value not in {"low", "medium", "high", "xhigh"}:
        raise ReviewError("REVIEW_ROUTE_INVALID", "unknown review effort")
    return value


def invocation_selection(invocation: str) -> dict | None:
    """An omitted selector inherits the captured native review session route."""
    invocation = invocation.removeprefix("$ ").removeprefix("/")
    try:
        tokens = shlex.split(invocation)
    except ValueError as exc:
        raise ReviewError("REVIEW_INVOCATION_INVALID", "malformed review arguments") from exc
    if not tokens or tokens[0] not in _REVIEW_COMMANDS:
        return None
    selections, efforts = [], []
    for index, token in enumerate(tokens[1:], 1):
        for name, values in (("--reviewer", selections), ("--effort", efforts), ("--review-effort", efforts)):
            if token == name:
                if index + 1 >= len(tokens):
                    raise ReviewError("REVIEW_INVOCATION_INVALID", f"missing {name} value")
                values.append(tokens[index + 1])
            elif token.startswith(name + "="):
                values.append(token.split("=", 1)[1])
    if len(selections) > 1 or len(efforts) > 1:
        raise ReviewError("REVIEW_INVOCATION_INVALID", "reviewer and effort may be specified only once")
    if not selections:
        if efforts and efforts[0] not in {"low", "medium", "high", "hight", "xhigh"}:
            raise ReviewError("REVIEW_ROUTE_INVALID", "unknown review effort")
        if tokens[0] not in _REVIEW_ONLY_COMMANDS and "--review" not in tokens[1:]:
            # A depth option alone never authorizes an executor to start review.
            return None
        return {"effort": "high" if efforts == ["hight"] else efforts[0]} if efforts else None
    selected = reviewer(selections[0])
    selected["effort"] = selected_effort(selections[0], efforts[0] if efforts else None,
                                         default="xhigh" if tokens[0] == f"{COMMAND_NAMESPACE}:plan-audit" else "high")
    return selected

