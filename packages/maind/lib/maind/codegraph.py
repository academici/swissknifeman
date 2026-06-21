"""maind code-graph — провиженер дефолтного .serena/project.yml + резолвер политики код-графа.

Когда у проекта включён код-граф (поле `code:true`, legacy-alias `graphify:true`), maind кладёт
ему стартовый `.serena/project.yml`: язык по типу проекта + игноры + initial_prompt. ВСЯ политика
(игноры vendor/packages, команда движка, промпты) берётся из секции `code_graph` конфига
(.maind.example.json), а не хардкодится — здесь только резолвер с per-project override и
legacy-alias `graphify_*` → `code_*`.

Пишем .serena/project.yml ТОЛЬКО если файла ещё нет: после первой активации Serena сама им владеет
(дописывает полный шаблон) — не клобберим. При включении опционально фоном прогреваем индекс
(pre_index) — чтобы первый вызов в сессии не ждал. stdlib-only; внешняя Serena — через subprocess."""
import os
import shutil
import subprocess
from pathlib import Path

from .common import atomic_write_text, warn
from .constants import CODE_GRAPH_DEFAULTS

SERENA_CONFIG = Path(".serena") / "project.yml"


# ── политика код-графа: конфиг + per-project override (alias graphify_* → code_*) ────
def settings(config):
    """Слитая политика код-графа (merge_defaults уже наложил CODE_GRAPH_DEFAULTS)."""
    return config.get("code_graph") or dict(CODE_GRAPH_DEFAULTS)


def _proj(project, *keys, default=None):
    """Первое заданное из per-project ключей (новые code_*, затем legacy graphify_*)."""
    for k in keys:
        if project.get(k) is not None:
            return project[k]
    return default


def enabled(project, st):
    return bool(_proj(project, "code", "graphify", default=st.get("enabled_default", False)))


def command(project, st):
    return _proj(project, "code_command", "graphify_command", default=st["command"])


def cmd_args(project, st):
    return _proj(project, "code_args", "graphify_args", default=st["args"])


def server_name(project, st):
    return _proj(project, "code_server_name", "graphify_server_name", default=st["server_name"])


def is_engine_serena(project, st):
    """Движок — дефолтный Serena (а не переопределённый сторонний MCP)? Только для него
    осмыслен .serena/project.yml."""
    return (command(project, st) == st["command"]
            and server_name(project, st) == st["server_name"])


def is_workspace(project, path):
    """Workspace-режим (единый граф с локальными пакетами): явный флаг code_workspace/
    graphify_workspace, иначе авто — есть каталог packages/ (монорепо или консьюмер с
    подсимлинкованными first-party пакетами; дефолт иначе прячет их исходник)."""
    flag = _proj(project, "code_workspace", "graphify_workspace")
    if flag is not None:
        return bool(flag)
    return (path / "packages").is_dir()


def _infer_language(project, path, st):
    """Язык для Serena: по типу проекта (из конфига), иначе по манифесту. None → Serena сама."""
    lang = (st.get("language_by_type") or {}).get(project.get("type"))
    if lang:
        return lang
    if (path / "composer.json").is_file():
        return "php"
    if (path / "package.json").is_file():
        return "typescript"
    return None


def render_project_yaml(name, language, ignores, initial_prompt, gitignore=True):
    """Минимальный валидный .serena/project.yml (Serena дополнит шаблон при активации)."""
    lines = [f'project_name: "{name}"']
    if language:
        lines += ["languages:", f"  - {language}"]
    lines += [f"ignore_all_files_in_gitignore: {'true' if gitignore else 'false'}",
              "ignored_paths:"]
    lines += [f'  - "{p}"' for p in ignores]
    lines += ["read_only: false", f'initial_prompt: "{initial_prompt}"', ""]
    return "\n".join(lines)


def _maybe_pre_index(st, project, path):
    """Фоновая прогрев-индексация Serena (детач, не блокирует). Тихий skip, если выключено
    в конфиге или движок недоступен."""
    if not st.get("pre_index"):
        return
    cmd = command(project, st)
    if shutil.which(cmd) is None:
        return
    argv = [cmd] + [a.replace("{root}", str(path)) for a in st.get("index_args", [])]
    try:
        subprocess.Popen(argv, cwd=str(path), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as e:
        warn(f"pre-index '{project['id']}' не запустился: {e}")


def apply_serena_config(env, config, project, mode, dry):
    """Положить стартовый .serena/project.yml, если код-граф включён (Serena) и файла нет."""
    pid = project["id"]
    st = settings(config)
    if not enabled(project, st):
        return {"provisioner": "code-graph", "id": pid, "status": "skip",
                "changed": False, "state": "disabled", "detail": "код-граф выключен"}
    if not is_engine_serena(project, st):
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
    ws = is_workspace(project, path)
    override = _proj(project, "code_ignores")
    ignores = override or (st["workspace_ignores"] if ws else st["ignores"])
    prompt = st["workspace_prompt"] if ws else st["initial_prompt"]
    content = render_project_yaml(pid, _infer_language(project, path, st),
                                  ignores, prompt, gitignore=not ws)
    if not dry:
        atomic_write_text(target, content)
        _maybe_pre_index(st, project, path)
    return {"provisioner": "code-graph", "id": pid,
            "status": "dry" if dry else "ok", "changed": not dry,
            "state": "absent", "detail": str(SERENA_CONFIG)}
