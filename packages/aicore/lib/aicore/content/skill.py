"""Skill model: what a skill directory is, how it is hashed, read and described.

The single home of the rules that every consumer shares (registry, budget, publication, evaluation,
materialization): the files that never travel with a skill, frontmatter reading, the content hash, the
transitive ``requires`` resolution and the descriptor contract ``skill-descriptor/v1``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..util.term import warn
from ..util.text import parse_frontmatter, parse_inline_list

# Skill catalog files that are NOT sent to the consuming project by any channel
# physical transfer (vendor/sync): upstream.json and .claude-plugin — service registry;
# SKILL.*.md — non-canonical localized/reference alternates ("SKILL.*.md" not
# matches itself EN-only "SKILL.md"); evals/ — behavioral tests
# skill; __pycache__/*.pyc — bytecode cache, appears locally when launched manually
# .py-snippets (e.g. snippets/check.py) — found while investigating unstable
# content_sha256 for the skill with .py-snippets (registry --check turned green locally and
# drifted in a clean checkout/CI). THE SINGLE source of truth: vendor.copy_skill and
# skillset.sync copy through it (used to be duplicated and skillset lost
# SKILL.*.md/evals → leak RU-source).
# selection.json — selection policy sidecar (skill-selection/v1): read by skiller from the library,
# not part of the skill content, so it is neither copied to consumers nor hashed.
SKILL_IGNORE = ("upstream.json", ".claude-plugin", "SKILL.*.md", "evals",
                "__pycache__", "*.pyc", "*.provider-artifact.bak", "selection.json")


# --- frontmatter --------------------------------------------------------------
# Analysis lives in aicore.util.text (single source for every package).
# Here all that remains is to read the file: utf-8-sig cuts BOM, if available (otherwise
# `﻿---` != `---` and all frontmatter would be silently ignored).
def read_frontmatter(path):
    """Frontmatter skill along the way (parse_frontmatter on top utf-8-sig-read)."""
    return parse_frontmatter(Path(path).read_text(encoding="utf-8-sig"))


def read_frontmatter_fields(skill_md):
    """name + requires from the first ----delimited block."""
    fm = read_frontmatter(skill_md)
    return {"name": fm.get("name", ""),
            "requires": parse_inline_list(fm.get("requires", ""))}


def split_frontmatter(text):
    """(frontmatter_text, body_text). Without frontmatter → ("", text).

    B-4 (audit): looks like a double common.parse_frontmatter/core.text.parse_frontmatter,
    but solves ANOTHER problem - so you need a disassembled YAML-dictionary (without body), this
    function needs EXACTLY the body (frontmatter_text is not parsed here as YAML, only
    is cut off). Merge would mean changing the signature core.parse_frontmatter (common for
    every package — risk is wider than one package) for 8-line border finder
    `---`...`---`. Left separately deliberately, not out of oversight."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return "", text


# --- requires (transitive dependency BFS) --------------------------------------
DEPENDENCY_DIAGNOSTIC_CODES = frozenset({
    "SKILL_REQUIRED_EXCLUDED",
    "SKILL_REQUIRED_UNKNOWN",
})


def aggregate_dependency_diagnostics(diagnostics):
    """Collapse dependency failures into stable machine-readable diagnostics.

    Human warnings remain owned by :func:`resolve_requires_bfs`; this projection is
    deliberately message-free so localization cannot change diagnostic identity.
    Repeated observations of the same ``code``/required skill are represented once,
    with the complete sorted requester set in ``affected_identities``.
    """
    grouped = {}
    for item in diagnostics:
        code = item.get("code")
        required = item.get("required_skill")
        requester = item.get("requester")
        if (code not in DEPENDENCY_DIAGNOSTIC_CODES
                or not isinstance(required, str) or not required
                or not isinstance(requester, str) or not requester):
            continue
        grouped.setdefault((code, required), set()).add(requester)
    return [
        {
            "code": code,
            "severity": "warning",
            "required_skill": required,
            "affected_identities": sorted(requesters),
        }
        for (code, required), requesters in sorted(grouped.items())
    ]


def resolve_requires_bfs(seed, lookup, selected_keys, exclude, *, diagnostics=None):
    """Transitive BFS resolve frontmatter `requires` — SINGLE source for
    vendor.resolve_requires (FS-tuples) and skillset._pull_requires (registry-entry):
    before these were two independent, already diverged bodies (RU/EN texts warn,
    audit V-1). The caller adapts its data model to the dictionary node via `lookup`.

    seed: [(dep_name, requester_key), ...] — start queue (requires already
        selected skills).
    lookup(dep_name) -> {"key", "requires": [str], "exclude_tokens": set[str], ...} | None
        — resolve dependency name to node; None — dependency not found in the registry.
        The node can carry any additional. fields (e.g. "_payload") — the caller reads them himself
        from return.
    selected_keys: mutable set of already selected keys - MUTATES (here
        keys of resolved nodes are added), to call again/recursion not
        doubled what was already selected.
    exclude: many tokens that BEAT addiction (safety-oriented) —
        dependency with intersection exclude_tokens is skipped with warning, even if
        another skill needs it.

    diagnostics: optional mutable list populated with stable dependency records.
        It does not suppress or change the existing human warning text.

    Returns [(node, requester_key), ...] in resolution order - caller himself
    decides how to put nodes in its structure (list of tuples / dict by name)."""
    queue = list(seed)
    resolved = []
    observed_diagnostics = []
    while queue:
        dep, requester = queue.pop(0)
        if dep in selected_keys:
            continue
        node = lookup(dep)
        if node is None:
            warn(f"'{requester}' requires unknown skill '{dep}' — pass")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_UNKNOWN",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        if node["exclude_tokens"] & exclude:
            warn(f"'{requester}' requires '{dep}', but he's in exclude — dependency missing")
            observed_diagnostics.append({
                "code": "SKILL_REQUIRED_EXCLUDED",
                "required_skill": dep,
                "requester": requester,
            })
            continue
        selected_keys.add(node["key"])
        resolved.append((node, requester))
        queue.extend((d, node["key"]) for d in node["requires"])
    if diagnostics is not None:
        prior = [
            {
                "code": item.get("code"),
                "required_skill": item.get("required_skill"),
                "requester": requester,
            }
            for item in diagnostics
            for requester in item.get("affected_identities", [])
        ]
        diagnostics[:] = aggregate_dependency_diagnostics(
            prior + observed_diagnostics)
    return resolved


def skill_content_hash(skill_dir):
    """SHA-256 based on the contents of ALL files in the skill catalog - drift detection sync wider,
    than one at a time SKILL.md: catches edits in snippets/ and references/ (which SKILL.md
    may not move). We ignore the same thing that is NOT vendored: upstream.json, language
    alternatives SKILL.*.md (except SKILL.md), .claude-plugin/, __pycache__/*.pyc.
    The relative path of the file is included in the hash (rename protection/movements).
    The order is stable (sorted).

    Full hexdigest, like the others sha256 in the registry/location. Complements, NOT replaces
    field sha256 (by SKILL.md) — old locks without content_sha256 degrade correctly."""
    h = hashlib.sha256()
    skill_dir = Path(skill_dir)
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file():
            continue
        name = f.name
        if name in ("upstream.json", "selection.json"):
            continue
        if name.startswith("SKILL.") and name.endswith(".md") and name != "SKILL.md":
            continue
        if ".claude-plugin" in f.parts:
            continue
        # __pycache__/*.pyc — bytecode cache when running locally.py-snippets (e.g.
        # snippets/check.py); without exception content_sha256 is unstable between machines
        # (found during drift investigation skills.json — on the developer disk was
        # __pycache__, in a clean checkout/CI it’s not there, the hashes were different).
        if "__pycache__" in f.parts or name.endswith(".pyc"):
            continue
        # evals/ — behavioral tests (eval-first), NOT vendored (see vendor.copy_skill);
        # is excluded from the hash so that editing the test is not considered a drift of the vendor skill.
        if "evals" in f.relative_to(skill_dir).parts:
            continue
        h.update(str(f.relative_to(skill_dir)).encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
    return h.hexdigest()


def skill_digest(skill_dir):
    """Tagged digest of a skill: ``sha256:`` plus :func:`skill_content_hash` (the ``content_sha256`` algorithm)."""
    return "sha256:" + skill_content_hash(skill_dir)


# --- descriptor (skill-descriptor/v1) -----------------------------------------
SKILL_DESCRIPTOR_SCHEMA = "skill-descriptor/v1"
# Agent Skills standard: ``compatibility`` is 1-500 characters.
COMPATIBILITY_MAX = 500
_PROVENANCE_KEYS = ("source", "repo", "strategy", "license")
_FILE_KEYS = ("path", "url", "sha256", "fetched_at")
_AUDIT_KEYS = ("verdict", "at", "upstream_sha")


def _invalid(path, problem):
    return ValueError(f"SKILL_DESCRIPTOR_INVALID: {path}: {problem}")


def _text(value):
    """A frontmatter or JSON scalar as a nonempty stripped string; anything else is absent (None)."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _frontmatter_metadata(text):
    """The ``metadata:`` map of the frontmatter (string to string); ``{}`` when absent.

    ``parse_frontmatter`` skips nested maps, so the block is read from the cut frontmatter text: the indented
    ``key: value`` lines under ``metadata:``.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    block, _ = split_frontmatter(text)
    result = {}
    inside = False
    for line in block.split("\n"):
        if not line.strip():
            continue
        if line[:1] not in (" ", "\t"):
            inside = line.startswith("metadata:") and not line[len("metadata:"):].strip()
            continue
        if inside and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().strip('"').strip("'")
            if key:
                result[key] = value.strip().strip('"').strip("'")
    return result


def _read_upstream(skill_dir):
    """``upstream.json`` next to the skill as a dict, or None when there is none."""
    path = Path(skill_dir) / "upstream.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _invalid(path, f"upstream.json is unreadable ({exc})") from None
    if not isinstance(data, dict):
        raise _invalid(path, "upstream.json is not an object")
    return data


def _provenance(upstream):
    if upstream is None:
        return {"source": "local"}
    result = {key: upstream[key] for key in _PROVENANCE_KEYS if _text(upstream.get(key))}
    files = upstream.get("files")
    if isinstance(files, list):
        result["files"] = [
            {key: item[key] for key in _FILE_KEYS if key in item}
            for item in files if isinstance(item, dict)]
    audit = upstream.get("audit")
    if isinstance(audit, dict):
        result["audit"] = {key: audit[key] for key in _AUDIT_KEYS if key in audit}
    result.setdefault("source", "upstream")
    return result


@dataclass(frozen=True)
class SkillDescriptor:
    """What a skill is, read from its directory; field meanings are in ``skill-descriptor/v1``."""

    id: str
    name: str
    description: str
    digest: str
    version: object = None
    license: object = None
    compatibility: object = None
    allowed_tools: tuple = ()
    adapters: tuple = ()
    requires: tuple = ()
    risk: object = None
    metadata: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=lambda: {"source": "local"})

    def to_json(self):
        """The ``skill-descriptor/v1`` document."""
        return {
            "schema": SKILL_DESCRIPTOR_SCHEMA,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "digest": self.digest,
            "license": self.license,
            "compatibility": self.compatibility,
            "allowed_tools": list(self.allowed_tools),
            "adapters": list(self.adapters),
            "requires": list(self.requires),
            "risk": self.risk,
            "metadata": dict(self.metadata),
            "provenance": json.loads(json.dumps(self.provenance)),
        }


def describe_skill(skill_dir, *, skill_id):
    """Describe the skill in *skill_dir* under the identity *skill_id*; only reads, never rewrites a value.

    Fields come from the SKILL.md frontmatter and the ``upstream.json`` next to it; whatever is absent is
    ``None``, ``[]`` or ``{}``. Raises ``ValueError("SKILL_DESCRIPTOR_INVALID: ...")`` when ``name`` or
    ``description`` is missing, ``compatibility`` is longer than the standard allows, or ``upstream.json``
    is unreadable.
    """
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise _invalid(skill_md, "SKILL.md is missing")
    text = skill_md.read_text(encoding="utf-8-sig")
    fm = parse_frontmatter(text)
    for key in ("name", "description"):
        if not _text(fm.get(key)):
            raise _invalid(skill_md, f"{key} is missing")
    compatibility = _text(fm.get("compatibility"))
    if compatibility is not None and len(compatibility) > COMPATIBILITY_MAX:
        raise _invalid(skill_md, f"compatibility is longer than {COMPATIBILITY_MAX} characters")
    upstream = _read_upstream(skill_dir)
    allowed = fm.get("allowed-tools", "")
    allowed_tools = allowed if isinstance(allowed, list) else str(allowed).split()
    return SkillDescriptor(
        id=skill_id,
        name=_text(fm["name"]),
        description=_text(fm["description"]),
        version=_text(fm.get("version")),
        digest=skill_digest(skill_dir),
        license=_text(fm.get("license")) or _text((upstream or {}).get("license")),
        compatibility=compatibility,
        allowed_tools=tuple(parse_inline_list(allowed_tools)),
        adapters=tuple(parse_inline_list(fm.get("adapters", ""))),
        requires=tuple(parse_inline_list(fm.get("requires", ""))),
        risk=_text(fm.get("risk")),
        metadata=_frontmatter_metadata(text),
        provenance=_provenance(upstream),
    )
