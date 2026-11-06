"""Normalize provider token counters and describe Codex session accounting."""
from __future__ import annotations


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def normalize(found: object) -> dict:
    if not isinstance(found, dict):
        return {"input": 0, "cached": 0, "output": 0}
    def count(*keys: str) -> int:
        return sum(found[key] for key in keys if is_int(found.get(key)) and found[key] >= 0)
    # Codex/OpenAI includes cache reads in input_tokens; invalid counts are ignored.
    cached = found.get("cached_input_tokens")
    if is_int(cached):
        cached = count("cached_input_tokens")
        return {"input": max(0, count("input_tokens") - cached), "cached": cached, "output": count("output_tokens")}
    return {"input": count("input_tokens", "cache_creation_input_tokens"),
            "cached": count("cache_read_input_tokens"), "output": count("output_tokens")}


def codex_accounting(native: object, session: str | None) -> dict:
    accounting = {"basis": "codex-session-cumulative"}
    if session:
        accounting["counter_id"] = "codex:" + str(session)
    else:
        accounting["unavailable"] = "Codex cumulative usage has no session identity"
    if (not isinstance(native, dict) or any(not is_int(native.get(key)) or native[key] < 0
            for key in ("input_tokens", "cached_input_tokens", "output_tokens"))
            or native["cached_input_tokens"] > native["input_tokens"]):
        accounting["unavailable"] = "Codex input/cache counters are missing or inconsistent"
    return accounting
