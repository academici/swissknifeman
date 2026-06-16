"""maind code-graph — провиженер дефолтного .serena/project.yml в проекты с graphify:true.

Когда у проекта включён код-граф на движке Serena, maind кладёт ему стартовый
`.serena/project.yml`: язык по типу проекта + игноры (vendor/node_modules/packages —
симлинкнутые first-party пакеты индексируются как СВОИ проекты, иначе дубли символов и
рекурсивные симлинки зацикливают скан) + initial_prompt (нативно нацеливает агента на
symbol-инструменты). Пишем ТОЛЬКО если файла ещё нет: после первой активации Serena сама
владеет этим файлом (дописывает полный шаблон) — не клобберим её правки.

stdlib-only: project.yml собирается строкой (без сторонних YAML-зависимостей)."""
import os
from pathlib import Path

from .constants import (CODE_MCP_COMMAND, CODE_MCP_NAME, SERENA_IGNORES,
                        SERENA_INITIAL_PROMPT, SERENA_LANG_BY_TYPE,
                        SERENA_WORKSPACE_IGNORES, SERENA_WORKSPACE_PROMPT)

SERENA_CONFIG = Path(".serena") / "project.yml"


def _is_serena(project):
    """Движок код-графа — дефолтный Serena (а не переопределённый сторонний MCP)?"""
    return (project.get("graphify_command", CODE_MCP_COMMAND) == CODE_MCP_COMMAND
            and project.get("graphify_server_name", CODE_MCP_NAME) == CODE_MCP_NAME)


def _infer_language(project, path):
    """Язык для Serena: по типу проекта, иначе по манифесту. None → Serena определит сама."""
    lang = SERENA_LANG_BY_TYPE.get(project.get("type"))
    if lang:
        return lang
    if (path / "composer.json").is_file():
        return "php"
    if (path / "package.json").is_file():
        return "typescript"
    return None


def render_project_yaml(name, language, ignores=SERENA_IGNORES,
                        initial_prompt=SERENA_INITIAL_PROMPT, gitignore=True):
    """Минимальный валидный .serena/project.yml (Serena дополнит шаблон при активации)."""
    lines = [f'project_name: "{name}"']
    if language:
        lines += ["languages:", f"  - {language}"]
    lines += [f"ignore_all_files_in_gitignore: {'true' if gitignore else 'false'}",
              "ignored_paths:"]
    lines += [f'  - "{p}"' for p in ignores]
    lines += ["read_only: false", f'initial_prompt: "{initial_prompt}"', ""]
    return "\n".join(lines)


def apply_serena_config(env, config, project, mode, dry):
    """Положить стартовый .serena/project.yml, если код-граф включён (Serena) и файла нет."""
    pid = project["id"]
    if not project.get("graphify"):
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "disabled", "detail": "graphify выключен"}
    if not _is_serena(project):
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "custom", "detail": "движок не Serena"}
    local = project.get("local_path")
    path = Path(os.path.expanduser(local)) if local else None
    if not path or not path.is_dir():
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "absent", "detail": "нет пути"}
    target = path / SERENA_CONFIG
    if target.exists():  # после активации файлом владеет Serena — не перезаписываем
        return {"provisioner": "code-graph", "id": pid, "status": "ok",
                "changed": False, "state": "present", "detail": str(SERENA_CONFIG)}
    workspace = bool(project.get("graphify_workspace"))
    content = render_project_yaml(
        pid, _infer_language(project, path),
        ignores=SERENA_WORKSPACE_IGNORES if workspace else SERENA_IGNORES,
        initial_prompt=SERENA_WORKSPACE_PROMPT if workspace else SERENA_INITIAL_PROMPT,
        gitignore=not workspace)
    if not dry:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return {"provisioner": "code-graph", "id": pid,
            "status": "dry" if dry else "ok", "changed": not dry,
            "state": "absent", "detail": str(SERENA_CONFIG)}
