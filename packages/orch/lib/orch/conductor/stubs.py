"""Stubs of the orch roles: the additional instructions a person keeps for a role (``aicore.stubs``), frozen per run.

The targets are the model roles that do the work, ``orch.role.<role>``; the registrar (it runs exactly one command the
conductor built) and the report-fixer (it only rewrites a closed block) have none: extra text there would only blur a
side-effect step. A run resolves every target once, when it starts, keeps the result in ``<run>/instructions.json``
and its digest in ``run.json``; every prompt of the run and of its resumes reads that snapshot, never the files again.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from aicore import stubs as core

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
    return core.snapshot(targets(), project, env=env, layers=layers(stubs_settings))


def text(snapshot_doc: Optional[dict], role: str) -> str:
    """The block text of ``role`` (heading and body), "" when the snapshot has none for it."""
    found = ((snapshot_doc or {}).get("targets") or {}).get(target(role))
    return HEADING + found["text"] if found and found.get("text") else ""


def origin(snapshot_doc: Optional[dict], role: str) -> str:
    """The provenance of the block: ``stub:<layer>:<slot>`` of each part, joined."""
    found = ((snapshot_doc or {}).get("targets") or {}).get(target(role)) or {}
    return ",".join(f"stub:{part['layer']}:{part['slot']}" for part in found.get("parts", [])) or "stub"
