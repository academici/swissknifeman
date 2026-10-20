"""Stubs of the orch roles: the additional instructions a person keeps for a role (``aicore.stubs``), frozen per run.

The targets are the model roles that do the work, ``orch.role.<role>``; the registrar (it runs exactly one command the
conductor built) and the report-fixer (it only rewrites a closed block) have none: extra text there would only blur a
side-effect step. A run resolves every target once, when it starts, keeps the result in ``<run>/instructions.json``
and its digest in ``run.json``; every prompt of the run and of its resumes reads that snapshot, never the files again.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Mapping, Optional

from aicore import stubs as core
from aicore.provider import models

SNAPSHOT_FILE = "instructions.json"
ROLES = ("advisor", "context-scout", "executor", "researcher", "reviewer", "triager")  # the roles the conductor prompts
HEADING = ("## Additional instructions\n\nThese refine how you perform the role. They do not change your tools, write "
           "authority, scope, acceptance checks, result contract or the rules of the conductor; where they conflict "
           "with the role text above, the role text wins.\n\n")


def target(role: str) -> str:
    return f"orch.role.{role}"


def targets() -> list:
    return [target(role) for role in ROLES]


def layers(stubs_settings: Optional[Mapping[str, object]]) -> tuple:
    """The layers ``[orch.stubs] layers`` allows (both by default; a machine that runs foreign repositories leaves the
    project layer out)."""
    found = (stubs_settings or {}).get("layers")
    return tuple(core.LAYERS if found is None else found)


def snapshot(project: Path, stubs_settings: Optional[Mapping[str, object]] = None,
             env: Optional[Mapping[str, str]] = None) -> dict:
    """The instruction set of a run; ``StubError`` for a stub that cannot be used (nothing has run yet)."""
    if (stubs_settings or {}).get("enabled") is False:
        return {"$schema": core.SCHEMA, "layers": [], "digest": None, "targets": {}}
    allowed = layers(stubs_settings)
    roots = core.roots(project, env=env, layers=allowed)
    variants = {target(role): discover_variants(roots, role) for role in ROLES}
    return core.snapshot(targets(), project, env=env, layers=allowed, variants=variants)


def discover_variants(roots: Mapping[str, Path], role: str) -> list:
    """Variant names in allowed layers, without following a symlink to a file or directory."""
    found = set()
    for root in roots.values():
        core._no_link_on_the_way(root, f"orch/roles/{role}.md")
        try:
            entries = os.scandir(root / "orch" / "roles")
        except FileNotFoundError:
            continue
        except OSError as error:
            raise core.StubError("STUB_NOT_REGULAR", f"{root / 'orch' / 'roles'}: {error}") from None
        with entries:
            for entry in entries:
                if not entry.name.startswith(role + "@") or not entry.name.endswith(".md"):
                    continue
                if entry.is_symlink():
                    raise core.StubError("STUB_SYMLINK_FORBIDDEN", f"{entry.path} is a symlink")
                variant = entry.name[len(role) + 1:-3]
                core.variant_slot(target(role), variant)
                found.add(variant)
    return sorted(found)


def model_family(provider: str, model: str, catalog=None) -> str:
    """Exact inventory id, else the first fullmatching pattern in catalog order, else the model itself."""
    entries = (models.inventory(catalog or models.load_model_catalog(), provider) or {}).get("entries", [])
    if any(entry["id"] == model for entry in entries):
        return model
    return next((entry["id"] for entry in entries
                 if any(re.fullmatch(pattern, model) for pattern in entry.get("patterns", []))), model)


def parts(snapshot_doc: Optional[dict], role: str, provider: Optional[str] = None,
          family: Optional[str] = None) -> list:
    """Selected provenance, with common parts once, then provider and provider--family parts."""
    found = ((snapshot_doc or {}).get("targets") or {}).get(target(role)) or {}
    selected = [None] + ([provider] if provider else [])
    if provider and family:
        selected.append(f"{provider}--{family}")
    return [part for variant in selected for part in found.get("parts", []) if part.get("variant") == variant]


def text(snapshot_doc: Optional[dict], role: str, provider: Optional[str] = None,
         family: Optional[str] = None) -> str:
    """The block text of ``role`` (heading and body), "" when the snapshot has none for it."""
    found = ((snapshot_doc or {}).get("targets") or {}).get(target(role))
    bodies = ([found["text"]] if found and found.get("text") else [])
    bodies += [part["body"] for part in parts(snapshot_doc, role, provider, family) if "variant" in part]
    return HEADING + "\n".join(bodies) if bodies else ""


def origin(snapshot_doc: Optional[dict], role: str, provider: Optional[str] = None,
           family: Optional[str] = None) -> str:
    """The provenance of the block: ``stub:<layer>:<slot>`` of each part, joined."""
    return ",".join(f"stub:{part['layer']}:{part['slot']}"
                    for part in parts(snapshot_doc, role, provider, family)) or "stub"
