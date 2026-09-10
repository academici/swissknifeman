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
    "plan-exec": "84a60b9857934e61750b5df3d0e25cf97cee9ab713e3e866fa47c7fc04c6bde4",
    "plan-run": "207fc5b95d404e21cbd955fd306342ab1bfec6d5491d8b806026a998bcb9c685",
}
# Markdown permits up to three leading spaces on a fenced-code delimiter.  Command
# sources use that form inside ordered lists, so matching only column-zero fences
# silently discarded executable fragments from the inventory.
_FENCE_RE = re.compile(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE_RE = re.compile(r"`([^`\n]+)`")
_URL_RE = re.compile(r"https?://[^\s)>]+")
_PATH_RE = re.compile(r"(?<![\w.-])(?:[\w.-]+/)+(?:[\w.-]+)(?:\.[\w.-]+)?")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_COMMAND_RE = re.compile(r"(?<![\w.-])(?:PYTHONPATH=\S+\s+)?(?:python3|codex|git|bash|make|npm)\b[^\n`]*")
_ID_RE = re.compile(r"\b(?:task:[\w:-]+|P\d+\.\d+|D\d+|[A-Z][A-Z0-9_]{2,}|v\d+(?:\.\d+){0,2})\b")
_KEY_RE = re.compile(r"\b[a-z][a-z0-9_]*(?==)")
_PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
_EXPECTED_INVENTORIES = {
    # Generated from git:980ee79d plus the D80 replacement source.  Each digest
    # binds the full typed sequence, including order and multiplicity.
    "plan-exec": {
        "preimage": "sha256:4ab5a60b17f011d0ae6f6a4da4548d7362010a0e5e998a571cac08dd4870dd73",
        "candidate": "sha256:ada61b1720b715f048acf89c5cbd4c75fe6c8bcdf6e32f5a312e28df481b4ead",
    },
    "plan-run": {
        "preimage": "sha256:476951e51315cfbcca269206edcccf19fc32e90de8c0dd3a4656194a23392082",
        "candidate": "sha256:0132d933226b09e252ab2effd0b99810653b2e169b2806b15659210c7ac55f60",
    },
}


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


def _machine_literals(text: str) -> tuple[tuple[str, str], ...]:
    """Collect the complete ordered, typed machine-bearing Markdown inventory."""
    literals: list[tuple[int, int, str, str]] = []

    def collect(kind: str, pattern: re.Pattern[str], group: int = 0, priority: int = 10):
        for match in pattern.finditer(text):
            literals.append((match.start(), priority, kind, match.group(group)))

    frontmatter = _FRONTMATTER_RE.search(text)
    if frontmatter:
        for match in re.finditer(r"^[A-Za-z][\w-]*:\s*(.+)$", frontmatter.group(1), re.MULTILINE):
            literals.append((frontmatter.start(1) + match.start(1), 0, "frontmatter-value", match.group(1)))
    collect("inline-code", _INLINE_RE, group=1, priority=1)
    collect("fenced-code", _FENCE_RE, group=1, priority=2)
    collect("url", _URL_RE, priority=3)
    collect("path", _PATH_RE, priority=4)
    collect("command", _COMMAND_RE, priority=5)
    collect("identifier", _ID_RE, priority=6)
    collect("key", _KEY_RE, priority=7)
    collect("placeholder", _PLACEHOLDER_RE, priority=8)
    return tuple((kind, value) for _, _, kind, value in sorted(literals))


def _inventory_sha256(entries: tuple[tuple[str, str], ...]) -> str:
    encoded = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def _is_protected_preimage_literal(kind: str, value: str) -> bool:
    """Select immutable command-contract atoms from the frozen preimage.

    The complete inventory intentionally also records prose-adjacent code spans so
    that a source rewrite is auditable.  Only this narrower, source-derived subset
    is required to survive the compact-English rewrite: command identities,
    provider/route identifiers, parser and action/diagnostic codes, and canonical
    Task paths.  The rule is independent of the candidate and therefore cannot be
    weakened by omitting a value in the new source.
    """
    if value.startswith("task.") and "(" in value:
        return True
    if value in {
        "sonnet", "medium", "model", "effort", "plan-exec", "plan-design",
        "manual", "allow", "delegated", "approval_required", "denied", "local-repair",
        "block-candidate", "terminal-block", "routing-rejected", "ROUTE-UNVERIFIABLE",
        "ROUTING-INCONSISTENT", "PLAN_LAYOUT_V1_RETIRED",
        "LOOP_BUDGET_EXCEEDED", "JUSTIFIED", "CAPABILITY_UNSUPPORTED", "COLD_START_INCOMPLETE",
        "PORTABILITY_EXTERNAL_INPUT", "PORTABILITY_INPUT_MISSING", "VERSION_HASH_MISMATCH",
        "CONFLICT_UNRESOLVED", "CONFLICT_PRECEDENCE_VIOLATION", "NEXT_CHANGED_WITHOUT_TRANSITION",
        "SLICE_INCOMPLETE", "block-confirmation:v1", "isolated-child-return", "DecisionRequest",
    }:
        return True
    if kind == "frontmatter-value" and value in {"sonnet", "medium"}:
        return True
    return False


def _preserves_protected_literals(
        expected: tuple[tuple[str, str], ...], actual: tuple[tuple[str, str], ...],
) -> bool:
    """Require every immutable atom from the preimage to remain in the candidate.

    Order and multiplicity of the complete inventories are pinned separately by
    their source hashes.  The semantic compacting step may move an atom, but may
    not drop it or invent a replacement spelling.
    """
    return set(expected).issubset(set(actual))


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
    preimage = _preimage(command_id)
    inventory = {
        "command_id": command_id,
        "preimage_commit": _PREIMAGE_COMMIT,
        "preimage_sha256": "sha256:" + _PREIMAGE_DIGESTS[command_id],
        "candidate_sha256": "sha256:" + sha256(text.encode()).hexdigest(),
        "preimage_literals": _machine_literals(preimage),
        "candidate_literals": _machine_literals(text),
    }
    inventory["protected_preimage_literals"] = tuple(
        literal for literal in inventory["preimage_literals"]
        if _is_protected_preimage_literal(*literal)
    )
    inventory["preimage_inventory_sha256"] = _inventory_sha256(inventory["preimage_literals"])
    inventory["candidate_inventory_sha256"] = _inventory_sha256(inventory["candidate_literals"])
    return inventory


def verify_literal_inventory(text: str, *, command_id: str) -> dict[str, object]:
    """Reject any omitted, reordered, multiplied, or unclassified literal sequence."""
    inventory = literal_inventory(text, command_id=command_id)
    expected = _EXPECTED_INVENTORIES[command_id]
    if (inventory["candidate_sha256"] != "sha256:" + _CANDIDATE_DIGESTS[command_id]
            or inventory["preimage_inventory_sha256"] != expected["preimage"]
            or inventory["candidate_inventory_sha256"] != expected["candidate"]
            ):
        raise ValueError("CMD_LOCALE_LITERAL_INVENTORY_MISMATCH")
    return inventory


def immutable_tokens(text: str, *, command_id: str | None = None) -> tuple[str, ...]:
    """Return the complete candidate inventory used when a localized unit is present."""
    command_id = command_id or (
        "plan-run" if "canonical `task:plan-exec` lifecycle" in text else "plan-exec")
    return tuple(value for _, value in verify_literal_inventory(text, command_id=command_id)["candidate_literals"])


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
