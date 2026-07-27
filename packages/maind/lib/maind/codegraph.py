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
from .constants import CODE_GRAPH_DEFAULTS, SERENA_SCHEMA_FIELDS, SERENA_SRC

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
    """Язык(и) для Serena. Приоритет: per-project override (code_language(s), legacy
    graphify_language) → по типу проекта (language_by_type) → по манифесту → None (Serena
    автодетектит сама). Возвращает str | список str | None. Override нужен для смешанных
    репо: type задаёт ОДИН язык (напр. node-package→typescript), а у python-монорепо с
    docs на TS код в основном python — здесь это и чинится без правки общих констант."""
    override = _proj(project, "code_language", "code_languages", "graphify_language")
    if override:
        return override
    lang = (st.get("language_by_type") or {}).get(project.get("type"))
    if lang:
        return lang
    if (path / "composer.json").is_file():
        return "php"
    if (path / "package.json").is_file():
        return "typescript"
    return None


def render_project_yaml(name, language, ignores, initial_prompt, gitignore=True):
    """Полный валидный .serena/project.yml под текущую схему Serena.
    language: str | список str | None.

    Serena `_from_dict` читает РЯД ключей без `.get()` (FIELDS_WITHOUT_DEFAULTS +
    обязательные): language_servers, symbol_info_budget, ignored_paths, fixed_tools,
    excluded_tools, included_optional_tools, read_only, ignore_all_files_in_gitignore,
    initial_prompt, encoding, added_modes, default_modes — отсутствие ЛЮБОГО → KeyError
    при загрузке (НЕ автодетект). Поэтому пишем ПОЛНЫЙ набор с дефолтами Serena, сохраняя
    свои курированные ignored_paths/initial_prompt/language_servers. Дефолты сверены с
    serena/resources/project.template.yml. `language_servers` всегда присутствует (пустой
    список при нераспознанном языке — standalone-тип + пустой репо)."""
    langs = [language] if isinstance(language, str) else (language or [])
    lines = [f'project_name: "{name}"']
    if langs:
        lines += ["language_servers:"] + [f"  - {lang}" for lang in langs]
    else:
        lines += ["language_servers: []"]  # Serena сама определит язык при активации (без KeyError)
    lines += ['encoding: "utf-8"',
              f"ignore_all_files_in_gitignore: {'true' if gitignore else 'false'}",
              "ignored_paths:"]
    lines += [f'  - "{p}"' for p in ignores]
    lines += ["read_only: false",
              # обязательные у текущей Serena — дефолты из её project.template.yml:
              "excluded_tools: []",
              "included_optional_tools: []",
              "fixed_tools: []",
              "default_modes:",
              "added_modes:",
              "symbol_info_budget:",
              f'initial_prompt: "{initial_prompt}"', ""]
    return "\n".join(lines)


def _extract_pin(src):
    """Форма пина `git+URL@REF` → REF (тег или полный SHA, D110 — обе легальны); None, если
    источник не пиннован (нет '@' или пустой хвост)."""
    if not src or "@" not in src:
        return None
    ref = src.rsplit("@", 1)[1]
    return ref or None


def _pin_from_args(args):
    """REF из `--from <SRC>` в списке args serena-команды (args/index_args конфига)."""
    for i, a in enumerate(args or []):
        if a == "--from" and i + 1 < len(args):
            return _extract_pin(args[i + 1])
    return None


def check_schema_connectivity(config):
    """Гейт связности (D111, P5.4): версия Serena, на которую пиннуется флот
    (`constants.SERENA_SRC` + `code_graph.args`/`index_args` конфига), обязана требовать ту же
    схему `.serena/project.yml`, которую реально печатает `render_project_yaml`. Офлайновый и
    детерминированный: сравнивает факты дерева (никакой сети, никакого uvx). НЕ чинит
    расхождение — только называет его; решение (бампнуть пин или откатить шаблон) — за
    владельцем (D111). Возвращает список человекочитаемых расхождений; пустой список — гейт
    зелёный."""
    st = settings(config)
    issues = []

    src_pin = _extract_pin(SERENA_SRC)
    args_pin = _pin_from_args(st.get("args"))
    index_pin = _pin_from_args(st.get("index_args"))

    if src_pin is None:
        issues.append(
            f"пин отсутствует: constants.SERENA_SRC не содержит '@REF' ({SERENA_SRC!r})")
    if st.get("args") and args_pin is None:
        issues.append(
            "пин отсутствует: code_graph.args конфига не содержит '@REF' в '--from'")
    if st.get("index_args") and index_pin is None:
        issues.append(
            "пин отсутствует: code_graph.index_args конфига не содержит '@REF' в '--from'")

    pins = {p for p in (src_pin, args_pin, index_pin) if p is not None}
    if len(pins) > 1:
        issues.append(
            "пины разошлись: constants.SERENA_SRC={!r}, code_graph.args={!r}, "
            "code_graph.index_args={!r} — правь оба места (constants.py и config.json) "
            "одним швом".format(src_pin, args_pin, index_pin))

    # Ключи берём из РЕАЛЬНОГО вывода рендерера (не из его копии здесь) — иначе гейт начал
    # бы проверять свою копию правды, а не настоящую (Code Guidance «Анти-самообман», P5.4).
    sample = render_project_yaml("_schema_probe", None, [], "", gitignore=True)
    rendered_keys = {line.split(":", 1)[0].strip()
                      for line in sample.splitlines()
                      if line and not line[0].isspace() and ":" in line}
    # Только НЕДОСТАЮЩИЕ обязательные ключи — расхождение; необязательные лишние ключи
    # рендерера (напр. project_name) вне FIELDS_WITHOUT_DEFAULTS не считаются (Scope Excluded).
    missing = set(SERENA_SCHEMA_FIELDS) - rendered_keys
    if missing:
        issues.append(
            "схема разошлась: constants.SERENA_SCHEMA_FIELDS (ожидание пина {!r}) требует "
            "{}, которых codegraph.render_project_yaml НЕ печатает (реально печатает {}) — "
            "правь constants.py SERENA_SCHEMA_FIELDS или codegraph.py render_project_yaml, "
            "пока оба места не совпадут".format(
                SERENA_SRC, sorted(missing), sorted(rendered_keys)))

    return issues


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
