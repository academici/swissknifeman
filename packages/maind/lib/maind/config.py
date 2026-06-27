"""Конфиг узла maind: config.json в корне монорепо (primary; legacy .maind.json
подхватывается тем же резолвером) + fallback на legacy .projects.json (brain).

Валидация — на stdlib (без jsonschema): декларативные карты типов + difflib-подсказки,
как в swissknifeman/config.py. load_config возвращает (config, source) для совместимости;
Config.load(env) — обёртка над тем же, инкапсулирует path/source/save и доступ к секциям,
чтобы менять логику конфига в одном месте. Config — подкласс dict (старый доступ
config["projects"] продолжает работать)."""
import copy
import difflib
import json
import os
import re
from pathlib import Path

from .common import detect_project_type, die, sanitize, warn
from .constants import (CODE_GRAPH_DEFAULTS, GRAPH_ADAPTERS, HEARTBEAT_DEFAULT_MS,
                        LEGACY_GRAPH_ADAPTERS, MAX_IDLE_DEFAULT_MS, MEMORY_HTTP_PORT,
                        MEMORY_STREAM_PORT, SERVICE_NAME)

# project.id попадает в scope-маркер памяти `[[s:project:<id>]]` (memory.mark_scope) и в
# имя namespace — поэтому ограничиваем безопасным алфавитом, иначе спецсимволы (']', пробел,
# перевод строки) ломают парсинг scope при recall/forget и могут подменить чужой scope.
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Топ-ключи .maind.json (кроме _-мета). Значение — ожидаемый Python-тип.
TOP_KEYS = {
    "node": dict,
    "memory": dict,
    "graph": dict,
    "code_graph": dict,
    "agents": dict,
    "projects": list,
    "namespaces": dict,
    "integrations": dict,
    "mcp": dict,
    "observability": dict,
    "role_packs": dict,        # роль → agent-pack (вариант C: project.roles → авто-доставка пака)
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
        pid = proj.get("id")
        if isinstance(pid, str) and not PROJECT_ID_RE.match(pid):
            die(f"{cfg_file}: projects[{i}].id = '{pid}' — недопустимый id; разрешены "
                f"только [A-Za-z0-9._-] (id идёт в scope-маркер памяти и namespace)")
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
    Не мутирует переданный config (глубокая копия в начале) и не делит вложенные
    объекты ни с входом, ни с module-level дефолтами."""
    config = copy.deepcopy(config)

    mem = config.get("memory") or {}
    mem.setdefault("enabled", True)
    mem.setdefault("http_port", MEMORY_HTTP_PORT)
    mem.setdefault("stream_port", MEMORY_STREAM_PORT)
    mem.setdefault("config_path", "config/memory/iii-config.yaml")
    mem.setdefault("data_dir", "./data")
    config["memory"] = mem

    gr = config.get("graph") or {}
    gr.setdefault("enabled", True)
    gr.setdefault("adapter", "federation")
    # legacy adapter → федерация (единственная раскладка; движок всегда stdlib)
    if gr["adapter"] in LEGACY_GRAPH_ADAPTERS:
        gr["adapter"] = "federation"
    config["graph"] = gr

    # code_graph: политика код-графа из конфига поверх fallback-дефолтов (top-level ключи).
    # copy.deepcopy(v) — чтобы списки/словари дефолтов не делились с CODE_GRAPH_DEFAULTS.
    cg = config.get("code_graph") or {}
    for k, v in CODE_GRAPH_DEFAULTS.items():
        if k not in cg:
            cg[k] = copy.deepcopy(v)
    config["code_graph"] = cg

    ag = config.get("agents") or {}
    ag.setdefault("registry_enabled", True)
    ag.setdefault("heartbeat_interval_ms", HEARTBEAT_DEFAULT_MS)
    ag.setdefault("max_idle_ms", MAX_IDLE_DEFAULT_MS)
    ag.setdefault("definitions", [])
    config["agents"] = ag

    obs = config.get("observability") or {}
    obs.setdefault("service_name", SERVICE_NAME)
    obs.setdefault("log_level", "info")
    obs.setdefault("metrics_enabled", True)
    obs.setdefault("traces_enabled", False)
    config["observability"] = obs

    config["node"] = config.get("node") or {}
    config["projects"] = config.get("projects") or []
    config["namespaces"] = config.get("namespaces") or {}
    config["integrations"] = config.get("integrations") or {}
    config["mcp"] = config.get("mcp") or {}
    return config


# ── brain .projects.json → maind (реальная схема brain, не из doc'а) ─────────
def _infer_type(local_path):
    """Best-effort тип проекта по маркерам — единый детектор core. Отсутствующий
    путь → 'unknown' (sentinel maind; core всегда отдаёт реальный id)."""
    if not local_path:
        return "unknown"
    p = Path(os.path.expanduser(local_path))
    if not p.is_dir():
        return "unknown"
    return detect_project_type(p)


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
    """Возвращает (config, source). Приоритет: config.json (корень монорепо;
    legacy .maind.json подхватывается тем же резолвером env.default_config) →
    legacy .projects.json (brain, read-only, с предупреждением) → пустой конфиг."""
    primary = env.default_config
    if primary.is_file():
        try:
            config = json.loads(primary.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{primary}: битый JSON: {e}")
        validate_config(config, primary)
        return merge_defaults(config), primary.name

    legacy = env.root / ".projects.json"
    if legacy.is_file():
        warn("config.json не найден — читаю legacy .projects.json (brain) в режиме "
             "read-only; запустите `maind migrate from-brain .projects.json` для "
             "постоянной конфигурации")
        config = {
            "projects": load_brain_projects(legacy),
            "integrations": {"brain": {"enabled": True, "projects_sync": True,
                                       "sync_direction": "import"}},
        }
        return merge_defaults(config), "brain-fallback"

    return merge_defaults({}), "empty"


# ── обёртка над конфигом ─────────────────────────────────────────────────────
class Config(dict):
    """Лёгкая обёртка узлового конфига. Подкласс dict — старый доступ
    (`cfg["projects"]`, `cfg.get(...)`, `cfg.items()`) работает без изменений.
    Сверху: load/save, происхождение (path/source) и аксессоры секций —
    единая точка, где живёт логика конфига (резолв имени файла, валидация, миграция).

    Использование:
        cfg = Config.load(env)          # читает env.default_config (config.json)
        cfg.projects                    # список проектов (или [])
        cfg.project("corex")            # запись проекта по id или None
        cfg.save(env)                   # atomic-запись обратно
    """

    def __init__(self, data=None, *, source="empty", path=None):
        super().__init__(data or {})
        self.source = source        # происхождение: "config.json"|".maind.json"|"brain-fallback"|"empty"
        self.path = path            # Path, откуда прочитан (None для пустого/fallback)

    @classmethod
    def load(cls, env):
        """Прочитать конфиг узла через общий резолвер (config.json в корне монорепо,
        с legacy-fallback). Возвращает Config с заполненными source/path."""
        data, source = load_config(env)
        path = env.default_config if source not in ("brain-fallback", "empty") else None
        return cls(data, source=source, path=path)

    def save(self, env):
        """Atomic-запись конфига обратно (через единственного писателя projects.write_config).
        Перед записью — валидация схемы (Config — подкласс dict, прямые мутации снаружи могли
        нарушить инварианты): не пишем заведомо испорченный state."""
        validate_config(self, str(self.path) if self.path else "in-memory")
        from .projects import write_config
        write_config(env, self)

    # ── аксессоры секций (логику фильтрации/поиска держим здесь) ──────────────
    @property
    def projects(self):
        return list(self.get("projects") or [])

    def project(self, project_id):
        """Запись проекта по id, либо None."""
        for p in self.get("projects") or []:
            if p.get("id") == project_id:
                return p
        return None

    @property
    def namespaces(self):
        return self.get("namespaces") or {}

    @property
    def integrations(self):
        return self.get("integrations") or {}
