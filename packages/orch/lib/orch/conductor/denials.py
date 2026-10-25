"""Counts of environment refusals in failed tool results, never in prose or successful tool output.

Only categories and counts leave this module. Error text can contain paths or secrets and is never retained.
Permission refusals keep their existing, separate RESULT_SILENT_DENIAL accounting.
"""
from __future__ import annotations

from collections import Counter
import fnmatch
import re

MASKS = ("skills.json", "*.lock", "package-lock.json", "*.min.js", "*.min.css", "node_modules/*",
         "dist/*", "build/*", "coverage/*", ".venv/*", "__pycache__/*", ".env", ".env.*", "*.pem", "*.key",
         ".ssh/*", ".aws/*")


def _text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(part) for part in value)
    if isinstance(value, dict):
        return _text(value.get("text") or value.get("content") or value.get("message") or "")
    return ""


def _failed(block: dict) -> bool:
    code = block.get("exit_code")
    return block.get("is_error") is True or (type(code) is int and code != 0)


def _errors(event: dict):
    item = event.get("item")
    if event.get("type") == "item.completed" and isinstance(item, dict) \
            and item.get("type") == "command_execution" and _failed(item):
        yield _text(item.get("aggregated_output")), True
    message = event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        blocks = content if isinstance(content, list) and (event.get("type") == "user" or message.get("role") == "tool") else []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "tool_result" and _failed(block):
                yield _text(block.get("content")), False
        if message.get("role") == "tool" and _failed(message):
            yield _text(content), False
    if event.get("type") == "tool_result" or event.get("role") == "tool":
        if _failed(event):
            yield _text(event.get("content") or event.get("output")), False


def _masked(text: str) -> bool:
    paths = re.findall(r"([^\s:'\"<>]+): Permission denied", text)
    paths += re.findall(r"Permission denied: ['\"]([^'\"]+)['\"]", text)
    return any(fnmatch.fnmatch(path.lstrip("/"), mask) or fnmatch.fnmatch(path.rsplit("/", 1)[-1], mask)
               or fnmatch.fnmatch(path, "*/" + mask) for path in paths for mask in MASKS)


def _kind(text: str, codex: bool, guard: str) -> str | None:
    low = text.lower()
    if re.search(r"(?m)^bwrap:", text):
        return "bwrap"
    if "LANDLOCK_" in text or (guard.startswith("landlock-") and "Operation not permitted" in text):
        return "landlock"
    if codex and (("sandbox" in low and "denied" in low) or ("/tmp/.git" in low and "read-only" in low)):
        return "codex_sandbox"
    if ("unsupported file type" in low and "cannot hash" in low) or "is a character device" in low or _masked(text):
        return "read_mask"
    if any(part in low for part in ("allowed_domains cannot widen network access", "temporary failure in name resolution",
                                   "could not resolve host", "network is unreachable")):
        return "network"
    if "read-only file system" in low:
        return "erofs"
    if "EACCES" in text or "Permission denied" in text:
        return "eacces"
    return None


def classify(transport: str, events) -> dict[str, int]:
    """One count per failed tool result matching an environment error form (most specific category wins).

    ``orch.guard`` is trusted context supplied by the process launcher, not a provider's final answer.
    An unstructured terminal error, a command input and code read by a successful tool prove no refusal.
    """
    if transport != "jsonl":
        return {}
    events = list(events)
    guard = next((event.get("guard", "") for event in events if event.get("type") == "orch.guard"), "")
    found: Counter = Counter()
    for event in events:
        for text, codex in _errors(event):
            kind = _kind(text, codex, guard)
            if kind:
                found[kind] += 1
    return dict(sorted(found.items()))
