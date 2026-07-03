"""maind ecosystem-skill — провиженер управляемого скилла `ecosystem-mcp` в проекты.

Раскатывает <project>/.claude/skills/ecosystem-mcp/SKILL.md — инструкцию агенту о том, что за
MCP-инструменты доступны в проекте (agent-memory/код-граф), когда их вызывать, с какими проектами
экосистемы он связан и как чинить связь при сбое. Источник истины — templates/skills/ecosystem-mcp/
SKILL.md в самом maind; файл целиком управляем (идемпотентность по content-hash, как у hook-скрипта).

Подстановки на проект (PROJECT/SCOPE/NAMESPACES/LINKS) считаются из конфига и derive-графа —
LINKS переиспользует seed.linked_projects (DRY с seed-памятью). mode install/update/auto задаёт
область синка, как у health-провиженеров."""
import os
from pathlib import Path

from ..health import _act, _file_state, _render, _result
from ..namespaces import namespaces_of
from ..seed import linked_projects

SKILL_PATH = Path(".claude") / "skills" / "ecosystem-mcp" / "SKILL.md"
TEMPLATE = "skills/ecosystem-mcp/SKILL.md"

SETUP_SKILL_PATH = Path(".claude") / "skills" / "ecosystem-setup" / "SKILL.md"
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


def _apply_managed_skill(env, config, project, mode, dry, *, label, template, skill_path):
    """Общий провиженер управляемого скилла (целиком управляем, идемпотентность по content-hash)."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, label, "absent", False, dry, "нет пути")
    content = _render(env, template, _subst(env, config, project))
    target = path / skill_path
    state = _file_state(target, content)
    if not _act(mode, state):
        return _result(pid, label, state, False, dry, str(skill_path))
    if not dry:
        from ..common import atomic_write_text, backup_file
        if target.is_file():
            backup_file(target)
        atomic_write_text(target, content)
    return _result(pid, label, state, True, dry, str(skill_path))


def apply_ecosystem_skill(env, config, project, mode, dry):
    """Управляемый скилл ecosystem-mcp в <project>/.claude/skills/ecosystem-mcp/SKILL.md."""
    return _apply_managed_skill(env, config, project, mode, dry,
                                label="ecosystem-skill", template=TEMPLATE,
                                skill_path=SKILL_PATH)


def apply_setup_skill(env, config, project, mode, dry):
    """Управляемый скилл ecosystem-setup (дерево решений тулинга) в
    <project>/.claude/skills/ecosystem-setup/SKILL.md — доезжает до внешних репо."""
    return _apply_managed_skill(env, config, project, mode, dry,
                                label="setup-skill", template=SETUP_TEMPLATE,
                                skill_path=SETUP_SKILL_PATH)
