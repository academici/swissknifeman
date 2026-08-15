"""Locale boundary for Task canonical command sources.

Provider renderers keep consuming the English canonical Markdown.  This module exposes the same
whole-command units to a locale-aware caller without reading provider state or targets.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from core.locale import Catalog, Overlay, render_message


_SCHEMA = "urn:swissknifeman:localized-overlay:v1"
_VERSION = "1.0.0"
_COMMAND_IDS = ("plan-exec", "plan-run")
_PREIMAGE_COMMIT = "980ee79d"
_PREIMAGE_DIGESTS = {
    "plan-exec": "646172c92e6e13b8cddb6af36594f4a24060224d0ceb2c8f981eff9f8c894664",
    "plan-run": "29fbffbeef7eb1cfdb712895978f1dc4a4b48221a1ac4029d9144124299d5828",
}
_CANDIDATE_DIGESTS = {
    "plan-exec": "6f6d7c67a6aebccb8460996b31714710e1ac5e1e3cb3bdaba5f830c02229644c",
    "plan-run": "9f344ebc808083ac4e8d5ee59f402515b71d95b7e5789e839ff8e81698e04942",
}
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```$", re.MULTILINE | re.DOTALL)
_INLINE_RE = re.compile(r"`([^`\n]+)`")
_URL_RE = re.compile(r"https?://[^\s)>]+")
_PATH_RE = re.compile(r"(?<![\w.-])(?:[\w.-]+/)+(?:[\w.-]+)(?:\.[\w.-]+)?")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def command_locale_key(command_id: str) -> str:
    if command_id not in _COMMAND_IDS:
        raise ValueError("CMD_LOCALE_COMMAND_UNKNOWN")
    return f"task.command.{command_id}.body"


def english_catalog(command_root: Path | None = None) -> Catalog:
    root = command_root or Path(__file__).resolve().parents[2] / "commands"
    return Catalog("en", {
        command_locale_key(command_id): (root / f"{command_id}.md").read_text(encoding="utf-8")
        for command_id in _COMMAND_IDS
    })


def _machine_literals(text: str) -> tuple[str, ...]:
    """Collect every ordered machine-bearing Markdown fragment without a hand-picked allowlist."""
    literals: list[tuple[int, str]] = []
    frontmatter = _FRONTMATTER_RE.search(text)
    if frontmatter:
        for match in re.finditer(r"^[A-Za-z][\w-]*:\s*(.+)$", frontmatter.group(1), re.MULTILINE):
            literals.append((frontmatter.start(1) + match.start(1), match.group(1)))
    for pattern in (_INLINE_RE, _FENCE_RE, _URL_RE, _PATH_RE):
        for match in pattern.finditer(text):
            value = match.group(1) if pattern in (_INLINE_RE, _FENCE_RE) else match.group(0)
            literals.append((match.start(), value))
    return tuple(value for _, value in sorted(literals, key=lambda item: item[0]))


def _preimage(command_id: str) -> str:
    result = subprocess.run(
        ("git", "show", f"{_PREIMAGE_COMMIT}:packages/task/commands/{command_id}.md"),
        check=True, capture_output=True, text=True,
    )
    text = result.stdout
    if sha256(text.encode()).hexdigest() != _PREIMAGE_DIGESTS[command_id]:
        raise ValueError("CMD_LOCALE_PREIMAGE_DIGEST_MISMATCH")
    return text


def literal_inventory(text: str, *, command_id: str) -> dict[str, object]:
    """Bind complete ordered preimage and candidate inventories to their source digests."""
    command_id = command_id or ("plan-run" if "task.route_evidence.capture_launch" in text else "plan-exec")
    if command_id not in _COMMAND_IDS:
        raise ValueError("CMD_LOCALE_COMMAND_UNKNOWN")
    if sha256(text.encode()).hexdigest() != _CANDIDATE_DIGESTS[command_id]:
        raise ValueError("CMD_LOCALE_CANDIDATE_DIGEST_MISMATCH")
    preimage = _preimage(command_id)
    return {
        "command_id": command_id,
        "preimage_commit": _PREIMAGE_COMMIT,
        "preimage_sha256": "sha256:" + _PREIMAGE_DIGESTS[command_id],
        "candidate_sha256": "sha256:" + _CANDIDATE_DIGESTS[command_id],
        "preimage_literals": _machine_literals(preimage),
        "candidate_literals": _machine_literals(text),
    }


def immutable_tokens(text: str, *, command_id: str | None = None) -> tuple[str, ...]:
    """Return the complete candidate inventory used when a localized unit is present."""
    command_id = command_id or ("plan-run" if "task.route_evidence.capture_launch" in text else "plan-exec")
    return literal_inventory(text, command_id=command_id)["candidate_literals"]


def load_russian_overlay(path: Path | None = None) -> Overlay:
    overlay_path = path or Path(__file__).resolve().parents[2] / "locales" / "ru.json"
    raw = json.loads(overlay_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "$schema", "contract_version", "locale", "source_catalog_sha256", "units",
    }:
        raise ValueError("CMD_LOCALE_OVERLAY_SCHEMA_INVALID")
    if raw["$schema"] != _SCHEMA or raw["contract_version"] != _VERSION:
        raise ValueError("CMD_LOCALE_OVERLAY_VERSION_UNSUPPORTED")
    if raw["locale"] != "ru" or not isinstance(raw["units"], dict):
        raise ValueError("CMD_LOCALE_OVERLAY_SCHEMA_INVALID")
    units = {}
    for key, unit in raw["units"].items():
        if key not in {command_locale_key(command_id) for command_id in _COMMAND_IDS}:
            raise ValueError("CMD_LOCALE_OVERLAY_SCHEMA_INVALID")
        if not isinstance(unit, dict) or set(unit) != {"source_sha256", "immutable_tokens", "text"}:
            raise ValueError("CMD_LOCALE_OVERLAY_SCHEMA_INVALID")
        if not isinstance(unit["immutable_tokens"], list) or not all(
                isinstance(token, str) and token for token in unit["immutable_tokens"]):
            raise ValueError("CMD_LOCALE_OVERLAY_SCHEMA_INVALID")
        units[key] = {"text": unit["text"]}
    return Overlay("ru", raw["source_catalog_sha256"], units)


def resolve_command(command_id: str, *, locale: str = "en", command_root: Path | None = None,
                    overlay_path: Path | None = None) -> dict[str, object]:
    """Resolve a canonical command as English or its sparse Russian overlay."""
    if locale not in {"en", "ru"}:
        raise ValueError("CMD_LOCALE_UNSUPPORTED")
    catalog = english_catalog(command_root)
    key = command_locale_key(command_id)
    overlay = load_russian_overlay(overlay_path) if locale == "ru" else None
    return render_message(catalog, overlay, key, immutable_tokens=immutable_tokens(catalog.units[key]))


def catalog_sha256(catalog: Catalog) -> str:
    return "sha256:" + sha256(json.dumps(dict(sorted(catalog.units.items())), ensure_ascii=False,
                                         separators=(",", ":")).encode()).hexdigest()
