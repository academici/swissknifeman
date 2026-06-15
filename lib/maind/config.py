"""Конфиг узла maind: .maind.json (primary) + fallback на legacy .projects.json (brain).

Валидация — на stdlib (без jsonschema): декларативные карты типов + difflib-подсказки,
как в swissknifeman/config.py. load_config возвращает (config, source), где source ∈
{".maind.json", "brain-fallback", "empty"} — чтобы вызывающий знал происхождение."""
import json
import os
from pathlib import Path

from .common import die, sanitize, warn
from .constants import (GRAPH_ADAPTERS, HEARTBEAT_DEFAULT_MS, LEGACY_GRAPH_ADAPTERS,
                        MAX_IDLE_DEFAULT_MS, MEMORY_HTTP_PORT, MEMORY_STREAM_PORT,
                        SERVICE_NAME)

# Топ-ключи .maind.json (кроме _-мета). Значение — ожидаемый Python-тип.
TOP_KEYS = {
    "node": dict,
    "memory": dict,
    "graph": dict,
    "agents": dict,
    "projects": list,
    "namespaces": dict,
    "integrations": dict,
    "mcp": dict,
    "observability": dict,
}

NODE_ROLES = {"primary", "secondary", "mirror"}
PROJECT_STATUSES = {"active", "archived", "planning"}
LOG_LEVELS = {"debug", "info", "warn", "error"}


# ── валидация ───────────────────────────────────────────────────────────────
def _check_section(cfg_file, section, value, types, enums=None):
    """Проверяет dict-секцию: известные ключи — по типу; enum-ключи — по множеству;
    неизвестные ключи — warn (forward-compat, не фатально)."""
    enums = enums or {}
    if not isinstance(value, dict):
        die(f"{cfg_file}: секция '{section}' должна быть объектом")
    for k, v in value.items():
        if k.startswith("_"):
            continue
        if k in enums:
            if v not in enums[k]:
                die(f"{cfg_file}: {section}.{k} = '{v}' — допустимо: "
                    f"{', '.join(sorted(map(str, enums[k])))}")
        elif k in types:
            if not isinstance(v, types[k]):
                die(f"{cfg_file}: {section}.{k} должно быть типа {types[k].__name__}")
        else:
            warn(f"{cfg_file}: неизвестный ключ {section}.{k} (игнорируется)")


def validate_config(config, cfg_file):
    """Бросает die при ошибке схемы. Неизвестные топ-ключи — фатальны (с подсказкой);
    неизвестные вложенные — предупреждение."""
    import difflib
    if not isinstance(config, dict):
        die(f"{cfg_file}: корень конфига должен быть объектом")
    for key in config:
        if key.startswith("_"):
            continue
        if key not in TOP_KEYS:
            hint = difflib.get_close_matches(key, list(TOP_KEYS), n=1)
            suffix = f" — возможно, '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: неизвестный ключ '{key}'{suffix}")
        if not isinstance(config[key], TOP_KEYS[key]):
            want = "массивом" if TOP_KEYS[key] is list else "объектом"
            die(f"{cfg_file}: '{key}' должно быть {want}")

    _check_section(cfg_file, "node", config.get("node", {}),
                   {"id": str, "name": str, "description": str},
                   {"role": NODE_ROLES})
    _check_section(cfg_file, "memory", config.get("memory", {}),
                   {"enabled": bool, "config_path": str, "http_port": int,
                    "stream_port": int, "data_dir": str, "url": str})
    _check_section(cfg_file, "graph", config.get("graph", {}),
                   {"enabled": bool, "adapter": str, "persist": bool,
                    "persist_path": str, "store_layout": str})
    # adapter: канонически {federation, disabled}; legacy (memory/graphify/networkx)
    # принимаем с предупреждением (нормализуется в federation в merge_defaults).
    adapter = (config.get("graph") or {}).get("adapter")
    if adapter is not None and adapter not in GRAPH_ADAPTERS:
        if adapter in LEGACY_GRAPH_ADAPTERS:
            warn(f"{cfg_file}: graph.adapter='{adapter}' устарел → используется "
                 f"'federation' (единственная раскладка; graphify — отдельный MCP-слой)")
        else:
            die(f"{cfg_file}: graph.adapter = '{adapter}' — допустимо: "
                f"{', '.join(sorted(GRAPH_ADAPTERS))}")
    _check_section(cfg_file, "agents", config.get("agents", {}),
                   {"registry_enabled": bool, "heartbeat_interval_ms": int,
                    "max_idle_ms": int, "definitions": list})
    _check_section(cfg_file, "observability", config.get("observability", {}),
                   {"service_name": str, "metrics_enabled": bool,
                    "traces_enabled": bool},
                   {"log_level": LOG_LEVELS})

    registry = config.get("namespaces") or {}
    for i, proj in enumerate(config.get("projects", [])):
        if not isinstance(proj, dict):
            die(f"{cfg_file}: projects[{i}] должно быть объектом")
        for fld in ("id", "name"):
            if fld in proj and not isinstance(proj[fld], str):
                die(f"{cfg_file}: projects[{i}].{fld} должно быть строкой")
        if "status" in proj and proj["status"] not in PROJECT_STATUSES:
            die(f"{cfg_file}: projects[{i}].status = '{proj['status']}' — допустимо: "
                f"{', '.join(sorted(PROJECT_STATUSES))}")
        if "namespaces" in proj:
            ns = proj["namespaces"]
            if not isinstance(ns, list) or not all(isinstance(x, str) for x in ns):
                die(f"{cfg_file}: projects[{i}].namespaces должно быть списком строк")
            for n in ns:                       # реестр задан → подсказка на опечатки
                if registry and n not in registry and n not in ("*", "default"):
                    warn(f"{cfg_file}: projects[{i}] ссылается на незарегистрированный "
                         f"namespace '{n}' (нет в секции namespaces)")


# ── дефолты ─────────────────────────────────────────────────────────────────
def merge_defaults(config):
    """Заполняет обязательные дефолты, чтобы вызывающий код не ловил KeyError.
    Не мутирует переданный config (секции пересобираются в новые объекты)."""
    config = dict(config)

    mem = dict(config.get("memory") or {})
    mem.setdefault("enabled", True)
    mem.setdefault("http_port", MEMORY_HTTP_PORT)
    mem.setdefault("stream_port", MEMORY_STREAM_PORT)
    mem.setdefault("config_path", "config/memory/iii-config.yaml")
    mem.setdefault("data_dir", "./data")
    config["memory"] = mem

    gr = dict(config.get("graph") or {})
    gr.setdefault("enabled", True)
    gr.setdefault("adapter", "federation")
    # legacy adapter → федерация (единственная раскладка; движок всегда stdlib)
    if gr["adapter"] in LEGACY_GRAPH_ADAPTERS:
        gr["adapter"] = "federation"
    config["graph"] = gr

    ag = dict(config.get("agents") or {})
    ag.setdefault("registry_enabled", True)
    ag.setdefault("heartbeat_interval_ms", HEARTBEAT_DEFAULT_MS)
    ag.setdefault("max_idle_ms", MAX_IDLE_DEFAULT_MS)
    ag.setdefault("definitions", [])
    config["agents"] = ag

    obs = dict(config.get("observability") or {})
    obs.setdefault("service_name", SERVICE_NAME)
    obs.setdefault("log_level", "info")
    obs.setdefault("metrics_enabled", True)
    obs.setdefault("traces_enabled", False)
    config["observability"] = obs

    config["node"] = dict(config.get("node") or {})
    config["projects"] = list(config.get("projects") or [])
    config["namespaces"] = dict(config.get("namespaces") or {})
    config["integrations"] = dict(config.get("integrations") or {})
    config["mcp"] = dict(config.get("mcp") or {})
    return config


# ── brain .projects.json → maind (реальная схема brain, не из doc'а) ─────────
def _infer_type(local_path):
    """Best-effort тип проекта по маркерам в репозитории (если путь существует)."""
    if not local_path:
        return "unknown"
    p = Path(os.path.expanduser(local_path))
    if not p.is_dir():
        return "unknown"
    if (p / ".obsidian").is_dir():
        return "obsidian-vault"
    if (p / "composer.json").is_file():
        return "php-package"
    if (p / "package.json").is_file():
        return "node-package"
    return "unknown"


def map_brain_project(bp):
    """Запись brain .projects.json → запись проекта maind (надмножество).

    brain-схема: {name, enabled, vault_path, repo (путь к коду!), folders}.
    Поля id/local_path/type из doc'а в brain отсутствуют — синтезируем."""
    name = bp.get("name", "")
    slug = sanitize(name)
    local_path = bp.get("repo")  # в brain repo = локальный путь к коду
    return {
        "id": slug,
        "name": name,
        "local_path": local_path,
        "vault_path": bp.get("vault_path"),
        "repo": None,                       # GitHub slug owner/repo — нет в brain-кэше
        "type": _infer_type(local_path),
        "enabled": bp.get("enabled", True),
        "docs_folders": bp.get("folders", []),
        "memory_scope": f"project:{slug}" if slug else None,
        "agents": [],
        "skills": [],
        "tags": [],
        "namespaces": [],                   # maind-only; brain не источник namespace
        "status": "active",
        "dependencies": [],
    }


def load_brain_projects(path):
    """Читает brain .projects.json (файл или каталог с ним) → список проектов maind."""
    path = Path(os.path.expanduser(path))
    if path.is_dir():
        path = path / ".projects.json"
    if not path.is_file():
        die(f"не найден brain .projects.json: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path}: битый JSON: {e}")
    return [map_brain_project(bp) for bp in data.get("projects", [])]


# ── загрузка с приоритетом ──────────────────────────────────────────────────
def load_config(env):
    """Возвращает (config, source). Приоритет: .maind.json → legacy .projects.json
    (brain, read-only, с предупреждением о миграции) → пустой конфиг."""
    primary = env.default_config
    if primary.is_file():
        try:
            config = json.loads(primary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{primary}: битый JSON: {e}")
        validate_config(config, primary)
        return merge_defaults(config), ".maind.json"

    legacy = env.root / ".projects.json"
    if legacy.is_file():
        warn(".maind.json не найден — читаю legacy .projects.json (brain) в режиме "
             "read-only; запустите `maind migrate from-brain .projects.json` для "
             "постоянной конфигурации")
        config = {
            "projects": load_brain_projects(legacy),
            "integrations": {"brain": {"enabled": True, "projects_sync": True,
                                       "sync_direction": "import"}},
        }
        return merge_defaults(config), "brain-fallback"

    return merge_defaults({}), "empty"
