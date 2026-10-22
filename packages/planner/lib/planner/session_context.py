"""Resolve the current provider-neutral session identity fail-closed."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Optional


class SessionContextError(ValueError):
    pass


@dataclass(frozen=True)
class SessionContext:
    provider: str
    session_id: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


Adapter = Callable[[], Optional[SessionContext]]


def _codex_adapter() -> SessionContext | None:
    from planner.session_context_codex import current

    return current()


def _claude_adapter() -> SessionContext | None:
    from planner.session_context_claude import current

    return current()


def _cursor_adapter() -> SessionContext | None:
    from planner.session_context_cursor import current

    return current()


def _grok_adapter() -> SessionContext | None:
    from planner.session_context_grok import current

    return current()


def resolve(*, adapters: Iterable[Adapter] = (
        _codex_adapter, _claude_adapter, _cursor_adapter, _grok_adapter)) -> SessionContext:
    """Return exactly one applicable provider adapter, or reject the write."""
    resolved = [context for adapter in adapters if (context := adapter()) is not None]
    if not resolved:
        raise SessionContextError("session context not found: no applicable provider adapter")
    if len(resolved) != 1:
        raise SessionContextError("session context is ambiguous: exactly one is required provider adapter")
    context = resolved[0]
    if not all(isinstance(value, str) and value.strip()
               for value in (context.provider, context.session_id, context.source)):
        raise SessionContextError("session context is invalid: provider/session_id/source are required")
    return context


def current_json() -> str:
    return json.dumps(resolve().as_dict(), ensure_ascii=False, sort_keys=True)


def current_id() -> str:
    return resolve().session_id
