"""Locale boundary for Task canonical command sources.

Provider renderers keep consuming the English canonical Markdown.  This module exposes the same
whole-command units to a locale-aware caller without reading provider state or targets.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from core.locale import Catalog, Overlay, render_message


_SCHEMA = "urn:swissknifeman:localized-overlay:v1"
_VERSION = "1.0.0"
_COMMAND_IDS = ("plan-exec", "plan-run")
_PLAN_EXEC_TOKENS = (
    "task.plan_authority.authorize()", "task.plan_blocking.evaluate()",
    "task.journal.derive_run_id(plan_id=plan_id, item_id=item_id, attempt=attempt, session_id=session_id)",
    "task.validation_admission.local_repair_decision(report)",
)
_PLAN_RUN_TOKENS = (
    'task.command_catalog.package_command_path("task:plan-exec")',
    "task.route_evidence.capture_launch",
    "task.route_evidence.build_run_receipt(...)", "task.route_evidence.start_decision(receipt)",
    "verify_run_receipt(..., current_evidence=<fresh>)",
    "task.journal.derive_run_id(plan_id=plan_id, item_id=item_id, attempt=attempt, session_id=session_id)",
)


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


def immutable_tokens(text: str) -> tuple[str, ...]:
    """Return the complete owner-declared execution literals for one command unit."""
    return _PLAN_RUN_TOKENS if "task.route_evidence.capture_launch" in text else _PLAN_EXEC_TOKENS


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
