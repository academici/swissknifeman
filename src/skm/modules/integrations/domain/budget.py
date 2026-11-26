"""Five-source resident first-turn estimates, never actual token usage (integrations §5.7)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from skm.kernel.json_types import JsonObject, JsonValue

from .merged_toml import parse_toml
from .target import TargetId

__all__ = [
    "FirstTurnSource",
    "FirstTurnSourceKind",
    "FirstTurnVerdict",
    "estimate_tokens",
    "first_turn_sources",
    "first_turn_verdict",
    "frontmatter_field",
    "source_total",
]


class FirstTurnSourceKind(StrEnum):
    SKILLS = "skills"
    AGENTS = "agents"
    INSTRUCTIONS = "instructions"
    HOOKS = "hooks"
    MCP = "mcp"


@dataclass(frozen=True, slots=True)
class FirstTurnSource:
    kind: FirstTurnSourceKind
    tokens: int | None
    method: str
    detail: Mapping[str, JsonValue]


class FirstTurnVerdict(StrEnum):
    OK = "ok"
    ELEVATED = "elevated"
    WARN = "warn"
    INCOMPLETE = "incomplete"


def estimate_tokens(text: str) -> int:
    """Unicode heuristic inherited from the budget contract; empty text costs zero."""
    cyr = sum(1 for char in text if "\u0400" <= char <= "\u04ff" or "\u0500" <= char <= "\u052f")
    return math.ceil(cyr / 2.9 + (len(text) - cyr) / 3.4)


def first_turn_verdict(total: int | None, *, target: int, warn: int) -> FirstTurnVerdict:
    if target > warn:
        raise ValueError("integrations.budget_order: target must not exceed warn")
    if total is None:
        return FirstTurnVerdict.INCOMPLETE
    if total <= target:
        return FirstTurnVerdict.OK
    return FirstTurnVerdict.ELEVATED if total <= warn else FirstTurnVerdict.WARN


def source_total(sources: Sequence[FirstTurnSource]) -> int | None:
    return (
        None
        if any(source.tokens is None for source in sources)
        else sum(source.tokens or 0 for source in sources)
    )


def frontmatter_field(text: str, key: str) -> str | None:
    """Read native string metadata without executing YAML tags or loading an agent body."""
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    header = lines[1 : lines.index("---", 1)]
    for index, line in enumerate(header):
        match = re.fullmatch(re.escape(key) + r":\s*(.*)", line)
        if match is None:
            continue
        value = match.group(1).strip()
        if value in (">", ">-", "|", "|-"):
            parts: list[str] = []
            for continuation in header[index + 1 :]:
                if continuation and not continuation[0].isspace():
                    break
                parts.append(continuation.strip())
            return ("\n" if value.startswith("|") else " ").join(parts)
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
            except ValueError:
                return None
            return decoded if isinstance(decoded, str) else None
        if value.startswith("'"):
            return value[1:-1].replace("''", "'") if value.endswith("'") else None
        return value
    return None


def _detail(texts: Mapping[str, str | None]) -> JsonObject:
    return {
        "estimator": "heuristic:cyr/2.9+other/3.4",
        "estimated": True,
        "files": list(texts),
        "digests": {
            path: "sha256:" + hashlib.sha256(text.encode()).hexdigest()
            for path, text in texts.items()
            if text is not None
        },
        "unmeasurable": [path for path, text in texts.items() if text is None],
    }


def _listing_source(
    target: TargetId,
    skills: Mapping[str, str | None],
    *,
    fraction: float,
    window: int,
) -> FirstTurnSource:
    entries: list[str] = []
    missing: list[str] = []
    for path, text in skills.items():
        name = None if text is None else frontmatter_field(text, "name")
        description = None if text is None else frontmatter_field(text, "description")
        if name is None or description is None:
            missing.append(path)
        else:
            entries.append((name + ": " + description)[:1536])
    native_tokens = sum(estimate_tokens(entry) for entry in entries)
    budget_tokens = math.floor(fraction * window)
    char_budget = 8000
    is_native = target is TargetId.CLAUDE_CODE
    tokens = (
        min(native_tokens, budget_tokens) if is_native else estimate_tokens("\n".join(entries)[:char_budget])
    )
    detail = _detail(skills)
    detail.update(
        cast(
            "JsonObject",
            {
                "skills": len(skills),
                "listing_chars": sum(map(len, entries)),
                "listing_budget_tokens": budget_tokens,
                "listing_budget_chars": math.floor(budget_tokens * 3.4) if is_native else char_budget,
                "unmeasurable": missing,
            },
        )
    )
    return FirstTurnSource(
        FirstTurnSourceKind.SKILLS,
        None if missing else tokens,
        "listing_entry_tokens" if is_native else "listing characters",
        detail,
    )


def _agents_source(agents: Mapping[str, str | None]) -> FirstTurnSource:
    descriptions: list[str | None] = []
    for path, text in agents.items():
        description = None
        if text is not None and path.endswith(".toml"):
            try:
                value = parse_toml(text).get("description")
            except ValueError:
                value = None
            if isinstance(value, str):
                description = value
        elif text is not None:
            description = frontmatter_field(text, "description")
        descriptions.append(description)
    tokens = (
        None
        if any(text is None for text in descriptions)
        else sum(estimate_tokens(text) for text in descriptions if text is not None)
    )
    detail = _detail(agents)
    detail["agents"] = len(agents)
    detail["unmeasurable"] = [path for path, value in zip(agents, descriptions, strict=True) if value is None]
    return FirstTurnSource(FirstTurnSourceKind.AGENTS, tokens, "frontmatter_description", detail)


def _mcp_source(servers: Mapping[str, JsonObject] | None, *, deferred: bool) -> FirstTurnSource:
    total = 0
    facts: JsonObject = {}
    if servers is not None:
        for name, server in sorted(servers.items()):
            if server.get("enabled") is False:
                continue
            tools = server.get("tool_count")
            configured = isinstance(tools, int) and not isinstance(tools, bool) and tools >= 0
            count = tools if isinstance(tools, int) and not isinstance(tools, bool) and tools >= 0 else 5
            instructions = server.get("instructions")
            instruction_tokens = estimate_tokens(instructions) if isinstance(instructions, str) else 40
            total += int(count) * (24 if deferred else 150) + instruction_tokens
            facts[name] = {
                "tools": count,
                "instructions_tokens": instruction_tokens,
                "tool_count_source": "integrations.mcp.servers." + name + ".tool_count"
                if configured
                else "fallback",
            }
    return FirstTurnSource(
        FirstTurnSourceKind.MCP,
        None if servers is None else total,
        "tools * 24 + instructions" if deferred else "tools * 150 + instructions",
        {"servers": facts, "deferred_tool_search": deferred, "estimated": True, "estimator": "mcp-tools-v1"},
    )


def first_turn_sources(  # noqa: PLR0913 - five sources and target-specific estimator parameters
    *,
    target: TargetId,
    skills: Mapping[str, str | None],
    agents: Mapping[str, str | None],
    instructions: Mapping[str, str | None],
    session_start_template: str | None,
    mcp_servers: Mapping[str, JsonObject] | None,
    listing_fraction: float = 0.01,
    context_window: int = 1_000_000,
    deferred_tool_search: bool = False,
) -> tuple[FirstTurnSource, ...]:
    """Value all five sources, preserving partial native observations as unknown."""
    instruction_tokens = (
        None
        if any(text is None for text in instructions.values())
        else sum(estimate_tokens(text) for text in instructions.values() if text is not None)
    )
    detail = _detail(instructions)
    detail["chars"] = sum(len(text) for text in instructions.values() if text is not None)
    detail["cyrillic_chars"] = sum(
        1
        for text in instructions.values()
        if text is not None
        for char in text
        if "\u0400" <= char <= "\u052f"
    )
    hooks = FirstTurnSource(
        FirstTurnSourceKind.HOOKS,
        None if session_start_template is None else estimate_tokens(session_start_template),
        "session_start template",
        {
            "run_hooks": False,
            "estimated": True,
            "estimator": "heuristic:cyr/2.9+other/3.4",
            "chars": None if session_start_template is None else len(session_start_template),
            "template_digest": None
            if session_start_template is None
            else "sha256:" + hashlib.sha256(session_start_template.encode()).hexdigest(),
        },
    )
    return (
        _listing_source(target, skills, fraction=listing_fraction, window=context_window),
        _agents_source(agents),
        FirstTurnSource(
            FirstTurnSourceKind.INSTRUCTIONS, instruction_tokens, "estimate_tokens(whole file)", detail
        ),
        hooks,
        _mcp_source(mcp_servers, deferred=deferred_tool_search),
    )
