#!/usr/bin/env python3
"""P1.1 — effective identity/ownership/capability inventory (stdlib-only).

Four named modes, one responsibility each:

* ``--capture-observed PATH`` — the ONLY read-only capture mode.  It records what
  the declared per-provider read-only commands return.  A provider whose enabled
  set cannot be read is recorded ``unknown``; it is never green and never narrows
  anything silently.
* generation (``--observed-state``/``--provenance-note``/``--output``/
  ``--remediation``/``--bootstrap-map``) — writes the effective inventory, the
  owner map of every measured collision and the class-A repository-bootstrap map.
* ``--check-bootstrap-map PATH`` — the deterministic read-only acceptance gate of
  D34/D38 (exact set equality, not key presence).
* ``--check-collision-owners PATH`` — every measured collision must name an owner
  item; a collision without one is a hard failure of P1.1, not a warning.

Collision detection is **repo-derived and cold** (D44): the authoritative carrier
set of an identity is computed from repository sources only — every publishable
unit declared in a provider's repository marketplace (worst case: any unit may be
enabled) plus every root projection of that provider.  The committed prose
``artifacts/source-evidence/runtime/effective-runtime-inventory.json`` is
provenance only: its counters are cross-checked where parseable and otherwise
classified ``pinned-not-recomputable``.  It is never the diff source, and the
observed capture may corroborate the repo-derived set but can never remove a
collision from it.
"""
from __future__ import annotations

import argparse
import collections
import datetime as _datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_INVENTORY = "effective-inventory/v1"
SCHEMA_BEFORE_STATE = "effective-runtime-before-state/v1"
SCHEMA_REMEDIATION = "remediation-map/v1"
SCHEMA_BOOTSTRAP = "repository-bootstrap-map/v1"

# --- Provider declarations (repository-derived inputs only) -------------------
PROVIDERS = {
    "claude-code": {
        "marketplace": ".claude-plugin/marketplace.json",
        "roots": ".claude/skills",
        "plugin_manifest": ".claude-plugin/plugin.json",
        # No read-only command publishes the Claude enabled set; the plan carries
        # this as named debt (plan.md §10), so the capture records `unknown`.
        "enabled_command": (),
    },
    "codex": {
        "marketplace": ".agents/plugins/marketplace.json",
        "roots": ".agents/skills",
        "plugin_manifest": ".codex-plugin/plugin.json",
        "enabled_command": ("codex", "plugin", "list", "--json"),
    },
}
MARKETPLACE_NAME = "swissknifeman"

# --- Frozen class-A repository-bootstrap set (D31/D38) ------------------------
CLASS_A_IDENTITIES = (
    "cross-project-optimizer",
    "decision-verification",
    "docs-maintenance",
    "ecosystem-integration",
    "ecosystem-mcp",
    "ecosystem-setup",
    "field-feedback-loop",
    "harness-operations",
    "maind-overview",
    "package-architecture",
    "project-tooling-runbook",
    "release-discipline",
    "skill-authoring",
)
BOOTSTRAP_CONTENT_VERSION = "0.1.0"
BOOTSTRAP_UNIT = "repository-bootstrap@0.1.0"
BOOTSTRAP_GENERATOR = ("packages/skiller/lib/skiller/registry.py"
                       "→packages/skiller/lib/skiller/publication.py")
BOOTSTRAP_LOCK = "packages/skiller/adapters/repository-bootstrap/publication-lock.json"
BOOTSTRAP_BUCKET = "packages/skiller/skills/repository-bootstrap"
BOOTSTRAP_RECORD_KEYS = frozenset({
    "identity", "seeds", "resolution", "canonical", "projections",
    "canonical_content_version", "publication_unit", "generator", "lock_path",
})
SEED_PROVIDERS = ("claude", "codex")
SEED_ROOTS = {"claude": ".claude/skills", "codex": ".agents/skills"}

# --- Class-B root-bootstrap record (D43) --------------------------------------
CLASS_B_IDENTITY = "workflow-craft"
CLASS_B_CANONICAL = "packages/skiller/skills/general/workflow-craft/SKILL.md"
CLASS_B_UNIT = "repository-bootstrap@0.2.0"
CLASS_B_PROJECTION = ".agents/skills/workflow-craft/SKILL.md"

# Declared enabled-unit literal used for the enabled-conditioned regression view.
# Provenance: findings/12-effective-collision-remeasure.md § "Observed runtime
# (2026-07-25)" — one read-only `codex plugin list --json`, cwd = repository root.
# It is a measurement INPUT; every count below is derived from it, never pinned.
DECLARED_ENABLED = {
    "codex": (
        "architect", "axioma", "core", "creative", "devops", "finance", "founder",
        "laravel-auth", "laravel-data-layer", "laravel-testing", "legal",
        "marketing", "operator", "php", "php-packages", "pm", "quality",
        "research", "roles", "sales", "skm", "system", "task",
    ),
}

# --- Frozen owner map of the measured collision surface (D40–D43) -------------
# Six colliding root core adapters (P1.2), six root task adapters (P1.3), four
# root `architect` adapters plus the class-B carrier and the D42 mutual-exclusion
# detector (P1.5).  `unit-vs-unit` is always the D42 diagnostic, never a profile
# write: the plan does not change the user-owned enabled set.
ROOT_OWNERS = {
    "anti-drift": "P1.2", "context-economy": "P1.2", "plan-protocol": "P1.2",
    "query-craft": "P1.2", "session-handoff": "P1.2", "verify-claims": "P1.2",
    "task-design": "P1.3", "task-plan-audit": "P1.3", "task-plan-close": "P1.3",
    "task-plan-design": "P1.3", "task-plan-exec": "P1.3", "task-plan-run": "P1.3",
    "architecture": "P1.5", "codebase-design": "P1.5", "domain-modeling": "P1.5",
    "package-contribution-protocol": "P1.5",
    CLASS_B_IDENTITY: "P1.5",
}
ROOT_ACTIONS = {
    "P1.2": ("delete-root-projection",
             "installed generated `core` bundle is authoritative; the root copy is "
             "deleted only after the generated bundle/marketplace proof"),
    "P1.3": ("delete-root-projection",
             "installed generated `task` bundle is authoritative; the root copy is "
             "deleted only after the generated bundle/marketplace proof"),
    "P1.5": ("delete-root-projection",
             "installed generated `architect` unit is authoritative; the root copy is "
             "deleted only after per-identity ownership proof"),
}
UNIT_VS_UNIT_OWNER = "P1.5"
UNIT_VS_UNIT_ACTION = (
    "diagnose-mutual-exclusion",
    "curated `core` physically copies donor-bucket identities, so `core` and its "
    "donor buckets (`general`, `research`, `oss-dev`) are mutually exclusive "
    "publications (D42); the detector emits owner/enabled pair/safe Owner action "
    "and never writes the user-owned enabled set",
)
CLASS_B_ACTION = (
    "generate-class-b-root-bootstrap",
    "public-bucket canon whose unit is not enabled: P1.5 gives it a generated thin "
    "Codex projection with provenance/hash under `repository-bootstrap@0.2.0`; "
    "deletion is rejected because the only legal restoration path (enabling "
    "`general`) is forbidden by the D42 invariant",
)

# --- Frozen version ledger and owner path sets (D27, five baseline owners) ----
VERSION_LEDGER = (
    {"owner_item": "P1.2", "unit": "skiller package API",
     "carrier": "packages/skiller/package.json", "from": "0.4.0", "to": "0.4.1"},
    {"owner_item": "P1.2", "unit": "core", "carrier": "publication-unit", "from": "0.4.0", "to": "0.4.1"},
    {"owner_item": "P1.2", "unit": "skm", "carrier": "publication-unit", "from": "0.4.0", "to": "0.4.1"},
    {"owner_item": "P1.2", "unit": "repository-bootstrap", "carrier": "publication-unit",
     "from": "absent", "to": "0.1.0"},
    {"owner_item": "P1.3", "unit": "task plugin/routing", "carrier": "plugin_version",
     "from": "0.3.0", "to": "0.3.1"},
    {"owner_item": "P1.3", "unit": "harness package",
     "carrier": "packages/harness/package.json", "from": "0.2.0", "to": "0.3.0"},
    {"owner_item": "P1.3", "unit": "harness plugin",
     "carrier": "packages/harness/.claude-plugin/plugin.json", "from": "0.1.0", "to": "0.2.0"},
    {"owner_item": "P1.5", "unit": "skiller package API",
     "carrier": "packages/skiller/package.json", "from": "0.4.1", "to": "0.4.2"},
    {"owner_item": "P1.5", "unit": "repository-bootstrap", "carrier": "publication-unit",
     "from": "0.1.0", "to": "0.2.0"},
    {"owner_item": "P2.2", "unit": "plan-protocol skill canon",
     "carrier": "packages/skiller/skills/general/plan-protocol/SKILL.md",
     "from": "2.11.0", "to": "2.12.0"},
    {"owner_item": "P2.2", "unit": "skiller package API",
     "carrier": "packages/skiller/package.json", "from": "0.4.2", "to": "0.5.0"},
    {"owner_item": "P2.2", "unit": "general", "carrier": "publication-unit",
     "from": "0.4.1", "to": "0.5.0"},
    {"owner_item": "P2.2", "unit": "core", "carrier": "publication-unit",
     "from": "0.4.1", "to": "0.5.0"},
    {"owner_item": "P2.2", "unit": "task plugin/routing", "carrier": "plugin_version",
     "from": "0.3.1", "to": "0.4.0"},
    {"owner_item": "P2.3", "unit": "task plugin/routing", "carrier": "plugin_version",
     "from": "0.4.0", "to": "0.5.0"},
)
# Units that must stay byte-identical while a named owner publishes (D27).
BYTE_IDENTICAL_GUARDS = (
    {"owner_item": "P1.5", "unit": "repository-bootstrap class-A payload",
     "rule": "the 13 class-A canonical sources, their 26 projections and their lock "
             "bytes stay byte-identical while P1.5 adds the class-B record"},
    {"owner_item": "P2.2", "unit": "repository-bootstrap",
     "rule": "stays 0.2.0 and byte-identical"},
)

OWNER_PATHS = {
    "P1.2": (
        "packages/skiller/buckets.json",
        "packages/skiller/skills/repository-bootstrap/",
        ".claude/skills/",
        ".agents/skills/",
        "packages/skiller/package.json",
        "packages/skiller/configs/publication-versions.json",
        "packages/skiller/configs/repository-bootstrap-skills.json",
        "packages/skiller/lib/skiller/publication.py",
        "packages/skiller/lib/skiller/registry.py",
        "packages/skiller/lib/skiller/skillset.py",
        "packages/skiller/lib/skiller/doctor.py",
        "packages/skiller/lib/skiller/lock.py",
        "packages/skiller/adapters/repository-bootstrap/publication-lock.json",
        "packages/skiller/adapters/codex/core/",
        "packages/skiller/adapters/codex/skm/",
        "packages/skiller/skills.json",
        "packages/skiller/skills/_index.md",
        "packages/skiller/docs/guide/graph.md",
        "packages/skiller/docs/guide/budget.md",
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        "packages/skiller/tests/",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.2/base-sha.txt",
        "CHANGELOG.md",
    ),
    "P1.3": (
        ".agents/skills/",
        "AGENTS.md",
        "packages/task/.claude-plugin/plugin.json",
        "packages/task/.codex-plugin/plugin.json",
        "packages/task/configs/command-routing.json",
        "packages/task/adapters/codex/",
        "packages/task/scripts/render-provider-commands.py",
        "packages/task/lib/task/command_catalog.py",
        "packages/task/lib/task/command_render.py",
        "packages/task/tests/",
        "packages/harness/package.json",
        "packages/harness/.claude-plugin/plugin.json",
        "packages/harness/lib/harness/provider_render.py",
        "packages/harness/lib/harness/provider_audit.py",
        "packages/harness/lib/harness/doctor.py",
        "packages/harness/tests/",
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.3/base-sha.txt",
        "CHANGELOG.md",
    ),
    "P1.5": (
        ".agents/skills/",
        "packages/skiller/configs/repository-bootstrap-skills.json",
        "packages/skiller/configs/publication-versions.json",
        "packages/skiller/package.json",
        "packages/skiller/lib/skiller/publication.py",
        "packages/skiller/lib/skiller/registry.py",
        "packages/skiller/lib/skiller/doctor.py",
        "packages/skiller/adapters/repository-bootstrap/publication-lock.json",
        "packages/skiller/tests/",
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/root-bootstrap-extension-map.json",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.5/base-sha.txt",
        "plans/2026.07.24-AGENT-RELIABILITY/findings/P1.5-collision-closure.md",
        "CHANGELOG.md",
    ),
    "P2.2": (
        "packages/task/.claude-plugin/plugin.json",
        "packages/task/.codex-plugin/plugin.json",
        "packages/task/configs/command-routing.json",
        "packages/task/adapters/codex/",
        "packages/task/lib/task/task_contract.py",
        "packages/task/lib/task/plan_lint.py",
        "packages/task/lib/task/command_render.py",
        "packages/task/lib/task/journal.py",
        "packages/task/commands/",
        "packages/task/tests/",
        "packages/skiller/package.json",
        "packages/skiller/configs/publication-versions.json",
        "packages/skiller/skills/general/plan-protocol/",
        "packages/skiller/skills/general/.claude-plugin/plugin.json",
        "packages/skiller/skills/general/.codex-plugin/plugin.json",
        "packages/skiller/adapters/codex/core/",
        "packages/skiller/skills.json",
        "packages/skiller/skills/_index.md",
        "packages/skiller/docs/guide/graph.md",
        "packages/skiller/docs/guide/budget.md",
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.2/base-sha.txt",
        "CHANGELOG.md",
    ),
    "P2.3": (
        "packages/task/.claude-plugin/plugin.json",
        "packages/task/.codex-plugin/plugin.json",
        "packages/task/configs/command-routing.json",
        "packages/task/adapters/codex/",
        "packages/task/lib/task/task_contract.py",
        "packages/task/lib/task/review_policy.py",
        "packages/task/lib/task/journal.py",
        "packages/task/tests/",
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
        "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P2.3/base-sha.txt",
        "CHANGELOG.md",
    ),
}
BASELINE_OWNERS = ("P1.2", "P1.3", "P1.5", "P2.2", "P2.3")
BASELINE_FILE = "plans/2026.07.24-AGENT-RELIABILITY/artifacts/{owner}/base-sha.txt"
PRIVATE_SOURCE_PREFIX = BOOTSTRAP_BUCKET + "/"

CAPABILITY_MANIFEST = "configs/provider-capabilities.json"
COMMAND_ROUTING = "packages/task/configs/command-routing.json"
SKILL_CAPABILITY = "skills.repository"

# Carrier literal → the capability it actually demands at runtime (closed enum).
# This is the "capability coverage from actual carrier literals" control of
# findings/03: a carrier that spells an execution literal but declares no matching
# capability cannot fail closed on an unsupported provider.
CARRIER_LITERAL_CAPABILITIES = (
    ("AskUserQuestion", "command.interactive-user-input"),
    ("WebSearch", "command.external-research"),
    ("WebFetch", "command.external-research"),
    ("Workflow({", "command.workflow-carrier"),
)

_FRONTMATTER_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_LIST = re.compile(r"^(snippets|requires):\s*\[(.*?)\]\s*$", re.MULTILINE)
_RELATIVE_REF = re.compile(r"(?<![\w./-])((?:snippets|references|templates)/[\w./-]+\.\w+)")


class InventoryError(RuntimeError):
    """Fail-closed error: every mode refuses rather than degrading to a warning."""


# --- primitives ---------------------------------------------------------------
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError:
        return None


def dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(value), encoding="utf-8")


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InventoryError(f"unreadable JSON carrier {path}: {error}") from error


def frontmatter(path: Path) -> tuple[str | None, str]:
    """Return (identity, body).  A file without a frontmatter fence has no identity."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, ""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    head, body = text[:end], text[end + 4:]
    match = _FRONTMATTER_NAME.search(head)
    if not match:
        return None, body
    return match.group(1).strip().strip("\"'"), body


def identity_of(path: Path) -> str | None:
    return frontmatter(path)[0]


def runtime_references(skill_md: Path) -> dict[str, object]:
    """Resolve every relative runtime reference declared by one skill carrier."""
    identity, body = frontmatter(skill_md)
    declared: set[str] = set()
    head = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
    for key, raw in _FRONTMATTER_LIST.findall(head):
        if key != "snippets":
            continue
        declared.update(item.strip().strip("\"'") for item in raw.split(",") if item.strip())
    references = {f"snippets/{item}" for item in declared if item}
    references.update(_RELATIVE_REF.findall(body))
    missing = sorted(ref for ref in references if not (skill_md.parent / ref).exists())
    return {
        "declared": sorted(references),
        "missing": missing,
        "complete": not missing,
    }


# --- repository-derived carrier computation (D44) -----------------------------
def _unit_skill_roots(repo: Path, provider_key: str, entry: dict) -> tuple[list[Path], str]:
    """Resolve a unit's declared skill roots without guessing nesting depth."""
    source = entry.get("source")
    if isinstance(source, dict):  # consumer-shaped local source record
        source = source.get("path")
    if not isinstance(source, str):
        raise InventoryError(f"marketplace entry {entry.get('name')!r} has no source")
    base = repo if source in ("./", ".") else repo / source.lstrip("./")
    declared = entry.get("skills")
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, list) and declared:
        return [base if item in ("./", ".") else repo / item.lstrip("./")
                for item in declared], "marketplace-skills"
    manifest = base / PROVIDERS[provider_key]["plugin_manifest"]
    if manifest.is_file():
        data = load_json(manifest)
        declared = data.get("skills") if isinstance(data, dict) else None
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, list) and declared:
            return [base if item in ("./", ".") else base / item.lstrip("./")
                    for item in declared], "plugin-manifest"
        return [], "plugin-manifest-declares-no-skills"
    return [base], "source-scan"


def unit_identities(repo: Path, provider_key: str, entry: dict) -> dict[str, object]:
    roots, resolution = _unit_skill_roots(repo, provider_key, entry)
    carriers: dict[str, Path] = {}
    for root in roots:
        if root.is_file() and root.name == "SKILL.md":
            files = [root]
        elif root.is_dir():
            files = sorted(root.rglob("SKILL.md"))
        else:
            files = []
        for skill_md in files:
            identity = identity_of(skill_md)
            if identity and identity not in carriers:
                carriers[identity] = skill_md
    return {
        "name": entry.get("name"),
        "source": entry.get("source"),
        "skills_resolution": resolution,
        "identities": {name: path for name, path in sorted(carriers.items())},
    }


def provider_state(repo: Path, provider_key: str) -> dict[str, object]:
    """Cold, repo-only carrier map for one provider: units plus root projections."""
    declaration = PROVIDERS[provider_key]
    marketplace_path = repo / declaration["marketplace"]
    marketplace = load_json(marketplace_path)
    if not isinstance(marketplace, dict) or not isinstance(marketplace.get("plugins"), list):
        raise InventoryError(f"{declaration['marketplace']}: plugins must be a list")
    units = [unit_identities(repo, provider_key, entry) for entry in marketplace["plugins"]]
    names = [unit["name"] for unit in units]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise InventoryError(
            f"{declaration['marketplace']}: duplicate unit entries {duplicates}")
    roots: dict[str, dict[str, object]] = {}
    extra_files: list[str] = []
    roots_dir = repo / declaration["roots"]
    if roots_dir.is_dir():
        for directory in sorted(roots_dir.iterdir()):
            skill_md = directory / "SKILL.md"
            if not skill_md.is_file():
                continue
            identity = identity_of(skill_md)
            if identity is None:
                raise InventoryError(
                    f"root projection {skill_md} carries no frontmatter identity")
            roots[directory.name] = {"identity": identity, "path": skill_md}
            # Anything beside SKILL.md inside a root projection is undeclared
            # content: the post-remediation invariant is "root set equals exactly
            # the declared target set", so it is measured here, never ignored.
            extra_files.extend(
                sorted(item.relative_to(repo).as_posix()
                       for item in directory.rglob("*")
                       if item.is_file() and item.name != "SKILL.md"))
    return {
        "root_projection_extra_files": sorted(extra_files),
        "provider": provider_key,
        "marketplace": declaration["marketplace"],
        "marketplace_sha256": sha256_file(marketplace_path),
        "roots_dir": declaration["roots"],
        "units": units,
        "root_projections": roots,
    }


def carrier_map(state: dict, enabled: tuple[str, ...] | None = None) -> dict[str, list[dict]]:
    """Identity → carriers.  ``enabled=None`` is the authoritative worst case."""
    carriers: dict[str, list[dict]] = collections.defaultdict(list)
    for unit in state["units"]:
        if enabled is not None and unit["name"] not in enabled:
            continue
        for identity, path in unit["identities"].items():
            carriers[identity].append(
                {"kind": "unit", "id": f"unit:{unit['name']}", "unit": unit["name"],
                 "source_path": path})
    for directory, record in state["root_projections"].items():
        carriers[record["identity"]].append(
            {"kind": "root", "id": f"root:{directory}", "unit": None,
             "source_path": record["path"]})
    return dict(carriers)


def classify(carriers: list[dict]) -> list[str]:
    units = [item for item in carriers if item["kind"] == "unit"]
    roots = [item for item in carriers if item["kind"] == "root"]
    classes = []
    if roots and units:
        classes.append("root-vs-unit")
    if len(units) > 1:
        classes.append("unit-vs-unit")
    if len(roots) > 1:
        classes.append("root-vs-root")
    return classes


def collision_view(state: dict, enabled: tuple[str, ...] | None) -> dict[str, object]:
    carriers = carrier_map(state, enabled)
    collisions = {}
    for identity, items in sorted(carriers.items()):
        if len(items) < 2:
            continue
        collisions[identity] = {
            "carriers": sorted(item["id"] for item in items),
            "classes": classify(items),
        }
    unique_roots = sorted(
        directory for directory, record in state["root_projections"].items()
        if not any(item["kind"] == "unit" for item in carriers.get(record["identity"], ()))
    )
    counts = collections.Counter()
    for record in collisions.values():
        for name in record["classes"]:
            counts[name] += 1
    return {
        "colliding_identities": len(collisions),
        "class_counts": dict(sorted(counts.items())),
        "collisions": collisions,
        "unique_root_carriers": unique_roots,
    }


# --- capabilities -------------------------------------------------------------
def capability_support(repo: Path) -> dict[str, dict[str, str]]:
    manifest = load_json(repo / CAPABILITY_MANIFEST)
    support: dict[str, dict[str, str]] = {}
    for capability in manifest.get("capabilities", ()):
        support[capability["id"]] = {
            provider: record.get("level", "unknown")
            for provider, record in capability.get("support", {}).items()
        }
    return support


def command_capabilities(repo: Path) -> dict[str, dict[str, object]]:
    """Carrier literal → required capabilities, taken from the frozen routing carrier."""
    routing = load_json(repo / COMMAND_ROUTING)
    result = {}
    for command in routing.get("commands", ()):
        identity = "task-" + command["command_id"].removeprefix("task:")
        result[identity] = {
            "command_id": command["command_id"],
            "required": list(command.get("capability_requirements", ())),
            "routing": command.get("routing", {}),
        }
    return result


def carrier_literal_gaps(repo: Path, commands: dict, support: dict) -> list[dict[str, object]]:
    """Compare what each canonical command carrier actually spells to what it declares."""
    gaps: list[dict[str, object]] = []
    for identity, record in sorted(commands.items()):
        source = repo / "packages/task/commands" / (
            record["command_id"].removeprefix("task:") + ".md")
        if not source.is_file():
            gaps.append({"identity": identity, "command_id": record["command_id"],
                         "literal": None, "expected_capability": None,
                         "gap_class": "carrier-source-missing",
                         "detail": f"canonical carrier {source.name} does not exist"})
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        declared = set(record["required"])
        for literal, capability in CARRIER_LITERAL_CAPABILITIES:
            if literal not in text:
                continue
            in_catalog = capability in support
            if not in_catalog:
                gap_class = "capability-absent-from-catalog"
            elif capability not in declared:
                gap_class = "capability-not-declared-by-carrier"
            else:
                continue
            gaps.append({
                "identity": identity,
                "command_id": record["command_id"],
                "carrier": source.relative_to(repo).as_posix(),
                "literal": literal,
                "expected_capability": capability,
                "in_capability_catalog": in_catalog,
                "declared_by_carrier": capability in declared,
                "gap_class": gap_class,
                "provider_support": support.get(capability, {}),
            })
    return gaps


def identity_capabilities(identity: str, commands: dict, support: dict,
                          provider_key: str) -> dict[str, object]:
    record = commands.get(identity)
    required = list(record["required"]) if record else [SKILL_CAPABILITY]
    levels = {}
    unmapped = []
    unsupported = []
    for capability in required:
        level = support.get(capability, {}).get(provider_key)
        if level is None:
            unmapped.append(capability)
            levels[capability] = "unmapped"
        else:
            levels[capability] = level
            if level == "unsupported":
                unsupported.append(capability)
    return {
        "required": required,
        "levels": levels,
        "unmapped": unmapped,
        "unsupported": unsupported,
        "complete": not unmapped and not unsupported,
        "command_id": record["command_id"] if record else None,
    }


# --- observed capture (one named read-only mode) ------------------------------
def _sanitize(value: str, home: str) -> str:
    return value.replace(home, "$HOME") if home else value


def capture_observed(repo: Path, out_path: Path, *, home: str,
                     runner=subprocess.run) -> dict[str, object]:
    commands: list[dict[str, object]] = []
    providers: dict[str, object] = {}
    for provider_key in sorted(PROVIDERS):
        state = provider_state(repo, provider_key)
        repo_identities = {unit["name"]: sorted(unit["identities"]) for unit in state["units"]}
        argv = PROVIDERS[provider_key]["enabled_command"]
        record: dict[str, object] = {
            "state": "unknown",
            "reason": "no declared read-only enabled-set command for this provider",
            "units": [],
            "other_marketplace_units": 0,
            "root_projections": [
                {"path": f"{state['roots_dir']}/{directory}/SKILL.md",
                 "identity": item["identity"]}
                for directory, item in sorted(state["root_projections"].items())
            ],
        }
        if argv:
            command_record: dict[str, object] = {
                "provider": provider_key, "argv": list(argv), "read_only": True,
            }
            try:
                completed = runner(list(argv), cwd=str(repo), capture_output=True,
                                   text=True, timeout=120, check=False)
            except (OSError, subprocess.SubprocessError) as error:
                command_record.update({"exit_code": None, "status": "unavailable",
                                       "detail": _sanitize(str(error), home)})
                record["reason"] = f"declared command unavailable: {type(error).__name__}"
            else:
                command_record["exit_code"] = completed.returncode
                if completed.returncode != 0:
                    command_record["status"] = "failed"
                    record["reason"] = f"declared command exited {completed.returncode}"
                else:
                    try:
                        payload = json.loads(completed.stdout)
                    except json.JSONDecodeError as error:
                        command_record["status"] = "unparseable"
                        record["reason"] = f"declared command output unparseable: {error}"
                    else:
                        command_record["status"] = "ok"
                        installed = payload.get("installed", [])
                        mine = [item for item in installed
                                if item.get("marketplaceName") == MARKETPLACE_NAME]
                        record["units"] = [
                            {"name": item.get("name"),
                             "version": item.get("version"),
                             "enabled": bool(item.get("enabled")),
                             "identities": repo_identities.get(item.get("name"), [])}
                            for item in sorted(mine, key=lambda entry: entry.get("name", ""))
                        ]
                        record["other_marketplace_units"] = len(installed) - len(mine)
                        record["state"] = "read"
                        record.pop("reason", None)
            commands.append(command_record)
        else:
            commands.append({"provider": provider_key, "argv": [], "read_only": True,
                             "exit_code": None, "status": "no-declared-command"})
        providers[provider_key] = record
    payload = {
        "schema_version": SCHEMA_BEFORE_STATE,
        "captured_at": _datetime.datetime.now(_datetime.timezone.utc)
                       .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commands": commands,
        "providers": providers,
    }
    if out_path.is_file():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if isinstance(previous, dict):
            comparable_old = {k: v for k, v in previous.items() if k != "captured_at"}
            comparable_new = {k: v for k, v in payload.items() if k != "captured_at"}
            if comparable_old == comparable_new:
                return previous  # byte-stable re-run: the capture did not change
    write_json(out_path, payload)
    return payload


def observed_enabled(observed: dict, provider_key: str) -> tuple[str, ...] | None:
    record = (observed.get("providers") or {}).get(provider_key) or {}
    if record.get("state") != "read":
        return None
    return tuple(sorted(unit["name"] for unit in record.get("units", ())
                        if unit.get("enabled")))


# --- provenance note (immutable bundle, D30/D44) ------------------------------
def provenance_record(path: Path) -> dict[str, object]:
    payload = load_json(path)
    parseable = {key: value for key, value in payload.items()
                 if isinstance(value, (int, float)) and not isinstance(value, bool)}
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "role": "provenance-only",
        "identity_records": 0,
        "cross_checked_counters": sorted(parseable),
        "classification": "pinned-not-recomputable" if not parseable else "cross-checked",
        "note": ("the committed prose runtime inventory carries no identity record, "
                 "no unit list and no version; it corroborates nothing machine-comparable "
                 "and is never the diff source of collision detection (D44)"),
        "top_level_keys": sorted(payload) if isinstance(payload, dict) else [],
    }


# --- builders -----------------------------------------------------------------
def build_inventory(repo: Path, observed: dict, provenance: Path) -> dict[str, object]:
    support = capability_support(repo)
    commands = command_capabilities(repo)
    providers: dict[str, object] = {}
    for provider_key in sorted(PROVIDERS):
        state = provider_state(repo, provider_key)
        worst = collision_view(state, None)
        declared = DECLARED_ENABLED.get(provider_key)
        enabled_view = collision_view(state, declared) if declared else None
        seen = observed_enabled(observed, provider_key)
        identities: list[dict[str, object]] = []
        carriers = carrier_map(state, None)
        for identity, items in sorted(carriers.items()):
            unit_carriers = [item for item in items if item["kind"] == "unit"]
            root_carriers = [item for item in items if item["kind"] == "root"]
            canonical = unit_carriers[0]["source_path"] if unit_carriers else (
                root_carriers[0]["source_path"] if root_carriers else None)
            references = runtime_references(canonical) if canonical else {
                "declared": [], "missing": [], "complete": False}
            identities.append({
                "semantic_id": identity,
                "canonical_owner": (f"unit:{unit_carriers[0]['unit']}" if unit_carriers
                                    else "root-bootstrap"),
                "canonical_source": canonical.relative_to(repo).as_posix() if canonical else None,
                "canonical_sha256": sha256_file(canonical) if canonical else None,
                "projection_owner": ([item["id"] for item in root_carriers] or
                                     ["none"]),
                "carriers": [
                    {"id": item["id"], "kind": item["kind"],
                     "source_path": item["source_path"].relative_to(repo).as_posix(),
                     "content_sha256": sha256_file(item["source_path"])}
                    for item in sorted(items, key=lambda entry: entry["id"])
                ],
                "capabilities": identity_capabilities(identity, commands, support, provider_key),
                "runtime_references": references,
                "discovery_state": (
                    "collision" if len(items) > 1 else
                    "root-only" if not unit_carriers else "unit-only"),
            })
        providers[provider_key] = {
            "marketplace": state["marketplace"],
            "marketplace_sha256": state["marketplace_sha256"],
            "roots_dir": state["roots_dir"],
            "root_projection_extra_files": state["root_projection_extra_files"],
            "units": [{"name": unit["name"], "source": unit["source"],
                       "skills_resolution": unit["skills_resolution"],
                       "identity_count": len(unit["identities"]),
                       "identities": sorted(unit["identities"])}
                      for unit in state["units"]],
            "identity_count": len(identities),
            "identities": identities,
            "collisions": {
                "repo_derived_worst_case": {
                    "authoritative": True,
                    "colliding_identities": worst["colliding_identities"],
                    "class_counts": worst["class_counts"],
                    "identities": sorted(worst["collisions"]),
                },
                "declared_enabled_conditioned": None if enabled_view is None else {
                    "authoritative": False,
                    "enabled_set_source": ("findings/12-effective-collision-remeasure.md "
                                           "§ Observed runtime (2026-07-25)"),
                    "enabled_units": list(declared),
                    "colliding_identities": enabled_view["colliding_identities"],
                    "class_counts": enabled_view["class_counts"],
                    "identities": sorted(enabled_view["collisions"]),
                    "unique_root_carriers": enabled_view["unique_root_carriers"],
                },
            },
            "observed": {
                "state": (observed.get("providers", {}).get(provider_key, {}) or {}).get("state"),
                "enabled_units": list(seen) if seen is not None else None,
                "matches_declared": (None if seen is None or declared is None
                                     else sorted(seen) == sorted(declared)),
                "role": ("corroboration only: it can never remove a collision from the "
                         "repo-derived set, and an unreadable provider stays `unknown`"),
            },
        }
    return {
        "schema_version": SCHEMA_INVENTORY,
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P1.1",
        "detection": {
            "mode": "repo-derived-cold",
            "rule": ("every publishable unit declared in a provider's repository "
                     "marketplace is a potential carrier (worst case: any unit may be "
                     "enabled); every root projection is a carrier; an identity with "
                     "≥2 carriers is a collision and needs an owner record"),
        },
        "provenance_note": provenance_record(provenance),
        "capability_gaps": carrier_literal_gaps(repo, commands, support),
        "observed_state": {
            "schema_version": observed.get("schema_version"),
            "captured_at": observed.get("captured_at"),
            "commands": observed.get("commands", []),
        },
        "providers": providers,
    }


def build_remediation(repo: Path, inventory: dict) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for provider_key in sorted(PROVIDERS):
        state = provider_state(repo, provider_key)
        worst = collision_view(state, None)
        declared = DECLARED_ENABLED.get(provider_key)
        enabled_view = collision_view(state, declared) if declared else None
        enabled_ids = set(enabled_view["collisions"]) if enabled_view else set()
        for identity, record in sorted(worst["collisions"].items()):
            owners = []
            for class_name in record["classes"]:
                if class_name == "root-vs-unit":
                    if identity == CLASS_B_IDENTITY:
                        owner, action = ROOT_OWNERS[identity], CLASS_B_ACTION
                    else:
                        owner = ROOT_OWNERS.get(identity)
                        if owner is None:
                            continue  # left unowned on purpose → the gate fails loudly
                        action = ROOT_ACTIONS[owner]
                    owners.append({"class": class_name, "owner_item": owner,
                                   "action": action[0], "rationale": action[1]})
                elif class_name == "unit-vs-unit":
                    owners.append({"class": class_name, "owner_item": UNIT_VS_UNIT_OWNER,
                                   "action": UNIT_VS_UNIT_ACTION[0],
                                   "rationale": UNIT_VS_UNIT_ACTION[1],
                                   "safe_owner_action": (
                                       "disable either the curated `core` unit or the donor "
                                       "bucket for this provider; the plan never writes the "
                                       "user-owned enabled set (D42)")})
                else:
                    owners.append({"class": class_name, "owner_item": None,
                                   "action": "unowned", "rationale": "no owner item frozen"})
            records.append({
                "provider": provider_key,
                "identity": identity,
                "carriers": record["carriers"],
                "classes": record["classes"],
                "live_under_declared_enabled_set": identity in enabled_ids,
                "owners": owners,
            })
    owners = {}
    for owner in BASELINE_OWNERS:
        owners[owner] = {
            "paths": list(OWNER_PATHS[owner]),
            "baseline_file": BASELINE_FILE.format(owner=owner),
            "version_bumps": [item for item in VERSION_LEDGER if item["owner_item"] == owner],
            "byte_identical_guards": [item for item in BYTE_IDENTICAL_GUARDS
                                      if item["owner_item"] == owner],
        }
    return {
        "schema_version": SCHEMA_REMEDIATION,
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P1.1",
        "collisions": records,
        "owners": owners,
        "baseline_owners": list(BASELINE_OWNERS),
        "class_a_identities": [{"identity": identity} for identity in CLASS_A_IDENTITIES],
        "private_source_prefix": PRIVATE_SOURCE_PREFIX,
        "version_ledger": list(VERSION_LEDGER),
        "class_b": {
            "identity": CLASS_B_IDENTITY,
            "owner_item": ROOT_OWNERS[CLASS_B_IDENTITY],
            "publication_unit": CLASS_B_UNIT,
            "providers": ["codex"],
            "projection": CLASS_B_PROJECTION,
            "canonical": CLASS_B_CANONICAL,
            "canonical_sha256": sha256_file(repo / CLASS_B_CANONICAL),
            "asymmetry_reason": (
                "a Claude root projection changes the first-turn budget and requires "
                "`skiller budget --first-turn` (CLAUDE.md), which is outside this scope; "
                "the asymmetry is declared, not accidental"),
            "precondition": "no enabled unit serves this identity",
            "exact_acceptance_owner": "P1.5 root-bootstrap-extension-map.json",
        },
    }


def build_bootstrap_map(repo: Path) -> dict[str, object]:
    records = []
    for identity in sorted(CLASS_A_IDENTITIES):
        seeds = {}
        for provider in SEED_PROVIDERS:
            path = f"{SEED_ROOTS[provider]}/{identity}/SKILL.md"
            digest = sha256_file(repo / path)
            if digest is None:
                raise InventoryError(f"missing migration seed {path}")
            seeds[provider] = {"path": path, "sha256": digest}
        differ = seeds["claude"]["sha256"] != seeds["codex"]["sha256"]
        records.append({
            "identity": identity,
            "seeds": seeds,
            "resolution": {
                "seeds_differ": differ,
                "selected_seed": "claude",
                "reason": (
                    "the Codex copy is a mechanical Claude→Codex string substitution of the "
                    "Claude copy (findings/03 § root adapters: 48 blind provider "
                    "substitutions producing non-existent paths such as `.Codex-plugin`), "
                    "so the Claude bytes are the undamaged migration seed"
                    if differ else
                    "both seeds are byte-identical; the Claude path is named for determinism"),
            },
            "canonical": {
                "ru": f"{BOOTSTRAP_BUCKET}/{identity}/SKILL.ru.md",
                "en": f"{BOOTSTRAP_BUCKET}/{identity}/SKILL.md",
            },
            "projections": {
                "claude": f".claude/skills/{identity}/SKILL.md",
                "codex": f".agents/skills/{identity}/SKILL.md",
            },
            "canonical_content_version": BOOTSTRAP_CONTENT_VERSION,
            "publication_unit": BOOTSTRAP_UNIT,
            "generator": BOOTSTRAP_GENERATOR,
            "lock_path": BOOTSTRAP_LOCK,
        })
    return {"schema_version": SCHEMA_BOOTSTRAP, "records": records}


# --- checkers -----------------------------------------------------------------
def check_bootstrap_map(repo: Path, path: Path) -> list[str]:
    """Exact set equality, not key presence (D38).  Returns the failure list."""
    failures: list[str] = []
    try:
        payload = load_json(path)
    except InventoryError as error:
        return [str(error)]
    if not isinstance(payload, dict):
        return ["bootstrap map root must be an object"]
    if set(payload) != {"schema_version", "records"}:
        failures.append(f"top-level keys must be exactly "
                        f"['records', 'schema_version'], got {sorted(payload)}")
    if payload.get("schema_version") != SCHEMA_BOOTSTRAP:
        failures.append(f"schema_version must be {SCHEMA_BOOTSTRAP!r}")
    records = payload.get("records")
    if not isinstance(records, list):
        return failures + ["records must be a list"]

    identities = [record.get("identity") for record in records
                  if isinstance(record, dict)]
    if len(identities) != len(records):
        failures.append("every record must be an object with an identity")
    if identities != sorted(identities):
        failures.append("records must be sorted by identity")
    if len(set(identities)) != len(identities):
        failures.append("duplicate identity records")
    if set(identities) != set(CLASS_A_IDENTITIES):
        missing = sorted(set(CLASS_A_IDENTITIES) - set(identities))
        extra = sorted(set(identities) - set(CLASS_A_IDENTITIES))
        failures.append(f"identity set mismatch: missing={missing} extra={extra}")

    targets: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        identity = record.get("identity")
        if set(record) != BOOTSTRAP_RECORD_KEYS:
            failures.append(f"{identity}: record keys must be exactly "
                            f"{sorted(BOOTSTRAP_RECORD_KEYS)}, got {sorted(record)}")
            continue
        canonical = record["canonical"]
        expected_canonical = {"ru": f"{BOOTSTRAP_BUCKET}/{identity}/SKILL.ru.md",
                              "en": f"{BOOTSTRAP_BUCKET}/{identity}/SKILL.md"}
        if canonical != expected_canonical:
            failures.append(f"{identity}: canonical bilingual formula mismatch")
        projections = record["projections"]
        expected_projections = {"claude": f".claude/skills/{identity}/SKILL.md",
                                "codex": f".agents/skills/{identity}/SKILL.md"}
        if projections != expected_projections:
            failures.append(f"{identity}: projection formula mismatch")
        else:
            targets.extend(projections.values())
        if record["canonical_content_version"] != BOOTSTRAP_CONTENT_VERSION:
            failures.append(f"{identity}: canonical_content_version literal mismatch")
        if record["publication_unit"] != BOOTSTRAP_UNIT:
            failures.append(f"{identity}: publication_unit literal mismatch")
        if record["generator"] != BOOTSTRAP_GENERATOR:
            failures.append(f"{identity}: generator literal mismatch")
        if record["lock_path"] != BOOTSTRAP_LOCK:
            failures.append(f"{identity}: lock_path literal mismatch")
        seeds = record["seeds"]
        if not isinstance(seeds, dict) or set(seeds) != set(SEED_PROVIDERS):
            failures.append(f"{identity}: seeds must carry exactly {list(SEED_PROVIDERS)}")
            continue
        digests = {}
        for provider in SEED_PROVIDERS:
            seed = seeds[provider]
            if not isinstance(seed, dict) or set(seed) != {"path", "sha256"}:
                failures.append(f"{identity}: seed {provider} must carry path+sha256")
                continue
            expected_path = f"{SEED_ROOTS[provider]}/{identity}/SKILL.md"
            if seed["path"] != expected_path:
                failures.append(f"{identity}: seed {provider} path mismatch")
            actual = sha256_file(repo / seed["path"])
            if actual is None:
                failures.append(f"{identity}: seed {provider} file is missing")
            elif actual != seed["sha256"]:
                failures.append(f"{identity}: seed {provider} hash drifted")
            digests[provider] = actual
        resolution = record["resolution"]
        if not isinstance(resolution, dict) or set(resolution) != {
                "seeds_differ", "selected_seed", "reason"}:
            failures.append(f"{identity}: resolution must carry "
                            "seeds_differ/selected_seed/reason")
            continue
        differ = len(set(digests.values())) > 1
        if resolution["seeds_differ"] != differ:
            failures.append(f"{identity}: resolution.seeds_differ disagrees with the seeds")
        if resolution["selected_seed"] not in SEED_PROVIDERS:
            failures.append(f"{identity}: resolution.selected_seed must name a seed")
        if not isinstance(resolution["reason"], str) or not resolution["reason"].strip():
            failures.append(f"{identity}: resolution.reason is required for every record")

    expected_targets = sorted(
        [f".claude/skills/{identity}/SKILL.md" for identity in CLASS_A_IDENTITIES]
        + [f".agents/skills/{identity}/SKILL.md" for identity in CLASS_A_IDENTITIES])
    if len(targets) != len(set(targets)):
        failures.append("projection targets are not globally unique")
    if sorted(targets) != expected_targets:
        failures.append(f"projection target set must be exactly the "
                        f"{len(expected_targets)} formula-derived paths, got {len(targets)}")
    return failures


def check_collision_owners(repo: Path, path: Path) -> list[str]:
    """Every measured collision must name an owner item for every measured class."""
    failures: list[str] = []
    try:
        payload = load_json(path)
    except InventoryError as error:
        return [str(error)]
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_REMEDIATION:
        return [f"remediation map schema_version must be {SCHEMA_REMEDIATION!r}"]
    recorded = {}
    for record in payload.get("collisions", ()):
        if not isinstance(record, dict):
            failures.append("collision record must be an object")
            continue
        recorded[(record.get("provider"), record.get("identity"))] = record

    for provider_key in sorted(PROVIDERS):
        state = provider_state(repo, provider_key)
        measured = collision_view(state, None)["collisions"]
        for identity, record in sorted(measured.items()):
            key = (provider_key, identity)
            entry = recorded.get(key)
            if entry is None:
                failures.append(
                    f"measured collision without an owner record: {provider_key}/{identity} "
                    f"carriers={record['carriers']}")
                continue
            if sorted(entry.get("carriers", ())) != sorted(record["carriers"]):
                failures.append(f"{provider_key}/{identity}: carrier set drifted")
            owned = {item.get("class"): item for item in entry.get("owners", ())
                     if isinstance(item, dict)}
            for class_name in record["classes"]:
                owner = owned.get(class_name)
                if owner is None or not owner.get("owner_item"):
                    failures.append(
                        f"{provider_key}/{identity}: class {class_name} has no owner item")
        for key in sorted(recorded):
            if key[0] == provider_key and key[1] not in measured:
                failures.append(f"{key[0]}/{key[1]}: owner record without a measured collision")

    owners = payload.get("owners", {})
    if sorted(owners) != sorted(BASELINE_OWNERS):
        failures.append(f"owners must be exactly {list(BASELINE_OWNERS)}, got {sorted(owners)}")
    for owner in BASELINE_OWNERS:
        record = owners.get(owner) or {}
        if list(record.get("paths", ())) != list(OWNER_PATHS[owner]):
            failures.append(f"{owner}: owner path set drifted from the frozen ledger")
        if record.get("baseline_file") != BASELINE_FILE.format(owner=owner):
            failures.append(f"{owner}: baseline carrier path mismatch")
    if list(payload.get("version_ledger", ())) != [dict(item) for item in VERSION_LEDGER]:
        failures.append("version ledger drifted from the frozen P1.1 approval")
    class_a = [item.get("identity") for item in payload.get("class_a_identities", ())
               if isinstance(item, dict)]
    if class_a != list(CLASS_A_IDENTITIES):
        failures.append("class-A identity set drifted from the frozen 13")
    if payload.get("private_source_prefix") != PRIVATE_SOURCE_PREFIX:
        failures.append("private source prefix drifted")
    return failures


# --- CLI ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--capture-observed")
    parser.add_argument("--observed-state")
    parser.add_argument("--provenance-note")
    parser.add_argument("--output")
    parser.add_argument("--remediation")
    parser.add_argument("--bootstrap-map")
    parser.add_argument("--check-bootstrap-map")
    parser.add_argument("--check-collision-owners")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"FAIL: {repo} is not a repository root", file=sys.stderr)
        return 2

    try:
        if args.capture_observed:
            out = Path(args.capture_observed)
            payload = capture_observed(repo, out, home=str(Path.home()))
            states = {key: value.get("state")
                      for key, value in sorted(payload["providers"].items())}
            print(f"capture-observed → {out} ({payload['captured_at']}) providers={states}")
            return 0

        if args.check_bootstrap_map:
            failures = check_bootstrap_map(repo, Path(args.check_bootstrap_map))
            if failures:
                print("FAIL check-bootstrap-map:", file=sys.stderr)
                for item in failures:
                    print(f"  - {item}", file=sys.stderr)
                return 1
            print(f"check-bootstrap-map: OK — exactly {len(CLASS_A_IDENTITIES)} class-A "
                  f"identities, {2 * len(CLASS_A_IDENTITIES)} unique projections, "
                  "literals and seed hashes match")
            return 0

        if args.check_collision_owners:
            failures = check_collision_owners(repo, Path(args.check_collision_owners))
            if failures:
                print("FAIL check-collision-owners:", file=sys.stderr)
                for item in failures:
                    print(f"  - {item}", file=sys.stderr)
                return 1
            total = sum(collision_view(provider_state(repo, key), None)["colliding_identities"]
                        for key in PROVIDERS)
            print(f"check-collision-owners: OK — {total} measured colliding identities "
                  "across both providers, every measured class has an owner item")
            return 0

        missing = [name for name in ("observed_state", "provenance_note", "output",
                                     "remediation", "bootstrap_map")
                   if not getattr(args, name)]
        if missing:
            print(f"FAIL: generation mode requires {missing}", file=sys.stderr)
            return 2
        observed = load_json(Path(args.observed_state))
        if observed.get("schema_version") != SCHEMA_BEFORE_STATE:
            print(f"FAIL: observed state must be {SCHEMA_BEFORE_STATE}", file=sys.stderr)
            return 1
        inventory = build_inventory(repo, observed, Path(args.provenance_note))
        remediation = build_remediation(repo, inventory)
        bootstrap = build_bootstrap_map(repo)
        write_json(Path(args.output), inventory)
        write_json(Path(args.remediation), remediation)
        write_json(Path(args.bootstrap_map), bootstrap)
        for provider_key in sorted(PROVIDERS):
            record = inventory["providers"][provider_key]
            worst = record["collisions"]["repo_derived_worst_case"]
            print(f"{provider_key}: {record['identity_count']} identities, "
                  f"worst-case collisions {worst['colliding_identities']} "
                  f"{worst['class_counts']}")
        print(f"remediation → {args.remediation} "
              f"({len(remediation['collisions'])} owner records); "
              f"bootstrap-map → {args.bootstrap_map} ({len(bootstrap['records'])} class-A)")
        return 0
    except InventoryError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
