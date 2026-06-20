"""maind ecosystem-skill — провиженер управляемого скилла `ecosystem-mcp` в проекты.

Раскатывает <project>/.claude/skills/ecosystem-mcp/SKILL.md — инструкцию агенту о том, что за
MCP-инструменты доступны в проекте (agent-memory/graphify), когда их вызывать, с какими проектами
экосистемы он связан и как чинить связь при сбое. Источник истины — templates/skills/ecosystem-mcp/
SKILL.md в самом maind; файл целиком управляем (идемпотентность по content-hash, как у hook-скрипта).

Подстановки на проект (PROJECT/SCOPE/NAMESPACES/LINKS) считаются из конфига и derive-графа —
LINKS переиспользует seed.linked_projects (DRY с seed-памятью). mode install/update/auto задаёт
область синка, как у health-провиженеров."""
import os
from pathlib import Path

from .health import _act, _file_state, _render, _result
from .namespaces import namespaces_of
from .seed import linked_projects

SKILL_PATH = Path(".claude") / "skills" / "ecosystem-mcp" / "SKILL.md"
TEMPLATE = "skills/ecosystem-mcp/SKILL.md"


def _subst(env, config, project):
    pid = project["id"]
    ns = sorted(namespaces_of(project))
    linked = linked_projects(env, config, project)
    return {
        "PROJECT": pid,
        "SCOPE": project.get("memory_scope") or f"project:{pid}",
        "NAMESPACES": ", ".join(ns),
        "LINKS": ", ".join(linked) if linked else "—",
    }


def apply_ecosystem_skill(env, config, project, mode, dry):
    """Управляемый скилл ecosystem-mcp в <project>/.claude/skills/ecosystem-mcp/SKILL.md."""
    pid = project["id"]
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return _result(pid, "ecosystem-skill", "absent", False, dry, "нет пути")
    content = _render(env, TEMPLATE, _subst(env, config, project))
    target = path / SKILL_PATH
    state = _file_state(target, content)
    if not _act(mode, state):
        return _result(pid, "ecosystem-skill", state, False, dry, str(SKILL_PATH))
    if not dry:
        from .common import backup_file
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            backup_file(target)
        target.write_text(content, encoding="utf-8")
    return _result(pid, "ecosystem-skill", state, True, dry, str(SKILL_PATH))
