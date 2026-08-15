"""Provision managed ecosystem-mcp and ecosystem-setup skills into projects.

Templates are fully managed by content hash. Project substitutions derive from
configuration and graph facts; install/update/auto follows health provisioners.
"""
import os
from pathlib import Path

from ..health import _act, _file_state, _render, _result
from ..namespaces import namespaces_of
from ..seed import linked_projects

SKILL_PATHS = (
    Path(".claude") / "skills" / "ecosystem-mcp" / "SKILL.md",
    Path(".agents") / "skills" / "ecosystem-mcp" / "SKILL.md",
)
TEMPLATE = "skills/ecosystem-mcp/SKILL.md"

SETUP_SKILL_PATHS = (
    Path(".claude") / "skills" / "ecosystem-setup" / "SKILL.md",
    Path(".agents") / "skills" / "ecosystem-setup" / "SKILL.md",
)
SETUP_TEMPLATE = "skills/ecosystem-setup/SKILL.md"


def _subst(env, config, project):
    pid = project["id"]
    ns = sorted(namespaces_of(project))
    linked = linked_projects(env, config, project)
    return {
        "PROJECT": pid,
        "TYPE": project.get("type") or "unknown",
        "SCOPE": project.get("memory_scope") or f"project:{pid}",
        "NAMESPACES": ", ".join(ns),
        "LINKS": ", ".join(linked) if linked else "—",
    }


def _apply_managed_skill(env, config, project, mode, dry, *, label, template, skill_paths):
    """Apply a fully managed, content-hash-idempotent skill."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, label, "absent", False, dry, "нет пути")
    content = _render(env, template, _subst(env, config, project))
    targets = tuple((skill_path, path / skill_path) for skill_path in skill_paths)
    states = tuple(_file_state(target, content) for _skill_path, target in targets)
    selected = tuple((skill_path, target) for (skill_path, target), state in zip(targets, states)
                     if _act(mode, state))
    state = "fresh" if all(item == "fresh" for item in states) else (
        "stale" if "stale" in states else "absent")
    if not dry:
        from ..common import atomic_write_text, backup_file
        for _skill_path, target in selected:
            if target.is_file():
                backup_file(target)
            atomic_write_text(target, content)
    detail = ",".join(str(skill_path) for skill_path in skill_paths)
    return _result(pid, label, state, bool(selected), dry, detail)


def apply_ecosystem_skill(env, config, project, mode, dry):
    """Apply ecosystem-mcp at its managed project path."""
    return _apply_managed_skill(env, config, project, mode, dry,
                                label="ecosystem-skill", template=TEMPLATE,
                                skill_paths=SKILL_PATHS)


def apply_setup_skill(env, config, project, mode, dry):
    """Apply ecosystem-setup at its managed project path."""
    return _apply_managed_skill(env, config, project, mode, dry,
                                label="setup-skill", template=SETUP_TEMPLATE,
                                skill_paths=SETUP_SKILL_PATHS)
